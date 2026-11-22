# Chef d'orchestre énergie

[English version](README.en.md)

Intégration Home Assistant qui décide chaque soir comment utiliser vos batteries pour que les heures pleines les plus chères soient couvertes par la batterie, au moindre coût.

Elle ne parle à aucun matériel. Elle **lit** vos tarifs, la prévision solaire et la consommation de la maison, et **pilote** votre batterie (ou votre Groupe de batteries) par son mode, sa limite de soutirage et son SOC cible de charge.

Chaque soir, elle répond à trois questions :

1. Faut-il charger cette nuit en heures creuses, et combien ?
2. Le gain justifie-t-il les pertes de la batterie ? Sinon, la batterie reste à l'arrêt la nuit, sans cycle inutile.
3. À quelle puissance charger sans faire disjoncter, compte tenu du chauffe-eau, de la PAC ou du VE ?

## Prérequis

| Intégration | Version | Rôle |
| --- | --- | --- |
| [ha-tarifs-electricite](https://github.com/JVmaisGpeur/ha-tarifs-electricite) | ≥ 1.1.0 | Prix, heures creuses, Tempo, puissance souscrite |
| [ha-zendure-solarflow-local](https://github.com/JVmaisGpeur/ha-zendure-solarflow-local) | ≥ 1.3.0 | Batterie ou Groupe de batteries à piloter |
| Une prévision solaire | – | Forecast.Solar, Open-Meteo Solar Forecast ou Solcast |
| Un compteur d'énergie (recommandé) | – | Pour apprendre la consommation de la maison |

Avec Forecast.Solar, ajoutez une entrée par orientation de panneaux : le Chef d'orchestre les additionne heure par heure, comme le tableau Énergie.

Une batterie ne doit être pilotée que par une seule intégration ou automatisation à la fois. Désactivez vos anciennes automatisations de charge en heures creuses avant d'activer le pilotage.

## Installation

1. HACS → Intégrations → menu ⋮ → Dépôts personnalisés → `https://github.com/JVmaisGpeur/ha-chef-orchestre-energie`, catégorie Intégration.
2. Installez « Chef d'orchestre énergie », redémarrez Home Assistant.
3. Paramètres → Appareils et services → Ajouter une intégration → Chef d'orchestre énergie.

L'assistant tient en quatre écrans : sources, consommation, économie, puissance. Tout se modifie ensuite dans **Configurer** : économie, puissance, consommation, sources, gros consommateurs, notifications, avancé.

## Comment il décide

Avant chaque début d'heures creuses (et dès qu'une donnée change), il simule par pas de 15 minutes la période qui va de la fin de cette nuit au début des heures creuses suivantes :

- le solaire couvre d'abord la maison, le surplus entre dans la batterie ;
- une charge réseau n'est utile que si `prix HP − (prix HC ÷ rendement + usure)` dépasse le **seuil de rentabilité** (0,02 €/kWh par défaut) ;
- il cherche l'énergie minimale en batterie pour ne jamais descendre sous le SOC minimum pendant ces heures, majorée de la marge du profil (prudent 20 %, équilibré 10 %, économe 0 %) ;
- si la batterie est trop petite, il garde l'énergie pour les heures les plus chères.

| Situation | Mode envoyé à la batterie |
| --- | --- |
| Heures creuses, pas de charge | `off` (ou `smart_charge` s'il y a du soleil) |
| Heures creuses, charge prévue | `grid_charge` jusqu'au SOC cible, en finissant 30 min avant la fin des HC |
| Heures pleines | `smart` |
| Heures pleines réservées pour plus tard | `smart_charge` |
| Pilotage coupé ou données manquantes | aucune commande |

Pendant la charge, la limite de soutirage vaut `puissance souscrite × (1 − marge)`, avec une marge d'au moins 10 % (÷ 3 en triphasé). La batterie la respecte en temps réel : si le four ou le chauffe-eau démarre, elle réduit sa charge aussitôt.

## Entités

| Entité | Rôle |
| --- | --- |
| Pilotage automatique | Coupé, plus aucune commande n'est envoyée |
| Profil de prudence | Prudent, équilibré, économe |
| Seuil de rentabilité | €/kWh, modifiable à chaud |
| Plan de la nuit | Charge, repos, non rentable, rien à couvrir, suspendu, données manquantes ; attributs `reason` et `hourly_plan` |
| Énergie à charger, SOC cible, Début de charge | Le plan de la nuit |
| Consommation prévue, Besoin en heures pleines, Production solaire prévue | Les prévisions utilisées |
| Gain prévu, Économies du mois | Ce que ça rapporte |
| Rendement de la batterie, Fiabilité de la prévision | Diagnostic |
| Alerte puissance | Risque de dépasser la puissance souscrite |
| Recalculer | Relance le calcul |

Services : `chef_orchestre_energie.recalculate` et `chef_orchestre_energie.force_night` (charge ou repos imposé pour la nuit en cours ; le pilotage reprend le lendemain).

## Gros consommateurs

Chauffe-eau, PAC, VE… déclarés dans les options avec leur puissance, et si possible un capteur de puissance ou une entité marche/arrêt, un capteur d'énergie et une plage habituelle (`23:00-02:00`). Ils ne sont **jamais coupés** : ils servent à avancer l'heure de début de charge, et à vous prévenir s'ils risquent de dépasser la puissance souscrite.

## Notifications

Choisissez un service `notify.*` et le niveau : plan du soir et alertes, alertes uniquement, ou aucune. Les messages suivent la langue de Home Assistant.

## Limites connues (v1.0.0)

- Un jour spécial non confirmé (`jour_special_confirme: false`) est calculé avec le prix d'un jour normal, puis recalculé dès la confirmation (le plan est relancé toutes les 15 minutes).
- Une couleur Tempo inconnue prend la couleur supposée dans les options (blanc par défaut), puis le plan est recalculé à l'annonce.
- La consommation apprise ne tient pas encore compte de la température extérieure.

## Interface pour les autres intégrations

Le Chef d'orchestre ne lit les autres intégrations que par leurs contrats publics :

- ha-tarifs-electricite (clés en français) : service `tarifs_electricite.previsions`, capteurs `puissance_souscrite`, `offre`, `prix_actuel`, `tempo_demain` ;
- ha-zendure-solarflow-local (clés en anglais) : `operating_mode`, `import_limit`, `charge_target_soc`, `electric_level`, `usable_capacity`, `available_energy`, `missing_energy`, `battery_power`, `max_charge_power`, `max_discharge_power`, `regulation_state`.

Les clés techniques du Chef d'orchestre (entités, valeurs, attributs, services) sont en anglais ; les noms affichés sont traduits.

## Licence

MIT © JVmaisGpeur
