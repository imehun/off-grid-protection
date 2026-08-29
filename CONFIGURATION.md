# OGP -- Configuration Guide

Detailed configuration guide for OGP v1.1.3.

## 1. Requirements and optional components

OGP core configuration and protection do not require Huawei Solar, Browser Mod, Button-card or Stack-in-card.

Optional components:

- **Browser Mod** -- only for Browser Mod popup notifications.
- **Button-card** -- recommended for the generated Override dashboard.
- **Stack-in-card** -- recommended for the generated Override dashboard.

Home Assistant notifications do not require Browser Mod and may use available notification targets, including the Home Assistant notification panel.

The generated Lovelace YAML is a convenience template. It is not an OGP dependency and may be edited freely.

## 2. Protection model

OGP protects the **battery system**, not individual devices.

Selected devices are existing Home Assistant loads. OGP monitors them and can turn them OFF during OFF-GRID operation.

Selected user automations are part of the protection strategy. OGP remembers their state before protection, disables the selected automations that were enabled, and restores their previous state after recovery.

If a selected load is nevertheless turned ON during OFF-GRID without an active Override, OGP turns it OFF again.

### Race condition

If a user automation is not selected, it can try to turn a load ON while OGP is trying to turn it OFF. This is a possible race condition. Select the user automations that can start relevant loads during OFF-GRID operation.

## 3. Central configuration

### 3.1 Inverter Off-grid Status

Select the entity reporting the inverter/main device operating mode.

Recognized OFF-GRID states:

- `off_grid`
- `offgrid`
- `island`
- `islanding`

Recognized ON-GRID states:

- `on_grid`
- `ongrid`
- `grid`
- `normal`
- `connected`

Other or unavailable states are treated as `UNKNOWN`.

### 3.2 Power Meter Status

Select the power-meter status entity used as an additional confirmation.

If Power Meter Status becomes `unknown` or `unavailable`, OGP treats this as confirmation that the inverter/main device is OFF-GRID. This is intentional because the power meter can lose communication or power during the OFF-GRID transition.

### 3.3 Recovery delay

Configure the central delay used after ON-GRID returns, allowing the system to stabilize before recovery.

This is different from the device Recovery timeout.

### 3.4 Logs

Central Setup provides three OGP logging levels:

- **Off** -- OGP does not emit operational log messages.
- **Warnings** -- important warning/error events are logged.
- **Debug** -- warning/error events plus detailed diagnostic messages are logged.

Use **Debug** during initial configuration, testing and troubleshooting. After successful testing, use **Off** or **Warnings**.

The OGP setting is the master switch for OGP operational logging. A Home Assistant logger set to DEBUG does not cause OGP messages to be emitted when OGP Logs is Off.

### 3.5 Notifications

Notifications are optional.

The central notification configuration is opened as **House power status notifications**.

It provides:

- **Send notification**;
- **Notification recipients**;
- **Show Browser Mod popup**;
- **Browser Mod devices**;
- notification categories for grid status, protection/Override status and security;
- English or Croatian notification language.

Notification configuration is stored separately from Central Setup and is preserved when Central Setup is edited or Home Assistant is restarted.

In v1.1.3, the selected notification categories apply globally to the configured notification and Browser Mod targets. Per-target notification routing is not included in this version.

### 3.6 Browser Mod popup

Browser Mod popup is optional.

Enable it only when Browser Mod is installed and popup presentation is desired.

Normal Home Assistant notifications do not require Browser Mod.

## 4. Device Entry configuration

A selected load is configured as a separate OGP Device Entry. Each Device Entry contains the main Home Assistant entity that OGP should monitor and control during battery protection.

### 4.1 Main entity

Select the existing Home Assistant main entity. An entity already used as the main entity by another OGP Device Entry is not offered again.

### 4.2 OFF state

Configure the state that represents the load being OFF.

### 4.3 User automations

Select existing user automations that could start this load during OFF-GRID operation.

OGP stores the pre-protection state of the selected automations, disables those that were enabled, and restores their previous state during recovery.

Only selected automations are affected.

### 4.4 Wait if unavailable

Enable this when the load can lose its own power or communication during the OFF-GRID transition.

A load may become `unavailable` because it lost its own power.

With this option enabled, OGP waits for the load to return so that the required shutdown/lock handling can be verified and completed.

UPS power is recommended for Home Assistant and network/communication equipment, but the load itself may still lose power.

### 4.5 Recovery timeout

This is the timeout for the selected load to return and complete the required shutdown/lock sequence.

If it does not return within this time, OGP reports that the load could not be shut down and locked.

The user must manually turn the load OFF. When OGP can confirm the OFF state, the load can proceed to the locked state.

### 4.6 Command timeout

Configure how long OGP waits for a device command to complete.

Use a value appropriate for the device and its Home Assistant integration.

## 5. Device settings and Lovelace YAML

Each OGP Device Entry has its own settings.

The Device Entry can be reconfigured without changing the Central Entry.

