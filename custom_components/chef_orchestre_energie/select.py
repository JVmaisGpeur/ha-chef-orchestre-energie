"""Profil de prudence : marge ajoutée au besoin des heures pleines."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PROFILES
from .entity import ChefEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ProfileSelect(entry.runtime_data, "profile")])


class ProfileSelect(ChefEntity, SelectEntity):
    _attr_options = list(PROFILES)

    @property
    def current_option(self) -> str:
        return self.orch.profile_name

    async def async_select_option(self, option: str) -> None:
        await self.orch.async_set_profile(option)
