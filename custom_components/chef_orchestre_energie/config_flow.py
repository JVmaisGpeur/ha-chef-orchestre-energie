"""Assistant d'installation (4 écrans) et options."""

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
from .timeline import parse_window

URL_TARIFF = "https://github.com/JVmaisGpeur/ha-tarifs-electricite"
URL_BATTERY = "https://github.com/JVmaisGpeur/ha-zendure-solarflow-local"
URL_SOLAR = "https://www.home-assistant.io/integrations/forecast_solar/"

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
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=lo, max=hi, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX
        )
    )


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


def _sources_schema(hass, cur: dict) -> vol.Schema:
    solar = src.solar_entries(hass)
    tariffs = _tariff_options(hass)
    batteries = _battery_options(hass)
    solar_ids = [e for e, _ in solar]
    solar_default = [e for e in cur.get(CONF_SOLAR_ENTRIES, solar_ids) if e in solar_ids] or solar_ids
    return vol.Schema(
        {
            vol.Required(CONF_TARIFF_ENTRY, default=_default(cur, CONF_TARIFF_ENTRY, tariffs)): _list(tariffs),
            vol.Required(CONF_BATTERY_DEVICE, default=_default(cur, CONF_BATTERY_DEVICE, batteries)): _list(batteries),
            vol.Required(CONF_SOLAR_ENTRIES, default=solar_default): _list(solar, multiple=True),
        }
    )


def _consumption_schema(cur: dict) -> vol.Schema:
    return vol.Schema(
        {
            _opt(CONF_HOUSE_SENSOR, cur): ENERGY_SENSOR,
            _opt(CONF_GRID_IMPORT, cur): ENERGY_SENSOR,
            _opt(CONF_GRID_EXPORT, cur): ENERGY_SENSOR,
            _opt(CONF_SOLAR_ACTUAL, cur): ENERGY_SENSOR,
            vol.Required(CONF_DAILY_KWH, default=cur.get(CONF_DAILY_KWH, DEFAULTS[CONF_DAILY_KWH])): _num(1, 150, 0.5, "kWh"),
        }
    )


def _economy_schema(cur: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_EFFICIENCY, default=cur.get(CONF_EFFICIENCY, DEFAULTS[CONF_EFFICIENCY])): _num(50, 100, 1, "%"),
            vol.Required(CONF_WEAR, default=cur.get(CONF_WEAR, DEFAULTS[CONF_WEAR])): _num(0, 1, 0.005, "EUR/kWh"),
            vol.Required(
                CONF_GAIN_THRESHOLD, default=cur.get(CONF_GAIN_THRESHOLD, DEFAULTS[CONF_GAIN_THRESHOLD])
            ): _num(0, 1, 0.005, "EUR/kWh"),
            vol.Required(CONF_PROFILE, default=cur.get(CONF_PROFILE, DEFAULTS[CONF_PROFILE])): _choice(
                list(PROFILES), "profile"
            ),
        }
    )


def _power_schema(cur: dict) -> vol.Schema:
    return vol.Schema(
        {
            _opt(CONF_SUBSCRIBED_KVA, cur): _num(1, 36, 1, "kVA"),
            vol.Required(CONF_THREE_PHASE, default=cur.get(CONF_THREE_PHASE, False)): selector.BooleanSelector(),
            vol.Required(CONF_MARGIN, default=cur.get(CONF_MARGIN, DEFAULTS[CONF_MARGIN])): _num(MIN_MARGIN, 50, 1, "%"),
        }
    )


async def _check_versions(hass) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not src.version_ok(await src.async_integration_version(hass, TARIFF_DOMAIN), TARIFF_MIN_VERSION):
        errors[CONF_TARIFF_ENTRY] = "tariff_version"
    if not src.version_ok(await src.async_integration_version(hass, BATTERY_DOMAIN), BATTERY_MIN_VERSION):
        errors[CONF_BATTERY_DEVICE] = "battery_version"
    return errors


def _placeholders() -> dict[str, str]:
    return {
        "tariff_url": URL_TARIFF,
        "battery_url": URL_BATTERY,
        "solar_url": URL_SOLAR,
        "tariff_min": TARIFF_MIN_VERSION,
        "battery_min": BATTERY_MIN_VERSION,
    }


def _clean(user_input: dict, keys=OPTIONAL_ENTITIES) -> dict:
    """Un champ facultatif vidé revient à None."""
    out = dict(user_input)
    for k in keys:
        out.setdefault(k, None)
    return out


class ChefConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        hass = self.hass
        if not hass.config_entries.async_entries(TARIFF_DOMAIN):
            return self.async_abort(reason="missing_tariff", description_placeholders=_placeholders())
        if not hass.config_entries.async_entries(BATTERY_DOMAIN):
            return self.async_abort(reason="missing_battery", description_placeholders=_placeholders())
        if not src.solar_entries(hass):
            return self.async_abort(reason="missing_solar", description_placeholders=_placeholders())
        errors = await _check_versions(hass)
        if user_input is not None and not errors:
            if not user_input.get(CONF_SOLAR_ENTRIES):
                errors[CONF_SOLAR_ENTRIES] = "no_solar_selected"
            else:
                self._data.update(user_input)
                return await self.async_step_consumption()
        return self.async_show_form(
            step_id="user",
            data_schema=_sources_schema(hass, user_input or {}),
            errors=errors,
            description_placeholders=_placeholders(),
        )

    async def async_step_consumption(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(_clean(user_input, OPTIONAL_ENTITIES[:4]))
            return await self.async_step_economy()
        return self.async_show_form(step_id="consumption", data_schema=_consumption_schema({}))

    async def async_step_economy(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_power()
        return self.async_show_form(step_id="economy", data_schema=_economy_schema({}))

    async def async_step_power(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(_clean(user_input, (CONF_SUBSCRIBED_KVA,)))
            return self.async_create_entry(title="Chef d'orchestre énergie", data=self._data)
        return self.async_show_form(step_id="power", data_schema=_power_schema({}))

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
            menu_options=["economy", "power", "consumption", "sources", "loads", "notifications", "advanced"],
        )

    async def async_step_economy(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        return self.async_show_form(step_id="economy", data_schema=_economy_schema(self._cur))

    async def async_step_power(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(_clean(user_input, (CONF_SUBSCRIBED_KVA,)))
        return self.async_show_form(step_id="power", data_schema=_power_schema(self._cur))

    async def async_step_consumption(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(_clean(user_input, OPTIONAL_ENTITIES[:4]))
        return self.async_show_form(step_id="consumption", data_schema=_consumption_schema(self._cur))

    async def async_step_sources(self, user_input=None) -> ConfigFlowResult:
        errors = await _check_versions(self.hass)
        if user_input is not None and not errors:
            if not user_input.get(CONF_SOLAR_ENTRIES):
                errors[CONF_SOLAR_ENTRIES] = "no_solar_selected"
            else:
                return self._save(user_input)
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
            }
        )
        return self.async_show_form(step_id="advanced", data_schema=schema)

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
        errors: dict[str, str] = {}
        loads = self._loads
        cur = loads[self._load_index] if self._load_index is not None else {}
        if user_input is not None:
            if user_input.get(LOAD_WINDOW) and parse_window(user_input[LOAD_WINDOW]) is None:
                errors[LOAD_WINDOW] = "bad_window"
            else:
                load = _clean(user_input, (LOAD_POWER_SENSOR, LOAD_STATE_ENTITY, LOAD_ENERGY_SENSOR, LOAD_WINDOW))
                if self._load_index is None:
                    loads.append(load)
                else:
                    loads[self._load_index] = load
                return self._save({CONF_LOADS: loads})
        schema = vol.Schema(
            {
                vol.Required(LOAD_NAME, default=cur.get(LOAD_NAME, vol.UNDEFINED)): selector.TextSelector(),
                vol.Required(LOAD_KIND, default=cur.get(LOAD_KIND, "water_heater")): _choice(LOAD_KINDS, "load_kind"),
                vol.Required(LOAD_POWER, default=cur.get(LOAD_POWER, 3000)): _num(100, 22000, 50, "W"),
                _opt(LOAD_POWER_SENSOR, cur): POWER_SENSOR,
                vol.Required(LOAD_THRESHOLD, default=cur.get(LOAD_THRESHOLD, 100)): _num(5, 5000, 5, "W"),
                _opt(LOAD_STATE_ENTITY, cur): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "binary_sensor", "input_boolean"])
                ),
                _opt(LOAD_ENERGY_SENSOR, cur): ENERGY_SENSOR,
                _opt(LOAD_WINDOW, cur): selector.TextSelector(),
            }
        )
        step = "load_edit"
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors)
