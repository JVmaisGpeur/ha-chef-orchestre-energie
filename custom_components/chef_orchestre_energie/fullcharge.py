"""Charge complète et calibration automatique des batteries (N3, pur Python).

D'après le support Zendure, une batterie peut lancer seule une calibration après
environ 30 jours sans charge à 100 %. Une charge complète de temps en temps suffit
en général à l'éviter : ce module compte les jours depuis la dernière charge
complète de chaque batterie et décide quand en programmer une.
"""

from __future__ import annotations

from datetime import datetime, timedelta

FULL_SOC = 99.5  # % : seuil retenu pour « chargée à 100 % »
CALIBRATION_DAYS = 30
LATE_MARGIN_DAYS = 3  # à J-3 on charge même la veille d'un jour cher

ACTION_SUN = "sun"  # SOC max à 100 % pour la journée, sans réseau
ACTION_TONIGHT = "tonight"  # charge réseau jusqu'à 100 % pendant les heures creuses
ACTION_NOW = "now"  # charge immédiate jusqu'à 100 %

REQUESTS = ("auto", "next_sun", "tonight", "now", "skip")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class FullChargeTracker:
    """Dates des dernières charges complètes, demande en cours et décision."""

    def __init__(self, data: dict | None = None) -> None:
        data = data or {}
        self.last_full: dict[str, str] = dict(data.get("last_full", {}))
        self.estimated: set[str] = set(data.get("estimated", []))
        self.request: str = data.get("request", "auto") if data.get("request") in REQUESTS else "auto"
        self.request_units: list[str] = list(data.get("request_units", []))

    def dump(self) -> dict:
        return {
            "last_full": self.last_full,
            "estimated": sorted(self.estimated),
            "request": self.request,
            "request_units": self.request_units,
        }

    # ------------------------------------------------------------ suivi
    def start(self, unit: str, when: datetime, *, estimated: bool) -> None:
        """Point de départ du compteur (historique ou jour de l'installation)."""
        if unit not in self.last_full:
            self.last_full[unit] = when.isoformat()
            if estimated:
                self.estimated.add(unit)

    def observe(self, unit: str, soc: float | None, now: datetime) -> bool:
        """Note une charge complète. Retourne True quand la demande en cours est finie."""
        if soc is None:
            return False
        self.start(unit, now, estimated=True)
        if soc < FULL_SOC:
            return False
        self.last_full[unit] = now.isoformat()
        self.estimated.discard(unit)
        if self.request != "auto" and unit in self.request_units:
            self.request_units = [u for u in self.request_units if u != unit]
            if not self.request_units:
                self.request = "auto"
                return True
        return False

    def last(self, unit: str) -> datetime | None:
        return _parse(self.last_full.get(unit))

    def days(self, unit: str, now: datetime) -> float | None:
        last = self.last(unit)
        if last is None:
            return None
        return max(0.0, (now - last).total_seconds() / 86400)

    def calibration_due(self, unit: str) -> datetime | None:
        last = self.last(unit)
        return last + timedelta(days=CALIBRATION_DAYS) if last else None

    def due_units(self, units: list[str], now: datetime, threshold: float) -> list[str]:
        return [u for u in units if (self.days(u, now) or 0) >= threshold]

    def max_days(self, units: list[str], now: datetime) -> float | None:
        values = [d for d in (self.days(u, now) for u in units) if d is not None]
        return max(values) if values else None

    # ------------------------------------------------------------ commande
    def set_request(self, request: str, units: list[str], now: datetime, socs: dict[str, float | None]) -> None:
        """Demande manuelle (carte, entité, service). « auto » annule la demande."""
        if request not in REQUESTS:
            raise ValueError(request)
        self.request = request
        if request in ("auto", "skip"):
            self.request_units = list(units) if request == "skip" else []
            return
        # Seules les batteries qui ne sont pas déjà pleines chargent
        self.request_units = [u for u in units if (socs.get(u) if socs.get(u) is not None else 0) < FULL_SOC]
        if not self.request_units:
            self.request = "auto"

    def decide(
        self,
        units: list[str],
        now: datetime,
        *,
        threshold: float,
        auto_enabled: bool,
        sunny: bool,
        tonight_ok: bool,
    ) -> tuple[str | None, list[str], bool]:
        """Action à mener, batteries concernées, et alerte « 30e jour sans moment favorable ».

        sunny : la prévision permet d'atteindre 100 % sans réseau ;
        tonight_ok : la nuit qui vient n'est pas la veille d'un jour cher.
        """
        if self.request == "now":
            return ACTION_NOW, self.request_units, False
        if self.request == "tonight":
            return ACTION_TONIGHT, self.request_units, False
        if self.request == "next_sun":
            return (ACTION_SUN if sunny else None), self.request_units, False
        if self.request == "skip":
            # Plus rien jusqu'à la prochaine charge complète (observe() revient en auto)
            return None, [], False
        due = self.due_units(units, now, threshold)
        if not auto_enabled or not due:
            return None, [], False
        late = (self.max_days(due, now) or 0) >= CALIBRATION_DAYS - LATE_MARGIN_DAYS
        if sunny:
            return ACTION_SUN, due, False
        if tonight_ok or late:
            return ACTION_TONIGHT, due, False
        return None, due, late
