"""Number entities for Off-grid Protection."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberEntity,
)
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
    """Set up Off-grid Protection number entities."""

    coordinator: OffGridCoordinator = hass.data[
        DOMAIN
    ][entry.entry_id]

    entities = []

    for device in coordinator.devices:

        entities.append(
            OffGridOverrideDurationNumber(
                coordinator,
                entry,
                device.id,
                device.name,
            )
        )

    async_add_entities(entities)


class OffGridOverrideDurationNumber(
    NumberEntity,
):
    """Represent override duration for a device."""

    _attr_should_poll = False
    _attr_native_unit_of_measurement = "min"
    _attr_mode = "box"
    _attr_icon = "mdi:timer-outline"

    def __init__(
        self,
        coordinator: OffGridCoordinator,
        entry: ConfigEntry,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the number entity."""

        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

        device = coordinator.central.get_device(
            device_id
        )

        if device is None:
            raise ValueError(
                f"Device {device_id} not found"
            )

        slug = slugify(device_name)

        self._attr_unique_id = (
            f"{entry.entry_id}_"
            f"override_duration_{slug}"
        )

        self._attr_name = (
            f"{device_name} Override Duration"
        )

        self._attr_native_min_value = (
            device.minimum_runtime
        )

        self._attr_native_max_value = (
            device.maximum_runtime
        )

        self._attr_native_step = 1

        self._attr_native_value = min(
            max(
                10,
                device.minimum_runtime,
            ),
            device.maximum_runtime,
        )

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""

        return self.coordinator.running

    async def async_set_native_value(
        self,
        value: float,
    ) -> None:
        """Set the requested override duration."""

        device = self.coordinator.central.get_device(
            self._device_id
        )

        if device is None:
            return

        value = max(
            device.minimum_runtime,
            min(
                int(value),
                device.maximum_runtime,
            ),
        )

        self._attr_native_value = value

        self.async_write_ha_state()

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