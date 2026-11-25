"""Arbitrage entre batteries et routeur solaire F1ATB (N5, pur Python).

Une décision par minute et par routeur. Conventions de signe : puissance batterie
positive en charge, négative en décharge (comme ha-zendure-solarflow-local).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

BATTERY_FIRST = "battery_first"
ROUTER_FIRST = "router_first"

SUSTAIN = timedelta(minutes=2)  # durée avant de déverrouiller ou de délester
RELEASE = timedelta(minutes=1)
UNLOCK_RATIO = 0.95  # charge ≥ 95 % de la puissance max…
RELOCK_RATIO = 0.80  # …reverrouillage sous 80 %
FULL_OPEN_RATIO = 0.95  # routeur « à pleine ouverture »
DISCHARGE_W = 50  # en dessous, la batterie est considérée au repos
ROUTED_W = 50

# Raisons affichées (carte, attributs)
R_LOCKED = "locked"  # verrouillé : batteries d'abord
R_ROUTING = "routing"  # routage solaire libre
R_SHED = "shed"  # délesté : les batteries chauffaient le ballon
R_ON_BLOCKED = "on_blocked"  # plage ON bloquée (ballon chaud ou soleil demain)
R_BOOST = "boost"  # plage ON : chauffe sur le réseau
R_HOT = "hot"  # ballon chaud


@dataclass
class RouterInputs:
    now: datetime
    priority: str
    routed_w: float | None
    load_w: float | None
    target_reached: bool
    on_slot: bool
    battery_w: float | None
    max_charge_w: float
    all_full: bool
    grid_export: bool
    soc: float | None
    summer_soc: float
    batteries_sun_ok: bool  # le soleil de demain suffit à recharger les batteries
    ballon_sun_ok: bool  # le soleil de demain suffit à chauffer le ballon


@dataclass
class RouterDecision:
    lock: bool  # arrêt forcé à envoyer au routeur
    reason: str
    charge_ceiling_w: float | None = None  # plafond de charge des batteries (routeur d'abord)
    no_discharge: bool = False  # interdire la décharge (plage ON qui chauffe)


@dataclass
class RouterLogic:
    """État d'un routeur entre deux décisions (minuteries des seuils)."""

    locked: bool = True
    unlock_since: datetime | None = None
    shed: bool = False
    shed_since: datetime | None = None
    calm_since: datetime | None = None

    def step(self, i: RouterInputs) -> RouterDecision:
        bat = i.battery_w or 0.0
        routed = i.routed_w or 0.0

        # Plage ON (rattrapage du routeur en heures creuses)
        if i.on_slot:
            self.unlock_since = None
            if i.target_reached or i.ballon_sun_ok:
                return RouterDecision(True, R_ON_BLOCKED)
            return RouterDecision(False, R_BOOST, no_discharge=True)

        # Surveillance : les batteries ne doivent pas chauffer le ballon
        summer = i.soc is not None and i.soc >= i.summer_soc and i.batteries_sun_ok
        feeding = bat < -DISCHARGE_W and routed > ROUTED_W and not summer
        if feeding:
            self.calm_since = None
            self.shed_since = self.shed_since or i.now
            if i.now - self.shed_since >= SUSTAIN:
                self.shed = True
        else:
            self.shed_since = None
            if self.shed:
                self.calm_since = self.calm_since or i.now
                if i.now - self.calm_since >= RELEASE:
                    self.shed, self.calm_since = False, None

        if i.priority == ROUTER_FIRST:
            self.locked = False
            if self.shed:
                return RouterDecision(True, R_SHED)
            if i.target_reached:
                return RouterDecision(False, R_HOT)
            full_open = bool(i.load_w) and routed >= FULL_OPEN_RATIO * float(i.load_w)
            return RouterDecision(False, R_ROUTING, charge_ceiling_w=None if full_open else 0.0)

        # Batteries toujours d'abord
        if self.locked:
            can_unlock = i.all_full or (bat >= UNLOCK_RATIO * i.max_charge_w and i.grid_export)
            if can_unlock:
                self.unlock_since = self.unlock_since or i.now
                if i.now - self.unlock_since >= SUSTAIN:
                    self.locked, self.unlock_since = False, None
            else:
                self.unlock_since = None
        else:
            relock = bat < -DISCHARGE_W or (bat < RELOCK_RATIO * i.max_charge_w and not i.all_full)
            if relock:
                self.locked = True
        if self.locked:
            return RouterDecision(True, R_LOCKED)
        if self.shed:
            return RouterDecision(True, R_SHED)
        return RouterDecision(False, R_HOT if i.target_reached else R_ROUTING)


def combine(decisions: list[RouterDecision], *, grid_charging: bool = False) -> tuple[float | None, bool]:
    """Plafond de charge et interdiction de décharge pour les batteries, tous routeurs confondus.

    Le plafond « routeur d'abord » ne vise que le surplus solaire : pendant une
    charge réseau (heures creuses, charge complète), il ne s'applique jamais.
    """
    ceilings = [] if grid_charging else [d.charge_ceiling_w for d in decisions if d.charge_ceiling_w is not None]
    return (min(ceilings) if ceilings else None), any(d.no_discharge for d in decisions)
