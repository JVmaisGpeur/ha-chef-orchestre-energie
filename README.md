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
| [ha-tarifs-electricite](https://github.com/JVmaisGpeur/ha-tarifs-electricite) | ≥ 1.1.0, recommandée | Prix, heures creuses, Tempo, puissance souscrite. Sans elle, le Chef d'orchestre s'installe mais ne pilote pas |
| [ha-zendure-solarflow-local](https://github.com/JVmaisGpeur/ha-zendure-solarflow-local) | ≥ 1.3.0 | Batterie ou Groupe de batteries à piloter |
| Une prévision solaire | – | Forecast.Solar, Open-Meteo Solar Forecast ou Solcast |
| Le tableau Énergie de Home Assistant (recommandé) | – | La consommation de la maison y est apprise sans rien saisir |
| Un capteur de puissance au tableau (facultatif) | – | Par exemple Shelly Pro 3EM, pour la jauge de la carte Énergie et le déverrouillage du routeur |
| [ha-zendure-solarflow-local](https://github.com/JVmaisGpeur/ha-zendure-solarflow-local) ≥ 1.6.0 (facultatif) | – | Plafonds de charge/décharge, puissance à ne pas couvrir, calibration : consommateurs exclus et routeur |
| [ha-routeur-f1atb](https://github.com/JVmaisGpeur/ha-routeur-f1atb) ≥ 1.0.0 (facultatif) | – | Routeur solaire F1ATB à piloter |

Avec Forecast.Solar, ajoutez une entrée par orientation de panneaux : le Chef d'orchestre les additionne heure par heure, comme le tableau Énergie.

Une batterie ne doit être pilotée que par une seule intégration ou automatisation à la fois. Désactivez vos anciennes automatisations de charge en heures creuses avant d'activer le pilotage.

## Installation

1. HACS → Intégrations → menu ⋮ → Dépôts personnalisés → `https://github.com/JVmaisGpeur/ha-chef-orchestre-energie`, catégorie Intégration.
2. Installez « Chef d'orchestre énergie », redémarrez Home Assistant.
3. Paramètres → Appareils et services → Ajouter une intégration → Chef d'orchestre énergie.

L'assistant détecte seul les autres intégrations et ne redemande rien de ce qu'elles savent déjà (puissance souscrite, offre, prix, heures creuses, modes et SOC de la batterie) :

1. **Détection** : intégrations trouvées et leurs versions ; Zendure et une prévision solaire sont obligatoires, Tarifs est recommandée ;
2. **Sources** : seulement s'il y a plusieurs choix (deux contrats, plusieurs batteries, plusieurs champs de panneaux) ;
3. **Rentabilité** : seuil (0,02 €/kWh), rendement (85 %), réserve si non rentable (50 %) ;
4. **Gros consommateurs** : nom, puissance en kW, capteur de détection facultatif ;
5. **Mesure de puissance** : capteur de puissance au tableau, facultatif ;
6. **Récapitulatif**, avec l'activation du pilotage.

La consommation de la maison est lue dans le tableau Énergie de Home Assistant. Tout se modifie ensuite dans **Configurer** : économie, puissance (capteur, seuils de la jauge, marge, triphasé), gros consommateurs, sources, consommation (réglage manuel si vous n'utilisez pas le tableau Énergie), notifications, avancé.

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

### SOC minimum et maximum (réserve)

- **Nuit non rentable** : le SOC minimum de chaque batterie passe à la **réserve** (50 % par défaut, entité « Réserve si non rentable ») si son propre réglage est plus bas. La batterie garde ainsi son énergie au lieu de la dépenser à perte.
- **Nuit rentable** : chaque batterie retrouve son SOC minimum à sa valeur exacte.
- **Soleil abondant** : si la prévision solaire dépasse ce que la batterie peut stocker sous votre SOC maximum, le SOC maximum passe à 100 % pour la journée, puis revient à votre valeur au début des heures creuses suivantes. La charge réseau ne dépasse jamais votre maximum.
- Vos valeurs sont mémorisées par le Chef d'orchestre et restituées quand le pilotage est coupé, au redémarrage et à la suppression de l'intégration. Si vous changez un SOC pendant la réserve, la nouvelle valeur est retenue.
- Ces réglages sont écrits dans la mémoire de la batterie : au plus une écriture toutes les 30 minutes, sauf pour rendre vos valeurs.

Pendant la charge, la limite de soutirage vaut `puissance souscrite × (1 − marge)`, avec une marge d'au moins 10 % (÷ 3 en triphasé). La batterie la respecte en temps réel : si le four ou le chauffe-eau démarre, elle réduit sa charge aussitôt.

## Entités

| Entité | Rôle |
| --- | --- |
| Pilotage automatique | Coupé, plus aucune commande n'est envoyée |
| Profil de prudence | Prudent, équilibré, économe |
| Seuil de rentabilité | €/kWh, modifiable à chaud |
| Réserve si non rentable | SOC minimum appliqué les nuits non rentables (0 à 50 %) |
| Puissance au tableau | Puissance appelée, avec la puissance souscrite, la marge et l'état des gros consommateurs en attributs |
| Plan de la nuit | Charge, repos, non rentable, rien à couvrir, suspendu, données manquantes ; attributs `reason` et `hourly_plan` |
| Énergie à charger, SOC cible, Début de charge | Le plan de la nuit |
| Consommation prévue, Besoin en heures pleines, Production solaire prévue | Les prévisions utilisées |
| Gain prévu, Économies du mois | Ce que ça rapporte |
| Rendement de la batterie, Fiabilité de la prévision | Diagnostic |
| Alerte puissance | Risque de dépasser la puissance souscrite |
| Recalculer | Relance le calcul |

Services : `chef_orchestre_energie.recalculate` et `chef_orchestre_energie.force_night` (charge ou repos imposé pour la nuit en cours ; le pilotage reprend le lendemain).

## Carte Énergie

Vue d'ensemble livrée avec l'intégration et chargée toute seule. Une ligne suffit :

```yaml
type: custom:chef-orchestre-energie-card
show_tariff: true      # tarif en cours
show_batteries: true   # batteries
show_plan: true        # plan pour demain
show_power: true       # puissance au tableau
gauge_warn: 80         # jauge orange (% de la puissance souscrite)
gauge_crit: 95         # jauge rouge
```

Les blocs sont masqués par défaut, comme dans la carte Tarifs ; l'éditeur visuel les coche pour vous.

- **En-tête** : interrupteur « Pilotage actif / coupé ».
- **Tarif en cours** : période, prix, prochain changement, prix de l'autre période ; bouton vers la carte Tarifs électricité.
- **Batteries** : SOC du groupe, puissance, mode (« Piloté par le Chef d'orchestre » ou « Réglé dans la carte Zendure »), et pour chaque batterie son SOC, sa puissance, ses SOC min et max ; bouton vers la carte Zendure.
- **Plan pour demain** : rentable, non rentable ou en pause, solaire prévu, consommation estimée, énergie à charger, écart de prix face au seuil, créneau de charge, SOC minimum appliqué ; bouton vers la carte détaillée ci-dessous.
- **Puissance au tableau** : jauge face à la puissance souscrite, marge avant disjonction, gros consommateurs.
- **Pied** : accès aux réglages du Chef d'orchestre.

Les boutons ouvrent les autres cartes dans une pop-up. La carte Énergie ne modifie ni le tarif ni les réglages des batteries. Un bloc sans source affiche un message à sa place.

## Carte détaillée du plan

La carte est livrée avec l'intégration et se charge toute seule : Modifier le tableau de bord → Ajouter une carte → « Chef d'orchestre énergie ».

```yaml
type: custom:chef-orchestre-card
name: Batteries            # facultatif
show_chart: true           # graphique des 48 h à venir
show_modes: true           # frise des modes prévus
show_settings: true        # réglages rapides
```

Elle montre le plan de la nuit et sa raison, les chiffres clés (énergie à charger, SOC cible, heure de début, gain prévu, économies du mois), le SOC simulé et les prix sur 48 h avec les heures creuses, la frise des modes, les alertes, et les réglages rapides (profil de prudence, seuil de rentabilité, recalcul). Elle suit la langue et le thème de Home Assistant.

## Gros consommateurs

Chauffe-eau, PAC, VE… déclarés dans les options avec leur puissance, et si possible un capteur de puissance ou une entité marche/arrêt, un capteur d'énergie et une plage habituelle (`23:00-02:00`). Ils ne sont **jamais coupés** : ils servent à avancer l'heure de début de charge, et à vous prévenir s'ils risquent de dépasser la puissance souscrite. La puissance se saisit en kW.

**Alimenté par les batteries** (oui par défaut) : mettez « non » pour qu'un appareil, par exemple le chauffe-eau, ne soit jamais alimenté par les batteries. Quand il est en marche, le Chef d'orchestre indique sa puissance à Zendure (« Puissance à ne pas couvrir ») : les batteries couvrent le reste de la maison, l'appareil prend le solaire ou le réseau. Son énergie sort aussi du besoin que le plan du soir fait couvrir aux batteries. Nécessite ha-zendure-solarflow-local 1.6.0 ou plus récente et un capteur de mise en route.

## Routeur solaire F1ATB

Avec [ha-routeur-f1atb](https://github.com/JVmaisGpeur/ha-routeur-f1atb), le Chef d'orchestre arbitre entre ballon et batteries. Si l'intégration a déjà des routeurs, l'assistant les liste directement, cochés : vous décochez ceux à ne pas piloter. Chaque routeur retenu devient un gros consommateur que les batteries n'alimentent pas.

- **Batteries toujours d'abord** (par défaut) : le routeur est verrouillé (le Chef d'orchestre prend son mode et le met à l'arrêt, renouvelé toutes les 15 minutes ; rendu aussitôt au déverrouillage) tant que les batteries peuvent prendre le surplus. Il est libéré, après 2 minutes, quand elles sont pleines ou qu'elles chargent à au moins 95 % de leur puissance maximale avec du surplus qui part au réseau ; il est reverrouillé dès qu'elles se déchargent ou que leur charge passe sous 80 %.
- **Routeur d'abord** : le ballon chauffe en premier ; les batteries ne chargent que ce qu'il n'absorbe pas, jusqu'à ce qu'il soit chaud.
- Pendant une plage ON du routeur (chauffe en heures creuses), les batteries ne se déchargent pas. La plage est bloquée si le ballon est déjà chaud ou si le soleil de demain suffit.
- La chauffe prévue en heures creuses est comptée dans le plan de la nuit : la charge des batteries tient compte de sa puissance pour ne pas dépasser la puissance souscrite. Une note sous le routeur, dans la carte Énergie, dit ce que le Chef d'orchestre a prévu.
- Option « Le Chef d'orchestre peut déplacer la chauffe en heures creuses » (Configurer → Routeurs solaires, désactivée par défaut) : si la plage ON dépasserait la puissance souscrite ou tombe pendant la charge des batteries (charge programmée, charge complète, calibration), le Chef d'orchestre bloque la plage du routeur et chauffe lui-même le ballon (marche forcée) à un autre moment des mêmes heures creuses, pendant la même durée, jusqu'à la température de la plage.
- Si les batteries se déchargent pendant que le routeur chauffe, plus de 2 minutes, le routeur est délesté (sauf exception été : batteries au-dessus de 90 % et soleil de demain suffisant).
- Quand le routeur l'expose, son seuil Pw est vérifié chaque heure : il doit être au moins 20 W sous la cible des batteries (par exemple −20 W).
- Jamais d'écriture permanente dans le routeur ; il ne prend la main que sur votre accord. Routeur hors ligne, ou réglé sur « Affichage seulement » dans sa carte : aucune commande, et la protection passe par la puissance à ne pas couvrir de Zendure.

## Charge complète et calibration

D'après le support Zendure, les batteries peuvent lancer une calibration automatique du niveau de charge après environ 30 jours sans charge à 100 %. Elle cherche à remplir la batterie, avec le solaire ou à défaut le réseau, et peut s'interrompre puis reprendre. Une charge à 100 % une à deux fois par mois suffit en général à l'éviter ; une décharge complète n'est pas un entretien et use la batterie ; pendant une calibration, laissez l'appareil sous tension, avec une limite de charge à 100 % et aucune puissance de sortie bloquée à 0 W. Si une calibration reste bloquée, contactez le support Zendure (modèle, numéro de série, versions, historique du SOC).

Le Chef d'orchestre compte les jours depuis la dernière charge complète de chaque batterie (capteur « Charge complète »). À partir de 20 jours (réglable dans Avancé), il programme une charge à 100 % : un jour de soleil si la prévision suffit, sinon la nuit d'heures creuses la moins chère, en évitant les veilles de jour Tempo blanc ou rouge. Pendant une calibration, il la laisse aller au bout. La liste « Charge complète » (carte, entité, service `chef_orchestre_energie.full_charge`) permet de choisir : Automatique, Au prochain jour de soleil, Cette nuit, Maintenant, Ignorer pour ce cycle.

## Choisir ce qui est piloté

L'interrupteur général « Pilotage automatique » arrête tout. Sous lui, « Pilotage des batteries » et un « Pilotage du routeur » par routeur permettent de laisser une partie en autonome ; rallumé, l'interrupteur général retrouve ces choix.

## Notifications

Choisissez un service `notify.*` et le niveau : plan du soir et alertes, alertes uniquement, ou aucune. Les messages suivent la langue de Home Assistant.

## Limites connues

- Un jour spécial non confirmé (`jour_special_confirme: false`) est calculé avec le prix d'un jour normal, puis recalculé dès la confirmation (le plan est relancé toutes les 15 minutes).
- Une couleur Tempo inconnue prend la couleur supposée dans les options (blanc par défaut), puis le plan est recalculé à l'annonce.
- La consommation apprise ne tient pas encore compte de la température extérieure.

## Interface pour les autres intégrations

### Ce que le Chef d'orchestre expose

L'interrupteur **Pilotage automatique** (`switch`, `translation_key: auto_control`) est l'entité stable à détecter. Ses attributs :

| Attribut | Contenu |
| --- | --- |
| `controlled_device_id` | Appareil piloté (batterie ou Groupe) |
| `controlled_device_ids` | Appareils réellement pilotés : batterie ou Groupe et ses membres (si le pilotage des batteries est actif), routeurs dont il a la main |
| `controlled_entities` | Entités que le Chef d'orchestre commande : mode, limite de soutirage, SOC cible, plafonds et puissance à ne pas couvrir (Zendure ≥ 1.6.0), et SOC min/max de chaque batterie |
| `interface_version` | `1` |

Quand le pilotage est actif, il se déclare aussi auprès de ha-zendure-solarflow-local (≥ 1.5.0) par le service `zendure_local.set_external_control` (`device_id`, `active`, `controller`, `controlled_keys`), à l'activation puis toutes les 15 minutes, et retire sa déclaration quand le pilotage est coupé. Sans renouvellement pendant 30 minutes, la carte Zendure réaffiche seule tous ses réglages. Avec une version plus ancienne de Zendure, rien n'est déclaré et le reste fonctionne.

### Ce qu'il lit

Le Chef d'orchestre ne lit les autres intégrations que par leurs contrats publics :

- ha-tarifs-electricite (clés en français) : service `tarifs_electricite.previsions`, capteurs `puissance_souscrite`, `offre`, `prix_actuel`, `tempo_demain` ;
- ha-zendure-solarflow-local (clés en anglais) : `operating_mode`, `import_limit`, `charge_target_soc`, `electric_level`, `usable_capacity`, `available_energy`, `missing_energy`, `battery_power`, `max_charge_power`, `max_discharge_power`, `regulation_state`, et par batterie `min_soc` et `soc_set` (sans eux, la réserve est désactivée avec une alerte dans Réparations) ; en 1.6.0, `charge_power_limit`, `discharge_power_limit`, `excluded_power` et par batterie `calibrating`, détectés par leur présence ;
- ha-routeur-f1atb ≥ 1.1.0 (domaine `f1atb_routeur`) : services `set_external_control` (clé `mode` seulement) et `set_mode` (avec `controller`) ; entités `routed_power`, `routed_energy_total`, `water_temperature`, `target_reached`, `connected`, `control_enabled`, `status`, `water_heater_power` (`load_power`, `on_slot_active`, `routing_power_threshold` lues si elles existent).

Les clés techniques du Chef d'orchestre (entités, valeurs, attributs, services) sont en anglais ; les noms affichés sont traduits.

## Licence

MIT © JVmaisGpeur
