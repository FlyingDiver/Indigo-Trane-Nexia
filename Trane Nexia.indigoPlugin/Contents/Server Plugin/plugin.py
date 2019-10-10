#! /usr/bin/env python
# -*- coding: utf-8 -*-

import time
import logging
import json
import platform

from nexia_thermostat import NexiaThermostat

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
        self.logger.info(u"Starting Trane Nexia")
       
        macOS = platform.mac_ver()[0]
        self.logger.debug(u"macOS {}, Indigo {}".format(macOS, indigo.server.version))
        if int(macOS[3:5]) < 13:
            self.logger.error(u"Unsupported macOS version! {}".format(macOS))
                
        self.updateFrequency = float(self.pluginPrefs.get('updateFrequency', "15")) *  60.0
        self.logger.debug(u"updateFrequency = " + str(self.updateFrequency))
        self.next_update = time.time() + self.updateFrequency
        
        self.nexia_accounts = {}
        self.nexia_thermostats = {}

        self.update_needed = False
        
    def shutdown(self):
        self.logger.info(u"Stopping Trane Nexia")
        

    def validatePrefsConfigUi(self, valuesDict):
        errorDict = indigo.Dict()

        updateFrequency = int(valuesDict['updateFrequency'])
        if (updateFrequency < 5) or (updateFrequency > 60):
            errorDict['updateFrequency'] = u"Update frequency is invalid - enter a valid number (between 5 and 60)"

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
            self.logger.debug(u"updateFrequency = " + str(self.updateFrequency))
            self.next_update = time.time()


    ########################################
        
    def runConcurrentThread(self):
        self.logger.debug(u"runConcurrentThread starting")
        try:
            while True:
                
                if (time.time() > self.next_update) or self.update_needed:
                    self.update_needed = False
                    self.next_update = time.time() + self.updateFrequency
                
                    # update from Nexia servers
                    
                    for accountID, account in self.nexia_accounts.items():
                        dev = indigo.devices[accountID]
                        if dev.states['authenticated']:
                            account.update()
                            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                        else:
                            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                            self.logger.debug("{}: Nexia account not authenticated, skipping update".format(dev.name))

                    # now update the Indigo devices         
                    
