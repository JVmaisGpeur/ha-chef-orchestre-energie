"""Assistant d'installation unique (E4, routeurs en v1.3.0) et options."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr, selector

from . import sources as src
from .const import (
    BATTERY_DOMAIN,
    BATTERY_MIN_VERSION,
    CONF_AUTO_START,
    CONF_BATTERY_DEVICE,
    CONF_DAILY_KWH,
    CONF_EFFICIENCY,
    CONF_FINISH_ADVANCE,
    CONF_FULL_CHARGE_AUTO,
    CONF_FULL_CHARGE_DAYS,
    CONF_ROUTER_DAILY_KWH,
    CONF_ROUTER_PRIORITY,
    CONF_ROUTERS,
    CONF_SUMMER_SOC,
    LOAD_BATTERY,
    LOAD_ROUTER,
    ROUTER_DOMAIN,
    ROUTER_KEYS,
    ROUTER_PRIORITIES,
    ROUTER_USAGES,
    CONF_GAUGE_CRIT,
    CONF_GAUGE_WARN,
    CONF_GAIN_THRESHOLD,
    CONF_GRID_EXPORT,
    CONF_GRID_IMPORT,
    CONF_HISTORY_WEEKS,
    CONF_HOUSE_SENSOR,
    CONF_LOADS,
    CONF_MARGIN,
    CONF_NOTIFY_LEVEL,
    CONF_NOTIFY_SERVICE,
    CONF_POWER_SENSOR,
    CONF_PROFILE,
    CONF_RESERVE_SOC,
    CONF_SOLAR_ACTUAL,
    CONF_SOLAR_CORRECTION,
    CONF_SOLAR_ENTRIES,
    CONF_SUBSCRIBED_KVA,
    CONF_TARIFF_ENTRY,
    CONF_TEMPO_ASSUMPTION,
    CONF_THREE_PHASE,
    CONF_WEAR,
    DEFAULTS,
    DOMAIN,
    LOAD_ENERGY_SENSOR,
    LOAD_KIND,
    LOAD_KINDS,
    LOAD_NAME,
    LOAD_POWER,
    LOAD_POWER_SENSOR,
    LOAD_STATE_ENTITY,
    LOAD_THRESHOLD,
    LOAD_WINDOW,
    MIN_MARGIN,
    NOTIFY_LEVELS,
    PROFILES,
    TARIFF_DOMAIN,
    TARIFF_MIN_VERSION,
    TEMPO_COLORS,
)

URL_TARIFF = "https://github.com/JVmaisGpeur/ha-tarifs-electricite"
URL_BATTERY = "https://github.com/JVmaisGpeur/ha-zendure-solarflow-local"
URL_SOLAR = "https://www.home-assistant.io/integrations/forecast_solar/"
URL_ROUTER = "https://github.com/JVmaisGpeur/ha-routeur-f1atb"

ENERGY_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
)
POWER_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power")
)
OPTIONAL_ENTITIES = (
    CONF_HOUSE_SENSOR,
    CONF_GRID_IMPORT,
    CONF_GRID_EXPORT,
    CONF_SOLAR_ACTUAL,
    CONF_SUBSCRIBED_KVA,
)


def _num(lo: float, hi: float, step: float, unit: str | None = None) -> selector.NumberSelector:
    # unit_of_measurement doit être absent, pas None : Home Assistant refuse None et
    # l'écran ne s'ouvre pas (bug du menu Avancé, v1.2.0).
    kwargs: dict[str, Any] = {"min": lo, "max": hi, "step": step, "mode": selector.NumberSelectorMode.BOX}
    if unit:
        kwargs["unit_of_measurement"] = unit
    return selector.NumberSelector(selector.NumberSelectorConfig(**kwargs))


def _choice(options: list[str], key: str) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, translation_key=key, mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


def _opt(key: str, cur: dict, default: Any = None) -> vol.Optional:
    """Champ facultatif qui peut être vidé (suggested_value plutôt que default)."""
    value = cur.get(key, default)
    return vol.Optional(key, description={"suggested_value": value} if value not in (None, "") else None)


def _list(options: list[tuple[str, str]], multiple: bool = False) -> selector.SelectSelector:
    """Liste simple : le sélecteur le plus sûr à afficher, sur ordinateur comme sur mobile."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[selector.SelectOptionDict(value=v, label=l) for v, l in options],
            multiple=multiple,
            mode=selector.SelectSelectorMode.LIST if multiple else selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _tariff_options(hass) -> list[tuple[str, str]]:
    return [(e.entry_id, e.title) for e in hass.config_entries.async_entries(TARIFF_DOMAIN)]


