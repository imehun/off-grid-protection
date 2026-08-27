"""Central model for Off-grid Protection."""

from dataclasses import dataclass, field
from typing import Any

from .device import OffGridDevice


@dataclass
class OffGridCentral:
    """Represent the central Off-grid Protection configuration."""

    inverter_off_grid_status: str
    power_meter_status: str
    recovery_delay: int = 60
    central_pin: str = "1234"
    pin_check: bool = True
    recovery_enabled: bool = True

    devices: list[OffGridDevice] = field(
        default_factory=list
    )

    @classmethod
    def from_entry_data(
        cls,
        data: dict[str, Any],
    ) -> "OffGridCentral":
        """Create the central model from ConfigEntry data."""

        central = data.get(
            "central",
            {},
        )

        devices = [
            OffGridDevice.from_dict(device)
            for device in data.get(
                "devices",
                [],
            )
        ]

        return cls(
            inverter_off_grid_status=central.get(
                "inverter_off_grid_status",
                "",
            ),
            power_meter_status=central.get(
                "power_meter_status",
                "",
            ),
            recovery_delay=int(
                central.get(
                    "recovery_delay",
                    60,
                )
            ),
            central_pin=str(
                central.get(
                    "central_pin",
                    "1234",
                )
            ),
            pin_check=bool(
                central.get(
                    "pin_check",
                    True,
                )
            ),
            recovery_enabled=bool(
                central.get(
                    "recovery_enabled",
                    True,
                )
            ),
            devices=devices,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the central model to ConfigEntry data."""

        return {
            "central": {
                "inverter_off_grid_status": (
                    self.inverter_off_grid_status
                ),
                "power_meter_status": (
                    self.power_meter_status
                ),
                "recovery_delay": self.recovery_delay,
                "central_pin": self.central_pin,
                "pin_check": self.pin_check,
                "recovery_enabled": self.recovery_enabled,
            },
            "devices": [
                device.to_dict()
                for device in self.devices
            ],
        }

    def get_device(
        self,
        device_id: str,
    ) -> OffGridDevice | None:
        """Return a device by its ID."""

        for device in self.devices:
            if device.id == device_id:
                return device

        return None

    def add_device(
        self,
        device: OffGridDevice,
    ) -> None:
        """Add a device to the central configuration."""

        self.devices.append(device)

    def remove_device(
        self,
        device_id: str,
    ) -> bool:
        """Remove a device by its ID."""

        device = self.get_device(device_id)

        if device is None:
            return False

        self.devices.remove(device)
        return True