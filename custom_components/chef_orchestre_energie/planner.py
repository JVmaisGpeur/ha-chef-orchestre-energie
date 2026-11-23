"""Calcul du plan : faut-il charger cette nuit, combien, quand, et dans quel mode.

Ce module est du Python pur (aucun import de Home Assistant) pour pouvoir être
testé seul. Il travaille sur des pas de temps réguliers (15 min par défaut) qui
couvrent les prochaines 24 à 48 h.

Vocabulaire :
- fenêtre creuse : la prochaine suite continue de pas en heures creuses
  (celle en cours si on y est déjà) ;
- période à couvrir : du bout de cette fenêtre au début de la suivante ;
- énergie batterie : kWh stockés au-dessus du SOC minimum.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import math

# Modes de ha-zendure-solarflow-local (contrat, interface 1)
MODE_OFF = "off"
MODE_SMART = "smart"
MODE_SMART_CHARGE = "smart_charge"
MODE_GRID_CHARGE = "grid_charge"

# États du plan de la nuit (capteur night_plan)
PLAN_CHARGE = "charge"
PLAN_IDLE = "idle"
PLAN_NOT_PROFITABLE = "not_profitable"
PLAN_NOTHING_TO_COVER = "nothing_to_cover"
PLAN_SUSPENDED = "suspended"
PLAN_MISSING_DATA = "missing_data"
PLAN_STATES = [
    PLAN_CHARGE,
    PLAN_IDLE,
    PLAN_NOT_PROFITABLE,
    PLAN_NOTHING_TO_COVER,
    PLAN_SUSPENDED,
    PLAN_MISSING_DATA,
]

# Raisons (attribut reason, traduites dans l'interface)
REASON_CHARGE_NEEDED = "charge_needed"
REASON_ENOUGH_ENERGY = "enough_energy"
REASON_SOLAR_COVERS = "solar_covers"
REASON_GAIN_TOO_LOW = "gain_too_low"
REASON_NO_PEAK_HOURS = "no_peak_hours"
REASON_NO_OFF_PEAK = "no_off_peak"
REASON_CAPACITY_SHORT = "capacity_short"
REASON_FORCED_CHARGE = "forced_charge"
REASON_FORCED_IDLE = "forced_idle"
REASON_MISSING_DATA = "missing_data"
REASONS = [
    REASON_CHARGE_NEEDED,
    REASON_ENOUGH_ENERGY,
    REASON_SOLAR_COVERS,
    REASON_GAIN_TOO_LOW,
    REASON_NO_PEAK_HOURS,
    REASON_NO_OFF_PEAK,
    REASON_CAPACITY_SHORT,
    REASON_FORCED_CHARGE,
    REASON_FORCED_IDLE,
    REASON_MISSING_DATA,
]

SOLAR_MIN_KWH = 0.02  # en dessous, on considère qu'il n'y a pas de soleil sur le pas
MIN_CHARGE_KWH = 0.1  # en dessous, la charge ne vaut pas la peine


@dataclass
class Step:
    """Un pas de temps à venir."""

    start: datetime
    consumption_kwh: float  # consommation de base prévue (hors gros consommateurs)
    solar_kwh: float  # production solaire prévue
    price: float | None  # €/kWh, None si inconnu
    off_peak: bool  # heures creuses
    loads_w: float = 0.0  # puissance des gros consommateurs attendus


@dataclass
class Battery:
    capacity_kwh: float  # capacité utile (100 % du SOC)
    soc: float  # %
    soc_min: float = 10.0
    soc_max: float = 100.0
    max_charge_w: float = 2400.0
    max_discharge_w: float = 2400.0
    grid_soc_max: float | None = None  # plafond de la charge réseau (SOC max de l'utilisateur)

    @property
    def grid_cap(self) -> float:
        cap = self.soc_max if self.grid_soc_max is None else min(self.soc_max, self.grid_soc_max)
        return max(self.soc_min, cap)

    @property
    def range_kwh(self) -> float:
        return max(0.0, self.capacity_kwh * (self.soc_max - self.soc_min) / 100)

    @property
    def energy_kwh(self) -> float:
        """Énergie au-dessus du SOC minimum."""
        e = self.capacity_kwh * (self.soc - self.soc_min) / 100
        return min(max(0.0, e), self.range_kwh)


@dataclass
class Settings:
    efficiency: float = 0.85  # rendement aller-retour
    wear_eur_kwh: float = 0.0  # usure par kWh restitué
    gain_threshold: float = 0.02  # €/kWh
    safety_margin: float = 0.10  # majoration du besoin des heures rentables
    import_limit_w: float = 9000.0  # soutirage maximal pendant la charge
    finish_advance_min: int = 30  # la charge doit finir avant la fin des HC


@dataclass
class Override:
    """Consigne imposée pour une nuit (service force_night)."""

    mode: str  # "charge" ou "idle"
    target_soc: float | None = None


@dataclass
class StepPlan:
    start: datetime
    mode: str
    soc: float  # SOC simulé en fin de pas
    price: float | None
    consumption_kwh: float
    solar_kwh: float
    charge_kwh: float = 0.0  # énergie prise au réseau pour la batterie
    discharge_kwh: float = 0.0  # énergie fournie à la maison par la batterie
    profitable: bool = False
    off_peak: bool = False
    overflow_kwh: float = 0.0  # surplus solaire qui ne rentre plus (batterie pleine)


@dataclass
class Plan:
    state: str
    reason: str
    window_start: datetime | None = None
    window_end: datetime | None = None
    cover_end: datetime | None = None  # fin de la période à couvrir
    charge_end: datetime | None = None
    price_gap: float | None = None  # meilleur écart HP − (HC ÷ rendement + usure), €/kWh
    reserve_soc: float | None = None  # SOC minimum relevé (E2) si appliqué
    soc_min: float | None = None  # SOC minimum utilisé par la simulation
    soc_max: float | None = None  # SOC maximum utilisé par la simulation
    charge_start: datetime | None = None
    target_soc: float | None = None
    energy_to_charge_kwh: float = 0.0  # énergie à stocker dans la batterie
    grid_energy_kwh: float = 0.0  # énergie prise au réseau pour la stocker
    peak_need_kwh: float = 0.0  # besoin des heures pleines rentables
    consumption_kwh: float = 0.0  # consommation prévue sur la période à couvrir
    solar_kwh: float = 0.0  # production prévue sur la période à couvrir
    forecast_gain_eur: float = 0.0
    may_not_finish: bool = False
    power_alert: bool = False
    capacity_short: bool = False
    steps: list[StepPlan] = field(default_factory=list)

    def mode_at(self, when: datetime) -> str | None:
        for sp in self.steps:
            if sp.start <= when < sp.start + _step_len(self.steps):
                return sp.mode
        return None


def _step_len(steps) -> timedelta:
    if len(steps) >= 2:
        return steps[1].start - steps[0].start
    return timedelta(minutes=15)


# ---------------------------------------------------------------- outils
def find_window(steps: list[Step]) -> tuple[int, int] | None:
    """Indices [début, fin) de la prochaine fenêtre creuse."""
    i = 0
    while i < len(steps) and not steps[i].off_peak:
        i += 1
    if i == len(steps):
        return None
    j = i
    while j < len(steps) and steps[j].off_peak:
        j += 1
    return i, j


def cover_range(steps: list[Step], window_end: int) -> tuple[int, int]:
    """Indices [début, fin) de la période à couvrir après la fenêtre."""
    k = window_end
    while k < len(steps) and not steps[k].off_peak:
        k += 1
    return window_end, k


def charge_cost(price_hc: float, s: Settings) -> float:
    """Coût d'un kWh restitué par la batterie après une charge au prix HC."""
    eff = min(max(s.efficiency, 0.3), 1.0)
    return price_hc / eff + s.wear_eur_kwh


