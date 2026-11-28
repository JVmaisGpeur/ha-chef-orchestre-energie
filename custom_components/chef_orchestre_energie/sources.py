"""Lecture des autres intégrations par leurs contrats publics (entités, services)."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .consumption import energy_dashboard_stats, energy_factor  # noqa: F401
from .const import (
    BATTERY_DOMAIN,
    ENERGY_COUNTER_KEYS,
    PROVENANCE_KEYS,
    PROVENANCE_REQUIRED,
    SOLAR_DOMAINS,
    TARIFF_DOMAIN,
)
from .timeline import wh_hours_to_periods

_LOGGER = logging.getLogger(__name__)


def find_entities(
    hass: HomeAssistant,
    platform: str,
    keys: tuple[str, ...],
    *,
    device_id: str | None = None,
    config_entry_id: str | None = None,
) -> dict[str, str]:
    """{translation_key: entity_id} pour un appareil ou une entrée de configuration."""
    reg = er.async_get(hass)
    if device_id:
        entries = er.async_entries_for_device(reg, device_id)
    elif config_entry_id:
        entries = er.async_entries_for_config_entry(reg, config_entry_id)
    else:
        return {}
    out: dict[str, str] = {}
    for e in entries:
        if e.platform == platform and e.translation_key in keys and e.disabled_by is None:
            out.setdefault(e.translation_key, e.entity_id)
    return out


def battery_units(hass: HomeAssistant, device_id: str) -> list[str]:
    """Appareils des batteries réelles : la batterie elle-même, ou les membres d'un Groupe.

    Zendure Local ≥ 1.4.0 expose `member_device_ids` ; en 1.3.x, le sélecteur de
    mode du Groupe liste ses batteries (attribut `batteries`, par entrée).
    """
    from homeassistant.helpers import device_registry as dr

    ents = find_entities(
        hass, BATTERY_DOMAIN, ("operating_mode", "regulation_state"), device_id=device_id
    )
    for eid in ents.values():
        st = hass.states.get(eid)
        if st and isinstance(st.attributes.get("member_device_ids"), list):
            return [d for d in st.attributes["member_device_ids"] if d] or [device_id]
    st = hass.states.get(ents.get("operating_mode", ""))
    batteries = st.attributes.get("batteries") if st else None
    if isinstance(batteries, list) and batteries:
        reg = dr.async_get(hass)
        out: list[str] = []
        for b in batteries:
            entry_id = b.get("entry_id") if isinstance(b, dict) else None
            if entry_id:
                out += [d.id for d in dr.async_entries_for_config_entry(reg, entry_id)]
        if out:
            return out
    return [device_id]


def battery_energy_counters(hass: HomeAssistant) -> dict[str, list[str]]:
    """Compteurs d'énergie de toutes les batteries Zendure (pour la conso calculée)."""
    reg = er.async_get(hass)
    out: dict[str, list[str]] = {k: [] for k in ENERGY_COUNTER_KEYS}
    for e in reg.entities.values():
        if e.platform == BATTERY_DOMAIN and e.translation_key in ENERGY_COUNTER_KEYS:
            if e.disabled_by is None:
                out[e.translation_key].append(e.entity_id)
    return out


def counters_for_device(hass: HomeAssistant, device_id: str) -> dict[str, list[str]]:
    """Compteurs d'énergie de la batterie pilotée, ou des membres d'un Groupe.

    Un Groupe n'a pas forcément ses propres compteurs : on prend alors ceux de
    toutes les batteries Zendure.
    """
    own = find_entities(hass, BATTERY_DOMAIN, ENERGY_COUNTER_KEYS, device_id=device_id)
    if "energy_charged" in own and "energy_discharged" in own:
        return {k: [own[k]] if k in own else [] for k in ENERGY_COUNTER_KEYS}
    return battery_energy_counters(hass)