def _battery_options(hass) -> list[tuple[str, str]]:
    """Appareils de ha-zendure-solarflow-local : batteries seules et Groupes."""
    reg = dr.async_get(hass)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in hass.config_entries.async_entries(BATTERY_DOMAIN):
        for dev in dr.async_entries_for_config_entry(reg, entry.entry_id):
            if dev.id in seen:
                continue
            seen.add(dev.id)
            out.append((dev.id, dev.name_by_user or dev.name or entry.title))
    return out


def _default(cur: dict, key: str, options: list[tuple[str, str]]):
    values = [v for v, _ in options]
    if cur.get(key) in values:
        return cur[key]
    return values[0] if len(values) == 1 else vol.UNDEFINED


def _sources_schema(hass, cur: dict, only_multiple: bool = False) -> vol.Schema:
    """Choix des sources. Dans l'assistant, seules les listes à plusieurs choix sont montrées."""
    solar = src.solar_entries(hass)
    tariffs = _tariff_options(hass)
    batteries = _battery_options(hass)
    solar_ids = [e for e, _ in solar]
    solar_default = [e for e in cur.get(CONF_SOLAR_ENTRIES) or solar_ids if e in solar_ids] or solar_ids
    fields: dict = {}
    if tariffs and (len(tariffs) > 1 or not only_multiple):
        fields[vol.Optional(CONF_TARIFF_ENTRY, default=_default(cur, CONF_TARIFF_ENTRY, tariffs))] = _list(tariffs)
    if len(batteries) > 1 or not only_multiple:
        fields[vol.Required(CONF_BATTERY_DEVICE, default=_default(cur, CONF_BATTERY_DEVICE, batteries))] = _list(batteries)
    if len(solar) > 1 or not only_multiple:
        fields[vol.Required(CONF_SOLAR_ENTRIES, default=solar_default)] = _list(solar, multiple=True)
    return vol.Schema(fields)


def _auto_sources(hass) -> dict[str, Any]:
    """Sources uniques choisies d'office (E4 : pas de question inutile)."""
    out: dict[str, Any] = {}
    tariffs = _tariff_options(hass)
    batteries = _battery_options(hass)
    solar = src.solar_entries(hass)
    out[CONF_TARIFF_ENTRY] = tariffs[0][0] if len(tariffs) == 1 else None
    if len(batteries) == 1:
        out[CONF_BATTERY_DEVICE] = batteries[0][0]
    out[CONF_SOLAR_ENTRIES] = [e for e, _ in solar]
    return out


def _consumption_schema(cur: dict) -> vol.Schema:
    """Réglage manuel facultatif : par défaut, la consommation vient du tableau Énergie."""
    return vol.Schema(
        {
            _opt(CONF_HOUSE_SENSOR, cur): ENERGY_SENSOR,
            _opt(CONF_GRID_IMPORT, cur): ENERGY_SENSOR,
            _opt(CONF_GRID_EXPORT, cur): ENERGY_SENSOR,
            _opt(CONF_SOLAR_ACTUAL, cur): ENERGY_SENSOR,
            vol.Required(CONF_DAILY_KWH, default=cur.get(CONF_DAILY_KWH, DEFAULTS[CONF_DAILY_KWH])): _num(1, 150, 0.5, "kWh"),
        }
    )


