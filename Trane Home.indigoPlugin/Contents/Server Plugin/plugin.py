#! /usr/bin/env python
# -*- coding: utf-8 -*-

import time
import logging
import json
import platform

from nexia_thermostat import NexiaThermostat as NexiaAccount
from nexia_devices import NexiaThermostat, NexiaZone

kHvacModeEnumToStrMap = {
    indigo.kHvacMode.Cool               : u"cool",
    indigo.kHvacMode.Heat               : u"heat",
    indigo.kHvacMode.HeatCool           : u"auto",
    indigo.kHvacMode.Off                : u"off",
    indigo.kHvacMode.ProgramHeat        : u"program heat",
    indigo.kHvacMode.ProgramCool        : u"program cool",
    indigo.kHvacMode.ProgramHeatCool    : u"program auto"
}

kFanModeEnumToStrMap = {
    indigo.kFanMode.Auto            : u"auto",
    indigo.kFanMode.AlwaysOn        : u"on"
}

minMacOS = "10.13"
def versiontuple(v):
    return tuple(map(int, (v.split("."))))
    
class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        pfmt = logging.Formatter('%(asctime)s.%(msecs)03d\t[%(levelname)8s] %(name)20s.%(funcName)-25s%(msg)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(pfmt)

        try:
            self.logLevel = int(self.pluginPrefs[u"logLevel"])
        except:
            self.logLevel = logging.INFO
        self.indigo_log_handler.setLevel(self.logLevel)
        self.logger.debug(u"logLevel = " + str(self.logLevel))


    def startup(self):
        self.logger.info(u"Starting Trane Home")
       
        macOS = platform.mac_ver()[0]
        self.logger.debug(u"macOS {}, Indigo {}".format(macOS, indigo.server.version))
        if versiontuple(macOS) < versiontuple(minMacOS):
            self.logger.error(u"Unsupported macOS version! {}".format(macOS))
   
                   
        self.updateFrequency = float(self.pluginPrefs.get('updateFrequency', "15")) *  60.0
        self.logger.debug(u"updateFrequency = {}".format(self.updateFrequency))
        self.next_update = time.time() + self.updateFrequency
        self.update_needed = False
        
        self.nexia_accounts = {}
        self.nexia_thermostats = {}
        self.nexia_zones = {}
        
    def shutdown(self):
        self.logger.info(u"Stopping Trane Home")
        

    def validatePrefsConfigUi(self, valuesDict):
        errorDict = indigo.Dict()

        updateFrequency = int(valuesDict['updateFrequency'])
        if (updateFrequency < 2) or (updateFrequency > 60):
            errorDict['updateFrequency'] = u"Update frequency is invalid - enter a valid number (between 2 and 60)"

        if len(errorDict) > 0:
            return (False, valuesDict, errorDict)

        return True

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            try:
                self.logLevel = int(valuesDict[u"logLevel"])
            except:
                self.logLevel = logging.INFO
            self.indigo_log_handler.setLevel(self.logLevel)
            self.logger.debug(u"logLevel = " + str(self.logLevel))

            self.updateFrequency = float(valuesDict['updateFrequency']) * 60.0
            self.logger.debug(u"updateFrequency = {}".format(self.updateFrequency))
            self.next_update = time.time()


    ########################################
        
    def runConcurrentThread(self):
        self.logger.debug(u"runConcurrentThread starting")
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
            self.logger.debug(u"runConcurrentThread ending")
            pass

                
    ########################################
    #
    # device UI methods
    #
    ########################################

    def get_account_list(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.logger.threaddebug("get_account_list: typeId = {}, targetId = {}, valuesDict = {}".format(typeId, targetId, valuesDict))
        accounts = [
            (accountID, indigo.devices[int(accountID)].name)
            for accountID in self.nexia_accounts
        ]
        self.logger.threaddebug("get_account_list: accounts = {}".format(accounts))
        return accounts
        

    def get_thermostat_list(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.logger.debug("get_thermostat_list: typeId = {}, targetId = {}, filter = {}, valuesDict = {}".format(typeId, targetId, filter, valuesDict))

        try:
            account = self.nexia_accounts[int(valuesDict["nexia_account"])]
        except:
            self.logger.debug("get_thermostat_list: no active accounts, returning empty list")
            return []
        
        active_stats =  [
            (int(indigo.devices[dev].pluginProps["nexia_thermostat"]))
            for dev in self.nexia_thermostats
        ]
        self.logger.debug("get_thermostat_list: active_stats = {}".format(active_stats))

        device_list =[]
        for thermostat_id in account.get_thermostat_ids():
            name = account.get_thermostat_name(thermostat_id)
            if filter == "Available" and thermostat_id not in active_stats:
                device_list.append((thermostat_id, name))
            elif filter == "Active" and thermostat_id in active_stats:
                device_list.append((thermostat_id, name))
            elif filter == "All":
                device_list.append((thermostat_id, name))
                                                    
        self.logger.debug("get_thermostat_list: device_list for {} ({}) = {}".format(typeId, filter, device_list))
        return device_list     
        
        
    def get_zone_list(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.logger.debug("get_zone_list: typeId = {}, targetId = {}, filter = {}, valuesDict = {}".format(typeId, targetId, filter, valuesDict))

        try:
            account = self.nexia_accounts[int(valuesDict["nexia_account"])]
        except:
            self.logger.debug("get_zone_list: no active accounts, returning empty list")
            return []

        try:                       
            thermostat_id = int(valuesDict["nexia_thermostat"])
        except:
            self.logger.debug("get_zone_list: no thermostat selected, returning empty list")
            return []
                                
        active_zones =  [
            (int(indigo.devices[dev].pluginProps["nexia_zone"]))
            for dev in self.nexia_zones
        ]
        self.logger.debug("get_zone_list: active_zones = {}".format(active_zones))

        device_list =[]
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
            except:
                pass
                        
        self.logger.debug("get_zone_list: device_list for {} ({}) = {}".format(typeId, filter, device_list))
        return device_list     



    # doesn't do anything, just needed to force other menus to dynamically refresh
    def menuChanged(self, valuesDict = None, typeId = None, devId = None):
        return valuesDict


    ########################################

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        self.logger.debug("validateDeviceConfigUi: valuesDict = {}, typeId = {}, devId = {}".format(valuesDict, typeId, devId))
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
        
            valuesDict["address"] = "{}:{}".format(valuesDict["nexia_thermostat"], valuesDict["nexia_zone"])
            
        return (valid, valuesDict, errorsDict)
        
    ########################################
        
    def deviceStartComm(self, dev):

        self.logger.info(u"{}: Starting {} Device {}".format(dev.name, dev.deviceTypeId, dev.id))
      
        if dev.deviceTypeId == 'NexiaAccount':
            account = NexiaAccount(int(dev.pluginProps['house_id']), 
                                username=dev.pluginProps['username'], 
                                password=dev.pluginProps['password'], 
                                auto_login=True, 
                                update_rate="Disable")
            if not account:
                self.logger.warning("{}: deviceStartComm error creating device".format(dev.name))
                dev.updateStateOnServer(key="authenticated", value=False)
                return
           
            self.nexia_accounts[dev.id] = account
            dev.updateStateOnServer(key="authenticated", value=True)
                            
        elif dev.deviceTypeId == 'NexiaThermostat':

            thermostat =  NexiaThermostat(dev.id, int(dev.pluginProps['nexia_account']), int(dev.pluginProps['nexia_thermostat']))
            if not thermostat:
                self.logger.warning("{}: deviceStartComm error creating device".format(dev.name))
                return

            self.nexia_thermostats[dev.id] = thermostat
            self.update_needed = True
            
        elif dev.deviceTypeId == 'NexiaZone':

            zone =  NexiaZone(dev.id, int(dev.pluginProps['nexia_account']), int(dev.pluginProps['nexia_thermostat']), int(dev.pluginProps['nexia_zone']))
            if not zone:
                self.logger.warning("{}: deviceStartComm error creating device".format(dev.name))
                return

            self.nexia_zones[dev.id] = zone
            self.update_needed = True
            

    def deviceStopComm(self, dev):

        self.logger.info(u"{}: Stopping {} Device {}".format( dev.name, dev.deviceTypeId, dev.id))

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
        self.logger.debug(u"{}: action.actionControlUniversal: {}".format(dev.name, action.deviceAction))
        self.logger.warning(u"{}: Unimplemented action.deviceAction: {}".format(dev.name, action.deviceAction))


    def actionControlThermostat(self, action, dev):
        self.logger.debug(u"{}: action.thermostatAction: {}".format(dev.name, action.thermostatAction))
        
       ###### SET HVAC MODE ######
        if action.thermostatAction == indigo.kThermostatAction.SetHvacMode:
            hvac_mode = kHvacModeEnumToStrMap.get(action.actionMode, u"unknown")
            self.logger.debug(u"{}: HVAC mode set to: {}".format(dev.name, hvac_mode))

            self.nexia_zones[dev.id].set_zone_mode(hvac_mode)
            self.update_needed = True

        ###### SET FAN MODE ######
        elif action.thermostatAction == indigo.kThermostatAction.SetFanMode:
       
            fan_mode = kFanModeEnumToStrMap.get(action.actionMode, u"auto")
            self.logger.debug(u"{}: Fan mode set to: {}".format(dev.name, fan_mode))
            self.nexia_thermostats[dev.id].set_fan_mode(fan_mode)        
            self.update_needed = True

        ###### SET COOL SETPOINT ######
        elif action.thermostatAction == indigo.kThermostatAction.SetCoolSetpoint:
            newSetpoint = action.actionValue
            self.handleChangeSetpointAction(dev, newSetpoint, u"setpointCool")

        ###### SET HEAT SETPOINT ######
        elif action.thermostatAction == indigo.kThermostatAction.SetHeatSetpoint:
            newSetpoint = action.actionValue
            self.handleChangeSetpointAction(dev, newSetpoint, u"setpointHeat")

        ###### DECREASE/INCREASE COOL SETPOINT ######
        elif action.thermostatAction == indigo.kThermostatAction.DecreaseCoolSetpoint:
            newSetpoint = dev.coolSetpoint - action.actionValue
            self.handleChangeSetpointAction(dev, newSetpoint, u"setpointCool")

        elif action.thermostatAction == indigo.kThermostatAction.IncreaseCoolSetpoint:
            newSetpoint = dev.coolSetpoint + action.actionValue
            self.handleChangeSetpointAction(dev, newSetpoint, u"setpointCool")

        ###### DECREASE/INCREASE HEAT SETPOINT ######
        elif action.thermostatAction == indigo.kThermostatAction.DecreaseHeatSetpoint:
            newSetpoint = dev.heatSetpoint - action.actionValue
            self.handleChangeSetpointAction(dev, newSetpoint, u"setpointHeat")

        elif action.thermostatAction == indigo.kThermostatAction.IncreaseHeatSetpoint:
            newSetpoint = dev.heatSetpoint + action.actionValue
            self.handleChangeSetpointAction(dev, newSetpoint, u"setpointHeat")

        ###### REQUEST STATE UPDATES ######
        elif action.thermostatAction in [indigo.kThermostatAction.RequestStatusAll, indigo.kThermostatAction.RequestMode,
         indigo.kThermostatAction.RequestEquipmentState, indigo.kThermostatAction.RequestTemperatures, indigo.kThermostatAction.RequestHumidities,
         indigo.kThermostatAction.RequestDeadbands, indigo.kThermostatAction.RequestSetpoints]:
            self.update_needed = True

        ###### UNTRAPPED CONDITIONS ######
        else:
            self.logger.warning(u"{}: Unimplemented action.thermostatAction: {}".format(dev.name, action.thermostatAction))

    ########################################
    # Process action request from Indigo Server to change a cool/heat setpoint.
    ########################################
    
    def handleChangeSetpointAction(self, dev, newSetpoint, stateKey):
        if dev.deviceTypeId != "NexiaZone":
            self.logger.warning(u'{}: Invalid {} command.  Only Zone devices have setpoints.'.format(dev.name, stateKey))
            return
            
        if stateKey == u"setpointCool":
            self.logger.info(u'{}: set cool to: {} and leave heat at: {}'.format(dev.name, newSetpoint, dev.heatSetpoint))
            self.nexia_zones[dev.id].set_zone_heat_cool_temp(dev.heatSetpoint, newSetpoint)
        elif stateKey == u"setpointHeat":
            self.logger.info(u'{}: set heat to: {} and leave cool at: {}'.format(dev.name, newSetpoint,dev.coolSetpoint))
            self.nexia_zones[dev.id].set_zone_heat_cool_temp(newSetpoint, dev.coolSetpoint)
        else:
            self.logger.error(u'{}: handleChangeSetpointAction Invalid operation - {}'.format(dev.name, stateKey))       
        self.update_needed = True

    ########################################
    # Menu callbacks
    ########################################
    
    def menuResumeAllSchedules(self):
        self.logger.debug(u"menuResumeAllSchedules")
        for devId, zone in self.nexia_zones.items():
            zone.call_return_to_schedule()
        return True


    def menuResumeSchedule(self, valuesDict, typeId):
        self.logger.debug(u"menuResumeSchedule")
        try:
            deviceId = int(valuesDict["targetDevice"])
        except:
            self.logger.error(u"Bad Device specified for Resume Schedule operation")
            return False

        self.nexia_zones[deviceId].call_return_to_schedule()
        return True
        
    def menuDumpThermostat(self):
        self.logger.debug(u"menuDumpThermostat")
        for accountID, account in self.nexia_accounts.items():
            if indigo.devices[accountID].states['authenticated']:
                data = account._get_thermostat_json()
                self.logger.info("{}: Data Dump\n{}".format(indigo.devices[accountID].name, json.dumps(data, sort_keys=True, indent=4, separators=(',', ': '))))
            else:
                self.logger.info("{}: Data Dump aborted, account not authenticated.".format(indigo.devices[accountID].name))
            
        return True
        

    ########################################
    # Action callbacks
    ########################################

    # Thermostat callbacks
    
    def airCleanerModeGenerator(self, filter, valuesDict, typeId, targetId):                                                                                                                 
        self.logger.debug(u"airCleanerModeGenerator: typeId = {}, targetId = {}".format(typeId, targetId)) 
        return [ (mode, mode) for mode in NexiaAccount.AIR_CLEANER_MODES ]

    def setAirCleanerModeAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        mode = pluginAction.props.get("cleaner_mode", "auto")
        self.logger.debug(u"{}: actionSetAirCleanerMode: {}".format(thermostatDevice.name, mode))
        self.nexia_thermostats[thermostatDevice.id].set_air_cleaner(mode)
                 
    def setDehumidifySetpointAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        setpoint = pluginAction.props.get("dehumidify_setpoint", "50")
        self.logger.debug(u"{}: setDehumidifySetpointAction: {}%".format(thermostatDevice.name, setpoint))
        self.nexia_thermostats[thermostatDevice.id].set_dehumidify_setpoint(float(setpoint) / 100.0)
                
    def setFollowScheduleAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        enabled = pluginAction.props.get("schedules_enabled", False)
        self.logger.debug(u"{}: setFollowScheduleAction: {}".format(thermostatDevice.name, enabled))
        self.nexia_thermostats[thermostatDevice.id].set_follow_schedule(enabled)
 
    # Zone callbacks
    
    def zonePresetGenerator(self, filter, valuesDict, typeId, targetId):                                                                                                                 
        self.logger.debug(u"zonePresetGenerator: typeId = {}, targetId = {}, valuesDict= {}".format(typeId, targetId, valuesDict)) 
        zone = self.nexia_zones[int(targetId)]
        return [ (preset, preset) for preset in zone.get_zone_presets() ]
               
    def zoneReturnToScheduleAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        self.logger.debug(u"{}: zoneReturnToScheduleAction".format(thermostatDevice.name))
        self.nexia_zones[thermostatDevice.id].call_return_to_schedule()
        
    def zoneSetHoldAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        self.logger.debug(u"{}: zoneSetHoldAction".format(thermostatDevice.name))
        self.nexia_zones[thermostatDevice.id].call_permanent_hold()
                
    def zoneSetPresetAction(self, pluginAction, thermostatDevice, callerWaitingForResult):
        preset = pluginAction.props.get("zone_preset", None)
        self.logger.debug(u"{}: zoneSetPresetAction: {}".format(thermostatDevice.name, preset))
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
 
    def pickZone(self, filter=None, valuesDict=None, typeId=0):
        retList = []
        for dev in indigo.devices.iter("self"):
            if dev.deviceTypeId == 'NexiaZone':
                retList.append((dev.id, dev.name))
        retList.sort(key=lambda tup: tup[1])
        return retList

############################################################################



