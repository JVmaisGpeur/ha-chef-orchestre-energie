"""Charge les modules de calcul sans importer Home Assistant."""

import importlib.util
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "chef_orchestre_energie"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"coe_{name}", BASE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"coe_{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


planner = _load("planner")
consumption = _load("consumption")
