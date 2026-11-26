"""Contrat ha-routeur-f1atb (≥ 1.1.0) : entités lues par le Chef d'orchestre."""

import pathlib
import re

BASE = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "chef_orchestre_energie"


def test_plage_on_lue_sur_le_capteur_planning():
    """Un routeur verrouillé affiche « blocked », jamais « on_slot » : la plage ON se lit sur `planning` (v1.3.4)."""
    const = (BASE / "const.py").read_text(encoding="utf-8")
    keys = const.split("ROUTER_KEYS = (")[1].split("\n)")[0]
    assert '"planning"' in keys
    manager = (BASE / "manager.py").read_text(encoding="utf-8")
    body = manager.split("def _router_on_slot")[1].split("\n    def ")[0]
    planning = body.index('ents.get("planning")')
    status = body.index('ents.get("status")')
    assert planning < status, "planning doit passer avant status"
    assert re.search(r'ents\["planning"\]\) == "on"', body)