def _profit_schema(cur: dict) -> vol.Schema:
    """Écran Rentabilité de l'assistant."""
    return vol.Schema(
        {
            vol.Required(
                CONF_GAIN_THRESHOLD, default=cur.get(CONF_GAIN_THRESHOLD, DEFAULTS[CONF_GAIN_THRESHOLD])
            ): _num(0, 1, 0.005, "EUR/kWh"),
            vol.Required(CONF_EFFICIENCY, default=cur.get(CONF_EFFICIENCY, DEFAULTS[CONF_EFFICIENCY])): _num(50, 100, 1, "%"),
            vol.Required(CONF_RESERVE_SOC, default=cur.get(CONF_RESERVE_SOC, DEFAULTS[CONF_RESERVE_SOC])): _num(0, 50, 5, "%"),
        }
    )


def _economy_schema(cur: dict) -> vol.Schema:
    return _profit_schema(cur).extend(
        {
            vol.Required(CONF_WEAR, default=cur.get(CONF_WEAR, DEFAULTS[CONF_WEAR])): _num(0, 1, 0.005, "EUR/kWh"),
            vol.Required(CONF_PROFILE, default=cur.get(CONF_PROFILE, DEFAULTS[CONF_PROFILE])): _choice(
                list(PROFILES), "profile"
            ),
        }
    )


def _measure_schema(cur: dict) -> vol.Schema:
    """Écran Mesure de puissance de l'assistant."""
    return vol.Schema({_opt(CONF_POWER_SENSOR, cur): POWER_SENSOR})


def _power_schema(cur: dict) -> vol.Schema:
    return vol.Schema(
        {
            _opt(CONF_POWER_SENSOR, cur): POWER_SENSOR,
            vol.Required(CONF_GAUGE_WARN, default=cur.get(CONF_GAUGE_WARN, DEFAULTS[CONF_GAUGE_WARN])): _num(50, 100, 1, "%"),
            vol.Required(CONF_GAUGE_CRIT, default=cur.get(CONF_GAUGE_CRIT, DEFAULTS[CONF_GAUGE_CRIT])): _num(50, 100, 1, "%"),
            _opt(CONF_SUBSCRIBED_KVA, cur): _num(1, 36, 1, "kVA"),
            vol.Required(CONF_THREE_PHASE, default=cur.get(CONF_THREE_PHASE, False)): selector.BooleanSelector(),
            vol.Required(CONF_MARGIN, default=cur.get(CONF_MARGIN, DEFAULTS[CONF_MARGIN])): _num(MIN_MARGIN, 50, 1, "%"),
        }
    )


def _gauge_errors(user_input: dict) -> dict[str, str]:
    if user_input.get(CONF_GAUGE_WARN, 0) >= user_input.get(CONF_GAUGE_CRIT, 100):
        return {CONF_GAUGE_CRIT: "gauge_order"}
    return {}


def _load_schema(cur: dict, with_more: bool = False) -> vol.Schema:
    """Gros consommateur : nom, type, puissance en kW, capteur de détection facultatif."""
    power_kw = cur.get(LOAD_POWER)
    fields = {
        vol.Required(LOAD_NAME, default=cur.get(LOAD_NAME, vol.UNDEFINED)): selector.TextSelector(),
        vol.Required(LOAD_KIND, default=cur.get(LOAD_KIND, "water_heater")): _choice(LOAD_KINDS, "load_kind"),
        vol.Required("power_kw", default=round(power_kw / 1000, 2) if power_kw else 3.0): _num(0.1, 22, 0.1, "kW"),
        _opt(LOAD_POWER_SENSOR, cur): POWER_SENSOR,
        _opt(LOAD_STATE_ENTITY, cur): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["switch", "binary_sensor", "input_boolean"])
        ),
        vol.Required(LOAD_BATTERY, default=bool(cur.get(LOAD_BATTERY, True))): selector.BooleanSelector(),
    }
    if with_more:
        fields[vol.Required("add_another", default=False)] = selector.BooleanSelector()
    return vol.Schema(fields)


