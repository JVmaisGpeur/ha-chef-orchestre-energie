"""Interrupteur « Pilotage automatique »."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ChefEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([AutoControlSwitch(entry.runtime_data, "auto_control")])


class AutoControlSwitch(ChefEntity, SwitchEntity):
    """Coupé : plus aucune commande, la batterie garde son dernier mode."""

    @property
    def is_on(self) -> bool:
        return self.orch.auto_control

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Contrat d'interface (E1) : ce que le Chef d'orchestre pilote."""
        return self.orch.interface_attributes

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.orch.async_set_auto_control(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.orch.async_set_auto_control(False)
