"""Config flow for Off-grid Protection."""

from __future__ import annotations

from uuid import uuid4
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import automation
from homeassistant.const import CONF_NAME
from homeassistant.components import persistent_notification
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from . import DOMAIN
from .lovelace import generate_setup_instructions
from .coordinator import normalize_log_level
from .runtime import GridStatus
from .notifications import (
    AUTOMATION_ID_PREFIX,
    async_generate_house_status_automation,
    async_remove_house_status_automation,
    get_notify_options,
    get_browser_mod_device_options,
    _load_notification_texts,
)


def _get_automation_options(
    hass,
    entity_id: str,
    show_all: bool = False,
    selected: list[str] | None = None,
) -> list[dict[str, str]]:
    """Return automation selector options relevant to an entity.

    Home Assistant's automation component already maintains the complete
    referenced-entity information for loaded automations. Use that instead
    of trying to reconstruct automation YAML from entity state attributes.
    """
    selected = selected or []

    if show_all:
        automation_ids = [
            state.entity_id
            for state in hass.states.async_all("automation")
        ]
    else:
        automation_ids = automation.automations_with_entity(
            hass,
            entity_id,
        )

        # Preserve already-associated automations when editing a device,
        # even if their current configuration no longer references the
        # selected device.
        automation_ids = list(
            dict.fromkeys(
                [*automation_ids, *selected]
            )
        )

    options: list[dict[str, str]] = []

    for automation_id in automation_ids:
        state = hass.states.get(automation_id)
        if state is None:
            continue

        options.append(
            {
                "value": automation_id,
                "label": state.name,
            }
        )

    options.sort(
        key=lambda option: option["label"].lower()
    )

    return options

async def _async_show_restart_required_notification(
    hass,
    language: str | None,
) -> None:
    """Show the restart notification in the OGP notification language."""
    if language not in ("hr", "en"):
        language = "en"

    texts = await _load_notification_texts(hass, language)
    persistent_notification.async_create(
        hass,
        message=texts["restart_required_message"],
        title=texts["restart_required_title"],
        notification_id="off_grid_protection_restart_required",
    )


def _get_configured_main_entity_ids(
    hass,
    central_entry_id: str,
) -> set[str]:
    """Return main entity IDs already assigned to OGP device entries."""
    configured: set[str] = set()

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get("type") != "device":
            continue
        if entry.data.get("central_entry_id") != central_entry_id:
            continue

        device = entry.data.get("device", {})
        entity_id = device.get("entity_id")
        if not entity_id:
            entity_id = device.get("type_config", {}).get("entity_id")

        if entity_id:
            configured.add(entity_id)

    return configured


def _ogp_settings_locked_off_grid(
    hass,
    config_entry,
) -> bool:
    """Return True while OGP is actively protecting the system OFF-GRID."""
    central_entry_id = config_entry.entry_id

    if config_entry.data.get("type") == "device":
        central_entry_id = config_entry.data.get("central_entry_id")

    if not isinstance(central_entry_id, str):
        return False

    coordinator = hass.data.get(DOMAIN, {}).get(
        central_entry_id
    )

    if coordinator is None:
        return False

    runtime = getattr(coordinator, "runtime", None)
    if runtime is None:
        return False

    return (
        runtime.grid_status == GridStatus.OFF_GRID
        and runtime.protection_active
    )


class OffGridProtectionConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Handle a config flow for Off-grid Protection."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Create the options flow."""

        return OffGridProtectionOptionsFlow()

    async def async_step_user(
        self,
        user_input=None,
    ):
        """Handle the name of the configuration or device."""

        central_entries = [
            entry
            for entry in self.hass.config_entries.async_entries(
                DOMAIN
            )
            if entry.data.get("type") == "central"
        ]

        self._central_entry = (
            central_entries[0]
            if central_entries
            else None
        )

        if user_input is not None:
            self._device_name = user_input[
                CONF_NAME
            ]
            return await self.async_step_type()

        default_name = ("" if self._central_entry else "OGP – Off-grid Battery Protection")

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME,
                    default=default_name,
                ): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )

    async def async_step_type(
        self,
        user_input=None,
    ):
        """Select the configuration type."""

        if self._central_entry:
            # An existing central means this Add flow adds a protected
            # device; it must never create another central configuration.
            available_types = {
                "climate": "Climate",
                "switch": "Switch",
                "custom": "Custom",
            }
        else:
            available_types = {
                "central": "Central Setup",
            }

        if user_input is not None:
            self._configuration_type = user_input[
                "type"
            ]

            if self._configuration_type == "central":
                return await self.async_step_central()

            if self._configuration_type == "climate":
                return await self.async_step_climate()

            if self._configuration_type == "switch":
                return await self.async_step_switch()

            return await self.async_step_custom()

        schema = vol.Schema(
            {
                vol.Required("type"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(available_types),
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="configuration_type",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="type",
            data_schema=schema,
        )

    async def _async_create_central_entry(
        self,
        central_config: dict,
    ):
        """Create the central OGP config entry."""
        return self.async_create_entry(
            title=self._device_name,
            data={
                "type": "central",
                "central": central_config,
            },
        )

    async def _async_finalize_central_notifications(
        self,
        central_config: dict,
        notification_config: dict,
    ):
        """Store and generate the central notification automation."""
        central_config = dict(central_config)
        notification_config = dict(notification_config)
        automation_id = notification_config.get(
            "automation_id"
        ) or f"{AUTOMATION_ID_PREFIX}_{uuid4().hex[:12]}"
        notification_config["automation_id"] = automation_id
        central_config["notifications"] = notification_config

        automation_id = await async_generate_house_status_automation(
            self.hass,
            automation_id=automation_id,
            inverter_entity=central_config[
                "inverter_off_grid_status"
            ],
            notification_types=notification_config[
                "notification_types"
            ],
            notification_events=notification_config[
                "notification_events"
            ],
            notify_targets=notification_config[
                "notify_targets"
            ],
            browser_mod_targets=notification_config[
                "browser_mod_targets"
            ],
            language=notification_config[
                "language"
            ],
            notification_mode=notification_config.get(
                "notification_mode",
                "global",
            ),
            custom_targets=notification_config.get(
                "custom_targets",
            ),
        )

        central_config["generated_resources"] = {
            "automations": [
                automation_id,
            ],
        }

        return await self._async_create_central_entry(
            central_config
        )

    async def async_step_central(
        self,
        user_input=None,
    ):
        """Configure central protection settings."""

        # Never create a second OGP central configuration.
        if self._central_entry is not None:
            return self.async_abort(
                reason="central_already_configured",
            )


        if user_input is not None:
            central_config = dict(user_input)

            if central_config.get(
                "notifications_enabled",
                False,
            ):
                self._central_config = central_config
                self._central_changed = central_changed
                return await self.async_step_central_notifications()

            return await self._async_create_central_entry(
                central_config
            )

        schema = vol.Schema(
            {
                vol.Required(
                    "inverter_off_grid_status",
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=[
                            "sensor",
                            "input_select",
                        ],
                    )
                ),
                vol.Required(
                    "power_meter_status",
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                    )
                ),
                vol.Required(
                    "recovery_delay",
                    default=60,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=600,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Required(
                    "central_pin",
                    default="1234",
                ): str,
                vol.Required(
                    "pin_check",
                    default=True,
                ): bool,
                vol.Required(
                    "recovery_enabled",
                    default=True,
                ): bool,
                vol.Required(
                    "logs",
                    default="warnings",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            "off",
                            "warnings",
                            "debug",
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="log_level",
                    )
                ),
                vol.Required(
                    "notifications_enabled",
                    default=False,
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="central",
            data_schema=schema,
        )


    async def async_step_custom_notification_targets(
        self,
        user_input=None,
        current=None,
    ):
        """Select notification targets for per-device notification mode."""
        current = current or getattr(self, "_current_notification_config", {})

        if user_input is not None:
            self._custom_notify_targets = list(
                user_input.get("notify_targets", [])
            )
            self._custom_browser_mod_targets = list(
                user_input.get("browser_mod_targets", [])
            )

            if not self._custom_notify_targets and not self._custom_browser_mod_targets:
                return self.async_show_form(
                    step_id="custom_notification_targets",
                    data_schema=self._custom_notification_targets_schema(
                        current,
                        user_input,
                    ),
                    errors={"base": "custom_target_required"},
                )

            self._custom_notification_language = user_input.get(
                "notification_language",
                current.get("language", "en"),
            )
            return await self.async_step_custom_notification_preferences(
                current=current,
            )

        return self.async_show_form(
            step_id="custom_notification_targets",
            data_schema=self._custom_notification_targets_schema(current),
        )

    def _custom_notification_targets_schema(
        self,
        current=None,
        submitted=None,
    ):
        """Build the target selector for per-device notification mode."""
        current = current or {}
        submitted = submitted or {}
        custom = current.get("custom_targets", {})

        notify_default = submitted.get(
            "notify_targets",
            list(custom.get("notify", {}).keys())
            or current.get("notify_targets", []),
        )
        popup_default = submitted.get(
            "browser_mod_targets",
            list(custom.get("popup", {}).keys())
            or current.get("browser_mod_targets", []),
        )

        return vol.Schema(
            {
                vol.Optional(
                    "notify_targets",
                    default=notify_default,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=get_notify_options(self.hass),
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "browser_mod_targets",
                    default=popup_default,
                ): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(
                        integration="browser_mod",
                        multiple=True,
                    )
                ),
                vol.Required(
                    "notification_language",
                    default=submitted.get(
                        "notification_language",
                        current.get("language", "en"),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "en", "label": "English"},
                            {"value": "hr", "label": "Hrvatski"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    async def async_step_custom_notification_preferences(
        self,
        user_input=None,
        current=None,
    ):
        """Configure notification events independently for each target."""
        current = current or getattr(self, "_current_notification_config", {})

        notify_targets = list(
            getattr(self, "_custom_notify_targets", [])
        )
        browser_targets = list(
            getattr(self, "_custom_browser_mod_targets", [])
        )

        # Build a stable mapping from form field names to target IDs.
        target_fields: dict[str, tuple[str, str]] = {}
        fields: dict = {}
        language = getattr(
            self,
            "_custom_notification_language",
            current.get("language", "en"),
        )
        event_options = [
            {
                "value": "grid",
                "label": "Status mreže" if language == "hr" else "Grid status",
            },
            {
                "value": "protection",
                "label": "Zaštita / Override" if language == "hr" else "Protection / Override",
            },
            {
                "value": "security",
                "label": "Sigurnost" if language == "hr" else "Security",
            },
        ]

        old_custom = current.get("custom_targets", {})
        old_notify = old_custom.get("notify", {})
        old_popup = old_custom.get("popup", {})

        for index, target in enumerate(notify_targets):
            options = get_notify_options(self.hass)
            label = next(
                (
                    item["label"]
                    for item in options
                    if item["value"] == target
                ),
                target,
            )
            field = f"📱 {label}"
            target_fields[field] = ("notify", target)
            fields[
                vol.Required(
                    field,
                    default=list(old_notify.get(target, ["grid", "protection", "security"])),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=event_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        browser_options = get_browser_mod_device_options(self.hass)
        for index, target in enumerate(browser_targets):
            label = next(
                (
                    item["label"]
                    for item in browser_options
                    if item["value"] == target
                ),
                target,
            )
            field = f"🖥️ {label}"
            target_fields[field] = ("popup", target)
            fields[
                vol.Required(
                    field,
                    default=list(old_popup.get(target, ["grid", "protection", "security"])),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=event_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        self._custom_target_fields = target_fields
        schema = vol.Schema(fields)

        if user_input is not None:
            custom_targets = {"notify": {}, "popup": {}}
            selected_events: set[str] = set()

            for field, (target_type, target) in target_fields.items():
                events = list(user_input.get(field, []))
                custom_targets[target_type][target] = events
                selected_events.update(events)

            if not selected_events:
                return self.async_show_form(
                    step_id="custom_notification_preferences",
                    data_schema=schema,
                    errors={"base": "custom_event_required"},
                )

            language = getattr(
                self,
                "_custom_notification_language",
                current.get("language", "en"),
            )

            notification_config = {
                "enabled": True,
                "notification_mode": "custom",
                "notification_types": [
                    target_type
                    for target_type, values in custom_targets.items()
                    if values
                ],
                "notification_events": sorted(selected_events),
                "notify_targets": notify_targets,
                "browser_mod_targets": browser_targets,
                "custom_targets": custom_targets,
                "language": language,
            }

            return await self._async_finalize_central_notifications(
                self._central_config,
                notification_config,
            )

        return self.async_show_form(
            step_id="custom_notification_preferences",
            data_schema=schema,
        )


    async def async_step_central_notifications(
        self,
        user_input=None,
    ):
        """Configure central house-status notifications."""

        if user_input is not None:
            mode = user_input.get("notification_mode", "global")
            if mode == "custom":
                self._current_notification_config = dict(
                    getattr(self, "_current_notification_config", {})
                )
                self._current_notification_config.update(user_input)
                self._custom_notification_language = user_input.get(
                    "notification_language", "en"
                )
                return await self.async_step_custom_notification_targets(
                    current=self._current_notification_config,
                )

            notification_types = []
            if user_input.get("send_notification", False):
                notification_types.append("notify")
            if user_input.get("send_popup", False):
                notification_types.append("popup")
            notification_events = []
            if user_input.get("notify_grid_status", True):
                notification_events.append("grid")
            if user_input.get("notify_protection_status", True):
                notification_events.append("protection")
            if user_input.get("notify_security", True):
                notification_events.append("security")

            notify_targets = list(user_input.get("notify_targets", []))
            browser_mod_targets = list(user_input.get("browser_mod_targets", []))

            if not notification_types:
                return self.async_show_form(
                    step_id="central_notifications",
                    data_schema=self._central_notifications_schema(user_input),
                    errors={"base": "notification_type_required"},
                )
            if "notify" in notification_types and not notify_targets:
                return self.async_show_form(
                    step_id="central_notifications",
                    data_schema=self._central_notifications_schema(user_input),
                    errors={"base": "notify_target_required"},
                )
            if "popup" in notification_types and not browser_mod_targets:
                return self.async_show_form(
                    step_id="central_notifications",
                    data_schema=self._central_notifications_schema(user_input),
                    errors={"base": "browser_mod_target_required"},
                )

            notification_config = {
                "enabled": True,
                "notification_mode": "global",
                "notification_types": notification_types,
                "notification_events": notification_events,
                "notify_targets": notify_targets,
                "browser_mod_targets": browser_mod_targets,
                "language": user_input.get("notification_language", "en"),
            }

            return await self._async_finalize_central_notifications(
                self._central_config,
                notification_config,
            )

        current = getattr(self, "_current_notification_config", {})
        return self.async_show_form(
            step_id="central_notifications",
            data_schema=self._central_notifications_schema(current),
        )

    def _central_notifications_schema(
        self,
        current: dict | None = None,
    ):
        """Build the central notification selector schema."""
        current = current or {}
        return vol.Schema(
            {
                vol.Required(
                    "notification_mode",
                    default=current.get("notification_mode", "global"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["global", "custom"],
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="notification_mode",
                    )
                ),
                vol.Required(
                    "send_notification",
                    default=current.get(
                        "send_notification",
                        "notify" in current.get("notification_types", ["notify"]),
                    ),
                ): bool,
                vol.Required(
                    "send_popup",
                    default=current.get(
                        "send_popup",
                        "popup" in current.get("notification_types", []),
                    ),
                ): bool,
                vol.Optional(
                    "notify_targets",
                    default=current.get("notify_targets", []),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=get_notify_options(self.hass),
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "browser_mod_targets",
                    default=current.get("browser_mod_targets", []),
                ): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(
                        integration="browser_mod",
                        multiple=True,
                    )
                ),
                vol.Required(
                    "notify_grid_status",
                    default="grid" in current.get(
                        "notification_events",
                        ["grid", "protection", "security"],
                    ),
                ): bool,
                vol.Required(
                    "notify_protection_status",
                    default="protection" in current.get(
                        "notification_events",
                        ["grid", "protection", "security"],
                    ),
                ): bool,
                vol.Required(
                    "notify_security",
                    default="security" in current.get(
                        "notification_events",
                        ["grid", "protection", "security"],
                    ),
                ): bool,
                vol.Required(
                    "notification_language",
                    default=current.get("language", "en"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "en", "label": "English"},
                            {"value": "hr", "label": "Hrvatski"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )


    async def async_step_climate(
        self,
        user_input=None,
    ):
        """Configure a climate device."""

        if user_input is not None:
            self._device_config = user_input
            return await self.async_step_automations()

        configured_entities = _get_configured_main_entity_ids(
            self.hass,
            self._central_entry.entry_id,
        )
        available_entities = [
            entity_id
            for entity_id in self.hass.states.async_entity_ids("climate")
            if entity_id not in configured_entities
        ]

        schema = vol.Schema(
            {
                vol.Required(
                    "entity_id",
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        include_entities=available_entities,
                    )
                ),
                vol.Required(
                    "shutdown_action",
                    default="turn_off",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["turn_off"],
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="shutdown_action",
                    )
                ),
                vol.Required(
                    "off_state",
                    default="off",
                ): str,
                vol.Required(
                    "wait_for_unavailable",
                    default=True,
                ): bool,
                vol.Required(
                    "recovery_timeout",
                    default=180,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=900,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    "command_timeout",
                    default=15,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=120,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="climate",
            data_schema=schema,
        )

    async def async_step_switch(
        self,
        user_input=None,
    ):
        """Configure a switch device."""

        if user_input is not None:
            self._device_config = user_input
            return await self.async_step_automations()

        configured_entities = _get_configured_main_entity_ids(
            self.hass,
            self._central_entry.entry_id,
        )
        available_entities = [
            entity_id
            for entity_id in self.hass.states.async_entity_ids("switch")
            if entity_id not in configured_entities
        ]

        schema = vol.Schema(
            {
                vol.Required(
                    "entity_id",
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        include_entities=available_entities,
                    )
                ),
                vol.Required(
                    "shutdown_action",
                    default="turn_off",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["turn_off"],
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="shutdown_action",
                    )
                ),
                vol.Required(
                    "off_state",
                    default="off",
                ): str,
                vol.Required(
                    "wait_for_unavailable",
                    default=True,
                ): bool,
                vol.Required(
                    "recovery_timeout",
                    default=180,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=900,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    "command_timeout",
                    default=15,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=120,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="switch",
            data_schema=schema,
        )

    async def async_step_custom(
        self,
        user_input=None,
    ):
        """Configure a fully generic Custom device."""

        if user_input is not None:
            self._device_config = user_input
            # Custom Climate does not use OGP automation snapshot/disable.
            # The selected control entity represents the complete external
            # control integration (for example a CC enable switch).
            self._device_automations = []
            return await self.async_step_override()

        configured_entities = _get_configured_main_entity_ids(
            self.hass,
            self._central_entry.entry_id,
        )
        available_entities = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.entity_id not in configured_entities
        ]

        schema = vol.Schema(
            {
                vol.Required(
                    "entity_id",
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        include_entities=available_entities
                    )
                ),
                vol.Required(
                    "control_entity_id",
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        include_entities=available_entities
                    )
                ),
                vol.Required(
                    "shutdown_action",
                    default="turn_off",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["turn_off"],
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="shutdown_action",
                    )
                ),
                vol.Required(
                    "off_state",
                    default="off",
                ): str,
                vol.Required(
                    "recovery_action",
                    default="stay_off",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["stay_off", "turn_on"],
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="recovery_action",
                    )
                ),
                vol.Required(
                    "wait_for_unavailable",
                    default=True,
                ): bool,
                vol.Required(
                    "recovery_timeout",
                    default=180,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=900,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    "command_timeout",
                    default=15,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=120,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="custom",
            data_schema=schema,
        )

    async def async_step_automations(
        self,
        user_input=None,
    ):
        """Select automations associated with the device."""

        entity_id = self._device_config.get(
            "entity_id",
            "",
        )

        if user_input is not None:
            self._device_automations = user_input.get(
                "automations",
                [],
            )
            return await self.async_step_override()

        # Custom devices intentionally see all Home Assistant automations.
        # The selected custom entity may belong to any HA domain, so the
        # automation list must not be filtered by that entity.
        options = _get_automation_options(
            self.hass,
            entity_id,
            show_all=True,
        )

        schema = vol.Schema(
            {
                vol.Optional(
                    "automations",
                    default=[],
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="automations",
            data_schema=schema,
        )

    async def async_step_override(
        self,
        user_input=None,
    ):
        """Configure device override settings."""

        if user_input is not None:
            self._device_override = user_input
            return await self.async_step_lovelace_language()

        schema = vol.Schema(
            {
                vol.Required(
                    "override_enabled",
                    default=True,
                ): bool,
                vol.Required(
                    "require_pin",
                    default=True,
                ): bool,
                vol.Required(
                    "minimum_runtime",
                    default=1,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=60,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
                vol.Required(
                    "maximum_runtime",
                    default=60,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=60,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="override",
            data_schema=schema,
        )


    async def async_step_lovelace_language(
        self,
        user_input=None,
    ):
        """Select language for generated Lovelace YAML."""

        if user_input is not None:
            self._lovelace_language = user_input["lovelace_language"]
            return await self.async_step_generate()

        schema = vol.Schema(
            {
                vol.Required(
                    "lovelace_language",
                    default="en",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "en", "label": "English"},
                            {"value": "hr", "label": "Hrvatski"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="lovelace_language",
            data_schema=schema,
        )

    async def async_step_generate(
        self,
        user_input=None,
    ):
        """Generate resources and Lovelace setup instructions."""

        if user_input is not None:
            generate_yaml = user_input.get(
                "generate_lovelace_yaml",
                False,
            )

            device = {
                "id": uuid4().hex,
                "name": self._device_name,
                "type": self._configuration_type,
                "entity_id": self._device_config[
                    "entity_id"
                ],
                "type_config": dict(
                    self._device_config
                ),
                "automations": list(
                    self._device_automations
                ),
                "override": dict(
                    self._device_override
                ),
                "generated_resources": {
                    "entities": [],
                    "automations": [],
                    "helpers": [],
                },
            }

            slug = slugify(self._device_name)

            device["generated_resources"]["entities"] = [
                f"binary_sensor.{slug}_off_grid_protection_locked",
                f"number.{slug}_override_duration",
                f"sensor.{slug}_override_remaining",
                f"sensor.{slug}_protection_status",
                f"text.{slug}_override_pin",
            ]

            if generate_yaml:
                instructions = generate_setup_instructions(
                    device_name=self._device_name,
                    device_entity_id=self._device_config["entity_id"],
                    language=self._lovelace_language,
                )

                persistent_notification.async_create(
                    self.hass,
                    message=instructions,
                    title=(
                        f"OGP – Off-grid Protection — "
                        f"Lovelace: {self._device_name}"
                    ),
                    notification_id=(
                        f"off_grid_lovelace_{device['id']}"
                    ),
                )

            return self.async_create_entry(
                title=self._device_name,
                data={
                    "type": "device",
                    "central_entry_id": self._central_entry.entry_id,
                    "device": device,
                },
            )

        schema = vol.Schema(
            {
                vol.Optional(
                    "generate_lovelace_yaml",
                    default=False,
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="generate",
            data_schema=schema,
        )


class OffGridProtectionOptionsFlow(
    config_entries.OptionsFlow
):
    """Handle options for Off-grid Protection."""

    async def _async_reload_ogp_device_entries(self) -> None:
        """Reload all OGP device entries belonging to this central entry."""

        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get("type") != "device":
                continue

            if entry.data.get("central_entry_id") != self.config_entry.entry_id:
                continue

            if entry.disabled_by is not None:
                continue

            await self.hass.config_entries.async_reload(
                entry.entry_id
            )

    def _get_ogp_notification_automation_ids(self) -> set[str]:
        """Return all OGP house-status automation IDs currently loaded."""
        ids: set[str] = set()

        for state in self.hass.states.async_all("automation"):
            automation_id = state.attributes.get("id")
            if (
                isinstance(automation_id, str)
                and automation_id.startswith(AUTOMATION_ID_PREFIX)
            ):
                ids.add(automation_id)

        central = self.config_entry.data.get("central", {})
        notifications = central.get("notifications", {})

        for automation_id in [
            notifications.get("automation_id"),
            *notifications.get("generated_resources", {}).get(
                "automations", []
            ),
            *central.get("generated_resources", {}).get(
                "automations", []
            ),
        ]:
            if isinstance(automation_id, str):
                ids.add(automation_id)

        return ids

    async def async_step_device_options(
        self,
        user_input=None,
    ):
        """Select what should be configured for this device."""

        if _ogp_settings_locked_off_grid(self.hass, self.config_entry):
            return self.async_abort(reason="settings_locked_off_grid")

        if user_input is not None:
            action = user_input["action"]

            if action == "device_settings":
                return await self.async_step_device_settings()

            if action == "regenerate_lovelace_yaml":
                return await self.async_step_regenerate_lovelace_yaml()

        schema = vol.Schema(
            {
                vol.Required(
                    "action",
                    default="device_settings",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            "device_settings",
                            "regenerate_lovelace_yaml",
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="device_options_action",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="device_options",
            data_schema=schema,
        )

    async def async_step_regenerate_lovelace_yaml(
        self,
        user_input=None,
    ):
        """Regenerate Lovelace YAML for this device."""

        device = self.config_entry.data.get("device", {})

        if user_input is not None:
            if _ogp_settings_locked_off_grid(self.hass, self.config_entry):
                return self.async_abort(reason="settings_locked_off_grid")

            language = user_input["lovelace_language"]

            instructions = generate_setup_instructions(
                device_name=device.get("name", ""),
                device_entity_id=device.get("entity_id", ""),
                language=language,
            )

            device_id = device.get(
                "id",
                self.config_entry.entry_id,
            )

            persistent_notification.async_create(
                self.hass,
                message=instructions,
                notification_id=f"off_grid_lovelace_{device_id}",
            )

            return self.async_create_entry(
                title="",
                data={},
            )

        current_language = device.get(
            "lovelace_language",
            "en",
        )

        schema = vol.Schema(
            {
                vol.Required(
                    "lovelace_language",
                    default=current_language,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["en", "hr"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="lovelace_language",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="regenerate_lovelace_yaml",
            data_schema=schema,
        )

    def _get_notification_profiles(self, notifications: dict | None = None) -> list[dict]:
        """Return notification profiles, migrating the old single profile format."""
        notifications = notifications or self.config_entry.data.get("central", {}).get("notifications", {})
        profiles = notifications.get("profiles")
        if isinstance(profiles, list):
            return [dict(profile) for profile in profiles if isinstance(profile, dict)]

        # V1.1.5 / early V1.2 format: one notification configuration.
        if not notifications or not notifications.get("enabled", False):
            return []

        mode = notifications.get("notification_mode", "global")
        if mode == "custom":
            custom = notifications.get("custom_targets", {})
            migrated: list[dict] = []
            for target_type, targets in (("notify", custom.get("notify", {})), ("popup", custom.get("popup", {}))):
                for target, events in targets.items():
                    migrated.append({
                        "id": uuid4().hex,
                        "mode": "custom",
                        "target_type": target_type,
                        "target": target,
                        "events": list(events),
                        "language": notifications.get("language", "en"),
                        "automation_id": f"{AUTOMATION_ID_PREFIX}_{uuid4().hex[:12]}",
                    })
            return migrated

        return [{
            "id": uuid4().hex,
            "mode": "global",
            "notification_types": list(notifications.get("notification_types", [])),
            "notification_events": list(notifications.get("notification_events", [])),
            "notify_targets": list(notifications.get("notify_targets", [])),
            "browser_mod_targets": list(notifications.get("browser_mod_targets", [])),
            "language": notifications.get("language", "en"),
            "automation_id": notifications.get("automation_id") or f"{AUTOMATION_ID_PREFIX}_{uuid4().hex[:12]}",
        }]

    def _notification_label(self, profile: dict) -> str:
        """Return a readable label for a notification profile."""
        if profile.get("mode") == "global":
            label = "Globalna obavijest" if profile.get("language") == "hr" else "Global notification"
            prefix = "🌐 "
        else:
            target_type = profile.get("target_type")
            target = profile.get("target", "")
            if target_type == "notify":
                label = next(
                    (item["label"] for item in get_notify_options(self.hass) if item["value"] == target),
                    target,
                )
                prefix = "📱 "
            else:
                label = next(
                    (item["label"] for item in get_browser_mod_device_options(self.hass) if item["value"] == target),
                    target,
                )
                prefix = "🖥️ "

        events = self._notification_event_labels(profile)
        return f"{prefix}{label}" + (f" — {events}" if events else "")

    def _notification_event_labels(self, profile: dict) -> str:
        """Return the selected event names for the list."""
        language = profile.get("language", "en")
        labels = {
            "grid": "Status mreže" if language == "hr" else "Grid status",
            "protection": "Zaštita / Override" if language == "hr" else "Protection / Override",
            "security": "Sigurnost" if language == "hr" else "Security",
        }
        return " · ".join(labels[event] for event in profile.get("notification_events", profile.get("events", [])) if event in labels)

    async def async_step_init(self, user_input=None):
        """Select what should be configured."""
        if _ogp_settings_locked_off_grid(self.hass, self.config_entry):
            return self.async_abort(reason="settings_locked_off_grid")

        if self.config_entry.data.get("type") == "device":
            return await self.async_step_device_options()

        if user_input is not None:
            if user_input["section"] == "central":
                return await self.async_step_central()
            if user_input["section"] == "notifications":
                return await self.async_step_notification_list()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("section", default="central"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["central", "notifications"],
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="configuration_section",
                    )
                )
            }),
        )

    async def async_step_notification_list(self, user_input=None):
        """Show the notification list and allow adding or managing one."""
        central = self.config_entry.data.get("central", {})
        if user_input is None:
            profiles = self._get_notification_profiles(central.get("notifications", {}))
            self._notification_profiles = profiles
        else:
            profiles = list(getattr(self, "_notification_profiles", []))
            selection = user_input.get("notification_selection")
            if selection == "__add__":
                return await self.async_step_notification_add()

            profile = next((item for item in profiles if item.get("id") == selection), None)
            if profile is not None:
                self._editing_notification = profile
                return await self.async_step_notification_action(profile=profile)

        options = [
            {
                "value": profile["id"],
                "label": self._notification_label(profile),
            }
            for profile in profiles
        ]
        options.append({"value": "__add__", "label": "➕ Dodaj obavijest" if self.hass.config.language.startswith("hr") else "➕ Add notification"})

        return self.async_show_form(
            step_id="notification_list",
            data_schema=vol.Schema({
                vol.Required(
                    "notification_selection",
                    default=options[0]["value"] if options else "__add__",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }),
        )

    async def async_step_notification_action(self, user_input=None, profile=None):
        """Choose whether to edit or delete an existing notification."""
        profile = profile or getattr(self, "_editing_notification", {})
        if not profile:
            return await self.async_step_notification_list()

        if user_input is not None:
            action = user_input.get("notification_action")
            if action == "edit":
                return await self.async_step_notification_edit(profile=profile)
            if action == "delete":
                return await self.async_step_notification_delete(profile=profile)

        return self.async_show_form(
            step_id="notification_action",
            data_schema=vol.Schema({
                vol.Required("notification_action", default="edit"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["edit", "delete"],
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="notification_action",
                    )
                )
            }),
        )

    async def async_step_notification_delete(self, user_input=None, profile=None):
        """Confirm deletion of an existing notification profile."""
        profile = profile or getattr(self, "_editing_notification", {})
        if not profile:
            return await self.async_step_notification_list()

        if user_input is not None:
            if user_input.get("confirm_delete"):
                profiles = [
                    item
                    for item in getattr(self, "_notification_profiles", [])
                    if item.get("id") != profile.get("id")
                ]
                return await self._async_save_notification_profiles(profiles)

            return await self.async_step_notification_list()

        return self.async_show_form(
            step_id="notification_delete",
            data_schema=vol.Schema({
                vol.Required("confirm_delete", default=False): bool,
            }),
        )

    async def async_step_notification_add(self, user_input=None):
        """Select the type of a new notification."""
        profiles = list(getattr(self, "_notification_profiles", []))
        if not profiles:
            profiles = self._get_notification_profiles()
        global_exists = any(profile.get("mode") == "global" for profile in profiles)
        options = [] if global_exists else [{"value": "global", "label": "Globalna obavijest" if self.hass.config.language.startswith("hr") else "Global notification"}]
        options.append({"value": "custom", "label": "Obavijest prema uređaju" if self.hass.config.language.startswith("hr") else "Per-device notification"})

        if user_input is not None:
            if user_input["notification_mode"] == "global":
                return await self.async_step_notification_global()
            return await self.async_step_notification_device()

        return self.async_show_form(
            step_id="notification_add",
            data_schema=vol.Schema({
                vol.Required("notification_mode", default=options[0]["value"]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="notification_mode",
                    )
                )
            }),
        )

    async def async_step_notification_global(self, user_input=None, profile=None):
        """Create or edit the single global notification profile."""
        profile = profile or getattr(self, "_editing_notification", {})
        if user_input is not None:
            notification_types = []
            if user_input.get("send_notification"):
                notification_types.append("notify")
            if user_input.get("send_popup"):
                notification_types.append("popup")
            events = [event for event, key in (("grid", "notify_grid_status"), ("protection", "notify_protection_status"), ("security", "notify_security")) if user_input.get(key, True)]
            if not notification_types:
                return self.async_show_form(step_id="notification_global", data_schema=self._notification_global_schema(profile, user_input), errors={"base": "notification_type_required"})
            if "notify" in notification_types and not user_input.get("notify_targets"):
                return self.async_show_form(step_id="notification_global", data_schema=self._notification_global_schema(profile, user_input), errors={"base": "notify_target_required"})
            if "popup" in notification_types and not user_input.get("browser_mod_targets"):
                return self.async_show_form(step_id="notification_global", data_schema=self._notification_global_schema(profile, user_input), errors={"base": "browser_mod_target_required"})
            new_profile = dict(profile)
            new_profile.update({
                "id": profile.get("id") or uuid4().hex,
                "mode": "global",
                "notification_types": notification_types,
                "notification_events": events,
                "notify_targets": list(user_input.get("notify_targets", [])),
                "browser_mod_targets": list(user_input.get("browser_mod_targets", [])),
                "language": user_input.get("notification_language", profile.get("language", "en")),
                "automation_id": profile.get("automation_id") or f"{AUTOMATION_ID_PREFIX}_{uuid4().hex[:12]}",
            })
            return await self._async_save_notification_profiles(self._replace_notification_profile(new_profile))

        return self.async_show_form(step_id="notification_global", data_schema=self._notification_global_schema(profile))

    def _notification_global_schema(self, profile=None, submitted=None):
        profile = profile or {}
        submitted = submitted or {}
        def val(key, default): return submitted.get(key, profile.get(key, default))
        return vol.Schema({
            vol.Required("send_notification", default="notify" in val("notification_types", ["notify"])): bool,
            vol.Required("send_popup", default="popup" in val("notification_types", [])): bool,
            vol.Optional("notify_targets", default=val("notify_targets", [])): selector.SelectSelector(selector.SelectSelectorConfig(options=get_notify_options(self.hass), multiple=True, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Optional("browser_mod_targets", default=val("browser_mod_targets", [])): selector.DeviceSelector(selector.DeviceSelectorConfig(integration="browser_mod", multiple=True)),
            vol.Required("notify_grid_status", default="grid" in val("notification_events", ["grid", "protection", "security"])): bool,
            vol.Required("notify_protection_status", default="protection" in val("notification_events", ["grid", "protection", "security"])): bool,
            vol.Required("notify_security", default="security" in val("notification_events", ["grid", "protection", "security"])): bool,
            vol.Required("notification_language", default=val("language", "en")): selector.SelectSelector(selector.SelectSelectorConfig(options=["en", "hr"], mode=selector.SelectSelectorMode.DROPDOWN)),
        })

    async def async_step_notification_device(self, user_input=None, profile=None):
        """Select the target type for a per-device notification."""
        profile = profile or getattr(self, "_editing_notification", {})
        if user_input is not None:
            self._notification_target_type = user_input["target_type"]
            return await self.async_step_notification_device_target(profile=profile)

        return self.async_show_form(
            step_id="notification_device",
            data_schema=vol.Schema({
                vol.Required(
                    "target_type",
                    default=profile.get("target_type", "notify"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "notify", "label": "Notify"},
                            {"value": "popup", "label": "Browser Mod"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="notification_target_type",
                    )
                )
            }),
        )

    async def async_step_notification_device_target(self, user_input=None, profile=None):
        """Select one recipient/device and its notification events."""
        profile = profile or getattr(self, "_editing_notification", {})
        target_type = getattr(
            self,
            "_notification_target_type",
            profile.get("target_type", "notify"),
        )

        if target_type == "notify":
            target_options = get_notify_options(self.hass)
        else:
            target_options = get_browser_mod_device_options(self.hass)

        if user_input is not None:
            target = user_input.get("target")
            events = list(user_input.get("events", []))
            if not target:
                return self.async_show_form(
                    step_id="notification_device_target",
                    data_schema=self._notification_device_target_schema(profile, target_type, user_input),
                    errors={"base": "custom_target_required"},
                )
            if not events:
                return self.async_show_form(
                    step_id="notification_device_target",
                    data_schema=self._notification_device_target_schema(profile, target_type, user_input),
                    errors={"base": "custom_event_required"},
                )

            new_profile = dict(profile)
            new_profile.update({
                "id": profile.get("id") or uuid4().hex,
                "mode": "custom",
                "target_type": target_type,
                "target": target,
                "events": events,
                "notification_events": events,
                "language": user_input.get(
                    "notification_language",
                    profile.get("language", "en"),
                ),
                "automation_id": profile.get("automation_id") or f"{AUTOMATION_ID_PREFIX}_{uuid4().hex[:12]}",
            })
            return await self._async_save_notification_profiles(
                self._replace_notification_profile(new_profile)
            )

        return self.async_show_form(
            step_id="notification_device_target",
            data_schema=self._notification_device_target_schema(
                profile,
                target_type,
            ),
        )

    def _notification_device_target_schema(
        self,
        profile=None,
        target_type="notify",
        submitted=None,
    ):
        profile = profile or {}
        submitted = submitted or {}
        target_options = (
            get_notify_options(self.hass)
            if target_type == "notify"
            else get_browser_mod_device_options(self.hass)
        )
        default_target = submitted.get(
            "target",
            profile.get("target"),
        )
        if default_target not in [item["value"] for item in target_options]:
            default_target = target_options[0]["value"] if target_options else ""

        return vol.Schema({
            vol.Required(
                "target",
                default=default_target,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=target_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                "events",
                default=submitted.get(
                    "events",
                    profile.get(
                        "events",
                        ["grid", "protection", "security"],
                    ),
                ),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        "grid",
                        "protection",
                        "security",
                    ],
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="notification_events",
                )
            ),
            vol.Required(
                "notification_language",
                default=submitted.get(
                    "notification_language",
                    profile.get("language", "en"),
                ),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["en", "hr"],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        })

    async def async_step_notification_edit(self, user_input=None, profile=None):
        """Open the editor for an existing notification."""
        profile = profile or getattr(self, "_editing_notification", {})
        if profile.get("mode") == "custom":
            self._notification_target_type = profile.get("target_type", "notify")
        if profile.get("mode") == "global":
            return await self.async_step_notification_global(user_input=user_input, profile=profile)
        return await self.async_step_notification_device(user_input=user_input, profile=profile)

    def _replace_notification_profile(self, profile: dict) -> list[dict]:
        profiles = list(getattr(self, "_notification_profiles", []))
        if not profiles:
            profiles = self._get_notification_profiles()
        profile_id = profile["id"]
        replaced = False
        result = []
        for item in profiles:
            if item.get("id") == profile_id:
                result.append(profile)
                replaced = True
            else:
                result.append(item)
        if not replaced:
            result.append(profile)
        return result

    async def _async_save_notification_profiles(self, profiles: list[dict]):
        """Replace generated notification automations and save all profiles."""
        if _ogp_settings_locked_off_grid(self.hass, self.config_entry):
            return self.async_abort(reason="settings_locked_off_grid")

        central_config = dict(self.config_entry.data.get("central", {}))
        old_notifications = central_config.get("notifications", {})
        old_ids = self._get_ogp_notification_automation_ids()
        for profile in profiles:
            if isinstance(profile.get("automation_id"), str):
                old_ids.add(profile["automation_id"])

        active_ids = set()
        for profile in profiles:
            automation_id = profile.get("automation_id") or f"{AUTOMATION_ID_PREFIX}_{uuid4().hex[:12]}"
            profile["automation_id"] = automation_id
            active_ids.add(automation_id)

            if profile.get("mode") == "global":
                await async_generate_house_status_automation(
                    self.hass,
                    automation_id=automation_id,
                    inverter_entity=central_config["inverter_off_grid_status"],
                    notification_types=profile.get("notification_types", []),
                    notification_events=profile.get("notification_events", []),
                    notify_targets=profile.get("notify_targets", []),
                    browser_mod_targets=profile.get("browser_mod_targets", []),
                    language=profile.get("language", "en"),
                )
            else:
                target_type = profile.get("target_type")
                target = profile.get("target")
                events = profile.get("events", [])
                custom_targets = {"notify": {}, "popup": {}}
                custom_targets[target_type][target] = events
                await async_generate_house_status_automation(
                    self.hass,
                    automation_id=automation_id,
                    inverter_entity=central_config["inverter_off_grid_status"],
                    notification_types=[target_type],
                    notification_events=events,
                    notify_targets=[target] if target_type == "notify" else [],
                    browser_mod_targets=[target] if target_type == "popup" else [],
                    language=profile.get("language", "en"),
                    notification_mode="custom",
                    custom_targets=custom_targets,
                )

        for automation_id in old_ids - active_ids:
            await async_remove_house_status_automation(self.hass, automation_id)

        notifications = {
            "enabled": bool(profiles),
            "profiles": profiles,
            "generated_resources": {"automations": sorted(active_ids)},
        }
        # Keep the first profile mirrored in legacy fields for compatibility.
        if profiles:
            first = profiles[0]
            notifications.update({
                "notification_mode": first.get("mode", "global"),
                "notification_types": first.get("notification_types", [first.get("target_type")] if first.get("target_type") else []),
                "notification_events": first.get("notification_events", first.get("events", [])),
                "notify_targets": first.get("notify_targets", [first.get("target")] if first.get("target_type") == "notify" else []),
                "browser_mod_targets": first.get("browser_mod_targets", [first.get("target")] if first.get("target_type") == "popup" else []),
                "language": first.get("language", "en"),
                "automation_id": first.get("automation_id"),
            })

        central_config["notifications"] = notifications
        central_config["generated_resources"] = dict(central_config.get("generated_resources", {}))
        central_config["generated_resources"]["automations"] = sorted(active_ids)
        new_data = dict(self.config_entry.data)
        new_data["central"] = central_config
        self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
        await self._async_reload_ogp_device_entries()
        language = profiles[0].get("language", "en") if profiles else old_notifications.get("language", "en")
        await _async_show_restart_required_notification(self.hass, language)
        return self.async_create_entry(title="", data={})

    async def async_step_central(self, user_input=None):
        """Edit central configuration."""
        current = self.config_entry.data.get("central", {})
        if user_input is not None:
            if _ogp_settings_locked_off_grid(self.hass, self.config_entry):
                return self.async_abort(reason="settings_locked_off_grid")

            central_config = dict(user_input)
            central_changed = any(central_config.get(key) != current.get(key) for key in (
                "inverter_off_grid_status", "power_meter_status", "recovery_delay", "central_pin", "pin_check", "recovery_enabled", "logs"))
            existing = current.get("notifications", {})
            if existing:
                central_config["notifications"] = dict(existing)
            if central_config.get("notifications_enabled", False):
                self._central_config = central_config
                self._central_changed = central_changed
                return await self.async_step_notification_list()
            new_data = dict(self.config_entry.data)
            new_data["central"] = central_config
            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
            if central_changed:
                await _async_show_restart_required_notification(self.hass, existing.get("language", "en"))
            return self.async_create_entry(title="", data={})
        return self.async_show_form(step_id="central", data_schema=vol.Schema({
            vol.Required("inverter_off_grid_status", default=current.get("inverter_off_grid_status")): selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "input_select"])),
            vol.Required("power_meter_status", default=current.get("power_meter_status")): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Required("recovery_delay", default=current.get("recovery_delay", 60)): selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=600, step=1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="s")),
            vol.Required("central_pin", default=current.get("central_pin", "1234")): str,
            vol.Required("pin_check", default=current.get("pin_check", True)): bool,
            vol.Required("recovery_enabled", default=current.get("recovery_enabled", True)): bool,
            vol.Required("logs", default=normalize_log_level(current.get("logs", "warnings"))): selector.SelectSelector(selector.SelectSelectorConfig(options=["off", "warnings", "debug"], mode=selector.SelectSelectorMode.LIST, translation_key="log_level")),
        }))

    async def async_step_device_settings(
        self,
        user_input=None,
    ):
        """Edit the selected device."""

        device = dict(
            self.config_entry.data.get(
                "device",
                {},
            )
        )
        device_type = device["type"]

        if user_input is not None:
            if _ogp_settings_locked_off_grid(self.hass, self.config_entry):
                return self.async_abort(reason="settings_locked_off_grid")

            show_all = bool(
                user_input.get(
                    "show_all_automations",
                    False,
                )
            )

            if (
                show_all
                and not getattr(
                    self,
                    "_automation_options_expanded",
                    False,
                )
            ):
                self._show_all_automations = True
                self._automation_options_expanded = True
                self._pending_device_settings = user_input
                return await self.async_step_device_settings()

            updated_device = dict(device)

            updated_device["name"] = user_input["name"]
            updated_device["entity_id"] = user_input[
                "entity_id"
            ]

            updated_type_config = dict(
                device.get(
                    "type_config",
                    {},
                )
            )

            updated_type_config["entity_id"] = (
                user_input["entity_id"]
            )
            if device_type == "custom":
                updated_type_config["control_entity_id"] = (
                    user_input["control_entity_id"]
                )
            updated_type_config["off_state"] = (
                user_input["off_state"]
            )
            if device_type == "custom":
                updated_type_config["recovery_action"] = (
                    user_input.get("recovery_action", "stay_off")
                )
            updated_type_config[
                "wait_for_unavailable"
            ] = user_input["wait_for_unavailable"]
            updated_type_config[
                "recovery_timeout"
            ] = user_input["recovery_timeout"]
            updated_type_config[
                "command_timeout"
            ] = user_input["command_timeout"]

            updated_device["type_config"] = (
                updated_type_config
            )
            updated_device["automations"] = (
                [] if device_type == "custom"
                else user_input.get("automations", [])
            )

            updated_device["override"] = {
                "override_enabled": user_input[
                    "override_enabled"
                ],
                "require_pin": user_input[
                    "require_pin"
                ],
                "minimum_runtime": user_input[
                    "minimum_runtime"
                ],
                "maximum_runtime": user_input[
                    "maximum_runtime"
                ],
            }

            updated_device[
                "generated_resources"
            ] = dict(
                device.get(
                    "generated_resources",
                    {
                        "entities": [],
                        "automations": [],
                        "helpers": [],
                    },
                )
            )

            new_data = dict(
                self.config_entry.data
            )
            new_data["device"] = updated_device

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                title=updated_device["name"],
                data=new_data,
            )

            return self.async_create_entry(
                title="",
                data={},
            )

        type_config = device.get(
            "type_config",
            {}
        )
        override = device.get(
            "override",
            {}
        )

        selected_automations = device.get(
            "automations",
            [],
        )

        show_all = bool(
            getattr(
                self,
                "_show_all_automations",
                False,
            )
        )

        automation_options = _get_automation_options(
            self.hass,
            device.get(
                "entity_id",
                "",
            ),
            show_all=show_all,
            selected=selected_automations,
        )

        schema_fields = {
                vol.Required(
                    "name",
                    default=device.get(
                        "name",
                        "",
                    ),
                ): str,

                vol.Required(
                    "entity_id",
                    default=device.get(
                        "entity_id"
                    ),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=(
                            "climate"
                            if device_type == "custom"
                            else device_type
                            if device_type in [
                                "climate",
                                "switch",
                            ]
                            else None
                        ),
                    )
                ),

                vol.Required(
                    "off_state",
                    default=type_config.get(
                        "off_state",
                        "off",
                    ),
                ): str,

                vol.Required(
                    "wait_for_unavailable",
                    default=type_config.get(
                        "wait_for_unavailable",
                        True,
                    ),
                ): bool,

                vol.Required(
                    "recovery_timeout",
                    default=type_config.get(
                        "recovery_timeout",
                        180,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=900,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),

                vol.Required(
                    "command_timeout",
                    default=type_config.get(
                        "command_timeout",
                        15,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=120,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),

                vol.Required(
                    "override_enabled",
                    default=override.get(
                        "override_enabled",
                        True,
                    ),
                ): bool,

                vol.Required(
                    "require_pin",
                    default=override.get(
                        "require_pin",
                        True,
                    ),
                ): bool,

                vol.Required(
                    "minimum_runtime",
                    default=override.get(
                        "minimum_runtime",
                        1,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=60,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),

                vol.Required(
                    "maximum_runtime",
                    default=override.get(
                        "maximum_runtime",
                        60,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=60,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
            }

        if device_type == "custom":
            schema_fields[
                vol.Required(
                    "recovery_action",
                    default=type_config.get(
                        "recovery_action",
                        "stay_off",
                    ),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["stay_off", "turn_on"],
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key="recovery_action",
                )
            )

        if device_type == "custom":
            schema_fields[
                vol.Required(
                    "control_entity_id",
                    default=type_config.get(
                        "control_entity_id",
                        "",
                    ),
                )
            ] = selector.EntitySelector()

        else:
            schema_fields[
                vol.Optional(
                    "automations",
                    default=selected_automations,
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=automation_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        schema = vol.Schema(schema_fields)

        return self.async_show_form(
            step_id="device_settings",
            data_schema=schema,
        )
