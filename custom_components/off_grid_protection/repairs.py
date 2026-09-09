"""Repairs for Off-grid Protection."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant

DOMAIN = "off_grid_protection"
ISSUE_CENTRAL_RESTART_REQUIRED = "central_restart_required"


class CentralRestartRepairFlow(RepairsFlow):
    """Handle the required Home Assistant restart."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> RepairsFlowResult:
        """Confirm and request a Home Assistant restart."""
        if user_input is not None:
            await self.hass.services.async_call(
                "homeassistant",
                "restart",
            )
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    """Create the repair flow for an OGP issue."""
    if issue_id == ISSUE_CENTRAL_RESTART_REQUIRED:
        return CentralRestartRepairFlow()

    raise ValueError(f"Unknown repair issue: {issue_id}")
