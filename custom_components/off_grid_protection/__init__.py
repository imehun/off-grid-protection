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
from .coordinator import (
    OffGridCoordinator,
    normalize_log_level,
)
from .notifications import (
    async_generate_house_status_automation,
    async_remove_house_status_automation,
)

DOMAIN = "off_grid_protection"

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_ACTIVATE_OVERRIDE = "activate_override"
SERVICE_REQUEST_OVERRIDE = "request_override"

REQUEST_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional("pin"): cv.string,
    }
)

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

        for coordinator in _iter_central_coordinators(hass):
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

        for coordinator in _iter_central_coordinators(hass):
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

            supplied_pin = call.data.get(
                "pin"
            )

            # The generated Browser Mod flow can issue a second request after
            # the Text entity has already accepted Enter and cleared its value.
            # If the device is already in Override, make that duplicate request
            # idempotent instead of treating the now-empty PIN as invalid.
            if (
                supplied_pin is None
                and not str(pin_state.state).strip()
            ):
                runtime = coordinator.get_device_runtime(
                    device_id
                )
                if (
                    runtime is not None
                    and runtime.override_active
                ):
                    return {"success": True}

            pin = str(
                supplied_pin
                if supplied_pin is not None
                else pin_state.state
            )

            success = (
                await coordinator.async_activate_override(
                    device_id=device_id,
                    duration_minutes=duration,
                    pin=pin,
                )
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
        schema=REQUEST_OVERRIDE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    return True




class _CoordinatorDeviceFilterView:
    """Expose selected devices from a shared central coordinator."""

    def __init__(
        self,
        coordinator: OffGridCoordinator,
        device_ids: set[str],
    ) -> None:
        """Initialize the filtered view."""
        self._coordinator = coordinator
        self._device_ids = device_ids

    @property
    def devices(self):
        """Return only the selected devices."""
        return [
            device
            for device in self._coordinator.devices
            if device.id in self._device_ids
        ]

    @property
    def central(self):
        """Return the shared central configuration."""
        return self._coordinator.central

    @property
    def runtime(self):
        """Return the shared runtime state."""
        return self._coordinator.runtime

    @property
    def running(self) -> bool:
        """Return whether the shared coordinator is running."""
        return self._coordinator.running

    def get_device_runtime(self, device_id: str):
        """Return runtime state from the shared coordinator."""
        return self._coordinator.get_device_runtime(device_id)

    def async_add_listener(self, update_method, context=None):
        """Register a listener on the shared coordinator."""
        return self._coordinator.async_add_listener(
            update_method,
            context,
        )


class _DeviceCoordinatorView:
    """Expose the shared central coordinator for one device Entry."""

    def __init__(
        self,
        coordinator: OffGridCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the device view."""
        self._coordinator = coordinator
        self._device_id = device_id

    @property
    def devices(self):
        """Return only the device represented by this Entry."""
        device = self._coordinator.central.get_device(
            self._device_id
        )
        return [device] if device is not None else []

    @property
    def central(self):
        """Return the shared central configuration."""
        return self._coordinator.central

    @property
    def runtime(self):
        """Return the shared runtime state."""
        return self._coordinator.runtime

    @property
    def running(self) -> bool:
        """Return whether the shared coordinator is running."""
        return self._coordinator.running

    def get_device_runtime(self, device_id: str):
        """Return runtime state from the shared coordinator."""
        return self._coordinator.get_device_runtime(device_id)

    def async_add_listener(self, update_method, context=None):
        """Register a listener on the shared coordinator."""
        return self._coordinator.async_add_listener(
            update_method,
            context,
        )


def _get_central_entry(
    hass: HomeAssistant,
) -> ConfigEntry | None:
    """Return the single OGP central Entry."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get("type") == "central":
            return entry
    return None


def _get_central_coordinator(
    hass: HomeAssistant,
) -> OffGridCoordinator | None:
    """Return the shared central coordinator."""
    central_entry = _get_central_entry(hass)

    if central_entry is None:
        return None

    coordinator = hass.data.get(DOMAIN, {}).get(
        central_entry.entry_id
    )

    if isinstance(coordinator, OffGridCoordinator):
        return coordinator

    return None


def _iter_central_coordinators(
    hass: HomeAssistant,
):
    """Yield only the shared central coordinator."""
    coordinator = _get_central_coordinator(hass)

    if coordinator is not None:
        yield coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up Off-grid Protection from a config entry."""

    if entry.data.get("type") == "device":
        central_entry_id = entry.data.get(
            "central_entry_id"
        )

        central_entry = hass.config_entries.async_get_entry(
            central_entry_id
        )

        if central_entry is None:
            return False

        coordinator = hass.data.get(
            DOMAIN,
            {},
        ).get(
            central_entry.entry_id
        )

        if not isinstance(
            coordinator,
            OffGridCoordinator,
        ):
            from homeassistant.exceptions import ConfigEntryNotReady

            raise ConfigEntryNotReady(
                "The central OGP coordinator is not ready yet."
            )

        device_data = entry.data.get(
            "device",
            {},
        )

        device_id = device_data.get("id")
        if not isinstance(device_id, str):
            return False

        from .device import OffGridDevice

        device = OffGridDevice.from_dict(device_data)

        if coordinator.central.get_device(device.id) is None:
            coordinator.central.add_device(device)
            runtime = coordinator.runtime.add_device(device.id)
            coordinator._update_device_state(
                device,
                runtime,
            )
            coordinator._notify_listeners()

        view = _DeviceCoordinatorView(
            coordinator,
            device.id,
        )

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = view

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

    central = OffGridCentral.from_entry_data(
        entry.data
    )

    logs_level = normalize_log_level(
        entry.data.get(
            "central",
            {},
        ).get(
            "logs",
            "warnings",
        )
    )

    coordinator = OffGridCoordinator(
        hass,
        central,
        logs_level=logs_level,
    )

    # Publish the shared coordinator before starting it. Home Assistant may
    # set up Central and Device config entries concurrently after a restart.
    # Device Entries depend on this shared coordinator, so it must be visible
    # in hass.data before their setup runs.
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Device Entries created by v1.1.3 are separate from the Central Entry.
    # Add their stored devices to the shared central model when the central
    # coordinator is initialized.
    for device_entry in hass.config_entries.async_entries(DOMAIN):
        if device_entry.data.get("type") != "device":
            continue

        if device_entry.data.get("central_entry_id") != entry.entry_id:
            continue

        device_data = device_entry.data.get(
            "device",
            {},
        )
        device_id = device_data.get("id")

        if not isinstance(device_id, str):
            continue

        if coordinator.central.get_device(device_id) is not None:
            continue

        from .device import OffGridDevice

        device = OffGridDevice.from_dict(device_data)
        coordinator.central.add_device(device)
        runtime = coordinator.runtime.add_device(device.id)
        coordinator._update_device_state(
            device,
            runtime,
        )

    async def _async_update_listener(
        hass: HomeAssistant,
        updated_entry: ConfigEntry,
    ) -> None:
        """Apply central configuration changes without a restart."""
        coordinator.set_logs_level(
            normalize_log_level(
                updated_entry.data.get(
                    "central",
                    {},
                ).get(
                    "logs",
                    "warnings",
                )
            )
        )

    entry.async_on_unload(
        entry.add_update_listener(
            _async_update_listener
        )
    )

    await coordinator.async_start()

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
            notification_events=notifications.get(
                "notification_events",
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

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Only devices stored directly in the Central Entry are exposed by the
    # Central Entry entity platforms. Device Entries create their own entity
    # platforms through a per-device shared-coordinator view.
    legacy_device_ids = {
        device.id
        for device in OffGridCentral.from_entry_data(
            entry.data
        ).devices
    }

    hass.data[DOMAIN][entry.entry_id] = _CoordinatorDeviceFilterView(
        coordinator,
        legacy_device_ids,
    )

    await hass.config_entries.async_forward_entry_setups(
        entry,
        [
            "binary_sensor",
            "number",
            "sensor",
            "text",
        ],
    )

    # Restore the real central coordinator for services and Device Entries.
    hass.data[DOMAIN][entry.entry_id] = coordinator

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload Off-grid Protection."""

    if entry.data.get("type") == "device":
        unload_ok = await hass.config_entries.async_unload_platforms(
            entry,
            [
                "binary_sensor",
                "number",
                "sensor",
                "text",
            ],
        )

        central_entry_id = entry.data.get(
            "central_entry_id"
        )

        coordinator = hass.data.get(
            DOMAIN,
            {},
        ).get(
            central_entry_id
        )

        device_data = entry.data.get(
            "device",
            {},
        )
        device_id = device_data.get("id")

        if isinstance(
            coordinator,
            OffGridCoordinator,
        ) and isinstance(
            device_id,
            str,
        ):
            coordinator.central.remove_device(
                device_id
            )
            coordinator.runtime.remove_device(
                device_id
            )
            coordinator._notify_listeners()

        hass.data.get(
            DOMAIN,
            {},
        ).pop(
            entry.entry_id,
            None,
        )

        return unload_ok

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        [
            "binary_sensor",
            "number",
            "sensor",
            "text",
        ],
    )

    coordinator = hass.data.get(
        DOMAIN,
        {},
    ).pop(
        entry.entry_id,
        None,
    )

    if isinstance(
        coordinator,
        OffGridCoordinator,
    ):
        await coordinator.async_stop()

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
