"""Seuil de rentabilité réglable à chaud."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ChefEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    orch = entry.runtime_data
    async_add_entities([GainThreshold(orch, "gain_threshold"), ReserveSoc(orch, "reserve_soc")])


class GainThreshold(ChefEntity, NumberEntity):
    _attr_native_min_value = 0.0
    _attr_native_max_value = 1.0
    _attr_native_step = 0.005
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return self.orch.gain_threshold

    async def async_set_native_value(self, value: float) -> None:
        await self.orch.async_set_gain_threshold(value)


class ReserveSoc(ChefEntity, NumberEntity):
    """SOC minimum imposé aux batteries quand le plan est non rentable (E2)."""

    _attr_native_min_value = 0
    _attr_native_max_value = 50
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> float:
        return self.orch.reserve_soc

    async def async_set_native_value(self, value: float) -> None:
        await self.orch.async_set_reserve_soc(value)
