# Changelog

## 1.3.4 – 26/11/2026

- **Correction** : le chauffe-eau ne chauffait pas pendant la plage ON du routeur (rattrapage en heures creuses). Le Chef d'orchestre reconnaissait la plage ON à l'état « on_slot » du routeur ; or un routeur qu'il verrouille affiche « blocked », jamais « on_slot » : il restait donc verrouillé toute la plage. La plage se lit maintenant sur le capteur « Plage en cours » (`planning`) du routeur, verrouillé ou non.
- **Carte Énergie, bloc Routeur solaire** : quand une plage ON (chauffe en heures creuses) arrive dans les 24 h, une note sous le routeur dit ce que le Chef d'orchestre a prévu : laisser chauffer (avec l'horaire et le seuil de température de la plage), bloquer la plage parce que le soleil du lendemain suffira, ou ne rien faire parce que le ballon est déjà chaud. Le Chef d'orchestre peut encore adapter la plage jusqu'à son début. Nouvel attribut `next_on` dans `routers` du plan de la nuit.
- **Plan de la nuit** : la chauffe prévue du ballon (plage ON) compte maintenant dans la puissance disponible pour la charge des batteries, comme un gros consommateur. Avant, le routeur ne comptait que pendant la minute en cours.
- **Nouvelle option « Le Chef d'orchestre peut déplacer la chauffe en heures creuses »** (Configurer → Routeurs solaires, désactivée par défaut) : si la plage ON dépasserait la puissance souscrite ou tombe pendant la charge des batteries (charge programmée, charge complète, calibration), le Chef d'orchestre bloque la plage du routeur et chauffe lui-même le ballon en marche forcée à un autre moment des mêmes heures creuses, pendant la même durée, jusqu'à la température de la plage. La note de la carte indique le nouvel horaire et la raison. Une chauffe commencée ne bouge plus.

## 1.3.3 – 25/11/2026

- **Correction** : dans la carte Énergie, le bouton du routeur ouvrait une carte vide (« Choisissez le sélecteur de mode d'un routeur F1ATB ») : la carte du routeur reçoit maintenant son sélecteur de mode (`entity`), avec tuiles, commandes et planning.
- **Carte Énergie** : un bouton « i » à côté du titre de chaque bloc (Tarif en cours, Batteries, Routeur solaire, Plan pour demain, Puissance au tableau) explique à quoi sert le bloc et ce qu'il fait, en français et en anglais.
- La petite icône carrée est remplacée par un bouton « Ouvrir la carte du routeur » sous chaque routeur, comme « Ouvrir la carte Zendure ». La pop-up porte le nom du routeur.

## 1.3.2 – 25/11/2026

- **Correction** : la puissance au tableau mettait à jour les entités depuis un autre fil que celui de Home Assistant, ce qui pouvait le faire planter (signalé dans les journaux, `manager.py` ligne 222 en 1.2.0).
- **Correction** : un routeur piloté apparaissait comme une batterie « Indisponible » dans le bloc Batteries de la carte Énergie. L'interrupteur de pilotage expose maintenant `battery_device_ids`, que la carte utilise ; les batteries restent affichées quand leur pilotage est coupé.

## 1.3.1 – 25/11/2026

- **Correction** : verrouillage du routeur conforme à ha-routeur-f1atb 1.1.x. La clé `shed` était refusée par `set_external_control`, donc le routeur n'était jamais verrouillé, et `set_mode` partait sans `controller`. Désormais : clé `mode` seule, `set_mode` « off » en tant que pilote, renouvelé toutes les 15 min, et main rendue tout de suite au déverrouillage (plus d'arrêt de 30 min qui traîne).
- **Correction** : en « Routeur d'abord », le plafond de charge des batteries (0 W tant que le ballon n'absorbe pas tout) bloquait aussi la charge réseau des heures creuses et la charge complète ; il est maintenant levé pendant toute charge réseau.
- **Correction** : plage ON lue sur le capteur `status` (« on_slot ») et puissance du ballon sur `water_heater_power` quand `on_slot_active` et `load_power` n'existent pas.
- **Correction** : un routeur ne compte plus dans la limite de soutirage, sauf pendant une plage ON.
- **Correction** : le besoin quotidien du ballon ne compte plus la journée en cours.
- **Correction** : après minuit, la « veille de jour cher » pour la charge complète se lit sur la couleur Tempo du jour même.
- **Correction** : les capteurs « Charge complète » des batteries d'un Groupe apparaissent aussi quand Zendure démarre après le Chef d'orchestre.

