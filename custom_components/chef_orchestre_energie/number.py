"""Seuil de rentabilité réglable à chaud."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ChefEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([GainThreshold(entry.runtime_data, "gain_threshold")])


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
