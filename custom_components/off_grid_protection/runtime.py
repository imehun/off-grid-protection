"""Runtime state model for Off-grid Protection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class GridStatus(StrEnum):
    """Grid status."""

    UNKNOWN = "unknown"
    ON_GRID = "on_grid"
    OFF_GRID = "off_grid"


@dataclass
class DeviceRuntime:
    """Runtime state of one protected device."""

    device_id: str

    available: bool = False
    state: str | None = None

    shutdown_requested: bool = False
    shutdown_confirmed: bool = False
    shutdown_failed: bool = False

    locked: bool = False

    override_active: bool = False
    override_started_at: float | None = None
    override_duration_minutes: int = 0

    recovery_started: bool = False
    recovery_completed: bool = False

    # Snapshot of the Custom control entity state captured before protection.
    # Used by Custom devices instead of automation snapshot/restore.
    custom_control_state: str | None = None

    # Automation states captured before protection.
    # True means the automation was enabled before off-grid.
    automation_states: dict[str, bool] = field(
        default_factory=dict
    )


@dataclass
class OffGridRuntime:
    """Runtime state of the central protection system."""

    grid_status: GridStatus = GridStatus.UNKNOWN

    protection_active: bool = False
    protection_cycle_complete: bool = False

    recovery_active: bool = False

    central_lock: bool = False
    central_override: bool = False

    devices: dict[str, DeviceRuntime] = field(
        default_factory=dict
    )

    def get_device(
        self,
        device_id: str,
    ) -> DeviceRuntime | None:
        """Return runtime state for a device."""

        return self.devices.get(device_id)

    def add_device(
        self,
        device_id: str,
    ) -> DeviceRuntime:
        """Create runtime state for a device."""

        if device_id not in self.devices:
            self.devices[device_id] = DeviceRuntime(
                device_id=device_id
            )

        return self.devices[device_id]

    def remove_device(
        self,
        device_id: str,
    ) -> None:
        """Remove runtime state for a device."""

        self.devices.pop(
            device_id,
            None,
        )

    def start_protection_cycle(self) -> None:
        """Start a protection cycle."""

        self.protection_active = True
        self.protection_cycle_complete = False
        self.recovery_active = False

        for device in self.devices.values():
            device.shutdown_requested = False
            device.shutdown_confirmed = False
            device.shutdown_failed = False
            device.locked = False

            device.override_active = False
            device.override_started_at = None
            device.override_duration_minutes = 0

            device.recovery_started = False
            device.recovery_completed = False

    def complete_protection_cycle(self) -> None:
        """Mark the protection cycle as complete."""

        self.protection_cycle_complete = True

    def reset_protection(self) -> None:
        """Reset the central protection state."""

        self.protection_active = False
        self.protection_cycle_complete = False
        self.recovery_active = False
        self.central_lock = False

        for device in self.devices.values():
            device.shutdown_requested = False
            device.shutdown_confirmed = False
            device.shutdown_failed = False
            device.locked = False

            device.override_active = False
            device.override_started_at = None
            device.override_duration_minutes = 0

            device.recovery_started = False
            device.recovery_completed = False