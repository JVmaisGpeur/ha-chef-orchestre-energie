"""Profil de consommation appris (Python pur, sans Home Assistant).

La consommation de la maison est apprise heure par heure, séparément pour trois
types de jour : semaine, samedi, dimanche et jours fériés. La valeur retenue
pour une heure est la médiane des dernières semaines, qui résiste mieux qu'une
moyenne aux journées exceptionnelles.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median

WEEKDAY = "weekday"
SATURDAY = "saturday"
SUNDAY = "sunday"  # dimanche et jours fériés
DAY_TYPES = (WEEKDAY, SATURDAY, SUNDAY)

RELIABILITY_LOW = "low"
RELIABILITY_MEDIUM = "medium"
RELIABILITY_GOOD = "good"
RELIABILITIES = [RELIABILITY_LOW, RELIABILITY_MEDIUM, RELIABILITY_GOOD]

# Forme type d'une journée de maison (part de la consommation par heure, somme = 1).
# Sert tant qu'il n'y a pas assez d'historique.
DEFAULT_SHAPE = [
    0.030, 0.026, 0.025, 0.025, 0.026, 0.030,  # 0 h - 5 h
    0.040, 0.048, 0.045, 0.040, 0.038, 0.042,  # 6 h - 11 h
    0.048, 0.044, 0.038, 0.036, 0.040, 0.050,  # 12 h - 17 h
    0.065, 0.070, 0.065, 0.055, 0.045, 0.039,  # 18 h - 23 h
]
_total = sum(DEFAULT_SHAPE)
DEFAULT_SHAPE = [v / _total for v in DEFAULT_SHAPE]


def easter(year: int) -> date:
    """Dimanche de Pâques (algorithme de Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def french_holidays(year: int) -> set[date]:
    p = easter(year)
    return {
        date(year, 1, 1),
        p + timedelta(days=1),  # lundi de Pâques
        date(year, 5, 1),
        date(year, 5, 8),
        p + timedelta(days=39),  # Ascension
        p + timedelta(days=50),  # lundi de Pentecôte
        date(year, 7, 14),
        date(year, 8, 15),
        date(year, 11, 1),
        date(year, 11, 11),
        date(year, 12, 25),
    }


def day_type(d: date) -> str:
    if d in french_holidays(d.year) or d.weekday() == 6:
        return SUNDAY
    if d.weekday() == 5:
        return SATURDAY
    return WEEKDAY


class ConsumptionProfile:
    """Consommation prévue (kWh) pour chaque heure, selon le type de jour."""

    def __init__(self, daily_kwh_fallback: float = 10.0) -> None:
        self.daily_kwh_fallback = daily_kwh_fallback
        self.hourly: dict[str, list[float | None]] = {t: [None] * 24 for t in DAY_TYPES}
        self.days_of_data = 0

    def learn(self, samples: list[tuple[datetime, float]], weeks: int = 4) -> None:
        """Apprend à partir de valeurs horaires (début d'heure en heure locale, kWh).

        Seules les `weeks` dernières semaines sont gardées. Les valeurs négatives
        ou aberrantes (plus de 36 kWh en une heure) sont ignorées.
        """
        if not samples:
            self.days_of_data = 0
            self.hourly = {t: [None] * 24 for t in DAY_TYPES}
            return
        last = max(ts for ts, _ in samples)
        since = last - timedelta(weeks=weeks)
        buckets: dict[tuple[str, int], list[float]] = defaultdict(list)
        days: set[date] = set()
        for ts, kwh in samples:
            if ts <= since or kwh is None or kwh < 0 or kwh > 36:
                continue
            buckets[(day_type(ts.date()), ts.hour)].append(kwh)
            days.add(ts.date())
        self.days_of_data = len(days)
        self.hourly = {t: [None] * 24 for t in DAY_TYPES}
        for (t, h), values in buckets.items():
            self.hourly[t][h] = median(values)

    @property
    def reliability(self) -> str:
        if self.days_of_data < 7:
            return RELIABILITY_LOW
        if self.days_of_data < 21:
            return RELIABILITY_MEDIUM
        return RELIABILITY_GOOD

    def hour_kwh(self, when: datetime) -> float:
        """Consommation prévue pour l'heure qui contient `when`."""
        fallback = self.daily_kwh_fallback * DEFAULT_SHAPE[when.hour]
        if self.days_of_data < 7:
            return fallback
        t = day_type(when.date())
        v = self.hourly[t][when.hour]
        if v is None:
            # Type de jour pas encore vu : on prend la semaine, sinon la forme type
            v = self.hourly[WEEKDAY][when.hour]
        return fallback if v is None else v

    def day_kwh(self, d: date, tz) -> float:
        start = datetime(d.year, d.month, d.day, tzinfo=tz)
        return sum(self.hour_kwh(start + timedelta(hours=h)) for h in range(24))


def hourly_changes(points: list[tuple[datetime, float]]) -> list[tuple[datetime, float]]:
    """Transforme des relevés cumulés (début d'heure, total kWh) en consommations horaires.

    Une remise à zéro du compteur (total qui baisse) est ignorée.
    """
    out = []
    prev = None
    for ts, total in sorted(points):
        if prev is not None and total is not None and prev[1] is not None:
            diff = total - prev[1]
            if diff >= 0:
                out.append((prev[0], round(diff, 6)))
        prev = (ts, total)
    return out


def correction_factor(pairs: list[tuple[float, float]]) -> float:
    """Rapport production réelle / prévue sur les jours fournis, borné entre 0,5 et 1,5.

    `pairs` = (prévu kWh, réel kWh). Les jours où l'on prévoyait moins de 0,5 kWh
    sont ignorés.
    """
    kept = [(f, r) for f, r in pairs if f is not None and r is not None and f >= 0.5]
    if len(kept) < 3:
        return 1.0
    total_f = sum(f for f, _ in kept)
    total_r = sum(r for _, r in kept)
    if total_f <= 0:
        return 1.0
    return round(min(1.5, max(0.5, total_r / total_f)), 3)


def measured_efficiency(charged_kwh: float, discharged_kwh: float, default: float) -> float:
    """Rendement aller-retour mesuré, si assez d'énergie a transité (≥ 5 kWh)."""
    if charged_kwh is None or discharged_kwh is None or charged_kwh < 5:
        return default
    return round(min(0.98, max(0.6, discharged_kwh / charged_kwh)), 3)
