# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is an [Indigo Domotics](http://indigodomo.com) plugin ("Trane Home") that monitors and controls Nexia Home compatible thermostats (Trane XL1050 / XL850) via the cloud. Indigo is a macOS home-automation server; plugins are bundle directories (`.indigoPlugin`) containing a Python "Server Plugin" plus XML UI definitions. There is no build step, no test suite, and no CLI — the plugin runs inside the Indigo Server process.

## Layout

Everything lives under `Trane Home.indigoPlugin/Contents/`:

- `Info.plist` — bundle metadata. `PluginVersion` is the plugin version (see Versioning below); `ServerApiVersion` is the Indigo API level.
- `Server Plugin/plugin.py` — the entire plugin implementation (single `Plugin` class subclassing `indigo.PluginBase`).
- `Server Plugin/Devices.xml` — device type definitions (`NexiaThermostat`, `NexiaZone`), their ConfigUI, and the device **states** the plugin publishes.
- `Server Plugin/Actions.xml`, `MenuItems.xml`, `PluginConfig.xml` — Indigo action, menu, and plugin-config UI. Each `<CallbackMethod>` / `method=` name must match a method on `Plugin`.
- `Server Plugin/requirements.txt` — Python deps (`aiohttp`, `nexia`).
- `Packages/` — vendored copies of the pip dependencies so they load without a separate install. **Untracked in git**; regenerate with `pip install -r requirements.txt --target Packages` and keep in sync with `requirements.txt`.

## Architecture

The plugin talks to the Nexia cloud through the third-party `nexia` library (`NexiaHome`), which is fully **async (asyncio)**. Indigo calls the plugin synchronously on its own thread, so the two worlds are bridged carefully:

- `startup()` spawns a background thread (`run_async_thread`) that owns a dedicated asyncio event loop (`self.event_loop`) and runs `async_main()` for the plugin's lifetime.
- `async_main()` opens the `aiohttp` `ClientSession`, logs into `NexiaHome`, then loops polling `nexia_home.update()` every `updateFrequency` minutes (or immediately when `self.update_needed` is set). `do_update()` reads every thermostat/zone and pushes values via `device.updateStatesOnServer()`.
- **All Nexia mutations from Indigo callbacks must be marshaled onto the async loop** with `asyncio.run_coroutine_threadsafe(coro, self.event_loop)`, then set `self.update_needed = True` to refresh states promptly. Never `await` directly in an Indigo callback — those methods are synchronous.

Two device types model one physical multi-zone system (see README):
- **`NexiaThermostat`** — the compressor/air handler; owns system-level fan mode, humidity, air cleaner, compressor speed. Has **no** setpoints and rejects `SetHvacMode`.
- **`NexiaZone`** — per-zone temperature sensor + heat/cool setpoints + HVAC mode. Setpoint and mode actions apply here.

`address` (device identity) is set in `validateDeviceConfigUi`: the thermostat's nexia id for thermostats, `thermostat:zone` for zones. Active devices are tracked in the `self.nexia_thermostats` / `self.nexia_zones` dicts, populated in `deviceStartComm` and torn down in `deviceStopComm`.

HVAC and fan modes are translated between Indigo enums and Nexia strings via the `kHvacMode*`/`kFanMode*` maps at the top of `plugin.py`.

The **root logger** gets `indigo_log_handler` attached (in `__init__`) so warnings from async callbacks surface in the Indigo log; it is removed from `self.logger` to avoid duplicate lines. Use `self.logger.debug/threaddebug` — `threaddebug` is Indigo's most-verbose level.

## Running / testing changes

There is no automated test path. To exercise a change, the `.indigoPlugin` bundle must be installed into a running Indigo Server (double-click the bundle, or reload it from Indigo). Behavior is observed through the Indigo Event Log. The **"Write Nexia Data to Log"** menu item (`menuDumpNexia`) dumps the raw thermostat/zone JSON from the Nexia API — the fastest way to see what fields the library exposes when adding new states.

## Versioning

Per the parent `../CLAUDE.md`: the version lives in `Info.plist` (`PluginVersion`). When a commit bumps it, tag that commit and push both:

```
git commit -m "..."
git tag v<version>
git push origin HEAD --tags
```

Only tag commits that actually change the version.