### Interface

- ha-routeur-f1atb ≥ 1.1.0 : `f1atb_routeur.set_external_control` (clé `mode`) et `set_mode` (avec `controller`) ; entités lues `routed_power`, `routed_energy_total`, `water_temperature`, `target_reached`, `connected`, `control_enabled`, `status`, `water_heater_power`, et si elles existent `load_power`, `on_slot_active`, `routing_power_threshold`.
- La déclaration de pilote auprès de Zendure demande ha-zendure-solarflow-local ≥ 1.5.0 (documentation corrigée).

## 1.3.0 – 25/11/2026

- **Routeur solaire F1ATB** (ha-routeur-f1atb) : routeurs listés directement à l'installation, priorité « batteries d'abord » (verrouillage par arrêts forcés de 30 min renouvelés) ou « routeur d'abord » (plafond de charge des batteries), décharge interdite pendant les plages ON, plage ON bloquée si le ballon est chaud ou si le soleil de demain suffit, délestage quand les batteries chauffent le ballon (exception été), contrôle horaire du seuil Pw, mode « Affichage seulement » respecté. Nouvel écran « Routeurs solaires » dans l'assistant et les options.
- **Consommateurs non alimentés par les batteries** : option « Alimenté par les batteries » par gros consommateur (non par défaut pour un routeur). Leur puissance en marche est envoyée à Zendure (« Puissance à ne pas couvrir ») et leur énergie sort du besoin du plan du soir.
- **Charge complète et calibration** : compteur de jours depuis la dernière charge à 100 % par batterie, charge complète programmée à partir de 20 jours (soleil, sinon nuit bon marché hors veille de jour cher), calibration en cours respectée, liste « Charge complète » (Automatique, prochain soleil, cette nuit, maintenant, ignorer) et service `full_charge`. Synthèse de la réponse du support Zendure dans le README et la carte.
- **Choisir ce qui est piloté** : interrupteurs « Pilotage des batteries » et « Pilotage du routeur » (un par routeur) sous l'interrupteur général.
- **Carte Énergie** : « Gain par kWh » et boutons « i » (gain, SOC min appliqué, marge, charge complète), ligne « Charge complète » par batterie avec menu et confirmation du coût pour « Maintenant », bloc Routeur solaire (une ligne par routeur, interrupteur, ouverture de sa carte en pop-up), mention « Réseau » pour les consommateurs exclus.
- **Correction** : le menu Avancé des réglages affichait une erreur (champ numérique sans unité).
- Changement : seule l'énergie des consommateurs non alimentés par les batteries est retirée de la consommation apprise.

### Interface

- Zendure ≥ 1.6.0 détecté par ses entités : `charge_power_limit`, `discharge_power_limit`, `excluded_power` (déclarés dans `controlled_keys`), `calibrating` par batterie.
- ha-routeur-f1atb : `f1atb_routeur.set_external_control` et `set_mode` ; entités lues `routed_power`, `routed_energy_total`, `water_temperature`, `target_reached`, `connected`, `control_enabled`, `load_power`, `on_slot_active`, `routing_power_threshold`.
- `controlled_device_ids` et `controlled_entities` ne listent que ce qui est réellement piloté.
- Nouvelles entités : `switch.battery_control`, `switch.router_control` (par routeur), `select.full_charge`, `sensor.full_charge_days` (par batterie) ; nouveaux attributs du plan : `routers`, `full_charge_planned`, `full_charge_request`, `full_charge_now_kwh`, `full_charge_now_cost`, `calibrating`, `excluded_power`, `battery_control`.
- Nouvelles alertes : `full_charge_late`, `router_found`, `router_threshold`.

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
