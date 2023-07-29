#! /usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
import threading
import time
import logging
import json

try:
    import aiohttp
    from nexia.home import NexiaHome
except ImportError:
    raise ImportError("'Required Python libraries missing.  Run 'pip3 install aiohttp nexia' in Terminal window, then reload plugin.")

kHvacModeEnumToStrMap = {
    indigo.kHvacMode.Cool: "COOL",
    indigo.kHvacMode.Heat: "HEAT",
    indigo.kHvacMode.HeatCool: "AUTO",
    indigo.kHvacMode.Off: "OFF"
}

HVAC_MODE_MAP = {
    'HEAT': indigo.kHvacMode.Heat,
    'COOL': indigo.kHvacMode.Cool,
    'AUTO': indigo.kHvacMode.HeatCool,
    'OFF': indigo.kHvacMode.Off
}

kFanModeEnumToStrMap = {
    indigo.kFanMode.Auto: "AUTO",
    indigo.kFanMode.AlwaysOn: "ON"
}

FAN_MODE_MAP = {
    'AUTO': indigo.kFanMode.Auto,
    'ON': indigo.kFanMode.AlwaysOn
}

class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        pfmt = logging.Formatter('%(asctime)s.%(msecs)03d\t[%(levelname)8s] %(name)20s.%(funcName)-25s%(msg)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(pfmt)
        self.logLevel = int(self.pluginPrefs.get("logLevel", logging.INFO))
        self.indigo_log_handler.setLevel(self.logLevel)
        self.logger.debug(f"logLevel = {self.logLevel}")

        self.updateFrequency = float(self.pluginPrefs.get('updateFrequency', "15")) * 60.0
        self.logger.debug(f"updateFrequency = {self.updateFrequency}")
        self.next_update = time.time() + self.updateFrequency
        self.update_needed = False

        # Adding IndigoLogHandler to the root logger makes it possible to see
        # warnings/errors from async callbacks in the Indigo log, which are otherwise not visible

        logging.getLogger(None).addHandler(self.indigo_log_handler)
        # Since we added this to the root, we don't need it low down in the hierarchy; without this
        # self.logger.*() calls produce duplicates.
        self.logger.removeHandler(self.indigo_log_handler)

        self.nexia_accounts = {}
        self.nexia_thermostats = {}
        self.nexia_zones = {}

        self.event_loop = None
        self.async_thread = None

    ##############################################################################################

    def validatePrefsConfigUi(self, valuesDict):    # noqa
        errorDict = indigo.Dict()

        updateFrequency = int(valuesDict['updateFrequency'])
        if (updateFrequency < 2) or (updateFrequency > 60):
            errorDict['updateFrequency'] = "Update frequency is invalid - enter a valid number (between 2 and 60)"

        if len(errorDict) > 0:
            return False, valuesDict, errorDict

        return True

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            self.logLevel = int(valuesDict.get("logLevel", logging.INFO))

            self.indigo_log_handler.setLevel(self.logLevel)
            self.logger.debug(f"logLevel = {self.logLevel}")

            self.updateFrequency = float(valuesDict['updateFrequency']) * 60.0
            self.logger.debug(f"updateFrequency = {self.updateFrequency}")
            self.next_update = time.time()

    def startup(self):
        self.logger.debug("startup")
        self.async_thread = threading.Thread(target=self.run_async_thread)
        self.async_thread.start()
        self.logger.debug("startup complete")

    def shutdown(self):
        self.logger.debug("shutdown")
        self.event_loop.call_soon_threadsafe(self.event_loop.stop)

    def run_async_thread(self):
        self.logger.debug("run_async_thread starting")
        self.event_loop = asyncio.new_event_loop()
        self.event_loop.set_debug(True)
        self.event_loop.set_exception_handler(self.asyncio_exception_handler)

        asyncio.set_event_loop(self.event_loop)
        self.event_loop.create_task(self.update_task())
        try:
            self.event_loop.run_forever()
        except Exception as exc:
            self.logger.exception(exc)
        self.event_loop.close()
        self.logger.debug("run_async_thread exiting")

    def asyncio_exception_handler(self, loop, context):
        self.logger.exception(f"Event loop exception {context}")

    async def fetch_nexia(self, username, password, brand):
        self.logger.debug(f"fetch_nexia")
        session = aiohttp.ClientSession()
        try:
            nexia_home = NexiaHome(session, username=username, password=password, brand=brand)
            await nexia_home.login()
            await nexia_home.update()
        except Exception as e:
            self.logger.warning(f"fetch_nexia: exception:{e}")
            raise e
        finally:
            await session.close()
        return nexia_home

    async def update_task(self):
        try:
            while True:
                if (time.time() > self.next_update) or self.update_needed:
                    self.logger.debug(f"update_task: running")

                    self.update_needed = False
                    self.next_update = time.time() + self.updateFrequency

                    for dev_id, thermostat in self.nexia_thermostats.items():
                        device = indigo.devices[dev_id]
                        self.logger.debug(f"update_task: updating thermostat {device.name} ({thermostat.get_name()})")

                        update_list = [
                            {'key': "thermostat_name", 'value': thermostat.get_name()},
                            {'key': "thermostat_model", 'value': thermostat.get_model()},
                            {'key': "thermostat_firmware", 'value': thermostat.get_firmware()},
                            {'key': "thermostat_type", 'value': thermostat.get_type()},
                            {'key': "fan_mode", 'value': thermostat.get_fan_mode()},
                            {'key': "fan_speed", 'value': thermostat.get_fan_speed_setpoint()},
                            {'key': "outdoor_temperature", 'value': thermostat.get_outdoor_temperature()},
                            {'key': "dehumidify_setpoint", 'value': thermostat.get_dehumidify_setpoint()},
                            {'key': "compressor_speed", 'value': thermostat.get_current_compressor_speed()},
                            {'key': "requested_compressor_speed", 'value': thermostat.get_requested_compressor_speed()},
                            {'key': "air_cleaner_mode", 'value': thermostat.get_air_cleaner_mode()},
                            {'key': "has_outdoor_temperature", 'value': thermostat.has_outdoor_temperature()},
                            {'key': "has_relative_humidity", 'value': thermostat.has_relative_humidity()},
                            {'key': "has_variable_speed_compressor", 'value': thermostat.has_variable_speed_compressor()},
                            {'key': "has_emergency_heat", 'value': thermostat.has_emergency_heat()},
                            {'key': "has_variable_fan_speed", 'value': thermostat.has_variable_fan_speed()},
                            {'key': "is_blower_active", 'value': thermostat.is_blower_active()},
                            {'key': "is_emergency_heat_active", 'value': (thermostat.is_emergency_heat_active() if thermostat.has_emergency_heat() else "")},
                        ]
                        try:
                            device.updateStatesOnServer(update_list)
                        except Exception as e:
                            self.logger.error(f"{device.name}: failed to update states: {e}")

                    for zone_id, zone in self.nexia_zones.items():
                        device = indigo.devices[zone_id]
                        self.logger.debug(f"update_task: updating zone {device.name} ({zone.get_name()})")

                        update_list = [
                            {'key': "temperatureInput1", 'value': zone.get_temperature()},
                            {'key': "setpointHeat", 'value': zone.get_heating_setpoint()},
                            {'key': "setpointCool", 'value': zone.get_cooling_setpoint()},
                            {'key': "hvacOperationMode", 'value': HVAC_MODE_MAP[zone.get_current_mode()]},
                            {'key': "zone_name", 'value': zone.get_name()},
                            {'key': "requested_mode", 'value': zone.get_requested_mode()},
                            {'key': "is_calling", 'value': zone.is_calling()},
                            {'key': "is_in_permanent_hold", 'value': zone.is_in_permanent_hold()},
                        ]
                        try:
                            device.updateStatesOnServer(update_list)
                        except Exception as e:
                            self.logger.error(f"{device.name}: failed to update states: {e}")

                await asyncio.sleep(2.0)
        except self.StopThread:
            pass
    ########################################

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        self.logger.debug(f"validateDeviceConfigUi: valuesDict = {valuesDict}, typeId = {typeId}, devId = {devId}")
        errorsDict = indigo.Dict()
        valid = True

        if typeId == "NexiaAccount":
            if len(valuesDict["username"]) == 0:
                errorsDict["username"] = "No username provided"
                self.logger.warning("validateDeviceConfigUi - No username provided")
                valid = False

            if len(valuesDict["password"]) == 0:
                errorsDict["password"] = "No password provided"
                self.logger.warning("validateDeviceConfigUi - No password provided")
                valid = False

        elif typeId == "NexiaThermostat":
            if valuesDict["nexia_account"] == 0:
                errorsDict["nexia_account"] = "No Trane Home Account Specified"
                self.logger.warning("validateDeviceConfigUi - No Trane Home Account Specified")
                valid = False

            if len(valuesDict["nexia_thermostat"]) == 0:
                errorsDict["nexia_thermostat"] = "No Thermostat Specified"
                self.logger.warning("validateDeviceConfigUi - No Thermostat Specified")
                valid = False

            valuesDict["address"] = valuesDict["nexia_thermostat"]

        elif typeId == "NexiaZone":
            if valuesDict["nexia_account"] == 0:
                errorsDict["nexia_account"] = "No Trane Home Account Specified"
                self.logger.warning("validateDeviceConfigUi - No Trane Home Account Specified")
                valid = False

            if len(valuesDict["nexia_thermostat"]) == 0:
                errorsDict["nexia_thermostat"] = "No Thermostat Specified"
                self.logger.warning("validateDeviceConfigUi - No Thermostat Specified")
                valid = False

            if len(valuesDict["nexia_zone"]) == 0:
                errorsDict["nexia_zone"] = "No Zone Specified"
                self.logger.warning("validateDeviceConfigUi - No Zone Specified")
                valid = False

            valuesDict["address"] = f"{valuesDict['nexia_thermostat']}:{valuesDict['nexia_zone']}"

        return valid, valuesDict, errorsDict

    ########################################

    def deviceStartComm(self, dev):

        self.logger.info(f"{dev.name}: Starting {dev.deviceTypeId} Device {dev.id}")

        if dev.deviceTypeId == 'NexiaAccount':
            nexia_home = asyncio.run(self.fetch_nexia(dev.pluginProps['username'], dev.pluginProps['password'], dev.pluginProps.get('brand', 'nexia')))
            if not nexia_home:
                self.logger.warning(f"{dev.name}: deviceStartComm error creating NexiaAccount device")
                dev.updateStateOnServer(key="authenticated", value=False)
                return

            for thermostat_id in nexia_home.get_thermostat_ids():
                thermostat = nexia_home.get_thermostat_by_id(thermostat_id)
                self.logger.threaddebug(f"\n{thermostat.get_name()}:\n{json.dumps(thermostat._thermostat_json, indent=4)}")
                for zone_id in thermostat.get_zone_ids():
                    zone = thermostat.get_zone_by_id(zone_id)
                    self.logger.threaddebug(f"\n{zone.get_name()}:\n{json.dumps(zone._zone_json, indent=4)}")

            self.nexia_accounts[dev.id] = nexia_home
            dev.updateStateOnServer(key="authenticated", value=True)

        elif dev.deviceTypeId == 'NexiaThermostat':

            try:
                account = self.nexia_accounts[int(dev.pluginProps['nexia_account'])]
                thermostat = account.get_thermostat_by_id(int(dev.pluginProps['nexia_thermostat']))
            except KeyError:
                self.logger.warning(f"{dev.name}: deviceStartComm error getting thermostat {dev.pluginProps['nexia_thermostat']}")
            else:
                self.logger.debug(f"Loaded Thermostat {thermostat.get_name()}")
                self.nexia_thermostats[dev.id] = thermostat
                self.update_needed = True

        elif dev.deviceTypeId == 'NexiaZone':

            try:
                account = self.nexia_accounts[int(dev.pluginProps['nexia_account'])]
                thermostat = account.get_thermostat_by_id(int(dev.pluginProps['nexia_thermostat']))
                self.logger.debug(f"Using Thermostat {thermostat.get_name()}")
                zone = thermostat.get_zone_by_id(int(dev.pluginProps['nexia_zone']))
            except KeyError:
                self.logger.warning(f"{dev.name}: deviceStartComm error getting zone {dev.pluginProps['nexia_zone']}")
            else:
                self.logger.debug(f"Loaded Zone {zone.get_name()}")
                self.nexia_zones[dev.id] = zone
                self.update_needed = True

    def deviceStopComm(self, dev):

        self.logger.info(f"{dev.name}: Stopping {dev.deviceTypeId} Device {dev.id}")

        if dev.deviceTypeId == 'NexiaAccount':
            if dev.id in self.nexia_accounts:
                del self.nexia_accounts[dev.id]

        elif dev.deviceTypeId == 'NexiaThermostat':
            if dev.id in self.nexia_thermostats:
                del self.nexia_thermostats[dev.id]

        elif dev.deviceTypeId == 'NexiaZone':
            if dev.id in self.nexia_zones:
                del self.nexia_zones[dev.id]

    ########################################
    #
    # device UI methods
    #
    ########################################

    def get_account_list(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.logger.threaddebug(f"get_account_list: typeId = {typeId}, targetId = {targetId}, valuesDict = {valuesDict}")
        accounts = [
            (accountID, indigo.devices[int(accountID)].name)
            for accountID in self.nexia_accounts
        ]
        self.logger.threaddebug(f"get_account_list: accounts = {accounts}")
        return accounts

    def get_thermostat_list(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.logger.debug(f"get_thermostat_list: typeId = {typeId}, targetId = {targetId}, filter = {filter}, valuesDict = {valuesDict}")

        try:
            nexia_home = self.nexia_accounts[int(valuesDict["nexia_account"])]
        except Exception as e:
            self.logger.debug("get_thermostat_list: no active accounts, returning empty list")
            return []

        active_stats = [
            (int(indigo.devices[dev].pluginProps["nexia_thermostat"]))
            for dev in self.nexia_thermostats
        ]
        self.logger.debug(f"get_thermostat_list: active_stats = {active_stats}")

        device_list = []
        for thermostat_id in nexia_home.get_thermostat_ids():
            name = nexia_home.get_thermostat_by_id(thermostat_id).get_name()
            if filter == "Available" and thermostat_id not in active_stats:
                device_list.append((thermostat_id, name))
            elif filter == "Active" and thermostat_id in active_stats:
                device_list.append((thermostat_id, name))
            elif filter == "All":
                device_list.append((thermostat_id, name))

#        if targetId:
#            try:
#                dev = indigo.devices[targetId]
#                device_list.insert(0, (dev.pluginProps["nexia_thermostat"], dev.name))
#            except (Exception,):
#                pass

        self.logger.debug(f"get_thermostat_list: device_list for {typeId} ({filter}) = {device_list}")
        return device_list

    def get_zone_list(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.logger.debug(f"get_zone_list: typeId = {typeId}, targetId = {targetId}, filter = {filter}, valuesDict = {valuesDict}")

        try:
            nexia_home = self.nexia_accounts[int(valuesDict["nexia_account"])]
        except (Exception,):
            self.logger.debug("get_zone_list: no active accounts, returning empty list")
            return []

        try:
            thermostat_id = int(valuesDict["nexia_thermostat"])
        except (Exception,):
            self.logger.debug("get_zone_list: no thermostat selected, returning empty list")
            return []

        active_zones = [
            (int(indigo.devices[dev].pluginProps["nexia_zone"]))
            for dev in self.nexia_zones
        ]
        self.logger.debug(f"get_zone_list: active_zones = {active_zones}")

        device_list = []
        thermostat = nexia_home.get_thermostat_by_id(thermostat_id)
        for zone_id in thermostat.get_zone_ids():
            name = thermostat.get_zone_by_id(zone_id).get_name()
            if filter == "Available" and zone_id not in active_zones:
                device_list.append((zone_id, name))
            elif filter == "Active" and zone_id in active_zones:
                device_list.append((zone_id, name))
            elif filter == "All":
                device_list.append((zone_id, name))

 #       if targetId:
 #           try:
 #               dev = indigo.devices[targetId]
 #               device_list.insert(0, (dev.pluginProps["nexia_zone"], dev.name))
 #           except (Exception,):
 #               pass

        self.logger.debug(f"get_zone_list: device_list for {typeId} ({filter}) = {device_list}")
        return device_list

        # doesn't do anything, just needed to force other menus to dynamically refresh

    def menuChanged(self, valuesDict=None, typeId=None, devId=None):    # noqa
        return valuesDict

    ########################################

    ########################################
    # Thermostat Action callbacks
    ########################################

    def actionControlUniversal(self, action, dev):
        self.logger.warning(f"{dev.name}: Unimplemented action.deviceAction: {action.deviceAction}")

    def actionControlThermostat(self, action, dev):
        self.logger.debug(f"{dev.name}: action.thermostatAction: {action.thermostatAction}")

        if action.thermostatAction == indigo.kThermostatAction.SetHvacMode:
            hvac_mode = kHvacModeEnumToStrMap.get(action.actionMode, "unknown")
            self.logger.debug(f"{dev.name}: HVAC mode set to: {hvac_mode}")

            self.nexia_zones[dev.id].set_zone_mode(hvac_mode)
            self.update_needed = True

        elif action.thermostatAction == indigo.kThermostatAction.SetFanMode:

            fan_mode = kFanModeEnumToStrMap.get(action.actionMode, "auto")
            self.logger.debug(f"{dev.name}: Fan mode set to: {fan_mode}")
            self.nexia_thermostats[dev.id].set_fan_mode(fan_mode)
            self.update_needed = True

        elif action.thermostatAction == indigo.kThermostatAction.SetCoolSetpoint:
            newSetpoint = action.actionValue
            self.handleChangeSetpointAction(dev, newSetpoint, "setpointCool")

        elif action.thermostatAction == indigo.kThermostatAction.SetHeatSetpoint:
            newSetpoint = action.actionValue
            self.handleChangeSetpointAction(dev, newSetpoint, "setpointHeat")

        elif action.thermostatAction == indigo.kThermostatAction.DecreaseCoolSetpoint:
            newSetpoint = dev.coolSetpoint - action.actionValue
            self.handleChangeSetpointAction(dev, newSetpoint, "setpointCool")

        elif action.thermostatAction == indigo.kThermostatAction.IncreaseCoolSetpoint:
            newSetpoint = dev.coolSetpoint + action.actionValue
            self.handleChangeSetpointAction(dev, newSetpoint, "setpointCool")

        elif action.thermostatAction == indigo.kThermostatAction.DecreaseHeatSetpoint:
            newSetpoint = dev.heatSetpoint - action.actionValue
            self.handleChangeSetpointAction(dev, newSetpoint, "setpointHeat")

        elif action.thermostatAction == indigo.kThermostatAction.IncreaseHeatSetpoint:
            newSetpoint = dev.heatSetpoint + action.actionValue
            self.handleChangeSetpointAction(dev, newSetpoint, "setpointHeat")

        elif action.thermostatAction in [indigo.kThermostatAction.RequestStatusAll, indigo.kThermostatAction.RequestMode,
                                         indigo.kThermostatAction.RequestEquipmentState, indigo.kThermostatAction.RequestTemperatures,
                                         indigo.kThermostatAction.RequestHumidities,
                                         indigo.kThermostatAction.RequestDeadbands, indigo.kThermostatAction.RequestSetpoints]:
            self.update_needed = True

        else:
            self.logger.warning(f"{dev.name}: Unimplemented action.thermostatAction: {action.thermostatAction}")

    ########################################
    # Process action request from Indigo Server to change a cool/heat setpoint.
    ########################################

    def handleChangeSetpointAction(self, dev, newSetpoint, stateKey):
        if dev.deviceTypeId != "NexiaZone":
            self.logger.warning(f'{dev.name}: Invalid {stateKey} command.  Only Zone devices have setpoints.')
            return

        if stateKey == "setpointCool":
            self.logger.info(f'{dev.name}: set cool to: {newSetpoint} and leave heat at: {dev.heatSetpoint}')
            self.nexia_zones[dev.id].set_zone_heat_cool_temp(dev.heatSetpoint, newSetpoint)
        elif stateKey == "setpointHeat":
            self.logger.info(f'{dev.name}: set heat to: {newSetpoint} and leave cool at: {dev.coolSetpoint}')
            self.nexia_zones[dev.id].set_zone_heat_cool_temp(newSetpoint, dev.coolSetpoint)
        else:
            self.logger.error(f'{dev.name}: handleChangeSetpointAction Invalid operation - {stateKey}')
        self.update_needed = True

    ########################################
    # Menu callbacks
    ########################################

    def menuResumeAllSchedules(self):
        self.logger.debug("menuResumeAllSchedules")
        for devId, zone in self.nexia_zones.items():
            zone.call_return_to_schedule()
        return True

    def menuResumeSchedule(self, valuesDict, typeId):
        self.logger.debug("menuResumeSchedule")
        try:
            deviceId = int(valuesDict["targetDevice"])
        except (Exception,):
            self.logger.error("Bad Device specified for Resume Schedule operation")
            return False

        self.nexia_zones[deviceId].call_return_to_schedule()
        return True

    ########################################
    # Action callbacks
    ########################################

    # Thermostat callbacks

    def airCleanerModeGenerator(self, filter, valuesDict, typeId, targetId):
        self.logger.debug(f"airCleanerModeGenerator: typeId = {typeId}, targetId = {targetId}")
        return [(mode, mode) for mode in NexiaAccount.AIR_CLEANER_MODES]

    def setAirCleanerModeAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        mode = pluginAction.props.get("cleaner_mode", "auto")
        self.logger.debug(f"{thermostatDevice.name}: actionSetAirCleanerMode: {mode}")
        self.nexia_thermostats[thermostatDevice.id].set_air_cleaner(mode)

    def setDehumidifySetpointAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        setpoint = pluginAction.props.get("dehumidify_setpoint", "50")
        self.logger.debug(f"{thermostatDevice.name}: setDehumidifySetpointAction: {setpoint}%")
        self.nexia_thermostats[thermostatDevice.id].set_dehumidify_setpoint(float(setpoint) / 100.0)

    def setFollowScheduleAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        enabled = pluginAction.props.get("schedules_enabled", False)
        self.logger.debug(f"{thermostatDevice.name}: setFollowScheduleAction: {enabled}")
        self.nexia_thermostats[thermostatDevice.id].set_follow_schedule(enabled)

    # Zone callbacks

    def zonePresetGenerator(self, filter, valuesDict, typeId, targetId):
        self.logger.debug(f"zonePresetGenerator: typeId = {typeId}, targetId = {targetId}, valuesDict= {valuesDict}")
        zone = self.nexia_zones[int(targetId)]
        return [(preset, preset) for preset in zone.get_zone_presets()]

    def zoneReturnToScheduleAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        self.logger.debug(f"{thermostatDevice.name}: zoneReturnToScheduleAction")
        self.nexia_zones[thermostatDevice.id].call_return_to_schedule()

    def zoneSetHoldAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        self.logger.debug(f"{thermostatDevice.name}: zoneSetHoldAction")
        self.nexia_zones[thermostatDevice.id].call_permanent_hold()

    def zoneSetPresetAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        preset = pluginAction.props.get("zone_preset", None)
        self.logger.debug(f"{thermostatDevice.name}: zoneSetPresetAction: {preset}")
        self.nexia_zones[thermostatDevice.id].set_zone_preset(preset)

    ############################################################################
    # 
    #     def pickThermostat(self, filter=None, valuesDict=None, typeId=0):
    #         retList = []
    #         for dev in indigo.devices.iter("self"):
    #             if dev.deviceTypeId == 'NexiaThermostat':
    #                 retList.append((dev.id, dev.name))
    #         retList.sort(key=lambda tup: tup[1])
    #         return retList

    def pickZone(self, filter=None, valuesDict=None, typeId=0): # noqa
        retList = []
        for dev in indigo.devices.iter("self"):
            if dev.deviceTypeId == 'NexiaZone':
                retList.append((dev.id, dev.name))
        retList.sort(key=lambda tup: tup[1])
        return retList

############################################################################
