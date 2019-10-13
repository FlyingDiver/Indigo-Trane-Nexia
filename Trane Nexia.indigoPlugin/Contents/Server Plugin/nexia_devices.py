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
        
        update_list.append({'key' : "thermostat_name", 'value' : self.account.get_thermostat_name(self.thermostat_id)})
        update_list.append({'key' : "thermostat_model", 'value' : self.account.get_thermostat_model(self.thermostat_id)})
        update_list.append({'key' : "thermostat_firmware", 'value' : self.account.get_thermostat_firmware(self.thermostat_id)})
        update_list.append({'key' : "thermostat_type", 'value' : self.account.get_thermostat_type(self.thermostat_id)})        
        update_list.append({'key' : "fan_mode", 'value' : self.account.get_fan_mode(self.thermostat_id)})        
        update_list.append({'key' : "outdoor_temperature", 'value' : self.account.get_outdoor_temperature(self.thermostat_id)})        
        update_list.append({'key' : "dehumidify_setpoint", 'value' : self.account.get_dehumidify_setpoint(self.thermostat_id)})        
        update_list.append({'key' : "system_status", 'value' : self.account.get_system_status(self.thermostat_id)})        
        update_list.append({'key' : "air_cleaner_mode", 'value' : self.account.get_air_cleaner_mode(self.thermostat_id)})
        update_list.append({'key' : "is_blower_active", 'value' : self.account.is_blower_active(self.thermostat_id)})

        has_relative_humidity = self.account.has_relative_humidity(self.thermostat_id)
        update_list.append({'key' : "has_relative_humidity", 'value' : has_relative_humidity})
        if has_relative_humidity:
            update_list.append({'key' : "humidityInput1", 'value' : (self.account.get_relative_humidity(self.thermostat_id) * 100.0)})        

        has_variable_fan_speed = self.account.has_variable_fan_speed(self.thermostat_id)
        update_list.append({'key' : "has_variable_fan_speed", 'value' : has_variable_fan_speed})
        if has_variable_fan_speed:
            update_list.append({'key' : "fan_speed", 'value' : self.account.get_fan_speed_setpoint(self.thermostat_id)})        

        has_emergency_heat = self.account.has_emergency_heat(self.thermostat_id)
        update_list.append({'key' : "has_emergency_heat", 'value' : has_emergency_heat})
        if has_emergency_heat:
            update_list.append({'key' : "is_emergency_heat_active", 'value' : self.account.is_emergency_heat_active(self.thermostat_id)})

        has_variable_speed_compressor = self.account.has_variable_speed_compressor(self.thermostat_id)
        update_list.append({'key' : "has_variable_speed_compressor", 'value' : has_variable_speed_compressor})
        if has_variable_speed_compressor:
            update_list.append({'key' : "requested_compressor_speed", 'value' : self.account.get_requested_compressor_speed(self.thermostat_id)})        
            update_list.append({'key' : "compressor_speed", 'value' : self.account.get_current_compressor_speed(self.thermostat_id)})        
         
        dev.updateStatesOnServer(update_list)

    def has_relative_humidity(self):
        return self.account.has_relative_humidity(self.thermostat_id)
        
    def has_emergency_heat(self):
        return self.account.has_emergency_heat(self.thermostat_id)
        
    def has_variable_fan_speed(self):
        return self.account.has_variable_fan_speed(self.thermostat_id)
        
    def has_variable_speed_compressor(self):
        return self.account.has_variable_speed_compressor(self.thermostat_id)
        
        
    def set_fan_mode(self, fan_mode):       
        self.account.set_fan_mode(fan_mode.upper(), self.thermostat_id)

    def set_air_cleaner(self, air_cleaner_mode):       
        self.account.set_air_cleaner(air_cleaner_mode, self.thermostat_id)

    def set_dehumidify_setpoint(self, setpoint):       
        self.account.set_dehumidify_setpoint(setpoint, self.thermostat_id)
                
    def set_follow_schedule(self, enabled):       
        self.account.set_follow_schedule(enabled, self.thermostat_id)

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
                            'uiValue'       : u"{}°F".format(hsp),
                            'decimalPlaces' : 0})

        csp = self.account.get_zone_cooling_setpoint(self.thermostat_id, self.zone_id)
        update_list.append({'key'           : "setpointCool", 
                            'value'         : csp, 
                            'uiValue'       : u"{}°F".format(csp),
                            'decimalPlaces' : 0})

        dispTemp = self.account.get_zone_temperature(self.thermostat_id, self.zone_id)
        update_list.append({'key'           : "temperatureInput1", 
                            'value'         : dispTemp, 
                            'uiValue'       : u"{}°F".format(dispTemp),
                            'decimalPlaces' : 0})

        hvacMode = self.account.get_zone_current_mode(self.thermostat_id, self.zone_id)
        update_list.append({'key' : "hvacOperationMode", 'value' : HVAC_MODE_MAP[hvacMode]})

        zone_name = self.account.get_zone_name(self.thermostat_id, self.zone_id)
        update_list.append({'key' : "zone_name", 'value' : zone_name})
        
        zone_status = self.account.get_zone_status(self.thermostat_id, self.zone_id)
        update_list.append({'key' : "zone_status", 'value' : zone_status})
        
        zone_called = self.account.is_zone_calling(self.thermostat_id, self.zone_id)
        update_list.append({'key' : "zone_called", 'value' : zone_called})
        
        requested_mode = self.account.get_zone_requested_mode(self.thermostat_id, self.zone_id)
        update_list.append({'key' : "requested_mode", 'value' : requested_mode})
              
        zone_preset = self.account.get_zone_preset(self.thermostat_id, self.zone_id)
        update_list.append({'key' : "zone_preset", 'value' : zone_preset})
              
        zone_setpoint_status = self.account.get_zone_setpoint_status(self.thermostat_id, self.zone_id)
        update_list.append({'key' : "zone_setpoint_status", 'value' : zone_setpoint_status})
              
        is_zone_calling = self.account.is_zone_calling(self.thermostat_id, self.zone_id)
        update_list.append({'key' : "is_zone_calling", 'value' : is_zone_calling})
              
        is_zone_in_permanent_hold = self.account.is_zone_in_permanent_hold(self.thermostat_id, self.zone_id)
        update_list.append({'key' : "is_zone_in_permanent_hold", 'value' : is_zone_in_permanent_hold})
              
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

    def get_zone_presets(self):
        return self.account.get_zone_presets(thermostat_id=self.thermostat_id, zone_id=self.zone_id)

    def get_zone_preset(self):
        return self.account.get_zone_preset(thermostat_id=self.thermostat_id, zone_id=self.zone_id)

    def set_zone_preset(self, preset):
        self.account.set_zone_preset(preset, thermostat_id=self.thermostat_id, zone_id=self.zone_id)


    def set_zone_mode(self, hvac_mode):        
        self.account.set_zone_mode(hvac_mode.upper(), thermostat_id=self.thermostat_id, zone_id=self.zone_id)

    def set_zone_heat_cool_temp(self, heatSetpoint, coolSetpoint):        
        self.account.set_zone_heat_cool_temp(heat_temperature=heatSetpoint, cool_temperature=coolSetpoint, 
                                                thermostat_id=self.thermostat_id, zone_id=self.zone_id)

    def call_return_to_schedule(self):        
        self.account.call_return_to_schedule(thermostat_id=self.thermostat_id, zone_id=self.zone_id)

    def call_permanent_hold(self):        
        self.account.call_permanent_hold(thermostat_id=self.thermostat_id, zone_id=self.zone_id)

