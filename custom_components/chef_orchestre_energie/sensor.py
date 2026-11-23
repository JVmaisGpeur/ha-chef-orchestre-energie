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
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfPower
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
        key="board_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o, p: None if o.board_power_w is None else round(o.board_power_w),
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
                "missing": self.orch.missing,
                "price_gap": plan.price_gap,
                "charge_end": plan.charge_end.isoformat() if plan.charge_end else None,
                "reserve_soc": plan.reserve_soc,
                "user_min_soc": self.orch.user_soc.get("min"),
                "user_max_soc": self.orch.user_soc.get("max"),
                "applied_min_soc": plan.reserve_soc if plan.reserve_soc is not None else self.orch.user_soc.get("min"),
                "applied_max_soc": 100 if self.orch.full_charge else self.orch.user_soc.get("max"),
                "full_charge": self.orch.full_charge,
                "gain_threshold": self.orch.gain_threshold,
                "efficiency": round(self.orch.efficiency_used, 3),
                "tariff_ok": self.orch.tariff_ok,
                "tariff_entity": self.orch.tariff_entities.get("prix_actuel"),
                "battery_ok": self.orch.sources_ok,
                "reserve_available": self.orch.e2_ok,
                "consumption_source": self.orch.consumption_source,
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
        if key == "board_power":
            kva = self.orch.subscribed_kva
            p = self.orch.board_power_w
            limit = kva * 1000 if kva else None
            return {
                "subscribed_kva": kva,
                "limit_w": limit,
                "margin_w": None if limit is None or p is None else round(limit - p),
                "percent": None if not limit or p is None else round(p / limit * 100, 1),
                "power_entity": self.orch.cfg.get("power_sensor"),
                "loads": self.orch.running_loads(),
                "gauge_warn": self.orch.cfg.get("gauge_warn", 80),
                "gauge_crit": self.orch.cfg.get("gauge_crit", 95),
            }
        if key == "measured_efficiency":
            return {"measured": self.orch.measured_efficiency is not None}
        if key == "forecast_solar":
            return {"correction_factor": self.orch.solar_factor}
        if key == "forecast_reliability":
            return {"days_of_data": self.orch.profile.days_of_data}
        return None
