# OGP --- Configuration Guide

Detailed configuration guide for OGP v1.1.4.

## 1. Requirements and optional components

OGP core configuration and protection do not require Huawei Solar,
Browser Mod, Button-card or Stack-in-card.

Optional components:

-   **Browser Mod** --- only for Browser Mod popup notifications.
-   **Button-card** --- recommended for the generated Override
    dashboard.
-   **Stack-in-card** --- recommended for the generated Override
    dashboard.

Home Assistant notifications do not require Browser Mod.

The generated Lovelace YAML is a convenience template. It is not an OGP
dependency and may be edited freely.

## 2. Protection model

OGP protects the **battery system**, not individual users or Home
Assistant permissions.

Each OGP Device Entry is independent.

If a Device Entry is disabled, OGP does not manage that device. Other
enabled Device Entries continue to operate normally.

For standard devices, selected user automations are part of the
protection strategy. OGP stores their pre-protection state, disables
selected automations that were enabled, and restores their previous
state after recovery.

If a protected device is turned ON during OFF-GRID without an active
Override, OGP reasserts the configured shutdown action.

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
this as confirmation that the inverter/main device is OFF-GRID. This is
intentional because the power meter can lose communication or power
during the OFF-GRID transition.

### 3.3 Recovery delay

Configure the central delay used after ON-GRID returns, allowing the
system to stabilize before recovery.

This differs from the Recovery timeout of an individual device.

### 3.4 Logs

Central OGP logging can be:

-   Off
-   Warnings
-   Debug

Debug is intended for commissioning, testing and diagnostics.

### 3.5 Notifications

Notifications are optional.

Configure:

-   notification enable/disable;
-   Home Assistant notification targets;
-   Browser Mod popup targets;
-   notification categories;
-   notification language.

Notification settings are stored independently and persist through
central configuration changes and Home Assistant restarts.

If OGP settings are changed, OGP can display a persistent notification
recommending a Home Assistant restart. OGP does not restart Home
Assistant automatically.

Initial `unavailable`/`unknown` → valid grid state transitions after
Home Assistant startup are suppressed so they are not reported as normal
grid changes.

## 4. Device Entry configuration

Each protected load is configured as a separate OGP Device Entry.

### 4.1 Device Entry enabled/disabled

A Device Entry can be disabled without disabling the central OGP entry.

When disabled, OGP does not:

-   shut down the device;
-   perform safety reassertion;
-   execute Override/recovery actions;
-   manage the device as part of the active protection cycle.

The device remains available to Home Assistant and other integrations.

This is intended for development, testing and maintenance when a
selected device should be completely outside OGP control.

### 4.2 Device entity

For Switch and Climate devices, select the main entity OGP should
monitor and control.

For a Custom Device, this is the **Device entity**: the entity OGP shuts
down and continues to monitor during protection.

The Custom Device entity is fully generic and is not restricted to a
particular Home Assistant domain.

### 4.3 OFF state

Configure the state that represents the Device entity being OFF.

### 4.4 User automations

For standard Switch and Climate devices, select existing user
automations that could start the device during OFF-GRID operation.

OGP stores their state before protection, disables those that were
enabled, and restores their previous state during recovery.

Only selected automations are affected.

A Custom Device does not require this automation selection for its
Control entity mechanism.

### 4.5 Custom Control entity

Custom Device has a separate **Control entity**.

The Control entity is completely generic and may be any Home Assistant
entity suitable for the user's control strategy.

During OFF-GRID protection:

1.  OGP snapshots the Control entity state.
2.  OGP performs the normal Device entity shutdown sequence.
3.  OGP turns the Control entity OFF.
4.  OGP continues monitoring the Device entity.

The Control entity can represent an entire external control integration.
This avoids requiring OGP to manage every internal automation of that
integration.

### 4.6 Custom recovery action

For Custom Device, select:

-   **Stay OFF** --- leave the Control entity OFF after recovery.
-   **Turn ON** --- turn the Control entity ON after the normal recovery
    sequence.

The Device entity itself remains OFF according to the normal OGP
recovery model.

### 4.7 Wait if unavailable

Enable this when the device can lose its own power or communication
during the OFF-GRID transition.

