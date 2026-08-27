"""Off-grid Protection integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.components.frontend.storage import async_user_store
from homeassistant.helpers import config_validation as cv
from homeassistant.util import slugify

from .central import OffGridCentral
from .coordinator import OffGridCoordinator
from .notifications import (
    async_generate_house_status_automation,
    async_remove_house_status_automation,
)

DOMAIN = "off_grid_protection"

SERVICE_ACTIVATE_OVERRIDE = "activate_override"
SERVICE_REQUEST_OVERRIDE = "request_override"

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional(
            "duration",
            default=10,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(
                min=1,
                max=60,
            ),
        ),
        vol.Required("pin"): cv.string,
    }
)



async def _get_call_language(
    hass: HomeAssistant,
    call: ServiceCall,
) -> str:
    """Return the frontend language of the user invoking the service."""

    language = hass.config.language

    user_id = call.context.user_id
    if not user_id:
        return language

    try:
        user_store = await async_user_store(
            hass,
            user_id,
        )
        language_data = user_store.data.get(
            "language"
        )

        if isinstance(language_data, dict):
            user_language = language_data.get(
                "language"
            )
            if isinstance(user_language, str) and user_language:
                return user_language

    except Exception:
        # Never let notification localization break the override service.
        pass

    return language


def _override_notification_text(
    language: str,
    *,
    device_reference: str | None = None,
    helper_error: bool = False,
) -> tuple[str, str]:
    """Return localized Override notification title and message."""

    is_english = language.lower().startswith("en")

    if is_english:
        title = "⚠️ OFF-GRID OVERRIDE"

        if helper_error:
            message = (
                "Override was not activated because "
                "the device override helpers are unavailable."
            )
        elif device_reference is not None:
            message = (
                f"Device '{device_reference}' was not found "
                "in the Off-grid Protection configuration."
            )
        else:
            message = (
                "Override was not activated. "
                "Check OFF-GRID status, PIN, "
                "and override duration."
            )

        return title, message

    title = "⚠️ OFF-GRID OVERRIDE"

    if helper_error:
        message = (
            "Override nije aktiviran jer "
            "override helperi za uređaj nisu dostupni."
        )
    elif device_reference is not None:
        message = (
            f"Uređaj '{device_reference}' "
            "nije pronađen u "
            "Off-grid Protection konfiguraciji."
        )
    else:
        message = (
            "Override nije aktiviran. "
            "Provjerite OFF-GRID stanje, "
            "PIN i trajanje overridea."
        )

    return title, message


def _find_device_id(
    coordinator: OffGridCoordinator,
    device_reference: str,
) -> str | None:
    """Resolve device ID from ID, name or entity ID."""

    reference = str(
        device_reference
    ).strip().lower()

    for device in coordinator.devices:
        if device.id.lower() == reference:
            return device.id

        if device.name.lower() == reference:
            return device.id

        if device.entity_id.lower() == reference:
            return device.id

    return None


async def async_setup(
    hass: HomeAssistant,
    config: dict,
) -> bool:
    """Set up the Off-grid Protection integration."""

    hass.data.setdefault(
        DOMAIN,
        {},
    )

    async def handle_activate_override(
        call: ServiceCall,
    ) -> None:
        """Handle an override activation request."""

        device_reference = str(
            call.data["device_id"]
        ).strip()

        duration = int(
            call.data.get(
                "duration",
                10,
            )
        )

        pin = str(
            call.data["pin"]
        )

        coordinators = hass.data.get(
            DOMAIN,
            {},
        )

        for coordinator in coordinators.values():
            device_id = _find_device_id(
                coordinator,
                device_reference,
            )

            if device_id is None:
                continue

            success = (
                await coordinator.async_activate_override(
                    device_id=device_id,
                    duration_minutes=duration,
                    pin=pin,
                )
            )

            if not success:
                language = await _get_call_language(
                    hass,
                    call,
                )
                title, message = _override_notification_text(
                    language,
                )
                persistent_notification.async_create(
                    hass,
                    message=message,
                    title=title,
                    notification_id=(
                        "off_grid_override_error"
                    ),
                )

            return

        language = await _get_call_language(
            hass,
            call,
        )
        title, message = _override_notification_text(
            language,
            device_reference=device_reference,
        )
        persistent_notification.async_create(
            hass,
            message=message,
            title=title,
            notification_id=(
                "off_grid_override_error"
            ),
        )

    async def handle_request_override(
        call: ServiceCall,
    ) -> None:
        """Activate override using the generated device helpers."""

        device_reference = str(
            call.data["device_id"]
        ).strip()

        coordinators = hass.data.get(
            DOMAIN,
            {},
        )

        for coordinator in coordinators.values():
            device_id = _find_device_id(
                coordinator,
                device_reference,
            )

            if device_id is None:
                continue

            device = next(
                (
                    item
                    for item in coordinator.devices
                    if item.id == device_id
                ),
                None,
            )

            if device is None:
                continue

            slug = slugify(device.name)

            duration_entity = (
                f"number.{slug}_override_duration"
            )
            pin_entity = (
                f"text.{slug}_override_pin"
            )

            duration_state = hass.states.get(
                duration_entity
            )
            pin_state = hass.states.get(
                pin_entity
            )

            if (
                duration_state is None
                or pin_state is None
            ):
                language = await _get_call_language(
                    hass,
                    call,
                )
                title, message = _override_notification_text(
                    language,
                    helper_error=True,
                )
                persistent_notification.async_create(
                    hass,
                    message=message,
                    title=title,
                    notification_id=(
                        "off_grid_override_error"
                    ),
                )
                return {"success": False}

            try:
                duration = int(
                    duration_state.state
                )
            except (TypeError, ValueError):
                duration = 0

            pin = str(
                pin_state.state
            )

            success = (
                await coordinator.async_activate_override(
                    device_id=device_id,
                    duration_minutes=duration,
                    pin=pin,
                )
            )

            if not success:
                language = await _get_call_language(
                    hass,
                    call,
                )
                title, message = _override_notification_text(
                    language,
                )
                persistent_notification.async_create(
                    hass,
                    message=message,
                    title=title,
                    notification_id=(
                        "off_grid_override_error"
                    ),
                )

            return {"success": success}

        language = await _get_call_language(
            hass,
            call,
        )
        title, message = _override_notification_text(
            language,
            device_reference=device_reference,
        )
        persistent_notification.async_create(
            hass,
            message=message,
            title=title,
            notification_id=(
                "off_grid_override_error"
            ),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_ACTIVATE_OVERRIDE,
        handle_activate_override,
        schema=SERVICE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_REQUEST_OVERRIDE,
        handle_request_override,
        schema=vol.Schema(
            {
                vol.Required("device_id"): cv.string,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )

    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up Off-grid Protection from a config entry."""

    central = OffGridCentral.from_entry_data(
        entry.data
    )

    logs_enabled = bool(
        entry.data.get(
            "central",
            {},
        ).get(
            "logs",
            True,
        )
    )

    coordinator = OffGridCoordinator(
        hass,
        central,
        logs_enabled=logs_enabled,
    )

    async def _async_update_listener(
        hass: HomeAssistant,
        updated_entry: ConfigEntry,
    ) -> None:
        """Apply central configuration changes without a restart."""

        coordinator.set_logs_enabled(
            bool(
                updated_entry.data.get(
                    "central",
                    {},
                ).get(
                    "logs",
                    True,
                )
            )
        )

    entry.async_on_unload(
        entry.add_update_listener(
            _async_update_listener
        )
    )

    await coordinator.async_start()

    if entry.data.get("type") == "central":
        central_config = entry.data.get(
            "central",
            {},
        )
        notifications = central_config.get(
            "notifications",
            {},
        )

        if notifications.get("enabled"):
            await async_generate_house_status_automation(
                hass,
                automation_id=notifications[
                    "automation_id"
                ],
                inverter_entity=central_config[
                    "inverter_off_grid_status"
                ],
                notification_types=notifications.get(
                    "notification_types",
                    [],
                ),
                notify_targets=notifications.get(
                    "notify_targets",
                    [],
                ),
                browser_mod_targets=notifications.get(
                    "browser_mod_targets",
                    [],
                ),
                language=notifications.get(
                    "language",
                    "en",
                ),
            )

    hass.data.setdefault(
        DOMAIN,
        {}
    )

    hass.data[DOMAIN][
        entry.entry_id
    ] = coordinator

    await hass.config_entries.async_forward_entry_setups(
        entry,
        [
            "binary_sensor",
            "number",
            "sensor",
            "text",
        ],
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload Off-grid Protection."""

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        [
            "binary_sensor",
            "number",
            "sensor",
            "text",
        ],
    )

    coordinator = hass.data[
        DOMAIN
    ].pop(
        entry.entry_id,
        None,
    )

    if coordinator is not None:
        await coordinator.async_stop()

    if entry.data.get("type") == "central":
        generated = (
            entry.data.get(
                "central",
                {},
            ).get(
                "generated_resources",
                {},
            )
        )

        for automation_id in generated.get(
            "automations",
            [],
        ):
            await async_remove_house_status_automation(
                hass,
                automation_id,
            )

    return unload_ok
