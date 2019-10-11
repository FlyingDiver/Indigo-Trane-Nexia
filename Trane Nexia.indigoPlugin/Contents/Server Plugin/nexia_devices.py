#! /usr/bin/env python
# -*- coding: utf-8 -*-

import requests
import json
import time
import logging
from nexia_thermostat import NexiaThermostat as NexiaAccount

import indigo


HVAC_MODE_MAP = {
    'HEAT'        : indigo.kHvacMode.Heat,
    'COOL'        : indigo.kHvacMode.Cool,
    'AUTO'        : indigo.kHvacMode.HeatCool,
    'OFF'         : indigo.kHvacMode.Off
    }

FAN_MODE_MAP = {
    'auto': indigo.kFanMode.Auto,
    'on'  : indigo.kFanMode.AlwaysOn,
    'circulate'  : indigo.kFanMode.Auto
    }


class NexiaThermostat:

    def __init__(self, device_id, account_id, thermostat_id):
        self.logger = logging.getLogger('Plugin.nexia_devices')
        self.device_id = device_id
        self.account_id = account_id
        self.thermostat_id = thermostat_id
        self.account = None
        dev = indigo.devices[self.device_id]
        
        self.logger.threaddebug(u"{}: NexiaThermostat __init__ starting, pluginProps =\n{}".format(dev.name, dev.pluginProps))
            
        return

    def update(self):
        dev = indigo.devices[self.device_id]
        self.logger.debug(u"{}: Update".format(dev.name))
        
        # has the Nexia account been initialized yet?
        account_dev = indigo.devices[self.account_id]
        if not account_dev.states['authenticated']:
            self.logger.info('Nexia account not authenticated yet; not initializing state of device {}'.format(self.address))
            return
        
        if not self.account:
            try:
                self.account = indigo.activePlugin.nexia_accounts[self.account_id]
                self.logger.debug(u"{}: Nexia Account device assigned, {}".format(dev.name, self.account_id))
            except:
                self.logger.error(u"updatable: Error obtaining Nexia account object")
                return
                    
        update_list = []
        
        thermostat_model = self.account.get_thermostat_model(self.thermostat_id)        
        update_list.append({'key' : "thermostat_model", 'value' : thermostat_model})
        
        thermostat_firmware = self.account.get_thermostat_firmware(self.thermostat_id)        
        update_list.append({'key' : "thermostat_firmware", 'value' : thermostat_firmware})
        
        thermostat_type = self.account.get_thermostat_type(self.thermostat_id)        
        update_list.append({'key' : "thermostat_type", 'value' : thermostat_type})
        
        fan_mode = self.account.get_fan_mode(self.thermostat_id)        
        update_list.append({'key' : "fan_mode", 'value' : fan_mode})
        
        fan_speed = self.account.get_fan_speed_setpoint(self.thermostat_id)        
        update_list.append({'key' : "fan_speed", 'value' : fan_speed})
        
        outdoor_temperature = self.account.get_outdoor_temperature(self.thermostat_id)        
        update_list.append({'key' : "outdoor_temperature", 'value' : outdoor_temperature})
        
        humidity = self.account.get_relative_humidity(self.thermostat_id) 
        update_list.append({'key' : "humidityInput1", 'value' : (humidity * 100.0)})
        
        dehumidify_setpoint = self.account.get_dehumidify_setpoint(self.thermostat_id)        
        update_list.append({'key' : "dehumidify_setpoint", 'value' : dehumidify_setpoint})
        
        blowerOn = self.account.is_blower_active(self.thermostat_id)
        update_list.append({'key' : "blowerOn", 'value' : blowerOn})

        system_status = self.account.get_system_status(self.thermostat_id)
        update_list.append({'key' : "system_status", 'value' : system_status})
        
        compressor_speed = self.account.get_current_compressor_speed(self.thermostat_id)        
        update_list.append({'key' : "compressor_speed", 'value' : compressor_speed})
        
        air_cleaner_mode = self.account.get_air_cleaner_mode(self.thermostat_id)        
        update_list.append({'key' : "air_cleaner_mode", 'value' : air_cleaner_mode})

        # hack to get compressor speed to show as 
        update_list.append({'key'           : "temperatureInput1", 
                            'value'         : (compressor_speed * 100), 
                            'uiValue'       : "{}%".format(compressor_speed * 100),
                            'decimalPlaces' : 0})

         
        dev.updateStatesOnServer(update_list)

    def set_fan_mode(self, fan_mode):       
        self.account.set_fan_mode(fan_mode.upper(), self.thermostat_id)


