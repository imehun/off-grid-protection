"""Sensors for Off-grid Protection."""

from __future__ import annotations

import time

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from . import DOMAIN
from .coordinator import OffGridCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Off-grid Protection sensors."""

    coordinator: OffGridCoordinator = hass.data[
        DOMAIN
    ][entry.entry_id]

    entities = []

    for device in coordinator.devices:

        entities.append(
            OffGridOverrideRemainingSensor(
                coordinator,
                entry,
                device.id,
                device.name,
            )
        )

        entities.append(
            OffGridDeviceStatusSensor(
                coordinator,
                entry,
                device.id,
                device.name,
            )
        )

    async_add_entities(entities)


class OffGridOverrideRemainingSensor(
    SensorEntity,
):
    """Represent remaining override time for a device."""

    _attr_should_poll = False
    _attr_icon = "mdi:timer-sand"

    def __init__(
        self,
        coordinator: OffGridCoordinator,
        entry: ConfigEntry,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""

        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

        slug = slugify(device_name)

        self._attr_unique_id = (
            f"{entry.entry_id}_"
            f"override_remaining_{slug}"
        )

        self._attr_name = (
            f"{device_name} Override Remaining"
        )

        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, device_id)
            },
            "name": device_name,
        }

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""

        return self.coordinator.running

    @property
    def native_value(self) -> str:
        """Return remaining override time as MM:SS."""

        runtime = self.coordinator.get_device_runtime(
            self._device_id
        )

        if runtime is None:
            return "00:00"

        if not runtime.override_active:
            return "00:00"

        if runtime.override_started_at is None:
            return "00:00"

        total_seconds = (
            runtime.override_duration_minutes * 60
        )

        elapsed = (
            time.monotonic()
            - runtime.override_started_at
        )

        remaining_seconds = max(
            0,
            int(
                total_seconds - elapsed
            ),
        )

        minutes, seconds = divmod(
            remaining_seconds,
            60,
        )

        return f"{minutes:02d}:{seconds:02d}"

    async def async_added_to_hass(self) -> None:
        """Register the coordinator listener."""

        await super().async_added_to_hass()

        self.async_on_remove(
            self.coordinator.async_add_listener(
                self._handle_coordinator_update
            )
        )

    def _handle_coordinator_update(self) -> None:
        """Handle a runtime update."""

        self.async_write_ha_state()

class OffGridDeviceStatusSensor(
    SensorEntity,
):
    """Represent the current OGP protection status of a device."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "protection_status"
    _attr_icon = "mdi:shield-lock-outline"

    def __init__(
        self,
        coordinator: OffGridCoordinator,
        entry: ConfigEntry,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""

        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

        slug = slugify(device_name)

        self._attr_unique_id = (
            f"{entry.entry_id}_"
            f"status_{slug}"
        )

        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, device_id)
            }
        }

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""

        return self.coordinator.running

    def _get_status(
        self,
    ) -> tuple[str, str]:
        """Return the current protection status and remaining time."""

        runtime = self.coordinator.get_device_runtime(
            self._device_id
        )

        if runtime is None:
            return "ready", ""

        if runtime.override_active:
            remaining_seconds = 0

            if runtime.override_started_at is not None:
                total_seconds = (
                    runtime.override_duration_minutes * 60
                )
                elapsed = (
                    time.monotonic()
                    - runtime.override_started_at
                )
                remaining_seconds = max(
                    0,
                    int(total_seconds - elapsed),
                )

            minutes, seconds = divmod(
                remaining_seconds,
                60,
            )

            return (
                "override",
                f"{minutes:02d}:{seconds:02d}",
            )

        if runtime.locked:
            return "locked", ""

        return "ready", ""

    @property
    def native_value(self) -> str:
        """Return the current protection status key."""

        status, _ = self._get_status()
        return status

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return status details."""

        status, detail = self._get_status()

        if status == "override":
            return {"remaining": detail}

        return {}

    async def async_added_to_hass(self) -> None:
        """Register the coordinator listener."""

        await super().async_added_to_hass()

        self.async_on_remove(
            self.coordinator.async_add_listener(
                self._handle_coordinator_update
            )
        )

    def _handle_coordinator_update(self) -> None:
        """Handle a runtime update."""

        self.async_write_ha_state()
