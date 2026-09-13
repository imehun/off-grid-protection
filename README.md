# OGP -- Off-grid Battery Protection

**Current release: v1.3.0**

Home Assistant custom integration for protecting a **battery system
during OFF-GRID operation**.

OGP monitors selected Home Assistant loads that can place a significant
load on the battery system. It can turn them OFF, disable selected user
automations that could turn them back ON, and restore those automations
to their previous state after recovery.

OGP also provides a second safety layer: if a protected device is turned
ON during OFF-GRID operation without an active Override, OGP reasserts
the configured shutdown action.

## Main features

-   ON-GRID / OFF-GRID monitoring
-   Additional Power Meter Status confirmation
-   Battery-load protection
-   Independent Device Entries
-   Per-device enabled/disabled state
-   Selected load monitoring and OFF control
-   Selected user automation snapshot, disabling and restoration
-   Device-state safety reassertion without Override
-   PIN-protected, time-limited Override
-   ON-GRID recovery
-   Optional Custom Device control entity
-   Custom recovery action: Stay OFF or Turn ON
-   Home Assistant notifications
-   Optional Browser Mod popup notifications
-   Config Flow configuration
-   Main OGP Lovelace dashboard card
-   Central Lovelace YAML generator
-   Entity Registry resolution for renamed generated entities
-   Custom Device Control entity display in Device Details
-   English and Croatian UI/documentation
-   Configurable OGP logging: Off, Warnings or Debug

## Protection model

OGP protects the **battery system**, not individual users or Home
Assistant permissions.

Each configured OGP Device Entry is independent. A disabled Device Entry
is not managed by OGP, while other enabled Device Entries continue to
operate normally.

Selected user automations are part of the protection strategy for
standard devices. OGP remembers their state before protection, disables
selected automations that were enabled, and restores their previous
state after recovery.

If a protected device is turned ON during OFF-GRID operation without an
active Override, OGP reasserts the configured shutdown action.

## Custom Device

Custom Device is intentionally generic. It is not tied to a specific
Home Assistant domain, integration, device name or use case.

A Custom Device has two independently selected entities:

-   **Device entity** --- the entity OGP shuts down and monitors.
-   **Control entity** --- an additional entity whose state is
    snapshotted, turned OFF during protection, and optionally turned ON
    during recovery.

Both entities are fully generic Home Assistant entities. They are not
restricted to `climate`, `switch`, `light`, `input_boolean` or any other
domain.

For example, a climate controlled by another integration can use:

-   Device entity: `climate.example`
-   Control entity: `switch.example_control_enabled`

The Control entity can represent an entire external control/automation
system. OGP therefore does not require the user to select every internal
automation used by that system.

### Custom protection sequence

During OFF-GRID protection:

1.  The Control entity state is snapshotted.
2.  The normal OGP device shutdown sequence is performed for the Device
    entity.
3.  The Control entity is turned OFF.
4.  The Device entity remains monitored and protected.

During ON-GRID recovery, the Device entity remains OFF according to the
normal OGP recovery model. The Control entity then follows the
configured recovery action:

-   **Stay OFF** --- leave the Control entity OFF.
-   **Turn ON** --- turn the Control entity ON so the external control
    system can resume operation.

Custom Device does not require selecting individual internal automations
for this control mechanism.

## Disabled Device Entries

A Device Entry can be disabled without disabling the central OGP entry.

When a Device Entry is disabled:

-   OGP does not control that device;
-   OGP does not shut it down;
-   OGP does not perform Override/recovery actions for it;
-   the device can still be used normally by Home Assistant and other
    integrations;
-   other enabled OGP Device Entries continue to be protected.

This is useful during development, testing and maintenance when selected
real devices should be left completely outside OGP control.

## Notifications

Notifications are optional and are managed as separate notification
profiles. Each profile can be edited or deleted independently.

OGP supports two notification profile types:

-   **Global notification** --- one global profile can exist. It always
    uses the built-in Home Assistant `persistent_notification` service.
    The user selects any combination of Grid status, Protection / Override
    and Security events, and selects the notification language.
-   **Per-device notification** --- multiple profiles can be created.
    Each profile targets one Home Assistant notification target or one
    Browser Mod device and can have its own event selection and language.

Browser Mod is available only for Per-device notifications. It is not used
by the Global notification profile.

The notification language supports English and Croatian.

OGP suppresses false startup grid notifications caused by an initial
`unavailable`/`unknown` state transitioning to a valid grid state after
Home Assistant startup.

When OGP settings are changed, OGP can create a persistent Home
Assistant notification recommending a Home Assistant restart. A restart
is not performed automatically.

