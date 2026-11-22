"""Chef d'orchestre : lit les sources, calcule le plan, pilote la batterie."""

from __future__ import annotations

from collections import defaultdict
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
    CONF_SOLAR_ACTUAL,
    CONF_SOLAR_CORRECTION,
    CONF_SOLAR_ENTRIES,
    CONF_SUBSCRIBED_KVA,
    CONF_TARIFF_ENTRY,
    CONF_TEMPO_ASSUMPTION,
    CONF_THREE_PHASE,
    CONF_WEAR,
    CONTROL_INTERVAL_S,
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
from .planner import (
    MODE_GRID_CHARGE,
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
    compute_plan,
    import_limit_w,
)
from .timeline import (
    at,
    fill_unknown_prices,
    in_window,
    parse_segments,
    parse_window,
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
        self.auto_control = True
        self.profile_name: str = self.cfg[CONF_PROFILE]
        self.gain_threshold: float = float(self.cfg[CONF_GAIN_THRESHOLD])
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
        self.tariff_entities: dict[str, str] = {}
        self.battery_entities: dict[str, str] = {}
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[Callable[[], None]] = []
        self._pending: Callable[[], None] | None = None
        self._lock_busy = False

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

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._pending:
            self._pending()
        await self._store.async_save(self._dump())

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    @callback
    def _notify_listeners(self) -> None:
        for cb in list(self._listeners):
            cb()

    # ------------------------------------------------------------ mémoire
    def _restore(self, data: dict) -> None:
        self.auto_control = data.get("auto_control", True)
        seen = data.get("options_seen", {})
        # Une valeur changée dans les options l'emporte sur la valeur à chaud
        if seen.get(CONF_PROFILE) == self.cfg[CONF_PROFILE] and data.get("profile") in PROFILES:
            self.profile_name = data["profile"]
        if seen.get(CONF_GAIN_THRESHOLD) == self.cfg[CONF_GAIN_THRESHOLD] and "gain_threshold" in data:
            self.gain_threshold = float(data["gain_threshold"])
        self.measured_efficiency = data.get("measured_efficiency")
        self.solar_factor = float(data.get("solar_factor", 1.0))
        self.solar_history = dict(data.get("solar_history", {}))
        self.monthly_savings = float(data.get("monthly_savings", 0.0))
        self._savings_month = data.get("savings_month", "")
        self._notified = dict(data.get("notified", {}))
        self._watch = data.get("watch")
        self._charging_night = data.get("charging_night")
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
            "options_seen": {
                CONF_PROFILE: self.cfg[CONF_PROFILE],
                CONF_GAIN_THRESHOLD: self.cfg[CONF_GAIN_THRESHOLD],
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
        }

    def _save(self) -> None:
        self._store.async_delay_save(self._dump, 30)

    # ------------------------------------------------------------ réglages à chaud
    async def async_set_auto_control(self, on: bool) -> None:
        self.auto_control = on
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
            ok &= good

        self.tariff_entities = src.find_entities(
            self.hass, TARIFF_DOMAIN, TARIFF_KEYS, config_entry_id=self.cfg[CONF_TARIFF_ENTRY]
        )
        self.battery_entities = src.find_entities(
            self.hass, BATTERY_DOMAIN, BATTERY_KEYS, device_id=self.cfg[CONF_BATTERY_DEVICE]
        )
        missing = [k for k in TARIFF_REQUIRED if k not in self.tariff_entities]
        missing += [k for k in BATTERY_KEYS if k not in self.battery_entities]
        self._issue(
            "missing_entities", bool(missing), "missing_entities", {"keys": ", ".join(missing)}
        )
        ok &= not missing
        self.sources_ok = ok

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

    def _loads_w(self, when: datetime, now: datetime) -> float:
        total = 0.0
        for load in self.cfg.get(CONF_LOADS) or []:
            power = float(load.get(LOAD_POWER) or 0)
            running = False
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
            self.plan = Plan(PLAN_MISSING_DATA, REASON_MISSING_DATA)
        finally:
            self._lock_busy = False
        self._notify_listeners()
        await self._async_after_plan()
        await self._async_control()

    async def _async_compute(self) -> Plan:
        if not self.sources_ok:
            return Plan(PLAN_MISSING_DATA, REASON_MISSING_DATA)
        now = dt_util.now()
        starts = step_starts(now, HORIZON_HOURS, STEP_MINUTES)
        try:
            resp = await src.async_tariff_forecast(
                self.hass, self.cfg[CONF_TARIFF_ENTRY], HORIZON_HOURS
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Prévisions tarifaires indisponibles : %s", err)
            return Plan(PLAN_MISSING_DATA, REASON_MISSING_DATA)
        segments = parse_segments(resp or {})
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
        factor = self.solar_factor if self.cfg[CONF_SOLAR_CORRECTION] else 1.0
        solar = [v * factor for v in spread(periods, starts, STEP)]
        self._remember_solar(periods)

        battery = self._battery()
        kva = self._subscribed_kva()
        self.subscribed_kva = kva
        if battery is None or kva is None:
            return Plan(PLAN_MISSING_DATA, REASON_MISSING_DATA)
        margin = max(float(self.cfg[CONF_MARGIN]), 10.0) / 100
        self.import_limit = import_limit_w(kva, margin, bool(self.cfg[CONF_THREE_PHASE]))

        steps: list[Step] = []
        per_step = STEP_MINUTES / 60
        for i, t in enumerate(starts):
            seg = at(segments, t)
            if seg is None:
                break  # au-delà de l'horizon des tarifs
            steps.append(
                Step(
                    start=t,
                    consumption_kwh=self.profile.hour_kwh(t) * per_step,
                    solar_kwh=solar[i],
                    price=seg.price,
                    off_peak=seg.off_peak,
                    loads_w=self._loads_w(t, now),
                )
            )
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
        plan = compute_plan(steps, battery, settings, override)
        if not self.auto_control:
            plan.state = PLAN_SUSPENDED
        return plan

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
        load_energy = [l.get(LOAD_ENERGY_SENSOR) for l in self.cfg.get(CONF_LOADS) or []]
        load_energy = [x for x in load_energy if x]
        ids = [house] if house else [
            self.cfg.get(CONF_GRID_IMPORT),
            self.cfg.get(CONF_GRID_EXPORT),
            self.cfg.get(CONF_SOLAR_ACTUAL),
            *counters["energy_charged"],
            *counters["energy_discharged"],
        ]
        ids = [i for i in ids if i] + load_energy
        sums = await src.async_hourly_sums(hass, ids, start, end)
        changes = {sid: dict(hourly_changes(pts)) for sid, pts in sums.items()}

        def series(sid: str | None) -> dict[datetime, float]:
            return changes.get(sid, {}) if sid else {}

        hourly: dict[datetime, float] = defaultdict(float)
        if house:
            for ts, v in series(house).items():
                hourly[ts] += v
        elif self.cfg.get(CONF_GRID_IMPORT):
            for ts, v in series(self.cfg.get(CONF_GRID_IMPORT)).items():
                hourly[ts] += v
            for sign, sids in (
                (-1, [self.cfg.get(CONF_GRID_EXPORT)]),
                (1, [self.cfg.get(CONF_SOLAR_ACTUAL)]),
                (-1, counters["energy_charged"]),
                (1, counters["energy_discharged"]),
            ):
                for sid in sids:
                    for ts, v in series(sid).items():
                        if ts in hourly:
                            hourly[ts] += sign * v
        for sid in load_energy:
            for ts, v in series(sid).items():
                if ts in hourly:
                    hourly[ts] -= v
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
        actual_id = self.cfg.get(CONF_SOLAR_ACTUAL)
        if actual_id and self.cfg[CONF_SOLAR_CORRECTION]:
            s_start = end - timedelta(days=SOLAR_FACTOR_DAYS + 1)
            pts = (await src.async_hourly_sums(hass, [actual_id], s_start, end)).get(actual_id, [])
            by_day: dict[str, float] = defaultdict(float)
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
        await self._async_control()

    async def _async_control(self) -> None:
        plan = self.plan
        if not self.auto_control or plan is None or not self.sources_ok:
            return
        if plan.state in (PLAN_MISSING_DATA, PLAN_SUSPENDED):
            return  # aucune commande : la batterie garde son dernier mode
        now = dt_util.now()
        mode = plan.mode_at(now)
        if mode is None:
            return
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
            await self._set_number("charge_target_soc", plan.target_soc)
        if current != mode:
            st = self.hass.states.get(select_id) if select_id else None
            if st is None or mode not in (st.attributes.get("options") or []):
                return
            await self.hass.services.async_call(
                "select", "select_option", {"entity_id": select_id, "option": mode}, blocking=True
            )

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