def _simulate(
    steps: list[Step],
    idx: range,
    e0: float,
    e_range: float,
    profitable: list[bool],
    s: Settings,
    b: Battery,
    step_h: float,
) -> tuple[float, float]:
    """Simule la batterie sur les pas `idx`.

    Retourne (énergie minimale atteinte, énergie finale). L'énergie peut devenir
    négative : c'est ce qui permet de mesurer ce qui manque.
    """
    eta = math.sqrt(min(max(s.efficiency, 0.3), 1.0))
    e = e0
    lowest = e0
    max_out = b.max_discharge_w / 1000 * step_h
    max_in = b.max_charge_w / 1000 * step_h
    for k in idx:
        st = steps[k]
        net = st.consumption_kwh - st.solar_kwh
        if net < 0:
            stored = min(-net, max_in) * eta
            e = min(e + stored, e_range)
        elif profitable[k] and net > 0:
            need = net * (1 + s.safety_margin)
            delivered = min(need, max_out)
            e -= delivered / eta
        lowest = min(lowest, e)
    return lowest, e


def _needed_start_energy(
    steps, idx, e_range, profitable, s, b, step_h
) -> float:
    """Énergie minimale au début de `idx` pour ne jamais passer sous le SOC min."""
    lo, hi = 0.0, e_range
    lowest, _ = _simulate(steps, idx, hi, e_range, profitable, s, b, step_h)
    if lowest < 0:
        return e_range - lowest  # même pleine, la batterie ne suffit pas
    for _ in range(40):
        mid = (lo + hi) / 2
        lowest, _ = _simulate(steps, idx, mid, e_range, profitable, s, b, step_h)
        if lowest >= 0:
            hi = mid
        else:
            lo = mid
    return hi


