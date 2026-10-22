"""Button entities for Off-grid Protection."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Set up one Override button per configured device."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        OffGridOverrideButton(coordinator, device.id, device.name)
        for device in coordinator.devices
    ]
    async_add_entities(entities)


class OffGridOverrideButton(ButtonEntity):
    """Button to activate the configured per-device Override duration."""

    _attr_icon = "mdi:shield-alert"
    _attr_has_entity_name = True

    def __init__(self, coordinator: OffGridCoordinator, device_id: str, device_name: str) -> None:
        self.coordinator = coordinator
        self._device_id = device_id
        self._attr_unique_id = f"{slugify(device_name)}_override_button"
        self._attr_name = "Override"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "name": device_name,
        }

    @property
    def available(self) -> bool:
        return self.coordinator.running

    async def async_press(self) -> None:
        """Request Override; service validates that duration is configured."""
        await self.hass.services.async_call(
            DOMAIN,
            "request_override",
            {"device_id": self._device_id},
            blocking=True,
        )