"""Mise en forme des données sur la grille de pas de temps (Python pur)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Segment:
    start: datetime
    end: datetime
    price: float | None
    off_peak: bool
    period: str | None
    color: str | None
    special_confirmed: bool = True


def parse_segments(response: dict) -> list[Segment]:
    """Tranches du service tarifs_electricite.previsions (contrat, interface 1)."""
    out = []
    for s in response.get("segments") or []:
        try:
            start = datetime.fromisoformat(s["debut"])
            end = datetime.fromisoformat(s["fin"])
        except (KeyError, TypeError, ValueError):
            continue
        price = s.get("prix")
        out.append(
            Segment(
                start=start,
                end=end,
                price=float(price) if price is not None else None,
                off_peak=bool(s.get("heures_creuses")),
                period=(s.get("periode") or "").lower() or None,
                color=s.get("couleur"),
                special_confirmed=s.get("jour_special_confirme", True) is not False,
            )
        )
    return out


def fill_unknown_prices(
    segments: list[Segment], grid: dict | None, tempo_assumption: str
) -> int:
    """Complète les prix inconnus. Retourne le nombre de tranches complétées.

    1. Tempo : prix de la couleur supposée dans la grille (attribut `grille` de
       prix_actuel, hors contrat, lu au mieux) ;
    2. sinon : dernier prix connu pour la même période ;
    3. sinon : le prix connu le plus élevé (hypothèse prudente).
    """
    by_period: dict[str, float] = {}
    for s in segments:
        if s.price is not None and s.period:
            by_period[s.period] = s.price
    known = [s.price for s in segments if s.price is not None]
    highest = max(known) if known else None
    tempo_prices = _tempo_prices(grid, tempo_assumption)
    filled = 0
    for s in segments:
        if s.price is not None:
            continue
        price = None
        if tempo_prices and s.period in tempo_prices:
            price = tempo_prices[s.period]
        if price is None and s.period in by_period:
            price = by_period[s.period]
        if price is None:
            price = highest
        if price is not None:
            s.price = price
            filled += 1
    return filled


def _tempo_prices(grid: dict | None, color: str) -> dict[str, float]:
    if not isinstance(grid, dict):
        return {}
    for line in grid.get("lignes") or []:
        if str(line.get("libelle", "")).lower() == color:
            prices = line.get("prix") or {}
            return {str(k).lower(): float(v) for k, v in prices.items() if v is not None}
    return {}


def step_starts(now: datetime, hours: int, minutes: int) -> list[datetime]:
    first = now.replace(second=0, microsecond=0)
    first -= timedelta(minutes=first.minute % minutes)
    return [first + timedelta(minutes=minutes * i) for i in range(hours * 60 // minutes)]


def at(segments: list[Segment], when: datetime) -> Segment | None:
    for s in segments:
        if s.start <= when < s.end:
            return s
    return None


def spread(
    periods: list[tuple[datetime, datetime, float]], starts: list[datetime], step: timedelta
) -> list[float]:
    """Répartit des énergies par période (début, fin, kWh) sur les pas, au prorata du temps."""
    out = [0.0] * len(starts)
    if not starts:
        return out
    for p_start, p_end, kwh in periods:
        span = (p_end - p_start).total_seconds()
        if span <= 0 or not kwh:
            continue
        for i, st in enumerate(starts):
            en = st + step
            overlap = (min(en, p_end) - max(st, p_start)).total_seconds()
            if overlap > 0:
                out[i] += kwh * overlap / span
    return out


def wh_hours_to_periods(wh_hours: dict) -> list[tuple[datetime, datetime, float]]:
    """{début ISO: Wh} (plateforme de prévision du tableau Énergie) → périodes en kWh.

    La durée d'une période va jusqu'au début suivant (1 h pour la dernière, ou
    l'écart habituel s'il est plus court).
    """
    items = []
    for k, v in wh_hours.items():
        try:
            ts = k if isinstance(k, datetime) else datetime.fromisoformat(str(k))
            items.append((ts, float(v)))
        except (TypeError, ValueError):
            continue
    items.sort()
    periods = []
    default = timedelta(hours=1)
    if len(items) >= 2:
        default = min(default, items[1][0] - items[0][0])
    for i, (ts, wh) in enumerate(items):
        end = items[i + 1][0] if i + 1 < len(items) else ts + default
        if end - ts > timedelta(hours=1):
            end = ts + default  # trou (nuit) : la période ne déborde pas
        periods.append((ts, end, wh / 1000))
    return periods


def parse_window(text: str | None) -> tuple[int, int] | None:
    """« 23:00-02:00 » → (minute de début, minute de fin)."""
    if not text:
        return None
    try:
        a, b = text.replace(" ", "").split("-")
        ha, ma = (int(x) for x in a.split(":"))
        hb, mb = (int(x) for x in b.split(":"))
    except (ValueError, AttributeError):
        return None
    if not (0 <= ha < 24 and 0 <= hb <= 24 and 0 <= ma < 60 and 0 <= mb < 60):
        return None
    return ha * 60 + ma, hb * 60 + mb


def in_window(when: datetime, window: tuple[int, int] | None) -> bool:
    if window is None:
        return False
    m = when.hour * 60 + when.minute
    a, b = window
    if a == b:
        return True
    return a <= m < b if a < b else (m >= a or m < b)