# ---------------------------------------------------------------- plan
def compute_plan(
    steps: list[Step],
    battery: Battery,
    settings: Settings,
    override: Override | None = None,
) -> Plan:
    """Calcule le plan à partir de maintenant (steps[0] = pas en cours)."""
    if not steps or battery.capacity_kwh <= 0:
        return Plan(PLAN_MISSING_DATA, REASON_MISSING_DATA)
    step_h = (
        (steps[1].start - steps[0].start).total_seconds() / 3600 if len(steps) > 1 else 0.25
    )
    s, b = settings, battery
    e_range = b.range_kwh
    eta = math.sqrt(min(max(s.efficiency, 0.3), 1.0))

    win = find_window(steps)
    if win is None:
        plan = Plan(PLAN_NOTHING_TO_COVER, REASON_NO_OFF_PEAK)
        plan.steps = _modes_without_window(steps, b, s, step_h)
        return plan
    ws, we = win
    cs, ce = cover_range(steps, we)

    hc_prices = [steps[k].price for k in range(ws, we) if steps[k].price is not None]
    price_hc = sum(hc_prices) / len(hc_prices) if hc_prices else None
    if price_hc is None:
        return Plan(PLAN_MISSING_DATA, REASON_MISSING_DATA)
    cost = charge_cost(price_hc, s)

    # worth[k] : heure pleine qui vaut d'être couverte par une charge réseau.
    worth = [False] * len(steps)
    for k, st in enumerate(steps):
        if not st.off_peak and st.price is not None:
            worth[k] = st.price - cost > s.gain_threshold
    # La batterie rend ce qu'elle contient à toutes les heures pleines.
    any_peak = [not st.off_peak for st in steps]

    plan = Plan(PLAN_IDLE, REASON_ENOUGH_ENERGY)
    plan.soc_min, plan.soc_max = b.soc_min, b.soc_max
    gaps = [steps[k].price - cost for k in range(cs, ce) if steps[k].price is not None and not steps[k].off_peak]
    plan.price_gap = round(max(gaps), 4) if gaps else None
    plan.window_start = steps[ws].start
    plan.window_end = steps[we - 1].start + timedelta(hours=step_h)
    plan.cover_end = steps[ce - 1].start + timedelta(hours=step_h) if ce > cs else plan.window_end
    plan.consumption_kwh = sum(steps[k].consumption_kwh for k in range(cs, ce))
    plan.solar_kwh = sum(steps[k].solar_kwh for k in range(cs, ce))

    # Énergie en batterie au début de la fenêtre (ce soir elle sert encore).
    _, e_ws = _simulate(steps, range(0, ws), b.energy_kwh, e_range, any_peak, s, b, step_h)
    e_ws = max(0.0, e_ws)
    # Pendant la fenêtre, la batterie ne décharge pas mais stocke le solaire.
    no_discharge = [False] * len(steps)
    _, e_we_free = _simulate(steps, range(ws, we), e_ws, e_range, no_discharge, s, b, step_h)

    if cs == ce:
        plan.state, plan.reason = PLAN_NOTHING_TO_COVER, REASON_NO_PEAK_HOURS
    elif not any(worth[cs:ce]):
        plan.state, plan.reason = PLAN_NOT_PROFITABLE, REASON_GAIN_TOO_LOW
    plan.peak_need_kwh = sum(
        max(0.0, steps[k].consumption_kwh - steps[k].solar_kwh) * (1 + s.safety_margin)
        for k in range(cs, ce)
        if worth[k]
    )

    needed = 0.0
    if plan.state == PLAN_IDLE:
        needed = _needed_start_energy(steps, range(cs, ce), e_range, worth, s, b, step_h)
        if needed > e_range + 1e-6:
            # Capacité insuffisante : on garde l'énergie pour les heures les plus
            # chères en retirant les moins chères jusqu'à ce que ça tienne.
            plan.capacity_short = True
            order = sorted((k for k in range(cs, ce) if worth[k]), key=lambda k: steps[k].price)
            for k in order:
                worth[k] = False
                needed = _needed_start_energy(steps, range(cs, ce), e_range, worth, s, b, step_h)
                if needed <= e_range + 1e-6:
                    break
            needed = min(needed, e_range)

    e_grid_cap = max(0.0, b.capacity_kwh * (b.grid_cap - b.soc_min) / 100)
    to_store = max(0.0, min(needed - e_we_free, e_range - e_ws, e_grid_cap - e_ws))
    if override is not None:
        if override.mode == "idle":
            to_store = 0.0
            plan.reason = REASON_FORCED_IDLE
        elif override.mode == "charge":
            target = override.target_soc if override.target_soc is not None else b.grid_cap
            target = min(max(target, b.soc_min), b.grid_cap)
            e_target = b.capacity_kwh * (target - b.soc_min) / 100
            to_store = max(0.0, e_target - e_ws)
            plan.reason = REASON_FORCED_CHARGE

    if to_store >= MIN_CHARGE_KWH:
        plan.state = PLAN_CHARGE
        if override is None:
            plan.reason = REASON_CAPACITY_SHORT if plan.capacity_short else REASON_CHARGE_NEEDED
        plan.energy_to_charge_kwh = to_store
        plan.grid_energy_kwh = to_store / eta
        soc_ws = b.soc_min + e_ws / b.capacity_kwh * 100
        plan.target_soc = min(b.grid_cap, math.ceil(soc_ws + to_store / b.capacity_kwh * 100))
        _schedule_charge(plan, steps, ws, we, b, s, step_h)
    elif plan.state == PLAN_IDLE and override is None:
        plan.reason = REASON_SOLAR_COVERS if plan.peak_need_kwh < 0.05 else REASON_ENOUGH_ENERGY
    if override is not None and plan.state != PLAN_CHARGE:
        plan.state = PLAN_IDLE

    plan.power_alert = any(
        steps[k].consumption_kwh / step_h * 1000 + steps[k].loads_w > s.import_limit_w
        for k in range(ws, we)
    )
    reserve = plan.state == PLAN_CHARGE or plan.capacity_short
    plan.steps = _build_steps(plan, steps, worth, reserve, (cs, ce), ws, we, b, s, step_h)
    plan.forecast_gain_eur = _forecast_gain(plan, price_hc, s)
    return plan


