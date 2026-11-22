# Changelog

## 1.0.0 – 22/11/2026

Première version.

- Calcul du soir par pas de 15 minutes : besoin des heures pleines, rentabilité d'une charge réseau, quantité et heure de début de charge.
- Pilotage de ha-zendure-solarflow-local (batterie seule ou Groupe) par `operating_mode`, `import_limit` et `charge_target_soc`.
- Lecture de ha-tarifs-electricite par le service `previsions` et ses capteurs ; prix inconnus complétés (couleur Tempo supposée).
- Prévision solaire de plusieurs champs additionnée via la plateforme du tableau Énergie, avec facteur de correction appris.
- Consommation apprise heure par heure (semaine, samedi, dimanche et jours fériés), médiane des dernières semaines.
- Rendement aller-retour appris sur 30 jours.
- Gros consommateurs : planification de la puissance de charge et alertes, sans jamais les couper.
- Entités, services `recalculate` et `force_night`, notifications et alertes Réparations.
- Entièrement en français et en anglais.

### Interface

- Clés techniques en anglais : entités `night_plan`, `energy_to_charge`, `target_soc`, `charge_start`, `forecast_consumption`, `peak_need`, `forecast_solar`, `forecast_gain`, `monthly_savings`, `measured_efficiency`, `forecast_reliability`, `power_alert`, `auto_control`, `profile`, `gain_threshold`, `recalculate`.