class NexiaZone:

    def __init__(self, device_id, account_id, thermostat_id, zone_id):
        self.logger = logging.getLogger('Plugin.nexia_devices')
        self.device_id = device_id
        self.account_id = account_id
        self.thermostat_id = thermostat_id
        self.zone_id = zone_id
        self.account = None
        dev = indigo.devices[self.device_id]
        
        self.logger.threaddebug(u"{}: NexiaZone __init__ starting, pluginProps =\n{}".format(dev.name, dev.pluginProps))
            
        return

    def update(self):
        dev = indigo.devices[self.device_id]
        self.logger.debug(u"{}: Update".format(dev.name))
        
        # has the Nexia account been initialized yet?
        account_dev = indigo.devices[self.account_id]
        if not account_dev.states['authenticated']:
            self.logger.info('Nexia account not authenticated yet; not initializing state of device {}'.format(self.address))
            return
        
        if not self.account:
            try:
                self.account = indigo.activePlugin.nexia_accounts[self.account_id]
                self.logger.debug(u"{}: Nexia Account device assigned, {}".format(dev.name, self.account_id))
            except:
                self.logger.error(u"updatable: Error obtaining Nexia account object")
                return

        
        update_list = []
                
        hsp = self.account.get_zone_heating_setpoint(self.thermostat_id, self.zone_id)
        update_list.append({'key'           : "setpointHeat", 
                            'value'         : hsp, 
                            'uiValue'       : hsp,
                            'decimalPlaces' : 1})

        csp = self.account.get_zone_cooling_setpoint(self.thermostat_id, self.zone_id)
        update_list.append({'key'           : "setpointCool", 
                            'value'         : csp, 
                            'uiValue'       : csp,
                            'decimalPlaces' : 1})

        dispTemp = self.account.get_zone_temperature(self.thermostat_id, self.zone_id)
        update_list.append({'key'           : "temperatureInput1", 
                            'value'         : dispTemp, 
                            'uiValue'       : dispTemp,
                            'decimalPlaces' : 1})

        hvacMode = self.account.get_zone_current_mode(self.thermostat_id, self.zone_id)
        update_list.append({'key' : "hvacOperationMode", 'value' : HVAC_MODE_MAP[hvacMode]})

        zone_status = self.account.get_zone_status(self.thermostat_id, self.zone_id)
        update_list.append({'key' : "zone_status", 'value' : zone_status})
        
        zone_called = self.account.is_zone_calling(self.thermostat_id, self.zone_id)
        update_list.append({'key' : "zone_called", 'value' : zone_called})
        
        requested_mode = self.account.get_zone_requested_mode(self.thermostat_id, self.zone_id)
        update_list.append({'key' : "requested_mode", 'value' : requested_mode})
              
        system_status = self.account.get_system_status(self.thermostat_id)
        if requested_mode == self.account.OPERATION_MODE_OFF:
            heatOn = False
            coolOn = False    
        elif not zone_called:
            heatOn = False
            coolOn = False    
        elif system_status == self.account.SYSTEM_STATUS_COOL:
            heatOn = False
            coolOn = True    
        elif system_status == self.account.SYSTEM_STATUS_HEAT:
            heatOn = True
            coolOn = False    
        elif system_status == self.account.SYSTEM_STATUS_IDLE:
            heatOn = False
            coolOn = False    
        else:
            heatOn = False
            coolOn = False    
        update_list.append({'key' : "hvacHeaterIsOn", 'value' : heatOn})
        update_list.append({'key' : "hvacCoolerIsOn", 'value' : coolOn})
        
        dev.updateStatesOnServer(update_list)


    def set_zone_mode(self, hvac_mode):        
        self.account.set_zone_mode(hvac_mode.upper(), self.thermostat_id, self.zone_id)

    def set_zone_heat_cool_temp(self, heatSetpoint, coolSetpoint):        
        self.account.set_zone_heat_cool_temp(heatSetpoint, coolSetpoint, None, self.thermostat_id, self.zone_id)