def _schedule_charge(plan: Plan, steps, ws, we, b: Battery, s: Settings, step_h: float) -> None:
    """Place la charge le plus tard possible, en finissant avant la fin des HC."""
    advance_steps = int(round(s.finish_advance_min / 60 / step_h))
    last = max(ws, we - advance_steps)  # premier pas exclu
    remaining = plan.grid_energy_kwh
    k = last
    while remaining > 1e-6 and k > ws:
        k -= 1
        st = steps[k]
        base_w = st.consumption_kwh / step_h * 1000
        avail_w = max(0.0, min(b.max_charge_w, s.import_limit_w - base_w - st.loads_w))
        remaining -= avail_w / 1000 * step_h
    if remaining > 1e-6:
        # Pas assez de temps avant l'avance demandée : on prend aussi la marge.
        k2 = last
        while remaining > 1e-6 and k2 < we:
            st = steps[k2]
            base_w = st.consumption_kwh / step_h * 1000
            avail_w = max(0.0, min(b.max_charge_w, s.import_limit_w - base_w - st.loads_w))
            remaining -= avail_w / 1000 * step_h
            k2 += 1
        plan.may_not_finish = remaining > 1e-6
        plan.charge_end = steps[min(k2, len(steps)) - 1].start + timedelta(hours=step_h)
    else:
        plan.charge_end = steps[last - 1].start + timedelta(hours=step_h)
    plan.charge_start = steps[k].start


