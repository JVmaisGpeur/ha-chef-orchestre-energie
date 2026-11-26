"""Chef d'orchestre : lit les sources, calcule le plan, pilote la batterie."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from . import sources as src
from .const import (
    BATTERY_DOMAIN,
    BATTERY_KEYS,
    BATTERY_MIN_VERSION,
    CONF_BATTERY_DEVICE,
    CONF_DAILY_KWH,
    CONF_EFFICIENCY,
    CONF_FINISH_ADVANCE,
    CONF_GAIN_THRESHOLD,
    CONF_GRID_EXPORT,
    CONF_GRID_IMPORT,
    CONF_HISTORY_WEEKS,
    CONF_HOUSE_SENSOR,
    CONF_LOADS,
    CONF_MARGIN,
    CONF_NOTIFY_LEVEL,
    CONF_NOTIFY_SERVICE,
    CONF_PROFILE,
    CONF_AUTO_START,
    CONF_FULL_CHARGE_AUTO,
    CONF_FULL_CHARGE_DAYS,
    CONF_ROUTER_DAILY_KWH,
    CONF_ROUTER_SHIFT,
    CONF_ROUTER_PRIORITY,
    CONF_ROUTERS,
    CONF_SUMMER_SOC,
    CEILING_KEYS,
    LOAD_BATTERY,
    LOAD_ROUTER,
    ROUTER_CONTROLLED_KEYS,
    ROUTER_DOMAIN,
    ROUTER_KEYS,
    ROUTER_RENEW_MIN,
    ROUTER_REQUIRED,
    UNIT_CAL_KEYS,
    CONF_GAUGE_CRIT,
    CONF_GAUGE_WARN,
    CONF_POWER_SENSOR,
    CONF_RESERVE_SOC,
    CONF_SOLAR_ACTUAL,
    CONF_SOLAR_CORRECTION,
    CONF_SOLAR_ENTRIES,
    CONF_SUBSCRIBED_KVA,
    CONF_TARIFF_ENTRY,
    CONF_TEMPO_ASSUMPTION,
    CONF_THREE_PHASE,
    CONF_WEAR,
    CONTROL_INTERVAL_S,
    CONTROLLER_NAME,
    EXTERNAL_CONTROL_RENEW_MIN,
    EXTERNAL_CONTROL_SERVICE,
    INTERFACE_VERSION,
    UNIT_SOC_BOUNDS,
    UNIT_SOC_KEYS,
    DEFAULTS,
    DOMAIN,
    EFFICIENCY_DAYS,
    HORIZON_HOURS,
    LOAD_ENERGY_SENSOR,
    LOAD_NAME,
    LOAD_POWER,
    LOAD_POWER_SENSOR,
    LOAD_STATE_ENTITY,
    LOAD_THRESHOLD,
    LOAD_WINDOW,
    PLAN_INTERVAL_MIN,
    PROFILES,
    SOLAR_FACTOR_DAYS,
    STEP_MINUTES,
    STORE_VERSION,
    TARIFF_CARD_KEYS,
    TARIFF_DOMAIN,
    TARIFF_KEYS,
    TARIFF_MIN_VERSION,
    TARIFF_REQUIRED,
)
from .consumption import (
    ConsumptionProfile,
    correction_factor,
    hourly_changes,
    measured_efficiency,
)
from .fullcharge import (
    ACTION_NOW,
    ACTION_SUN,
    ACTION_TONIGHT,
    CALIBRATION_DAYS,
    FULL_SOC,
    FullChargeTracker,
)
from .router_logic import (
    OUTLOOK_HEAT,
    OUTLOOK_HOT,
    NightStep,
    RouterDecision,
    RouterInputs,
    RouterLogic,
    choose_heat_window,
    combine,
    next_on_slot,
    on_slot_outlook,
)
from .planner import (
    MODE_GRID_CHARGE,
    MODE_OFF,
    MODE_SMART,
    PLAN_CHARGE,
    PLAN_IDLE,
    PLAN_MISSING_DATA,
    PLAN_NOT_PROFITABLE,
    PLAN_SUSPENDED,
    REASON_MISSING_DATA,
    Battery,
    Override,
    Plan,
    Settings,
    Step,
    compute_plan_with_reserve,
    reserve_at,
    daylight_overflow,
    import_limit_w,
    wants_full_charge,
)
from .soc_keeper import SocKeeper, Target
from .timeline import (
    at,
    fill_unknown_prices,
    in_window,
    parse_segments,
    parse_window,
    segment_for_step,
    spread,
    step_starts,
)

_LOGGER = logging.getLogger(__name__)
STEP = timedelta(minutes=STEP_MINUTES)


class Orchestrator:
    """Un Chef d'orchestre par entrée de configuration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.cfg: dict[str, Any] = {**DEFAULTS, **entry.data, **entry.options}
        self._store: Store = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.profile = ConsumptionProfile(float(self.cfg[CONF_DAILY_KWH]))
        self.plan: Plan | None = None
        # Réglages à chaud (entités), conservés au redémarrage
        self.auto_control = bool(self.cfg.get(CONF_AUTO_START, True))
        self.profile_name: str = self.cfg[CONF_PROFILE]
        self.gain_threshold: float = float(self.cfg[CONF_GAIN_THRESHOLD])
        self.reserve_soc: float = float(self.cfg[CONF_RESERVE_SOC])
        # SOC min / max de chaque batterie (E2)
        self.keeper = SocKeeper()
        self.units: list[str] = []  # appareils des batteries réelles
        self.units_listener: Callable[[], None] | None = None  # capteurs par batterie (sensor.py)
        self.unit_soc: dict[str, dict[str, str]] = {}  # appareil → {min_soc, soc_set}
        self.e2_ok = False
        self.full_charge = False
        self.user_soc: dict[str, float | None] = {"min": None, "max": None}
        self._last_declare: datetime | None = None
        self.tariff_ok = False
        self.consumption_source = "none"
        self._solar_actual_ids: list[str] = []
        # Appris
        self.efficiency: float = float(self.cfg[CONF_EFFICIENCY]) / 100
        self.measured_efficiency: float | None = None
        self.solar_factor = 1.0
        self.solar_history: dict[str, float] = {}
        # Suivi
        self.monthly_savings = 0.0
        self._savings_month = ""
        self._last_tick: datetime | None = None
        self.override: dict[str, Any] | None = None
        self._notified: dict[str, str] = {}
        self._watch: dict[str, Any] | None = None
        self._charging_night: str | None = None
        self._last_max_charge: float | None = None
        self._last_solar_ok: datetime | None = None
        self.import_limit: float | None = None
        self.subscribed_kva: float | None = None
        self.sources_ok = False
        self.missing: list[str] = []
        self.tariff_entities: dict[str, str] = {}
        self.battery_entities: dict[str, str] = {}
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[Callable[[], None]] = []
        self._pending: Callable[[], None] | None = None
        self._lock_busy = False
        # v1.3.0 : choix de ce qui est piloté (N6)
        self.battery_control = True
        self.router_control: dict[str, bool] = {}
        # Charge complète et calibration (N3)
        self.fullcharge = FullChargeTracker()
        self.fc_action: str | None = None
        self.fc_units: list[str] = []
        self.fc_alert = False
        self._fc_notified: str | None = None
        self.unit_level: dict[str, str] = {}  # appareil → electric_level
        self.unit_cal: dict[str, str] = {}  # appareil → calibrating
        self._history_checked: set[str] = set()
        # Plafonds et puissance à ne pas couvrir (Zendure ≥ 1.6.0, N1/N5)
        self.ceiling_entities: dict[str, str] = {}
        self.ceilings_ok = False
        self._written: dict[str, tuple[float, datetime]] = {}
        self.excluded_w = 0.0
        self._max_cache: dict[str, float] = {}
        self._excluded_pending: Callable[[], None] | None = None
        self._battery_mode: str | None = None  # dernier mode commandé (plafond routeur)
        # Routeurs F1ATB (N5)
        self.routers: list[dict[str, Any]] = list(self.cfg.get(CONF_ROUTERS) or [])
        self.router_entities: dict[str, dict[str, str]] = {}
        self.router_logic: dict[str, RouterLogic] = {}
        self.router_decisions: dict[str, RouterDecision] = {}
        self.router_status: list[dict[str, Any]] = []
        # Prochaine plage ON de chaque routeur et fenêtre de chauffe retenue (v1.3.4)
        self.router_windows: dict[str, dict[str, Any]] = {}
        self._router_heat_done: dict[str, datetime] = {}  # fenêtre déplacée déjà terminée (ballon chaud)
        self.router_daily_kwh: dict[str, float] = {}
        self._router_sent: dict[str, dict[str, Any]] = {}
        self._router_threshold_check: datetime | None = None
        self.tomorrow_surplus_kwh: float | None = None
        self._battery_range_kwh: float | None = None

    # ------------------------------------------------------------ cycle de vie
    async def async_start(self) -> None:
        data = await self._store.async_load() or {}
        self._restore(data)
        await self.async_check_sources()
        await self.async_learn()
        await self.async_update_plan()
        hass = self.hass
        self._unsubs += [
            async_track_time_interval(hass, self._plan_tick, timedelta(minutes=PLAN_INTERVAL_MIN)),
            async_track_time_interval(hass, self._control_tick, timedelta(seconds=CONTROL_INTERVAL_S)),
            async_track_time_change(hass, self._learn_tick, hour=0, minute=35, second=0),
        ]
        watched = [
            self.tariff_entities.get(k) for k in ("puissance_souscrite", "offre", "tempo_demain")
        ] + [self.battery_entities.get(k) for k in ("usable_capacity", "max_charge_power")]
        for load in self.cfg.get(CONF_LOADS) or []:
            watched += [load.get(LOAD_POWER_SENSOR), load.get(LOAD_STATE_ENTITY)]
        watched = [w for w in watched if w]
        if watched:
            self._unsubs.append(async_track_state_change_event(hass, watched, self._on_change))
        # Puissance à ne pas couvrir : suit les consommateurs exclus en direct (N1)
        excl = self._excluded_sources()
        if excl:
            self._unsubs.append(async_track_state_change_event(hass, excl, self._on_excluded_change))
        # Puissance au tableau : affichage en direct, sans recalcul du plan
        if self.cfg.get(CONF_POWER_SENSOR):
            self._unsubs.append(
                async_track_state_change_event(
                    hass, [self.cfg[CONF_POWER_SENSOR]], self._on_power_change
                )
            )

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._pending:
            self._pending()
        if self._excluded_pending:
            self._excluded_pending()
        await self._async_release()
        await self._async_release_routers()
        await self._store.async_save(self._dump())

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    @callback
    def _on_power_change(self, _event: Event) -> None:
        """Puissance au tableau : mise à jour des entités dans la boucle de Home Assistant.

        Un rappel sans @callback (l'ancien lambda) était exécuté dans un autre fil
        et y mettait à jour les entités : Home Assistant le signale comme dangereux.
        """
        self._notify_listeners()

    @callback
    def _notify_listeners(self) -> None:
        for cb in list(self._listeners):
            cb()

    # ------------------------------------------------------------ mémoire
    def _restore(self, data: dict) -> None:
        self.auto_control = data.get("auto_control", bool(self.cfg.get(CONF_AUTO_START, True)))
        seen = data.get("options_seen", {})
        # Une valeur changée dans les options l'emporte sur la valeur à chaud
        if seen.get(CONF_PROFILE) == self.cfg[CONF_PROFILE] and data.get("profile") in PROFILES:
            self.profile_name = data["profile"]
        if seen.get(CONF_GAIN_THRESHOLD) == self.cfg[CONF_GAIN_THRESHOLD] and "gain_threshold" in data:
            self.gain_threshold = float(data["gain_threshold"])
        if seen.get(CONF_RESERVE_SOC) == self.cfg[CONF_RESERVE_SOC] and "reserve_soc" in data:
            self.reserve_soc = float(data["reserve_soc"])
        self.keeper = SocKeeper(data.get("keeper"))
        self.measured_efficiency = data.get("measured_efficiency")
        self.solar_factor = float(data.get("solar_factor", 1.0))
        self.solar_history = dict(data.get("solar_history", {}))
        self.monthly_savings = float(data.get("monthly_savings", 0.0))
        self._savings_month = data.get("savings_month", "")
        self._notified = dict(data.get("notified", {}))
        self._watch = data.get("watch")
        self._charging_night = data.get("charging_night")
        self.battery_control = bool(data.get("battery_control", True))
        saved = data.get("router_control", {})
        self.router_control = {r["device_id"]: bool(saved.get(r["device_id"], True)) for r in self.routers}
        self.fullcharge = FullChargeTracker(data.get("fullcharge"))
        self._fc_notified = data.get("fc_notified")
        ov = data.get("override")
        if ov and dt_util.parse_datetime(ov.get("until", "")) and dt_util.parse_datetime(
            ov["until"]
        ) > dt_util.now():
            self.override = ov

    def _dump(self) -> dict:
        return {
            "auto_control": self.auto_control,
            "profile": self.profile_name,
            "gain_threshold": self.gain_threshold,
            "reserve_soc": self.reserve_soc,
            "keeper": self.keeper.dump(),
            "options_seen": {
                CONF_PROFILE: self.cfg[CONF_PROFILE],
                CONF_GAIN_THRESHOLD: self.cfg[CONF_GAIN_THRESHOLD],
                CONF_RESERVE_SOC: self.cfg[CONF_RESERVE_SOC],
            },
            "measured_efficiency": self.measured_efficiency,
            "solar_factor": self.solar_factor,
            "solar_history": self.solar_history,
            "monthly_savings": round(self.monthly_savings, 4),
            "savings_month": self._savings_month,
            "notified": self._notified,
            "watch": self._watch,
            "charging_night": self._charging_night,
            "override": self.override,
            "battery_control": self.battery_control,
            "router_control": self.router_control,
            "fullcharge": self.fullcharge.dump(),
            "fc_notified": self._fc_notified,
        }

    def _save(self) -> None:
        self._store.async_delay_save(self._dump, 30)

    # ------------------------------------------------------------ réglages à chaud
    async def async_set_auto_control(self, on: bool) -> None:
        """Interrupteur général : coupé, tout s'arrête ; rallumé, les choix de N6 reviennent."""
        self.auto_control = on
        self._save()
        if not on:
            await self._async_release()
            await self._async_release_routers()
        else:
            self._last_declare = None
            self._router_sent.clear()
        await self.async_update_plan()

    async def async_set_battery_control(self, on: bool) -> None:
        """Pilotage des batteries (N6) : coupé, Zendure reprend la main."""
        self.battery_control = on
        self._save()
        if not on:
            await self._async_release()
        else:
            self._last_declare = None
        await self.async_update_plan()

    async def async_set_router_control(self, device_id: str, on: bool) -> None:
        """Pilotage d'un routeur (N6) : coupé, le routeur revient en autonome."""
        if device_id not in self.router_control:
            return
        self.router_control[device_id] = on
        self._save()
        if not on:
            await self._async_release_routers([device_id])
        await self._async_control_routers(dt_util.now())
        self._notify_listeners()

    async def async_set_full_charge(self, request: str) -> None:
        """Demande de charge complète (N3) : auto, next_sun, tonight, now, skip."""
        socs = {u: src.state_float(self.hass, self.unit_level.get(u)) for u in self.units}
        self.fullcharge.set_request(request, self.units, dt_util.now(), socs)
        self._save()
        await self.async_update_plan()

    @property
    def battery_piloted(self) -> bool:
        return self.auto_control and self.battery_control

    async def async_set_reserve_soc(self, value: float) -> None:
        self.reserve_soc = max(0.0, min(50.0, float(value)))
        self._save()
        await self.async_update_plan()

    async def async_set_profile(self, name: str) -> None:
        if name in PROFILES:
            self.profile_name = name
            self._save()
            await self.async_update_plan()

    async def async_set_gain_threshold(self, value: float) -> None:
        self.gain_threshold = max(0.0, min(1.0, float(value)))
        self._save()
        await self.async_update_plan()

    async def async_force_night(self, mode: str, target_soc: float | None) -> None:
        plan = self.plan
        end = plan.window_end if plan and plan.window_end else dt_util.now() + timedelta(hours=24)
        self.override = {"mode": mode, "target_soc": target_soc, "until": end.isoformat()}
        self._save()
        await self.async_update_plan()

    @property
    def efficiency_used(self) -> float:
        return self.measured_efficiency or self.efficiency

    # ------------------------------------------------------------ sources
    async def async_check_sources(self) -> None:
        """Vérifie versions et entités des contrats ; lève ou retire les alertes."""
        ok = True
        tariff_good = False
        for domain, minimum, name in (
            (TARIFF_DOMAIN, TARIFF_MIN_VERSION, "ha-tarifs-electricite"),
            (BATTERY_DOMAIN, BATTERY_MIN_VERSION, "ha-zendure-solarflow-local"),
        ):
            found = await src.async_integration_version(self.hass, domain)
            good = src.version_ok(found, minimum)
            self._issue(
                f"version_{domain}",
                not good,
                "integration_version",
                {"name": name, "minimum": minimum, "found": found or "-"},
            )
            if domain == TARIFF_DOMAIN:
                tariff_good = good  # recommandée : son absence n'arrête pas le reste
            else:
                ok &= good

        self.tariff_entities = (
            src.find_entities(
                self.hass,
                TARIFF_DOMAIN,
                TARIFF_KEYS + TARIFF_CARD_KEYS,
                config_entry_id=self.cfg.get(CONF_TARIFF_ENTRY),
            )
            if self.cfg.get(CONF_TARIFF_ENTRY)
            else {}
        )
        self.battery_entities = src.find_entities(
            self.hass, BATTERY_DOMAIN, BATTERY_KEYS, device_id=self.cfg[CONF_BATTERY_DEVICE]
        )
        self.tariff_ok = tariff_good and all(k in self.tariff_entities for k in TARIFF_REQUIRED)
        missing = [k for k in BATTERY_KEYS if k not in self.battery_entities]
        if tariff_good and self.cfg.get(CONF_TARIFF_ENTRY):
            missing += [k for k in TARIFF_REQUIRED if k not in self.tariff_entities]
        self._issue(
            "missing_entities", bool(missing), "missing_entities", {"keys": ", ".join(missing)}
        )
        ok &= not missing
        self.sources_ok = ok
        # E2 : SOC min / max de chaque batterie réelle
        self.units = src.battery_units(self.hass, self.cfg[CONF_BATTERY_DEVICE])
        if self.units_listener:
            self.units_listener()
        self.unit_soc = {
            dev: src.find_entities(self.hass, BATTERY_DOMAIN, UNIT_SOC_KEYS, device_id=dev)
            for dev in self.units
        }
        self.e2_ok = bool(self.unit_soc) and all(
            len(v) == len(UNIT_SOC_KEYS) for v in self.unit_soc.values()
        )
        self._issue("reserve_unavailable", ok and not self.e2_ok, "reserve_unavailable")
        # N3 : niveau de charge et calibration de chaque batterie
        self.unit_level, self.unit_cal = {}, {}
        for dev in self.units:
            found = src.find_entities(self.hass, BATTERY_DOMAIN, ("electric_level",) + UNIT_CAL_KEYS, device_id=dev)
            if "electric_level" in found:
                self.unit_level[dev] = found["electric_level"]
            if "calibrating" in found:
                self.unit_cal[dev] = found["calibrating"]
        await self._async_init_full_charge()
        # N1/N5 : plafonds et puissance à ne pas couvrir (Zendure ≥ 1.6.0)
        self.ceiling_entities = src.find_entities(
            self.hass, BATTERY_DOMAIN, CEILING_KEYS, device_id=self.cfg[CONF_BATTERY_DEVICE]
        )
        self.ceilings_ok = all(k in self.ceiling_entities for k in CEILING_KEYS)
        # N5 : routeurs déclarés
        self.router_entities = {
            r["device_id"]: src.find_entities(self.hass, ROUTER_DOMAIN, ROUTER_KEYS, device_id=r["device_id"])
            for r in self.routers
        }
        for r in self.routers:
            self.router_logic.setdefault(r["device_id"], RouterLogic())
            self.router_control.setdefault(r["device_id"], True)
        configured = {r["device_id"] for r in self.routers}
        seen = set(self.cfg.get("routers_seen") or [])
        new = [name for dev, name in src.router_devices(self.hass) if dev not in configured and dev not in seen]
        self._issue("router_found", bool(new), "router_found", {"routers": ", ".join(new)})

    async def _async_init_full_charge(self) -> None:
        """Point de départ du compteur : dernière charge à 100 % de l'historique, sinon aujourd'hui."""
        now = dt_util.now()
        for dev, eid in self.unit_level.items():
            if dev in self.fullcharge.last_full or dev in self._history_checked:
                continue
            self._history_checked.add(dev)
            last = await src.async_last_full_charge(
                self.hass, eid, now - timedelta(days=CALIBRATION_DAYS + 5), now, FULL_SOC
            )
            if last is not None:
                self.fullcharge.start(dev, last, estimated=False)
            else:
                self.fullcharge.start(dev, now, estimated=True)
        self._save()

    def _issue(self, issue_id: str, active: bool, key: str, placeholders: dict | None = None) -> None:
        full_id = f"{self.entry.entry_id}_{issue_id}"
        if active:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                full_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=key,
                translation_placeholders=placeholders or {},
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, full_id)

    def _battery(self) -> Battery | None:
        e = self.battery_entities
        cap = src.state_float(self.hass, e.get("usable_capacity"))
        soc = src.state_float(self.hass, e.get("electric_level"))
        if not cap or soc is None:
            return None
        avail = src.state_float(self.hass, e.get("available_energy"))
        miss = src.state_float(self.hass, e.get("missing_energy"))
        soc_min = soc - avail / cap * 100 if avail is not None else 10.0
        soc_max = soc + miss / cap * 100 if miss is not None else 100.0
        maxc = src.state_float(self.hass, e.get("max_charge_power"))
        if maxc:
            self._last_max_charge = maxc
        maxc = maxc or self._last_max_charge or 1200.0
        maxd = src.state_float(self.hass, e.get("max_discharge_power")) or maxc
        return Battery(
            capacity_kwh=cap,
            soc=soc,
            soc_min=max(0.0, min(soc, soc_min)),
            soc_max=min(100.0, max(soc, soc_max)),
            max_charge_w=maxc,
            max_discharge_w=maxd,
        )

    def _subscribed_kva(self) -> float | None:
        kva = src.state_float(self.hass, self.tariff_entities.get("puissance_souscrite"))
        if kva is None and self.cfg.get(CONF_SUBSCRIBED_KVA):
            kva = float(self.cfg[CONF_SUBSCRIBED_KVA])
        self._issue("subscribed_power", kva is None, "subscribed_power_missing")
        return kva

    def _loads_w(self, when: datetime, now: datetime, exclude: str | None = None) -> float:
        total = 0.0
        for load in self.cfg.get(CONF_LOADS) or []:
            power = float(load.get(LOAD_POWER) or 0)
            running = False
            router = load.get(LOAD_ROUTER)
            if router and router == exclude:
                continue
            if router:
                # Un routeur chauffe au surplus solaire : il ne pèse sur le soutirage
                # que pendant sa chauffe sur le réseau, prévue (plage ON ou fenêtre
                # déplacée par le Chef) ou en cours
                w = self.router_windows.get(router)
                heats = w is not None and w["outlook"] == OUTLOOK_HEAT
                if heats and w["start"] <= when < w["end"]:
                    total += power
                elif (
                    when < now + STEP
                    and not (heats and w["shifted"])
                    and self._router_on_slot(self.router_entities.get(router, {}))
                ):
                    total += power
                continue
            if when < now + STEP:
                p = src.state_float(self.hass, load.get(LOAD_POWER_SENSOR))
                if p is not None:
                    running = p > float(load.get(LOAD_THRESHOLD) or 100)
                st = src.state_str(self.hass, load.get(LOAD_STATE_ENTITY))
                if st is not None:
                    running = running or st == "on"
            if running or in_window(when, parse_window(load.get(LOAD_WINDOW))):
                total += power
        return total

    # ------------------------------------------------------------ plan
    @callback
    def _on_change(self, _event: Event) -> None:
        if self._pending:
            self._pending()
        self._pending = async_call_later(self.hass, 5, self._delayed_update)

    async def _delayed_update(self, _now=None) -> None:
        self._pending = None
        await self.async_update_plan()

    async def _plan_tick(self, _now=None) -> None:
        if not self.sources_ok:
            # Au démarrage, les autres intégrations peuvent être chargées après nous
            await self.async_check_sources()
        await self.async_update_plan()

    async def _learn_tick(self, _now=None) -> None:
        await self.async_check_sources()
        await self.async_learn()
        await self.async_update_plan()

    async def async_update_plan(self) -> None:
        if self._lock_busy:
            return
        self._lock_busy = True
        try:
            self.plan = await self._async_compute()
        except Exception:  # noqa: BLE001 - le pilotage ne doit jamais planter HA
            _LOGGER.exception("Calcul du plan impossible")
            self.missing = ["error"]
            self.plan = Plan(PLAN_MISSING_DATA, REASON_MISSING_DATA)
        finally:
            self._lock_busy = False
        self._notify_listeners()
        await self._async_after_plan()
        await self._async_control()

    async def _async_compute(self) -> Plan:
        self.missing = []
        if not self.sources_ok:
            self.missing.append("sources")
            return Plan(PLAN_MISSING_DATA, REASON_MISSING_DATA)
        now = dt_util.now()
        starts = step_starts(now, HORIZON_HOURS, STEP_MINUTES)
        if not self.tariff_ok:
            # Sans Tarifs, la rentabilité n'est pas calculée : jamais de charge réseau
            self.missing.append("tariff")
            return Plan(PLAN_MISSING_DATA, REASON_MISSING_DATA)
        try:
            resp = await src.async_tariff_forecast(
                self.hass, self.cfg[CONF_TARIFF_ENTRY], HORIZON_HOURS
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Prévisions tarifaires indisponibles : %s", err)
            self.missing.append("tariff_forecast")
            return Plan(PLAN_MISSING_DATA, REASON_MISSING_DATA)
        segments = parse_segments(resp or {})
        if not segments:
            self.missing.append("tariff_forecast")
            return Plan(PLAN_MISSING_DATA, REASON_MISSING_DATA)
        fill_unknown_prices(
            segments,
            src.tariff_grid(self.hass, self.tariff_entities.get("prix_actuel")),
            self.cfg[CONF_TEMPO_ASSUMPTION],
        )
        periods, read = await src.async_solar_periods(self.hass, self.cfg[CONF_SOLAR_ENTRIES])
        if read:
            self._last_solar_ok = now
        stale = self._last_solar_ok is None or now - self._last_solar_ok > timedelta(hours=24)
        self._issue("no_solar_forecast", stale, "no_solar_forecast")
        if stale:
            # Sans prévision solaire, pas de charge en heures creuses (E3, états dégradés)
            self.missing.append("solar_forecast")
            return Plan(PLAN_MISSING_DATA, REASON_MISSING_DATA)
        factor = self.solar_factor if self.cfg[CONF_SOLAR_CORRECTION] else 1.0
        solar = [v * factor for v in spread(periods, starts, STEP)]
        self._remember_solar(periods)

        battery = self._battery()
        kva = self._subscribed_kva()
        self.subscribed_kva = kva
        if battery is None:
            self.missing.append("battery_state")
        if kva is None:
            self.missing.append("subscribed_power")
        if battery is None or kva is None:
            return Plan(PLAN_MISSING_DATA, REASON_MISSING_DATA)
        margin = max(float(self.cfg[CONF_MARGIN]), 10.0) / 100
        self.import_limit = import_limit_w(kva, margin, bool(self.cfg[CONF_THREE_PHASE]))

        steps: list[Step] = []
        per_step = STEP_MINUTES / 60
        for i, t in enumerate(starts):
            seg = segment_for_step(segments, t, STEP)
            if seg is None:
                break  # au-delà de l'horizon des tarifs
            steps.append(
                Step(
                    start=t,
                    consumption_kwh=self.profile.hour_kwh(t) * per_step,
                    solar_kwh=solar[i],
                    price=seg.price,
                    off_peak=seg.off_peak,
                )
            )
        tomorrow = (now + timedelta(days=1)).date()
        self.tomorrow_surplus_kwh = round(
            sum(max(0.0, st.solar_kwh - st.consumption_kwh) for st in steps if dt_util.as_local(st.start).date() == tomorrow),
            2,
        )
        self._battery_range_kwh = battery.range_kwh
        # Chauffe des routeurs prévue cette nuit (plage ON), comptée dans le soutirage
        self._router_plan_windows(now)
        for st in steps:
            st.loads_w = self._loads_w(st.start, now)
        settings = Settings(
            efficiency=self.efficiency_used,
            wear_eur_kwh=float(self.cfg[CONF_WEAR]),
            gain_threshold=self.gain_threshold,
            safety_margin=PROFILES.get(self.profile_name, 0.10),
            import_limit_w=self.import_limit,
            finish_advance_min=int(self.cfg[CONF_FINISH_ADVANCE]),
        )
        override = None
        if self.override:
            until = dt_util.parse_datetime(self.override.get("until", ""))
            if until and until > now:
                override = Override(self.override["mode"], self.override.get("target_soc"))
            else:
                self.override = None
                self._save()
        if not steps:
            self.missing.append("tariff_forecast")
        plan = self._plan_with_soc_rules(steps, battery, settings, override)
        if self._router_shift_windows(steps, plan, now):
            # Chauffe déplacée : le plan des batteries est refait avec la nouvelle fenêtre
            for st in steps:
                st.loads_w = self._loads_w(st.start, now)
            plan = self._plan_with_soc_rules(steps, battery, settings, override)
        if plan.state == PLAN_MISSING_DATA and not self.missing:
            self.missing.append("off_peak_price")
        if not self.auto_control:
            plan.state = PLAN_SUSPENDED
        return plan

    def _soc_targets(self) -> list[Target]:
        out: list[Target] = []
        for dev in self.units:
            level = src.state_float(self.hass, self.unit_level.get(dev))
            for key, kind in (("min_soc", "min"), ("soc_set", "max")):
                eid = self.unit_soc.get(dev, {}).get(key)
                if eid:
                    lo, hi = UNIT_SOC_BOUNDS[key]
                    out.append(Target(eid, kind, src.state_float(self.hass, eid), lo, hi, level))
        return out

    def reserve_now(self, now: datetime | None = None) -> float | None:
        """R1 : réserve en vigueur maintenant (heures creuses d'une nuit non rentable), sinon None."""
        return reserve_at(self.plan, now or dt_util.now())

    def applied_min_soc(self, reserve: float | None) -> float | None:
        """SOC min en vigueur : celui de l'utilisateur, ou la réserve posée cette nuit.

        Valeur réellement posée (moyenne des batteries) : une batterie déjà sous la
        réserve garde son niveau, et rien n'est écrit si elle est au SOC min.
        """
        user = self.user_soc.get("min")
        if reserve is None:
            return user
        mins = {v.get("min_soc") for v in self.unit_soc.values()}
        posed = [v for eid, v in self.keeper.applied.items() if eid in mins]
        return round(sum(posed) / len(posed), 1) if posed else user

    def _plan_with_soc_rules(self, steps, battery: Battery, settings, override) -> Plan:
        """Plan avec la réserve de SOC min (E2) et la règle du SOC max (D5).

        La simulation part toujours des réglages de l'utilisateur (mémorisés), et
        non des valeurs que le Chef d'orchestre a lui-même écrites.
        """
        self.keeper.new_plan()
        now = dt_util.now()
        calibrating = bool(self.calibrating_units)
        if not self.e2_ok:
            self.full_charge = False
            plan = compute_plan_with_reserve(steps, battery, settings, override, None)
            action = self._decide_full_charge(
                now, daylight_overflow(plan) >= battery.capacity_kwh * 0.05, plan.window_end
            )
            if action == ACTION_TONIGHT and override is None:
                plan = compute_plan_with_reserve(steps, battery, settings, Override("charge", 100.0), None)
            return plan
        mins, maxs = [], []
        for t in self._soc_targets():
            v = self.keeper.user_value(t)
            if v is not None:
                (mins if t.kind == "min" else maxs).append(v)
        user_min = sum(mins) / len(mins) if mins else battery.soc_min
        user_max = sum(maxs) / len(maxs) if maxs else battery.soc_max
        self.user_soc = {"min": user_min, "max": user_max}
        base = replace(battery, soc_min=user_min, soc_max=user_max, grid_soc_max=user_max)
        # Pendant une calibration : pas de réserve, SOC max à 100 % (N3, d'après le support Zendure)
        reserve = None if calibrating else self.reserve_soc
        plan = compute_plan_with_reserve(steps, base, settings, override, reserve)
        self.full_charge = wants_full_charge(plan)
        # N3 : le soleil suffit-il à monter à 100 % sans réseau ?
        need = battery.capacity_kwh * max(0.0, 100.0 - user_max) / 100
        sunny = daylight_overflow(plan) >= max(need, 0.2)
        action = self._decide_full_charge(now, sunny, plan.window_end)
        if action == ACTION_TONIGHT and override is None:
            full = replace(base, soc_max=100.0, grid_soc_max=100.0)
            plan = compute_plan_with_reserve(steps, full, settings, Override("charge", 100.0), reserve)
            self.full_charge = True
        elif action in (ACTION_SUN, ACTION_NOW) or calibrating or (self.full_charge and user_max < 100):
            self.full_charge = True
            full = replace(base, soc_max=100.0)
            plan = compute_plan_with_reserve(steps, full, settings, override, reserve)
        self._save()
        return plan

    @property
    def calibrating_units(self) -> list[str]:
        return [u for u, eid in self.unit_cal.items() if src.state_str(self.hass, eid) == "on"]

    def _decide_full_charge(self, now: datetime, sunny: bool, window_end: datetime | None = None) -> str | None:
        """Charge complète à programmer (N3) : soleil, cette nuit, maintenant ou rien."""
        # Couleur du jour qui suit la nuit de charge : après minuit, c'est aujourd'hui
        key = "tempo_demain"
        if window_end is not None and dt_util.as_local(window_end).date() == dt_util.as_local(now).date():
            key = "tempo_aujourdhui"
        tempo = (src.state_str(self.hass, self.tariff_entities.get(key)) or "").lower()
        tonight_ok = tempo not in ("blanc", "rouge", "white", "red")
        action, units, alert = self.fullcharge.decide(
            self.units,
            now,
            threshold=float(self.cfg[CONF_FULL_CHARGE_DAYS]),
            auto_enabled=bool(self.cfg[CONF_FULL_CHARGE_AUTO]),
            sunny=sunny,
            tonight_ok=tonight_ok,
        )
        self.fc_action, self.fc_units, self.fc_alert = action, units, alert
        days = self.fullcharge.max_days(self.units, now)
        self._issue("full_charge_late", alert, "full_charge_late", {"days": str(round(days or 0))})
        return action

    def _remember_solar(self, periods) -> None:
        """Garde la prévision de demain faite le soir, pour le facteur de correction."""
        now = dt_util.now()
        if now.hour < 18 or not periods:
            return
        tomorrow = (now + timedelta(days=1)).date()
        total = sum(kwh for s, _e, kwh in periods if dt_util.as_local(s).date() == tomorrow)
        self.solar_history[tomorrow.isoformat()] = round(total, 3)
        keep = sorted(self.solar_history)[-(SOLAR_FACTOR_DAYS + 5):]
        self.solar_history = {k: self.solar_history[k] for k in keep}
        self._save()

    # ------------------------------------------------------------ apprentissage
    async def async_learn(self) -> None:
        try:
            await self._async_learn()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Apprentissage impossible")
        self._notify_listeners()

    async def _async_learn(self) -> None:
        hass = self.hass
        weeks = int(self.cfg[CONF_HISTORY_WEEKS])
        end = dt_util.now().replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(weeks=weeks, days=1)
        counters = src.counters_for_device(hass, self.cfg[CONF_BATTERY_DEVICE])
        house = self.cfg.get(CONF_HOUSE_SENSOR)
        # N1 : seule l'énergie des consommateurs que les batteries n'alimentent pas
        # sort du besoin à couvrir
        excluded_loads = [l for l in self.cfg.get(CONF_LOADS) or [] if not l.get(LOAD_BATTERY, True)]
        load_energy = [l.get(LOAD_ENERGY_SENSOR) for l in excluded_loads if l.get(LOAD_ENERGY_SENSOR)]
        # Sources de la consommation : capteur maison, sinon compteurs saisis à la main,
        # sinon ceux du tableau Énergie de Home Assistant (D10)
        flows: dict[str, list[str]] = {k: [] for k in ("import", "export", "solar", "charge", "discharge")}
        if not house:
            if self.cfg.get(CONF_GRID_IMPORT):
                flows["import"] = [self.cfg[CONF_GRID_IMPORT]]
                flows["export"] = [x for x in [self.cfg.get(CONF_GRID_EXPORT)] if x]
                flows["solar"] = [x for x in [self.cfg.get(CONF_SOLAR_ACTUAL)] if x]
            else:
                flows = src.energy_dashboard_stats(await src.async_energy_prefs(hass))
            if not flows["charge"] and not flows["discharge"]:
                flows["charge"] = list(counters.get("energy_charged") or [])
                flows["discharge"] = list(counters.get("energy_discharged") or [])
        self.consumption_source = "house" if house else (
            "manual" if self.cfg.get(CONF_GRID_IMPORT) else ("energy_dashboard" if flows["import"] else "none")
        )
        ids = [house] if house else [x for v in flows.values() for x in v]
        ids = [i for i in ids if i] + load_energy
        sums = await src.async_hourly_sums(hass, ids, start, end)
        changes = {sid: dict(hourly_changes(pts)) for sid, pts in sums.items()}

        def series(sid: str | None) -> dict[datetime, float]:
            return changes.get(sid, {}) if sid else {}

        hourly: dict[datetime, float] = defaultdict(float)
        if house:
            for ts, v in series(house).items():
                hourly[ts] += v
        elif flows["import"]:
            for sid in flows["import"]:
                for ts, v in series(sid).items():
                    hourly[ts] += v
            for sign, sids in (
                (-1, flows["export"]),
                (1, flows["solar"]),
                (-1, flows["charge"]),
                (1, flows["discharge"]),
            ):
                for sid in sids:
                    for ts, v in series(sid).items():
                        if ts in hourly:
                            hourly[ts] += sign * v
        for sid in load_energy:
            for ts, v in series(sid).items():
                if ts in hourly:
                    hourly[ts] -= v
        # Besoin quotidien des ballons (N5), d'après leur énergie routée
        for load in excluded_loads:
            dev, sid = load.get(LOAD_ROUTER), load.get(LOAD_ENERGY_SENSOR)
            if dev and sid:
                days: dict = defaultdict(float)
                for ts, v in series(sid).items():
                    days[ts.date()] += v
                # Jours complets seulement : la journée en cours fausserait la moyenne
                recent = sorted(d for d in days if d < end.date())[-7:]
                if recent:
                    self.router_daily_kwh[dev] = round(sum(days[d] for d in recent) / len(recent), 2)
        self._solar_actual_ids = [self.cfg[CONF_SOLAR_ACTUAL]] if self.cfg.get(CONF_SOLAR_ACTUAL) else flows["solar"]
        self.profile.daily_kwh_fallback = float(self.cfg[CONF_DAILY_KWH])
        self.profile.learn(
            [(ts, max(0.0, v)) for ts, v in hourly.items()], weeks=weeks
        )

        # Rendement aller-retour sur 30 jours
        e_start = end - timedelta(days=EFFICIENCY_DAYS)
        ec = await src.async_hourly_sums(
            hass, counters["energy_charged"] + counters["energy_discharged"], e_start, end
        )

        def total(sids):
            return sum(sum(v for _t, v in hourly_changes(ec.get(s, []))) for s in sids)

        measured = measured_efficiency(
            total(counters["energy_charged"]), total(counters["energy_discharged"]), 0.0
        )
        self.measured_efficiency = measured or None

        # Facteur de correction solaire sur 14 jours
        actual_ids = self._solar_actual_ids
        if actual_ids and self.cfg[CONF_SOLAR_CORRECTION]:
            s_start = end - timedelta(days=SOLAR_FACTOR_DAYS + 1)
            got = await src.async_hourly_sums(hass, actual_ids, s_start, end)
            by_day: dict[str, float] = defaultdict(float)
            for pts in got.values():
                for ts, v in hourly_changes(pts):
                    by_day[ts.date().isoformat()] += v
            pairs = [
                (self.solar_history[d], by_day[d])
                for d in self.solar_history
                if d in by_day and d < end.date().isoformat()
            ]
            self.solar_factor = correction_factor(pairs)
        self._save()

    # ------------------------------------------------------------ pilotage
    async def _control_tick(self, _now=None) -> None:
        self._accumulate_savings()
        await self._async_check_end_of_window()
        if self._observe_full_charge(dt_util.now()):
            await self.async_update_plan()
            return
        await self._async_control()

    def _observe_full_charge(self, now: datetime) -> bool:
        """Note les charges à 100 % (N3). True quand une demande vient de se terminer."""
        done = False
        before = {u: self.fullcharge.last_full.get(u) for u in self.fc_units}
        for dev, eid in self.unit_level.items():
            done |= self.fullcharge.observe(dev, src.state_float(self.hass, eid), now)
        if self.fc_action and any(
            self.fullcharge.last_full.get(u) != before[u] for u in before
        ) and all((self.fullcharge.days(u, now) or 0) < 1 for u in self.fc_units):
            done = True
        self._save()
        return done

    async def _async_control(self) -> None:
        now = dt_util.now()
        if self.auto_control:
            await self._async_control_routers(now)
        await self._async_control_battery(now)
        await self._async_notify_full_charge()

    async def _async_control_battery(self, now: datetime) -> None:
        plan = self.plan
        if not self.battery_piloted or plan is None or not self.sources_ok:
            return
        if plan.state in (PLAN_MISSING_DATA, PLAN_SUSPENDED):
            return  # aucune commande : la batterie garde son dernier mode
        mode = plan.mode_at(now)
        if self.fc_action == ACTION_NOW:
            mode = MODE_GRID_CHARGE  # charge complète demandée tout de suite (N3)
        if mode is None:
            return
        if mode == MODE_OFF and self.calibrating_units:
            mode = MODE_SMART  # pas de batterie à l'arrêt pendant une calibration
        night = plan.window_end.isoformat() if plan.window_end else None
        if mode == MODE_GRID_CHARGE:
            self._charging_night = night
        elif (
            plan.state == PLAN_CHARGE
            and night is not None
            and self._charging_night == night
            and plan.window_start <= now < plan.window_end
        ):
            # Charge déjà commencée cette nuit : le recalcul peut repousser l'heure
            # de début (le SOC a monté), mais on ne s'arrête pas en chemin.
            # La batterie s'arrête seule au SOC cible.
            mode = MODE_GRID_CHARGE
        self._battery_mode = mode
        select_id = self.battery_entities.get("operating_mode")
        current = src.state_str(self.hass, select_id)
        if current == "group":
            # Batterie membre d'un Groupe : c'est le Groupe qu'il faut piloter
            self._issue("member_battery", True, "member_battery")
            return
        self._issue("member_battery", False, "member_battery")
        regulation = src.state_str(self.hass, self.battery_entities.get("regulation_state"))
        self._issue("battery_degraded", regulation == "degraded", "battery_degraded")
        if mode == MODE_GRID_CHARGE:
            await self._set_number("import_limit", self.import_limit)
            target = 100.0 if self.fc_action in (ACTION_NOW, ACTION_TONIGHT) else plan.target_soc
            await self._set_number("charge_target_soc", target)
        if current != mode:
            st = self.hass.states.get(select_id) if select_id else None
            if st is not None and mode in (st.attributes.get("options") or []):
                await self.hass.services.async_call(
                    "select", "select_option", {"entity_id": select_id, "option": mode}, blocking=True
                )
        await self._async_apply_soc(plan, now)
        await self._async_write_ceilings(now)
        await self._async_declare(True, now)

    async def _async_apply_soc(self, plan: Plan, now: datetime) -> None:
        """Réserve de SOC min et SOC max à 100 % (E2), batterie par batterie."""
        if not self.e2_ok:
            return
        writes = self.keeper.writes(self._soc_targets(), now, reserve_at(plan, now), self.full_charge)
        for entity_id, value in writes:
            await self.hass.services.async_call(
                "number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
            )
        if writes:
            self._save()
            self._notify_listeners()

    async def _async_release(self) -> None:
        """Rend leurs réglages aux batteries et retire la déclaration de pilote."""
        for entity_id, value in self.keeper.restore_all():
            try:
                await self.hass.services.async_call(
                    "number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("SOC de %s non restitué : %s", entity_id, err)
        if self.ceilings_ok:
            for key in CEILING_KEYS:
                eid = self.ceiling_entities.get(key)
                value = 0.0 if key == "excluded_power" else self._entity_max(eid)
                if eid and value is not None:
                    try:
                        await self.hass.services.async_call(
                            "number", "set_value", {"entity_id": eid, "value": value}, blocking=True
                        )
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.debug("%s non rendu : %s", eid, err)
        self._written.clear()
        self._save()
        await self._async_declare(False, dt_util.now())

    async def _async_declare(self, active: bool, now: datetime) -> None:
        """Déclaration de pilote externe auprès de Zendure Local (≥ 1.4.0, D6).

        Renouvelée toutes les 15 minutes ; sans renouvellement, Zendure Local
        réaffiche seul ses réglages au bout de 30 minutes.
        """
        if not self.hass.services.has_service(BATTERY_DOMAIN, EXTERNAL_CONTROL_SERVICE):
            return
        if active and self._last_declare and now - self._last_declare < timedelta(
            minutes=EXTERNAL_CONTROL_RENEW_MIN
        ):
            return
        for dev in self.battery_device_ids:
            try:
                await self.hass.services.async_call(
                    BATTERY_DOMAIN,
                    EXTERNAL_CONTROL_SERVICE,
                    {
                        "device_id": dev,
                        "active": active,
                        "controller": CONTROLLER_NAME,
                        "controlled_keys": self.controlled_keys(dev),
                    },
                    blocking=True,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Déclaration de pilote refusée pour %s : %s", dev, err)
        self._last_declare = now if active else None

    # ------------------------------------------------------------ interface (E1)
    @property
    def battery_device_ids(self) -> list[str]:
        target = self.cfg[CONF_BATTERY_DEVICE]
        return [target] + [d for d in self.units if d != target]

    @property
    def controlled_device_ids(self) -> list[str]:
        out = self.battery_device_ids if self.battery_control else []
        return out + [d for d in self._router_sent]

    def controlled_keys(self, device_id: str) -> list[str]:
        keys: list[str] = []
        if device_id == self.cfg[CONF_BATTERY_DEVICE]:
            keys += ["operating_mode", "import_limit", "charge_target_soc"]
            if self.ceilings_ok:
                keys += list(CEILING_KEYS)
        if self.e2_ok and device_id in self.unit_soc:
            keys += list(UNIT_SOC_KEYS)
        return keys

    @property
    def controlled_entities(self) -> list[str]:
        if not self.battery_control:
            return []
        out = [self.battery_entities.get(k) for k in ("operating_mode", "import_limit", "charge_target_soc")]
        if self.ceilings_ok:
            out += [self.ceiling_entities.get(k) for k in CEILING_KEYS]
        if self.e2_ok:
            for dev in self.units:
                out += [self.unit_soc.get(dev, {}).get(k) for k in UNIT_SOC_KEYS]
        return [e for e in out if e]

    @property
    def interface_attributes(self) -> dict[str, Any]:
        return {
            "controlled_device_id": self.cfg[CONF_BATTERY_DEVICE],
            "controlled_device_ids": self.controlled_device_ids,
            "controlled_entities": self.controlled_entities,
            "interface_version": INTERFACE_VERSION,
            # Pour la carte : batteries seules, pilotées ou non (les routeurs n'y figurent pas)
            "battery_device_ids": self.battery_device_ids,
        }

    # ------------------------------------------------------------ puissance à ne pas couvrir (N1)
    def _excluded_loads(self) -> list[dict[str, Any]]:
        return [l for l in self.cfg.get(CONF_LOADS) or [] if not l.get(LOAD_BATTERY, True)]

    def _excluded_sources(self) -> list[str]:
        out = []
        for load in self._excluded_loads():
            out += [load.get(LOAD_POWER_SENSOR), load.get(LOAD_STATE_ENTITY)]
        return [x for x in out if x]

    def _excluded_power_w(self) -> float:
        """Puissance des consommateurs en marche que les batteries ne doivent pas alimenter."""
        total = 0.0
        for load in self._excluded_loads():
            p = src.power_w(self.hass, load.get(LOAD_POWER_SENSOR))
            if p is not None:
                if p > float(load.get(LOAD_THRESHOLD) or (50 if load.get(LOAD_ROUTER) else 100)):
                    total += p
                continue
            if src.state_str(self.hass, load.get(LOAD_STATE_ENTITY)) == "on":
                total += float(load.get(LOAD_POWER) or 0)
        return total

    @callback
    def _on_excluded_change(self, _event: Event) -> None:
        if self._excluded_pending is None:
            self._excluded_pending = async_call_later(self.hass, 10, self._excluded_update)

    async def _excluded_update(self, _now=None) -> None:
        self._excluded_pending = None
        if self.battery_piloted and self.ceilings_ok:
            await self._async_write_ceilings(dt_util.now())

    def _entity_max(self, entity_id: str | None) -> float | None:
        st = self.hass.states.get(entity_id) if entity_id else None
        try:
            value = float(st.attributes.get("max")) if st else None
        except (TypeError, ValueError):
            value = None
        if value is not None:
            self._max_cache[entity_id] = value
        return value if value is not None else self._max_cache.get(entity_id)

    async def _write_key(self, key: str, value: float, now: datetime, *, delta: float) -> None:
        """Écrit un plafond Zendure s'il a assez changé (jamais en flash côté Zendure)."""
        eid = self.ceiling_entities.get(key)
        if eid is None:
            return
        last = self._written.get(key)
        current = src.state_float(self.hass, eid)
        if current is not None and abs(current - value) < 1:
            self._written[key] = (value, now)
            return
        if last and abs(last[0] - value) < delta and now - last[1] < timedelta(minutes=5):
            return
        await self.hass.services.async_call(
            "number", "set_value", {"entity_id": eid, "value": value}, blocking=True
        )
        self._written[key] = (value, now)

    async def _async_write_ceilings(self, now: datetime) -> None:
        """Plafonds de charge / décharge (routeur) et puissance à ne pas couvrir (N1, N5)."""
        if not (self.ceilings_ok and self.battery_piloted):
            return
        # Charge réseau en cours : le plafond « routeur d'abord » est levé
        ceiling, no_discharge = combine(
            list(self.router_decisions.values()), grid_charging=self._battery_mode == MODE_GRID_CHARGE
        )
        if self.calibrating_units:
            no_discharge = False  # jamais de puissance bloquée à 0 W pendant une calibration
        maxc = self._entity_max(self.ceiling_entities.get("charge_power_limit"))
        maxd = self._entity_max(self.ceiling_entities.get("discharge_power_limit"))
        self.excluded_w = self._excluded_power_w()
        try:
            if maxc is not None:
                value = maxc if ceiling is None else min(maxc, ceiling)
                await self._write_key("charge_power_limit", round(value / 10) * 10, now, delta=100)
            if maxd is not None:
                await self._write_key("discharge_power_limit", 0.0 if no_discharge else maxd, now, delta=1)
            await self._write_key("excluded_power", round(self.excluded_w / 10) * 10, now, delta=50)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Plafonds Zendure non écrits : %s", err)

    # ------------------------------------------------------------ routeurs F1ATB (N5)
    async def _async_control_routers(self, now: datetime) -> None:
        if not self.routers:
            self.router_status = []
            return
        hass = self.hass
        has_service = hass.services.has_service(ROUTER_DOMAIN, EXTERNAL_CONTROL_SERVICE)
        b = self.battery_entities
        bat_w = src.state_float(hass, b.get("battery_power"))
        maxc = src.state_float(hass, b.get("max_charge_power")) or self._last_max_charge or 2400.0
        missing = src.state_float(hass, b.get("missing_energy"))
        soc = src.state_float(hass, b.get("electric_level"))
        grid = src.power_w(hass, self.cfg.get(CONF_POWER_SENSOR))
        priority = self.cfg[CONF_ROUTER_PRIORITY]
        surplus = self.tomorrow_surplus_kwh
        range_kwh = self._battery_range_kwh or 0.0
        status = []
        for r in self.routers:
            dev = r["device_id"]
            ents = self.router_entities.get(dev, {})
            connected = src.state_str(hass, ents.get("connected"))
            online = connected == "on" if ents.get("connected") else bool(ents)
            enabled = src.state_str(hass, ents.get("control_enabled")) != "off"
            routed = src.power_w(hass, ents.get("routed_power"))
            load_w = self._router_power_w(dev, ents)
            reached = src.state_str(hass, ents.get("target_reached")) == "on"
            on_slot = self._router_on_slot(ents)
            ballon_sun_ok = self._ballon_sun_ok(dev)
            temperature = src.state_float(hass, ents.get("water_temperature"))
            piloted = (
                self.auto_control and self.router_control.get(dev, True) and online and enabled and has_service
            )
            reason = "offline" if not online else ("display_only" if not enabled else "autonomous")
            # Chauffe déplacée par le Chef (option « Le Chef peut déplacer la chauffe »)
            w = self.router_windows.get(dev)
            shifted = bool(w and w["shifted"] and now < max(w["end"], w["slot_end"]))
            force_heat = False
            if shifted and w["start"] <= now < w["end"]:
                live = on_slot_outlook(temperature, w["t_below"], reached, ballon_sun_ok)
                if live != OUTLOOK_HEAT:
                    self._router_heat_done[dev] = w["start"]  # ballon chaud : fenêtre terminée
                force_heat = live == OUTLOOK_HEAT and self._router_heat_done.get(dev) != w["start"]
            if piloted:
                dec = self.router_logic.setdefault(dev, RouterLogic()).step(
                    RouterInputs(
                        now=now,
                        priority=priority,
                        routed_w=routed,
                        load_w=load_w,
                        target_reached=reached,
                        on_slot=on_slot,
                        battery_w=bat_w,
                        max_charge_w=maxc,
                        all_full=missing is not None and missing <= 0.05,
                        grid_export=grid is not None and grid < -30,
                        soc=soc,
                        summer_soc=float(self.cfg[CONF_SUMMER_SOC]),
                        batteries_sun_ok=surplus is not None and surplus >= range_kwh,
                        ballon_sun_ok=ballon_sun_ok,
                        force_heat=force_heat,
                        slot_shifted=shifted,
                    )
                )
                self.router_decisions[dev] = dec
                reason = dec.reason
                await self._async_router_apply(dev, dec, now)
            else:
                self.router_decisions.pop(dev, None)
                if dev in self._router_sent:
                    await self._async_release_routers([dev])
            status.append(
                {
                    "device_id": dev,
                    "name": r.get("name") or src.device_name(hass, dev),
                    "usage": r.get("usage", "water_heater"),
                    "online": online,
                    "control_enabled": enabled,
                    "piloted": piloted,
                    "switch_on": self.router_control.get(dev, True),
                    "temperature": temperature,
                    "routed_power": routed,
                    "target_reached": reached,
                    "on_slot": on_slot,
                    "state": reason,
                    "next_on": self._router_next_on(dev, ents, now, temperature, reached, ballon_sun_ok),
                }
            )
        self.router_status = status
        await self._async_check_router_threshold(now)

    def _router_power_w(self, device_id: str, ents: dict[str, str]) -> float | None:
        """Puissance du ballon : `load_power`, sinon `water_heater_power` (1.1.x), sinon la saisie."""
        for key in ("load_power", "water_heater_power"):
            value = src.power_w(self.hass, ents.get(key))
            if value:
                return value
        return self._router_load_w(device_id)

    def _router_on_slot(self, ents: dict[str, str]) -> bool:
        """Plage ON du planning : `on_slot_active`, sinon le capteur `planning` (1.1.x), sinon `status`.

        `status` passe à « blocked » dès que le Chef verrouille le routeur : il ne
        montre jamais « on_slot » à un routeur verrouillé, qui restait alors bloqué
        toute la plage ON. `planning` donne la plage du planning, verrouillé ou non.
        """
        if ents.get("on_slot_active"):
            return src.state_str(self.hass, ents["on_slot_active"]) == "on"
        if ents.get("planning"):
            return src.state_str(self.hass, ents["planning"]) == "on"
        return src.state_str(self.hass, ents.get("status")) == "on_slot"

    def _ballon_sun_ok(self, dev: str) -> bool:
        """Le soleil de demain suffit-il à chauffer le ballon (après les batteries en « batteries d'abord ») ?"""
        surplus = self.tomorrow_surplus_kwh
        if surplus is None:
            return False
        need = self.router_daily_kwh.get(dev) or float(self.cfg[CONF_ROUTER_DAILY_KWH])
        spare = surplus - ((self._battery_range_kwh or 0.0) if self.cfg[CONF_ROUTER_PRIORITY] == "battery_first" else 0.0)
        return spare >= need

    def _router_slot(self, ents: dict[str, str], now: datetime) -> tuple[datetime, datetime, float | None] | None:
        state = self.hass.states.get(ents["planning"]) if ents.get("planning") else None
        return next_on_slot(state.attributes.get("slots") if state else None, now)

    def _router_plan_windows(self, now: datetime) -> None:
        """Prochaine plage ON de chaque routeur et ce que le Chef en fera, avant le plan des batteries.

        Une chauffe déplacée qui a commencé ne bouge plus jusqu'à la fin de la plage
        qu'elle remplace : sinon le ballon pourrait chauffer deux fois.
        """
        out: dict[str, dict[str, Any]] = {}
        for r in self.routers:
            dev = r["device_id"]
            ents = self.router_entities.get(dev, {})
            old = self.router_windows.get(dev)
            if old and old["shifted"] and old["start"] <= now < max(old["end"], old["slot_end"]):
                out[dev] = old
                continue
            slot = self._router_slot(ents, now)
            if slot is None:
                continue
            start, end, t_below = slot
            piloted = self.auto_control and self.router_control.get(dev, True)
            out[dev] = {
                "start": start,
                "end": end,
                "slot_start": start,
                "slot_end": end,
                "t_below": t_below,
                "shifted": False,
                "why": None,
                "previous": old["start"] if old and old["shifted"] else None,
                "outlook": on_slot_outlook(
                    src.state_float(self.hass, ents.get("water_temperature")),
                    t_below,
                    src.state_str(self.hass, ents.get("target_reached")) == "on",
                    piloted and self._ballon_sun_ok(dev),
                ),
            }
        self.router_windows = out

    def _router_shift_windows(self, steps: list[Step], plan: Plan, now: datetime) -> bool:
        """Option « Le Chef peut déplacer la chauffe » : place chaque chauffe prévue cette nuit.

        La fenêtre garde la durée de la plage ON, reste dans les mêmes heures creuses
        et évite d'abord un dépassement de la puissance souscrite, puis la charge des
        batteries (charge programmée, charge complète, calibration). Renvoie True si
        une fenêtre a changé : le plan des batteries doit alors être refait.
        """
        if not self.cfg.get(CONF_ROUTER_SHIFT) or not self.auto_control or not steps or not self.import_limit:
            return False
        step_h = STEP_MINUTES / 60
        charge = {sp.start: sp.charge_kwh for sp in plan.steps}
        changed = False
        for r in self.routers:
            dev = r["device_id"]
            w = self.router_windows.get(dev)
            if not w or w["outlook"] != OUTLOOK_HEAT or not self.router_control.get(dev, True):
                continue
            if min(w["start"], w["slot_start"]) <= now:
                continue  # plage ou chauffe déjà commencée
            power = self._router_power_w(dev, self.router_entities.get(dev, {}))
            if not power:
                continue
            night = []
            for st in steps:
                charge_w = charge.get(st.start, 0.0) / step_h * 1000
                busy = st.consumption_kwh / step_h * 1000 + self._loads_w(st.start, now, exclude=dev) + charge_w
                night.append(NightStep(st.start, st.off_peak, busy, charge_w > 0))
            start, end, why = choose_heat_window(
                night, STEP, w["slot_start"], w["slot_end"], power, self.import_limit, w.get("previous")
            )
            shifted = why is not None
            if shifted != w["shifted"] or start != w["start"]:
                changed = True
            w.update(start=start, end=end, shifted=shifted, why=why)
        return changed

    def _router_next_on(
        self, dev: str, ents: dict[str, str], now: datetime, temperature: float | None, reached: bool, sun_ok: bool
    ) -> dict[str, Any] | None:
        """Prochaine chauffe en heures creuses et ce que le Chef en fera (commentaire de la carte Énergie)."""
        w = self.router_windows.get(dev)
        if w is None or now >= max(w["end"], w["slot_end"]):
            slot = self._router_slot(ents, now)
            if slot is None:
                return None
            start, end, t_below = slot
            w = {"start": start, "end": end, "slot_start": start, "slot_end": end, "t_below": t_below, "shifted": False, "why": None}
        outlook = on_slot_outlook(temperature, w["t_below"], reached, sun_ok)
        shifted = w["shifted"] and outlook == OUTLOOK_HEAT
        if shifted and self._router_heat_done.get(dev) == w["start"]:
            outlook, shifted = OUTLOOK_HOT, False
        start, end = (w["start"], w["end"]) if shifted else (w["slot_start"], w["slot_end"])
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "slot_start": w["slot_start"].isoformat(),
            "slot_end": w["slot_end"].isoformat(),
            "t_below": w["t_below"],
            "outlook": outlook,
            "shifted": shifted,
            "why": w["why"] if shifted else None,
        }

    def _router_load_w(self, device_id: str) -> float | None:
        for load in self.cfg.get(CONF_LOADS) or []:
            if load.get(LOAD_ROUTER) == device_id:
                return float(load.get(LOAD_POWER) or 0) or None
        return None

    async def _router_call(self, service: str, data: dict[str, Any]) -> bool:
        try:
            await self.hass.services.async_call(ROUTER_DOMAIN, service, data, blocking=True)
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Routeur %s : %s refusé (%s)", data.get("device_id"), service, err)
            return False

    async def _async_router_apply(self, dev: str, dec: RouterDecision, now: datetime) -> None:
        """Verrouillage : prise de la clé « mode » puis mode « off » en tant que pilote.

        Contrat ha-routeur-f1atb (≥ 1.1.0) : seules `mode`, `boost` et
        `target_temperature` sont acceptées dans `controlled_keys` ; `set_mode`
        doit porter `controller` (sans lui, l'appel est refusé ou change le mode
        de l'utilisateur pour de bon). La prise de main expire seule au bout de
        30 min, d'où le renouvellement toutes les 15 min. Au déverrouillage, la
        main est rendue aussitôt : le routeur reprend le mode de l'utilisateur.

        Chauffe déplacée (v1.3.4) : même prise de main, mode « forced » envoyé
        par le Chef ; le routeur garde sa température de sécurité.
        """
        sent = self._router_sent.get(dev)
        if not dec.lock and not dec.force:
            if sent:
                await self._async_release_routers([dev], reset_logic=False)
            return
        mode = "forced" if dec.force else "off"
        if sent and sent.get("mode", "off") == mode and now - sent["at"] < timedelta(minutes=ROUTER_RENEW_MIN):
            return
        keys = list(ROUTER_CONTROLLED_KEYS)
        ok = await self._router_call(
            EXTERNAL_CONTROL_SERVICE,
            {"device_id": dev, "active": True, "controller": CONTROLLER_NAME, "controlled_keys": keys},
        )
        if ok:
            ok = await self._router_call(
                "set_mode", {"device_id": dev, "mode": mode, "controller": CONTROLLER_NAME}
            )
        if ok:
            self._router_sent[dev] = {"keys": keys, "lock": dec.lock, "mode": mode, "at": now}

    async def _async_release_routers(self, devices: list[str] | None = None, *, reset_logic: bool = True) -> None:
        for dev in list(devices if devices is not None else self._router_sent):
            if dev in self._router_sent:
                await self._router_call(
                    EXTERNAL_CONTROL_SERVICE,
                    {"device_id": dev, "active": False, "controller": CONTROLLER_NAME},
                )
                self._router_sent.pop(dev, None)
            if reset_logic:
                self.router_decisions.pop(dev, None)
                if dev in self.router_logic:
                    self.router_logic[dev] = RouterLogic()

    async def _async_check_router_threshold(self, now: datetime) -> None:
        """Seuil Pw du routeur au moins 20 W sous la cible des batteries (0 W), chaque heure."""
        if self._router_threshold_check and now - self._router_threshold_check < timedelta(hours=1):
            return
        self._router_threshold_check = now
        bad = []
        for r in self.routers:
            value = src.state_float(self.hass, self.router_entities.get(r["device_id"], {}).get("routing_power_threshold"))
            if value is not None and value > -20:
                bad.append(f"{r.get('name') or r['device_id']} ({value:g} W)")
        self._issue("router_threshold", bool(bad), "router_threshold", {"routers": ", ".join(bad)})

    # ------------------------------------------------------------ charge complète (N3)
    def full_charge_now_estimate(self) -> dict[str, float | None]:
        """Énergie à acheter et coût estimé d'une charge complète immédiate (confirmation de la carte)."""
        e = self.battery_entities
        cap = src.state_float(self.hass, e.get("usable_capacity"))
        soc = src.state_float(self.hass, e.get("electric_level"))
        price = src.state_float(self.hass, self.tariff_entities.get("prix_actuel"))
        if not cap or soc is None:
            return {"full_charge_now_kwh": None, "full_charge_now_cost": None}
        kwh = max(0.0, cap * (100 - soc) / 100) / max(0.5, self.efficiency_used ** 0.5)
        return {
            "full_charge_now_kwh": round(kwh, 2),
            "full_charge_now_cost": round(kwh * price, 2) if price is not None else None,
        }

    async def _async_notify_full_charge(self) -> None:
        action = self.fc_action
        if action not in (ACTION_SUN, ACTION_TONIGHT, ACTION_NOW):
            return
        key = action + "|" + ",".join(sorted(self.fullcharge.last_full.get(u, "") for u in self.fc_units))
        if self._fc_notified == key or self.cfg[CONF_NOTIFY_LEVEL] == "none":
            return
        self._fc_notified = key
        self._save()
        names = ", ".join(src.device_name(self.hass, u) for u in self.fc_units) or "-"
        await self._async_send(f"notify_full_charge_{action}", {"batteries": names})

    # ------------------------------------------------------------ puissance au tableau
    @property
    def board_power_w(self) -> float | None:
        return src.power_w(self.hass, self.cfg.get(CONF_POWER_SENSOR))

    def running_loads(self) -> list[dict[str, Any]]:
        now = dt_util.now()
        out = []
        for load in self.cfg.get(CONF_LOADS) or []:
            p = src.power_w(self.hass, load.get(LOAD_POWER_SENSOR))
            st = src.state_str(self.hass, load.get(LOAD_STATE_ENTITY))
            running = None
            if p is not None:
                running = p > float(load.get(LOAD_THRESHOLD) or 100)
            elif st is not None:
                running = st == "on"
            out.append(
                {
                    "name": load.get(LOAD_NAME),
                    "power_w": float(load.get(LOAD_POWER) or 0),
                    "current_w": p,
                    "running": running,
                    "usual_now": in_window(now, parse_window(load.get(LOAD_WINDOW))),
                    "battery": bool(load.get(LOAD_BATTERY, True)),
                    "router": load.get(LOAD_ROUTER),
                }
            )
        return out

    async def _set_number(self, key: str, value: float | None) -> None:
        entity_id = self.battery_entities.get(key)
        if entity_id is None or value is None:
            return
        current = src.state_float(self.hass, entity_id)
        if current is not None and abs(current - value) < 0.5:
            return
        await self.hass.services.async_call(
            "number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
        )

    def _accumulate_savings(self) -> None:
        """Économies du mois : énergie rendue × prix du moment, moins la charge réseau."""
        now = dt_util.now()
        month = now.strftime("%Y-%m")
        if month != self._savings_month:
            self._savings_month, self.monthly_savings = month, 0.0
        last, self._last_tick = self._last_tick, now
        if last is None:
            return
        hours = min((now - last).total_seconds(), 300) / 3600
        power = src.state_float(self.hass, self.battery_entities.get("battery_power"))
        price = src.state_float(self.hass, self.tariff_entities.get("prix_actuel"))
        if power is None or price is None:
            return
        mode = src.state_str(self.hass, self.battery_entities.get("operating_mode"))
        if power < 0:
            self.monthly_savings += -power / 1000 * hours * price
        elif power > 0 and mode == MODE_GRID_CHARGE:
            self.monthly_savings -= power / 1000 * hours * price
        self._save()
        self._notify_listeners()

    # ------------------------------------------------------------ notifications
    async def _async_after_plan(self) -> None:
        plan = self.plan
        if plan is None or plan.window_start is None or not self.auto_control:
            return
        now = dt_util.now()
        key = plan.window_end.isoformat()
        level = self.cfg[CONF_NOTIFY_LEVEL]
        if plan.state == PLAN_CHARGE:
            self._watch = {"end": plan.window_end.isoformat(), "target": plan.target_soc}
            self._save()
        if (
            level == "all"
            and self._notified.get("plan") != key
            and plan.window_start - timedelta(hours=1) <= now < plan.window_end
            and plan.state in (PLAN_CHARGE, PLAN_IDLE, PLAN_NOT_PROFITABLE)
        ):
            self._notified["plan"] = key
            await self._async_send_plan(plan)
        if level in ("all", "alerts") and plan.power_alert and self._notified.get("alert") != key:
            if plan.window_start - timedelta(hours=3) <= now < plan.window_end:
                self._notified["alert"] = key
                await self._async_send(
                    "notify_power_alert", {"limit": self._fmt_w(self.import_limit or 0)}
                )
        self._save()

    async def _async_check_end_of_window(self) -> None:
        watch = self._watch
        if not watch:
            return
        end = dt_util.parse_datetime(watch.get("end", ""))
        if end is None or dt_util.now() < end:
            return
        self._watch = None
        self._save()
        soc = src.state_float(self.hass, self.battery_entities.get("electric_level"))
        target = watch.get("target")
        if (
            soc is not None
            and target is not None
            and soc < target - 3
            and self.cfg[CONF_NOTIFY_LEVEL] in ("all", "alerts")
        ):
            await self._async_send(
                "notify_charge_unfinished", {"soc": self._fmt_num(soc, 0), "target": self._fmt_num(target, 0)}
            )

    async def _async_send_plan(self, plan: Plan) -> None:
        if plan.state == PLAN_CHARGE:
            await self._async_send(
                "notify_plan_charge",
                {
                    "energy": self._fmt_kwh(plan.grid_energy_kwh),
                    "soc": self._fmt_num(plan.target_soc or 0, 0),
                    "start": self._fmt_time(plan.charge_start),
                    "gain": self._fmt_eur(plan.forecast_gain_eur),
                },
            )
        elif plan.state == PLAN_NOT_PROFITABLE:
            await self._async_send("notify_plan_not_profitable", {})
        else:
            await self._async_send("notify_plan_idle", {})

    async def _async_send(self, key: str, placeholders: dict[str, str]) -> None:
        service = (self.cfg.get(CONF_NOTIFY_SERVICE) or "").strip()
        if not service or self.cfg[CONF_NOTIFY_LEVEL] == "none":
            return
        service = service.removeprefix("notify.")
        lang = self.hass.config.language
        texts = await async_get_translations(self.hass, lang, "exceptions", {DOMAIN})
        if not texts and lang != "en":
            texts = await async_get_translations(self.hass, "en", "exceptions", {DOMAIN})
        base = f"component.{DOMAIN}.exceptions"
        message = texts.get(f"{base}.{key}.message", key)
        title = texts.get(f"{base}.notify_title.message", "Chef d'orchestre")
        try:
            message = message.format(**placeholders)
        except (KeyError, IndexError):
            pass
        try:
            await self.hass.services.async_call(
                "notify", service, {"title": title, "message": message}, blocking=False
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Notification impossible (%s) : %s", service, err)

    # formats selon la langue de Home Assistant
    @property
    def _fr(self) -> bool:
        return (self.hass.config.language or "en").startswith("fr")

    def _fmt_num(self, v: float, digits: int = 1) -> str:
        text = f"{v:.{digits}f}"
        return text.replace(".", ",") if self._fr else text

    def _fmt_kwh(self, v: float) -> str:
        return f"{self._fmt_num(v)} kWh"

    def _fmt_w(self, v: float) -> str:
        return f"{int(round(v))} W"

    def _fmt_eur(self, v: float) -> str:
        return f"{self._fmt_num(v, 2)} €" if self._fr else f"€{v:.2f}"

    def _fmt_time(self, when: datetime | None) -> str:
        if when is None:
            return "-"
        when = dt_util.as_local(when)
        if self._fr:
            return f"{when.hour} h {when.minute:02d}"
        hour12 = when.hour % 12 or 12
        return f"{hour12}:{when.minute:02d} {'AM' if when.hour < 12 else 'PM'}"
