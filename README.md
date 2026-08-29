# OGP -- Off-grid Battery Protection

Home Assistant custom integration for protecting a **battery system during OFF-GRID operation**.

OGP monitors selected Home Assistant loads that can place a significant load on the battery system. It can turn them OFF, disable selected user automations that could turn them back ON, and restore those automations to their previous state after recovery.

OGP also provides a second safety layer: if a selected load is turned ON during OFF-GRID operation without an active Override, OGP turns it OFF again.

## Main features

- ON-GRID / OFF-GRID monitoring
- Additional Power Meter Status confirmation
- Battery-load protection
- Selected load monitoring and OFF control
- Selected user automation disabling and restoration
- Device-state reassertion without Override
- PIN-protected, time-limited Override
- ON-GRID recovery
- Home Assistant notifications
- Optional Browser Mod popup notifications
- Central notification configuration with selectable notification categories
- Config Flow configuration
- Optional generated Lovelace YAML for a dashboard
- English and Croatian UI/documentation
- Configurable OGP logging: Off, Warnings, or Debug
- Persistent configuration across Home Assistant restarts

## Notifications

OGP can generate a central notification automation for house power-status and protection events.

The notification configuration can enable or disable:

- grid status notifications;
- protection and Override notifications;
- security notifications for invalid PIN attempts;
- Home Assistant notification targets;
- optional Browser Mod popup devices;
- English or Croatian notification text.

Notification configuration is stored independently from the Central Setup configuration and is preserved when Central Setup is changed or Home Assistant is restarted.

In v1.1.3, notification categories are configured globally for the selected notification targets and Browser Mod popup targets. Per-device/per-target notification routing is intentionally not part of v1.1.3 and is reserved for a future version.

## Logging

OGP logging can be configured from Central Setup:

- **Off** -- OGP does not emit operational log messages.
- **Warnings** -- important OGP warning/error events are logged.
- **Debug** -- warning/error events plus detailed diagnostic messages are logged.

Debug logging is intended for configuration, testing and troubleshooting. After successful testing, Off or Warnings is recommended.

The OGP logging setting is independent of the Home Assistant logger level. Setting the Home Assistant logger to DEBUG does not enable OGP operational logging when OGP Logs is Off.

## Optional Lovelace components

OGP core configuration and protection **do not require** Browser Mod, Button-card or Stack-in-card.

- **Browser Mod** is optional and is needed only for Browser Mod popup notifications.
- **Button-card** and **Stack-in-card** are optional and recommended for the generated Override dashboard.

The generated Lovelace YAML is a starting template. It is not an OGP dependency and can be modified by the user.

## Tested integrations

OGP has been tested with Home Assistant entities provided by **Huawei Solar**.

Huawei Solar is **not an OGP dependency**. OGP does not include, install, or distribute Huawei Solar source code.

OGP is designed to work with different Home Assistant entities that provide the required states and services.

## Documentation

- `README.md` -- Project overview
- `README_hr.md` -- Hrvatski pregled
- `CONFIGURATION.md` -- Detailed configuration
- `CONFIGURATION_hr.md` -- Detaljne upute

## Version

**v1.1.3 -- Stable**

v1.1.3 is the locked stable release. Future changes are developed as new versions.

## Disclaimer

OGP assists with battery-system load protection in Home Assistant. It is not a replacement for inverter, battery, electrical-installation or other hardware safety mechanisms.

Test the complete installation before relying on OGP for automatic load protection.
