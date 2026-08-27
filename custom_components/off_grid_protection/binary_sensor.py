"""Binary sensors for Off-grid Protection."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from . import DOMAIN
from .coordinator import OffGridCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Off-grid Protection binary sensors."""

    coordinator: OffGridCoordinator = hass.data[
        DOMAIN
    ][entry.entry_id]

    entities = []

    for device in coordinator.devices:

        entities.append(
            OffGridLockedBinarySensor(
                coordinator,
                entry,
                device.id,
                device.name,
            )
        )

    async_add_entities(entities)


class OffGridLockedBinarySensor(
    BinarySensorEntity,
):
    """Represent the OGP lock state of a device."""

    _attr_should_poll = False
    _attr_icon = "mdi:lock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: OffGridCoordinator,
        entry: ConfigEntry,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the binary sensor."""

        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

        slug = slugify(device_name)

        self._attr_unique_id = (
            f"{entry.entry_id}_"
            f"locked_{slug}"
        )

        self._attr_name = (
            f"{device_name} Off-grid Protection Locked"
        )

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""

        return self.coordinator.running

    @property
    def is_on(self) -> bool:
        """Return whether the device is locked."""

        runtime = self.coordinator.get_device_runtime(
            self._device_id
        )

        if runtime is None:
            return False

        return runtime.locked

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