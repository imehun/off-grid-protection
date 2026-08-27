"""Config flow for Off-grid Protection."""

from __future__ import annotations

from uuid import uuid4

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
from .notifications import (
    AUTOMATION_ID_PREFIX,
    async_generate_house_status_automation,
    async_remove_house_status_automation,
    get_notify_options,
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

        default_name = ("" if self._central_entry else "OGP – Off-grid Protection")

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
                "devices": [],
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
            notify_targets=notification_config[
                "notify_targets"
            ],
            browser_mod_targets=notification_config[
                "browser_mod_targets"
            ],
            language=notification_config[
                "language"
            ],
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
                    default=True,
                ): bool,
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

    async def async_step_central_notifications(
        self,
        user_input=None,
    ):
        """Configure central house-status notifications."""

        if user_input is not None:
            notification_types = []
            if user_input.get(
                "send_notification",
                False,
            ):
                notification_types.append("notify")
            if user_input.get(
                "send_popup",
                False,
            ):
                notification_types.append("popup")
            notify_targets = list(
                user_input.get(
                    "notify_targets",
                    [],
                )
            )
            browser_mod_targets = list(
                user_input.get(
                    "browser_mod_targets",
                    [],
                )
            )

            if not notification_types:
                return self.async_show_form(
                    step_id="central_notifications",
                    data_schema=self._central_notifications_schema(
                        user_input
                    ),
                    errors={
                        "base": "notification_type_required",
                    },
                )

            if (
                "notify" in notification_types
                and not notify_targets
            ):
                return self.async_show_form(
                    step_id="central_notifications",
                    data_schema=self._central_notifications_schema(
                        user_input
                    ),
                    errors={
                        "base": "notify_target_required",
                    },
                )

            if (
                "popup" in notification_types
                and not browser_mod_targets
            ):
                return self.async_show_form(
                    step_id="central_notifications",
                    data_schema=self._central_notifications_schema(
                        user_input
                    ),
                    errors={
                        "base": "browser_mod_target_required",
                    },
                )

            notification_config = {
                "enabled": True,
                "notification_types": notification_types,
                "notify_targets": notify_targets,
                "browser_mod_targets": browser_mod_targets,
                "language": user_input.get(
                    "notification_language",
                    "en",
                ),
            }

            return await self._async_finalize_central_notifications(
                self._central_config,
                notification_config,
            )

        return self.async_show_form(
            step_id="central_notifications",
            data_schema=self._central_notifications_schema(),
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
                    "send_notification",
                    default=current.get(
                        "send_notification",
                        "notify"
                        in current.get(
                            "notification_types",
                            ["notify"],
                        ),
                    ),
                ): bool,
                vol.Required(
                    "send_popup",
                    default=current.get(
                        "send_popup",
                        "popup"
                        in current.get(
                            "notification_types",
                            [],
                        ),
                    ),
                ): bool,
                vol.Optional(
                    "notify_targets",
                    default=current.get(
                        "notify_targets",
                        [],
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=get_notify_options(
                            self.hass
                        ),
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "browser_mod_targets",
                    default=current.get(
                        "browser_mod_targets",
                        [],
                    ),
                ): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(
                        integration="browser_mod",
                        multiple=True,
                    )
                ),
                vol.Required(
                    "notification_language",
                    default=current.get(
                        "language",
                        "en",
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "en",
                                "label": "English",
                            },
                            {
                                "value": "hr",
                                "label": "Hrvatski",
                            },
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

        schema = vol.Schema(
            {
                vol.Required(
                    "entity_id",
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="climate",
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

        schema = vol.Schema(
            {
                vol.Required(
                    "entity_id",
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="switch",
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
        """Configure a custom device."""

        if user_input is not None:
            self._device_config = user_input
            return await self.async_step_automations()

        schema = vol.Schema(
            {
                vol.Required(
                    "entity_id",
                ): selector.EntitySelector(),
                vol.Required(
                    "shutdown_action",
                ): selector.ActionSelector(),
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
            show_all = bool(
                user_input.get(
                    "show_all_automations",
                    False,
                )
            )

            # The checkbox is intentionally a two-stage control. The first
            # submit changes the available list to all automations; the next
            # submit confirms the actual selection.
            if (
                show_all
                and not getattr(
                    self,
                    "_automation_options_expanded",
                    False,
                )
            ):
                self._automation_options_expanded = True
                self._show_all_automations = True
                return await self.async_step_automations()

            self._device_automations = user_input.get(
                "automations",
                [],
            )
            return await self.async_step_override()

        show_all = bool(
            getattr(
                self,
                "_show_all_automations",
                False,
            )
        )

        options = _get_automation_options(
            self.hass,
            entity_id,
            show_all=show_all,
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
                vol.Optional(
                    "show_all_automations",
                    default=show_all,
                ): bool,
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
            if not user_input.get("confirm_generate", False):
                return self.async_abort(
                    reason="generation_cancelled",
                )

            device = {
                "id": uuid4().hex,
                "name": self._device_name,
                "type": self._configuration_type,
                "entity_id": self._device_config[
                    "entity_id"
                ],
                "type_config": self._device_config,
                "automations": self._device_automations,
                "override": self._device_override,
                "generated_resources": {
                    "entities": [],
                    "automations": [],
                    "helpers": [],
                },
            }

            current_data = dict(
                self._central_entry.data
            )

            devices = list(
                current_data.get(
                    "devices",
                    [],
                )
            )

            devices.append(device)

            current_data["devices"] = devices

            self.hass.config_entries.async_update_entry(
                self._central_entry,
                data=current_data,
            )

            # Record ownership of all OGP resources generated for this
            # device. No device name or entity ID is hardcoded.
            slug = slugify(self._device_name)

            device["generated_resources"]["entities"] = [
                f"binary_sensor.{slug}_off_grid_protection_locked",
                f"number.{slug}_override_duration",
                f"sensor.{slug}_override_remaining",
                f"text.{slug}_override_pin",
            ]

            updated_data = dict(
                self._central_entry.data
            )

            updated_devices = list(
                updated_data.get(
                    "devices",
                    [],
                )
            )

            for index, existing_device in enumerate(
                updated_devices
            ):
                if existing_device["id"] == device["id"]:
                    updated_devices[index] = device
                    break

            updated_data["devices"] = updated_devices

            self.hass.config_entries.async_update_entry(
                self._central_entry,
                data=updated_data,
            )

            # Reload only after ownership is stored so the entity platforms
            # see the newly added device immediately.
            await self.hass.config_entries.async_reload(
                self._central_entry.entry_id
            )

            # Generate Lovelace instructions for every configured device.
            instructions = generate_setup_instructions(
                device_name=self._device_name,
                device_entity_id=self._device_config["entity_id"],
                language=self._lovelace_language,
            )

            persistent_notification.async_create(
                self.hass,
                message=instructions,
                title=(
                    "OGP – Off-grid Protection — "
                    f"Lovelace: {self._device_name}"
                ),
                notification_id=(
                    f"off_grid_lovelace_{device['id']}"
                ),
            )

            return self.async_abort(
                reason="device_added",
            )

        schema = vol.Schema(
            {
                vol.Required(
                    "confirm_generate",
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

    async def async_step_init(
        self,
        user_input=None,
    ):
        """Select what should be configured."""

        if user_input is not None:
            if user_input["section"] == "central":
                return await self.async_step_central()

            if user_input["section"] == "device":
                return await self.async_step_device()

            if user_input["section"] == "notifications":
                current = self.config_entry.data.get(
                    "central",
                    {},
                )
                self._central_config = dict(current)
                current_notifications = current.get(
                    "notifications",
                    {},
                )
                return await self.async_step_central_notifications(
                    current=current_notifications
                )

        schema = vol.Schema(
            {
                vol.Required(
                    "section",
                    default="central",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["central", "device", "notifications"],
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="configuration_section",
                    )
                )
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )

    async def async_step_central(
        self,
        user_input=None,
    ):
        """Edit central configuration."""

        current = self.config_entry.data.get(
            "central",
            {},
        )

        if user_input is not None:
            central_config = dict(user_input)

            if central_config.get(
                "notifications_enabled",
                False,
            ):
                self._central_config = central_config
                current_notifications = current.get(
                    "notifications",
                    {},
                )
                return await self.async_step_central_notifications(
                    current=current_notifications
                )

            old_notifications = current.get(
                "notifications",
                {},
            )
            old_automation_id = (
                old_notifications.get(
                    "generated_resources",
                    {},
                ).get(
                    "automations",
                    [],
                )[0]
                if old_notifications.get(
                    "enabled",
                    False,
                )
                else None
            )

            if old_automation_id:
                await async_remove_house_status_automation(
                    self.hass,
                    old_automation_id,
                )

            central_config.pop(
                "notifications",
                None,
            )
            central_config["generated_resources"] = {
                "automations": [],
            }

            new_data = dict(
                self.config_entry.data
            )
            new_data["central"] = central_config

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )

            return self.async_create_entry(
                title="",
                data={},
            )

        schema = vol.Schema(
            {
                vol.Required(
                    "inverter_off_grid_status",
                    default=current.get(
                        "inverter_off_grid_status",
                    ),
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
                    default=current.get(
                        "power_meter_status",
                    ),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                    )
                ),
                vol.Required(
                    "recovery_delay",
                    default=current.get(
                        "recovery_delay",
                        60,
                    ),
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
                    default=current.get(
                        "central_pin",
                        "1234",
                    ),
                ): str,
                vol.Required(
                    "pin_check",
                    default=current.get(
                        "pin_check",
                        True,
                    ),
                ): bool,
                vol.Required(
                    "recovery_enabled",
                    default=current.get(
                        "recovery_enabled",
                        True,
                    ),
                ): bool,
                vol.Required(
                    "logs",
                    default=current.get(
                        "logs",
                        True,
                    ),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="central",
            data_schema=schema,
        )

    async def async_step_central_notifications(
        self,
        user_input=None,
        current=None,
    ):
        """Configure central house-status notifications."""
        current = current or {}

        if user_input is not None:
            notification_types = []
            if user_input.get("send_notification", False):
                notification_types.append("notify")
            if user_input.get("send_popup", False):
                notification_types.append("popup")

            notify_targets = list(user_input.get("notify_targets", []))
            browser_mod_targets = list(
                user_input.get("browser_mod_targets", [])
            )
            language = user_input.get(
                "notification_language",
                current.get("language", "en"),
            )

            # Settings replace the single OGP notification automation.
            # Also discover orphaned OGP automations created by earlier
            # test versions so they cannot continue sending notifications.
            old_ids = self._get_ogp_notification_automation_ids()
            stored_id = current.get("automation_id")
            if isinstance(stored_id, str):
                old_ids.add(stored_id)

            if not notification_types:
                for automation_id in old_ids:
                    await async_remove_house_status_automation(
                        self.hass,
                        automation_id,
                    )

                central_config = dict(
                    self.config_entry.data.get("central", {})
                )
                central_config.pop("notifications", None)
                central_config["generated_resources"] = {
                    "automations": [],
                }

                new_data = dict(self.config_entry.data)
                new_data["central"] = central_config
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=new_data,
                )

                return self.async_create_entry(
                    title="",
                    data={},
                )

            errors = {}
            if "notify" in notification_types and not notify_targets:
                errors["base"] = "notify_target_required"
            elif (
                "popup" in notification_types
                and not browser_mod_targets
            ):
                errors["base"] = "browser_mod_target_required"

            if errors:
                return self.async_show_form(
                    step_id="central_notifications",
                    data_schema=self._central_notifications_schema(
                        current, user_input
                    ),
                    errors=errors,
                )

            automation_id = (
                current.get("automation_id")
                or (next(iter(old_ids)) if old_ids else None)
                or f"{AUTOMATION_ID_PREFIX}_{uuid4().hex[:12]}"
            )

            for old_id in old_ids:
                if old_id != automation_id:
                    await async_remove_house_status_automation(
                        self.hass,
                        old_id,
                    )

            central_config = dict(
                self.config_entry.data.get("central", {})
            )
            central_config["notifications"] = {
                "enabled": True,
                "notification_types": notification_types,
                "notify_targets": notify_targets,
                "browser_mod_targets": browser_mod_targets,
                "language": language,
                "automation_id": automation_id,
            }
            central_config["generated_resources"] = {
                "automations": [automation_id],
            }

            await async_generate_house_status_automation(
                self.hass,
                automation_id=automation_id,
                inverter_entity=central_config[
                    "inverter_off_grid_status"
                ],
                notification_types=notification_types,
                notify_targets=notify_targets,
                browser_mod_targets=browser_mod_targets,
                language=language,
            )

            new_data = dict(self.config_entry.data)
            new_data["central"] = central_config
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )

            return self.async_create_entry(
                title="",
                data={},
            )

        return self.async_show_form(
            step_id="central_notifications",
            data_schema=self._central_notifications_schema(current)
        )

    def _central_notifications_schema(
        self,
        current=None,
        submitted=None,
    ):
        """Build the central notification selector schema."""
        current = current or {}
        submitted = submitted or {}

        def value(
            key,
            fallback,
        ):
            return submitted.get(
                key,
                current.get(
                    key,
                    fallback,
                ),
            )

        return vol.Schema(
            {
                vol.Required(
                    "send_notification",
                    default=(
                        submitted.get(
                            "send_notification",
                            "notify"
                            in value(
                                "notification_types",
                                ["notify"],
                            ),
                        )
                    ),
                ): bool,
                vol.Required(
                    "send_popup",
                    default=(
                        submitted.get(
                            "send_popup",
                            "popup"
                            in value(
                                "notification_types",
                                [],
                            ),
                        )
                    ),
                ): bool,
                vol.Optional(
                    "notify_targets",
                    default=value(
                        "notify_targets",
                        [],
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=get_notify_options(
                            self.hass
                        ),
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "browser_mod_targets",
                    default=value(
                        "browser_mod_targets",
                        [],
                    ),
                ): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(
                        integration="browser_mod",
                        multiple=True,
                    )
                ),
                vol.Required(
                    "notification_language",
                    default=value(
                        "notification_language",
                        current.get(
                            "language",
                            "en",
                        ),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "en",
                                "label": "English",
                            },
                            {
                                "value": "hr",
                                "label": "Hrvatski",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    async def async_step_device(
        self,
        user_input=None,
    ):
        """Select a device to edit or remove."""

        devices = self.config_entry.data.get(
            "devices",
            []
        )

        if not devices:
            return self.async_abort(
                reason="no_devices",
            )

        if user_input is not None:
            self._selected_device_id = user_input[
                "device_id"
            ]

            self._selected_device = next(
                device
                for device in devices
                if device["id"]
                == self._selected_device_id
            )

            if user_input["action"] == "delete":
                return await self.async_step_device_delete()

            return await self.async_step_device_settings()

        device_options = {
            device["id"]: device["name"]
            for device in devices
        }

        schema = vol.Schema(
            {
                vol.Required(
                    "device_id"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": device_id,
                                "label": device_name,
                            }
                            for device_id, device_name
                            in device_options.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    "action",
                    default="edit",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["edit", "delete"],
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="device_action",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="device",
            data_schema=schema,
        )

    def _prepare_legacy_generated_resources(
        self,
        device: dict,
    ) -> dict:
        """Populate ownership for resources created by older OGP versions.

        This is intentionally limited to resources we know were created by
        the first S32 implementation. It does not guess or delete arbitrary
        user entities.
        """

        generated = dict(
            device.get(
                "generated_resources",
                {},
            )
        )

        generated["entities"] = list(
            generated.get(
                "entities",
                [],
            )
        )
        generated["automations"] = list(
            generated.get(
                "automations",
                [],
            )
        )
        generated["helpers"] = list(
            generated.get(
                "helpers",
                [],
            )
        )

        # Legacy devices may predate generated_resources ownership.
        # Reconstruct ownership from the device name instead of a
        # device-specific entity ID.
        if not generated["entities"]:
            slug = slugify(device.get("name", ""))
            if slug:
                legacy_entities = [
                    f"binary_sensor.{slug}_off_grid_protection_locked",
                    f"number.{slug}_override_duration",
                    f"sensor.{slug}_override_remaining",
                    f"text.{slug}_override_pin",
                ]

                generated["entities"].extend(
                    entity_id
                    for entity_id in legacy_entities
                    if entity_id not in generated["entities"]
                )

        device["generated_resources"] = generated

        return generated

    async def async_step_device_delete(
        self,
        user_input=None,
    ):
        """Confirm removal and cleanup of a device."""

        device = self._selected_device

        generated = self._prepare_legacy_generated_resources(
            device
        )

        generated_entities = list(
            generated.get(
                "entities",
                [],
            )
        )

        generated_automations = list(
            generated.get(
                "automations",
                [],
            )
        )

        generated_helpers = list(
            generated.get(
                "helpers",
                [],
            )
        )

        if user_input is not None:
            if not user_input["confirm"]:
                return self.async_abort(
                    reason="delete_cancelled",
                )

            await self._cleanup_generated_resources(
                device
            )

            devices = list(
                self.config_entry.data.get(
                    "devices",
                    [],
                )
            )

            devices = [
                existing
                for existing in devices
                if existing["id"] != device["id"]
            ]

            new_data = dict(
                self.config_entry.data
            )

            new_data["devices"] = devices

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )

            return self.async_create_entry(
                title="",
                data={},
            )

        generated_resources = (
            generated_entities
            + generated_helpers
            + generated_automations
        )

        if generated_resources:
            resources = "\n".join(
                f"- {resource}"
                for resource in generated_resources
            )
        else:
            resources = "—"

        schema = vol.Schema(
            {
                vol.Required(
                    "confirm",
                    default=False,
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="device_delete",
            data_schema=schema,
            description_placeholders={
                "device_name": device["name"],
                "resources": resources,
            },
        )

    async def _cleanup_generated_resources(
        self,
        device: dict,
    ) -> None:
        """Remove only resources owned by OGP."""

        generated = device.get(
            "generated_resources",
            {},
        )

        # Remove entity-registry entries recorded by OGP.
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self.hass)

        for entity_id in generated.get(
            "entities",
            [],
        ):
            if registry.async_get(entity_id):
                registry.async_remove(entity_id)

        # Remove helpers recorded by OGP if they are registry entities.
        for entity_id in generated.get(
            "helpers",
            [],
        ):
            if registry.async_get(entity_id):
                registry.async_remove(entity_id)

        # Automations will only be removed when OGP explicitly recorded
        # them as generated. Existing automations in device["automations"]
        # are intentionally NOT touched.
        for automation_id in generated.get(
            "automations",
            [],
        ):
            if self.hass.services.has_service(
                "automation",
                "delete",
            ):
                await self.hass.services.async_call(
                    "automation",
                    "delete",
                    {
                        "entity_id": automation_id,
                    },
                    blocking=True,
                )


    async def async_step_device_settings(
        self,
        user_input=None,
    ):
        """Edit the selected device."""

        device = self._selected_device
        device_type = device["type"]

        if user_input is not None:
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
            updated_type_config["off_state"] = (
                user_input["off_state"]
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
            updated_device["automations"] = user_input.get(
                "automations",
                [],
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

            devices = list(
                self.config_entry.data.get(
                    "devices",
                    [],
                )
            )

            for index, existing_device in enumerate(
                devices
            ):
                if existing_device["id"] == device["id"]:
                    devices[index] = updated_device
                    break

            new_data = dict(
                self.config_entry.data
            )
            new_data["devices"] = devices

            self.hass.config_entries.async_update_entry(
                self.config_entry,
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

        schema = vol.Schema(
            {
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
                            device_type
                            if device_type
                            in [
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

                vol.Optional(
                    "automations",
                    default=selected_automations,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=automation_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),

                vol.Optional(
                    "show_all_automations",
                    default=show_all,
                ): bool,

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
        )

        return self.async_show_form(
            step_id="device_settings",
            data_schema=schema,
        )
