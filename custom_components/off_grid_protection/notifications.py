"""OGP central house-status notification automation."""

from __future__ import annotations

from functools import partial
from pathlib import Path
import json
import re
from typing import Any

import yaml

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

DOMAIN = "off_grid_protection"
AUTOMATION_ID_PREFIX = "ogp_house_status_notification"
AUTOMATIONS_FILE = "automations.yaml"


def get_notify_options(hass: HomeAssistant) -> list[dict[str, str]]:
    """Return available notify entities and legacy notify actions."""
    options: list[dict[str, str]] = []
    seen: set[str] = set()

    for state in hass.states.async_all("notify"):
        if state.entity_id in seen:
            continue
        seen.add(state.entity_id)
        options.append(
            {
                "value": f"entity:{state.entity_id}",
                "label": state.name,
            }
        )

    for service_name in hass.services.async_services().get(
        "notify",
        {},
    ):
        value = f"service:{service_name}"
        if value in seen:
            continue
        seen.add(value)
        options.append(
            {
                "value": value,
                "label": f"notify.{service_name}",
            }
        )

    options.sort(
        key=lambda item: item["label"].lower()
    )
    return options


def get_browser_mod_device_options(
    hass: HomeAssistant,
) -> list[dict[str, str]]:
    """Return Browser Mod devices from the device registry."""
    registry = dr.async_get(hass)
    options: list[dict[str, str]] = []

    for device in registry.devices.values():
        if not any(
            domain == "browser_mod"
            for domain, _identifier in device.identifiers
        ):
            continue

        label = device.name_by_user or device.name
        options.append(
            {
                "value": device.id,
                "label": label,
            }
        )

    options.sort(
        key=lambda item: item["label"].lower()
    )
    return options


def _automation_file(hass: HomeAssistant) -> Path:
    return Path(
        hass.config.path(
            AUTOMATIONS_FILE
        )
    )


def _remove_generated_block(
    content: str,
    automation_id: str,
) -> str:
    """Remove one OGP generated automation item from automations.yaml."""
    lines = content.splitlines(keepends=True)
    start = None

    for index, line in enumerate(lines):
        if re.match(
            rf"^\s*-\s+id:\s*{re.escape(automation_id)}\s*$",
            line.rstrip(),
        ):
            start = index
            break

    if start is None:
        return content

    end = len(lines)

    for index in range(start + 1, len(lines)):
        if re.match(r"^\s*-\s+id:\s*", lines[index]):
            end = index
            break

    remaining = lines[:start] + lines[end:]
    return "".join(remaining)


def _append_generated_block(
    content: str,
    block: str,
) -> str:
    cleaned = content.rstrip()

    if cleaned in ("", "[]"):
        return block.rstrip() + "\n"

    return (
        cleaned
        + "\n\n"
        + block.rstrip()
        + "\n"
    )


def _notify_action(
    target: str,
    title: str,
    message: str,
) -> dict[str, Any]:
    """Build one notification action."""
    if target.startswith("entity:"):
        entity_id = target.split(
            ":",
            1,
        )[1]
        return {
            "action": "notify.send_message",
            "target": {
                "entity_id": [
                    entity_id,
                ],
            },
            "data": {
                "title": title,
                "message": message,
            },
        }

    service = target.split(
        ":",
        1,
    )[1]

    return {
        "action": f"notify.{service}",
        "data": {
            "title": title,
            "message": message,
        },
    }


def _popup_action(
    device_ids: list[str],
    title: str,
    message: str,
) -> dict[str, Any]:
    """Build one Browser Mod popup action."""
    return {
        "action": "browser_mod.popup",
        "target": {
            "device_id": list(device_ids),
        },
        "data": {
            "title": title,
            "content": {
                "type": "markdown",
                "content": (
                    f"## {title}\n\n"
                    f"{message}"
                ),
            },
            "dismissable": True,
            "autoclose": 0,
        },
    }


