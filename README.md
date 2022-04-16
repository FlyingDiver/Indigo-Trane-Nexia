# Nexia thermostat plugin for Indigo 
The plugin enables monitoring and control of Nexia Home compatible thermostats.


[![N|Solid](http://forums.indigodomo.com/static/www/images/wordmark.png)](http://indigodomo.com)

| Requirement            |                     |   |
|------------------------|---------------------|---|
| Minimum Indigo Version | 2022.1              |   |
| Python Library (API)   | Unofficial          |   |
| Requires Local Network | No                  |   |
| Requires Internet      | Yes                 |   |
| Hardware Interface     | None                |   |

Requirements:

* The username/password for your Nexia Home account
* Your HOUSEID. You can get this from logging in and examining the url when you're looking at your climate device:

`https://www.mynexia.com/houses/HOUSEID/`

* A supported Nexia Home compatible thermostat:
	* Trane XL1050
	* Trane XL850	
	

How to use:

1. Install the plugin
2. Create an Nexia Account device
3. Create a Thermostat device
4. Create a Zone device for each zone controlled by that thermostat.

Due to the way the Trane system handles multi-zone systems, there are separate Thermostat and Zone devices in Indigo.  The Thermostat device manages the compressor and air handler, and is where you control system mode (heat or cool) and fan operation.  The humidity sensor (if equipped) is part of the thermostat device.

The zone devices manage the temperature setpoints for each controllable zone, and provide the actual temperature sensor for the zone.


