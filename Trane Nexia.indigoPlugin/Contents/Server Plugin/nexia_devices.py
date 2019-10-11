#! /usr/bin/env python
# -*- coding: utf-8 -*-

import requests
import json
import time
import logging
from nexia_thermostat import NexiaThermostat as NexiaAccount

import temperature_scale
import indigo


HVAC_MODE_MAP = {
    'heat'        : indigo.kHvacMode.Heat,
    'cool'        : indigo.kHvacMode.Cool,
    'auto'        : indigo.kHvacMode.HeatCool,
    'auxHeatOnly' : indigo.kHvacMode.Heat,
    'off'         : indigo.kHvacMode.Off
    }

FAN_MODE_MAP = {
    'auto': indigo.kFanMode.Auto,
    'on'  : indigo.kFanMode.AlwaysOn
    }


class NexiaThermostat:

    def __init__(self, dev):
        self.logger = logging.getLogger('Plugin.nexia_devices')
        self.dev = dev
        self.address = dev.address
        self.account = None
        
        self.logger.threaddebug(u"{}: NexiaThermostat __init__ starting, pluginProps =\n{}".format(dev.name, dev.pluginProps))
            
        return

    def update(self):

        self.logger.debug(u"{}: Updating device".format(self.dev.name))
        
        # has the Nexia account been initialized yet?
        if not self.account:

            if len(indigo.activePlugin.nexia_accounts) == 0:
                self.logger.debug(u"{}: No Nexia accounts available, skipping this device.".format(self.dev.name))
                return
            
            try:
                accountID = int(self.dev.pluginProps["account"])
                self.account = indigo.activePlugin.nexia_accounts[accountID]
                self.logger.debug(u"{}: Nexia Account device assigned, {}".format(self.dev.name, accountID))
            except:
                self.logger.error(u"updatable: Error obtaining Nexia account object")
                return
            
            if not self.account.states['authenticated']:
                self.logger.info('not authenticated to Nexia servers yet; not initializing state of device {}'.format(self.address))
                return

        
        update_list = []
        
        self.name = thermostat_data.get('name')

        device_type = thermostat_data.get('modelNumber')
        self.dev.updateStateOnServer(key="device_type", value=device_type)
        
        update_list.append({'key' : "device_type", 'value' : device_type})
        
        hsp = thermostat_data.get('desiredHeat')
        update_list.append({'key'           : "setpointHeat", 
                            'value'         : EcobeeThermostat.temperatureFormatter.convert(hsp), 
                            'uiValue'       : EcobeeThermostat.temperatureFormatter.format(hsp),
                            'decimalPlaces' : 1})

        csp = thermostat_data.get('desiredCool')
        update_list.append({'key'           : "setpointCool", 
                            'value'         : EcobeeThermostat.temperatureFormatter.convert(csp), 
                            'uiValue'       : EcobeeThermostat.temperatureFormatter.format(csp),
                            'decimalPlaces' : 1})

        dispTemp = thermostat_data.get('actualTemperature')
        update_list.append({'key'           : "temperatureInput1", 
                            'value'         : EcobeeThermostat.temperatureFormatter.convert(dispTemp), 
                            'uiValue'       : EcobeeThermostat.temperatureFormatter.format(dispTemp),
                            'decimalPlaces' : 1})


        climate = thermostat_data.get('currentClimate')
        update_list.append({'key' : "climate", 'value' : climate})

        hvacMode = thermostat_data.get('hvacMode')
        update_list.append({'key' : "hvacOperationMode", 'value' : HVAC_MODE_MAP[hvacMode]})

        fanMode = thermostat_data.get('desiredFanMode')
        update_list.append({'key' : "hvacFanMode", 'value' : int(FAN_MODE_MAP[fanMode])})

        hum = thermostat_data.get('actualHumidity')
        update_list.append({'key' : "humidityInput1", 'value' : float(hum)})
        
        fanMinOnTime = thermostat_data.get('fanMinOnTime')
        update_list.append({'key' : "fanMinOnTime", 'value' : fanMinOnTime})

        status = thermostat_data.get('equipmentStatus')
        update_list.append({'key' : "equipmentStatus", 'value' : status})

        val = bool(status and ('heatPump' in status or 'auxHeat' in status))
        update_list.append({'key' : "hvacHeaterIsOn", 'value' : val})

        val = bool(status and ('compCool' in status))
        update_list.append({'key' : "hvacCoolerIsOn", 'value' : val})

        val = bool(status and ('fan' in status or 'ventilator' in status))
        update_list.append({'key' : "hvacFanIsOn", 'value' : val})
        
        if device_type in ['athenaSmart', 'nikeSmart', 'apolloSmart']:
        
            temp2 = thermostat_data.get('internal').get('temperature')
            update_list.append({'key'           : "temperatureInput2", 
                                'value'         : EcobeeThermostat.temperatureFormatter.convert(temp2), 
                                'uiValue'       : EcobeeThermostat.temperatureFormatter.format(temp2),
                                'decimalPlaces' : 1})

            latestEventType = thermostat_data.get('latestEventType')
            update_list.append({'key': "autoHome", 'value' : bool(latestEventType and ('autoHome' in latestEventType))})
            update_list.append({'key': "autoAway", 'value' : bool(latestEventType and ('autoAway' in latestEventType))})

        self.dev.updateStatesOnServer(update_list)

