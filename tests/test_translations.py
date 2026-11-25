"""Français et anglais complets : mêmes clés, aucun texte affiché codé en dur."""

import json
import pathlib
import re

BASE = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "chef_orchestre_energie"


def keys(d, prefix=""):
    out = set()
    for k, v in d.items():
        p = f"{prefix}.{k}" if prefix else k
        out |= keys(v, p) if isinstance(v, dict) else {p}
    return out


def load(name):
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def test_memes_cles():
    en, fr, strings = load("translations/en.json"), load("translations/fr.json"), load("strings.json")
    assert keys(en) == keys(fr)
    assert strings == en


def test_memes_parametres():
    en, fr = load("translations/en.json"), load("translations/fr.json")

    def flat(d, p=""):
        for k, v in d.items():
            q = f"{p}.{k}" if p else k
            if isinstance(v, dict):
                yield from flat(v, q)
            else:
                yield q, v

    fr_flat = dict(flat(fr))
    for k, v in flat(en):
        assert set(re.findall(r"{(\w+)}", v)) == set(re.findall(r"{(\w+)}", fr_flat[k])), k


def test_etats_traduits():
    import importlib.util, sys

    sys.path.insert(0, str(BASE.parent.parent / "tests"))
    from conftest import consumption, planner

    en = load("translations/en.json")
    night = en["entity"]["sensor"]["night_plan"]
    assert set(night["state"]) == set(planner.PLAN_STATES)
    assert set(night["state_attributes"]["reason"]["state"]) == set(planner.REASONS)
    assert set(en["entity"]["sensor"]["forecast_reliability"]["state"]) == set(consumption.RELIABILITIES)


def test_entites_traduites():
    en = load("translations/en.json")
    declared = set()
    for path in BASE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        declared |= set(re.findall(r'(?<!\w)key="(\w+)"', text))
        declared |= set(re.findall(r'\(entry\.runtime_data, "(\w+)"\)', text))
    translated = {k for plat in en["entity"].values() for k in plat}
    assert declared <= translated, declared - translated


def test_pas_de_texte_francais_dans_le_code_affiche():
    """Les messages envoyés à l'utilisateur passent par les traductions."""
    for path in BASE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r'raise \w+\(\s*"', text):
            raise AssertionError(f"message codé en dur dans {path.name}")


def test_carte_coherente():
    """La carte connaît tous les états du plan et les deux langues ont les mêmes textes."""
    import sys

    sys.path.insert(0, str(BASE.parent.parent / "tests"))
    from conftest import planner

    js = (BASE / "frontend" / "chef-orchestre-card.js").read_text(encoding="utf-8")
    colors = set(re.findall(r"(\w+): \"#", js.split("const PLAN_COLORS")[1].split("};")[0]))
    assert colors == set(planner.PLAN_STATES)
    for mode in (planner.MODE_OFF, planner.MODE_GRID_CHARGE, planner.MODE_SMART, planner.MODE_SMART_CHARGE):
        assert js.count(f"{mode}:") >= 3, mode  # couleur + nom en français + nom en anglais
    fr = js.split("  fr: {")[1].split("\n  en: {")[0]
    en = js.split("\n  en: {")[1].split("\n};")[0]
    key = re.compile(r"(?:^|[{,])\s*(\w+):", re.M)
    assert set(key.findall(fr)) == set(key.findall(en))


def test_etapes_assistant_traduites():
    """Chaque écran et chaque menu de config_flow.py a son titre dans les deux langues."""
    import re

    code = (BASE / "config_flow.py").read_text(encoding="utf-8")
    flow, options = code.split("class ChefOptionsFlow")
    for lang in ("fr", "en"):
        d = json.loads((BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
        for part, section in ((flow, "config"), (options, "options")):
            for step in set(re.findall(r'step_id="([a-z_]+)"', part)):
                assert step in d[section]["step"], (lang, section, step)
            for menu in re.findall(r"menu_options=\[([^\]]+)\]", part):
                for opt in re.findall(r'"([a-z_]+)"', menu):
                    assert opt in d[section]["step"], (lang, section, opt)


def test_placeholders_assistant():
    """Les textes de l'assistant n'utilisent que les variables fournies par le code."""
    import re

    code = (BASE / "config_flow.py").read_text(encoding="utf-8")
    provided = set(re.findall(r'"([a-z_]+)": ', code))
    for lang in ("fr", "en"):
        d = json.loads((BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
        for step in d["config"]["step"].values():
            for name in re.findall(r"{([a-z_]+)}", step.get("description", "")):
                assert name in provided, (lang, name)


def test_carte_energie_coherente():
    """Carte Énergie (E3) : mêmes textes en français et en anglais, tous les états du plan, carte enregistrée."""
    import sys

    sys.path.insert(0, str(BASE.parent.parent / "tests"))
    from conftest import planner

    js = (BASE / "frontend" / "chef-orchestre-energie-card.js").read_text(encoding="utf-8")
    fr = js.split("  fr: {")[1].split("\n  en: {")[0]
    en = js.split("\n  en: {")[1].split("\n};")[0]
    key = re.compile(r"(?:^|[{,])\s*(\w+):", re.M)
    assert set(key.findall(fr)) == set(key.findall(en))
    verdicts = set(re.findall(r"(\w+): \"", fr.split("verdict: {")[1].split("}")[0]))
    assert set(planner.PLAN_STATES) <= verdicts
    assert "chef-orchestre-energie-card.js" in (BASE / "__init__.py").read_text(encoding="utf-8")
    # Blocs masqués par défaut, comme la carte Tarifs
    assert "show_tariff: true" in js.split("getStubConfig")[1].split("}")[0]
    assert "this._config = { ...(config || {}) }" in js


def test_interface_stable():
    """E1 : l'interrupteur auto_control porte les attributs d'interface."""
    switch = (BASE / "switch.py").read_text(encoding="utf-8")
    manager = (BASE / "manager.py").read_text(encoding="utf-8")
    assert 'translation_key = "auto_control"' in switch or '"auto_control"' in switch
    assert "interface_attributes" in switch
    for attr in ("controlled_device_id", "controlled_device_ids", "controlled_entities", "interface_version"):
        assert f'"{attr}"' in manager, attr


def test_selecteurs_nombre_sans_unite_none():
    """Un NumberSelector ne doit jamais recevoir unit_of_measurement=None (menu Avancé en erreur, v1.2.0)."""
    code = (BASE / "config_flow.py").read_text(encoding="utf-8")
    assert "unit_of_measurement=unit" not in code