def _load_from_input(user_input: dict, previous: dict | None = None) -> dict:
    load = dict(previous or {})
    load.update(
        {
            LOAD_NAME: user_input[LOAD_NAME].strip(),
            LOAD_KIND: user_input.get(LOAD_KIND, "other"),
            LOAD_POWER: round(float(user_input["power_kw"]) * 1000),
            LOAD_POWER_SENSOR: user_input.get(LOAD_POWER_SENSOR) or None,
            LOAD_STATE_ENTITY: user_input.get(LOAD_STATE_ENTITY) or None,
            LOAD_BATTERY: bool(user_input.get(LOAD_BATTERY, True)),
        }
    )
    load.setdefault(LOAD_THRESHOLD, 100)
    load.setdefault(LOAD_ENERGY_SENSOR, None)
    load.setdefault(LOAD_WINDOW, None)
    return load


def _guess_usage(name: str) -> str:
    low = name.lower()
    if "piscine" in low or "pool" in low:
        return "pool"
    if "chauff" in low and "eau" not in low or "heating" in low or "radiat" in low:
        return "heating"
    return "water_heater"


def _router_load(hass, router: dict[str, Any], previous: dict | None = None) -> dict:
    """Ligne « gros consommateur » d'un routeur (N5) : préremplie, batteries à non."""
    ents = src.find_entities(hass, ROUTER_DOMAIN, ROUTER_KEYS, device_id=router["device_id"])
    power = src.power_w(hass, ents.get("load_power")) or src.power_w(hass, ents.get("water_heater_power"))
    load = dict(previous or {})
    load.setdefault(LOAD_BATTERY, False)
    load.update(
        {
            LOAD_NAME: load.get(LOAD_NAME) or router["name"],
            LOAD_KIND: "water_heater" if router.get("usage") == "water_heater" else "other",
            LOAD_POWER: load.get(LOAD_POWER) or round(power or 2400),
            LOAD_POWER_SENSOR: ents.get("routed_power"),
            LOAD_STATE_ENTITY: None,
            LOAD_THRESHOLD: 50,
            LOAD_ENERGY_SENSOR: ents.get("routed_energy_total"),
            LOAD_WINDOW: None,
            LOAD_ROUTER: router["device_id"],
        }
    )
    return load


def _sync_router_loads(hass, loads: list[dict], routers: list[dict]) -> list[dict]:
    """Une ligne par routeur retenu ; les lignes des routeurs retirés disparaissent."""
    wanted = {r["device_id"]: r for r in routers}
    out, seen = [], set()
    for load in loads:
        dev = load.get(LOAD_ROUTER)
        if dev is None:
            out.append(load)
        elif dev in wanted:
            out.append(_router_load(hass, wanted[dev], load))
            seen.add(dev)
    out += [_router_load(hass, r) for dev, r in wanted.items() if dev not in seen]
    return out


def _routers_schema(hass, cur: dict, devices: list[tuple[str, str]], extended: bool = False) -> vol.Schema:
    chosen = [r["device_id"] for r in cur.get(CONF_ROUTERS) or []]
    default = [d for d in chosen if d in dict(devices)] if cur.get(CONF_ROUTERS) is not None else [d for d, _ in devices]
    fields = {
        vol.Optional(CONF_ROUTERS, default=default): _list(devices, multiple=True),
        vol.Required(CONF_ROUTER_PRIORITY, default=cur.get(CONF_ROUTER_PRIORITY, DEFAULTS[CONF_ROUTER_PRIORITY])): _choice(
            ROUTER_PRIORITIES, "router_priority"
        ),
    }
    if extended:
        fields[vol.Required(CONF_SUMMER_SOC, default=cur.get(CONF_SUMMER_SOC, DEFAULTS[CONF_SUMMER_SOC]))] = _num(50, 100, 1, "%")
        fields[vol.Required(CONF_ROUTER_DAILY_KWH, default=cur.get(CONF_ROUTER_DAILY_KWH, DEFAULTS[CONF_ROUTER_DAILY_KWH]))] = _num(0.5, 20, 0.5, "kWh")
    return vol.Schema(fields)


def _routers_from_input(devices: list[tuple[str, str]], ids: list[str], previous: list[dict]) -> list[dict]:
    names = dict(devices)
    old = {r["device_id"]: r for r in previous or []}
    return [
        {"device_id": d, "name": names.get(d, d), "usage": old.get(d, {}).get("usage") or _guess_usage(names.get(d, ""))}
        for d in ids
        if d in names
    ]


