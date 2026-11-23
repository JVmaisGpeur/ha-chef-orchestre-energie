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
| [ha-tarifs-electricite](https://github.com/JVmaisGpeur/ha-tarifs-electricite) | ≥ 1.1.0, recommended | Prices, off-peak hours, Tempo, subscribed power. Without it the conductor installs but does not drive anything |
| [ha-zendure-solarflow-local](https://github.com/JVmaisGpeur/ha-zendure-solarflow-local) | ≥ 1.3.0 | Battery or battery Group to drive |
| A solar forecast | – | Forecast.Solar, Open-Meteo Solar Forecast or Solcast |
| The Home Assistant Energy dashboard (recommended) | – | The house consumption is learned from it with nothing to enter |
| A panel power sensor (optional) | – | For example Shelly Pro 3EM, for the Energy card gauge |

With Forecast.Solar, add one entry per panel orientation: the conductor adds them up hour by hour, like the Energy dashboard.

A battery must be driven by a single integration or automation at a time. Disable your old off-peak charging automations before enabling automatic control.

## Installation

1. HACS → Integrations → ⋮ menu → Custom repositories → `https://github.com/JVmaisGpeur/ha-chef-orchestre-energie`, category Integration.
2. Install "Chef d'orchestre énergie", restart Home Assistant.
3. Settings → Devices & services → Add integration → Chef d'orchestre énergie.

The setup detects the other integrations by itself and never asks again for what they already know (subscribed power, offer, prices, off-peak hours, battery modes and SOC):

1. **Detection**: integrations found and their versions; Zendure and a solar forecast are required, Tariffs is recommended;
2. **Sources**: only when there are several choices (two contracts, several batteries, several panel arrays);
3. **Profitability**: threshold (0.02 €/kWh), efficiency (85 %), reserve when not profitable (50 %);
4. **Large loads**: name, power in kW, optional detection sensor;
5. **Power measurement**: optional panel power sensor;
6. **Summary**, with control activation.

The house consumption is read from the Home Assistant Energy dashboard. Everything can be changed later in **Configure**: economics, power (sensor, gauge thresholds, margin, three-phase), large loads, sources, consumption (manual setting if you do not use the Energy dashboard), notifications, advanced.

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

### Min and max SOC (reserve)

- **Non-profitable night**: each battery's min SOC is raised to the **reserve** (50 % by default, "Reserve if not profitable" entity) if its own setting is lower. The battery keeps its energy instead of spending it at a loss.
- **Profitable night**: each battery gets its min SOC back at its exact value.
- **Plenty of sun**: if the solar forecast exceeds what the battery can store under your max SOC, the max SOC goes to 100 % for the day, then back to your value at the start of the next off-peak hours. Grid charging never exceeds your maximum.
- Your values are remembered by the conductor and restored when control is turned off, on restart and when the integration is removed. If you change a SOC during the reserve, the new value is kept.
- These settings are written to the battery memory: at most one write every 30 minutes, except to restore your values.

While charging, the import limit is `subscribed power × (1 − margin)`, with a margin of at least 10 % (÷ 3 for three-phase). The battery enforces it in real time: if the oven or water heater starts, it reduces its charge immediately.

## Entities

| Entity | Role |
| --- | --- |
| Automatic control | Off: no command is sent anymore |
| Caution profile | Cautious, balanced, economical |
| Profitability threshold | €/kWh, adjustable live |
| Reserve if not profitable | Min SOC applied on non-profitable nights (0 to 50 %) |
| Panel power | Power drawn, with subscribed power, margin and large-load states as attributes |
| Night plan | Charge, rest, not profitable, nothing to cover, suspended, missing data; `reason` and `hourly_plan` attributes |
| Energy to charge, Target state of charge, Charge start | Tonight's plan |
| Forecast consumption, Peak-hour need, Forecast solar production | The forecasts used |
| Forecast gain, Savings this month | What it earns |
| Battery efficiency, Forecast reliability | Diagnostics |
| Power alert | Risk of exceeding the subscribed power |
| Recalculate | Recomputes the plan |

Services: `chef_orchestre_energie.recalculate` and `chef_orchestre_energie.force_night` (charge or rest imposed for the current night; automatic control resumes the next day).

## Energy card

Overview card shipped with the integration and loaded by itself. One line is enough:

```yaml
type: custom:chef-orchestre-energie-card
show_tariff: true      # current tariff
show_batteries: true   # batteries
show_plan: true        # plan for tomorrow
show_power: true       # panel power
gauge_warn: 80         # gauge orange (% of the subscribed power)
gauge_crit: 95         # gauge red
```

Blocks are hidden by default, as in the Tariffs card; the visual editor ticks them for you.

- **Header**: "Control on / off" switch.
- **Current tariff**: period, price, next change, price of the other period; button to the Electricity Tariffs card.
- **Batteries**: group SOC, power, mode ("Driven by the Conductor" or "Set in the Zendure card"), and for each battery its SOC, power, min and max SOC; button to the Zendure card.
- **Plan for tomorrow**: profitable, not profitable or paused, expected solar, estimated use, energy to charge, price gap against the threshold, charging slot, applied min SOC; button to the detailed card below.
- **Panel power**: gauge against the subscribed power, margin before tripping, large loads.
- **Footer**: access to the conductor settings.

Buttons open the other cards in a pop-up. The Energy card never changes the tariff or the battery settings. A block without its source shows a message instead.

## Detailed plan card

The card ships with the integration and loads by itself: Edit dashboard → Add card → "Chef d'orchestre énergie".

```yaml
type: custom:chef-orchestre-card
name: Batteries            # optional
show_chart: true           # next 48 h chart
show_modes: true           # planned mode strip
show_settings: true        # quick settings
```

It shows tonight's plan and its reason, the key figures (energy to charge, target SOC, start time, forecast gain, monthly savings), the simulated SOC and prices over 48 h with off-peak hours, the mode strip, the alerts, and quick settings (caution profile, profitability threshold, recalculate). It follows the Home Assistant language and theme.

## Large appliances

Water heater, heat pump, EV… declared in the options with their power and, if possible, a power sensor or on/off entity, an energy sensor and a usual time window (`23:00-02:00`). They are **never switched off**: they are used to bring the charge start forward and to warn you if they may exceed the subscribed power. Power is entered in kW.

## Notifications

Choose a `notify.*` service and the level: evening plan and alerts, alerts only, or none. Messages follow the Home Assistant language.

## Known limitations

- An unconfirmed special day (`jour_special_confirme: false`) is computed with the normal-day price, then recomputed once confirmed (the plan runs every 15 minutes).
- An unknown Tempo colour uses the colour assumed in the options (white by default), then the plan is recomputed when it is announced.
- The learned consumption does not take the outdoor temperature into account yet.

## Interface with other integrations

### What the conductor exposes

The **Automatic control** switch (`switch`, `translation_key: auto_control`) is the stable entity to detect. Its attributes:

| Attribute | Content |
| --- | --- |
| `controlled_device_id` | Driven device (battery or Group) |
| `controlled_device_ids` | Driven device and each member battery |
| `controlled_entities` | Entities the conductor commands: mode, import limit, target SOC, and min/max SOC of each battery |
| `interface_version` | `1` |

While control is on, it also declares itself to ha-zendure-solarflow-local (≥ 1.4.0) through the `zendure_local.set_external_control` service (`device_id`, `active`, `controller`, `controlled_keys`), when turned on and then every 15 minutes, and withdraws when control is turned off. Without renewal for 30 minutes, the Zendure card shows all its settings again by itself. With an older Zendure version nothing is declared and everything else works.

### What it reads

The conductor reads the other integrations only through their public contracts:

- ha-tarifs-electricite (French keys): `tarifs_electricite.previsions` service, `puissance_souscrite`, `offre`, `prix_actuel`, `tempo_demain` sensors;
- ha-zendure-solarflow-local (English keys): `operating_mode`, `import_limit`, `charge_target_soc`, `electric_level`, `usable_capacity`, `available_energy`, `missing_energy`, `battery_power`, `max_charge_power`, `max_discharge_power`, `regulation_state`, and per battery `min_soc` and `soc_set` (without them the reserve is disabled with a Repairs alert).

The conductor's own technical keys (entities, values, attributes, services) are in English; displayed names are translated.

## License

MIT © JVmaisGpeur
