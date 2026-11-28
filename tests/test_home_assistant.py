"""Chargement réel dans Home Assistant : assistant, entités, menu des options.

La batterie Zendure et la prévision solaire sont des entrées et entités fictives
(registres de Home Assistant), sans réseau.
Ignoré si Home Assistant et pytest-homeassistant-custom-component ne sont pas installés
(lancé par le job CI « home-assistant », sous Linux).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

import voluptuous_serialize  # noqa: E402
from homeassistant import config_entries  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.helpers import config_validation as cv  # noqa: E402
from homeassistant.helpers import device_registry as dr  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

DOMAIN = "chef_orchestre_energie"
REPO_COMPONENTS = str(Path(__file__).resolve().parent.parent / "custom_components")

# Entités fictives de la batterie : (clé de traduction, domaine, état, attributs)
BATTERIE = [
    ("operating_mode", "select", "smart", {"options": ["smart", "smart_charge", "manual", "off"]}),
    ("import_limit", "number", "0", {"unit_of_measurement": "W", "min": 0, "max": 2400}),
    ("charge_target_soc", "number", "100", {"unit_of_measurement": "%", "min": 0, "max": 100}),
    ("electric_level", "sensor", "55", {"unit_of_measurement": "%", "device_class": "battery"}),
    ("usable_capacity", "sensor", "2.4", {"unit_of_measurement": "kWh"}),
    ("available_energy", "sensor", "1.1", {"unit_of_measurement": "kWh"}),
    ("missing_energy", "sensor", "1.0", {"unit_of_measurement": "kWh"}),
    ("battery_power", "sensor", "0", {"unit_of_measurement": "W", "device_class": "power"}),
    ("max_charge_power", "sensor", "2400", {"unit_of_measurement": "W"}),
    ("max_discharge_power", "sensor", "2400", {"unit_of_measurement": "W"}),
    ("regulation_state", "sensor", "idle", {}),
    ("min_soc", "number", "10", {"unit_of_measurement": "%", "min": 0, "max": 50}),
    ("soc_set", "number", "100", {"unit_of_measurement": "%", "min": 70, "max": 100}),
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations, hass):
    """L'historique (recorder) doit être prêt avant Home Assistant.

    L'outil de test charge son propre paquet custom_components : on y ajoute le nôtre.
    La version de l'intégration batterie (absente ici) est simulée.
    """
    import custom_components
    from homeassistant import loader

    if REPO_COMPONENTS not in list(custom_components.__path__):
        custom_components.__path__.append(REPO_COMPONENTS)
    hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)

    async def _version(_hass, domain):
        return {"zendure_local": "1.7.0", "tarifs_electricite": "1.2.0"}.get(domain)

    with patch(
        "custom_components.chef_orchestre_energie.sources.async_integration_version",
        AsyncMock(side_effect=_version),
    ):
        yield


def _ecran(r, step_id: str | None = None):
    """Vérifie l'écran affiché et sérialise son formulaire comme le fait l'interface."""
    if step_id is not None:
        assert r.get("step_id") == step_id, (r.get("step_id"), r.get("errors"), r.get("reason"))
    if r["type"] is FlowResultType.FORM:
        assert not r.get("errors"), r["errors"]
        if r.get("data_schema") is not None:
            voluptuous_serialize.convert(r["data_schema"], custom_serializer=cv.custom_serializer)
    return r


def _environnement(hass: HomeAssistant) -> str:
    """Batterie Zendure et prévision solaire fictives ; renvoie l'appareil batterie."""
    bat = MockConfigEntry(domain="zendure_local", title="Zendure test", unique_id="TESTSN0001")
    bat.add_to_hass(hass)
    MockConfigEntry(domain="forecast_solar", title="Toit").add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(
        config_entry_id=bat.entry_id, identifiers={("zendure_local", "TESTSN0001")},
        name="Batterie test", manufacturer="Zendure", model="Test")
    reg = er.async_get(hass)
    for key, domain, state, attrs in BATTERIE:
        ent = reg.async_get_or_create(
            domain, "zendure_local", f"TESTSN0001_{key}", config_entry=bat, device_id=dev.id,
            translation_key=key, suggested_object_id=f"batterie_test_{key}")
        hass.states.async_set(ent.entity_id, state, attrs)
    hass.states.async_set("sensor.puissance_tableau", "1200", {"device_class": "power", "unit_of_measurement": "W"})
    return dev.id