def _build_steps(plan, steps, worth, reserve, cover, ws, we, b, s, step_h) -> list[StepPlan]:
    eta = math.sqrt(min(max(s.efficiency, 0.3), 1.0))
    e_range = b.range_kwh
    # Énergie au-dessus du SOC minimum ; négative si la batterie est déjà en dessous
    # (réserve relevée) : elle ne décharge alors plus, mais peut encore stocker.
    e = min(b.capacity_kwh * (b.soc - b.soc_min) / 100, e_range)
    target_e = (
        b.capacity_kwh * (plan.target_soc - b.soc_min) / 100
        if plan.target_soc is not None
        else None
    )
    out: list[StepPlan] = []
    for k, st in enumerate(steps):
        net = st.consumption_kwh - st.solar_kwh
        charge = 0.0
        if ws <= k < we:
            if (
                plan.state == PLAN_CHARGE
                and plan.charge_start is not None
                and st.start >= plan.charge_start
            ):
                mode = MODE_GRID_CHARGE
                if target_e is not None and e < target_e:
                    base_w = st.consumption_kwh / step_h * 1000
                    avail_w = max(0.0, min(b.max_charge_w, s.import_limit_w - base_w - st.loads_w))
                    charge = min(avail_w / 1000 * step_h, (target_e - e) / eta)
            else:
                mode = MODE_SMART_CHARGE if st.solar_kwh > SOLAR_MIN_KWH else MODE_OFF
        elif st.off_peak:
            mode = MODE_SMART_CHARGE if st.solar_kwh > SOLAR_MIN_KWH else MODE_OFF
        elif reserve and cover[0] <= k < cover[1] and not worth[k]:
            # Énergie réservée aux heures les plus chères de la période
            mode = MODE_SMART_CHARGE
        else:
            mode = MODE_SMART
        # SOC simulé
        if charge > 0:
            e = min(e + charge * eta, e_range)
        overflow = 0.0
        if net < 0 and mode != MODE_OFF:
            stored = min(-net, b.max_charge_w / 1000 * step_h) * eta
            room = max(0.0, e_range - e)
            if stored > room:
                overflow = (stored - room) / eta
            e = min(e + stored, e_range)
        delivered = 0.0
        if net > 0 and mode == MODE_SMART:
            out_kwh = min(net, b.max_discharge_w / 1000 * step_h, max(0.0, e) * eta)
            e = e - out_kwh / eta
            delivered = out_kwh
        soc = b.soc_min + e / b.capacity_kwh * 100 if b.capacity_kwh else 0.0
        out.append(
            StepPlan(
                start=st.start,
                mode=mode,
                soc=round(soc, 1),
                price=st.price,
                consumption_kwh=st.consumption_kwh,
                solar_kwh=st.solar_kwh,
                charge_kwh=round(charge, 4),
                discharge_kwh=round(delivered, 4),
                overflow_kwh=round(overflow, 4),
                profitable=worth[k],
                off_peak=st.off_peak,
            )
        )
    return out


