"""Réparations du Chef d'orchestre énergie (R2, v1.3.6)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

DEFAULT_USER_MIN_SOC = 5.0


class UserMinSocFlow(RepairsFlow):
    """« SOC min de l'utilisateur égal à la réserve » : rendre 5 % ou la valeur choisie."""

    def __init__(self, entry_id: str | None) -> None:
        self._entry_id = entry_id

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        entry = self.hass.config_entries.async_get_entry(self._entry_id) if self._entry_id else None
        orch = getattr(entry, "runtime_data", None) if entry else None
        if orch is None:
            return self.async_abort(reason="not_loaded")
        if user_input is not None:
            await orch.async_set_user_min_soc(float(user_input["min_soc"]))
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("min_soc", default=DEFAULT_USER_MIN_SOC): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0, max=50, step=1, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX
                        )
                    )
                }
            ),
            description_placeholders={"reserve": f"{orch.reserve_soc:g}"},
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str | int | float | None] | None
) -> RepairsFlow:
    return UserMinSocFlow((data or {}).get("entry_id"))