def _placeholders() -> dict[str, str]:
    return {
        "tariff_url": URL_TARIFF,
        "battery_url": URL_BATTERY,
        "solar_url": URL_SOLAR,
        "tariff_min": TARIFF_MIN_VERSION,
        "battery_min": BATTERY_MIN_VERSION,
        "router_url": URL_ROUTER,
    }


def _mark(found: str | None, minimum: str | None) -> str:
    if found is None:
        return "❌"
    if minimum and not src.version_ok(found, minimum):
        return f"⚠️ {found}"
    return f"✅ {found}"


async def _detection(hass) -> dict[str, str]:
    """Intégrations trouvées et leurs versions, pour l'écran Détection."""
    tariff = await src.async_integration_version(hass, TARIFF_DOMAIN) if hass.config_entries.async_entries(TARIFF_DOMAIN) else None
    battery = await src.async_integration_version(hass, BATTERY_DOMAIN) if hass.config_entries.async_entries(BATTERY_DOMAIN) else None
    solar = src.solar_entries(hass)
    return {
        **_placeholders(),
        "tariff_found": _mark(tariff, TARIFF_MIN_VERSION),
        "battery_found": _mark(battery, BATTERY_MIN_VERSION),
        "solar_found": ("✅ " + ", ".join(t for _, t in solar)) if solar else "❌",
        "router_found": (
            "✅ " + ", ".join(n for _, n in src.router_devices(hass))
            if src.router_devices(hass)
            else ("✅ —" if hass.config_entries.async_entries(ROUTER_DOMAIN) else "—")
        ),
    }


def _clean(user_input: dict, keys=OPTIONAL_ENTITIES) -> dict:
    """Un champ facultatif vidé revient à None."""
    out = dict(user_input)
    for k in keys:
        out.setdefault(k, None)
    return out


