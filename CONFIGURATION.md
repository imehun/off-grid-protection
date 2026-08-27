# OGP -- Configuration Guide

Detailed configuration guide for OGP v1.1.0.

## 1. Requirements and optional components

OGP core configuration and protection do not require Huawei Solar,
Browser Mod, Button-card or Stack-in-card.

Optional components:

-   **Browser Mod** -- only for Browser Mod popup notifications.
-   **Button-card** -- recommended for the generated Override dashboard.
-   **Stack-in-card** -- recommended for the generated Override
    dashboard.

Home Assistant notifications do not require Browser Mod and may use
available notification targets, including the Home Assistant
notification panel.

The generated Lovelace YAML is a convenience template. It is not an OGP
dependency and may be edited freely.

## 2. Protection model

OGP protects the **battery system**, not individual devices.

Selected devices are existing Home Assistant loads. OGP monitors them
and can turn them OFF during OFF-GRID operation.

Selected user automations are part of the protection strategy. OGP
remembers their state before protection, disables the selected
automations that were enabled, and restores their previous state after
recovery.

This prevents a user automation from trying to start a load while
battery protection is active.

If a selected load is nevertheless turned ON during OFF-GRID without an
active Override, OGP turns it OFF again.

### Race condition

If a user automation is not selected, it can try to turn a load ON while
OGP is trying to turn it OFF. This is a possible **race condition**.

Select the user automations that can start relevant loads during
OFF-GRID operation.

## 3. Central configuration

### 3.1 Inverter Off-grid Status

Select the entity reporting the inverter/main device operating mode.

Recognized OFF-GRID states:

-   `off_grid`
-   `offgrid`
-   `island`
-   `islanding`

Recognized ON-GRID states:

-   `on_grid`
-   `ongrid`
-   `grid`
-   `normal`
-   `connected`

Other or unavailable states are treated as `UNKNOWN`.

### 3.2 Power Meter Status

Select the power-meter status entity used as an additional confirmation.

If Power Meter Status becomes `unknown` or `unavailable`, OGP treats
this as confirmation that the inverter/main device is OFF-GRID.

This is intentional because the power meter can lose communication or
power during the OFF-GRID transition.

### 3.3 Recovery delay

Configure the central delay used after ON-GRID returns, allowing the
system to stabilize before recovery.

This is different from the device Recovery timeout.

### 3.4 Notifications

Notifications are optional.

Select an available Home Assistant notification target, such as:

-   Home Assistant Notification panel;
-   mobile notification service;
-   another supported notification service.

Browser Mod is not required for these notifications.

### 3.5 Browser Mod popup

Browser Mod popup is optional.

Enable it only when Browser Mod is installed and popup presentation is
desired.

## 4. Add a selected load

Add the Home Assistant device/entity that OGP should monitor and control
during battery protection.

### 4.1 Device

Select the existing Home Assistant device/entity.

### 4.2 OFF state

Configure the state that represents the load being OFF.

### 4.3 User automations

Select existing user automations that could start this load during
OFF-GRID operation.

OGP stores the pre-protection state of the selected automations,
disables those that were enabled, and restores their previous state
during recovery.

Only selected automations are affected.

### 4.4 Wait if unavailable

**Enable this when the load can lose its own power or communication
during the OFF-GRID transition.**

A load may become `unavailable` because it lost its own power.

With this option enabled, OGP waits for the load to return so that the
required shutdown/lock handling can be verified and completed.

UPS power is recommended for Home Assistant and network/communication
equipment, but the load itself may still lose power.

### 4.5 Recovery timeout

This is the timeout for the selected load to return and complete the
required shutdown/lock sequence.

If it does not return within this time, OGP reports that the load could
not be shut down and locked.

The user must manually turn the load OFF. When OGP can confirm the OFF
state, the load can proceed to the locked state.

### 4.6 Command timeout

Configure how long OGP waits for a device command to complete.

Use a value appropriate for the device and its Home Assistant
integration.

## 5. Override

Override is an OGP function and does not require Browser Mod,
Button-card or Stack-in-card.

Override uses:

-   configurable duration;
-   PIN protection.

Override does not automatically turn the load ON. After an accepted
Override, the user can operate the load manually.

The Override function can be tested directly through Home Assistant
service/action tools.

### Override dashboard

Button-card and Stack-in-card are optional dashboard components
recommended for the generated Lovelace Override interface.

The generated YAML is only a starting template and can be modified.

## 6. Generated Lovelace YAML

When a selected load is created, OGP can generate a Lovelace YAML
template.

The template may reference:

-   Browser Mod;
-   Button-card;
-   Stack-in-card.

These are not installed by OGP.

If a referenced custom card is not installed, that dashboard
configuration will not render correctly. OGP configuration and core
protection remain independent of those dashboard components.

## 7. OFF-GRID protection sequence

When OFF-GRID operation is confirmed:

1.  Confirm OFF-GRID state.
2.  Capture the current state of selected user automations.
3.  Disable selected automations that were enabled.
4.  Check selected load states.
5.  Turn OFF selected loads when required.
6.  Continue monitoring selected loads.
7.  If a selected load turns ON without an active Override, turn it OFF
    again.
8.  Handle unavailable loads according to their configuration.
9.  Keep battery protection active while OFF-GRID.

## 8. Recovery sequence

When ON-GRID is confirmed:

1.  Start recovery.
2.  Wait for the central Recovery delay.
3.  Confirm ON-GRID stability.
4.  Refresh selected load/protection states.
5.  Restore selected user automations to their pre-protection states.
6.  Clear the protection cycle.

If OFF-GRID returns during recovery, battery protection takes priority.

## 9. Huawei Solar and other integrations

OGP was tested with entities provided by the Huawei Solar integration.

Huawei Solar is **not an OGP dependency**. OGP does not include, install
or distribute Huawei Solar source code.

The same principle applies to other Home Assistant integrations. OGP is
designed to work with Home Assistant entities that provide the required
states and services.

## 10. Testing

Before relying on OGP in an energy system, test:

-   ON-GRID detection;
-   OFF-GRID detection;
-   Power Meter confirmation;
-   selected load OFF control;
-   selected automation disabling;
-   automation restoration;
-   device-state reassertion;
-   unavailable behavior;
-   Recovery timeout;
-   ON-GRID recovery;
-   correct and incorrect Override PIN;
-   Home Assistant notifications;
-   Browser Mod popup if enabled;
-   generated Lovelace interface if used.

## 11. Troubleshooting

### Load does not turn OFF

Check the selected entity, OFF state, availability, Home Assistant
service support, Command timeout and the device integration.

### Load turns ON again during OFF-GRID

Check whether the automation that starts it was selected in OGP.
Selecting relevant automations is recommended to reduce race conditions.

### Load becomes unavailable

Check its power supply, **Wait if unavailable**, Recovery timeout, and
Home Assistant/network availability.

### No popup

Check Browser Mod installation, popup configuration and Browser Mod
client availability.

Normal Home Assistant notifications do not require Browser Mod.

### Lovelace does not render

Check whether the generated YAML references Button-card, Stack-in-card
or Browser Mod that are not installed. Install them or modify the YAML.

## 12. Version policy

**v1.1.0 is the locked stable release.**

Future changes use a new version number, for example:

-   `v1.1.1` -- bugfix
-   `v1.2.0` -- new functionality

The v1.1.0 release remains the exact reference to the tested stable
version.
