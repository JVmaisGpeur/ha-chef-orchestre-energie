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
R_SHIFTED = "shifted"  # plage ON du routeur bloquée : la chauffe est déplacée
R_SHIFT_HEAT = "shift_heat"  # chauffe déplacée en cours (marche forcée du Chef)


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
    force_heat: bool = False  # fenêtre de chauffe déplacée en cours, ballon à chauffer
    slot_shifted: bool = False  # la plage ON du routeur est remplacée par une fenêtre du Chef


@dataclass
class RouterDecision:
    lock: bool  # arrêt forcé à envoyer au routeur
    reason: str
    charge_ceiling_w: float | None = None  # plafond de charge des batteries (routeur d'abord)
    no_discharge: bool = False  # interdire la décharge (plage ON qui chauffe)
    force: bool = False  # marche forcée à envoyer au routeur (chauffe déplacée)


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

        # Chauffe déplacée par le Chef : marche forcée, les batteries ne la paient pas
        if i.force_heat:
            self.unlock_since = None
            return RouterDecision(False, R_SHIFT_HEAT, no_discharge=True, force=True)

        # Plage ON (rattrapage du routeur en heures creuses)
        if i.on_slot:
            self.unlock_since = None
            if i.slot_shifted:
                return RouterDecision(True, R_SHIFTED)
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


# Prévision de la prochaine plage ON (commentaire de la carte)
OUTLOOK_HEAT = "heat"  # le Chef laissera le routeur chauffer
OUTLOOK_SUN = "sun"  # le Chef bloquera la plage : le soleil de demain suffit
OUTLOOK_HOT = "hot"  # pas de chauffe : ballon déjà chaud


def next_on_slot(
    slots: list | None, now: datetime, horizon: timedelta = timedelta(hours=24)
) -> tuple[datetime, datetime, float | None] | None:
    """Prochaine plage ON du planning du routeur, en cours ou à venir dans l'horizon.

    `slots` : attribut `slots` du capteur `planning` de ha-routeur-f1atb (minutes
    depuis minuit, `kind` off/on/route). Renvoie (début, fin, seuil de température)
    ; le seuil `t_below` ne compte que si la plage suit une sonde (`temp_channel` ≥ 0).
    """
    best = None
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for day in (0, 1):
        base = midnight + timedelta(days=day)
        for s in slots or []:
            if not isinstance(s, dict) or s.get("kind") != "on":
                continue
            try:
                a, b = int(s["start_min"]), int(s["end_min"])
            except (KeyError, TypeError, ValueError):
                continue
            start = base + timedelta(minutes=a)
            end = base + timedelta(minutes=b if b > a else b + 1440)
            if end <= now or start > now + horizon:
                continue
            if best is None or start < best[0]:
                channel = s.get("temp_channel")
                t_below = s.get("t_below") if isinstance(channel, int) and channel >= 0 else None
                best = (start, end, float(t_below) if t_below is not None else None)
    return best


def on_slot_outlook(
    temperature: float | None, t_below: float | None, target_reached: bool, ballon_sun_ok: bool
) -> str:
    """Ce que le Chef fera de la prochaine plage ON, avec les données d'aujourd'hui (même règle que `step`)."""
    if target_reached or (t_below is not None and temperature is not None and temperature >= t_below):
        return OUTLOOK_HOT
    if ballon_sun_ok:
        return OUTLOOK_SUN
    return OUTLOOK_HEAT


WHY_POWER = "power"  # la plage dépasserait la puissance souscrite
WHY_BATTERY = "battery"  # la plage tombait pendant la charge des batteries


@dataclass
class NightStep:
    """Un pas du plan de la nuit, vu par le placement de la chauffe."""

    start: datetime
    off_peak: bool
    busy_w: float  # consommation de base + gros consommateurs + charge réseau des batteries
    charging: bool  # charge réseau des batteries prévue sur ce pas


def choose_heat_window(
    night: list[NightStep],
    step: timedelta,
    slot_start: datetime,
    slot_end: datetime,
    router_w: float,
    limit_w: float,
    previous: datetime | None = None,
) -> tuple[datetime, datetime, str | None]:
    """Fenêtre de chauffe de même durée que la plage ON, dans les mêmes heures creuses.

    Critères, dans l'ordre : ne pas dépasser la puissance souscrite, ne pas tomber
    pendant la charge des batteries, garder la fenêtre déjà choisie (pas de va-et-vient),
    rester au plus près de la plage du routeur. Renvoie (début, fin, raison du
    déplacement) ; la plage du routeur est rendue telle quelle si elle convient.
    """
    length = slot_end - slot_start
    keep = (slot_start, slot_end, None)
    if length <= timedelta(0) or not night:
        return keep
    # Heures creuses qui contiennent le début de la plage
    k0 = next((k for k, n in enumerate(night) if n.start <= slot_start < n.start + step), None)
    if k0 is None or not night[k0].off_peak:
        return keep
    lo = k0
    while lo > 0 and night[lo - 1].off_peak:
        lo -= 1
    hi = k0
    while hi + 1 < len(night) and night[hi + 1].off_peak:
        hi += 1
    hc_end = night[hi].start + step

    def score(start: datetime) -> tuple[float, int]:
        end = start + length
        over, overlap = 0.0, 0
        for n in night[lo : hi + 1]:
            if n.start < end and n.start + step > start:
                over += max(0.0, n.busy_w + router_w - limit_w)
                overlap += n.charging
        return round(over), overlap

    candidates = {slot_start} | {
        night[k].start for k in range(lo, hi + 1) if night[k].start + length <= hc_end
    }
    if previous is not None and night[lo].start <= previous and previous + length <= hc_end:
        candidates.add(previous)
    best = min(
        candidates,
        key=lambda s: (*score(s), s != previous, abs((s - slot_start).total_seconds()), s),
    )
    if best == slot_start:
        return keep
    over, overlap = score(slot_start)
    why = WHY_POWER if over > 0 else (WHY_BATTERY if overlap else None)
    if why is None:
        return keep
    return best, best + length, why


def combine(decisions: list[RouterDecision], *, grid_charging: bool = False) -> tuple[float | None, bool]:
    """Plafond de charge et interdiction de décharge pour les batteries, tous routeurs confondus.

    Le plafond « routeur d'abord » ne vise que le surplus solaire : pendant une
    charge réseau (heures creuses, charge complète), il ne s'applique jamais.
    """
    ceilings = [] if grid_charging else [d.charge_ceiling_w for d in decisions if d.charge_ceiling_w is not None]
    return (min(ceilings) if ceilings else None), any(d.no_discharge for d in decisions)
