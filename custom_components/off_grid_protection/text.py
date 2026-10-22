"""Legacy text platform for Off-grid Protection.

Override no longer uses PINs. Keep this platform module for compatibility with
existing installations, but do not create or store PIN text entities.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Do not register legacy Override PIN entities."""
    return