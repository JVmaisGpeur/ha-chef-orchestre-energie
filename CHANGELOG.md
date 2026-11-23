# Changelog

## 1.2.0 – 23/11/2026

- **Carte Énergie** (`type: custom:chef-orchestre-energie-card`), livrée avec l'intégration : tarif en cours, batteries, plan pour demain et puissance au tableau, avec l'interrupteur de pilotage. Les boutons ouvrent la carte Tarifs électricité, la carte Zendure et la carte détaillée du plan dans une pop-up. Blocs masqués par défaut, seuils de jauge 80 / 95 % réglables, états dégradés affichés en clair, français et anglais.
- **Réserve de SOC** : une nuit non rentable, le SOC minimum de chaque batterie passe à la réserve (50 % par défaut, nouvelle entité « Réserve si non rentable ») ; il revient à votre valeur exacte dès que c'est rentable, quand le pilotage est coupé, au redémarrage ou à la suppression.
- **SOC maximum à 100 %** les jours où la prévision solaire dépasse ce que la batterie peut stocker sous votre maximum ; votre valeur revient au début des heures creuses suivantes. La charge réseau ne dépasse jamais votre maximum.
- Vos SOC min et max sont mémorisés par le Chef d'orchestre ; une valeur changée pendant la réserve est retenue. Au plus une écriture toutes les 30 minutes dans la mémoire de la batterie.
- **Nouvel assistant** en six écrans : détection des intégrations et de leurs versions, sources (seulement s'il y a plusieurs choix), rentabilité, gros consommateurs (puissance en kW), capteur de puissance au tableau, récapitulatif avec activation du pilotage. Plus aucune puissance souscrite ni entité de consommation à saisir.
- La consommation de la maison est lue dans le tableau Énergie de Home Assistant quand aucun capteur n'est saisi.
- Tarifs électricité devient recommandée et non bloquante : sans elle, l'intégration s'installe et attend les prix pour piloter.
- Sans prévision solaire pendant 24 h, plus de charge en heures creuses (plan « Prévision solaire indisponible »).
- Nouveau capteur « Puissance au tableau » ; options Puissance : capteur, seuils de jauge, marge, triphasé.
- Une installation 1.1.x garde ses entités, ses réglages et sa carte.

### Interface

- L'interrupteur `auto_control` porte `controlled_device_id`, `controlled_device_ids`, `controlled_entities` et `interface_version` (1).
- Déclaration de pilote externe par `zendure_local.set_external_control` (ha-zendure-solarflow-local ≥ 1.4.0) à l'activation et toutes les 15 minutes, retirée quand le pilotage est coupé.
- Capteur `night_plan` : nouveaux attributs `price_gap`, `charge_end`, `reserve_soc`, `user_min_soc`, `user_max_soc`, `applied_min_soc`, `applied_max_soc`, `full_charge`, `gain_threshold`, `efficiency`, `tariff_ok`, `tariff_entity`, `battery_ok`, `reserve_available`, `consumption_source` ; nouvelles valeurs de `missing` : `tariff`, `solar_forecast`.
- Nouvelles entités `number.reserve_soc` et `sensor.board_power` ; nouvelle alerte de réparation `reserve_unavailable`.

## 1.1.2 – 22/11/2026

- Correction : le plan restait sur « Données manquantes ». Les prévisions tarifaires commencent à l'instant de l'appel, alors que la grille de calcul démarre au quart d'heure précédent : le premier pas ne trouvait pas son tarif et le calcul s'arrêtait. Chaque pas prend maintenant la tranche qui couvre son milieu.
- Le capteur « Plan de la nuit » indique ce qui manque (attribut `missing`), et la carte l'affiche dans l'alerte.

### Interface

- Ajout de l'attribut `missing` au capteur `night_plan` : `sources`, `tariff_forecast`, `battery_state`, `subscribed_power`, `off_peak_price`, `error`.

## 1.1.1 – 22/11/2026

- Correction : les compteurs d'énergie en Wh, MWh ou GWh (Enphase, par exemple) sont convertis en kWh, chacun selon l'unité enregistrée avec ses statistiques, même s'il est momentanément indisponible. Avant, la consommation apprise pouvait être 1 000 fois trop faible ou trop forte.
- Aide ajoutée sous chaque capteur de l'écran Consommation, avec des exemples Enphase, et l'avertissement sur les batteries AC.

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
