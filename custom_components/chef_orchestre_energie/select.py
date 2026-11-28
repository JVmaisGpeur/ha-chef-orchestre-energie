"""Profil de prudence : marge ajoutée au besoin des heures pleines."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import FULL_CHARGE_OPTIONS, PROFILES
from .days import DAY_STARTS
from .entity import ChefEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    orch = entry.runtime_data
    async_add_entities(
        [ProfileSelect(orch, "profile"), FullChargeSelect(orch, "full_charge"), DayStartSelect(orch, "day_start")]
    )


class ProfileSelect(ChefEntity, SelectEntity):
    _attr_options = list(PROFILES)

    @property
    def current_option(self) -> str:
        return self.orch.profile_name

    async def async_select_option(self, option: str) -> None:
        await self.orch.async_set_profile(option)


class FullChargeSelect(ChefEntity, SelectEntity):
    """Charge complète (N3) : automatique, prochain soleil, cette nuit, maintenant, ignorer."""

    _attr_options = list(FULL_CHARGE_OPTIONS)

    @property
    def current_option(self) -> str:
        return self.orch.fullcharge.request

    async def async_select_option(self, option: str) -> None:
        await self.orch.async_set_full_charge(option)


class DayStartSelect(ChefEntity, SelectEntity):
    """Début de la journée du plan (v1.4.0, ex-1.3.7, A2) : découpe des cases de la carte."""

    _attr_options = list(DAY_STARTS)
    _attr_icon = "mdi:calendar-clock"

    @property
    def current_option(self) -> str:
        return self.orch.day_start

    async def async_select_option(self, option: str) -> None:
        await self.orch.async_set_day_start(option)