class ChefConfigFlow(ConfigFlow, domain=DOMAIN):
    """Assistant unique : détection, sources, rentabilité, gros consommateurs, mesure, récapitulatif.

    Rien n'est demandé de ce que les autres intégrations savent déjà : puissance souscrite,
    offre, prix, heures creuses, modes et SOC de la batterie.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._loads: list[dict] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """1. Détection."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        hass = self.hass
        placeholders = await _detection(hass)
        if not hass.config_entries.async_entries(BATTERY_DOMAIN):
            return self.async_abort(reason="missing_battery", description_placeholders=placeholders)
        if not src.solar_entries(hass):
            return self.async_abort(reason="missing_solar", description_placeholders=placeholders)
        errors: dict[str, str] = {}
        if not src.version_ok(await src.async_integration_version(hass, BATTERY_DOMAIN), BATTERY_MIN_VERSION):
            errors["base"] = "battery_version"
        if user_input is not None and not errors:
            self._data.update(_auto_sources(hass))
            return await self.async_step_sources()
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema({}), errors=errors, description_placeholders=placeholders
        )

    async def async_step_sources(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """2. Sources : seulement s'il y a plusieurs choix."""
        schema = _sources_schema(self.hass, self._data, only_multiple=True)
        errors: dict[str, str] = {}
        if not schema.schema:
            return await self.async_step_profit()
        if user_input is not None:
            if CONF_SOLAR_ENTRIES in schema.schema and not user_input.get(CONF_SOLAR_ENTRIES):
                errors[CONF_SOLAR_ENTRIES] = "no_solar_selected"
            if not errors:
                self._data.update(user_input)
                return await self.async_step_profit()
        return self.async_show_form(
            step_id="sources", data_schema=schema, errors=errors, description_placeholders=_placeholders()
        )

    async def async_step_profit(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """3. Rentabilité."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_routers()
        return self.async_show_form(step_id="profit", data_schema=_profit_schema(self._data))

    async def async_step_routers(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """4. Routeurs solaires : liste directe si ha-routeur-f1atb en a, sinon une question (N5)."""
        devices = src.router_devices(self.hass)
        if not devices:
            if self.hass.config_entries.async_entries(ROUTER_DOMAIN):
                return await self.async_step_routers_none()
            return await self.async_step_router_question()
        if user_input is not None:
            routers = _routers_from_input(devices, user_input.get(CONF_ROUTERS) or [], [])
            self._data[CONF_ROUTERS] = routers
            self._data[CONF_ROUTER_PRIORITY] = user_input[CONF_ROUTER_PRIORITY]
            self._data["routers_seen"] = [d for d, _ in devices]
            self._loads = _sync_router_loads(self.hass, self._loads, routers)
            return await self.async_step_loads()
        return self.async_show_form(
            step_id="routers",
            data_schema=_routers_schema(self.hass, {}, devices),
            description_placeholders=_placeholders(),
        )

    async def async_step_routers_none(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_loads()
        return self.async_show_form(step_id="routers_none", data_schema=vol.Schema({}), description_placeholders=_placeholders())

    async def async_step_router_question(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_loads()
        schema = vol.Schema(
            {vol.Required("router_kind", default="none"): _choice(["f1atb", "other", "none"], "router_kind")}
        )
        return self.async_show_form(step_id="router_question", data_schema=schema, description_placeholders=_placeholders())

    async def async_step_loads(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """4. Gros consommateurs (facultatif, un par écran)."""
        return self.async_show_menu(
            step_id="loads",
            menu_options=["load_new", "measure"],
            description_placeholders={"count": str(len(self._loads))},
        )

    async def async_step_load_new(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._loads.append(_load_from_input(user_input))
            if user_input.get("add_another"):
                return self.async_show_form(
                    step_id="load_new",
                    data_schema=_load_schema({}, with_more=True),
                    description_placeholders={"count": str(len(self._loads))},
                )
            return await self.async_step_measure()
        return self.async_show_form(
            step_id="load_new",
            data_schema=_load_schema({}, with_more=True),
            description_placeholders={"count": str(len(self._loads))},
        )

    async def async_step_measure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """5. Mesure de puissance au tableau (facultatif)."""
        if user_input is not None:
            self._data[CONF_POWER_SENSOR] = user_input.get(CONF_POWER_SENSOR) or None
            return await self.async_step_recap()
        return self.async_show_form(step_id="measure", data_schema=_measure_schema(self._data))

    def _recap_placeholders(self) -> dict[str, str]:
        tariffs = dict(_tariff_options(self.hass))
        batteries = dict(_battery_options(self.hass))
        solar = dict(src.solar_entries(self.hass))
        d = self._data
        loads = ", ".join(f"{l[LOAD_NAME]} ({l[LOAD_POWER] / 1000:g} kW)" for l in self._loads)
        return {
            "tariff": tariffs.get(d.get(CONF_TARIFF_ENTRY) or "", "—"),
            "battery": batteries.get(d.get(CONF_BATTERY_DEVICE) or "", "—"),
            "solar": ", ".join(solar.get(e, e) for e in d.get(CONF_SOLAR_ENTRIES) or []) or "—",
            "threshold": f"{float(d.get(CONF_GAIN_THRESHOLD, DEFAULTS[CONF_GAIN_THRESHOLD])):.3f}",
            "efficiency": f"{float(d.get(CONF_EFFICIENCY, DEFAULTS[CONF_EFFICIENCY])):g}",
            "reserve": f"{float(d.get(CONF_RESERVE_SOC, DEFAULTS[CONF_RESERVE_SOC])):g}",
            "loads": loads or "—",
            "power_sensor": d.get(CONF_POWER_SENSOR) or "—",
            "routers": ", ".join(r["name"] for r in d.get(CONF_ROUTERS) or []) or "—",
        }

    async def async_step_recap(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """6. Récapitulatif et activation du pilotage."""
        if user_input is not None:
            data = {**self._data, CONF_AUTO_START: bool(user_input.get(CONF_AUTO_START, True))}
            data[CONF_LOADS] = self._loads
            data.setdefault(CONF_DAILY_KWH, DEFAULTS[CONF_DAILY_KWH])
            data.setdefault(CONF_WEAR, DEFAULTS[CONF_WEAR])
            data.setdefault(CONF_PROFILE, DEFAULTS[CONF_PROFILE])
            data.setdefault(CONF_THREE_PHASE, DEFAULTS[CONF_THREE_PHASE])
            data.setdefault(CONF_MARGIN, DEFAULTS[CONF_MARGIN])
            data.setdefault(CONF_ROUTERS, [])
            for key in OPTIONAL_ENTITIES:
                data.setdefault(key, None)
            return self.async_create_entry(title="Chef d'orchestre énergie", data=data)
        schema = vol.Schema({vol.Required(CONF_AUTO_START, default=True): selector.BooleanSelector()})
        return self.async_show_form(
            step_id="recap", data_schema=schema, description_placeholders=self._recap_placeholders()
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ChefOptionsFlow()


class ChefOptionsFlow(OptionsFlow):
    """Tout se règle ici après l'installation."""

    def __init__(self) -> None:
        self._load_index: int | None = None

    @property
    def _cur(self) -> dict[str, Any]:
        return {**DEFAULTS, **self.config_entry.data, **self.config_entry.options}

    def _save(self, changes: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **changes})

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["economy", "power", "loads", "routers", "sources", "consumption", "notifications", "advanced"],
        )

    async def async_step_economy(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        return self.async_show_form(step_id="economy", data_schema=_economy_schema(self._cur))

    async def async_step_power(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _gauge_errors(user_input)
            if not errors:
                return self._save(_clean(user_input, (CONF_SUBSCRIBED_KVA, CONF_POWER_SENSOR)))
        return self.async_show_form(
            step_id="power", data_schema=_power_schema(user_input or self._cur), errors=errors
        )

    async def async_step_consumption(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(_clean(user_input, OPTIONAL_ENTITIES[:4]))
        return self.async_show_form(step_id="consumption", data_schema=_consumption_schema(self._cur))

    async def async_step_sources(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_SOLAR_ENTRIES):
                errors[CONF_SOLAR_ENTRIES] = "no_solar_selected"
            elif user_input.get(CONF_TARIFF_ENTRY) and not src.version_ok(
                await src.async_integration_version(self.hass, TARIFF_DOMAIN), TARIFF_MIN_VERSION
            ):
                errors[CONF_TARIFF_ENTRY] = "tariff_version"
            elif not src.version_ok(
                await src.async_integration_version(self.hass, BATTERY_DOMAIN), BATTERY_MIN_VERSION
            ):
                errors[CONF_BATTERY_DEVICE] = "battery_version"
            else:
                return self._save(_clean(user_input, (CONF_TARIFF_ENTRY,)))
        return self.async_show_form(
            step_id="sources",
            data_schema=_sources_schema(self.hass, self._cur),
            errors=errors,
            description_placeholders=_placeholders(),
        )

    async def async_step_notifications(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            user_input.setdefault(CONF_NOTIFY_SERVICE, "")
            return self._save(user_input)
        cur = self._cur
        services = sorted(self.hass.services.async_services().get("notify", {}))
        schema = vol.Schema(
            {
                _opt(CONF_NOTIFY_SERVICE, cur): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[f"notify.{s}" for s in services],
                        custom_value=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_NOTIFY_LEVEL, default=cur[CONF_NOTIFY_LEVEL]): _choice(NOTIFY_LEVELS, "notify_level"),
            }
        )
        return self.async_show_form(step_id="notifications", data_schema=schema)

    async def async_step_advanced(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        cur = self._cur
        schema = vol.Schema(
            {
                vol.Required(CONF_HISTORY_WEEKS, default=cur[CONF_HISTORY_WEEKS]): _num(2, 8, 1),
                vol.Required(CONF_SOLAR_CORRECTION, default=cur[CONF_SOLAR_CORRECTION]): selector.BooleanSelector(),
                vol.Required(CONF_TEMPO_ASSUMPTION, default=cur[CONF_TEMPO_ASSUMPTION]): _choice(TEMPO_COLORS, "tempo_assumption"),
                vol.Required(CONF_FINISH_ADVANCE, default=cur[CONF_FINISH_ADVANCE]): _num(0, 120, 5, "min"),
                vol.Required(CONF_FULL_CHARGE_AUTO, default=cur[CONF_FULL_CHARGE_AUTO]): selector.BooleanSelector(),
                vol.Required(CONF_FULL_CHARGE_DAYS, default=cur[CONF_FULL_CHARGE_DAYS]): _num(7, 28, 1, "d"),
            }
        )
        return self.async_show_form(step_id="advanced", data_schema=schema)

    # ------------------------------------------------------------ routeurs (N5)
    async def async_step_routers(self, user_input=None) -> ConfigFlowResult:
        devices = src.router_devices(self.hass)
        if not devices:
            return self.async_abort(reason="no_router")
        cur = self._cur
        if user_input is not None:
            routers = _routers_from_input(devices, user_input.get(CONF_ROUTERS) or [], cur.get(CONF_ROUTERS) or [])
            self._pending_routers = routers
            self._pending_changes = {
                CONF_ROUTER_PRIORITY: user_input[CONF_ROUTER_PRIORITY],
                CONF_SUMMER_SOC: user_input[CONF_SUMMER_SOC],
                CONF_ROUTER_DAILY_KWH: user_input[CONF_ROUTER_DAILY_KWH],
                "routers_seen": sorted(set(cur.get("routers_seen") or []) | {d for d, _ in devices}),
            }
            self._usage_index = 0
            return await self.async_step_router_usage()
        return self.async_show_form(
            step_id="routers", data_schema=_routers_schema(self.hass, cur, devices, extended=True)
        )

    async def async_step_router_usage(self, user_input=None) -> ConfigFlowResult:
        routers = self._pending_routers
        if user_input is not None:
            routers[self._usage_index]["usage"] = user_input["usage"]
            self._usage_index += 1
        if self._usage_index >= len(routers):
            loads = _sync_router_loads(self.hass, self._loads, routers)
            return self._save({**self._pending_changes, CONF_ROUTERS: routers, CONF_LOADS: loads})
        router = routers[self._usage_index]
        schema = vol.Schema({vol.Required("usage", default=router.get("usage", "water_heater")): _choice(ROUTER_USAGES, "router_usage")})
        return self.async_show_form(
            step_id="router_usage", data_schema=schema, description_placeholders={"router": router["name"]}
        )

    # ------------------------------------------------------------ gros consommateurs
    @property
    def _loads(self) -> list[dict]:
        return list(self._cur.get(CONF_LOADS) or [])

    async def async_step_loads(self, user_input=None) -> ConfigFlowResult:
        options = ["load_add"]
        if self._loads:
            options += ["load_pick_edit", "load_pick_remove"]
        return self.async_show_menu(step_id="loads", menu_options=options)

    def _pick_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("load"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=str(i), label=l.get(LOAD_NAME, "?"))
                            for i, l in enumerate(self._loads)
                        ]
                    )
                )
            }
        )

    async def async_step_load_pick_edit(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._load_index = int(user_input["load"])
            return await self.async_step_load_edit()
        return self.async_show_form(step_id="load_pick_edit", data_schema=self._pick_schema())

    async def async_step_load_pick_remove(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            loads = self._loads
            loads.pop(int(user_input["load"]))
            return self._save({CONF_LOADS: loads})
        return self.async_show_form(step_id="load_pick_remove", data_schema=self._pick_schema())

    async def async_step_load_add(self, user_input=None) -> ConfigFlowResult:
        self._load_index = None
        return await self.async_step_load_edit(user_input)

    async def async_step_load_edit(self, user_input=None) -> ConfigFlowResult:
        loads = self._loads
        cur = loads[self._load_index] if self._load_index is not None else {}
        if user_input is not None:
            load = _load_from_input(user_input, cur)
            if self._load_index is None:
                loads.append(load)
            else:
                loads[self._load_index] = load
            return self._save({CONF_LOADS: loads})
        return self.async_show_form(step_id="load_edit", data_schema=_load_schema(cur))
