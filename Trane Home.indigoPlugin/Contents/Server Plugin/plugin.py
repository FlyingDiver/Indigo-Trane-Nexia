#! /usr/bin/env python
# -*- coding: utf-8 -*-

import time
import logging
import json
import platform

from nexia_thermostat import NexiaThermostat as NexiaAccount
from nexia_devices import NexiaThermostat, NexiaZone

kHvacModeEnumToStrMap = {
    indigo.kHvacMode.Cool: "cool",
    indigo.kHvacMode.Heat: "heat",
    indigo.kHvacMode.HeatCool: "auto",
    indigo.kHvacMode.Off: "off",
    indigo.kHvacMode.ProgramHeat: "program heat",
    indigo.kHvacMode.ProgramCool: "program cool",
    indigo.kHvacMode.ProgramHeatCool: "program auto"
}

kFanModeEnumToStrMap = {
    indigo.kFanMode.Auto: "auto",
    indigo.kFanMode.AlwaysOn: "on"
}

minMacOS = "10.13"


def versiontuple(v):
    return tuple(map(int, (v.split("."))))


class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        pfmt = logging.Formatter('%(asctime)s.%(msecs)03d\t[%(levelname)8s] %(name)20s.%(funcName)-25s%(msg)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(pfmt)
        self.logLevel = int(self.pluginPrefs.get("logLevel", logging.INFO))
        self.indigo_log_handler.setLevel(self.logLevel)
        self.logger.debug(f"logLevel = {self.logLevel}")

        macOS = platform.mac_ver()[0]
        self.logger.debug(f"macOS {macOS}, Indigo {indigo.server.version}")
        if versiontuple(macOS) < versiontuple(minMacOS):
            self.logger.error(f"Unsupported macOS version! {macOS}")

        self.updateFrequency = float(self.pluginPrefs.get('updateFrequency', "15")) * 60.0
        self.logger.debug(f"updateFrequency = {self.updateFrequency}")
        self.next_update = time.time() + self.updateFrequency
        self.update_needed = False

        self.nexia_accounts = {}
        self.nexia_thermostats = {}
        self.nexia_zones = {}

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

    ########################################

    def runConcurrentThread(self):
        try:
            while True:
                if (time.time() > self.next_update) or self.update_needed:

                    self.update_needed = False
                    self.next_update = time.time() + self.updateFrequency

                    for thermostat in self.nexia_thermostats.values():
                        thermostat.update()

                    for zone in self.nexia_zones.values():
                        zone.update()

                self.sleep(2.0)
        except self.StopThread:
            pass

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
            account = self.nexia_accounts[int(valuesDict["nexia_account"])]
        except (Exception,):
            self.logger.debug("get_thermostat_list: no active accounts, returning empty list")
            return []

        active_stats = [
            (int(indigo.devices[dev].pluginProps["nexia_thermostat"]))
            for dev in self.nexia_thermostats
        ]
        self.logger.debug(f"get_thermostat_list: active_stats = {active_stats}")

        device_list = []
        for thermostat_id in account.get_thermostat_ids():
            name = account.get_thermostat_name(thermostat_id)
            if filter == "Available" and thermostat_id not in active_stats:
                device_list.append((thermostat_id, name))
            elif filter == "Active" and thermostat_id in active_stats:
                device_list.append((thermostat_id, name))
            elif filter == "All":
                device_list.append((thermostat_id, name))

        self.logger.debug(f"get_thermostat_list: device_list for {typeId} ({filter}) = {device_list}")
        return device_list

    def get_zone_list(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.logger.debug(f"get_zone_list: typeId = {typeId}, targetId = {targetId}, filter = {filter}, valuesDict = {valuesDict}")

        try:
            account = self.nexia_accounts[int(valuesDict["nexia_account"])]
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
        for zone_id in account.get_zone_ids(thermostat_id):
            name = account.get_zone_name(thermostat_id, zone_id)
            if filter == "Available" and zone_id not in active_zones:
                device_list.append((zone_id, name))
            elif filter == "Active" and zone_id in active_zones:
                device_list.append((zone_id, name))
            elif filter == "All":
                device_list.append((zone_id, name))

        if targetId:
            try:
                dev = indigo.devices[targetId]
                device_list.insert(0, (dev.pluginProps["nexia_zone"], dev.name))
            except (Exception,):
                pass

        self.logger.debug(f"get_zone_list: device_list for {typeId} ({filter}) = {device_list}")
        return device_list

        # doesn't do anything, just needed to force other menus to dynamically refresh

    def menuChanged(self, valuesDict=None, typeId=None, devId=None):    # noqa
        return valuesDict

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

            if len(valuesDict["house_id"]) == 0:
                errorsDict["house_id"] = "No house_id provided"
                self.logger.warning("validateDeviceConfigUi - No house_id provided")
                valid = False

            valuesDict["address"] = valuesDict["house_id"]

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
            account = NexiaAccount(int(dev.pluginProps['house_id']),
                                   username=dev.pluginProps['username'],
                                   password=dev.pluginProps['password'],
                                   auto_login=True,
                                   update_rate="Disable")
            if not account:
                self.logger.warning(f"{dev.name}: deviceStartComm error creating device")
                dev.updateStateOnServer(key="authenticated", value=False)
                return

            self.nexia_accounts[dev.id] = account
            dev.updateStateOnServer(key="authenticated", value=True)

        elif dev.deviceTypeId == 'NexiaThermostat':

            thermostat = NexiaThermostat(dev.id, int(dev.pluginProps['nexia_account']), int(dev.pluginProps['nexia_thermostat']))
            if not thermostat:
                self.logger.warning(f"{dev.name}: deviceStartComm error creating device")
                return

            self.nexia_thermostats[dev.id] = thermostat
            self.update_needed = True

        elif dev.deviceTypeId == 'NexiaZone':

            zone = NexiaZone(dev.id, int(dev.pluginProps['nexia_account']), int(dev.pluginProps['nexia_thermostat']),
                             int(dev.pluginProps['nexia_zone']))
            if not zone:
                self.logger.warning(f"{dev.name}: deviceStartComm error creating device")
                return

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

    def menuDumpThermostat(self):
        self.logger.debug("menuDumpThermostat")
        for accountID, account in self.nexia_accounts.items():
            if indigo.devices[accountID].states['authenticated']:
                data = account._get_thermostat_json()
                self.logger.info(
                    f"{indigo.devices[accountID].name}: Data Dump\n{json.dumps(data, sort_keys=True, indent=4, separators=(',', ': '))}")
            else:
                self.logger.info(f"{indigo.devices[accountID].name}: Data Dump aborted, account not authenticated.")

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