async def _assistant(hass: HomeAssistant):
    flow = hass.config_entries.flow
    r = _ecran(await flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER}), "user")
    # Une seule batterie et une seule prévision : l'écran Sources est sauté
    r = _ecran(await flow.async_configure(r["flow_id"], {}), "profit")
    r = _ecran(await flow.async_configure(r["flow_id"], {}), "router_question")
    r = await flow.async_configure(r["flow_id"], {"router_kind": "none"})
    assert r["type"] is FlowResultType.MENU and r["step_id"] == "loads"
    r = _ecran(await flow.async_configure(r["flow_id"], {"next_step_id": "load_new"}), "load_new")
    r = _ecran(await flow.async_configure(r["flow_id"], {
        "name": "Chauffe-eau", "kind": "water_heater", "power_kw": 2.4,
        "battery_powered": False, "add_another": False}), "measure")
    r = _ecran(await flow.async_configure(r["flow_id"], {"power_sensor": "sensor.puissance_tableau"}), "recap")
    r = await flow.async_configure(r["flow_id"], {"auto_start": False})
    assert r["type"] is FlowResultType.CREATE_ENTRY, r
    await hass.async_block_till_done()
    return r["result"]


def _entites(hass: HomeAssistant, entry) -> dict[str, str]:
    reg = er.async_get(hass)
    return {e.unique_id: e.entity_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)}


async def _decharger(hass: HomeAssistant, entry) -> None:
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_assistant_et_chargement(hass: HomeAssistant) -> None:
    dev = _environnement(hass)
    entry = await _assistant(hass)
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data["battery_device_id"] == dev
    assert entry.data["loads"][0]["power_w"] == 2400
    assert entry.data["auto_start"] is False

    ents = _entites(hass, entry)
    assert len(ents) > 10, sorted(ents)
    domaines = {e.split(".")[0] for e in ents.values()}
    assert {"sensor", "switch", "select", "number", "button", "binary_sensor", "time"} <= domaines, domaines
    disponibles = [e for e in ents.values() if (s := hass.states.get(e)) and s.state != "unavailable"]
    assert disponibles, "aucune entité disponible"

    # Une seule installation
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.ABORT
    await _decharger(hass, entry)


async def test_options_menu(hass: HomeAssistant) -> None:
    _environnement(hass)
    entry = await _assistant(hass)
    opts = hass.config_entries.options

    r = await opts.async_init(entry.entry_id)
    assert r["type"] is FlowResultType.MENU
    menu = r["menu_options"]
    for etape in menu:
        r = await opts.async_init(entry.entry_id)
        r = await opts.async_configure(r["flow_id"], {"next_step_id": etape})
        if etape == "routers":  # aucun routeur F1ATB : refus attendu
            assert r["type"] is FlowResultType.ABORT and r["reason"] == "no_router", r
        elif etape == "loads":
            assert r["type"] is FlowResultType.MENU, r
            assert "load_pick_edit" in r["menu_options"]
            r2 = _ecran(await opts.async_configure(r["flow_id"], {"next_step_id": "load_pick_edit"}), "load_pick_edit")
            _ecran(await opts.async_configure(r2["flow_id"], {"load": "0"}), "load_edit")
        else:
            _ecran(r, etape)
        if r["type"] is not FlowResultType.ABORT:
            opts.async_abort(r["flow_id"])

    # Enregistrement des réglages avancés (valeurs par défaut) : l'entrée se recharge
    r = await opts.async_init(entry.entry_id)
    r = await opts.async_configure(r["flow_id"], {"next_step_id": "advanced"})
    r = await opts.async_configure(r["flow_id"], {})
    assert r["type"] is FlowResultType.CREATE_ENTRY, r
    await hass.async_block_till_done()

    # Rentabilité : seuil de gain modifié
    r = await opts.async_init(entry.entry_id)
    r = await opts.async_configure(r["flow_id"], {"next_step_id": "economy"})
    r = await opts.async_configure(r["flow_id"], {"gain_threshold": 0.03})
    assert r["type"] is FlowResultType.CREATE_ENTRY, r
    await hass.async_block_till_done()
    entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert entry.options["gain_threshold"] == 0.03
    assert entry.state is config_entries.ConfigEntryState.LOADED
    await _decharger(hass, entry)
