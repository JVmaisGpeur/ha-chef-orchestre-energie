/*
 * Carte « Énergie » du Chef d'orchestre (E3) — livrée avec l'intégration chef_orchestre_energie.
 * Vue d'ensemble : tarif en cours, batteries, plan pour demain, puissance au tableau.
 * Elle ne modifie ni le tarif ni les réglages batterie : elle ouvre les cartes
 * Tarifs électricité et Zendure dans une pop-up.
 *
 *   type: custom:chef-orchestre-energie-card
 *   show_tariff: true      # blocs masqués par défaut, comme dans la carte Tarifs
 *   show_batteries: true
 *   show_router: true      # routeurs solaires F1ATB (v1.3.0)
 *   show_plan: true
 *   show_power: true
 *   gauge_warn: 80         # % de la puissance souscrite : jauge orange
 *   gauge_crit: 95         # jauge rouge
 */
const ENERGY_CARD_VERSION = "1.3.0";
const CHEF = "chef_orchestre_energie";
const TARIFF = "tarifs_electricite";
const ZENDURE = "zendure_local";
const BLOCKS = ["show_tariff", "show_batteries", "show_router", "show_plan", "show_power"];

const ENERGY_I18N = {
  fr: {
    title: "Énergie",
    subtitle: "Chef d'orchestre",
    pilotOn: "Pilotage actif",
    pilotOff: "Pilotage coupé",
    noChef: "Chef d'orchestre introuvable : installez et configurez l'intégration Chef d'orchestre énergie.",
    unavailable: "Indisponible",
    tariff: {
      title: "Tarif en cours",
      next: "Prochain changement",
      at: "à",
      other: "Autre période",
      open: "Ouvrir la carte Tarifs électricité",
      missing: "Tarifs électricité absente ou trop ancienne (1.1.0 minimum) : la rentabilité n'est pas calculée.",
      repairs: "Voir dans Réparations",
      tempo: { bleu: "Jour bleu", blanc: "Jour blanc", rouge: "Jour rouge" },
    },
    bat: {
      title: "Batteries",
      group: "Ensemble",
      charging: "Charge",
      discharging: "Décharge",
      resting: "Au repos",
      mode: "Mode",
      piloted: "Piloté par le Chef d'orchestre",
      manual: "Réglé dans la carte Zendure",
      min: "min",
      max: "max",
      open: "Ouvrir la carte Zendure",
      missing: "Batteries Zendure introuvables ou intégration trop ancienne : pilotage impossible.",
    },
    plan: {
      title: "Plan pour demain",
      verdict: {
        charge: "Rentable",
        not_profitable: "Non rentable",
        suspended: "En pause",
        idle: "Pas de charge utile",
        nothing_to_cover: "Rien à couvrir",
        missing_data: "Données manquantes",
        no_solar: "Prévision solaire indisponible",
      },
      solar: "Solaire prévu",
      consumption: "Conso estimée",
      toCharge: "À charger en HC",
      gap: "Gain par kWh",
      fullRow: "Charge complète",
      full: { sun: "Aujourd'hui avec le soleil", tonight: "Cette nuit (calibration)", now: "En cours" },
      threshold: "seuil",
      slot: "Créneau de charge",
      minSoc: "SOC min appliqué",
      reserve: "réserve",
      fullCharge: "SOC max à 100 % (soleil)",
      detail: "Voir le détail du plan",
    },
    power: {
      title: "Puissance au tableau",
      of: "sur",
      margin: "Marge avant disjonction",
      noKva: "Puissance souscrite inconnue : alerte de disjonction indisponible.",
      noSensor: "Aucun capteur de puissance au tableau : ajoutez-le dans les réglages (Puissance).",
      running: "En marche",
      stopped: "Arrêté",
      unknown: "État inconnu",
      noLoads: "Aucun gros consommateur déclaré.",
      grid: "Réseau",
      nominal: "max",
    },
    info: {
      gain: "Économie nette sur chaque kWh acheté en heures creuses, stocké dans la batterie puis rendu à l'heure pleine la plus chère de demain, comparée à l'achat de ce kWh en heures pleines. Le prix payé la nuit et les pertes de la batterie sont déjà déduits. La batterie ne charge la nuit que si ce gain atteint le seuil de rentabilité, et seulement s'il manque de l'énergie pour couvrir les heures pleines.",
      minsoc: "SOC minimum que le Chef d'orchestre impose à chaque batterie pour la nuit. Quand la recharge n'est pas rentable, il passe à la réserve (50 % par défaut) pour ne pas dépenser en heures pleines une énergie qui ne rapporte presque rien. Sinon, c'est votre propre réglage de la batterie, rendu dès que le pilotage est coupé.",
      margin: "Puissance que la maison peut encore appeler avant d'atteindre la puissance souscrite de votre contrat. La jauge passe à l'orange puis au rouge quand on s'en approche (80 % et 95 % par défaut). La charge des batteries ralentit d'elle-même pour garder au moins 10 % de marge.",
      full: "D'après le support Zendure, les batteries peuvent lancer une calibration automatique après environ 30 jours sans charge à 100 %. Une charge complète une à deux fois par mois suffit en général à l'éviter : le Chef d'orchestre la programme un jour de soleil ou une nuit d'heures creuses bon marché. Aucune décharge complète n'est provoquée, elle userait la batterie.",
    },
    full: {
      days: (n) => `Charge complète il y a ${n} j`,
      unknown: "Charge complète : pas encore vue",
      calibrating: "Calibration en cours",
      title: "Charge complète",
      options: [
        ["auto", "Automatique", "Le Chef d'orchestre choisit un jour de soleil ou une nuit bon marché."],
        ["next_sun", "Au prochain jour de soleil", "100 % avec les panneaux, sans réseau."],
        ["tonight", "Cette nuit", "Charge à 100 % pendant les heures creuses."],
        ["now", "Maintenant", "Charge immédiate, même en heures pleines."],
        ["skip", "Ignorer pour ce cycle", "Plus de charge programmée ni d'alerte jusqu'à la prochaine charge complète."],
      ],
      confirmTitle: "Charger à 100 % maintenant ?",
      confirmText: (kwh, cost) => `Environ ${kwh} à acheter${cost ? `, soit ${cost} au prix actuel` : ""}.`,
      confirm: "Confirmer",
      cancel: "Annuler",
    },
    router: {
      title: "Routeur solaire",
      open: "Ouvrir la carte du routeur",
      displayNote: "Réglé dans la carte du routeur",
      states: {
        locked: "Verrouillé : batteries d'abord",
        routing: "Routage solaire",
        shed: "Délesté : les batteries le chauffaient",
        on_blocked: "Plage ON bloquée",
        boost: "Chauffe en heures creuses",
        hot: "Ballon chaud",
        offline: "Hors ligne",
        display_only: "Affichage seulement",
        autonomous: "En autonome",
      },
      usage: { water_heater: "Chauffe-eau", pool: "Piscine", heating: "Chauffage", other: "Autre" },
    },
    settings: "Réglages du Chef d'orchestre",
    close: "Fermer",
    notLoaded: "Cette carte n'est pas chargée : vérifiez que l'intégration correspondante est installée.",
    editor: {
      show_tariff: "Bloc Tarif en cours",
      show_batteries: "Bloc Batteries",
      show_router: "Bloc Routeur solaire",
      show_plan: "Bloc Plan pour demain",
      show_power: "Bloc Puissance au tableau",
      gauge_warn: "Jauge orange à partir de (%)",
      gauge_crit: "Jauge rouge à partir de (%)",
    },
  },
  en: {
    title: "Energy",
    subtitle: "Conductor",
    pilotOn: "Control on",
    pilotOff: "Control off",
    noChef: "Conductor not found: install and set up the Energy Conductor integration.",
    unavailable: "Unavailable",
    tariff: {
      title: "Current tariff",
      next: "Next change",
      at: "at",
      other: "Other period",
      open: "Open the Electricity Tariffs card",
      missing: "Electricity Tariffs missing or too old (1.1.0 minimum): profitability is not computed.",
      repairs: "See in Repairs",
      tempo: { bleu: "Blue day", blanc: "White day", rouge: "Red day" },
    },
    bat: {
      title: "Batteries",
      group: "Total",
      charging: "Charging",
      discharging: "Discharging",
      resting: "Idle",
      mode: "Mode",
      piloted: "Driven by the Conductor",
      manual: "Set in the Zendure card",
      min: "min",
      max: "max",
      open: "Open the Zendure card",
      missing: "Zendure batteries not found or integration too old: control is not possible.",
    },
    plan: {
      title: "Plan for tomorrow",
      verdict: {
        charge: "Profitable",
        not_profitable: "Not profitable",
        suspended: "Paused",
        idle: "No useful charge",
        nothing_to_cover: "Nothing to cover",
        missing_data: "Data missing",
        no_solar: "Solar forecast unavailable",
      },
      solar: "Expected solar",
      consumption: "Estimated use",
      toCharge: "To charge off-peak",
      gap: "Gain per kWh",
      fullRow: "Full charge",
      full: { sun: "Today with the sun", tonight: "Tonight (calibration)", now: "In progress" },
      threshold: "threshold",
      slot: "Charging slot",
      minSoc: "Applied min SOC",
      reserve: "reserve",
      fullCharge: "Max SOC at 100 % (sun)",
      detail: "See the plan in detail",
    },
    power: {
      title: "Panel power",
      of: "of",
      margin: "Margin before tripping",
      noKva: "Subscribed power unknown: tripping alert unavailable.",
      noSensor: "No panel power sensor: add it in the settings (Power).",
      running: "Running",
      stopped: "Stopped",
      unknown: "Unknown state",
      noLoads: "No large load declared.",
      grid: "Grid",
      nominal: "max",
    },
    info: {
      gain: "Net saving on each kWh bought off-peak, stored in the battery and given back at tomorrow's most expensive peak hour, compared with buying that kWh at peak price. The night price and battery losses are already deducted. The battery only charges at night if this gain reaches the profitability threshold, and only if energy is missing to cover the peak hours.",
      minsoc: "Minimum SOC the conductor sets on each battery for the night. When charging is not profitable it is raised to the reserve (50 % by default) so the battery does not spend at peak hours energy that earns almost nothing. Otherwise it is your own battery setting, given back as soon as control is turned off.",
      margin: "Power the home can still draw before reaching the subscribed power of your contract. The gauge turns orange then red as it gets close (80 % and 95 % by default). Battery charging slows down by itself to keep at least a 10 % margin.",
      full: "According to Zendure support, the batteries may start an automatic calibration after about 30 days without a 100 % charge. A full charge once or twice a month usually avoids it: the conductor schedules it on a sunny day or a cheap off-peak night. No full discharge is forced, as it would wear the battery.",
    },
    full: {
      days: (n) => `Full charge ${n} d ago`,
      unknown: "Full charge: not seen yet",
      calibrating: "Calibrating",
      title: "Full charge",
      options: [
        ["auto", "Automatic", "The conductor picks a sunny day or a cheap night."],
        ["next_sun", "Next sunny day", "100 % with the panels, no grid."],
        ["tonight", "Tonight", "Charge to 100 % during off-peak hours."],
        ["now", "Now", "Immediate charge, even at peak hours."],
        ["skip", "Skip this cycle", "No scheduled charge or alert until the next full charge."],
      ],
      confirmTitle: "Charge to 100 % now?",
      confirmText: (kwh, cost) => `About ${kwh} to buy${cost ? `, ${cost} at the current price` : ""}.`,
      confirm: "Confirm",
      cancel: "Cancel",
    },
    router: {
      title: "Solar router",
      open: "Open the router card",
      displayNote: "Set in the router card",
      states: {
        locked: "Locked: batteries first",
        routing: "Solar routing",
        shed: "Shed: batteries were heating it",
        on_blocked: "ON slot blocked",
        boost: "Heating off-peak",
        hot: "Tank hot",
        offline: "Offline",
        display_only: "Display only",
        autonomous: "Autonomous",
      },
      usage: { water_heater: "Water heater", pool: "Pool", heating: "Heating", other: "Other" },
    },
    settings: "Conductor settings",
    close: "Close",
    notLoaded: "This card is not loaded: check that the matching integration is installed.",
    editor: {
      show_tariff: "Current tariff block",
      show_batteries: "Batteries block",
      show_router: "Solar router block",
      show_plan: "Plan for tomorrow block",
      show_power: "Panel power block",
      gauge_warn: "Gauge orange from (%)",
      gauge_crit: "Gauge red from (%)",
    },
  },
};

