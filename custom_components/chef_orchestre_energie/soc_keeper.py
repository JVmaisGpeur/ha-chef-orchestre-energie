"""SOC minimum et maximum de chaque batterie (E2, Python pur).

Le Chef d'orchestre relève le SOC minimum (réserve) quand le plan est non
rentable, et passe le SOC maximum à 100 % quand le soleil remplira la batterie.
Il ne perd jamais le réglage de l'utilisateur :

- tant qu'il n'a rien modifié sur une entité, la valeur lue EST le réglage de
  l'utilisateur, et elle est mémorisée telle quelle ;
- dès qu'il a écrit une valeur, il la retient ; si la valeur lue diffère ensuite,
  c'est que l'utilisateur l'a changée : elle devient le nouveau réglage mémorisé,
  et le Chef d'orchestre n'y retouche qu'au calcul suivant ;
- il remet le réglage de l'utilisateur quand le pilotage est coupé ou l'intégration
  déchargée.

Zendure Local écrit ces réglages en mémoire flash : une écriture n'a lieu que si
la valeur change, et jamais plus d'une fois par période `min_interval` (sauf pour
rendre son réglage à l'utilisateur).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

TOLERANCE = 0.5  # %


@dataclass
class Target:
    entity_id: str
    kind: str  # "min" ou "max"
    current: float | None
    lo: float = 0.0  # bornes de l'entité (min_soc : 0-50, soc_set : 70-100)
    hi: float = 100.0
    soc: float | None = None  # niveau de charge de la batterie (R1 : réserve plafonnée au niveau courant)


class SocKeeper:
    def __init__(self, data: dict | None = None, min_interval: timedelta = timedelta(minutes=30)) -> None:
        data = data or {}
        self.memo: dict[str, float] = dict(data.get("memo", {}))
        self.applied: dict[str, float] = dict(data.get("applied", {}))
        self.last_write: dict[str, str] = dict(data.get("last_write", {}))
        self.hold: set[str] = set(data.get("hold", []))
        self.min_interval = min_interval

    def dump(self) -> dict:
        return {
            "memo": self.memo,
            "applied": self.applied,
            "last_write": self.last_write,
            "hold": sorted(self.hold),
        }

    def new_plan(self) -> None:
        """Un nouveau calcul : les réglages changés par l'utilisateur peuvent être repris."""
        self.hold.clear()

    def user_value(self, t: Target) -> float | None:
        """Réglage de l'utilisateur (mémorisé, ou lu s'il n'a jamais été modifié)."""
        self._observe(t)
        return self.memo.get(t.entity_id)

    def _observe(self, t: Target) -> None:
        if t.current is None:
            return
        eid = t.entity_id
        if eid not in self.applied:
            self.memo[eid] = t.current
        elif abs(t.current - self.applied[eid]) > TOLERANCE:
            # L'utilisateur a changé la valeur pendant que le Chef d'orchestre la tenait
            self.memo[eid] = t.current
            del self.applied[eid]
            self.hold.add(eid)

    def writes(
        self,
        targets: list[Target],
        now: datetime,
        reserve: float | None,
        full_charge: bool,
    ) -> list[tuple[str, float]]:
        """Écritures à faire pour appliquer la réserve et la règle du SOC max.

        `reserve` : réserve à appliquer maintenant (R1 : seulement pendant les heures
        creuses d'une nuit non rentable, None sinon). Une batterie déjà sous la
        réserve garde son niveau : la réserve l'empêche de descendre, sans la faire
        charger. Une fois posée, la valeur ne bouge plus jusqu'à la levée : une pose
        et une levée par nuit.
        """
        out: list[tuple[str, float]] = []
        for t in targets:
            self._observe(t)
            eid = t.entity_id
            user = self.memo.get(eid)
            if t.current is None or user is None or eid in self.hold:
                continue
            if t.kind == "min":
                if reserve is None:
                    wanted = user
                elif eid in self.applied:
                    wanted = self.applied[eid]  # réserve déjà posée cette nuit
                else:
                    level = reserve if t.soc is None else min(reserve, math.floor(t.soc))
                    wanted = max(user, level)
            else:
                wanted = 100.0 if full_charge else user
            wanted = min(max(wanted, t.lo), t.hi)
            if abs(t.current - wanted) <= TOLERANCE:
                if abs(wanted - user) <= TOLERANCE:
                    self.applied.pop(eid, None)
                continue
            restoring = abs(wanted - user) <= TOLERANCE
            last = self.last_write.get(eid)
            if not restoring and last and now - datetime.fromisoformat(last) < self.min_interval:
                continue
            out.append((eid, wanted))
            self.last_write[eid] = now.isoformat()
            if restoring:
                self.applied.pop(eid, None)
            else:
                self.applied[eid] = wanted
        return out

    def restore_all(self) -> list[tuple[str, float]]:
        """Rend à chaque batterie le réglage de l'utilisateur."""
        out = [(eid, self.memo[eid]) for eid in self.applied if eid in self.memo]
        self.applied.clear()
        self.hold.clear()
        return out

    @property
    def active(self) -> bool:
        return bool(self.applied)
