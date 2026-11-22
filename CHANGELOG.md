# Changelog

## 1.1.0 – 22/11/2026

- Nouvelle carte Lovelace « Chef d'orchestre énergie », livrée avec l'intégration et chargée automatiquement (`type: custom:chef-orchestre-card`) :
  - plan de la nuit avec sa raison, et interrupteur de pilotage automatique ;
  - énergie à charger, SOC cible, heure de début, gain prévu, économies du mois ;
  - graphique des 48 prochaines heures : SOC simulé, charge réseau, prix, heures creuses, avec infobulle ;
  - frise des modes prévus ;
  - alertes (puissance, charge non terminée, batterie trop petite, pilotage suspendu, données manquantes) ;
  - réglages rapides : profil de prudence, seuil de rentabilité, recalcul.
- Le plan horaire (`hourly_plan`) indique aussi les heures creuses (`off_peak`).

### Interface

- Ajout du champ `off_peak` dans l'attribut `hourly_plan` du capteur `night_plan`.

## 1.0.1 – 22/11/2026

- Correction : l'écran « Sources » de l'assistant s'affichait vide. Le contrat de tarifs et la batterie se choisissent maintenant dans des listes simples, comme les prévisions solaires.

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