const eEsc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const eNum = (v) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
};
const BAD = new Set(["unavailable", "unknown", "none", ""]);

class ChefOrchestreEnergieCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("chef-orchestre-energie-card-editor");
  }
  static getStubConfig() {
    return { show_tariff: true, show_batteries: true, show_router: true, show_plan: true, show_power: true };
  }
  setConfig(config) {
    this._config = { ...(config || {}) };
    this._sig = null;
    if (this._hass) this._render();
  }
  set hass(hass) {
    this._hass = hass;
    if (this._popCard) this._popCard.hass = hass;
    const sig = this._signature();
    if (sig !== this._sig) this._render();
  }
  getCardSize() {
    return 2 + BLOCKS.filter((b) => this._config?.[b]).length * 3;
  }
  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  /* ---------------------------------------------------------------- langue et formats */
  get _lang() {
    return (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
  }
  get _t() {
    return ENERGY_I18N[this._lang] || ENERGY_I18N.en;
  }
  get _locale() {
    return this._hass?.locale?.language || this._lang;
  }
  _n(v, digits = 1) {
    const n = eNum(v);
    if (n === null) return null;
    return new Intl.NumberFormat(this._locale, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
  }
  _price(v) {
    const s = this._n(v, 4);
    return s === null ? this._t.unavailable : `${s} €/kWh`;
  }
  _kwh(v) {
    const s = this._n(v, 1);
    return s === null ? "—" : `${s} kWh`;
  }
  _w(v) {
    const n = eNum(v);
    if (n === null) return this._t.unavailable;
    if (Math.abs(n) >= 1000) return `${this._n(n / 1000, 2)} kW`;
    return `${this._n(n, 0)} W`;
  }
  _time(v) {
    if (!v || BAD.has(String(v))) return null;
    const d = new Date(v);
    if (isNaN(d)) return null;
    return d.toLocaleTimeString(this._locale, { hour: "2-digit", minute: "2-digit" });
  }

  /* ---------------------------------------------------------------- entités */
  _entities() {
    const out = { chef: {}, tariff: {}, zendure: {} };
    const all = Object.values(this._hass.entities || {});
    for (const e of all) {
      if (e.platform === CHEF && e.translation_key && !(e.translation_key in out.chef)) out.chef[e.translation_key] = e.entity_id;
    }
    return { all, ...out };
  }
  _state(id) {
    return id ? this._hass.states[id] : undefined;
  }
  /* toutes les entités du Chef d'orchestre d'une clé (une par batterie ou par routeur) */
  _chefByKey(all, key) {
    return all.filter((e) => e.platform === CHEF && e.translation_key === key).map((e) => e.entity_id);
  }
  _chefForDevice(all, key, deviceId) {
    return this._chefByKey(all, key).find((id) => this._state(id)?.attributes?.device_id === deviceId);
  }
  _ok(st) {
    return st && !BAD.has(String(st.state));
  }
  _byDevice(all, deviceId, platform) {
    const map = {};
    for (const e of all) {
      if (e.device_id === deviceId && e.platform === platform && e.translation_key && !(e.translation_key in map)) {
        map[e.translation_key] = e.entity_id;
      }
    }
    return map;
  }
  _deviceName(id) {
    const d = this._hass.devices?.[id];
    return d?.name_by_user || d?.name || id;
  }
  _signature() {
    if (!this._hass) return null;
    const ids = this._watched || [];
    return [this._lang, ...ids.map((id) => this._hass.states[id]?.last_updated + "|" + this._hass.states[id]?.state)].join(";");
  }

  /* ---------------------------------------------------------------- rendu */
  _render() {
    if (!this._hass || !this._config) return;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.innerHTML = `<style>${ENERGY_STYLE}</style><ha-card><div id="main"></div></ha-card><div id="pop"></div>`;
      this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    }
    const t = this._t;
    const ents = this._entities();
    const watched = [];
    const main = this.shadowRoot.getElementById("main");
    if (!ents.chef.night_plan) {
      main.innerHTML = `<div class="msg warn"><ha-icon icon="mdi:alert-outline"></ha-icon><span>${eEsc(t.noChef)}</span></div>`;
      this._watched = [];
      this._sig = this._signature();
      return;
    }
    const sw = this._state(ents.chef.auto_control);
    const plan = this._state(ents.chef.night_plan);
    watched.push(ents.chef.auto_control, ents.chef.night_plan);
    const pa = plan?.attributes || {};
    const on = sw?.state === "on";
    const batteryOk = pa.battery_ok !== false;
    const ctx = { ents, sw, plan, pa, on, batteryOk, watched };
    const c = this._config;
    main.innerHTML = [
      this._header(ctx),
      c.show_tariff ? this._tariff(ctx) : "",
      c.show_batteries ? this._batteries(ctx) : "",
      c.show_router ? this._router(ctx) : "",
      c.show_plan ? this._plan(ctx) : "",
      c.show_power ? this._power(ctx) : "",
      this._footer(),
    ].join("");
    this._watched = watched.filter(Boolean);
    this._sig = this._signature();
  }

  _header({ sw, on, batteryOk }) {
    const t = this._t;
    const disabled = !sw || !batteryOk;
    return `<div class="head">
      <div class="titles"><div class="title">${eEsc(this._config.name || t.title)}</div><div class="sub">${eEsc(t.subtitle)}</div></div>
      <button class="pilot ${on ? "on" : "off"}" data-act="toggle" ${disabled ? "disabled" : ""} role="switch" aria-checked="${on}">
        <span class="knob"></span><span>${eEsc(on ? t.pilotOn : t.pilotOff)}</span>
      </button>
    </div>`;
  }

  _section(icon, title, body, action, toggle) {
    return `<section><div class="sh"><ha-icon icon="${icon}"></ha-icon><span class="grow">${eEsc(title)}</span>${toggle || ""}</div>${body}${action || ""}</section>`;
  }
  _info(key) {
    return `<button class="ibtn ${this._openInfo === key ? "open" : ""}" data-act="info" data-key="${eEsc(key)}" aria-label="Information" aria-expanded="${this._openInfo === key}">i</button>`;
  }
  _bubble(key, text, cls = "") {
    return this._openInfo === key ? `<div class="bubble ${cls}">${eEsc(text)}</div>` : "";
  }
  _mini(act, on, disabled, key = "", label = "") {
    return `<button class="mini ${on ? "on" : ""}" data-act="${act}" data-key="${eEsc(key)}" role="switch" aria-checked="${on}" aria-label="${eEsc(label)}" ${disabled ? "disabled" : ""}><span class="knob"></span></button>`;
  }
  _action(act, icon, label) {
    return `<button class="act" data-act="${act}"><ha-icon icon="${icon}"></ha-icon><span>${eEsc(label)}</span><ha-icon class="chev" icon="mdi:chevron-right"></ha-icon></button>`;
  }
  _warn(text, act, label) {
    const link = act ? `<button class="link" data-act="${act}">${eEsc(label)}</button>` : "";
    return `<div class="msg warn"><ha-icon icon="mdi:alert-outline"></ha-icon><span>${eEsc(text)} ${link}</span></div>`;
  }

  /* ---- Tarif en cours (ha-tarifs-electricite, entité prix_actuel) */
  _tariff({ pa, watched }) {
    const t = this._t.tariff;
    const st = this._state(pa.tariff_entity);
    watched.push(pa.tariff_entity);
    if (pa.tariff_ok === false || !st) {
      return this._section("mdi:cash-clock", t.title, this._warn(t.missing, "repairs", t.repairs));
    }
    const a = st.attributes || {};
    const period = a.periode_libelle || (a.periode ? String(a.periode).toUpperCase() : this._t.unavailable);
    const tempo = a.couleur_tempo ? t.tempo[String(a.couleur_tempo).toLowerCase()] || a.couleur_tempo : null;
    const cls = a.heures_creuses ? "hc" : "hp";
    const next = this._time(a.prochain_changement);
    const nextTxt = next ? `${a.prochaine_periode_libelle || ""} ${t.at} ${next}`.trim() : "—";
    const body = `<div class="tariff">
        <span class="chip ${cls}${a.couleur_tempo ? " tempo-" + eEsc(String(a.couleur_tempo).toLowerCase()) : ""}">${eEsc(period)}</span>
        ${tempo ? `<span class="chip ghost">${eEsc(tempo)}</span>` : ""}
        <span class="big">${eEsc(this._ok(st) ? this._price(st.state) : this._t.unavailable)}</span>
      </div>
      <div class="rows">
        <div class="row"><span>${eEsc(t.next)}</span><b>${eEsc(nextTxt)}</b></div>
        <div class="row"><span>${eEsc(t.other)}</span><b>${eEsc(a.prochain_prix != null ? this._price(a.prochain_prix) : "—")}</b></div>
      </div>`;
    return this._section("mdi:cash-clock", t.title, body, this._action("tariff", "mdi:open-in-new", t.open));
  }

  /* ---- Batteries (ha-zendure-solarflow-local) */
  _devices({ sw, ents }) {
    const a = sw?.attributes || {};
    let ids = Array.isArray(a.controlled_device_ids) ? [...a.controlled_device_ids] : [];
    if (!ids.length) {
      // Ancien Chef d'orchestre ou interrupteur absent : toutes les batteries Zendure
      ids = [...new Set(ents.all.filter((e) => e.platform === ZENDURE && e.translation_key === "operating_mode").map((e) => e.device_id))];
    }
    return { main: a.controlled_device_id || ids[0], ids };
  }
  _ring(soc) {
    const r = 30;
    const c = 2 * Math.PI * r;
    const v = soc === null ? 0 : Math.max(0, Math.min(100, soc));
    const color = v < 20 ? "var(--error-color, #db4437)" : v < 50 ? "var(--warning-color, #ffa000)" : "var(--success-color, #43a047)";
    return `<svg class="ring" viewBox="0 0 72 72" aria-hidden="true">
      <circle cx="36" cy="36" r="${r}" class="track"/>
      <circle cx="36" cy="36" r="${r}" stroke="${color}" stroke-dasharray="${(c * v) / 100} ${c}" transform="rotate(-90 36 36)" class="val"/>
      <text x="36" y="41" text-anchor="middle">${soc === null ? "—" : Math.round(v) + " %"}</text></svg>`;
  }
  _flow(p) {
    const t = this._t.bat;
    const n = eNum(p);
    if (n === null) return this._t.unavailable;
    if (Math.abs(n) < 5) return t.resting;
    return `${n > 0 ? t.charging : t.discharging} ${this._w(Math.abs(n))}`;
  }
  _batteries(ctx) {
    const t = this._t.bat;
    const { on, batteryOk, watched, ents, pa } = ctx;
    const batSw = this._state(ents.chef.battery_control);
    watched.push(ents.chef.battery_control);
    const batOn = batSw ? batSw.state === "on" : true;
    const piloted = on && batOn;
    const toggle = batSw ? this._mini("bat_toggle", piloted, !on, "", t.title) : "";
    if (!batteryOk) return this._section("mdi:home-battery", t.title, this._warn(t.missing));
    const { main, ids } = this._devices(ctx);
    if (!main) return this._section("mdi:home-battery", t.title, this._warn(t.missing));
    const m = this._byDevice(ents.all, main, ZENDURE);
    const soc = this._state(m.electric_level);
    const pw = this._state(m.battery_power);
    const mode = this._state(m.operating_mode);
    watched.push(m.electric_level, m.battery_power, m.operating_mode);
    const modeTxt = !this._ok(mode)
      ? this._t.unavailable
      : this._hass.formatEntityState
        ? this._hass.formatEntityState(mode)
        : mode.state;
    const units = ids.filter((id) => id !== main);
    const rows = (units.length ? units : []).map((id) => {
      const u = this._byDevice(ents.all, id, ZENDURE);
      watched.push(u.electric_level, u.battery_power, u.min_soc, u.soc_set);
      const s = this._state(u.electric_level);
      const p = this._state(u.battery_power);
      const lo = this._state(u.min_soc);
      const hi = this._state(u.soc_set);
      const pct = (st) => (this._ok(st) ? `${this._n(st.state, 0)} %` : "—");
      const fullId = this._chefForDevice(ents.all, "full_charge_days", id);
      watched.push(fullId);
      const full = this._state(fullId);
      let fullLine = "";
      if (full) {
        const ft = this._t.full;
        const days = this._ok(full) ? Math.floor(eNum(full.state)) : null;
        const thr = eNum(full.attributes.threshold_days) ?? 20;
        const label = full.attributes.calibrating ? ft.calibrating : days === null ? ft.unknown : ft.days(days);
        const late = full.attributes.calibrating || (days !== null && days >= thr);
        fullLine = `<span class="ufull"><button class="fulllink ${late ? "late" : ""}" data-act="fullmenu">${eEsc(label)}<ha-icon icon="mdi:chevron-down"></ha-icon></button>${this._info("full_" + id)}</span>${this._bubble("full_" + id, this._t.info.full, "span2")}`;
      }
      return `<div class="unit">
        <span class="uname">${eEsc(this._deviceName(id))}</span>
        <span class="usoc">${this._ok(s) ? this._n(s.state, 0) + " %" : eEsc(this._t.unavailable)}</span>
        <span class="upow">${eEsc(this._ok(p) ? this._flow(p.state) : this._t.unavailable)}</span>
        <span class="ulim">${eEsc(t.min)} ${pct(lo)} · ${eEsc(t.max)} ${pct(hi)}</span>
        ${fullLine}
      </div>`;
    });
    const body = `<div class="bat">
        ${this._ring(this._ok(soc) ? eNum(soc.state) : null)}
        <div class="rows">
          <div class="row"><span>${eEsc(units.length ? t.group : this._deviceName(main))}</span><b>${eEsc(this._ok(pw) ? this._flow(pw.state) : this._t.unavailable)}</b></div>
          <div class="row"><span>${eEsc(t.mode)}</span><b>${eEsc(modeTxt)}</b></div>
          <div class="note ${piloted ? "piloted" : ""}"><ha-icon icon="${piloted ? "mdi:robot-outline" : "mdi:hand-back-right-outline"}"></ha-icon>${eEsc(piloted ? t.piloted : t.manual)}</div>
        </div>
      </div>
      ${rows.length ? `<div class="units">${rows.join("")}</div>` : ""}`;
    return this._section("mdi:home-battery", t.title, body, this._action("zendure", "mdi:open-in-new", t.open), toggle);
  }

  /* ---- Routeurs solaires F1ATB (N5, N6) */
  _router({ pa, on, ents, watched }) {
    const r = this._t.router;
    const list = Array.isArray(pa.routers) ? pa.routers : [];
    if (!list.length) return "";
    const lines = list.map((x) => {
      const swId = this._chefForDevice(ents.all, "router_control", x.device_id);
      watched.push(swId);
      const sw = this._state(swId);
      const switchOn = sw ? sw.state === "on" : x.switch_on;
      const display = x.state === "display_only";
      const tone = { routing: "good", hot: "good", locked: "blue", boost: "warn", shed: "warn", on_blocked: "blue" }[x.state] || "muted";
      const state = r.states[x.state] || x.state;
      const disabled = !on || !x.online || display || !swId;
      return `<div class="rline ${x.online ? "" : "offline"}">
        <div class="rhead"><span class="rname">${eEsc(x.name)}</span><span class="muted small">${eEsc(r.usage[x.usage] || x.usage || "")}</span><span class="grow"></span>${this._mini("router_toggle", on && switchOn && !display, disabled, swId || "", x.name)}</div>
        <div class="rbody">
          ${x.temperature != null ? `<span class="rtemp">${this._n(x.temperature, 0)} °C</span>` : ""}
          <span class="rpow">${x.online && x.routed_power != null ? eEsc(this._w(x.routed_power)) : "—"}</span>
          <span class="chip small ${tone}">${eEsc(state)}</span>
          <button class="icon open" data-act="routercard" data-key="${eEsc(x.device_id)}" aria-label="${eEsc(r.open)}"><ha-icon icon="mdi:open-in-new"></ha-icon></button>
        </div>
        ${display ? `<div class="note">${eEsc(r.displayNote)}</div>` : ""}
      </div>`;
    });
    return this._section("mdi:water-boiler", r.title, `<div class="routers">${lines.join("")}</div>`);
  }

  /* ---- Plan pour demain (Chef d'orchestre) */
  _plan({ plan, pa, on, ents, watched }) {
    const t = this._t.plan;
    const keys = ["energy_to_charge", "forecast_solar", "forecast_consumption", "charge_start"];
    keys.forEach((k) => watched.push(ents.chef[k]));
    const val = (k) => this._state(ents.chef[k]);
    let verdict = plan?.state;
    if (!on) verdict = "suspended";
    else if (verdict === "missing_data" && (pa.missing || []).includes("solar_forecast")) verdict = "no_solar";
    const label = t.verdict[verdict] || plan?.state || this._t.unavailable;
    const tone = { charge: "good", not_profitable: "bad", suspended: "muted", missing_data: "bad", no_solar: "bad" }[verdict] || "info";
    const paused = !on;
    const start = this._time(val("charge_start")?.state);
    const end = this._time(pa.charge_end);
    const slot = paused || plan?.state !== "charge" || !start ? "—" : end ? `${start} – ${end}` : start;
    const gap = eNum(pa.price_gap);
    const thr = eNum(pa.gain_threshold);
    const gapTxt = gap === null || pa.tariff_ok === false ? "—" : `${this._n(gap, 3)} €/kWh${thr !== null ? ` (${t.threshold} ${this._n(thr, 3)})` : ""}`;
    const minSoc = eNum(pa.applied_min_soc);
    const minTxt = minSoc === null ? "—" : `${this._n(minSoc, 0)} %${pa.reserve_soc != null ? ` (${t.reserve})` : ""}`;
    const rows = [
      [t.solar, this._kwh(val("forecast_solar")?.state)],
      [t.consumption, this._kwh(val("forecast_consumption")?.state)],
      [t.toCharge, paused ? "—" : this._kwh(val("energy_to_charge")?.state)],
      [t.gap, gapTxt, gap !== null && thr !== null && pa.tariff_ok !== false ? (gap >= thr ? "good" : "bad") : "", "gain"],
      [t.slot, slot],
      [t.minSoc, minTxt, "", "minsoc"],
      ...(pa.full_charge_planned && on && t.full[pa.full_charge_planned] ? [[t.fullRow, t.full[pa.full_charge_planned], "warn"]] : []),
    ];
    const body = `<div class="verdict ${tone}">${eEsc(label)}</div>
      <div class="rows">${rows
        .map(([k, v, cls, info]) => `<div class="row"><span class="lab">${eEsc(k)}${info ? this._info(info) : ""}</span><b class="${cls || ""}">${eEsc(v)}</b></div>${info ? this._bubble(info, this._t.info[info]) : ""}`)
        .join("")}
      ${pa.full_charge && on ? `<div class="note piloted"><ha-icon icon="mdi:white-balance-sunny"></ha-icon>${eEsc(t.fullCharge)}</div>` : ""}
      </div>`;
    return this._section("mdi:calendar-clock", t.title, body, this._action("detail", "mdi:chart-timeline-variant", t.detail));
  }

  /* ---- Puissance au tableau */
  _power({ ents, watched }) {
    const t = this._t.power;
    const st = this._state(ents.chef.board_power);
    watched.push(ents.chef.board_power);
    const a = st?.attributes || {};
    const kva = eNum(a.subscribed_kva);
    const warn = eNum(this._config.gauge_warn) ?? eNum(a.gauge_warn) ?? 80;
    const crit = eNum(this._config.gauge_crit) ?? eNum(a.gauge_crit) ?? 95;
    const p = this._ok(st) ? eNum(st.state) : null;
    const parts = [];
    if (!a.power_entity) {
      parts.push(this._warn(t.noSensor));
    } else {
      const pct = p !== null && kva ? (p / (kva * 1000)) * 100 : null;
      const level = pct === null ? "" : pct >= crit ? "crit" : pct >= warn ? "warn" : "ok";
      const kvaTxt = kva ? `${this._n(kva, 0)} kVA` : "? kVA";
      parts.push(`<div class="gauge-head"><span class="big">${eEsc(p === null ? this._t.unavailable : this._w(p))}</span>
          <span class="muted">${eEsc(t.of)} ${eEsc(kvaTxt)}</span></div>
        <div class="gauge ${level}" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct === null ? 0 : Math.round(pct)}">
          <div class="fill" style="width:${pct === null ? 0 : Math.min(100, pct).toFixed(1)}%"></div>
          <div class="tick" style="left:${warn}%"></div><div class="tick" style="left:${crit}%"></div>
        </div>`);
      if (!kva) parts.push(this._warn(t.noKva));
      else if (a.margin_w != null) parts.push(`<div class="rows"><div class="row"><span class="lab">${eEsc(t.margin)}${this._info("margin")}</span><b class="${level === "ok" ? "" : level}">${eEsc(this._w(a.margin_w))}</b></div>${this._bubble("margin", this._t.info.margin)}</div>`);
    }
    const loads = Array.isArray(a.loads) ? a.loads : [];
    if (loads.length) {
      parts.push(
        `<div class="loads">${loads
          .map((l) => {
            const state = l.running === true ? t.running : l.running === false ? t.stopped : t.unknown;
            const measured = l.current_w != null;
            const pw = this._w(measured ? l.current_w : l.power_w);
            return `<div class="load ${l.running ? "run" : ""}"><span class="dot"></span><span class="lname">${eEsc(l.name)}${l.battery === false ? `<span class="chip small ghost">${eEsc(t.grid)}</span>` : ""}</span><span class="muted">${eEsc(state)}</span><b class="${measured ? "" : "nominal"}">${eEsc(measured ? pw : `${t.nominal} ${pw}`)}</b></div>`;
          })
          .join("")}</div>`
      );
    } else {
      parts.push(`<div class="muted small">${eEsc(t.noLoads)}</div>`);
    }
    return this._section("mdi:flash", t.title, parts.join(""));
  }

  _footer() {
    return `<div class="foot">${this._action("settings", "mdi:cog-outline", this._t.settings)}</div>`;
  }

  /* ---------------------------------------------------------------- actions */
  _navigate(path) {
    history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }
  _onClick(ev) {
    const btn = ev.composedPath().find((n) => n.dataset?.act);
    if (!btn || btn.disabled) return;
    const act = btn.dataset.act;
    const ents = this._entities();
    const plan = this._state(ents.chef.night_plan);
    const sw = this._state(ents.chef.auto_control);
    if (act === "toggle" && sw) {
      this._hass.callService("switch", sw.state === "on" ? "turn_off" : "turn_on", { entity_id: sw.entity_id });
    } else if (act === "repairs") {
      this._navigate("/config/repairs");
    } else if (act === "settings") {
      this._navigate(`/config/integrations/integration/${CHEF}`);
    } else if (act === "tariff") {
      this._open("tarifs-electricite-card", { type: "custom:tarifs-electricite-card", entity: plan?.attributes?.tariff_entity, afficher_frise: true, afficher_tempo: true, afficher_grille: true }, this._t.tariff.title);
    } else if (act === "zendure") {
      const { main } = this._devices({ sw, ents });
      this._open("zendure-solarflow-card", { type: "custom:zendure-solarflow-card", device_id: main, show_history: true, show_flow: true }, this._t.bat.title);
    } else if (act === "detail") {
      this._open("chef-orchestre-card", { type: "custom:chef-orchestre-card", show_chart: true, show_modes: true, show_settings: true }, this._t.plan.title);
    } else if (act === "close") {
      this._close();
    } else if (act === "info") {
      this._openInfo = this._openInfo === btn.dataset.key ? null : btn.dataset.key;
      this._render();
    } else if (act === "bat_toggle" && ents.chef.battery_control) {
      const st = this._state(ents.chef.battery_control);
      this._hass.callService("switch", st?.state === "on" ? "turn_off" : "turn_on", { entity_id: ents.chef.battery_control });
    } else if (act === "router_toggle" && btn.dataset.key) {
      const st = this._state(btn.dataset.key);
      this._hass.callService("switch", st?.state === "on" ? "turn_off" : "turn_on", { entity_id: btn.dataset.key });
    } else if (act === "routercard") {
      this._open("f1atb-routeur-card", { type: "custom:f1atb-routeur-card", device_id: btn.dataset.key }, this._t.router.title);
    } else if (act === "fullmenu") {
      this._menu(ents);
    } else if (act === "pick") {
      if (btn.dataset.key === "now") this._confirmNow(ents, plan);
      else this._pick(ents, btn.dataset.key);
    } else if (act === "confirm_now") {
      this._pick(ents, "now");
    }
  }
  _open(tag, config, title) {
    const pop = this.shadowRoot.getElementById("pop");
    pop.innerHTML = `<div class="overlay" data-act="close"></div>
      <div class="dialog" role="dialog" aria-modal="true" aria-label="${eEsc(title)}">
        <div class="dh"><span>${eEsc(title)}</span><button class="icon" data-act="close" aria-label="${eEsc(this._t.close)}"><ha-icon icon="mdi:close"></ha-icon></button></div>
        <div class="dbody"></div></div>`;
    const body = pop.querySelector(".dbody");
    this._popCard = null;
    if (customElements.get(tag)) {
      try {
        const el = document.createElement(tag);
        el.setConfig(config);
        el.hass = this._hass;
        body.appendChild(el);
        this._popCard = el;
      } catch (e) {
        body.innerHTML = `<div class="msg warn"><ha-icon icon="mdi:alert-outline"></ha-icon><span>${eEsc(e?.message || this._t.notLoaded)}</span></div>`;
      }
    } else {
      body.innerHTML = `<div class="msg warn"><ha-icon icon="mdi:alert-outline"></ha-icon><span>${eEsc(this._t.notLoaded)}</span></div>`;
    }
    this._onKey = (e) => e.key === "Escape" && this._close();
    window.addEventListener("keydown", this._onKey);
    pop.querySelector(".dialog button")?.focus();
  }
  _pick(ents, option) {
    if (ents.chef.full_charge) this._hass.callService("select", "select_option", { entity_id: ents.chef.full_charge, option });
    this._close();
  }
  _menu(ents) {
    const pop = this.shadowRoot.getElementById("pop");
    const f = this._t.full;
    const current = this._state(ents.chef.full_charge)?.state || "auto";
    pop.innerHTML = `<div class="overlay" data-act="close"></div>
      <div class="dialog sheet" role="dialog" aria-modal="true" aria-label="${eEsc(f.title)}">
        <div class="dh"><span>${eEsc(f.title)}</span><button class="icon" data-act="close" aria-label="${eEsc(this._t.close)}"><ha-icon icon="mdi:close"></ha-icon></button></div>
        <div class="dbody opts" role="radiogroup">${f.options
          .map(([k, label, desc]) => `<button class="opt ${k === current ? "sel" : ""}" role="radio" aria-checked="${k === current}" data-act="pick" data-key="${k}"><span class="radio"></span><span><b>${eEsc(label)}</b><span class="muted small">${eEsc(desc)}</span></span></button>`)
          .join("")}</div>
      </div>`;
    this._onKey = (e) => e.key === "Escape" && this._close();
    window.addEventListener("keydown", this._onKey);
  }
  _confirmNow(ents, plan) {
    const pop = this.shadowRoot.getElementById("pop");
    const f = this._t.full;
    const a = plan?.attributes || {};
    const kwh = a.full_charge_now_kwh != null ? this._kwh(a.full_charge_now_kwh) : "—";
    const cost = a.full_charge_now_cost != null ? `${this._n(a.full_charge_now_cost, 2)} €` : null;
    pop.querySelector(".dbody").innerHTML = `<div class="confirm"><b>${eEsc(f.confirmTitle)}</b><p class="muted">${eEsc(f.confirmText(kwh, cost))}</p>
      <div class="btns"><button class="act ghostbtn" data-act="close">${eEsc(f.cancel)}</button><button class="act" data-act="confirm_now">${eEsc(f.confirm)}</button></div></div>`;
  }
  _close() {
    const pop = this.shadowRoot?.getElementById("pop");
    if (pop) pop.innerHTML = "";
    this._popCard = null;
    if (this._onKey) window.removeEventListener("keydown", this._onKey);
  }
  disconnectedCallback() {
    this._close();
  }
}