def _modes_without_window(steps, b, s, step_h) -> list[StepPlan]:
    """Aucune heure creuse à l'horizon (offre Base) : on stocke le solaire et on le rend."""
    out = []
    for st in steps:
        mode = MODE_SMART
        out.append(
            StepPlan(
                st.start, mode, b.soc, st.price, st.consumption_kwh, st.solar_kwh, off_peak=st.off_peak
            )
        )
    return out


def _forecast_gain(plan: Plan, price_hc: float, s: Settings) -> float:
    """Gain estimé jusqu'à la fin de la période couverte : énergie rendue par la
    batterie, valorisée au prix du moment, moins le coût de la charge réseau."""
    gain = sum(
        sp.discharge_kwh * (sp.price - s.wear_eur_kwh)
        for sp in plan.steps
        if sp.price is not None and (plan.cover_end is None or sp.start < plan.cover_end)
    )
    gain -= plan.grid_energy_kwh * price_hc
    return round(gain, 2)


# ---------------------------------------------------------------- SOC min / max (E2)
OVERFLOW_MIN_KWH = 0.2  # surplus solaire prévu au-delà duquel on passe le SOC max à 100 %


def compute_plan_with_reserve(
    steps: list[Step],
    battery: Battery,
    settings: Settings,
    override: Override | None = None,
    reserve_soc: float | None = None,
) -> Plan:
    """Plan complet avec la réserve de SOC (E2).

    Si le plan est non rentable et que la réserve dépasse le SOC minimum de
    l'utilisateur, la simulation est refaite avec la réserve : seule l'énergie
    au-dessus d'elle peut alors être rendue aux heures pleines.
    """
    plan = compute_plan(steps, battery, settings, override)
    if (
        reserve_soc is not None
        and plan.state == PLAN_NOT_PROFITABLE
        and reserve_soc > battery.soc_min
    ):
        raised = replace(battery, soc_min=min(reserve_soc, battery.soc_max))
        plan = compute_plan(steps, raised, settings, override)
        plan.reserve_soc = raised.soc_min
    return plan


def daylight_overflow(plan: Plan, solar_min: float = SOLAR_MIN_KWH) -> float:
    """Surplus solaire prévu qui ne rentrera pas dans la batterie, sur la journée
    solaire en cours (ou la prochaine, s'il fait nuit)."""
    total = 0.0
    seen_sun = False
    for sp in plan.steps:
        sunny = sp.solar_kwh > solar_min
        if sunny:
            seen_sun = True
            total += sp.overflow_kwh
        elif seen_sun:
            break
    return round(total, 3)


def wants_full_charge(plan: Plan) -> bool:
    """Règle D5 : SOC max à 100 % quand le soleil remplira la batterie et qu'il
    resterait encore du surplus à injecter."""
    return daylight_overflow(plan) >= OVERFLOW_MIN_KWH


# ---------------------------------------------------------------- puissance
def import_limit_w(
    subscribed_kva: float, margin: float, three_phase: bool = False
) -> float:
    """Soutirage maximal autorisé pendant la charge (marge d'au moins 10 %)."""
    margin = max(0.10, margin)
    limit = subscribed_kva * 1000 * (1 - margin)
    if three_phase:
        limit /= 3
    return round(limit)