#                    for dev in self.nexia_thermostats.values():
#                        dev.update()
                    
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
        

    def get_device_list(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.logger.debug("get_device_list: typeId = {}, targetId = {}, filter = {}, valuesDict = {}".format(typeId, targetId, filter, valuesDict))

        try:
            account = self.nexia_accounts[int(valuesDict["account"])]
        except:
            self.logger.debug("get_device_list: no active accounts, returning empty list")
            return []
        
        if typeId == "NexiaThermostat":
        
            active_stats =  [
                (int(indigo.devices[dev].pluginProps["address"]))
                for dev in self.nexia_thermostats
            ]
            self.logger.debug("get_device_list: active_stats = {}".format(active_stats))

            available_devices =[]
            for thermostat_id in account.get_thermostat_ids():
                if thermostat_id not in active_stats:
                    name = account.get_thermostat_name(thermostat_id)
                    available_devices.append((thermostat_id, name))
        
            if targetId:
                try:
                    dev = indigo.devices[targetId]
                    available_devices.insert(0, (dev.pluginProps["address"], dev.name))
                except:
                    pass
                        
        else:
            self.logger.warning("get_device_list: unknown typeId = {}".format(typeId))
          
        self.logger.debug("get_device_list: available_devices for {} = {}".format(typeId, available_devices))
        return available_devices     

    # doesn't do anything, just needed to force other menus to dynamically refresh
    def menuChanged(self, valuesDict = None, typeId = None, devId = None):
        return valuesDict


    ########################################

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        self.logger.debug("validateDeviceConfigUi: valuesDict = {}, typeId = {}, devId = {}".format(valuesDict, typeId, devId))
        errorsDict = indigo.Dict()
        valid = True
        
        if typeId == "NexiaThermostat":
            if valuesDict["account"] == 0:
                errorsDict["account"] = "No Nexia Account Specified"
                self.logger.warning("validateDeviceConfigUi - No Nexia Account Specified")
                valid = False
            
            if len(valuesDict["address"]) == 0:
                errorsDict["address"] = "No Thermostat Specified"
                self.logger.warning("validateDeviceConfigUi - No Thermostat Specified")
                valid = False              
        
        return (valid, valuesDict, errorsDict)

    ########################################
        
    def deviceStartComm(self, dev):

        self.logger.info(u"{}: Starting {} Device {}".format(dev.name, dev.deviceTypeId, dev.id))
        
        if dev.deviceTypeId == 'NexiaAccount':
            NexiaAccount = NexiaThermostat(int(dev.pluginProps['house_id']), dev.pluginProps['username'], dev.pluginProps['password'], True, self.updateFrequency)
            if not NexiaAccount:
                dev.updateStateOnServer(key="authenticated", value=False)
                return
           
            self.nexia_accounts[dev.id] = NexiaAccount
            dev.updateStateOnServer(key="authenticated", value=True)
                            
        elif dev.deviceTypeId == 'NexiaThermostat':

            self.nexia_thermostats[dev.id] = dev
            self.update_needed = True
            

    def deviceStopComm(self, dev):

        self.logger.info(u"{}: Stopping {} Device {}".format( dev.name, dev.deviceTypeId, dev.id))

        if dev.deviceTypeId == 'NexiaAccount':
            if dev.id in self.nexia_accounts:
                del self.nexia_accounts[dev.id]
            
        elif dev.deviceTypeId == 'NexiaThermostat':
            if dev.id in self.nexia_thermostats:
                del self.nexia_thermostats[dev.id]
 

    ########################################
    # Thermostat Action callbacks
    ########################################
       
    def actionControlUniversal(self, action, dev):
        self.logger.debug(u"{}: action.actionControlUniversal: {}".format(dev.name, action.deviceAction))
        if action.deviceAction == indigo.kUniversalAction.RequestStatus:
            self.update_needed = True
        else:
            self.logger.warning(u"{}: Unimplemented action.deviceAction: {}".format(dev.name, action.deviceAction))

    def actionControlThermostat(self, action, dev):
        self.logger.debug(u"{}: action.thermostatAction: {}".format(dev.name, action.thermostatAction))
        
       ###### SET HVAC MODE ######
        if action.thermostatAction == indigo.kThermostatAction.SetHvacMode:
            hvac_mode = kHvacModeEnumToStrMap.get(action.actionMode, u"unknown")
            self.logger.debug(u"{} ({}): Mode set to: {}".format(dev.name, dev.address, hvac_mode))

            self.nexia_thermostats[dev.id].set_hvac_mode(hvac_mode)
            self.update_needed = True
            if "hvacOperationMode" in dev.states:
                dev.updateStateOnServer("hvacOperationMode", newHvacMode)

        ###### SET FAN MODE ######
        elif action.thermostatAction == indigo.kThermostatAction.SetFanMode:
       
            newFanMode = kFanModeEnumToStrMap.get(action.actionMode, u"auto")
        
            if newFanMode == u"on":
                self.logger.info(u'{}: set fan to ON, leave cool at {} and heat at {}'.format(dev.name, dev.coolSetpoint,dev.heatSetpoint))
                self.nexia_thermostats[dev.id].set_hold_temp_with_fan(dev.coolSetpoint, dev.heatSetpoint, holdType)

            if newFanMode == u"auto":
                self.logger.info(u'{}: resume normal program to set fan to Auto'.format(dev.name))
                self.nexia_thermostats[dev.id].resume_program()

            self.update_needed = True
            if stateKey in dev.states:
                dev.updateStateOnServer(u"hvacFanIsOn", action.actionMode, uiValue="True")

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

        if stateKey == u"setpointCool":
            self.logger.info(u'{}: set cool to: {} and leave heat at: {}'.format(dev.name, newSetpoint, dev.heatSetpoint))
            self.nexia_thermostats[dev.id].set_hold_temp(newSetpoint, dev.heatSetpoint, holdType)

        elif stateKey == u"setpointHeat":
            self.logger.info(u'{}: set heat to: {} and leave cool at: {}'.format(dev.name, newSetpoint,dev.coolSetpoint))
            self.nexia_thermostats[dev.id].set_hold_temp(dev.coolSetpoint, newSetpoint, holdType)

        else:
            self.logger.error(u'{}: handleChangeSetpointAction Invalid operation - {}'.format(dev.name, stateKey))
        
        self.update_needed = True
        if stateKey in dev.states:
            dev.updateStateOnServer(stateKey, newSetpoint, uiValue="%.1f °F" % (newSetpoint))

    ########################################
    # Menu callbacks
    ########################################
    
    def menuDumpThermostat(self):
        self.logger.debug(u"menuDumpThermostat")
        for accountID, account in self.nexia_accounts.items():
            self.logger.debug("{}: {}".format(indigo.devices[accountID].name, account._get_thermostat_json()))
        return True


