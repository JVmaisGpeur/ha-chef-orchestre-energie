"""Chef d'orchestre énergie : pilote les batteries selon les tarifs et le soleil."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS, SERVICE_FORCE_NIGHT, SERVICE_RECALCULATE
from .manager import Orchestrator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SCHEMA_RECALCULATE = vol.Schema({vol.Optional("config_entry_id"): cv.string})
SCHEMA_FORCE_NIGHT = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Required("mode"): vol.In(["charge", "idle"]),
        vol.Optional("target_soc"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    }
)

type ChefConfigEntry = ConfigEntry[Orchestrator]


def _targets(hass: HomeAssistant, call: ServiceCall) -> list[Orchestrator]:
    wanted = call.data.get("config_entry_id")
    found = [
        e.runtime_data
        for e in hass.config_entries.async_entries(DOMAIN)
        if isinstance(getattr(e, "runtime_data", None), Orchestrator)
        and (not wanted or e.entry_id == wanted)
    ]
    if not found:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_orchestrator"
        )
    return found


async def async_setup(hass: HomeAssistant, config) -> bool:
    async def _recalculate(call: ServiceCall) -> None:
        for orch in _targets(hass, call):
            await orch.async_check_sources()
            await orch.async_update_plan()

    async def _force_night(call: ServiceCall) -> None:
        for orch in _targets(hass, call):
            await orch.async_force_night(call.data["mode"], call.data.get("target_soc"))

    hass.services.async_register(DOMAIN, SERVICE_RECALCULATE, _recalculate, SCHEMA_RECALCULATE)
    hass.services.async_register(DOMAIN, SERVICE_FORCE_NIGHT, _force_night, SCHEMA_FORCE_NIGHT)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ChefConfigEntry) -> bool:
    orch = Orchestrator(hass, entry)
    entry.runtime_data = orch
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await orch.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChefConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_stop()
    return ok


async def _async_reload(hass: HomeAssistant, entry: ChefConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
