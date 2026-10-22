"""OGP central house-status notification automation."""

from __future__ import annotations

from pathlib import Path
import json
from typing import Any


from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event

DOMAIN = "off_grid_protection"
AUTOMATION_ID_PREFIX = "ogp_house_status_notification"


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


async def _load_notification_texts(
    hass: HomeAssistant,
    language: str,
) -> dict[str, str]:
    """Load notification texts without blocking the event loop."""

    translation_path = (
        Path(__file__).parent
        / "notification_messages.json"
    )

    data = await hass.async_add_executor_job(
        lambda: translation_path.read_text(
            encoding="utf-8",
        )
    )
    translations = json.loads(data)

    messages = translations.get(language, {})
    if not isinstance(messages, dict):
        return {}

    return {
        str(key): str(value)
        for key, value in messages.items()
    }


async def async_generate_house_status_automation(
    hass: HomeAssistant,
    *,
    automation_id: str,
    inverter_entity: str,
    notification_types: list[str],
    notification_events: list[str],
    notify_targets: list[str],
    language: str,
    notification_mode: str = "global",
    custom_targets: dict[str, dict[str, list[str]]] | None = None,
) -> str:
    """Register OGP notification listeners directly in Home Assistant."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    listeners = domain_data.setdefault("notification_listeners", {})
    old_unsubs = listeners.pop(automation_id, [])
    for unsub in old_unsubs:
        unsub()

    texts = await _load_notification_texts(hass, language)
    enabled_events = set(notification_events)

    # Older entries may use per-profile notification configuration.
    targets_by_event: dict[str, list[str]] = {}
    if notification_mode == "custom":
        for target, events in (custom_targets or {}).get("notify", {}).items():
            for event_name in events:
                targets_by_event.setdefault(event_name, []).append(target)
    else:
        for event_name in enabled_events:
            targets_by_event[event_name] = list(notify_targets)

    def targets_for(event_name: str) -> list[str]:
        return targets_by_event.get(event_name, [])

    async def send(event_name: str, title_key: str, message_key: str, event_data: dict[str, Any] | None = None) -> None:
        title = texts.get(title_key, title_key)
        message = texts.get(message_key, message_key)
        values = event_data or {}
        message = message.replace("{{ trigger.event.data.device_name }}", str(values.get("device_name", "nepoznat uređaj")))
        message = message.replace("{{ trigger.event.data.duration_minutes }}", str(values.get("duration_minutes", "?")))
        for target in targets_for(event_name):
            if target.startswith("entity:"):
                service = "send_message"
                service_data = {"title": title, "message": message}
                target_data = {"entity_id": target.split(":", 1)[1]}
                await hass.services.async_call("notify", service, service_data | {"target": target_data}, blocking=False)
            elif target.startswith("service:"):
                service_name = target.split(":", 1)[1]
                await hass.services.async_call("notify", service_name, {"title": title, "message": message}, blocking=False)

    unsubs = []

    if "grid" in enabled_events:
        async def grid_changed(event):
            old = event.data.get("old_state")
            new_state = event.data.get("new_state")
            if old is None or new_state is None or old.state.lower() in ("unknown", "unavailable"):
                return
            normalized = new_state.state.lower().replace("-", "_").replace(" ", "_")
            if normalized in ("off_grid", "offgrid", "island", "islanding"):
                await send("grid", "grid_off_title", "grid_off_message")
            elif normalized in ("on_grid", "ongrid", "grid", "normal", "connected"):
                await send("grid", "grid_on_title", "grid_on_message")
        unsubs.append(async_track_state_change_event(hass, [inverter_entity], grid_changed))

    event_map = {
        "off_grid_protection_recovery": ("protection", "recovery_title", "recovery_message", "completed"),
        "off_grid_protection_override": ("protection", "override_title", "override_message", "activated"),
        "off_grid_protection_locked": ("protection", "locked_title", "locked_message", None),
        "off_grid_protection_shutdown_failed": ("protection", "shutdown_failed_title", "shutdown_failed_message", None),
    }
    # Separate event subscriptions keep behavior local to this integration and do not create HA automations.
    for event_type, (category, title_key, message_key, required_action) in event_map.items():
        if category not in enabled_events and not (category == "protection" and "protection" in enabled_events):
            continue
        if event_type == "off_grid_protection_override":
            actions = {
                "activated": ("override_title", "override_message"),
                "expired": ("override_expired_title", "override_expired_message"),
                "grid_return": ("override_grid_return_title", "override_grid_return_message"),
            }
        else:
            actions = {required_action: (title_key, message_key)} if required_action else {None: (title_key, message_key)}
        async def handle_event(event, _actions=actions, _category=category, _event_type=event_type):
            action = event.data.get("action")
            if action not in _actions:
                return
            if _event_type == "off_grid_protection_recovery" and action != "completed":
                return
            if _event_type == "off_grid_protection_security" and action != "invalid_pin":
                return
            t_key, m_key = _actions[action]
            await send(_category, t_key, m_key, event.data)
        unsubs.append(hass.bus.async_listen(event_type, handle_event))

    listeners[automation_id] = unsubs
    return automation_id


async def async_remove_house_status_automation(
    hass: HomeAssistant,
    automation_id: str,
) -> None:
    """Unregister OGP notification listeners."""
    listeners = hass.data.get(DOMAIN, {}).get("notification_listeners", {})
    for unsub in listeners.pop(automation_id, []):
        unsub()