const ENERGY_STYLE = `
:host{display:block}
ha-card{display:block;padding:16px;overflow:hidden}
.head{display:flex;align-items:center;justify-content:space-between;gap:12px}
.title{font-size:1.35rem;font-weight:500;color:var(--primary-text-color)}
.sub,.muted{color:var(--secondary-text-color)}
.small{font-size:.85rem}
button{font:inherit;color:inherit;background:none;border:0;cursor:pointer;-webkit-tap-highlight-color:transparent}
button:disabled{cursor:not-allowed;opacity:.5}
button:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
.pilot{display:flex;align-items:center;gap:10px;min-height:44px;padding:0 14px 0 8px;border-radius:22px;
  background:color-mix(in srgb,var(--secondary-text-color) 14%,transparent);font-weight:500}
.pilot .knob{width:36px;height:20px;border-radius:10px;background:var(--disabled-color,#9e9e9e);position:relative;flex:none;transition:background .2s}
.pilot .knob::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:#fff;transition:left .2s}
.pilot.on{background:color-mix(in srgb,var(--primary-color) 16%,transparent);color:var(--primary-color)}
.pilot.on .knob{background:var(--primary-color)}
.pilot.on .knob::after{left:18px}
.pilot.off{color:var(--secondary-text-color)}
section{margin-top:16px;padding-top:14px;border-top:1px solid var(--divider-color,rgba(127,127,127,.2))}
.sh{display:flex;align-items:center;gap:8px;font-weight:500;margin-bottom:10px;color:var(--primary-text-color)}
.sh ha-icon{--mdc-icon-size:20px;color:var(--state-icon-color,var(--primary-color))}
.rows{display:flex;flex-direction:column;gap:6px;flex:1;min-width:0}
.row{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.row span{color:var(--secondary-text-color)}
.row b{font-weight:500;text-align:right}
b.good{color:var(--success-color,#43a047)} b.bad,b.crit{color:var(--error-color,#db4437)} b.warn{color:var(--warning-color,#ffa000)}
.big{font-size:1.5rem;font-weight:500}
.tariff{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:10px}
.tariff .big{margin-left:auto}
.chip{display:inline-flex;align-items:center;min-height:28px;padding:0 10px;border-radius:14px;font-weight:500;font-size:.9rem}
.chip.hp{background:color-mix(in srgb,var(--warning-color,#ffa000) 22%,transparent)}
.chip.hc{background:color-mix(in srgb,var(--success-color,#43a047) 22%,transparent)}
.chip.ghost{border:1px solid var(--divider-color,rgba(127,127,127,.35))}
.chip.tempo-bleu{background:color-mix(in srgb,#1e88e5 26%,transparent)}
.chip.tempo-blanc{background:color-mix(in srgb,var(--secondary-text-color) 18%,transparent)}
.chip.tempo-rouge{background:color-mix(in srgb,#e53935 28%,transparent)}
.bat{display:flex;gap:14px;align-items:center}
.ring{width:84px;height:84px;flex:none}
.ring circle{fill:none;stroke-width:8;stroke-linecap:round}
.ring .track{stroke:color-mix(in srgb,var(--secondary-text-color) 20%,transparent)}
.ring text{fill:var(--primary-text-color);font-size:15px;font-weight:500}
.note{display:flex;align-items:center;gap:6px;font-size:.88rem;color:var(--secondary-text-color)}
.note ha-icon{--mdc-icon-size:18px}
.note.piloted{color:var(--primary-color)}
.units{margin-top:10px;display:flex;flex-direction:column;gap:6px}
.unit{display:grid;grid-template-columns:1fr auto;gap:2px 12px;padding:8px 10px;border-radius:10px;
  background:color-mix(in srgb,var(--secondary-text-color) 8%,transparent)}
.uname{font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.usoc{font-weight:500;text-align:right}
.upow,.ulim{font-size:.85rem;color:var(--secondary-text-color)}
.ulim{text-align:right}
.verdict{display:inline-flex;align-items:center;min-height:30px;padding:0 12px;border-radius:15px;font-weight:500;margin-bottom:10px}
.verdict.good{background:color-mix(in srgb,var(--success-color,#43a047) 20%,transparent);color:var(--success-color,#43a047)}
.verdict.bad{background:color-mix(in srgb,var(--error-color,#db4437) 18%,transparent);color:var(--error-color,#db4437)}
.verdict.muted{background:color-mix(in srgb,var(--secondary-text-color) 16%,transparent);color:var(--secondary-text-color)}
.verdict.info{background:color-mix(in srgb,var(--primary-color) 16%,transparent);color:var(--primary-color)}
.gauge-head{display:flex;align-items:baseline;gap:8px;margin-bottom:8px}
.gauge{position:relative;height:14px;border-radius:7px;background:color-mix(in srgb,var(--secondary-text-color) 18%,transparent);overflow:hidden;margin-bottom:10px}
.gauge .fill{height:100%;border-radius:7px;background:var(--success-color,#43a047);transition:width .4s}
.gauge.warn .fill{background:var(--warning-color,#ffa000)}
.gauge.crit .fill{background:var(--error-color,#db4437)}
.gauge .tick{position:absolute;top:0;bottom:0;width:2px;background:var(--card-background-color,#fff);opacity:.8}
.loads{display:flex;flex-direction:column;gap:4px;margin-top:8px}
.load{display:grid;grid-template-columns:auto 1fr auto auto;align-items:center;gap:10px;min-height:32px}
.load .dot{width:10px;height:10px;border-radius:50%;background:var(--disabled-color,#9e9e9e)}
.load.run .dot{background:var(--warning-color,#ffa000)}
b.nominal{font-weight:400;color:var(--secondary-text-color)}
.lname{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.msg{display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border-radius:10px;font-size:.92rem;line-height:1.4}
.msg ha-icon{flex:none;--mdc-icon-size:20px}
.msg.warn{background:color-mix(in srgb,var(--warning-color,#ffa000) 14%,transparent)}
.msg.warn ha-icon{color:var(--warning-color,#ffa000)}
.link{color:var(--primary-color);text-decoration:underline;padding:0;min-height:0;font-weight:500}
.act{display:flex;align-items:center;gap:10px;width:100%;min-height:44px;margin-top:10px;padding:0 12px;border-radius:10px;
  background:color-mix(in srgb,var(--primary-color) 10%,transparent);color:var(--primary-color);font-weight:500;text-align:left}
.act span{flex:1}
.act ha-icon{--mdc-icon-size:20px}
.foot{margin-top:16px}
.grow{flex:1}
.lab{display:inline-flex;align-items:center;gap:6px}
.ibtn{position:relative;width:20px;height:20px;border-radius:50%;border:1.5px solid currentColor;font:600 12px/1 Georgia,serif;font-style:italic;
  color:var(--secondary-text-color);display:inline-flex;align-items:center;justify-content:center;padding:0;flex:none}
.ibtn::after{content:"";position:absolute;inset:-12px}
.ibtn.open{color:var(--primary-color);background:color-mix(in srgb,var(--primary-color) 14%,transparent)}
.bubble{margin:2px 0 6px;padding:10px 12px;border-radius:10px;font-size:.86rem;line-height:1.45;
  background:color-mix(in srgb,var(--primary-color) 10%,transparent);color:var(--primary-text-color)}
.bubble.span2{grid-column:1/-1}
.mini{position:relative;width:44px;height:26px;border-radius:13px;background:var(--disabled-color,#9e9e9e);padding:0;flex:none;transition:background .2s}
.mini .knob{position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:left .2s}
.mini.on{background:var(--primary-color)}
.mini.on .knob{left:21px}
.mini::after{content:"";position:absolute;inset:-9px 0}
.ufull{grid-column:1/-1;display:flex;align-items:center;gap:8px;margin-top:2px}
.fulllink{display:inline-flex;align-items:center;gap:2px;font-size:.85rem;color:var(--secondary-text-color);padding:6px 0;min-height:32px}
.fulllink ha-icon{--mdc-icon-size:16px}
.fulllink.late{color:var(--warning-color,#ffa000);font-weight:500}
b.warn{color:var(--warning-color,#ffa000)}
.chip.small{min-height:22px;padding:0 8px;font-size:.78rem;border-radius:11px}
.lname .chip.small{margin-left:6px}
.chip.good{background:color-mix(in srgb,var(--success-color,#43a047) 20%,transparent);color:var(--success-color,#43a047)}
.chip.blue{background:color-mix(in srgb,var(--primary-color) 16%,transparent);color:var(--primary-color)}
.chip.warn{background:color-mix(in srgb,var(--warning-color,#ffa000) 18%,transparent);color:var(--warning-color,#ffa000)}
.chip.muted{background:color-mix(in srgb,var(--secondary-text-color) 16%,transparent);color:var(--secondary-text-color)}
.routers{display:flex;flex-direction:column;gap:8px}
.rline{padding:8px 10px;border-radius:10px;background:color-mix(in srgb,var(--secondary-text-color) 8%,transparent)}
.rline.offline{opacity:.6}
.rhead{display:flex;align-items:center;gap:8px}
.rname{font-weight:500}
.rbody{display:flex;align-items:center;gap:12px;margin-top:4px;flex-wrap:wrap}
.rtemp{font-size:1.15rem;font-weight:500}
.rpow{color:var(--secondary-text-color)}
.rbody .open{margin-left:auto;color:var(--primary-color)}
.opts{display:flex;flex-direction:column;padding:6px 8px 14px}
.opt{display:flex;gap:12px;align-items:flex-start;text-align:left;padding:12px 10px;border-radius:10px;min-height:44px}
.opt b{display:block;font-weight:500;margin-bottom:2px}
.opt .radio{flex:none;width:18px;height:18px;margin-top:2px;border-radius:50%;border:2px solid var(--secondary-text-color)}
.opt.sel{background:color-mix(in srgb,var(--primary-color) 10%,transparent)}
.opt.sel .radio{border-color:var(--primary-color);box-shadow:inset 0 0 0 3px var(--card-background-color,#fff),inset 0 0 0 10px var(--primary-color)}
.confirm{padding:8px 10px 14px}
.confirm p{margin:6px 0 12px}
.btns{display:flex;gap:10px}
.btns .act{margin-top:0;justify-content:center;text-align:center}
.ghostbtn{background:color-mix(in srgb,var(--secondary-text-color) 12%,transparent);color:var(--primary-text-color)}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:8}
.dialog{position:fixed;z-index:9;left:50%;top:50%;transform:translate(-50%,-50%);width:min(560px,calc(100vw - 16px));
  max-height:calc(100vh - 32px);overflow:auto;border-radius:16px;background:var(--card-background-color,#fff);
  box-shadow:0 10px 40px rgba(0,0,0,.35)}
.dh{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;padding:6px 6px 6px 18px;
  font-weight:500;background:var(--card-background-color,#fff);border-bottom:1px solid var(--divider-color,rgba(127,127,127,.2))}
.icon{width:44px;height:44px;display:flex;align-items:center;justify-content:center;border-radius:50%}
.dbody{padding:8px}
@media (max-width:420px){ha-card{padding:12px}.big{font-size:1.25rem}.ring{width:72px;height:72px}}
`;

