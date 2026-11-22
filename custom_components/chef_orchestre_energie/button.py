"""Bouton « Recalculer »."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ChefEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([RecalculateButton(entry.runtime_data, "recalculate")])


class RecalculateButton(ChefEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self.orch.async_check_sources()
        await self.orch.async_update_plan()