## Override

Override provides a temporary, controlled exception to OFF-GRID
protection.

Override can use:

-   minimum runtime;
-   maximum runtime;
-   requested duration;
-   PIN protection.

Override does not automatically turn a protected device ON. The user
decides whether and when the device should operate.

## Lovelace frontend installation

### Lovelace frontend installation

The `OGP.js` frontend card is installed separately from the Python
integration:

1. Copy `OGP.js` to `/config/www/`.
2. Add `/local/OGP.js` under **Settings → Dashboards → Resources** as
   **JavaScript module**.
3. Reload the Home Assistant frontend.

Detailed Lovelace configuration and the generated YAML workflow are
documented in `CONFIGURATION.md`.

## Generated entities and Lovelace

OGP tracks resources that it generates so it can distinguish them from
existing Home Assistant resources.

Generated Lovelace YAML is a starting template and is not a dependency
of the core protection logic.

Optional frontend components:

-   Browser Mod --- only for Browser Mod popup notifications;
-   Button-card --- recommended for generated Override dashboard UI;
-   Stack-in-card --- recommended for generated Override dashboard UI.

## Tested integrations

OGP has been tested with Home Assistant entities provided by Huawei
Solar and with different Home Assistant entity types.

Huawei Solar is **not an OGP dependency**. OGP does not include, install
or distribute Huawei Solar source code.

## Documentation

-   [`README.md`](README.md) --- Project overview
-   [`README_hr.md`](README_hr.md) --- Croatian overview
-   [`CONFIGURATION.md`](CONFIGURATION.md) --- Detailed configuration
-   [`CONFIGURATION_hr.md`](CONFIGURATION_hr.md) --- Detailed Croatian configuration

## V1.3.0 changes

**v1.3.0 --- Lovelace UI and configuration workflow**

V1.3.0 adds the first complete Lovelace UI layer for OGP while keeping
the existing protection, shutdown, recovery and Override backend logic
unchanged.

-   **Main OGP Lovelace card:** a central dashboard card shows ON-GRID /
    OFF-GRID status, protection status, recovery countdown and configured
    OGP devices.
-   **Central controls:** the card provides access to Central settings,
    Reload central and Enable / Disable central.
-   **Device controls:** each device shows its protection state and
    actual Home Assistant entity state. Manual ON / OFF control is
    available only while that device's existing OGP Override is active.
-   **Device options:** device Settings, Reload Device and Device Details
    are available from the card.
-   **Central Options menu:** OGP central Options now provides Central
    setup, Notifications and Generate Lovelace YAML.
-   **Full central Lovelace YAML generator:** generates the complete OGP
    card configuration from the currently configured central and device
    entries. The central generator does not require a language selection;
    the card provides English / Croatian UI dynamically.
-   **Renamed generated entities:** the central Lovelace generator resolves
    OGP-generated helper entities through the Home Assistant Entity
    Registry, so manually renamed entity IDs can still be used in the
    generated YAML.
-   **Custom Device details:** Custom Devices display their configured
    Control entity in the Device Details view as **Automations / entities**
    instead of treating the Control entity as a normal automation list.
-   **Lovelace is UI-only:** the Lovelace card does not replace or modify
    OGP's protection lifecycle. The existing backend remains authoritative.

The add/delete device workflow does not automatically regenerate the
central Lovelace YAML in this release.

## V1.2.1 changes

**v1.2.1 --- Stable**

V1.2.1 is a maintenance and safety release focused on integration
lifecycle, configuration safety and loading performance:

-   **Integration reload:** re-enabling the central OGP integration
    creates a Home Assistant Repair request so the OGP integration can
    be reloaded cleanly.
-   **Restart request:** the Home Assistant restart is not automatic.
    It is performed only after the user opens the Repair and confirms
    the Fix/Submit action. If it is not confirmed, the Repair request
    remains active.
-   **OFF-GRID Settings lock:** OGP Settings cannot be changed while
    OFF-GRID protection is active. This prevents configuration changes
    from interfering with an active protection cycle.
-   **Icon optimization:** the integration icon was resized and
    optimized from 1254x1254 (~1.52 MB) to 512x512 (~240 KB) for faster
    loading.
-   **Translations:** the new Repair and OFF-GRID Settings lock messages
    are available in English and Croatian.

The protection, shutdown, recovery and Override logic from the stable
V1.2.0 release remains unchanged.

## Disclaimer

OGP assists with battery-system load protection in Home Assistant. It is
not a replacement for inverter, battery, electrical-installation or
other hardware safety mechanisms.

Test the complete installation before relying on OGP for automatic load
protection.
