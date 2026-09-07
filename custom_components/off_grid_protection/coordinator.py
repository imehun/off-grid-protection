"""Runtime coordinator for Off-grid Protection."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from collections.abc import Callable

from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .central import OffGridCentral
from .device import OffGridDevice
from .runtime import (
    DeviceRuntime,
    GridStatus,
    OffGridRuntime,
)

_LOGGER = logging.getLogger(__name__)

SYNC_INTERVAL = timedelta(seconds=5)


def normalize_log_level(
    value: str | bool | None,
) -> str:
    """Normalize the stored OGP log setting."""

    # Backward compatibility with the boolean setting used by older versions.
    if isinstance(value, bool):
        return "warnings" if value else "off"

    normalized = str(value or "").strip().lower()

    if normalized in (
        "off",
        "warnings",
        "debug",
    ):
        return normalized

    # Unknown/missing values keep the safe operational default.
    return "warnings"


class OffGridCoordinator:
    """Coordinate the Off-grid Protection runtime."""

    def __init__(
        self,
        hass: HomeAssistant,
        central: OffGridCentral,
        logs_level: str | bool = "warnings",
    ) -> None:
        """Initialize the coordinator."""

        self.hass = hass
        self._central_entry_id = next(
            (
                entry.entry_id
                for entry in hass.config_entries.async_entries(
                    "off_grid_protection"
                )
                if entry.data.get("type") == "central"
            ),
            None,
        )
        self.central = central
        self._logs_level = normalize_log_level(logs_level)

        self.runtime = OffGridRuntime()

        self._running = False
        self._unsubscribers = []
        self._sync_unsubscriber = None
        self._recovery_task: asyncio.Task | None = None

        # Startup baseline: the initial inverter state is established
        # during initialization and must not be treated as a grid transition.
        self._startup_baseline_initialized = False

        # Runtime listeners used by OGP entities.
        self._listeners: set[Callable[[], None]] = set()

        # Active per-device override tasks.
        self._override_tasks: dict[
            str,
            asyncio.Task,
        ] = {}

        self._initialize_devices()
        self._initialize_grid_status()


    def set_logs_level(
        self,
        level: str | bool,
    ) -> None:
        """Set the OGP operational logging level."""
        self._logs_level = normalize_log_level(level)

    def set_logs_enabled(
        self,
        enabled: bool,
    ) -> None:
        """Backward-compatible logging switch."""
        self.set_logs_level(enabled)

    def _log(
        self,
        level: int,
        message: str,
        *args,
    ) -> None:
        """Write an OGP log message according to the configured level."""

        if self._logs_level == "off":
            return

        if (
            self._logs_level == "warnings"
            and level < logging.WARNING
        ):
            return

        _LOGGER.log(
            level,
            message,
            *args,
        )


    def async_add_listener(
        self,
        update_method: Callable[[], None],
        context=None,
    ) -> Callable[[], None]:
        """Register a listener for runtime changes."""

        self._listeners.add(update_method)

        def remove_listener() -> None:
            self._listeners.discard(
                update_method
            )

        return remove_listener

    def _notify_listeners(self) -> None:
        """Notify all OGP entities about a runtime change."""

        for listener in tuple(self._listeners):
            try:
                listener()
            except Exception as err:
                self._log(logging.ERROR, 
                    "OFF-GRID: entity listener failed: %s",
                    err,
                )

    def _active_devices(self) -> list[OffGridDevice]:
        """Return only OGP Device Entries that are enabled.

        A disabled Device Entry is deliberately excluded from OGP runtime
        control while other enabled Device Entries continue to operate.
        Legacy devices stored directly in the Central Entry remain active.
        """

        active_devices: list[OffGridDevice] = []
        device_entries = {
            entry.data.get("device", {}).get("id"): entry
            for entry in self.hass.config_entries.async_entries(
                "off_grid_protection"
            )
            if entry.data.get("type") == "device"
            and entry.data.get("central_entry_id") == self._central_entry_id
        }

        for device in self.central.devices:
            entry = device_entries.get(device.id)
            if entry is not None and entry.disabled_by is not None:
                continue
            active_devices.append(device)

        return active_devices

    def _initialize_devices(self) -> None:
        """Initialize runtime state for configured devices."""

        for device in self._active_devices():
            runtime = self.runtime.add_device(
                device.id
            )

            self._update_device_state(
                device,
                runtime,
            )

    def _initialize_grid_status(self) -> None:
        """Initialize the current grid status."""

        state = self.hass.states.get(
            self.central.inverter_off_grid_status
        )

        self.runtime.grid_status = self._parse_grid_status(
            state.state if state is not None else None
        )

        # The state read during coordinator initialization is the startup
        # baseline. It must never generate an ON-GRID/OFF-GRID transition.
        self._startup_baseline_initialized = True

        self._log(logging.DEBUG,
            "OFF-GRID: inverter=%s -> "
            "HA state=%s, grid_status=%s, "
            "startup baseline initialized",
            self.central.inverter_off_grid_status,
            state.state if state is not None else None,
            self.runtime.grid_status,
        )

    def _parse_grid_status(
        self,
        state: str | None,
    ) -> GridStatus:
        """Convert the HA inverter state into GridStatus."""

        if state is None:
            return GridStatus.UNKNOWN

        normalized = state.strip().lower()

        normalized = normalized.replace(
            "-",
            "_",
        )

        normalized = normalized.replace(
            " ",
            "_",
        )

        if normalized in (
            "off_grid",
            "offgrid",
            "island",
            "islanding",
        ):
            return GridStatus.OFF_GRID

        if normalized in (
            "on_grid",
            "ongrid",
            "grid",
            "normal",
            "connected",
        ):
            return GridStatus.ON_GRID

        if normalized in (
            "unknown",
            "unavailable",
            "none",
        ):
            return GridStatus.UNKNOWN

        self._log(logging.WARNING, 
            "OFF-GRID: unknown inverter state '%s'",
            state,
        )

        return GridStatus.UNKNOWN

    def _update_device_state(
        self,
        device: OffGridDevice,
        runtime: DeviceRuntime,
    ) -> None:
        """Update runtime state from Home Assistant."""

        state = self.hass.states.get(
            device.entity_id
        )

        if state is None:
            runtime.state = None
            runtime.available = False
        else:
            runtime.state = state.state
            runtime.available = state.state not in (
                "unavailable",
                "unknown",
            )

        self._log(logging.DEBUG, 
            "OFF-GRID DEVICE: %s -> "
            "state=%s, available=%s",
            device.name,
            runtime.state,
            runtime.available,
        )

    def _refresh_all_device_states(self) -> None:
        """Refresh all protected devices."""

        for device in self._active_devices():
            runtime = self.runtime.get_device(
                device.id
            )

            if runtime is None:
                runtime = self.runtime.add_device(
                    device.id
                )

            self._update_device_state(
                device,
                runtime,
            )

        self._notify_listeners()

    async def _update_grid_status(self) -> None:
        """Update the runtime grid status."""

        state = self.hass.states.get(
            self.central.inverter_off_grid_status
        )

        ha_state = (
            state.state
            if state is not None
            else None
        )

        new_grid_status = self._parse_grid_status(
            ha_state
        )

        old_grid_status = self.runtime.grid_status

        self.runtime.grid_status = new_grid_status

        self._log(logging.DEBUG, 
            "OFF-GRID SYNC: "
            "HA state=%s, grid_status=%s, previous=%s",
            ha_state,
            new_grid_status,
            old_grid_status,
        )

        self._notify_listeners()

        if (
            new_grid_status == GridStatus.OFF_GRID
            and old_grid_status != GridStatus.OFF_GRID
        ):
            self._refresh_all_device_states()

            await self._handle_off_grid()

    def _device_requires_shutdown(
        self,
        device: OffGridDevice,
        runtime: DeviceRuntime,
    ) -> bool:
        """Determine whether a device requires shutdown."""

        if device not in self._active_devices():
            return False

        if runtime.override_active:
            return False

        if device.device_type == "custom":
            control_entity_id = device.control_entity_id
            if control_entity_id:
                control_state = self.hass.states.get(
                    control_entity_id
                )
                if (
                    control_state is not None
                    and control_state.state == "on"
                ):
                    return True

        if not runtime.available:
            return False

        if runtime.state is None:
            return False

        normalized_state = runtime.state.strip().lower()

        if normalized_state in (
            "off",
            "idle",
            "standby",
        ):
            return False

        if normalized_state in (
            "unavailable",
            "unknown",
        ):
            return False

        return True

    def _resolve_automation_entity(
        self,
        automation_reference: str,
    ) -> str | None:
        """Resolve an automation reference to an automation entity ID."""
        reference = str(
            automation_reference
        ).strip()

        if not reference:
            return None

        # Normal case: Config Flow stores automation entity IDs.
        state = self.hass.states.get(reference)
        if (
            state is not None
            and state.entity_id.startswith("automation.")
        ):
            return state.entity_id

        # Also accept an automation entity ID with different casing.
        reference_lower = reference.lower()
        for state in self.hass.states.async_all("automation"):
            if state.entity_id.lower() == reference_lower:
                return state.entity_id

        # Accept the displayed automation name as a fallback.
        for state in self.hass.states.async_all("automation"):
            if state.name.strip().lower() == reference_lower:
                return state.entity_id

        return None

    def _capture_automation_states(
        self,
        device: OffGridDevice,
        runtime: DeviceRuntime,
    ) -> None:
        """Capture automation or Custom control state before protection."""

        if device.device_type == "custom":
            control_entity_id = device.control_entity_id
            if not control_entity_id:
                self._log(
                    logging.ERROR,
                    "OFF-GRID CUSTOM SNAPSHOT: %s -> control entity not configured",
                    device.name,
                )
                return

            state = self.hass.states.get(control_entity_id)
            if state is None:
                self._log(
                    logging.ERROR,
                    "OFF-GRID CUSTOM SNAPSHOT: %s -> %s not found",
                    device.name,
                    control_entity_id,
                )
                return

            if runtime.custom_control_state is None:
                runtime.custom_control_state = state.state
                self._log(
                    logging.WARNING,
                    "OFF-GRID CUSTOM SNAPSHOT: %s -> %s = %s",
                    device.name,
                    control_entity_id,
                    state.state,
                )
            return

        if runtime.automation_states:
            self._log(logging.DEBUG, 
                "OFF-GRID AUTOMATION SNAPSHOT: "
                "%s -> snapshot already exists",
                device.name,
            )
            return

        for automation_reference in device.automations:
            automation_id = self._resolve_automation_entity(
                automation_reference
            )

            if automation_id is None:
                self._log(logging.ERROR, 
                    "OFF-GRID AUTOMATION: "
                    "%s -> %s not found",
                    device.name,
                    automation_reference,
                )
                continue

            state = self.hass.states.get(
                automation_id
            )

            if state is None:
                self._log(logging.ERROR, 
                    "OFF-GRID AUTOMATION: "
                    "%s -> %s not found after resolution",
                    device.name,
                    automation_id,
                )
                continue

            enabled = state.state == "on"

            runtime.automation_states[
                automation_id
            ] = enabled

            self._log(logging.WARNING, 
                "OFF-GRID AUTOMATION SNAPSHOT: "
                "%s -> %s = %s",
                device.name,
                automation_id,
                "enabled" if enabled else "disabled",
            )

    async def _disable_captured_automations(
        self,
        device: OffGridDevice,
        runtime: DeviceRuntime,
    ) -> None:
        """Disable automations that were enabled before protection."""

        for automation_id, was_enabled in (
            runtime.automation_states.items()
        ):
            if not was_enabled:
                self._log(logging.DEBUG, 
                    "OFF-GRID AUTOMATION: "
                    "%s -> %s was already disabled",
                    device.name,
                    automation_id,
                )
                continue

            try:
                self._log(logging.WARNING, 
                    "OFF-GRID AUTOMATION: "
                    "DISABLE REQUEST: %s -> %s",
                    device.name,
                    automation_id,
                )

                await self.hass.services.async_call(
                    "automation",
                    "turn_off",
                    {
                        "entity_id": automation_id,
                    },
                    blocking=True,
                )

                # Verify the real HA state. Do not assume that a
                # successful service call means the automation is off.
                state = self.hass.states.get(
                    automation_id
                )

                if (
                    state is not None
                    and state.state == "off"
                ):
                    self._log(logging.WARNING, 
                        "OFF-GRID AUTOMATION: "
                        "DISABLED CONFIRMED: %s -> %s",
                        device.name,
                        automation_id,
                    )
                    continue

                # One immediate retry for integrations/automations
                # whose state update is asynchronous.
                await asyncio.sleep(0.2)

                state = self.hass.states.get(
                    automation_id
                )

                if (
                    state is not None
                    and state.state == "off"
                ):
                    self._log(logging.WARNING, 
                        "OFF-GRID AUTOMATION: "
                        "DISABLED CONFIRMED AFTER RETRY: "
                        "%s -> %s",
                        device.name,
                        automation_id,
                    )
                    continue

                self._log(logging.ERROR, 
                    "OFF-GRID AUTOMATION: "
                    "DISABLE NOT CONFIRMED: %s -> %s -> state=%s",
                    device.name,
                    automation_id,
                    state.state if state is not None else None,
                )

            except Exception as err:
                self._log(logging.ERROR, 
                    "OFF-GRID AUTOMATION: "
                    "DISABLE FAILED: %s -> %s -> %s",
                    device.name,
                    automation_id,
                    err,
                )

    async def _restore_automations(
        self,
        device: OffGridDevice,
        runtime: DeviceRuntime,
    ) -> None:
        """Restore automations to their pre-protection state."""

        for automation_id, was_enabled in (
            runtime.automation_states.items()
        ):
            if not was_enabled:
                self._log(logging.WARNING, 
                    "OFF-GRID RECOVERY: "
                    "AUTOMATION LEFT DISABLED: %s -> %s",
                    device.name,
                    automation_id,
                )
                continue

            state = self.hass.states.get(
                automation_id
            )

            if state is None:
                self._log(logging.ERROR, 
                    "OFF-GRID RECOVERY: "
                    "AUTOMATION NOT FOUND: %s -> %s",
                    device.name,
                    automation_id,
                )
                continue

            try:
                await self.hass.services.async_call(
                    "automation",
                    "turn_on",
                    {
                        "entity_id": automation_id,
                    },
                    blocking=True,
                )

                self._log(logging.WARNING, 
                    "OFF-GRID RECOVERY: "
                    "AUTOMATION RESTORED: %s -> %s",
                    device.name,
                    automation_id,
                )

            except Exception as err:
                self._log(logging.ERROR, 
                    "OFF-GRID RECOVERY: "
                    "AUTOMATION RESTORE FAILED: "
                    "%s -> %s -> %s",
                    device.name,
                    automation_id,
                    err,
                )

    async def _shutdown_control_entity(
        self,
        device: OffGridDevice,
        runtime: DeviceRuntime,
    ) -> None:
        """Turn OFF a Custom control entity and verify the result."""

        entity_id = device.control_entity_id
        if "." not in entity_id:
            runtime.shutdown_failed = True
            self._notify_listeners()
            self._log(
                logging.ERROR,
                "OFF-GRID CUSTOM: control entity invalid: %s -> %s",
                device.name,
                entity_id,
            )
            return

        domain = entity_id.split(".", 1)[0]

        try:
            await self.hass.services.async_call(
                domain,
                "turn_off",
                {"entity_id": entity_id},
                blocking=True,
            )
        except Exception as err:
            runtime.shutdown_failed = True
            self._notify_listeners()
            self._log(
                logging.ERROR,
                "OFF-GRID CUSTOM: control shutdown failed: %s -> %s -> %s",
                device.name,
                entity_id,
                err,
            )
            return

        deadline = self.hass.loop.time() + device.command_timeout
        while self.hass.loop.time() < deadline:
            state = self.hass.states.get(entity_id)
            if state is not None and state.state == "off":
                self._log(
                    logging.WARNING,
                    "OFF-GRID CUSTOM: control OFF confirmed: %s -> %s",
                    device.name,
                    entity_id,
                )
                return
            await asyncio.sleep(0.5)

        runtime.shutdown_failed = True
        self._notify_listeners()
        self._log(
            logging.ERROR,
            "OFF-GRID CUSTOM: control shutdown timeout: %s -> %s",
            device.name,
            entity_id,
        )

    async def _shutdown_device(
        self,
        device: OffGridDevice,
        runtime: DeviceRuntime,
    ) -> None:
        """Send shutdown command and verify the result."""

        if device not in self._active_devices():
            self._log(
                logging.DEBUG,
                "OFF-GRID PROTECTION: shutdown skipped for disabled device: %s",
                device.name,
            )
            return

        runtime.shutdown_requested = True
        runtime.shutdown_confirmed = False
        runtime.shutdown_failed = False

        self._notify_listeners()

        self._log(logging.WARNING, 
            "OFF-GRID PROTECTION: "
            "SHUTDOWN START: %s",
            device.name,
        )

        entity_id = device.entity_id

        if "." not in entity_id:
            runtime.shutdown_failed = True

            self._notify_listeners()

            self._log(logging.ERROR, 
                "OFF-GRID PROTECTION: "
                "SHUTDOWN FAILED: invalid entity_id=%s",
                entity_id,
            )

            return

        domain = entity_id.split(
            ".",
            1,
        )[0]

        shutdown_action = device.shutdown_action

        if shutdown_action == "turn_off":
            service = "turn_off"
            service_data = {}
        else:
            runtime.shutdown_failed = True

            self._notify_listeners()

            self._log(logging.ERROR, 
                "OFF-GRID PROTECTION: "
                "SHUTDOWN FAILED: unsupported "
                "shutdown_action=%s for %s",
                shutdown_action,
                device.name,
            )

            return

        try:
            await self.hass.services.async_call(
                domain,
                service,
                {
                    "entity_id": entity_id,
                    **service_data,
                },
                blocking=True,
            )

            if device.device_type == "custom":
                control_entity_id = device.control_entity_id
                if not control_entity_id or "." not in control_entity_id:
                    runtime.shutdown_failed = True
                    self._log(
                        logging.ERROR,
                        "OFF-GRID CUSTOM: control entity missing/invalid: %s -> %s",
                        device.name,
                        control_entity_id,
                    )
                    return

                control_domain = control_entity_id.split(".", 1)[0]
                await self.hass.services.async_call(
                    control_domain,
                    "turn_off",
                    {"entity_id": control_entity_id},
                    blocking=True,
                )

                self._log(
                    logging.WARNING,
                    "OFF-GRID CUSTOM: CONTROL ENTITY OFF: %s -> %s",
                    device.name,
                    control_entity_id,
                )

        except Exception as err:
            runtime.shutdown_failed = True

            self._notify_listeners()

            self._log(logging.ERROR, 
                "OFF-GRID PROTECTION: "
                "SHUTDOWN FAILED: %s -> %s",
                device.name,
                err,
            )

            return

        self._log(logging.WARNING, 
            "OFF-GRID PROTECTION: "
            "SHUTDOWN COMMAND SENT: %s",
            device.name,
        )

        timeout = device.command_timeout

        deadline = (
            self.hass.loop.time()
            + timeout
        )

        while self.hass.loop.time() < deadline:
            state = self.hass.states.get(
                entity_id
            )

            if (
                state is not None
                and state.state == device.off_state
            ):
                runtime.state = state.state
                runtime.available = True
                runtime.shutdown_confirmed = True
                runtime.shutdown_failed = False

                self._notify_listeners()

                self._log(logging.WARNING, 
                    "OFF-GRID PROTECTION: "
                    "SHUTDOWN CONFIRMED: %s -> state=%s",
                    device.name,
                    state.state,
                )

                return

            await asyncio.sleep(0.5)

        state = self.hass.states.get(
            entity_id
        )

        runtime.state = (
            state.state
            if state is not None
            else None
        )

        runtime.available = (
            state is not None
            and state.state not in (
                "unavailable",
                "unknown",
            )
        )

        runtime.shutdown_failed = True

        self._notify_listeners()

        self._log(logging.ERROR, 
            "OFF-GRID PROTECTION: "
            "SHUTDOWN TIMEOUT: %s -> "
            "expected state=%s, actual state=%s",
            device.name,
            device.off_state,
            runtime.state,
        )

    async def _run_protection_cycle(self) -> None:
        """Run the protection cycle."""

        if self.runtime.protection_active:
            self._log(logging.WARNING, 
                "OFF-GRID PROTECTION: "
                "cycle already active - ignoring new trigger"
            )
            return

        self._log(logging.WARNING, 
            "OFF-GRID PROTECTION: "
            "PROTECTION CYCLE STARTED"
        )

        self.runtime.start_protection_cycle()

        self._notify_listeners()

        # ---------------------------------------------------------
        # PHASE 1:
        # Capture automation state for ALL devices first.
        # ---------------------------------------------------------

        for device in self._active_devices():
            runtime = self.runtime.get_device(
                device.id
            )

            if runtime is None:
                runtime = self.runtime.add_device(
                    device.id
                )

            self._capture_automation_states(
                device,
                runtime,
            )

        # ---------------------------------------------------------
        # PHASE 2:
        # Disable automations for ALL devices.
        # ---------------------------------------------------------

        for device in self._active_devices():
            runtime = self.runtime.get_device(
                device.id
            )

            if runtime is None:
                continue

            await self._disable_captured_automations(
                device,
                runtime,
            )

        # ---------------------------------------------------------
        # PHASE 3:
        # Determine which devices require shutdown.
        # ---------------------------------------------------------

        shutdown_devices: list[
            tuple[OffGridDevice, DeviceRuntime]
        ] = []

        for device in self._active_devices():
            runtime = self.runtime.get_device(
                device.id
            )

            if runtime is None:
                runtime = self.runtime.add_device(
                    device.id
                )

            self._update_device_state(
                device,
                runtime,
            )

            self._log(logging.WARNING, 
                "OFF-GRID PROTECTION: "
                "DEVICE CHECK: %s -> "
                "state=%s, available=%s",
                device.name,
                runtime.state,
                runtime.available,
            )

            if not runtime.available:
                runtime.shutdown_requested = False
                runtime.shutdown_confirmed = False
                runtime.shutdown_failed = True

                self._log(logging.ERROR, 
                    "OFF-GRID PROTECTION: "
                    "DEVICE UNAVAILABLE: %s -> "
                    "state=%s",
                    device.name,
                    runtime.state,
                )

                self._log(logging.WARNING, 
                    "OFF-GRID PROTECTION: "
                    "SHUTDOWN DECISION: %s -> "
                    "shutdown_required=False, "
                    "shutdown_failed=True",
                    device.name,
                )

                continue

            shutdown_required = (
                self._device_requires_shutdown(
                    device,
                    runtime,
                )
            )

            runtime.shutdown_requested = (
                shutdown_required
            )

            self._log(logging.WARNING, 
                "OFF-GRID PROTECTION: "
                "SHUTDOWN DECISION: %s -> "
                "shutdown_required=%s",
                device.name,
                shutdown_required,
            )

            if not shutdown_required:
                runtime.shutdown_confirmed = (
                    runtime.state == device.off_state
                )
                runtime.shutdown_failed = False

                continue

            shutdown_devices.append(
                (
                    device,
                    runtime,
                )
            )

        # ---------------------------------------------------------
        # PHASE 4:
        # Send shutdown commands independently.
        # ---------------------------------------------------------

        if shutdown_devices:
            self._log(logging.WARNING, 
                "OFF-GRID PROTECTION: "
                "STARTING PARALLEL SHUTDOWN FOR %s DEVICE(S)",
                len(shutdown_devices),
            )

            shutdown_tasks = [
                asyncio.create_task(
                    self._shutdown_device(
                        device,
                        runtime,
                    )
                )
                for device, runtime in shutdown_devices
            ]

            results = await asyncio.gather(
                *shutdown_tasks,
                return_exceptions=True,
            )

            for (
                device_runtime,
                result,
            ) in zip(
                shutdown_devices,
                results,
            ):
                device, runtime = device_runtime

                if isinstance(
                    result,
                    Exception,
                ):
                    runtime.shutdown_failed = True

                    self._log(logging.ERROR, 
                        "OFF-GRID PROTECTION: "
                        "SHUTDOWN TASK FAILED: %s -> %s",
                        device.name,
                        result,
                    )

        self.runtime.complete_protection_cycle()

        # The protection cycle locks every protected device.
        # Override is the controlled exception for a device.
        for device in self._active_devices():
            runtime = self.runtime.get_device(
                device.id
            )

            if runtime is None:
                continue

            runtime.locked = True

            self.hass.bus.async_fire(
                "off_grid_protection_locked",
                {
                    "device_id": device.id,
                    "device_name": device.name,
                },
            )

        self._notify_listeners()

        self._log(logging.WARNING, 
            "OFF-GRID PROTECTION: "
            "PROTECTION CYCLE COMPLETE"
        )

    async def async_activate_override(
        self,
        device_id: str,
        duration_minutes: int,
        pin: str,
    ) -> bool:
        """Activate a per-device OFF-GRID override."""

        device = self.central.get_device(
            device_id
        )

        if device is None:
            self._log(logging.ERROR, 
                "OFF-GRID OVERRIDE: "
                "device not found: %s",
                device_id,
            )
            return False

        if device not in self._active_devices():
            self._log(
                logging.DEBUG,
                "OFF-GRID OVERRIDE: skipped for disabled device: %s",
                device.name,
            )
            return False

        runtime = self.runtime.get_device(
            device_id
        )

        if runtime is None:
            self._log(logging.ERROR, 
                "OFF-GRID OVERRIDE: "
                "runtime not found: %s",
                device.name,
            )
            return False

        if self.runtime.grid_status != GridStatus.OFF_GRID:
            self._log(logging.WARNING, 
                "OFF-GRID OVERRIDE: "
                "REJECTED: %s -> system is not OFF-GRID",
                device.name,
            )
            return False

        if not device.override_enabled:
            self._log(logging.WARNING, 
                "OFF-GRID OVERRIDE: "
                "REJECTED: %s -> override disabled",
                device.name,
            )
            return False

        if device.require_pin:
            if str(pin) != str(
                self.central.central_pin
            ):
                self._log(logging.WARNING, 
                    "OFF-GRID OVERRIDE: "
                    "REJECTED: %s -> invalid PIN",
                    device.name,
                )

                self.hass.bus.async_fire(
                    "off_grid_protection_security",
                    {
                        "action": "invalid_pin",
                        "device_id": device.id,
                        "device_name": device.name,
                    },
                )

                return False

        duration = int(duration_minutes)

        if duration < device.minimum_runtime:
            self._log(logging.WARNING, 
                "OFF-GRID OVERRIDE: "
                "REJECTED: %s -> duration %s min "
                "below minimum %s min",
                device.name,
                duration,
                device.minimum_runtime,
            )
            return False

        if duration > device.maximum_runtime:
            self._log(logging.WARNING, 
                "OFF-GRID OVERRIDE: "
                "REJECTED: %s -> duration %s min "
                "above maximum %s min",
                device.name,
                duration,
                device.maximum_runtime,
            )
            return False

        # Cancel an existing override for this device.
        existing_task = self._override_tasks.get(
            device_id
        )

        if (
            existing_task is not None
            and not existing_task.done()
        ):
            existing_task.cancel()

            try:
                await existing_task
            except asyncio.CancelledError:
                pass

        runtime.override_active = True
        runtime.override_started_at = (
            asyncio.get_running_loop().time()
        )
        runtime.override_duration_minutes = duration

        # The active override is the explicit exception to the
        # shutdown/reassert logic. The override does NOT turn the
        # device on. It only unlocks the device for manual control
        # during the configured time window.
        runtime.locked = False
        runtime.shutdown_requested = False
        runtime.shutdown_failed = False
        runtime.shutdown_confirmed = (
            runtime.state == device.off_state
        )

        self.hass.bus.async_fire(
            "off_grid_protection_override",
            {
                "action": "activated",
                "device_id": device.id,
                "device_name": device.name,
                "duration_minutes": duration,
            },
        )

        self._notify_listeners()

        self._log(logging.WARNING, 
            "OFF-GRID OVERRIDE: "
            "UNLOCKED: %s -> duration=%s min",
            device.name,
            duration,
        )

        self._override_tasks[
            device_id
        ] = asyncio.create_task(
            self._run_override_timer(
                device,
                runtime,
                duration,
            )
        )

        return True

    async def _run_override_timer(
        self,
        device: OffGridDevice,
        runtime: DeviceRuntime,
        duration_minutes: int,
    ) -> None:
        """Run the override timer."""

        duration_seconds = (
            duration_minutes * 60
        )

        try:
            await asyncio.sleep(
                duration_seconds
            )

        except asyncio.CancelledError:
            self._log(logging.DEBUG, 
                "OFF-GRID OVERRIDE: "
                "timer cancelled: %s",
                device.name,
            )
            raise

        # If the grid returned during the timer,
        # recovery will handle the final state.
        if self.runtime.grid_status != GridStatus.OFF_GRID:
            runtime.override_active = False
            runtime.override_started_at = None
            runtime.override_duration_minutes = 0

            self.hass.bus.async_fire(
                "off_grid_protection_override",
                {
                    "action": "grid_return",
                    "device_id": device.id,
                    "device_name": device.name,
                },
            )

            self._notify_listeners()

            self._log(logging.WARNING, 
                "OFF-GRID OVERRIDE: "
                "ENDED BY GRID RETURN: %s",
                device.name,
            )

            return

        runtime.override_active = False
        runtime.override_started_at = None
        runtime.override_duration_minutes = 0
        runtime.locked = True

        self.hass.bus.async_fire(
            "off_grid_protection_override",
            {
                "action": "expired",
                "device_id": device.id,
                "device_name": device.name,
            },
        )

        self._notify_listeners()

        self._log(logging.WARNING, 
            "OFF-GRID OVERRIDE: "
            "TIME EXPIRED: %s",
            device.name,
        )

        self._update_device_state(
            device,
            runtime,
        )

        if (
            runtime.available
            and runtime.state not in (
                device.off_state,
                "unavailable",
                "unknown",
            )
        ):
            await self._shutdown_device(
                device,
                runtime,
            )

        self._notify_listeners()

        self._log(logging.WARNING, 
            "OFF-GRID OVERRIDE: "
            "LOCK RESTORED: %s",
            device.name,
        )

    async def _cancel_device_override(
        self,
        device_id: str,
    ) -> None:
        """Cancel an active device override."""

        task = self._override_tasks.pop(
            device_id,
            None,
        )

        if task is not None:
            if not task.done():
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass

        runtime = self.runtime.get_device(
            device_id
        )

        if runtime is None:
            return

        runtime.override_active = False
        runtime.override_started_at = None
        runtime.override_duration_minutes = 0

        self._notify_listeners()

    async def _cancel_all_overrides(self) -> None:
        """Cancel all active device overrides."""

        device_ids = list(
            self._override_tasks.keys()
        )

        for device_id in device_ids:
            await self._cancel_device_override(
                device_id
            )

        for runtime in self.runtime.devices.values():
            runtime.override_active = False
            runtime.override_started_at = None
            runtime.override_duration_minutes = 0

        self._notify_listeners()

    async def _reassert_device_shutdown(
        self,
        device: OffGridDevice,
        runtime: DeviceRuntime,
    ) -> None:
        """Reassert shutdown if a device turns on while off-grid."""

        if device not in self._active_devices():
            return

        if self.runtime.grid_status != GridStatus.OFF_GRID:
            return

        if not self.runtime.protection_active:
            return

        # ---------------------------------------------------------
        # OVERRIDE EXCEPTION:
        #
        # This is the critical point that prevents #3 from
        # immediately turning the device back OFF.
        # ---------------------------------------------------------

        if runtime.override_active:
            self._log(logging.DEBUG, 
                "OFF-GRID PROTECTION: "
                "REASSERT SKIPPED - OVERRIDE ACTIVE: %s",
                device.name,
            )
            return

        if not runtime.available:
            self._log(logging.WARNING, 
                "OFF-GRID PROTECTION: "
                "REASSERT SHUTDOWN SKIPPED - "
                "DEVICE UNAVAILABLE: %s",
                device.name,
            )
            return

        if not self._device_requires_shutdown(
            device,
            runtime,
        ):
            return

        self._log(logging.WARNING, 
            "OFF-GRID PROTECTION: "
            "DEVICE TURNED ON DURING OFF-GRID: %s -> "
            "reasserting shutdown",
            device.name,
        )

        await self._shutdown_device(
            device,
            runtime,
        )

    async def _cancel_recovery_task(self) -> None:
        """Cancel an active recovery task."""

        task = self._recovery_task

        if task is None:
            return

        if task.done():
            self._recovery_task = None
            return

        self._log(logging.WARNING, 
            "OFF-GRID RECOVERY: "
            "cancelling active recovery"
        )

        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            self._log(logging.WARNING, 
                "OFF-GRID RECOVERY: "
                "recovery task cancelled"
            )

        self._recovery_task = None

    async def _handle_off_grid(self) -> None:
        """Handle transition into off-grid mode."""

        if (
            self._recovery_task is not None
            and not self._recovery_task.done()
        ):
            await self._cancel_recovery_task()

            self.runtime.reset_protection()

            self._notify_listeners()

            self._log(logging.WARNING, 
                "OFF-GRID PROTECTION: "
                "new off-grid event interrupted recovery"
            )

        await self._run_protection_cycle()

    async def _recover_custom_device(
        self,
        device: OffGridDevice,
        runtime: DeviceRuntime,
    ) -> None:
        """Apply the configured recovery action for a Custom device."""

        if device.device_type != "custom":
            return

        if device.recovery_action != "turn_on":
            self._log(
                logging.DEBUG,
                "OFF-GRID RECOVERY: CUSTOM DEVICE LEFT OFF: %s",
                device.name,
            )
            return

        entity_id = device.control_entity_id
        if "." not in entity_id:
            self._log(
                logging.ERROR,
                "OFF-GRID RECOVERY: CUSTOM TURN-ON FAILED: invalid control_entity_id=%s",
                entity_id,
            )
            return

        domain = entity_id.split(".", 1)[0]

        try:
            await self.hass.services.async_call(
                domain,
                "turn_on",
                {"entity_id": entity_id},
                blocking=True,
            )
            self._log(
                logging.WARNING,
                "OFF-GRID RECOVERY: CUSTOM CONTROL TURN-ON SENT: %s -> %s",
                device.name,
                entity_id,
            )
        except Exception as err:
            self._log(
                logging.ERROR,
                "OFF-GRID RECOVERY: CUSTOM TURN-ON FAILED: %s -> %s -> %s",
                device.name,
                entity_id,
                err,
            )

    async def _run_recovery(self) -> None:
        """Run the recovery sequence."""

        if not self.central.recovery_enabled:
            self._log(logging.WARNING, 
                "OFF-GRID RECOVERY: "
                "recovery disabled in configuration"
            )
            return

        if self.runtime.recovery_active:
            self._log(logging.WARNING, 
                "OFF-GRID RECOVERY: "
                "recovery already active"
            )
            return

        self.runtime.recovery_active = True

        # An ON-GRID return always terminates any active
        # per-device override.
        await self._cancel_all_overrides()

        self._notify_listeners()

        self._log(logging.WARNING, 
            "OFF-GRID RECOVERY: "
            "RECOVERY STARTED"
        )

        delay = self.central.recovery_delay

        self._log(logging.WARNING, 
            "OFF-GRID RECOVERY: "
            "waiting %s seconds",
            delay,
        )

        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            self.runtime.recovery_active = False

            self._notify_listeners()

            self._log(logging.WARNING, 
                "OFF-GRID RECOVERY: "
                "RECOVERY CANCELLED"
            )

            raise

        state = self.hass.states.get(
            self.central.inverter_off_grid_status
        )

        ha_state = (
            state.state
            if state is not None
            else None
        )

        current_grid_status = self._parse_grid_status(
            ha_state
        )

        if current_grid_status != GridStatus.ON_GRID:
            self.runtime.recovery_active = False

            self._notify_listeners()

            self._log(logging.WARNING, 
                "OFF-GRID RECOVERY: "
                "aborted - grid is not on-grid "
                "(state=%s)",
                ha_state,
            )

            return

        self._log(logging.WARNING, 
            "OFF-GRID RECOVERY: "
            "grid confirmed ON-GRID"
        )

        self._refresh_all_device_states()

        self._log(
            logging.DEBUG,
            "OFF-GRID RECOVERY: "
            "configured devices=%s",
            [
                device.name
                for device in self._active_devices()
            ],
        )

        for device in self._active_devices():
            runtime = self.runtime.get_device(
                device.id
            )

            if runtime is None:
                self._log(
                    logging.ERROR,
                    "OFF-GRID RECOVERY: "
                    "DEVICE SKIPPED: %s -> runtime missing",
                    device.name,
                )
                continue

            runtime.recovery_started = True

            self._log(
                logging.DEBUG,
                "OFF-GRID RECOVERY: DEVICE START: %s -> state=%s, available=%s",
                device.name,
                runtime.state,
                runtime.available,
            )

            self._log(
                logging.DEBUG,
                "OFF-GRID RECOVERY: "
                "DEVICE: %s -> state=%s, available=%s",
                device.name,
                runtime.state,
                runtime.available,
            )

            await self._restore_automations(
                device,
                runtime,
            )

            if (
                device.device_type == "custom"
                and device.recovery_action == "turn_on"
            ):
                await self._recover_custom_device(
                    device,
                    runtime,
                )

            runtime.recovery_completed = True

            self._log(
                logging.DEBUG,
                "OFF-GRID RECOVERY: DEVICE COMPLETE: %s",
                device.name,
            )

            self._log(logging.WARNING, 
                "OFF-GRID RECOVERY: "
                "DEVICE RECOVERY COMPLETE: %s",
                device.name,
            )

        for device in self.runtime.devices.values():
            device.automation_states.clear()
            device.custom_control_state = None

        self.runtime.protection_active = False
        self.runtime.protection_cycle_complete = False
        self.runtime.recovery_active = False

        for device in self.runtime.devices.values():
            device.shutdown_requested = False
            device.shutdown_confirmed = False
            device.shutdown_failed = False
            device.locked = False

            device.override_active = False
            device.override_started_at = None
            device.override_duration_minutes = 0

            device.recovery_started = False
            device.recovery_completed = False

        self._notify_listeners()

        self.hass.bus.async_fire(
            "off_grid_protection_recovery",
            {
                "action": "completed",
            },
        )

        self._log(logging.WARNING, 
            "OFF-GRID RECOVERY: "
            "previous protection cycle reset"
        )

        self._log(logging.WARNING, 
            "OFF-GRID RECOVERY: "
            "RECOVERY COMPLETE"
        )

    async def _async_state_changed(
        self,
        event: Event,
    ) -> None:
        """Handle a state change of a protected device."""

        entity_id = event.data.get(
            "entity_id"
        )

        if not entity_id:
            return

        device = self._find_device_by_entity(
            entity_id
        )

        # Custom control entities are also protected while OFF-GRID.
        # They represent the complete external control integration
        # (for example a CC enable switch), so turning one ON must not
        # bypass OGP protection.
        if device is None:
            control_device = self._find_custom_by_control_entity(
                entity_id
            )
            if control_device is None:
                return

            new_state = event.data.get("new_state")
            if (
                self.runtime.grid_status == GridStatus.OFF_GRID
                and self.runtime.protection_active
                and new_state is not None
                and new_state.state == "on"
            ):
                runtime = self.runtime.get_device(
                    control_device.id
                )
                if runtime is not None and not runtime.override_active:
                    self._log(
                        logging.WARNING,
                        "OFF-GRID PROTECTION: "
                        "CUSTOM CONTROL TURNED ON: %s -> %s -> reasserting OFF",
                        control_device.name,
                        entity_id,
                    )
                    await self._shutdown_control_entity(
                        control_device,
                        runtime,
                    )
            return

        runtime = self.runtime.get_device(
            device.id
        )

        if runtime is None:
            return

        previous_available = runtime.available
        previous_state = runtime.state

        new_state = event.data.get(
            "new_state"
        )

        if new_state is None:
            runtime.state = None
            runtime.available = False
        else:
            runtime.state = new_state.state
            runtime.available = new_state.state not in (
                "unavailable",
                "unknown",
            )

        self._log(logging.WARNING, 
            "OFF-GRID DEVICE EVENT: %s -> "
            "state=%s, available=%s",
            device.name,
            runtime.state,
            runtime.available,
        )

        if (
            not previous_available
            and runtime.available
        ):
            runtime.shutdown_failed = False
            runtime.shutdown_requested = False

            runtime.shutdown_confirmed = (
                runtime.state == device.off_state
            )

            self._log(logging.WARNING, 
                "OFF-GRID PROTECTION: "
                "DEVICE RECOVERED: %s -> "
                "previous_state=%s, state=%s, "
                "available=True, shutdown_failed=False",
                device.name,
                previous_state,
                runtime.state,
            )

        if (
            runtime.shutdown_requested
            and new_state is not None
            and new_state.state == device.off_state
        ):
            runtime.shutdown_confirmed = True
            runtime.shutdown_failed = False

            self._log(logging.WARNING, 
                "OFF-GRID PROTECTION: "
                "SHUTDOWN CONFIRMED BY EVENT: %s -> state=%s",
                device.name,
                new_state.state,
            )

        self._notify_listeners()

        # ---------------------------------------------------------
        # SAFETY REASSERT
        #
        # Override is explicitly checked before creating the
        # reassert task. This prevents an override from racing
        # against #3.
        # ---------------------------------------------------------

        if (
            self.runtime.grid_status == GridStatus.OFF_GRID
            and self.runtime.protection_active
            and runtime.available
            and not runtime.override_active
            and runtime.state not in (
                device.off_state,
                "unavailable",
                "unknown",
            )
        ):
            asyncio.create_task(
                self._reassert_device_shutdown(
                    device,
                    runtime,
                )
            )

    async def _async_grid_state_changed(
        self,
        event: Event,
    ) -> None:
        """Handle inverter grid status changes."""

        entity_id = event.data.get(
            "entity_id"
        )

        if entity_id != self.central.inverter_off_grid_status:
            return

        new_state = event.data.get(
            "new_state"
        )

        ha_state = (
            new_state.state
            if new_state is not None
            else None
        )

        old_status = self.runtime.grid_status

        new_status = self._parse_grid_status(
            ha_state
        )

        # The coordinator establishes the initial grid state before
        # listeners are active. If a state event arrives during startup,
        # synchronize the baseline but do not treat it as a transition.
        if not self._startup_baseline_initialized:
            self.runtime.grid_status = new_status
            self._startup_baseline_initialized = True

            self._notify_listeners()

            self._log(
                logging.DEBUG,
                "OFF-GRID GRID EVENT: "
                "startup baseline initialized: "
                "HA state=%s, grid_status=%s",
                ha_state,
                new_status,
            )
            return

        self.runtime.grid_status = new_status

        self._notify_listeners()

        self._log(logging.WARNING,
            "OFF-GRID GRID EVENT: "
            "HA state=%s, grid_status=%s, previous=%s",
            ha_state,
            new_status,
            old_status,
        )

        if (
            new_status == GridStatus.OFF_GRID
            and old_status != GridStatus.OFF_GRID
        ):
            await self._handle_off_grid()

        if (
            new_status == GridStatus.ON_GRID
            and old_status == GridStatus.OFF_GRID
        ):
            self._log(logging.WARNING, 
                "OFF-GRID PROTECTION: "
                "GRID RETURNED - starting recovery"
            )

            if self._recovery_task is not None:
                if not self._recovery_task.done():
                    self._log(logging.WARNING, 
                        "OFF-GRID RECOVERY: "
                        "recovery task already running"
                    )
                    return

            self._recovery_task = asyncio.create_task(
                self._run_recovery()
            )

    async def _async_periodic_sync(
        self,
        now: datetime,
    ) -> None:
        """Synchronize runtime with Home Assistant."""

        self._log(logging.DEBUG, 
            "OFF-GRID SYNC: callback running at %s",
            now.strftime("%H:%M:%S"),
        )

        for device in self._active_devices():
            runtime = self.runtime.get_device(
                device.id
            )

            if runtime is None:
                runtime = self.runtime.add_device(
                    device.id
                )

            state = self.hass.states.get(
                device.entity_id
            )

            if state is None:
                ha_state = None
                ha_available = False
            else:
                ha_state = state.state
                ha_available = state.state not in (
                    "unavailable",
                    "unknown",
                )

            runtime.state = ha_state
            runtime.available = ha_available

        await self._update_grid_status()

        self._notify_listeners()

        # ---------------------------------------------------------
        # Safety re-check.
        #
        # Override is the explicit exception. Do NOT use
        # shutdown_requested as a suppression flag here. A device can
        # turn ON again after the initial shutdown, and the periodic
        # safety path must be able to reassert OFF even when the first
        # shutdown request is still marked as requested.
        # ---------------------------------------------------------

        if (
            self.runtime.grid_status == GridStatus.OFF_GRID
            and self.runtime.protection_active
        ):
            for device in self._active_devices():
                runtime = self.runtime.get_device(
                    device.id
                )

                if runtime is None:
                    continue

                if not runtime.available:
                    continue

                if runtime.override_active:
                    continue

                if runtime.state in (
                    device.off_state,
                    "unavailable",
                    "unknown",
                ):
                    continue

                self._log(
                    logging.WARNING,
                    "OFF-GRID PROTECTION: "
                    "SAFETY RECHECK - DEVICE ON: %s -> reasserting shutdown",
                    device.name,
                )

                asyncio.create_task(
                    self._reassert_device_shutdown(
                        device,
                        runtime,
                    )
                )

    def _find_device_by_entity(
        self,
        entity_id: str,
    ) -> OffGridDevice | None:
        """Find a configured device by its controlled entity ID."""

        for device in self._active_devices():
            if device.entity_id == entity_id:
                return device

        return None

    def _find_custom_by_control_entity(
        self,
        entity_id: str,
    ) -> OffGridDevice | None:
        """Find a Custom device by its control entity ID."""

        for device in self._active_devices():
            if (
                device.device_type == "custom"
                and device.control_entity_id == entity_id
            ):
                return device

        return None

    def _subscribe_to_devices(self) -> None:
        """Subscribe to controlled and Custom control entity state changes."""

        subscribed: set[str] = set()

        for device in self._active_devices():
            entity_ids = [device.entity_id]

            if (
                device.device_type == "custom"
                and device.control_entity_id
            ):
                entity_ids.append(device.control_entity_id)

            for entity_id in entity_ids:
                if not entity_id or entity_id in subscribed:
                    continue

                unsubscribe = async_track_state_change_event(
                    self.hass,
                    [entity_id],
                    self._async_state_changed,
                )

                self._unsubscribers.append(
                    unsubscribe
                )
                subscribed.add(entity_id)

                self._log(logging.DEBUG,
                    "OFF-GRID: subscribed to %s (%s)",
                    device.name,
                    entity_id,
                )

    def _subscribe_to_grid_status(self) -> None:
        """Subscribe to inverter grid status changes."""

        unsubscribe = async_track_state_change_event(
            self.hass,
            [self.central.inverter_off_grid_status],
            self._async_grid_state_changed,
        )

        self._unsubscribers.append(
            unsubscribe
        )

        self._log(logging.DEBUG, 
            "OFF-GRID GRID: subscribed to %s",
            self.central.inverter_off_grid_status,
        )

    def _unsubscribe_from_devices(self) -> None:
        """Remove all state listeners."""

        for unsubscribe in self._unsubscribers:
            unsubscribe()

        self._unsubscribers.clear()

    def _start_periodic_sync(self) -> None:
        """Start periodic runtime synchronization."""

        self._sync_unsubscriber = async_track_time_interval(
            self.hass,
            self._async_periodic_sync,
            SYNC_INTERVAL,
        )

        self._log(logging.DEBUG, 
            "OFF-GRID: periodic sync registered "
            "every %s seconds",
            int(SYNC_INTERVAL.total_seconds()),
        )

    def _stop_periodic_sync(self) -> None:
        """Stop periodic runtime synchronization."""

        if self._sync_unsubscriber is not None:
            self._sync_unsubscriber()

            self._sync_unsubscriber = None

    @property
    def running(self) -> bool:
        """Return whether the coordinator is running."""

        return self._running

    @property
    def devices(self):
        """Return all configured devices."""

        return self._active_devices()

    @property
    def device_count(self) -> int:
        """Return the number of configured devices."""

        return len(
            self._active_devices()
        )

    def get_device_runtime(
        self,
        device_id: str,
    ) -> DeviceRuntime | None:
        """Return runtime state for a device."""

        return self.runtime.get_device(
            device_id
        )

    async def async_start(self) -> None:
        """Start the coordinator."""

        if self._running:
            return

        self._subscribe_to_devices()

        self._subscribe_to_grid_status()

        self._start_periodic_sync()

        self._running = True

        self._log(logging.WARNING, 
            "OFF-GRID: coordinator started "
            "with %s device(s)",
            self.device_count,
        )

    async def async_stop(self) -> None:
        """Stop the coordinator."""

        if not self._running:
            return

        self._stop_periodic_sync()

        if self._recovery_task is not None:
            if not self._recovery_task.done():
                self._recovery_task.cancel()

        for task in self._override_tasks.values():
            if not task.done():
                task.cancel()

        self._override_tasks.clear()

        self._unsubscribe_from_devices()

        self._listeners.clear()

        self._running = False

        self._log(logging.WARNING, 
            "OFF-GRID: coordinator stopped"
        )