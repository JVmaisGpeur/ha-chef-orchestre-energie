"""Plan du jour et plan du lendemain (v1.4.0, ex-1.3.7, A1 à A3).

Module pur : découpe les pas du plan en deux journées selon l'heure de début choisie
par l'utilisateur, et résume chacune pour les cartes. Le calcul du plan ne change pas.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

DAY_STARTS = ["off_peak_end", "off_peak_start", "midnight", "fixed"]
DEFAULT_DAY_START = "off_peak_end"
DEFAULT_DAY_TIME = time(6, 0)
STEP = timedelta(minutes=15)


def _runs(steps) -> list[tuple[int, int]]:
    """Plages [début, fin) de pas consécutifs en heures creuses."""
    out, i = [], 0
    while i < len(steps):
        if steps[i].off_peak:
            j = i
            while j < len(steps) and steps[j].off_peak:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def night_range(steps) -> tuple[time, time] | None:
    """Heures de début et de fin de la plage creuse de nuit (celle qui couvre 03:00).

    Avec plusieurs plages (12:30 → 14:30 et 23:30 → 07:30), c'est celle de la nuit ; une
    plage de plus de 24 h (week-end en heures creuses) ne sert qu'à défaut d'une autre.
    None : aucune heure creuse (offre Base).
    """
    best = fallback = None
    for i, j in _runs(steps):
        if not any(steps[k].start.hour == 3 for k in range(i, j)):
            continue
        start = steps[i].start
        end = steps[j - 1].start + STEP
        rng = (start.timetz().replace(tzinfo=None), end.timetz().replace(tzinfo=None))
        # une plage tronquée par le début des pas ne dit pas quand elle commence
        if i == 0 or j == len(steps):
            fallback = fallback or rng
            continue
        if end - start <= timedelta(hours=24):
            best = rng
            break
        fallback = fallback or rng
    return best or fallback


def boundary(steps, choice: str, fixed: time | None = None) -> time:
    """Heure de début d'une journée du plan (A2)."""
    if choice == "midnight":
        return time(0, 0)
    if choice == "fixed":
        return fixed or DEFAULT_DAY_TIME
    rng = night_range(steps)
    if rng is None:  # offre Base : de minuit à minuit
        return time(0, 0)
    return rng[1] if choice == "off_peak_end" else rng[0]


def day_starts(now: datetime, at: time) -> tuple[datetime, datetime, datetime]:
    """Début du jour en cours, du lendemain et fin du lendemain (heure locale de `now`)."""
    tz = now.tzinfo
    start = datetime.combine(now.date(), at, tzinfo=tz)
    if start > now:
        start = datetime.combine(now.date() - timedelta(days=1), at, tzinfo=tz)
    nxt = datetime.combine(start.date() + timedelta(days=1), at, tzinfo=tz)
    end = datetime.combine(start.date() + timedelta(days=2), at, tzinfo=tz)
    return start, nxt, end


def _iso(t: datetime | None) -> str | None:
    return t.isoformat() if t else None


def summarize(plan, start: datetime, end: datetime, forecast: bool) -> dict[str, Any]:
    """Résumé d'une journée du plan (A3, attribut `days`)."""
    steps = [sp for sp in plan.steps if start <= sp.start < end]
    out: dict[str, Any] = {"start": _iso(start), "end": _iso(end), "forecast": forecast}
    if not steps:
        out["empty"] = True
        return out
    last_end = steps[-1].start + STEP
    out["truncated_at"] = _iso(last_end) if last_end < end else None
    socs = [sp.soc for sp in steps]
    out["soc_start"], out["soc_min"], out["soc_end"] = socs[0], min(socs), socs[-1]
    out["solar_kwh"] = round(sum(sp.solar_kwh for sp in steps), 2)
    out["consumption_kwh"] = round(sum(sp.consumption_kwh for sp in steps), 2)
    charging = [sp for sp in steps if sp.charge_kwh > 0]
    out["charge_kwh"] = round(sum(sp.charge_kwh for sp in charging), 2)
    out["charge_start"] = _iso(charging[0].start) if charging else None
    out["charge_end"] = _iso(charging[-1].start + STEP) if charging else None
    if charging and all(sp.price is not None for sp in charging):
        out["cost"] = round(sum(sp.charge_kwh * sp.price for sp in charging), 2)
    else:
        out["cost"] = 0.0 if not charging else None
    # La nuit décidée par le plan est-elle dans cette journée ?
    ws, we = plan.window_start, plan.window_end
    decided = ws is not None and we is not None and ws < end and we > start
    out["night_decided"] = decided
    out["night_state"] = plan.state if decided else None
    out["target_soc"] = plan.target_soc if decided else None
    rf, ru = getattr(plan, "reserve_from", None), getattr(plan, "reserve_until", None)
    in_day = decided and rf is not None and start <= rf < end
    out["reserve_soc"] = plan.reserve_soc if in_day else None
    out["reserve_from"] = _iso(rf) if in_day else None
    out["reserve_until"] = _iso(ru) if in_day else None
    floors = [sp.floor_soc for sp in steps if sp.floor_soc is not None and sp.mode == "smart"]
    out["night_floor_soc"] = min(floors) if floors else None
    out["modes"] = [[_iso(sp.start), sp.mode] for sp in _changes(steps)]
    return out


def _changes(steps):
    """Pas où le mode change : de quoi dessiner la frise sans les 96 pas."""
    out, prev = [], None
    for sp in steps:
        if sp.mode != prev:
            out.append(sp)
            prev = sp.mode
    return out


def days(plan, now: datetime, choice: str, fixed: time | None = None) -> tuple[dict, list[dict]]:
    """(`day_start`, `days`) pour l'attribut du plan de la nuit."""
    at = boundary(plan.steps, choice, fixed)
    start, nxt, end = day_starts(now, at)
    info = {"choice": choice, "time": at.strftime("%H:%M")}
    return info, [summarize(plan, start, nxt, False), summarize(plan, nxt, end, True)]