### 5.1 Regenerate Lovelace YAML

Use **Regenerate Lovelace YAML** in the Device Entry settings when the generated dashboard YAML was accidentally removed or needs to be generated again.

The YAML language can be selected as English or Croatian.

Regenerating the YAML does not recreate or reconfigure the Device Entry.

When adding a new Device Entry, Lovelace YAML generation is optional. If the Lovelace YAML option is not selected, the Device Entry is still created normally.

### 5.2 Device Entry removal

Device Entry removal uses the native Home Assistant Config Entry delete action.

Removing a Device Entry does not remove the Central Entry or other OGP Device Entries.

## 6. Override

Override is an OGP function and does not require Browser Mod, Button-card or Stack-in-card.

Override uses:

- configurable duration;
- PIN protection.

Override does not automatically turn the load ON. After an accepted Override, the user can operate the load manually.

The generated Lovelace Override interface supports entering the PIN and activating the Override. The PIN can be submitted through the normal Enter action or the generated action control.

### Override dashboard

Button-card and Stack-in-card are optional dashboard components recommended for the generated Lovelace Override interface.

The generated YAML is only a starting template and can be modified.

## 7. Generated Lovelace YAML

When a selected load is created, OGP can generate a Lovelace YAML template.

The template may reference:

- Browser Mod;
- Button-card;
- Stack-in-card.

These are not installed by OGP.

If a referenced custom card is not installed, that dashboard configuration will not render correctly. OGP configuration and core protection remain independent of those dashboard components.

## 8. OFF-GRID protection sequence

When OFF-GRID operation is confirmed:

1. Confirm OFF-GRID state.
2. Capture the current state of selected user automations.
3. Disable selected automations that were enabled.
4. Check selected load states.
5. Turn OFF selected loads when required.
6. Continue monitoring selected loads.
7. If a selected load turns ON without an active Override, turn it OFF again.
8. Handle unavailable loads according to their configuration.
9. Keep battery protection active while OFF-GRID.

## 9. Recovery sequence

When ON-GRID is confirmed:

1. Start recovery.
2. Wait for the central Recovery delay.
3. Confirm ON-GRID stability.
4. Refresh selected load/protection states.
5. Restore selected user automations to their pre-protection states.
6. Clear the protection cycle.

If OFF-GRID returns during recovery, battery protection takes priority.

## 10. Huawei Solar and other integrations

OGP was tested with entities provided by the Huawei Solar integration.

Huawei Solar is **not an OGP dependency**. OGP does not include, install or distribute Huawei Solar source code.

The same principle applies to other Home Assistant integrations. OGP is designed to work with Home Assistant entities that provide the required states and services.

## 11. Testing

Before relying on OGP in an energy system, test:

- ON-GRID detection;
- OFF-GRID detection;
- Power Meter confirmation;
- selected load OFF control;
- selected automation disabling;
- automation restoration;
- device-state reassertion;
- unavailable behavior;
- Recovery timeout;
- ON-GRID recovery;
- correct Override PIN;
- incorrect Override PIN;
- Override duration and expiration;
- Home Assistant notifications;
- Browser Mod popup if enabled;
- notification category selection;
- notification configuration persistence after Central Setup changes;
- notification configuration persistence after Home Assistant restart;
- generated Lovelace interface if used;
- OGP Logs Off / Warnings / Debug behavior.

For detailed diagnostics, set OGP Logs to **Debug** and, if necessary, set the Home Assistant logger for `custom_components.off_grid_protection` to DEBUG. After testing, return OGP Logs to Off or Warnings.

## 12. Troubleshooting

### Load does not turn OFF

Check the selected entity, OFF state, availability, Home Assistant service support, Command timeout and the device integration.

### Load turns ON again during OFF-GRID

Check whether the automation that starts it was selected in OGP. Selecting relevant automations is recommended to reduce race conditions.

### Load becomes unavailable

Check its power supply, **Wait if unavailable**, Recovery timeout, and Home Assistant/network availability.

### No notification

Check that notification sending is enabled, that at least one notification target is selected, and that the required notification category is enabled.

### No popup

Check Browser Mod installation, popup configuration, selected Browser Mod devices and Browser Mod client availability.

Normal Home Assistant notifications do not require Browser Mod.

### Notification settings disappear after editing Central Setup

In v1.1.3, notification configuration is stored separately and should not be removed when Central Setup is edited. If it disappears, check the OGP logs and configuration entry state.

### Lovelace does not render

Check whether the generated YAML references Button-card, Stack-in-card or Browser Mod that are not installed. Install them or modify the YAML.

### Too many log messages

Use **Warnings** for normal operation or **Off** after testing. Use **Debug** only when detailed diagnostics are required.

## 13. Version policy

**v1.1.3 is the locked stable release.**

Future development uses a new version number, for example:

- `v1.1.4` -- bugfix
- `v1.2.0` -- new functionality

The v1.1.3 release remains the exact reference to the tested stable version.