class NexiaZone:

    def __init__(self, dev):
        self.logger = logging.getLogger('Plugin.nexia_devices')
        self.dev = dev
        self.address = dev.address
        self.account = None
        
        self.logger.threaddebug(u"{}: NexiaZone __init__ starting, pluginProps =\n{}".format(dev.name, dev.pluginProps))
            
        return

    def update(self):

        self.logger.debug(u"{}: Updating device".format(self.dev.name))
        
        # has the Nexia account been initialized yet?
        if not self.account:

            if len(indigo.activePlugin.nexia_accounts) == 0:
                self.logger.debug(u"{}: No Nexia accounts available, skipping this device.".format(self.dev.name))
                return
            
            try:
                accountID = int(self.dev.pluginProps["account"])
                self.account = indigo.activePlugin.nexia_accounts[accountID]
                self.logger.debug(u"{}: Nexia Account device assigned, {}".format(self.dev.name, accountID))
            except:
                self.logger.error(u"updatable: Error obtaining Nexia account object")
                return
            
            if not self.account.states['authenticated']:
                self.logger.info('not authenticated to Nexia servers yet; not initializing state of device {}'.format(self.address))
                return

        
        update_list = []
        
        self.name = self.account.get_zone_name()

        device_type = thermostat_data.get('modelNumber')
        self.dev.updateStateOnServer(key="device_type", value=device_type)
        
        update_list.append({'key' : "device_type", 'value' : device_type})
        
        hsp = thermostat_data.get('desiredHeat')
        update_list.append({'key'           : "setpointHeat", 
                            'value'         : EcobeeThermostat.temperatureFormatter.convert(hsp), 
                            'uiValue'       : EcobeeThermostat.temperatureFormatter.format(hsp),
                            'decimalPlaces' : 1})

        csp = thermostat_data.get('desiredCool')
        update_list.append({'key'           : "setpointCool", 
                            'value'         : EcobeeThermostat.temperatureFormatter.convert(csp), 
                            'uiValue'       : EcobeeThermostat.temperatureFormatter.format(csp),
                            'decimalPlaces' : 1})

        dispTemp = thermostat_data.get('actualTemperature')
        update_list.append({'key'           : "temperatureInput1", 
                            'value'         : EcobeeThermostat.temperatureFormatter.convert(dispTemp), 
                            'uiValue'       : EcobeeThermostat.temperatureFormatter.format(dispTemp),
                            'decimalPlaces' : 1})


        climate = thermostat_data.get('currentClimate')
        update_list.append({'key' : "climate", 'value' : climate})

        hvacMode = thermostat_data.get('hvacMode')
        update_list.append({'key' : "hvacOperationMode", 'value' : HVAC_MODE_MAP[hvacMode]})

        fanMode = thermostat_data.get('desiredFanMode')
        update_list.append({'key' : "hvacFanMode", 'value' : int(FAN_MODE_MAP[fanMode])})

        hum = thermostat_data.get('actualHumidity')
        update_list.append({'key' : "humidityInput1", 'value' : float(hum)})
        
        fanMinOnTime = thermostat_data.get('fanMinOnTime')
        update_list.append({'key' : "fanMinOnTime", 'value' : fanMinOnTime})

        status = thermostat_data.get('equipmentStatus')
        update_list.append({'key' : "equipmentStatus", 'value' : status})

        val = bool(status and ('heatPump' in status or 'auxHeat' in status))
        update_list.append({'key' : "hvacHeaterIsOn", 'value' : val})

        val = bool(status and ('compCool' in status))
        update_list.append({'key' : "hvacCoolerIsOn", 'value' : val})

        val = bool(status and ('fan' in status or 'ventilator' in status))
        update_list.append({'key' : "hvacFanIsOn", 'value' : val})
        
        if device_type in ['athenaSmart', 'nikeSmart', 'apolloSmart']:
        
            temp2 = thermostat_data.get('internal').get('temperature')
            update_list.append({'key'           : "temperatureInput2", 
                                'value'         : EcobeeThermostat.temperatureFormatter.convert(temp2), 
                                'uiValue'       : EcobeeThermostat.temperatureFormatter.format(temp2),
                                'decimalPlaces' : 1})

            latestEventType = thermostat_data.get('latestEventType')
            update_list.append({'key': "autoHome", 'value' : bool(latestEventType and ('autoHome' in latestEventType))})
            update_list.append({'key': "autoAway", 'value' : bool(latestEventType and ('autoAway' in latestEventType))})

        self.dev.updateStatesOnServer(update_list)


    def set_hvac_mode(self, hvac_mode):     # possible hvac modes are auto, auxHeatOnly, cool, heat, off 
        body =  {
                    "selection": 
                    {
                        "selectionType"  : "thermostats",
                        "selectionMatch" : self.dev.address 
                    },
                    "thermostat" : 
                    {
                        "settings": 
                        {
                            "hvacMode": hvac_mode
                        }
                    }
                }
        log_msg_action = "set HVAC mode"
        self.ecobee.make_request(body, log_msg_action)


    def set_hold_temp(self, cool_temp, heat_temp, hold_type="nextTransition"):  # Set a hold
        body =  {
                    "selection": 
                    {
                        "selectionType"  : "thermostats",
                        "selectionMatch" : self.dev.address 
                    },
                    "functions": 
                    [
                        {
                            "type"   : "setHold", 
                            "params" : 
                            {
                                "holdType": hold_type,
                                "coolHoldTemp": int(cool_temp * 10),
                                "heatHoldTemp": int(heat_temp * 10)
                            }
                        }
                    ]
                }
        log_msg_action = "set hold temp"
        self.ecobee.make_request(body, log_msg_action)

    def set_hold_temp_with_fan(self, cool_temp, heat_temp, hold_type="nextTransition"):     # Set a fan hold
        body =  {
                    "selection" : 
                    {
                        "selectionType"  : "thermostats",
                        "selectionMatch" : self.dev.address 
                    },
                    "functions" : 
                    [
                        {
                            "type"   : "setHold", 
                            "params" : 
                            {
                                "holdType"     : hold_type,
                                "coolHoldTemp" : int(cool_temp * 10),
                                "heatHoldTemp" : int(heat_temp * 10),
                                "fan"          : "on"
                            }
                        }
                    ]
                }
        log_msg_action = "set hold temp with fan on"
        self.ecobee.make_request(body, log_msg_action)

    def set_climate_hold(self, climate, hold_type="nextTransition"):    # Set a climate hold - ie away, home, sleep
        body =  {
                    "selection" : 
                    {
                        "selectionType"  : "thermostats",
                        "selectionMatch" : self.dev.address 
                    },
                    "functions" : 
                    [
                        {
                            "type"   : "setHold", 
                            "params" : 
                            {
                                "holdType"       : hold_type,
                                "holdClimateRef" : climate
                            }
                        }
                    ]
                }
        log_msg_action = "set climate hold"
        self.ecobee.make_request(body, log_msg_action)

    def resume_program(self):   # Resume currently scheduled program
        body =  {
                    "selection" : 
                    {
                        "selectionType"  : "thermostats",
                        "selectionMatch" : self.dev.address 
                    },
                    "functions" : 
                    [
                        {
                            "type"   : "resumeProgram", 
                            "params" : 
                            {
                                "resumeAll": "False"
                            }
                        }
                    ]
                }
        log_msg_action = "resume program"
        self.ecobee.make_request(body, log_msg_action)