/* ------------------------------------------------------------------ éditeur visuel */
class ChefOrchestreEnergieCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._draw();
  }
  set hass(hass) {
    this._hass = hass;
    this._draw();
  }
  _draw() {
    if (!this._hass || !this._config) return;
    const lang = (this._hass.locale?.language || "en").slice(0, 2);
    const t = (ENERGY_I18N[lang] || ENERGY_I18N.en).editor;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => t[s.name] || s.name;
      this._form.addEventListener("value-changed", (ev) => {
        this._config = { ...this._config, ...ev.detail.value };
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = [
      ...BLOCKS.map((name) => ({ name, selector: { boolean: {} } })),
      { name: "gauge_warn", selector: { number: { min: 50, max: 100, step: 1, mode: "box", unit_of_measurement: "%" } } },
      { name: "gauge_crit", selector: { number: { min: 50, max: 100, step: 1, mode: "box", unit_of_measurement: "%" } } },
    ];
    this._form.data = this._config;
  }
}

if (!customElements.get("chef-orchestre-energie-card")) {
  customElements.define("chef-orchestre-energie-card", ChefOrchestreEnergieCard);
  customElements.define("chef-orchestre-energie-card-editor", ChefOrchestreEnergieCardEditor);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "chef-orchestre-energie-card",
    name: "Chef d'orchestre — Énergie",
    description: "Tarif, batteries, plan et puissance au tableau / Tariff, batteries, plan and panel power",
    preview: true,
    documentationURL: "https://github.com/JVmaisGpeur/ha-chef-orchestre-energie",
  });
  console.info(`%c CHEF-ORCHESTRE-ENERGIE-CARD %c ${ENERGY_CARD_VERSION} `, "background:#0b7a75;color:#fff", "");
}
