"""SOC minimum et maximum de chaque batterie (E2, Python pur).

Le Chef d'orchestre relève le SOC minimum (réserve) pendant les heures creuses
d'une nuit non rentable, et passe le SOC maximum à 100 % quand le soleil remplira
la batterie. Il ne perd jamais le réglage de l'utilisateur :

- tant qu'il n'a rien modifié sur une entité, la valeur lue EST le réglage de
  l'utilisateur, et elle est mémorisée telle quelle ;
- dès qu'il a écrit une valeur, il la retient (`applied`) ; si la valeur lue diffère
  ensuite, c'est que l'utilisateur l'a changée : elle devient le nouveau réglage
  mémorisé, et le Chef d'orchestre n'y retouche qu'au calcul suivant ;
- il remet le réglage de l'utilisateur quand la réserve est levée, quand le
  pilotage est coupé ou l'intégration déchargée.

R2 (v1.3.6) : la restitution se fait en deux temps. La valeur rendue est notée
« en attente » (`pending`) et la valeur posée reste connue (`applied`) jusqu'à ce
que la batterie affiche la valeur rendue. Tant que la batterie affiche encore la
valeur posée (Zendure lent, redémarrage, écriture refusée), cette valeur n'est
jamais prise pour le réglage de l'utilisateur ; elle est renvoyée dans la limite
des écritures. Garde-fou : une valeur lue égale à la réserve configurée n'est pas
mémorisée si une réserve a été posée sur cette batterie depuis le dernier réglage
connu (`reserved`) ; elle est signalée (`suspect`, réparation) et le réglage
mémorisé est rendu.

Zendure Local écrit ces réglages en mémoire flash : une écriture n'a lieu que si
la valeur change, et jamais plus d'une fois par période `min_interval` (sauf la
première restitution, qui passe toujours).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

TOLERANCE = 0.5  # %
VERSION = 2  # v1.3.6 : restitution en deux temps (migration des mémoires faussées)


def _close(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= TOLERANCE


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
        # R2 (v1.3.6)
        self.pending: dict[str, float] = dict(data.get("pending", {}))  # valeur rendue, pas encore confirmée
        self.reserved: set[str] = set(data.get("reserved", []))  # réserve posée depuis le dernier réglage connu
        self.suspect: dict[str, float] = dict(data.get("suspect", {}))  # valeur lue = réserve, refusée
        self.version: int = int(data.get("version", 1))
        self.min_interval = min_interval
        self.reserve_setting: float | None = None  # « Réserve si non rentable », donnée par le manager
        self.events: list[tuple[str, str, float, float | None]] = []  # (genre, entité, valeur, mémoire) à journaliser

    def dump(self) -> dict:
        return {
            "memo": self.memo,
            "applied": self.applied,
            "last_write": self.last_write,
            "hold": sorted(self.hold),
            "pending": self.pending,
            "reserved": sorted(self.reserved),
            "suspect": self.suspect,
            "version": self.version,
        }

    def new_plan(self) -> None:
        """Un nouveau calcul : les réglages changés par l'utilisateur peuvent être repris."""
        self.hold.clear()

    def user_value(self, t: Target) -> float | None:
        """Réglage de l'utilisateur (mémorisé, ou lu s'il n'a jamais été modifié)."""
        self._observe(t)
        return self.memo.get(t.entity_id)

    # ---------------------------------------------------------------- lecture
    def _observe(self, t: Target) -> None:
        cur = t.current
        if cur is None:
            return
        eid = t.entity_id
        posed = self.applied.get(eid)
        back = self.pending.get(eid)
        if back is not None:
            if _close(cur, back):
                self._restored(eid)  # restitution confirmée par la batterie
            elif not _close(cur, posed):
                self._user_value(t, cur, held=True)  # ni posée ni rendue : réglage de l'utilisateur
            return  # encore la valeur posée : on attend (et on renverra)
        if posed is not None:
            if not _close(cur, posed):
                self._user_value(t, cur, held=True)  # changée pendant que le Chef la tenait
            return
        if _close(cur, self.memo.get(eid)):
            return
        self._user_value(t, cur, held=False)

    def _user_value(self, t: Target, cur: float, held: bool) -> None:
        """Valeur lue qui n'est pas celle du Chef d'orchestre : réglage de l'utilisateur, sauf garde-fou.

        `held` : le Chef tenait une valeur ; le changement de l'utilisateur est alors
        respecté jusqu'au calcul suivant (`hold`).
        """
        eid = t.entity_id
        memo = self.memo.get(eid)
        if (
            t.kind == "min"
            and eid in self.reserved
            and memo is not None
            and not _close(memo, cur)
            and _close(cur, self.reserve_setting)
        ):
            # Sans doute une réserve restée affichée : le réglage mémorisé est gardé et rendu
            self.suspect[eid] = cur
            self.applied[eid] = cur
            self.pending[eid] = memo
            self.events.append(("suspect", eid, cur, memo))
            return
        self.memo[eid] = cur
        self.applied.pop(eid, None)
        self.pending.pop(eid, None)
        self.reserved.discard(eid)
        self.suspect.pop(eid, None)
        if held:
            self.hold.add(eid)

    def _restored(self, eid: str) -> None:
        self.pending.pop(eid, None)
        self.applied.pop(eid, None)

    # ---------------------------------------------------------------- écritures
    def _recent(self, eid: str, now: datetime) -> bool:
        last = self.last_write.get(eid)
        return bool(last) and now - datetime.fromisoformat(last) < self.min_interval

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
        et une levée par nuit. La levée passe toujours ; si la batterie ne la
        confirme pas, elle est renvoyée au plus une fois par `min_interval`.
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
            restoring = _close(wanted, user)
            if not restoring:
                self.pending.pop(eid, None)  # le Chef garde la main (réserve de nouveau voulue)
            if _close(t.current, wanted):
                if restoring:
                    self._restored(eid)
                continue
            if self._recent(eid, now) and (not restoring or eid in self.pending):
                continue
            out.append((eid, wanted))
            self.last_write[eid] = now.isoformat()
            if restoring:
                self.pending[eid] = wanted
                if eid not in self.applied:
                    self.applied[eid] = t.current  # valeur affichée à ne pas prendre pour l'utilisateur
            else:
                self.applied[eid] = wanted
                if t.kind == "min" and wanted > user + TOLERANCE:
                    self.reserved.add(eid)
        return out

    def pending_writes(self, targets: list[Target], now: datetime) -> list[tuple[str, float]]:
        """Pilotage coupé : renvoie la valeur rendue aux batteries qui affichent encore la valeur posée."""
        out: list[tuple[str, float]] = []
        for t in targets:
            self._observe(t)
            eid = t.entity_id
            back = self.pending.get(eid)
            if back is None or t.current is None or _close(t.current, back) or self._recent(eid, now):
                continue
            out.append((eid, back))
            self.last_write[eid] = now.isoformat()
        return out

    def restore_all(self, now: datetime | None = None) -> list[tuple[str, float]]:
        """Rend à chaque batterie le réglage de l'utilisateur (restitution en attente de confirmation)."""
        out = []
        for eid in self.applied:
            if eid in self.memo:
                self.pending[eid] = self.memo[eid]
                out.append((eid, self.memo[eid]))
                if now is not None:
                    self.last_write[eid] = now.isoformat()
        self.hold.clear()
        return out

    def set_user(self, eid: str, value: float, current: float | None) -> bool:
        """Réglage choisi par l'utilisateur (réparation) : mémorisé ; True s'il faut l'écrire."""
        self.memo[eid] = value
        self.suspect.pop(eid, None)
        self.reserved.discard(eid)
        self.hold.discard(eid)
        if _close(current, value):
            self._restored(eid)
            return False
        self.applied[eid] = current if current is not None else value
        self.pending[eid] = value
        return True

    @property
    def active(self) -> bool:
        """Le Chef tient une valeur sur au moins une batterie (hors restitution en attente)."""
        return any(eid not in self.pending for eid in self.applied)

    # ---------------------------------------------------------------- migration v1.3.6
    def migrate(
        self,
        min_entities: list[str],
        histories: dict[str, list[float]],
        reserve: float,
    ) -> list[tuple[str, float | None]]:
        """Mémoire faussée par v1.3.5 et avant : SOC min mémorisé = réserve, rien de posé.

        Si l'historique montre la réserve posée par le Chef d'orchestre (passage d'une
        valeur à la réserve, sur une entité où il a déjà écrit), la valeur d'avant
        revient. À défaut, la valeur d'une autre batterie qui n'est pas la réserve ;
        sinon la batterie est signalée (réparation). Renvoie (entité, valeur retrouvée
        ou None) pour chaque mémoire corrigée ou signalée.
        """
        fixes: list[tuple[str, float | None]] = []
        if self.version >= VERSION:
            return fixes
        self.version = VERSION
        # v1.3.5 vidait `applied` en rendant la main (rechargement pour la mise à jour) :
        # une réserve encore affichée serait prise pour le réglage de l'utilisateur.
        # Le garde-fou s'arme sur toute batterie où le Chef a déjà écrit.
        self.reserved |= {e for e in min_entities if e in self.last_write}
        faulty = [
            eid
            for eid in min_entities
            if _close(self.memo.get(eid), reserve)
            and eid not in self.applied
            and eid not in self.pending
            and eid in self.last_write  # sinon le Chef n'a jamais écrit ici : c'est bien le réglage
        ]
        unresolved = []
        for eid in faulty:  # 1. la valeur d'avant la réserve, dans l'historique
            before = value_before_reserve(histories.get(eid) or [], reserve)
            if before is None:
                unresolved.append(eid)
            else:
                fixes.append((eid, before))
                self._recover(eid, before)
        for eid in unresolved:  # 2. à défaut, le réglage d'une autre batterie
            sane = next(
                (self.memo[e] for e in min_entities if e in self.memo and not _close(self.memo[e], reserve)), None
            )
            if sane is None:
                self.suspect[eid] = self.memo[eid]
                fixes.append((eid, None))
            else:
                fixes.append((eid, sane))
                self._recover(eid, sane)
        return fixes

    def _recover(self, eid: str, value: float) -> None:
        posed = self.memo[eid]
        self.memo[eid] = value
        self.applied[eid] = posed  # la batterie affiche encore la réserve
        self.pending[eid] = value


def value_before_reserve(values: list[float], reserve: float) -> float | None:
    """Valeur juste avant le dernier passage à la réserve dans l'historique (ordre chronologique)."""
    for k in range(len(values) - 1, 0, -1):
        if _close(values[k], reserve) and not _close(values[k - 1], reserve):
            return values[k - 1]
    return None
