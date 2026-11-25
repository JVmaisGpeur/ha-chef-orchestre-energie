"""Interrupteurs de pilotage : général (E1), batteries et routeurs (N6)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ChefEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    orch = entry.runtime_data
    entities: list[SwitchEntity] = [
        AutoControlSwitch(orch, "auto_control"),
        BatteryControlSwitch(orch, "battery_control"),
    ]
    entities += [RouterControlSwitch(orch, r) for r in orch.routers]
    async_add_entities(entities)


class AutoControlSwitch(ChefEntity, SwitchEntity):
    """Interrupteur général : coupé, plus aucune commande ; rallumé, les choix reviennent."""

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


class BatteryControlSwitch(ChefEntity, SwitchEntity):
    """Pilotage des batteries : coupé, Zendure reprend la main (vos réglages rendus)."""

    @property
    def is_on(self) -> bool:
        return self.orch.battery_control

    @property
    def available(self) -> bool:
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"effective": self.orch.battery_piloted}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.orch.async_set_battery_control(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.orch.async_set_battery_control(False)


class RouterControlSwitch(ChefEntity, SwitchEntity):
    """Pilotage d'un routeur F1ATB : coupé, le routeur revient en autonome."""

    def __init__(self, orch, router: dict[str, Any]) -> None:
        super().__init__(orch, "router_control")
        self._device = router["device_id"]
        self._attr_unique_id = f"{orch.entry.entry_id}_router_control_{self._device}"
        self._attr_translation_placeholders = {"router": router.get("name") or self._device}

    @property
    def is_on(self) -> bool:
        return self.orch.router_control.get(self._device, True)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = next((r for r in self.orch.router_status if r["device_id"] == self._device), {})
        return {"device_id": self._device, "effective": bool(status.get("piloted")), "state": status.get("state")}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.orch.async_set_router_control(self._device, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.orch.async_set_router_control(self._device, False)