### 4.8 Recovery timeout

Configure how long OGP waits for the required device state and
protection sequence.

If the device cannot be safely switched OFF and locked within the
configured timeout, OGP reports the failure and the user must manually
switch the device OFF.

### 4.9 Command timeout

Configure how long OGP waits for a device command to complete.

## 5. Override

Override is a temporary exception to active OFF-GRID protection.

It can use:

-   minimum runtime;
-   maximum runtime;
-   requested duration;
-   PIN protection.

Override does not automatically turn the device ON. The user controls
whether the device is actually enabled.

While Override is active, the normal safety reassertion is intentionally
suspended for that device.

When Override expires, protection is restored and an ON device is shut
down again.

## 6. OFF-GRID protection sequence

When OFF-GRID protection is confirmed:

1.  OGP confirms the OFF-GRID state.
2.  For standard devices, OGP snapshots selected user automations.
3.  Enabled selected automations are disabled.
4.  Device states are checked.
5.  Required shutdown actions are executed.
6.  For Custom Devices, the Control entity is also turned OFF after its
    state has been snapshotted.
7.  Protection remains active.
8.  Protected devices continue to be monitored.
9.  If a protected Device entity is turned ON without Override, OGP
    reasserts its shutdown action.
10. Failure to safely complete shutdown is handled through the
    configured timeout/failure mechanism.

## 7. Recovery sequence

When ON-GRID is confirmed:

1.  Recovery starts.
2.  Central Recovery delay is applied.
3.  Stable ON-GRID is confirmed.
4.  Device/protection state is refreshed.
5.  Standard-device selected automations are restored to their
    pre-protection states.
6.  Custom Device Control entities follow their configured recovery
    action.
7.  The Device entity remains OFF according to the normal OGP recovery
    model.
8.  The protection cycle is cleared.

If OFF-GRID returns during recovery, battery protection has priority.

## 8. Safety reassertion and failure handling

OGP does not rely on a single shutdown command.

While protection is active, OGP continues monitoring protected Device
entities.

If a protected device turns ON without Override, OGP reasserts the
configured shutdown action.

If the device cannot be safely switched OFF or confirmed OFF within the
applicable timeout, OGP reports that the device could not be safely shut
down and locked. The user must manually switch it OFF.

Override is the intentional exception to reassertion.

## 9. Generated Lovelace YAML

The generated Lovelace YAML is a starting template.

It may use Browser Mod, Button-card and Stack-in-card, but these are not
core OGP dependencies.

Custom Device YAML may require user adaptation to the selected Device
entity and desired interface.

## 10. Device removal and resource ownership

OGP tracks generated resources.

When a Device Entry is removed, OGP removes only resources recorded as
generated by OGP.

Existing user resources are not deleted merely because OGP used or
selected them.

## 11. Testing

Before relying on OGP, test:

-   ON-GRID detection;
-   OFF-GRID detection;
-   Power Meter Status confirmation;
-   standard Switch protection;
-   standard Climate protection;
-   Custom Device protection;
-   Custom Control entity snapshot and OFF action;
-   Custom recovery Stay OFF;
-   Custom recovery Turn ON;
-   disabled Device Entry behavior;
-   safety reassertion;
-   failure/timeout notification;
-   Override;
-   Override expiration;
-   ON-GRID recovery;
-   notification settings persistence;
-   startup notification suppression;
-   restart recommendation after changed settings;
-   generated Lovelace UI if used.

## 12. Troubleshooting

### Device is not controlled

Check that the Device Entry is enabled, the entity is correct, the OFF
state is correct, the entity is available and the configured Home
Assistant action is supported.

### Device turns ON during OFF-GRID

Check safety reassertion logs and whether an Override is active.

### Custom Device does not disable its external control system

Check the configured Control entity. It must be the entity that
represents the external control system's enable/disable state.

### Custom Device does not resume external control

Check that Custom recovery is set to **Turn ON** and that the Control
entity supports the required ON action.

### Device cannot be safely switched OFF

Check the entity, OFF state, command timeout, Recovery timeout and
device integration. If OGP reports a shutdown failure, manually switch
the device OFF.

### Too many logs

Use Warnings or Off after testing. Debug should be used for diagnostics.
