#! /usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
import threading
import time
import logging
import json

try:
    from aiohttp import ClientSession
    from nexia.home import NexiaHome
    from nexia.const import AIR_CLEANER_MODES
except ImportError:
    raise ImportError("'Required Python libraries missing.  Run 'pip3 install aiohttp nexia' in Terminal window, then reload plugin.")

kHvacModeEnumToStrMap = {
    indigo.kHvacMode.Cool: "COOL",
    indigo.kHvacMode.Heat: "HEAT",
    indigo.kHvacMode.HeatCool: "AUTO",
    indigo.kHvacMode.Off: "OFF"
}

kHvacModeStrToEnumMap = {
    'HEAT': indigo.kHvacMode.Heat,
    'COOL': indigo.kHvacMode.Cool,
    'AUTO': indigo.kHvacMode.HeatCool,
    'OFF': indigo.kHvacMode.Off
}

kFanModeEnumToStrMap = {
    indigo.kFanMode.Auto: "AUTO",
    indigo.kFanMode.AlwaysOn: "ON"
}

kFanModeStrToEnumMap = {
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

        self.pluginPrefs = pluginPrefs

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

        self.nexia_thermostats = {}
        self.nexia_zones = {}

        self.nexia_home = None
        self.event_loop = None
        self.async_thread = None
        self.session = None

    ##############################################################################################

    def validatePrefsConfigUi(self, valuesDict):    # noqa
        errorDict = indigo.Dict()

        username = valuesDict['username']
        if len(username) == 0:
            errorDict['username'] = "Username is required"

        password = valuesDict['password']
        if len(password) == 0:
            errorDict['password'] = "Password is required"

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
        asyncio.set_event_loop(self.event_loop)
        self.event_loop.set_debug(True)
        self.event_loop.set_exception_handler(self.asyncio_exception_handler)

        try:
            self.event_loop.run_until_complete(self.async_main())
        except Exception as exc:
            self.logger.exception(exc)
        self.event_loop.close()
        self.logger.debug("run_async_thread exiting")

    def asyncio_exception_handler(self, loop, context):
        self.logger.exception(f"Event loop exception {context}")

    async def async_main(self):
        self.logger.debug(f"async_main: running")
        """Create the aiohttp session and run."""
        async with ClientSession() as self.session:

            try:

                self.nexia_home = NexiaHome(self.session, username=self.pluginPrefs.get("username"), password=self.pluginPrefs.get("password"), brand=self.pluginPrefs.get("brand"))
                await self.nexia_home.login()
                await self.nexia_home.update()
            except Exception as e:
                self.logger.warning(f"async_main: exception:{e}")
                raise e

            if not self.nexia_home:
                self.logger.warning(f"async_main: no nexia_home")
                return

            while True:
                if (time.time() > self.next_update) or self.update_needed:

                    self.update_needed = False
                    self.next_update = time.time() + self.updateFrequency
                    await self.do_update()

                await asyncio.sleep(2.0)
                if self.stopThread:
                    self.logger.debug("async_main: stopping")
                    break

    async def do_update(self):
        await self.nexia_home.update()

        for dev_id in self.nexia_thermostats:
            device = indigo.devices[dev_id]
            thermostat_id = int(device.pluginProps['nexia_thermostat'])
            self.logger.debug(f"{device.name}: starting update for thermostat {thermostat_id}")
            thermostat = self.nexia_home.get_thermostat_by_id(thermostat_id)
            update_list = [
                {'key': "thermostat_name", 'value': thermostat.get_name()},
                {'key': "thermostat_model", 'value': thermostat.get_model()},
                {'key': "thermostat_firmware", 'value': thermostat.get_firmware()},
                {'key': "thermostat_type", 'value': thermostat.get_type()},
                {'key': "thermostat_id", 'value': thermostat.get_device_id()},
                {'key': "system_status", 'value': thermostat.get_system_status()},

                {'key': "fan_mode", 'value': thermostat.get_fan_mode()},
                {'key': "has_variable_fan_speed", 'value': thermostat.has_variable_fan_speed()},
                {'key': "fan_speed", 'value': (thermostat.get_fan_speed_setpoint() if thermostat.has_variable_fan_speed() else "")},

                {'key': "has_relative_humidity", 'value': thermostat.has_relative_humidity()},
                {'key': "relative_humidity", 'value': thermostat.get_relative_humidity() if thermostat.has_relative_humidity() else ""},
                {'key': "has_dehumidify_support", 'value': thermostat.has_dehumidify_support()},
                {'key': "dehumidify_setpoint", 'value': thermostat.get_dehumidify_setpoint() if thermostat.has_dehumidify_support() else ""},
                {'key': "has_humidify_support", 'value': thermostat.has_humidify_support()},
                {'key': "humidify_setpoint", 'value': thermostat.get_humidify_setpoint() if thermostat.has_humidify_support() else ""},

                {'key': "has_variable_speed_compressor", 'value': thermostat.has_variable_speed_compressor()},
                {'key': "compressor_speed_current", 'value': thermostat.get_current_compressor_speed() if thermostat.has_variable_speed_compressor() else ""},
                {'key': "compressor_speed_requested", 'value': thermostat.get_requested_compressor_speed() if thermostat.has_variable_speed_compressor() else ""},

                {'key': "has_outdoor_temperature", 'value': thermostat.has_outdoor_temperature()},
                {'key': "outdoor_temperature", 'value': thermostat.get_outdoor_temperature() if thermostat.has_outdoor_temperature() else ""},

                {'key': "has_emergency_heat", 'value': thermostat.has_emergency_heat()},
                {'key': "is_emergency_heat_active", 'value': (thermostat.is_emergency_heat_active() if thermostat.has_emergency_heat() else "")},

                {'key': "has_air_cleaner", 'value': thermostat.has_air_cleaner()},
                {'key': "air_cleaner_mode", 'value': thermostat.get_air_cleaner_mode() if thermostat.has_air_cleaner() else ""},

                {'key': "is_blower_active", 'value': thermostat.is_blower_active()},
            ]
            try:
                self.logger.threaddebug(f"do_update: update_list: {update_list}")
                device.updateStatesOnServer(update_list)
            except Exception as e:
                self.logger.error(f"{device.name}: failed to update states: {e}")

        for zone_id in self.nexia_zones:
            device = indigo.devices[zone_id]
            thermostat_id = int(device.pluginProps['nexia_thermostat'])
            zone_id = int(device.pluginProps['nexia_zone'])
            self.logger.debug(f"{device.name}: starting update for zone {thermostat_id}:{zone_id}")
            thermostat = self.nexia_home.get_thermostat_by_id(thermostat_id)
            zone = thermostat.get_zone_by_id(zone_id)
            update_list = [
                {'key': "temperatureInput1", 'value': zone.get_temperature()},
                {'key': "setpointHeat", 'value': zone.get_heating_setpoint()},
                {'key': "setpointCool", 'value': zone.get_cooling_setpoint()},
                {'key': "hvacOperationMode", 'value': kHvacModeStrToEnumMap[zone.get_current_mode()]},
                {'key': "zone_name", 'value': zone.get_name()},
                {'key': "zone_status", 'value': zone.get_status()},
                {'key': "zone_preset", 'value': zone.get_preset()},
                {'key': "zone_setpoint_status", 'value': zone.get_setpoint_status()},
                {'key': "zone_mode_current", 'value': zone.get_current_mode()},
                {'key': "zone_mode_requested", 'value': zone.get_requested_mode()},
                {'key': "is_calling", 'value': zone.is_calling()},
                {'key': "is_native_zone", 'value': zone.is_native_zone()},
                {'key': "is_in_permanent_hold", 'value': zone.is_in_permanent_hold()},
            ]
            try:
                self.logger.threaddebug(f"do_update: update_list: {update_list}")
                device.updateStatesOnServer(update_list)
            except Exception as e:
                self.logger.error(f"{device.name}: failed to update states: {e}")

    ########################################

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        self.logger.debug(f"validateDeviceConfigUi: valuesDict = {valuesDict}, typeId = {typeId}, devId = {devId}")
        errorsDict = indigo.Dict()
        valid = True

        if typeId == "NexiaThermostat":
            if len(valuesDict["nexia_thermostat"]) == 0:
                errorsDict["nexia_thermostat"] = "No Thermostat Specified"
                self.logger.warning("validateDeviceConfigUi - No Thermostat Specified")
                valid = False
            valuesDict["address"] = valuesDict["nexia_thermostat"]

        elif typeId == "NexiaZone":
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

    def deviceStartComm(self, device):

        self.logger.info(f"{device.name}: Starting {device.deviceTypeId} Device {device.id}")
        device.stateListOrDisplayStateIdChanged()

        if device.deviceTypeId == 'NexiaThermostat':

            self.nexia_thermostats[device.id] = device.name
            self.update_needed = True

        elif device.deviceTypeId == 'NexiaZone':

            self.nexia_zones[device.id] = device.name
            self.update_needed = True

    def deviceStopComm(self, device):

        self.logger.info(f"{device.name}: Stopping {device.deviceTypeId} Device {device.id}")

        if device.deviceTypeId == 'NexiaThermostat':
            if device.id in self.nexia_thermostats:
                del self.nexia_thermostats[device.id]

        elif device.deviceTypeId == 'NexiaZone':
            if device.id in self.nexia_zones:
                del self.nexia_zones[device.id]

    ########################################
    #
    # device UI methods
    #
    ########################################

    def get_thermostat_list(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.logger.threaddebug(f"get_thermostat_list: typeId = {typeId}, targetId = {targetId}, valuesDict = {valuesDict}")

        device_list = []
        for thermostat_id in self.nexia_home.get_thermostat_ids():
            name = self.nexia_home.get_thermostat_by_id(thermostat_id).get_name()
            device_list.append((thermostat_id, name))

        self.logger.threaddebug(f"get_thermostat_list: device_list for {typeId} ({filter}) = {device_list}")
        return device_list

    def get_zone_list(self, filter="",  valuesDict=None, typeId="", targetId=0):
        self.logger.threaddebug(f"get_zone_list: typeId = {typeId}, targetId = {targetId}, filter = {filter}, valuesDict = {valuesDict}")

        try:
            thermostat_id = int(valuesDict["nexia_thermostat"])
        except (Exception,):
            self.logger.debug("get_zone_list: no thermostat selected, returning empty list")
            return []

        device_list = []
        thermostat = self.nexia_home.get_thermostat_by_id(thermostat_id)
        for zone_id in thermostat.get_zone_ids():
            name = thermostat.get_zone_by_id(zone_id).get_name()
            device_list.append((zone_id, name))

        self.logger.threaddebug(f"get_zone_list: device_list for {typeId} ({filter}) = {device_list}")
        return device_list

        # doesn't do anything, just needed to force other menus to dynamically refresh

    def menuChanged(self, valuesDict=None, typeId=None, devId=None):    # noqa
        return valuesDict

    ########################################

    ########################################
    # Thermostat Action callbacks
    ########################################

    def actionControlUniversal(self, action, device):
        self.logger.warning(f"{device.name}: Unimplemented action.deviceAction: {action.deviceAction}")

    def actionControlThermostat(self, action, device):
        self.logger.debug(f"{device.name}: action.thermostatAction: {action.thermostatAction}")

        if action.thermostatAction == indigo.kThermostatAction.SetHvacMode:
            if device.deviceTypeId == 'NexiaThermostat':
                self.logger.warning(f"{device.name}: SetHvacMode not supported for NexiaThermostat devices")
                return

            hvac_mode = kHvacModeEnumToStrMap.get(action.actionMode, "unknown")
            self.logger.debug(f"{device.name}: HVAC mode set to: {hvac_mode}")
            thermostat = self.nexia_home.get_thermostat_by_id(int(device.pluginProps['nexia_thermostat']))
            zone = thermostat.get_zone_by_id(int(device.pluginProps['nexia_zone']))
            asyncio.run_coroutine_threadsafe(zone.set_mode(hvac_mode), self.event_loop)
            self.update_needed = True

        elif action.thermostatAction == indigo.kThermostatAction.SetFanMode:

            fan_mode = kFanModeEnumToStrMap.get(action.actionMode, "auto")
            self.logger.debug(f"{device.name}: Fan mode set to: {fan_mode}")
            thermostat = self.nexia_home.get_thermostat_by_id(int(device.pluginProps['nexia_thermostat']))
            asyncio.run_coroutine_threadsafe(thermostat.set_fan_mode(fan_mode), self.event_loop)
            self.update_needed = True

        elif action.thermostatAction == indigo.kThermostatAction.SetCoolSetpoint:
            newSetpoint = action.actionValue
            self.handleChangeSetpointAction(device, newSetpoint, "setpointCool")

        elif action.thermostatAction == indigo.kThermostatAction.SetHeatSetpoint:
            newSetpoint = action.actionValue
            self.handleChangeSetpointAction(device, newSetpoint, "setpointHeat")

        elif action.thermostatAction == indigo.kThermostatAction.DecreaseCoolSetpoint:
            newSetpoint = device.coolSetpoint - action.actionValue
            self.handleChangeSetpointAction(device, newSetpoint, "setpointCool")

        elif action.thermostatAction == indigo.kThermostatAction.IncreaseCoolSetpoint:
            newSetpoint = device.coolSetpoint + action.actionValue
            self.handleChangeSetpointAction(device, newSetpoint, "setpointCool")

        elif action.thermostatAction == indigo.kThermostatAction.DecreaseHeatSetpoint:
            newSetpoint = device.heatSetpoint - action.actionValue
            self.handleChangeSetpointAction(device, newSetpoint, "setpointHeat")

        elif action.thermostatAction == indigo.kThermostatAction.IncreaseHeatSetpoint:
            newSetpoint = device.heatSetpoint + action.actionValue
            self.handleChangeSetpointAction(device, newSetpoint, "setpointHeat")

        elif action.thermostatAction in [indigo.kThermostatAction.RequestStatusAll, indigo.kThermostatAction.RequestMode,
                                         indigo.kThermostatAction.RequestEquipmentState, indigo.kThermostatAction.RequestTemperatures,
                                         indigo.kThermostatAction.RequestHumidities,
                                         indigo.kThermostatAction.RequestDeadbands, indigo.kThermostatAction.RequestSetpoints]:
            self.update_needed = True

        else:
            self.logger.warning(f"{device.name}: Unimplemented action.thermostatAction: {action.thermostatAction}")

    ########################################
    # Process action request from Indigo Server to change a cool/heat setpoint.
    ########################################

    def handleChangeSetpointAction(self, device, newSetpoint, stateKey):
        if device.deviceTypeId != "NexiaZone":
            self.logger.warning(f'{device.name}: Invalid {stateKey} command.  Only Zone devices have setpoints.')
            return

        self.logger.debug(f"{device.name}: handleChangeSetpointAction: setpoint {newSetpoint} {stateKey}")
        thermostat = self.nexia_home.get_thermostat_by_id(int(device.pluginProps['nexia_thermostat']))
        zone = thermostat.get_zone_by_id(int(device.pluginProps['nexia_zone']))

        if stateKey == "setpointCool":
            self.logger.info(f'{device.name}: set cool to: {newSetpoint} and leave heat at: {device.heatSetpoint}')
            asyncio.run_coroutine_threadsafe(zone.set_heat_cool_temp(device.heatSetpoint, newSetpoint), self.event_loop)
        elif stateKey == "setpointHeat":
            self.logger.info(f'{device.name}: set heat to: {newSetpoint} and leave cool at: {device.coolSetpoint}')
            asyncio.run_coroutine_threadsafe(zone.set_heat_cool_temp(newSetpoint, device.coolSetpoint), self.event_loop)
        else:
            self.logger.error(f'{device.name}: handleChangeSetpointAction Invalid operation - {stateKey}')
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

    def menuDumpNexia(self):
        for thermostat_id in self.nexia_home.get_thermostat_ids():
            thermostat = self.nexia_home.get_thermostat_by_id(thermostat_id)
            self.logger.info(f"\n{thermostat.get_name()}:\n{json.dumps(thermostat._thermostat_json, sort_keys=True, indent=4, separators=(',', ': '))}")
            for zone_id in thermostat.get_zone_ids():
                zone = thermostat.get_zone_by_id(zone_id)
                self.logger.info(f"\n{zone.get_name()}:\n{json.dumps(zone._zone_json, sort_keys=True, indent=4, separators=(',', ': '))}")
        return True

    ########################################
    # Action callbacks
    ########################################

    # Thermostat callbacks

    def airCleanerModeGenerator(self, filter, valuesDict, typeId, targetId):
        self.logger.debug(f"airCleanerModeGenerator: typeId = {typeId}, targetId = {targetId}")
        return [(mode, mode) for mode in AIR_CLEANER_MODES]

    def setAirCleanerModeAction(self, pluginAction, thermostat_device, callerWaitingForResult):
        mode = pluginAction.props.get("cleaner_mode", "auto")
        self.logger.debug(f"{thermostat_device.name}: actionSetAirCleanerMode: {mode}")
        thermostat = self.nexia_home.get_thermostat_by_id(int(thermostat_device.pluginProps['nexia_thermostat']))
        if thermostat.has_air_cleaner():
            asyncio.run_coroutine_threadsafe(thermostat.set_air_cleaner(mode), self.event_loop)
        else:
            self.logger.warning(f"{thermostat_device.name}: actionSetAirCleanerMode: System does not have an air cleaner.")

    def setDehumidifySetpointAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        setpoint = pluginAction.props.get("dehumidify_setpoint", "50")
        self.logger.debug(f"{thermostatDevice.name}: setDehumidifySetpointAction: {setpoint}%")
        thermostat = self.nexia_home.get_thermostat_by_id(int(thermostatDevice.pluginProps['nexia_thermostat']))
        if thermostat.has_dehumidify_support():
            asyncio.run_coroutine_threadsafe(thermostat.set_dehumidify_setpoint(float(setpoint) / 100.0), self.event_loop)
        else:
            self.logger.warning(f"{thermostatDevice.name}: setDehumidifySetpointAction: System does not have dehumidify support.")

    def setFollowScheduleAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        enabled = pluginAction.props.get("schedules_enabled", False)
        self.logger.debug(f"{thermostatDevice.name}: setFollowScheduleAction: {enabled}")
        thermostat = self.nexia_home.get_thermostat_by_id(int(thermostatDevice.pluginProps['nexia_thermostat']))
        asyncio.run_coroutine_threadsafe(thermostat.set_follow_schedule(enabled), self.event_loop)

    # Zone callbacks

    def zonePresetGenerator(self, filter, valuesDict, typeId, targetId):
        self.logger.debug(f"zonePresetGenerator: typeId = {typeId}, targetId = {targetId}, valuesDict= {valuesDict}")
        zone_device = indigo.devices[int(targetId)]
        thermostat = self.nexia_home.get_thermostat_by_id(int(zone_device.pluginProps['nexia_thermostat']))
        zone = thermostat.get_zone_by_id(int(zone_device.pluginProps['nexia_zone']))
        return [(preset, preset) for preset in zone.get_presets()]

    def zoneSetPresetAction(self, pluginAction, zone_device, callerWaitingForResult):
        preset = pluginAction.props.get("zone_preset", None)
        self.logger.debug(f"{zone_device.name}: zoneSetPresetAction: {preset}")
        thermostat = self.nexia_home.get_thermostat_by_id(int(zone_device.pluginProps['nexia_thermostat']))
        zone = thermostat.get_zone_by_id(int(zone_device.pluginProps['nexia_zone']))
        asyncio.run_coroutine_threadsafe(zone.set_preset(preset), self.event_loop)

    def zoneReturnToScheduleAction(self, pluginAction, zone_device, callerWaitingForResult):
        self.logger.debug(f"{zone_device.name}: zoneReturnToScheduleAction")
        thermostat = self.nexia_home.get_thermostat_by_id(int(zone_device.pluginProps['nexia_thermostat']))
        zone = thermostat.get_zone_by_id(int(zone_device.pluginProps['nexia_zone']))
        asyncio.run_coroutine_threadsafe(zone.call_return_to_schedule(), self.event_loop)

    def zoneSetHoldAction(self, pluginAction, zone_device, callerWaitingForResult):
        self.logger.debug(f"{zone_device.name}: zoneSetHoldAction")
        thermostat = self.nexia_home.get_thermostat_by_id(int(zone_device.pluginProps['nexia_thermostat']))
        zone = thermostat.get_zone_by_id(int(zone_device.pluginProps['nexia_zone']))
        asyncio.run_coroutine_threadsafe(zone.call_permanent_hold(), self.event_loop)

    # def pickZone(self, filter=None, valuesDict=None, typeId=0): # noqa
    #     retList = []
    #     for dev in indigo.devices.iter("self"):
    #         if dev.deviceTypeId == 'NexiaZone':
    #             retList.append((dev.id, dev.name))
    #     retList.sort(key=lambda tup: tup[1])
    #     return retList

############################################################################