async def _load_notification_texts(
    hass: HomeAssistant,
    language: str,
) -> dict[str, str]:
    """Load notification texts without blocking the event loop."""

    translation_path = (
        Path(__file__).parent
        / "translations"
        / f"{language}.json"
    )

    data = await hass.async_add_executor_job(
        lambda: translation_path.read_text(
            encoding="utf-8",
        )
    )
    translations = json.loads(data)

    return translations.get(
        "notification_messages",
        {},
    )


def _build_automation(
    *,
    automation_id: str,
    inverter_entity: str,
    notification_types: list[str],
    notification_events: list[str],
    notify_targets: list[str],
    browser_mod_targets: list[str],
    texts: dict[str, str],
) -> dict[str, Any]:
    """Build the central OGP notification automation."""

    def text(key: str) -> str:
        return texts.get(key, key)

    def notify_actions(title: str, message: str) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []

        effective_notification_types = set(
            notification_types
        )

        # Keep saved configurations compatible with the UI: if recipients
        # exist, notifications are enabled even if an older entry did not
        # persist the corresponding type flag.
        if notify_targets:
            effective_notification_types.add("notify")

        if browser_mod_targets:
            effective_notification_types.add("popup")

        if "notify" in effective_notification_types:
            for target in notify_targets:
                actions.append(
                    _notify_action(
                        target,
                        title,
                        message,
                    )
                )

        if "popup" in effective_notification_types:
            actions.append(
                _popup_action(
                    browser_mod_targets,
                    title,
                    message,
                )
            )

        return actions

    triggers: list[dict[str, Any]] = []

    if "grid" in notification_events:
        triggers.append({
            "trigger": "state",
            "entity_id": inverter_entity,
            "id": "grid_status",
        })

    if "protection" in notification_events:
        triggers.extend([
            {
                "trigger": "event",
                "event_type": "off_grid_protection_recovery",
                "id": "recovery_event",
            },
            {
                "trigger": "event",
                "event_type": "off_grid_protection_override",
                "event_data": {"action": "activated"},
                "id": "override_activated",
            },
            {
                "trigger": "event",
                "event_type": "off_grid_protection_override",
                "event_data": {"action": "expired"},
                "id": "override_expired",
            },
            {
                "trigger": "event",
                "event_type": "off_grid_protection_override",
                "event_data": {"action": "grid_return"},
                "id": "override_grid_return",
            },
            {
                "trigger": "event",
                "event_type": "off_grid_protection_locked",
                "id": "protection_locked",
            },
        ])

    if "security" in notification_events:
        triggers.append({
            "trigger": "event",
            "event_type": "off_grid_protection_security",
            "id": "security_event",
        })

    choose: list[dict[str, Any]] = []

    if "grid" in notification_events:
        choose.extend([
            {
                "conditions": [
                    {
                        "condition": "template",
                        "value_template": (
                            "{{ trigger.id == 'grid_status' and "
                            "trigger.to_state.state | lower "
                            "| replace('-', '_') | replace(' ', '_') "
                            "in ['off_grid', 'offgrid', 'island', 'islanding'] }}"
                        ),
                    }
                ],
                "sequence": notify_actions(
                    text("grid_off_title"),
                    text("grid_off_message"),
                ),
            },
            {
                "conditions": [
                    {
                        "condition": "template",
                        "value_template": (
                            "{{ trigger.id == 'grid_status' and "
                            "trigger.to_state.state | lower "
                            "| replace('-', '_') | replace(' ', '_') "
                            "in ['on_grid', 'ongrid', 'grid', 'normal', 'connected'] }}"
                        ),
                    }
                ],
                "sequence": notify_actions(
                    text("grid_on_title"),
                    text("grid_on_message"),
                ),
            },
        ])

    if "protection" in notification_events:
        choose.extend([
            {
                "conditions": [{"condition": "trigger", "id": "override_activated"}],
                "sequence": notify_actions(
                    text("override_title"),
                    text("override_message"),
                ),
            },
            {
                "conditions": [{"condition": "trigger", "id": "override_expired"}],
                "sequence": notify_actions(
                    text("override_expired_title"),
                    text("override_expired_message"),
                ),
            },
            {
                "conditions": [{"condition": "trigger", "id": "override_grid_return"}],
                "sequence": notify_actions(
                    text("override_grid_return_title"),
                    text("override_grid_return_message"),
                ),
            },
            {
                "conditions": [{"condition": "trigger", "id": "protection_locked"}],
                "sequence": notify_actions(
                    text("locked_title"),
                    text("locked_message"),
                ),
            },
            {
                "conditions": [
                    {
                        "condition": "template",
                        "value_template": (
                            "{{ trigger.id == 'recovery_event' and "
                            "trigger.event.data.action == 'completed' }}"
                        ),
                    }
                ],
                "sequence": notify_actions(
                    text("recovery_title"),
                    text("recovery_message"),
                ),
            },
        ])

    if "security" in notification_events:
        choose.append({
            "conditions": [
                {
                    "condition": "template",
                    "value_template": (
                        "{{ trigger.id == 'security_event' and "
                        "trigger.event.data.action == 'invalid_pin' }}"
                    ),
                }
            ],
            "sequence": notify_actions(
                text("invalid_pin_title"),
                text("invalid_pin_message"),
            ),
        })

    return {
        "id": automation_id,
        "alias": text("automation_alias"),
        "description": text("automation_description"),
        "triggers": triggers,
        "conditions": [],
        "actions": [{"choose": choose}] if choose else [],
        "mode": "queued",
        "max": 20,
    }

