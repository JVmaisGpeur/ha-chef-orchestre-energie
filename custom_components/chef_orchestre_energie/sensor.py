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
from homeassistant.core import HomeAssistant, callback
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
    async_add_entities([ChefSensor(orch, d) for d in SENSORS])
    from . import sources as src

    created: set[str] = set()

    @callback
    def add_full_charge_sensors() -> None:
        """Un capteur par batterie, y compris celles connues plus tard (Zendure chargé après nous)."""
        units = orch.units or src.battery_units(hass, orch.cfg["battery_device_id"])
        new = [dev for dev in units if dev not in created]
        created.update(new)
        if new:
            async_add_entities([FullChargeDaysSensor(orch, dev, src.device_name(hass, dev)) for dev in new])

    add_full_charge_sensors()
    orch.units_listener = add_full_charge_sensors


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
            reserve = self.orch.reserve_now()
            return {
                "reason": plan.reason,
                "missing": self.orch.missing,
                "price_gap": plan.price_gap,
                "charge_end": plan.charge_end.isoformat() if plan.charge_end else None,
                "reserve_soc": plan.reserve_soc,
                # R1 (v1.3.5) : réserve prévue pour les heures creuses de la nuit seulement
                "reserve_from": plan.reserve_from.isoformat() if plan.reserve_from else None,
                "reserve_until": plan.reserve_until.isoformat() if plan.reserve_until else None,
                "reserve_active": reserve is not None,
                "user_min_soc": self.orch.user_soc.get("min"),
                "user_max_soc": self.orch.user_soc.get("max"),
                "applied_min_soc": self.orch.applied_min_soc(reserve),
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
                # v1.3.0
                "battery_control": self.orch.battery_control,
                "ceilings_available": self.orch.ceilings_ok,
                "excluded_power": round(self.orch.excluded_w),
                "full_charge_planned": self.orch.fc_action,
                "full_charge_request": self.orch.fullcharge.request,
                "full_charge_units": self.orch.fc_units,
                "full_charge_late": self.orch.fc_alert,
                **self.orch.full_charge_now_estimate(),
                "calibrating": self.orch.calibrating_units,
                "router_priority": self.orch.cfg.get("router_priority"),
                "routers": self.orch.router_status,
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


class FullChargeDaysSensor(ChefEntity, SensorEntity):
    """Jours depuis la dernière charge complète d'une batterie (N3)."""

    _attr_native_unit_of_measurement = "d"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, orch: Orchestrator, device_id: str, name: str) -> None:
        super().__init__(orch, "full_charge_days")
        self._device = device_id
        self._attr_unique_id = f"{orch.entry.entry_id}_full_charge_days_{device_id}"
        self._attr_translation_placeholders = {"battery": name}

    @property
    def native_value(self) -> float | None:
        from homeassistant.util import dt as dt_util

        days = self.orch.fullcharge.days(self._device, dt_util.now())
        return None if days is None else round(days, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        fc = self.orch.fullcharge
        last = fc.last(self._device)
        due = fc.calibration_due(self._device)
        return {
            "device_id": self._device,
            "last_full_charge": last.isoformat() if last else None,
            "estimated": self._device in fc.estimated,
            "calibration_expected": due.isoformat() if due else None,
            "calibrating": self._device in self.orch.calibrating_units,
            "threshold_days": self.orch.cfg.get("full_charge_days", 20),
        }
