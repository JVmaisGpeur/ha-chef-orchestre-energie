"""Alerte : risque de dépasser la puissance souscrite cette nuit."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ChefEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([PowerAlert(entry.runtime_data, "power_alert")])


class PowerAlert(ChefEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool:
        plan = self.orch.plan
        return bool(plan and plan.power_alert)

    @property
    def extra_state_attributes(self):
        return {
            "import_limit": self.orch.import_limit,
            "subscribed_kva": self.orch.subscribed_kva,
        }
