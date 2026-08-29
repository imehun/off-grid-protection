"""Text entities for Off-grid Protection."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
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
    """Set up Off-grid Protection text entities."""

    coordinator: OffGridCoordinator = hass.data[
        DOMAIN
    ][entry.entry_id]

    entities = []

    for device in coordinator.devices:

        entities.append(
            OffGridOverridePinText(
                coordinator=coordinator,
                device_id=device.id,
                device_name=device.name,
            )
        )

    async_add_entities(entities)


class OffGridOverridePinText(TextEntity):
    """PIN input used by the generated Lovelace card."""

    _attr_icon = "mdi:lock"
    _attr_native_max = 32
    _attr_native_min = 0
    _attr_mode = "password"

    def __init__(
        self,
        coordinator: OffGridCoordinator,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the PIN entity."""

        self.coordinator = coordinator
        self._device_id = device_id

        slug = slugify(device_name)

        self._attr_unique_id = (
            f"{slug}_override_pin"
        )
        self._attr_name = (
            f"{device_name} Override PIN"
        )

        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, device_id)
            },
            "name": device_name,
        }
        self._attr_native_value = ""

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""

        return self.coordinator.running

    async def async_set_value(
        self,
        value: str,
    ) -> None:
        """Store the entered PIN and request an override."""

        self._attr_native_value = str(value)
        self.async_write_ha_state()

        await self.hass.services.async_call(
            DOMAIN,
            "request_override",
            {
                "device_id": self._device_id,
                "pin": str(value),
            },
            blocking=True,
        )

        self._attr_native_value = ""
        self.async_write_ha_state()
