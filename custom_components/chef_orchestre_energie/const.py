"""Constantes du Chef d'orchestre énergie."""

from __future__ import annotations

DOMAIN = "chef_orchestre_energie"
VERSION = "1.2.0"
PLATFORMS = ["binary_sensor", "button", "number", "select", "sensor", "switch"]

# Intégrations lues et versions minimales (contrats, interface 1)
TARIFF_DOMAIN = "tarifs_electricite"
TARIFF_MIN_VERSION = "1.1.0"
BATTERY_DOMAIN = "zendure_local"
BATTERY_MIN_VERSION = "1.3.0"
SOLAR_DOMAINS = ("forecast_solar", "open_meteo_solar_forecast", "solcast_solar")

# Clés du contrat ha-tarifs-electricite (en français, comme le prévoit son contrat)
TARIFF_KEYS = ("puissance_souscrite", "offre", "prix_actuel", "tempo_demain")
TARIFF_REQUIRED = ("puissance_souscrite", "offre", "prix_actuel")
# Lues pour la carte Énergie (E3)
TARIFF_CARD_KEYS = ("periode", "prochain_changement", "prochain_prix", "tempo_aujourdhui", "tempo_demain")

# Clés du contrat ha-zendure-solarflow-local (en anglais)
BATTERY_KEYS = (
    "operating_mode",
    "import_limit",
    "charge_target_soc",
    "electric_level",
    "usable_capacity",
    "available_energy",
    "missing_energy",
    "battery_power",
    "max_charge_power",
    "max_discharge_power",
    "regulation_state",
)
ENERGY_COUNTER_KEYS = ("energy_charged", "energy_discharged")
# SOC minimum et maximum de chaque batterie (E2)
UNIT_SOC_KEYS = ("min_soc", "soc_set")
UNIT_SOC_BOUNDS = {"min_soc": (0, 50), "soc_set": (70, 100)}
# Pilote externe générique de ha-zendure-solarflow-local (≥ 1.4.0, D6)
EXTERNAL_CONTROL_SERVICE = "set_external_control"
EXTERNAL_CONTROL_RENEW_MIN = 15
CONTROLLER_NAME = "Chef d'orchestre énergie"
INTERFACE_VERSION = 1

# ------------------------------------------------------------------ configuration
CONF_TARIFF_ENTRY = "tariff_entry_id"
CONF_BATTERY_DEVICE = "battery_device_id"
CONF_SOLAR_ENTRIES = "solar_entry_ids"
CONF_HOUSE_SENSOR = "house_energy_sensor"
CONF_GRID_IMPORT = "grid_import_sensor"
CONF_GRID_EXPORT = "grid_export_sensor"
CONF_SOLAR_ACTUAL = "solar_actual_sensor"
CONF_DAILY_KWH = "daily_kwh"
CONF_EFFICIENCY = "efficiency"  # %
CONF_WEAR = "wear"  # €/kWh
CONF_GAIN_THRESHOLD = "gain_threshold"  # €/kWh
CONF_PROFILE = "profile"
CONF_SUBSCRIBED_KVA = "subscribed_kva"
CONF_THREE_PHASE = "three_phase"
CONF_MARGIN = "margin"  # %
CONF_NOTIFY_SERVICE = "notify_service"
CONF_NOTIFY_LEVEL = "notify_level"
CONF_HISTORY_WEEKS = "history_weeks"
CONF_SOLAR_CORRECTION = "solar_correction"
CONF_TEMPO_ASSUMPTION = "tempo_assumption"
CONF_FINISH_ADVANCE = "finish_advance"  # min
CONF_LOADS = "loads"
CONF_RESERVE_SOC = "reserve_soc"  # % (E2)
CONF_POWER_SENSOR = "power_sensor"  # puissance au tableau (E4)
CONF_GAUGE_WARN = "gauge_warn"
CONF_GAUGE_CRIT = "gauge_crit"
CONF_AUTO_START = "auto_start"  # pilotage activé à la fin de l'assistant

# Gros consommateurs
LOAD_NAME = "name"
LOAD_KIND = "kind"
LOAD_POWER = "power_w"
LOAD_POWER_SENSOR = "power_sensor"
LOAD_THRESHOLD = "threshold_w"
LOAD_STATE_ENTITY = "state_entity"
LOAD_ENERGY_SENSOR = "energy_sensor"
LOAD_WINDOW = "usual_window"
LOAD_KINDS = ["water_heater", "heat_pump", "ev", "other"]

DEFAULTS = {
    CONF_DAILY_KWH: 10.0,
    CONF_EFFICIENCY: 85,
    CONF_WEAR: 0.0,
    CONF_GAIN_THRESHOLD: 0.02,
    CONF_PROFILE: "balanced",
    CONF_THREE_PHASE: False,
    CONF_MARGIN: 10,
    CONF_NOTIFY_SERVICE: "",
    CONF_NOTIFY_LEVEL: "alerts",
    CONF_HISTORY_WEEKS: 4,
    CONF_SOLAR_CORRECTION: True,
    CONF_TEMPO_ASSUMPTION: "blanc",
    CONF_FINISH_ADVANCE: 30,
    CONF_RESERVE_SOC: 50,
    CONF_GAUGE_WARN: 80,
    CONF_GAUGE_CRIT: 95,
    CONF_AUTO_START: True,
}
MIN_MARGIN = 10  # % : la régulation peut dépasser la limite 2 à 5 s

PROFILES = {"cautious": 0.20, "balanced": 0.10, "economical": 0.0}
NOTIFY_LEVELS = ["all", "alerts", "none"]
TEMPO_COLORS = ["bleu", "blanc", "rouge"]

# ------------------------------------------------------------------ fonctionnement
STEP_MINUTES = 15
HORIZON_HOURS = 48
PLAN_INTERVAL_MIN = 15
CONTROL_INTERVAL_S = 60
EFFICIENCY_DAYS = 30
SOLAR_FACTOR_DAYS = 14
STORE_VERSION = 1

SERVICE_RECALCULATE = "recalculate"
SERVICE_FORCE_NIGHT = "force_night"

SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"