def provenance_entities(hass: HomeAssistant, device_id: str, units: list[str]) -> dict[str, list[str]]:
    """Capteurs de provenance de Zendure ≥ 1.7.0 (v1.4.0, C1/C2) : ceux du groupe, sinon
    ceux de chaque batterie membre (additionnés). Facultatifs : jamais de réparation."""
    own = find_entities(hass, BATTERY_DOMAIN, PROVENANCE_KEYS, device_id=device_id)
    if all(k in own for k in PROVENANCE_REQUIRED):
        return {k: [v] for k, v in own.items()}
    out: dict[str, list[str]] = {k: [] for k in PROVENANCE_KEYS}
    for dev in units:
        if dev == device_id:
            continue
        for k, v in find_entities(hass, BATTERY_DOMAIN, PROVENANCE_KEYS, device_id=dev).items():
            out[k].append(v)
    return out


def platform_entities(hass: HomeAssistant, platform: str, key: str) -> list[str]:
    """Toutes les entités actives d'une intégration ayant cette translation_key."""
    reg = er.async_get(hass)
    return [
        e.entity_id
        for e in reg.entities.values()
        if e.platform == platform and e.translation_key == key and e.disabled_by is None
    ]


def sum_states(hass: HomeAssistant, entity_ids: list[str] | None) -> float | None:
    """Somme des états ; None si l'un manque (une somme partielle fausserait les écarts)."""
    if not entity_ids:
        return None
    total = 0.0
    for eid in entity_ids:
        v = state_float(hass, eid)
        if v is None:
            return None
        total += v
    return total


def state_float(hass: HomeAssistant, entity_id: str | None) -> float | None:
    if not entity_id:
        return None
    st = hass.states.get(entity_id)
    if st is None or st.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
        return None
    try:
        return float(st.state)
    except (TypeError, ValueError):
        return None


def state_str(hass: HomeAssistant, entity_id: str | None) -> str | None:
    if not entity_id:
        return None
    st = hass.states.get(entity_id)
    if st is None or st.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    return st.state


async def async_integration_version(hass: HomeAssistant, domain: str) -> str | None:
    try:
        integration = await async_get_integration(hass, domain)
    except Exception:  # noqa: BLE001 - intégration absente
        return None
    return str(integration.version) if integration.version else "0"


def version_ok(found: str | None, minimum: str) -> bool:
    if found is None:
        return False
    try:
        from awesomeversion import AwesomeVersion

        return AwesomeVersion(found) >= AwesomeVersion(minimum)
    except Exception:  # noqa: BLE001
        def parts(v: str) -> tuple[int, ...]:
            return tuple(int(x) for x in v.split(".")[:3] if x.isdigit())

        return parts(found) >= parts(minimum)


async def async_tariff_forecast(hass: HomeAssistant, entry_id: str, hours: int) -> dict:
    """Appelle tarifs_electricite.previsions (réponse uniquement)."""
    return await hass.services.async_call(
        TARIFF_DOMAIN,
        "previsions",
        {"config_entry_id": entry_id, "heures": min(72, max(1, hours))},
        blocking=True,
        return_response=True,
    )


def solar_entries(hass: HomeAssistant) -> list[tuple[str, str]]:
    """(entry_id, titre) des prévisions solaires installées."""
    out = []
    for domain in SOLAR_DOMAINS:
        for entry in hass.config_entries.async_entries(domain):
            out.append((entry.entry_id, f"{entry.title} ({domain})"))
    return out


async def async_solar_periods(
    hass: HomeAssistant, entry_ids: list[str]
) -> tuple[list[tuple[datetime, datetime, float]], int]:
    """Prévision de production de toutes les entrées, via la plateforme `energy`.

    C'est la même source que le tableau Énergie : une entrée par champ de
    panneaux, additionnées. Retourne (périodes, nombre d'entrées lues).
    """
    periods: list[tuple[datetime, datetime, float]] = []
    read = 0
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            continue
        try:
            integration = await async_get_integration(hass, entry.domain)
            platform = await integration.async_get_platform("energy")
            forecast = await platform.async_get_solar_forecast(hass, entry_id)
        except Exception as err:  # noqa: BLE001 - une prévision défaillante n'arrête pas les autres
            _LOGGER.debug("Prévision solaire %s illisible : %s", entry_id, err)
            continue
        wh = (forecast or {}).get("wh_hours") or {}
        if wh:
            periods += wh_hours_to_periods(wh)
            read += 1
    return periods, read


