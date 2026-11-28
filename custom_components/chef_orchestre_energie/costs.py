"""Coût réel de la recharge et coût de l'énergie en stock (v1.4.0, C1 à C4).

Module pur (sans Home Assistant), testé à part. Zendure fournit les quantités (capteurs
de provenance, v1.7.0), Tarifs les prix, ce module fait les calculs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

INITIAL_ESTIMATED_SHARE = 0.10  # C2 : « estimé » tant que le stock initial pèse plus de 10 %


def weighted_wear(values: list[tuple[float, float | None]]) -> float | None:
    """C4 : usure par kWh restitué lue dans la Rentabilité solaire.

    `values` : (storage_cost €/kWh, capacité utile kWh ou None) par batterie. Moyenne
    pondérée par la capacité ; sans capacité connue, moyenne simple. None si aucune valeur.
    """
    vals = [(c, cap) for c, cap in values if c is not None and c >= 0]
    if not vals:
        return None
    if all(cap and cap > 0 for _c, cap in vals):
        total = sum(cap for _c, cap in vals)
        return round(sum(c * cap for c, cap in vals) / total, 4)
    return round(sum(c for c, _cap in vals) / len(vals), 4)


def value_slices(
    slices: list[tuple[datetime, float]], prices: list[tuple[datetime, float | None]], fallback: float | None
) -> tuple[float, float]:
    """C1, rattrapage après une coupure : valorise chaque tranche d'énergie (5 min) au
    prix en vigueur à son début (dernier changement d'état de `prix_actuel` avant elle).

    Retourne (coût €, kWh valorisés au prix de repli faute d'historique).
    """
    prices = sorted((t, p) for t, p in prices if p is not None)
    cost = unpriced = 0.0
    j = -1
    for ts, kwh in sorted(slices):
        if kwh <= 0:
            continue
        while j + 1 < len(prices) and prices[j + 1][0] <= ts:
            j += 1
        if j >= 0:
            cost += kwh * prices[j][1]
        elif fallback is not None:
            cost += kwh * fallback
            unpriced += kwh
    return cost, unpriced


@dataclass
class ChargeCost:
    """C1 : coût réel de la recharge du mois, minute par minute.

    À chaque contrôle, la hausse des compteurs `energy_charged_grid` et
    `energy_charged_solar` est valorisée : le réseau au prix du moment, le solaire au
    prix de revente (ce qu'il aurait rapporté). Sans prix, l'énergie attend le premier
    prix connu. Un compteur qui baisse (batterie remplacée) n'est jamais un coût négatif.
    """

    month: str = ""
    cost_eur: float = 0.0  # réseau, ce mois-ci
    grid_kwh: float = 0.0
    solar_kwh: float = 0.0
    solar_value_eur: float = 0.0  # solaire stocké au lieu d'être revendu, ce mois-ci
    last_grid: float | None = None
    last_solar: float | None = None
    last_time: datetime | None = None
    pending_kwh: float = 0.0  # énergie réseau en attente d'un prix

    def roll(self, now: datetime) -> None:
        month = now.strftime("%Y-%m")
        if month != self.month:
            self.month = month
            self.cost_eur = self.grid_kwh = self.solar_kwh = self.solar_value_eur = 0.0

    def deltas(self, grid: float | None, solar: float | None) -> tuple[float, float]:
        """Hausse des compteurs depuis la dernière lecture (0 au premier passage ou après une baisse)."""
        dg = ds = 0.0
        if grid is not None:
            if self.last_grid is not None and grid >= self.last_grid:
                dg = grid - self.last_grid
            self.last_grid = grid
        if solar is not None:
            if self.last_solar is not None and solar >= self.last_solar:
                ds = solar - self.last_solar
            self.last_solar = solar
        return dg, ds

    def add(
        self, now: datetime, d_grid: float, d_solar: float, price: float | None, resale: float | None
    ) -> tuple[float, float]:
        """Ajoute l'énergie chargée ; retourne (coût réseau €, coût solaire €) ajoutés."""
        self.roll(now)
        self.last_time = now
        self.grid_kwh += d_grid
        self.solar_kwh += d_solar
        g_cost = 0.0
        if price is None:
            self.pending_kwh += d_grid
        else:
            g_cost = (d_grid + self.pending_kwh) * price
            self.pending_kwh = 0.0
        s_cost = d_solar * (resale or 0.0)
        self.cost_eur += g_cost
        self.solar_value_eur += s_cost
        return g_cost, s_cost

    def update(
        self, now: datetime, grid: float | None, solar: float | None, price: float | None, resale: float | None
    ) -> tuple[float, float]:
        dg, ds = self.deltas(grid, solar)
        return self.add(now, dg, ds, price, resale)

    @property
    def average_price(self) -> float | None:
        return round(self.cost_eur / self.grid_kwh, 4) if self.grid_kwh > 0.01 else None

    def dump(self) -> dict[str, Any]:
        return {
            "month": self.month,
            "cost_eur": round(self.cost_eur, 5),
            "grid_kwh": round(self.grid_kwh, 4),
            "solar_kwh": round(self.solar_kwh, 4),
            "solar_value_eur": round(self.solar_value_eur, 5),
            "last_grid": self.last_grid,
            "last_solar": self.last_solar,
            "last_time": self.last_time.isoformat() if self.last_time else None,
            "pending_kwh": round(self.pending_kwh, 4),
        }

    @classmethod
    def load(cls, data: dict[str, Any] | None) -> ChargeCost:
        if not data:
            return cls()
        last = data.get("last_time")
        return cls(
            month=data.get("month", ""),
            cost_eur=float(data.get("cost_eur", 0.0)),
            grid_kwh=float(data.get("grid_kwh", 0.0)),
            solar_kwh=float(data.get("solar_kwh", 0.0)),
            solar_value_eur=float(data.get("solar_value_eur", 0.0)),
            last_grid=data.get("last_grid"),
            last_solar=data.get("last_solar"),
            last_time=datetime.fromisoformat(last) if last else None,
            pending_kwh=float(data.get("pending_kwh", 0.0)),
        )


@dataclass
class StockCost:
    """C2 : coût de l'énergie en stock, par origine, pour l'affichage seulement.

    C_r et C_s suivent les stocks de Zendure : chaque charge ajoute son coût ; quand un
    stock baisse (décharge, recalage), son coût baisse dans la même proportion.
    """

    cost_grid: float | None = None
    cost_solar: float | None = None
    stock_grid: float | None = None
    stock_solar: float | None = None
    initial_share: float = 0.0

    @property
    def started(self) -> bool:
        return self.cost_grid is not None

    def start(self, s_grid: float, s_solar: float, hc_price: float | None, resale: float | None) -> bool:
        """Premier passage : le stock présent, d'origine inconnue pour le Chef, est valorisé
        au prix moyen des heures creuses à venir (réseau) et au prix de revente (solaire)."""
        if hc_price is None:
            return False
        self.cost_grid = max(0.0, s_grid) * hc_price
        self.cost_solar = max(0.0, s_solar) * (resale or 0.0)
        self.stock_grid, self.stock_solar = s_grid, s_solar
        return True

    def update(self, s_grid: float, s_solar: float, add_grid: float = 0.0, add_solar: float = 0.0) -> None:
        if not self.started:
            return
        self.cost_grid = _follow(self.cost_grid + add_grid, self.stock_grid, s_grid)
        self.cost_solar = _follow((self.cost_solar or 0.0) + add_solar, self.stock_solar, s_solar)
        self.stock_grid, self.stock_solar = s_grid, s_solar

    def price_stored(self) -> float | None:
        """€/kWh de l'énergie dans le pack (pertes de charge déjà comprises)."""
        if not self.started:
            return None
        total = (self.stock_grid or 0.0) + (self.stock_solar or 0.0)
        if total < 0.05:
            return None
        return round((self.cost_grid + (self.cost_solar or 0.0)) / total, 4)

    def price_delivered(self, eta_d: float | None) -> float | None:
        p = self.price_stored()
        if p is None or not eta_d:
            return None
        return round(p / eta_d, 4)

    @property
    def solar_share(self) -> float | None:
        total = (self.stock_grid or 0.0) + (self.stock_solar or 0.0)
        return round((self.stock_solar or 0.0) / total * 100, 1) if total > 0.05 else None

    @property
    def estimated(self) -> bool:
        return self.initial_share > INITIAL_ESTIMATED_SHARE

    def dump(self) -> dict[str, Any]:
        return {
            "cost_grid": self.cost_grid,
            "cost_solar": self.cost_solar,
            "stock_grid": self.stock_grid,
            "stock_solar": self.stock_solar,
        }

    @classmethod
    def load(cls, data: dict[str, Any] | None) -> StockCost:
        if not data:
            return cls()
        return cls(
            cost_grid=data.get("cost_grid"),
            cost_solar=data.get("cost_solar"),
            stock_grid=data.get("stock_grid"),
            stock_solar=data.get("stock_solar"),
        )


def _follow(cost: float, old: float | None, new: float) -> float:
    """Le coût suit le stock quand il baisse ; il ne bouge pas quand le stock monte."""
    if old is None or new >= old:
        return max(0.0, cost)
    if new <= 0 or old <= 0:
        return 0.0
    return max(0.0, cost * new / old)