def _read_text(path: Path) -> str:
    """Read a text file in the executor thread."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _write_text(path: Path, content: str) -> None:
    """Write a text file in the executor thread."""
    path.write_text(
        content,
        encoding="utf-8",
    )


async def async_generate_house_status_automation(
    hass: HomeAssistant,
    *,
    automation_id: str,
    inverter_entity: str,
    notification_types: list[str],
    notification_events: list[str],
    notify_targets: list[str],
    browser_mod_targets: list[str],
    language: str,
) -> str:
    """Create or replace the OGP central notification automation."""
    texts = await _load_notification_texts(
        hass,
        language,
    )

    automation = _build_automation(
        automation_id=automation_id,
        inverter_entity=inverter_entity,
        notification_types=notification_types,
        notification_events=notification_events,
        notify_targets=notify_targets,
        browser_mod_targets=browser_mod_targets,
        texts=texts,
    )

    path = _automation_file(hass)

    try:
        content = await hass.async_add_executor_job(
            partial(
                _read_text,
                path,
            )
        )
    except OSError as err:
        raise HomeAssistantError(
            f"Unable to read {path}: {err}"
        ) from err

    content = _remove_generated_block(
        content,
        automation_id,
    )

    block = yaml.safe_dump(
        [automation],
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).rstrip()

    content = _append_generated_block(
        content,
        block,
    )

    try:
        await hass.async_add_executor_job(
            partial(
                _write_text,
                path,
                content,
            )
        )
    except OSError as err:
        raise HomeAssistantError(
            f"Unable to write {path}: {err}"
        ) from err

    if hass.services.has_service(
        "automation",
        "reload",
    ):
        await hass.services.async_call(
            "automation",
            "reload",
            blocking=True,
        )

    return automation_id


async def async_remove_house_status_automation(
    hass: HomeAssistant,
    automation_id: str,
) -> None:
    """Remove an OGP-generated central notification automation."""
    path = _automation_file(hass)

    try:
        content = await hass.async_add_executor_job(
            partial(
                _read_text,
                path,
            )
        )
    except OSError:
        return

    if not content:
        return

    updated = _remove_generated_block(
        content,
        automation_id,
    )

    if updated == content:
        return

    try:
        await hass.async_add_executor_job(
            partial(
                _write_text,
                path,
                updated,
            )
        )
    except OSError:
        return

    if hass.services.has_service(
        "automation",
        "reload",
    ):
        await hass.services.async_call(
            "automation",
            "reload",
            blocking=True,
        )
