"""Capteurs : le plan de la nuit, ses raisons et ce qu'il rapporte."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .consumption import RELIABILITIES
from .entity import ChefEntity
from .manager import Orchestrator
from .planner import PLAN_STATES, Plan


@dataclass(frozen=True, kw_only=True)
class ChefSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Orchestrator, Plan | None], Any]


def _p(attr: str, digits: int = 2):
    def fn(_o: Orchestrator, plan: Plan | None):
        if plan is None:
            return None
        v = getattr(plan, attr)
        return round(v, digits) if isinstance(v, float) else v

    return fn


KWH = {
    "native_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
    "device_class": SensorDeviceClass.ENERGY,
    "suggested_display_precision": 1,
}

SENSORS: tuple[ChefSensorDescription, ...] = (
    ChefSensorDescription(
        key="night_plan",
        device_class=SensorDeviceClass.ENUM,
        options=PLAN_STATES,
        value_fn=lambda o, p: p.state if p else None,
    ),
    ChefSensorDescription(key="energy_to_charge", value_fn=_p("grid_energy_kwh"), **KWH),
    ChefSensorDescription(
        key="target_soc",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda o, p: p.target_soc if p else None,
    ),
    ChefSensorDescription(
        key="charge_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda o, p: p.charge_start if p else None,
    ),
    ChefSensorDescription(key="forecast_consumption", value_fn=_p("consumption_kwh"), **KWH),
    ChefSensorDescription(key="peak_need", value_fn=_p("peak_need_kwh"), **KWH),
    ChefSensorDescription(key="forecast_solar", value_fn=_p("solar_kwh"), **KWH),
    ChefSensorDescription(
        key="forecast_gain",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=_p("forecast_gain_eur"),
    ),
    ChefSensorDescription(
        key="monthly_savings",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda o, p: round(o.monthly_savings, 2),
    ),
    ChefSensorDescription(
        key="measured_efficiency",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda o, p: round(o.efficiency_used * 100, 1),
    ),
    ChefSensorDescription(
        key="forecast_reliability",
        device_class=SensorDeviceClass.ENUM,
        options=RELIABILITIES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda o, p: o.profile.reliability,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    orch: Orchestrator = entry.runtime_data
    async_add_entities(ChefSensor(orch, d) for d in SENSORS)


class ChefSensor(ChefEntity, SensorEntity):
    entity_description: ChefSensorDescription
    _unrecorded_attributes = frozenset({"hourly_plan"})

    def __init__(self, orch: Orchestrator, description: ChefSensorDescription) -> None:
        super().__init__(orch, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.orch, self.orch.plan)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        key = self.entity_description.key
        plan = self.orch.plan
        if key == "night_plan":
            if plan is None:
                return None
            return {
                "reason": plan.reason,
                "window_start": plan.window_start.isoformat() if plan.window_start else None,
                "window_end": plan.window_end.isoformat() if plan.window_end else None,
                "capacity_short": plan.capacity_short,
                "may_not_finish": plan.may_not_finish,
                "import_limit": self.orch.import_limit,
                "hourly_plan": [
                    {
                        "start": sp.start.isoformat(),
                        "mode": sp.mode,
                        "soc": sp.soc,
                        "price": sp.price,
                        "consumption": round(sp.consumption_kwh, 3),
                        "solar": round(sp.solar_kwh, 3),
                        "off_peak": sp.off_peak,
                    }
                    for sp in plan.steps
                ],
            }
        if key == "measured_efficiency":
            return {"measured": self.orch.measured_efficiency is not None}
        if key == "forecast_solar":
            return {"correction_factor": self.orch.solar_factor}
        if key == "forecast_reliability":
            return {"days_of_data": self.orch.profile.days_of_data}
        return None
