# Energy conductor (Chef d'orchestre énergie)

[Version française](README.md)

Home Assistant integration that decides every evening how to use your batteries so that the most expensive peak hours are covered by the battery, at the lowest cost.

It talks to no hardware. It **reads** your tariffs, the solar forecast and the house consumption, and **drives** your battery (or battery Group) through its mode, its grid import limit and its charge target SOC.

Every evening it answers three questions:

1. Should the battery charge tonight during off-peak hours, and how much?
2. Is the gain worth the battery losses? If not, the battery stays off at night, with no useless cycle.
3. At what power can it charge without tripping the main breaker, given the water heater, heat pump or EV?

## Requirements

| Integration | Version | Role |
| --- | --- | --- |
| [ha-tarifs-electricite](https://github.com/JVmaisGpeur/ha-tarifs-electricite) | ≥ 1.1.0 | Prices, off-peak hours, Tempo, subscribed power |
| [ha-zendure-solarflow-local](https://github.com/JVmaisGpeur/ha-zendure-solarflow-local) | ≥ 1.3.0 | Battery or battery Group to drive |
| A solar forecast | – | Forecast.Solar, Open-Meteo Solar Forecast or Solcast |
| An energy meter (recommended) | – | To learn the house consumption |

With Forecast.Solar, add one entry per panel orientation: the conductor adds them up hour by hour, like the Energy dashboard.

A battery must be driven by a single integration or automation at a time. Disable your old off-peak charging automations before enabling automatic control.

## Installation

1. HACS → Integrations → ⋮ menu → Custom repositories → `https://github.com/JVmaisGpeur/ha-chef-orchestre-energie`, category Integration.
2. Install "Chef d'orchestre énergie", restart Home Assistant.
3. Settings → Devices & services → Add integration → Chef d'orchestre énergie.

The setup takes four screens: sources, consumption, economics, power. Everything can be changed later in **Configure**: economics, power, consumption, sources, large appliances, notifications, advanced.

## How it decides

Before each off-peak period starts (and whenever an input changes), it simulates in 15-minute steps the period from the end of tonight to the start of the next off-peak hours:

- solar first covers the house, the surplus goes into the battery;
- a grid charge is only useful if `peak price − (off-peak price ÷ efficiency + wear)` exceeds the **profitability threshold** (€0.02/kWh by default);
- it looks for the minimum battery energy so the SOC never drops below its minimum during those hours, increased by the profile margin (cautious 20 %, balanced 10 %, economical 0 %);
- if the battery is too small, it keeps energy for the most expensive hours.

| Situation | Mode sent to the battery |
| --- | --- |
| Off-peak, no charge | `off` (or `smart_charge` when there is sun) |
| Off-peak, charge planned | `grid_charge` up to the target SOC, finishing 30 min before off-peak ends |
| Peak hours | `smart` |
| Peak hours kept for later | `smart_charge` |
| Control off or missing data | no command |

While charging, the import limit is `subscribed power × (1 − margin)`, with a margin of at least 10 % (÷ 3 for three-phase). The battery enforces it in real time: if the oven or water heater starts, it reduces its charge immediately.

## Entities

| Entity | Role |
| --- | --- |
| Automatic control | Off: no command is sent anymore |
| Caution profile | Cautious, balanced, economical |
| Profitability threshold | €/kWh, adjustable live |
| Night plan | Charge, rest, not profitable, nothing to cover, suspended, missing data; `reason` and `hourly_plan` attributes |
| Energy to charge, Target state of charge, Charge start | Tonight's plan |
| Forecast consumption, Peak-hour need, Forecast solar production | The forecasts used |
| Forecast gain, Savings this month | What it earns |
| Battery efficiency, Forecast reliability | Diagnostics |
| Power alert | Risk of exceeding the subscribed power |
| Recalculate | Recomputes the plan |

Services: `chef_orchestre_energie.recalculate` and `chef_orchestre_energie.force_night` (charge or rest imposed for the current night; automatic control resumes the next day).

## Large appliances

Water heater, heat pump, EV… declared in the options with their power and, if possible, a power sensor or on/off entity, an energy sensor and a usual time window (`23:00-02:00`). They are **never switched off**: they are used to bring the charge start forward and to warn you if they may exceed the subscribed power.

## Notifications

Choose a `notify.*` service and the level: evening plan and alerts, alerts only, or none. Messages follow the Home Assistant language.

## Known limitations (v1.0.0)

- An unconfirmed special day (`jour_special_confirme: false`) is computed with the normal-day price, then recomputed once confirmed (the plan runs every 15 minutes).
- An unknown Tempo colour uses the colour assumed in the options (white by default), then the plan is recomputed when it is announced.
- The learned consumption does not take the outdoor temperature into account yet.

## Interface with other integrations

The conductor reads the other integrations only through their public contracts:

- ha-tarifs-electricite (French keys): `tarifs_electricite.previsions` service, `puissance_souscrite`, `offre`, `prix_actuel`, `tempo_demain` sensors;
- ha-zendure-solarflow-local (English keys): `operating_mode`, `import_limit`, `charge_target_soc`, `electric_level`, `usable_capacity`, `available_energy`, `missing_energy`, `battery_power`, `max_charge_power`, `max_discharge_power`, `regulation_state`.

The conductor's own technical keys (entities, values, attributes, services) are in English; displayed names are translated.

## License

MIT © JVmaisGpeur
