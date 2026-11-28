"""Heure de début de la journée du plan (v1.4.0, ex-1.3.7, A2), pour le choix « Heure fixe »."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ChefEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DayStartTime(entry.runtime_data, "day_start_time")])


class DayStartTime(ChefEntity, TimeEntity):
    _attr_icon = "mdi:clock-start"

    @property
    def native_value(self) -> time:
        return self.orch.day_start_time

    async def async_set_value(self, value: time) -> None:
        await self.orch.async_set_day_start_time(value)