async def async_hourly_sums(
    hass: HomeAssistant, statistic_ids: list[str], start: datetime, end: datetime, period: str = "hour"
) -> dict[str, list[tuple[datetime, float]]]:
    """Totaux cumulés horaires (statistiques long terme) : {id: [(début d'heure, somme)]}.

    `period` = "5minute" pour les statistiques à 5 minutes (rattrapage du coût, C1)."""
    ids = [i for i in statistic_ids if i]
    if not ids:
        return {}
    try:
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import (
            get_metadata,
            statistics_during_period,
        )
    except ImportError:  # pragma: no cover - recorder absent
        return {}
    recorder = get_instance(hass)
    try:
        stats = await recorder.async_add_executor_job(
            statistics_during_period, hass, start, end, set(ids), period, None, {"sum"}
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Lecture des statistiques impossible : %s", err)
        return {}
    # Unité enregistrée avec les statistiques : connue même si le capteur est indisponible
    units: dict[str, str | None] = {}
    try:
        meta = await recorder.async_add_executor_job(
            lambda: get_metadata(hass, statistic_ids=set(ids))
        )
        units = {sid: m[1].get("unit_of_measurement") for sid, m in meta.items()}
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Unités des statistiques illisibles : %s", err)
    out: dict[str, list[tuple[datetime, float]]] = {}
    for sid, rows in stats.items():
        # Chaque capteur est ramené en kWh selon sa propre unité
        unit = units.get(sid)
        if unit is None:
            st = hass.states.get(sid)
            unit = st.attributes.get("unit_of_measurement") if st else None
        factor = energy_factor(unit)
        pts = []
        for row in rows:
            ts = row.get("start")
            if isinstance(ts, (int, float)):
                ts = dt_util.utc_from_timestamp(ts)
            if ts is None or row.get("sum") is None:
                continue
            pts.append((dt_util.as_local(ts), float(row["sum"]) * factor))
        out[sid] = pts
    return out


async def async_hourly_means(
    hass: HomeAssistant, statistic_id: str | None, start: datetime, end: datetime
) -> dict[datetime, float]:
    """Moyennes horaires enregistrées d'un capteur (niveau de charge…) : {début d'heure: moyenne}."""
    if not statistic_id:
        return {}
    try:
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import statistics_during_period
    except ImportError:  # pragma: no cover - recorder absent
        return {}
    try:
        stats = await get_instance(hass).async_add_executor_job(
            statistics_during_period, hass, start, end, {statistic_id}, "hour", None, {"mean"}
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Lecture des statistiques impossible : %s", err)
        return {}
    out: dict[datetime, float] = {}
    for row in stats.get(statistic_id, []):
        if row.get("mean") is None:
            continue
        ts = row["start"]
        ts = dt_util.utc_from_timestamp(ts) if isinstance(ts, (int, float)) else ts
        out[dt_util.as_local(ts)] = float(row["mean"])
    return out


async def async_energy_prefs(hass: HomeAssistant) -> dict | None:
    """Configuration du tableau Énergie de Home Assistant, si elle existe."""
    try:
        from homeassistant.components.energy.data import async_get_manager

        manager = await async_get_manager(hass)
        return dict(manager.data) if manager.data else None
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Tableau Énergie illisible : %s", err)
        return None


def power_w(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Puissance en W (convertit les kW)."""
    v = state_float(hass, entity_id)
    if v is None:
        return None
    st = hass.states.get(entity_id)
    unit = (st.attributes.get("unit_of_measurement") or "W").lower() if st else "w"
    return v * 1000 if unit == "kw" else v


def tariff_grid(hass: HomeAssistant, prix_actuel: str | None) -> Any:
    """Attribut `grille` de prix_actuel (hors contrat, lu au mieux pour l'hypothèse Tempo)."""
    if not prix_actuel:
        return None
    st = hass.states.get(prix_actuel)
    return st.attributes.get("grille") if st else None


# ------------------------------------------------------------------ routeurs F1ATB (N5)
def router_devices(hass: HomeAssistant) -> list[tuple[str, str]]:
    """Routeurs ajoutés dans ha-routeur-f1atb : [(device_id, nom)], par leur puissance routée."""
    from homeassistant.helpers import device_registry as dr

    from .const import ROUTER_DOMAIN

    reg = er.async_get(hass)
    dreg = dr.async_get(hass)
    out: dict[str, str] = {}
    for e in reg.entities.values():
        if e.platform == ROUTER_DOMAIN and e.translation_key == "routed_power" and e.device_id:
            dev = dreg.async_get(e.device_id)
            if dev is not None and dev.disabled_by is None:
                out[e.device_id] = dev.name_by_user or dev.name or e.device_id
    return sorted(out.items(), key=lambda kv: kv[1].lower())


def device_name(hass: HomeAssistant, device_id: str) -> str:
    from homeassistant.helpers import device_registry as dr

    dev = dr.async_get(hass).async_get(device_id)
    return (dev.name_by_user or dev.name) if dev else device_id


async def async_number_history(hass: HomeAssistant, entity_id: str, start: datetime, end: datetime) -> list[float]:
    """Valeurs successives d'une entité numérique (ordre chronologique), vide si l'historique manque."""
    try:
        from homeassistant.components.recorder import get_instance, history
    except ImportError:  # recorder absent
        return []

    def _query():
        return history.state_changes_during_period(hass, start, end, entity_id, no_attributes=True)

    try:
        states = await get_instance(hass).async_add_executor_job(_query)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Historique de %s illisible : %s", entity_id, err)
        return []
    out: list[float] = []
    for st in states.get(entity_id, []):
        try:
            out.append(float(st.state))
        except (TypeError, ValueError):
            continue
    return out


async def async_last_full_charge(
    hass: HomeAssistant, entity_id: str, start: datetime, end: datetime, full_soc: float
) -> datetime | None:
    """Dernière fois où le niveau de charge a atteint 100 % dans l'historique (N3)."""
    try:
        from homeassistant.components.recorder import get_instance, history
    except ImportError:  # recorder absent
        return None

    def _query():
        return history.state_changes_during_period(hass, start, end, entity_id, no_attributes=True)

    try:
        states = await get_instance(hass).async_add_executor_job(_query)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Historique de %s illisible : %s", entity_id, err)
        return None
    last = None
    for st in states.get(entity_id, []):
        try:
            if float(st.state) >= full_soc:
                last = st.last_changed
        except (TypeError, ValueError):
            continue
    return last


async def async_state_history(
    hass: HomeAssistant, entity_id: str | None, start: datetime, end: datetime
) -> list[tuple[datetime, float | None]]:
    """Historique de l'état d'une entité (le prix du moment de Tarifs) : [(depuis, valeur)].

    Le premier élément donne l'état en vigueur au début de la période."""
    if not entity_id:
        return []
    try:
        from homeassistant.components.recorder import get_instance, history
    except ImportError:  # pragma: no cover - recorder absent
        return []
    try:
        states = await get_instance(hass).async_add_executor_job(
            lambda: history.state_changes_during_period(
                hass, start, end, entity_id, include_start_time_state=True
            )
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Historique de %s illisible : %s", entity_id, err)
        return []
    out: list[tuple[datetime, float | None]] = []
    for st in states.get(entity_id, []):
        try:
            v: float | None = float(st.state)
        except (TypeError, ValueError):
            v = None
        out.append((max(st.last_changed, start), v))
    return out