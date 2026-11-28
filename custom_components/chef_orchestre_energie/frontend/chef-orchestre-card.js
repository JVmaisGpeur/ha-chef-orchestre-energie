/*
 * Chef d'orchestre énergie — carte Lovelace livrée avec l'intégration chef_orchestre_energie.
 * Aucune configuration requise : la carte trouve seule les entités du Chef d'orchestre.
 *
 *   type: custom:chef-orchestre-card
 *   name: ...              # optionnel : titre
 *   show_chart: true       # graphique des 48 h à venir
 *   show_modes: true       # frise des modes prévus
 *   show_settings: true    # réglages rapides
 *   show_days: true        # plan du jour et plan du lendemain (v1.4.0)
 */
const CARD_VERSION = "1.4.0";
const DOMAIN = "chef_orchestre_energie";

const HELP_KEYS = ["plan", "nightActive", "nightKept", "efficiency", "wear", "gain", "savings", "days", "chart", "modes", "settings"];

const I18N = {
  fr: {
    title: "Chef d'orchestre énergie",
    auto: "Pilotage automatique",
    toCharge: "À charger", target: "SOC cible", start: "Début", gain: "Gain prévu", savings: "Économies du mois",
    next48: "48 prochaines heures", soc: "SOC simulé", price: "Prix", offPeak: "Heures creuses", gridCharge: "Charge réseau",
    modes: "Modes prévus", settings: "Réglages rapides", profile: "Prudence", threshold: "Seuil de rentabilité",
    recalc: "Recalculer", now: "maintenant",
    notFound: "Chef d'orchestre énergie introuvable. Vérifie que l'intégration est configurée.",
    alerts: {
      power: "Risque de dépasser la puissance souscrite cette nuit : vérifie les gros consommateurs.",
      finish: "La charge risque de ne pas finir avant la fin des heures creuses.",
      short: "Batterie trop petite pour tout couvrir : l'énergie est gardée pour les heures les plus chères.",
      suspended: "Pilotage suspendu : aucune commande n'est envoyée à la batterie.",
      missing: "Données manquantes : aucune commande n'est envoyée. Consulte Paramètres → Réparations.",
    },
    missingItems: { sources: "intégrations ou entités introuvables", tariff: "Tarifs électricité absente (prix et heures creuses)", solar_forecast: "prévision solaire indisponible", tariff_forecast: "prévisions tarifaires",
      battery_state: "état de la batterie (capacité, SOC)", subscribed_power: "puissance souscrite",
      off_peak_price: "prix des heures creuses", error: "erreur de calcul (voir les journaux)" },
    modeNames: { off: "Arrêt", grid_charge: "Charge réseau", smart: "Couplage intelligent", smart_charge: "Réserve (stocke le solaire)" },
    profiles: { cautious: "Prudent", balanced: "Équilibré", economical: "Économe" },
    ed: { name: "Titre", show_chart: "Afficher le graphique des 48 h", show_modes: "Afficher la frise des modes", show_settings: "Afficher les réglages rapides", show_days: "Afficher le plan du jour et du lendemain" },
    nightActive: "Cette nuit : la batterie alimente la maison jusqu'à {floor} %, le soleil de demain la remplira",
    nightKept: "Cette nuit : batterie gardée pour demain (besoin {need} kWh)",
    nightKeptNoNeed: "Cette nuit : batterie gardée pour demain",
    nightUnavailable: "Nuit sur batterie indisponible : pas de prévision solaire",
    efficiency: "Rendement", measuredAc: "mesuré côté prise", typed: "saisi", wear: "Usure", wearPayback: "Rentabilité solaire", wearManual: "saisie",
    dayToday: "Plan du jour", dayTomorrow: "Plan du lendemain", forecast: "Prévision", tomorrow: "demain",
    chargeLine: "Charge {kwh} kWh de {from} à {to}", targetSoc: "SOC cible {soc} %", noCharge: "Pas de charge", decidedEve: "Charge décidée la veille au soir",
    reserveLine: "Réserve {soc} % de {from} à {to}", nightFloor: "Nuit sur batterie jusqu'à {soc} %",
    socLine: "Batterie : {a} % → mini {b} % → {c} %", energyLine: "Solaire {s} kWh · conso {c} kWh · réseau {g} kWh", cost: "Coût de la charge",
    truncated: "jusqu'à {t} (fin des prévisions)", dayStart: "Début de journée", dayStarts: { off_peak_end: "Fin des HC", off_peak_start: "Début des HC", midnight: "Minuit", fixed: "Heure fixe" },
    help: {
      plan: "Ce que le Chef d'orchestre a décidé pour la prochaine nuit : charger au réseau en heures creuses, ou non, et pourquoi. Touchez le bloc pour le détail.",
      nightActive: "Demain, le soleil prévu remplira la batterie. Elle peut donc alimenter la maison cette nuit, en gardant de quoi couvrir les heures pleines de demain avant le soleil, avec une marge.",
      nightKept: "La batterie ne descend pas cette nuit : le soleil de demain ne suffira pas à la remplir, et son énergie vaut plus en heures pleines.",
      efficiency: "Mesuré côté prise sur 30 jours : ce qui ressort vers la maison pour ce qui est entré du réseau. Sans mesure fiable (hors 60 à 95 %), le rendement saisi est utilisé.",
      wear: "Le coût d'usure par kWh rendu, lu dans la Rentabilité solaire ou saisi, ajouté au coût d'une recharge.",
      gain: "Ce que la recharge de cette nuit doit faire économiser demain : l'énergie rendue aux heures pleines, moins son coût en heures creuses, pertes et usure comprises.",
      savings: "Ce que la batterie a évité d'acheter, moins ce qu'a coûté sa recharge et le surplus qu'elle a pris au lieu de le revendre. La Rentabilité solaire compte la même chose sur toute la vie de la batterie.",
      days: "Le plan découpé en journées, à partir de l'heure de début choisie dans les réglages rapides. Le Chef ne décide que la prochaine nuit : la nuit suivante sera décidée la veille au soir.",
      chart: "Niveau prévu des batteries, prix de l'électricité et heures creuses sur les 48 prochaines heures. Survolez pour le détail d'un quart d'heure.",
      modes: "Le mode que le Chef donnera aux batteries à chaque moment : arrêt, charge réseau, couplage intelligent (la batterie alimente la maison) ou réserve (elle stocke seulement le solaire).",
      settings: "Prudence : marge ajoutée au besoin de demain. Seuil : gain minimal par kWh pour charger la nuit. Début de journée : où commencent les cases du plan.",
    },
  },
  en: {
    title: "Energy conductor",
    auto: "Automatic control",
    toCharge: "To charge", target: "Target SOC", start: "Start", gain: "Forecast gain", savings: "Savings this month",
    next48: "Next 48 hours", soc: "Simulated SOC", price: "Price", offPeak: "Off-peak hours", gridCharge: "Grid charge",
    modes: "Planned modes", settings: "Quick settings", profile: "Caution", threshold: "Profitability threshold",
    recalc: "Recalculate", now: "now",
    notFound: "Energy conductor not found. Make sure the integration is set up.",
    alerts: {
      power: "Risk of exceeding the subscribed power tonight: check the large appliances.",
      finish: "The charge may not finish before the end of off-peak hours.",
      short: "Battery too small to cover everything: energy is kept for the most expensive hours.",
      suspended: "Control suspended: no command is sent to the battery.",
      missing: "Data missing: no command is sent. See Settings → Repairs.",
    },
    missingItems: { sources: "integrations or entities not found", tariff: "Electricity Tariffs missing (prices and off-peak hours)", solar_forecast: "solar forecast unavailable", tariff_forecast: "tariff forecast",
      battery_state: "battery state (capacity, SOC)", subscribed_power: "subscribed power",
      off_peak_price: "off-peak price", error: "calculation error (see the logs)" },
    modeNames: { off: "Off", grid_charge: "Grid charge", smart: "Smart matching", smart_charge: "Reserve (stores solar)" },
    profiles: { cautious: "Cautious", balanced: "Balanced", economical: "Economical" },
    ed: { name: "Title", show_chart: "Show the 48 h chart", show_modes: "Show the mode strip", show_settings: "Show quick settings", show_days: "Show the plan for today and tomorrow" },
    nightActive: "Tonight: the battery powers the house down to {floor} %, tomorrow's sun will refill it",
    nightKept: "Tonight: battery kept for tomorrow (need {need} kWh)",
    nightKeptNoNeed: "Tonight: battery kept for tomorrow",
    nightUnavailable: "Night on battery unavailable: no solar forecast",
    efficiency: "Efficiency", measuredAc: "measured at the plug", typed: "entered", wear: "Wear", wearPayback: "Solar payback", wearManual: "entered",
    dayToday: "Today's plan", dayTomorrow: "Tomorrow's plan", forecast: "Forecast", tomorrow: "tomorrow",
    chargeLine: "Charge {kwh} kWh from {from} to {to}", targetSoc: "target SOC {soc} %", noCharge: "No charge", decidedEve: "Charge decided the evening before",
    reserveLine: "Reserve {soc} % from {from} to {to}", nightFloor: "Night on battery down to {soc} %",
    socLine: "Battery: {a} % → low {b} % → {c} %", energyLine: "Solar {s} kWh · use {c} kWh · grid {g} kWh", cost: "Charge cost",
    truncated: "until {t} (end of forecast)", dayStart: "Day start", dayStarts: { off_peak_end: "End of off-peak", off_peak_start: "Start of off-peak", midnight: "Midnight", fixed: "Fixed time" },
    help: {
      plan: "What the Energy conductor decided for the next night: charge from the grid during off-peak hours or not, and why. Tap the block for details.",
      nightActive: "Tomorrow's forecast sun will refill the battery. It can therefore power the house tonight, keeping enough to cover tomorrow's peak hours before the sun, with a margin.",
      nightKept: "The battery does not go down tonight: tomorrow's sun will not be enough to refill it, and its energy is worth more at peak hours.",
      efficiency: "Measured at the plug over 30 days: what comes out to the house for what came in from the grid. Without a reliable measurement (outside 60 to 95 %), the entered efficiency is used.",
      wear: "The wear cost per kWh delivered, read from Solar payback or entered, added to the cost of a charge.",
      gain: "What tonight's charge should save tomorrow: the energy delivered at peak hours, minus its off-peak cost, losses and wear included.",
      savings: "What the battery avoided buying, minus the cost of charging it and of the surplus it took instead of selling it. Solar payback counts the same over the whole life of the battery.",
      days: "The plan cut into days, from the start time chosen in the quick settings. The conductor only decides the next night: the following one is decided the evening before.",
      chart: "Forecast battery level, electricity price and off-peak hours over the next 48 hours. Hover for a quarter-hour's details.",
      modes: "The mode the conductor gives the batteries at each moment: off, grid charge, smart matching (the battery powers the house) or reserve (it only stores solar).",
      settings: "Caution: margin added to tomorrow's need. Threshold: minimum gain per kWh to charge at night. Day start: where the plan's days begin.",
    },
  },
};

const MODE_COLORS = { off: "#9e9e9e", grid_charge: "#4a90d9", smart: "#26c6a8", smart_charge: "#ffb300" };
const PLAN_COLORS = {
  charge: "#4a90d9", idle: "#26c6a8", not_profitable: "#9e9e9e",
  nothing_to_cover: "#2ecc71", suspended: "#ff9800", missing_data: "#ef5350",
};
const PLAN_ICONS = {
  charge: "mdi:battery-charging-high", idle: "mdi:battery-heart-variant", not_profitable: "mdi:cash-remove",
  nothing_to_cover: "mdi:battery-check", suspended: "mdi:pause-circle-outline", missing_data: "mdi:alert-circle-outline",
};
const KEYS = [
  "night_plan", "energy_to_charge", "target_soc", "charge_start", "forecast_gain", "monthly_savings",
  "auto_control", "profile", "gain_threshold", "power_alert", "recalculate", "day_start", "day_start_time",
];
const num = (v) => {
  const n = parseFloat(v);
  return isNaN(n) ? null : n;
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class ChefOrchestreCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("chef-orchestre-card-editor");
  }
  static getStubConfig() {
    return { show_chart: true, show_modes: true, show_settings: true, show_days: true };
  }
  setConfig(config) {
    this._config = { show_chart: true, show_modes: true, show_settings: true, show_days: true, ...(config || {}) };
    this._sig = null;
    if (this._hass) this._render();
  }
  set hass(hass) {
    this._hass = hass;
    this._render();
  }
  getCardSize() {
    return 10;
  }
  connectedCallback() {
    if (!this._ro) {
      this._ro = new ResizeObserver((entries) => {
        const w = Math.round(entries[0].contentRect.width) - 36; // marges de la carte
        if (w > 0 && Math.abs(w - (this._width || 0)) > 8) {
          this._width = w;
          this._sig = null;
          this._render();
        }
      });
    }
    this._ro.observe(this);
  }
  disconnectedCallback() {
    this._ro?.disconnect();
  }
  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  get _lang() {
    return (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
  }
  get _t() {
    return I18N[this._lang] || I18N.en;
  }

  /* ---------- entités par translation_key (indépendant des noms et de la langue) ---------- */
  _resolve() {
    const map = {};
    for (const e of Object.values(this._hass.entities || {})) {
      if (e.platform === DOMAIN && KEYS.includes(e.translation_key) && !(e.translation_key in map)) {
        map[e.translation_key] = e.entity_id;
      }
    }
    return map.night_plan ? map : null;
  }
  _st(key) {
    const id = this._ents?.[key];
    return id ? this._hass.states[id] : undefined;
  }
  _fmtState(key) {
    const s = this._st(key);
    if (!s) return "—";
    return this._hass.formatEntityState ? this._hass.formatEntityState(s) : s.state;
  }
  _fmtAttr(key, attr) {
    const s = this._st(key);
    if (!s || s.attributes[attr] == null) return "";
    return this._hass.formatEntityAttributeValue ? this._hass.formatEntityAttributeValue(s, attr) : s.attributes[attr];
  }
  _nf(v, digits) {
    return new Intl.NumberFormat(this._hass.locale?.language || this._lang, {
      minimumFractionDigits: digits, maximumFractionDigits: digits,
    }).format(v);
  }
  _time(d, withDay = false) {
    const opts = { hour: "2-digit", minute: "2-digit" };
    if (withDay) opts.weekday = "short";
    return new Intl.DateTimeFormat(this._hass.locale?.language || this._lang, opts).format(d);
  }
  _more(key) {
    const entityId = this._ents?.[key];
    if (entityId) this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
  }
  _call(domain, service, data) {
    return this._hass.callService(domain, service, data);
  }

  /* ---------------------------------------- rendu ---------------------------------------- */
  _render() {
    if (!this._hass || !this._config) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._ents = this._resolve();
    if (!this._ents) {
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card class="empty">${esc(this._t.notFound)}</ha-card>`;
      return;
    }
    // On ne redessine que si une de nos entités a changé
    const sig = KEYS.map((k) => this._st(k)?.last_updated + "|" + this._st(k)?.state).join(";") + this._lang;
    if (sig === this._sig) return;
    this._sig = sig;

    const t = this._t;
    const plan = this._st("night_plan");
    const state = plan?.state;
    const a = plan?.attributes || {};
    const steps = Array.isArray(a.hourly_plan) ? a.hourly_plan : [];
    const auto = this._st("auto_control")?.state === "on";
    const color = PLAN_COLORS[state] || "#9e9e9e";

    const alerts = [];
    if (this._st("power_alert")?.state === "on") alerts.push(["mdi:flash-alert", t.alerts.power, "crit"]);
    if (a.may_not_finish) alerts.push(["mdi:timer-alert-outline", t.alerts.finish, "warn"]);
    if (a.capacity_short) alerts.push(["mdi:battery-alert-variant-outline", t.alerts.short, "info"]);
    if (state === "suspended") alerts.push(["mdi:pause-circle-outline", t.alerts.suspended, "warn"]);
    if (state === "missing_data") {
      const items = (a.missing || []).map((k) => t.missingItems[k] || k);
      alerts.push(["mdi:alert-circle-outline", t.alerts.missing + (items.length ? ` (${items.join(", ")})` : ""), "crit"]);
    }

    const charge = state === "charge";
    const energy = num(this._st("energy_to_charge")?.state);
    const soc = num(this._st("target_soc")?.state);
    const startRaw = this._st("charge_start")?.state;
    const startDate = startRaw && !["unknown", "unavailable"].includes(startRaw) ? new Date(startRaw) : null;
    const gain = num(this._st("forecast_gain")?.state);
    const sav = num(this._st("monthly_savings")?.state);
    const ib = (k) => `<button class="ib" data-help="${k}" title="i">i</button>`;
    const hp = (k) => `<div class="help ${this._open?.has(k) ? "show" : ""}" data-for="${k}">${esc(t.help[k])}</div>`;
    const tile = (key, icon, label, value, dim = false, help = "") => `
      <div class="tile ${dim ? "dim" : ""}" data-more="${key}">
        <ha-icon icon="${icon}"></ha-icon><span class="v">${value}</span><span class="l">${esc(label)}${help}</span>
      </div>`;

    const reason = this._fmtAttr("night_plan", "reason");
    // v1.4.0 (P1) : nuit sur batterie
    const nob = a.night_on_battery;
    let night = "";
    if (nob === "active" && a.night_floor_soc != null) {
      night = `<div class="note ok"><ha-icon icon="mdi:weather-night"></ha-icon><span>${esc(t.nightActive.replace("{floor}", this._nf(a.night_floor_soc, 0)))}${ib("nightActive")}</span></div>${hp("nightActive")}`;
    } else if (nob === "kept") {
      const need = a.tomorrow_need_kwh;
      const txt = need != null ? t.nightKept.replace("{need}", this._nf(need, 1)) : t.nightKeptNoNeed;
      night = `<div class="note"><ha-icon icon="mdi:battery-lock"></ha-icon><span>${esc(txt)}${ib("nightKept")}</span></div>${hp("nightKept")}`;
    } else if (nob === "unavailable") {
      night = `<div class="note"><ha-icon icon="mdi:weather-cloudy-alert"></ha-icon><span>${esc(t.nightUnavailable)}</span></div>`;
    }
    // v1.4.0 (C0, C4) : rendement mesuré côté prise et usure
    const eff = num(a.efficiency);
    const wear = num(a.wear);
    const details = eff !== null ? `
      <div class="details">
        <span>${esc(t.efficiency)} ${this._nf(eff * 100, 0)} %${ib("efficiency")}</span>
        ${wear !== null ? `<span>${esc(t.wear)} ${this._nf(wear, 3)} €/kWh (${esc(a.wear_source === "solar_payback" ? t.wearPayback : t.wearManual)})${ib("wear")}</span>` : ""}
      </div>${hp("efficiency")}${wear !== null ? hp("wear") : ""}` : "";
    const html = `
      <style>${STYLE}</style>
      <ha-card style="--plan:${color}">
        <div class="head">
          <div class="title">${esc(this._config.name || t.title)}</div>
          <button class="auto ${auto ? "on" : ""}" id="auto" title="${esc(t.auto)}">
            <ha-icon icon="${auto ? "mdi:robot-outline" : "mdi:robot-off-outline"}"></ha-icon><span>${esc(t.auto)}</span><i></i>
          </button>
        </div>

        <div class="plan" data-more="night_plan">
          <div class="badge"><ha-icon icon="${PLAN_ICONS[state] || "mdi:battery-clock"}"></ha-icon></div>
          <div>
            <div class="state">${esc(this._fmtState("night_plan"))}${ib("plan")}</div>
            <div class="reason">${esc(reason)}</div>
          </div>
        </div>
        ${hp("plan")}
        ${night}
        ${details}

        ${alerts.map(([i, m, c]) => `<div class="alert ${c}"><ha-icon icon="${i}"></ha-icon><span>${esc(m)}</span></div>`).join("")}

        <div class="tiles">
          ${tile("energy_to_charge", "mdi:battery-arrow-up", t.toCharge, charge && energy !== null ? `${this._nf(energy, 1)} kWh` : "—", !charge)}
          ${tile("target_soc", "mdi:battery-high", t.target, charge && soc !== null ? `${this._nf(soc, 0)} %` : "—", !charge)}
          ${tile("charge_start", "mdi:clock-start", t.start, charge && startDate ? this._time(startDate) : "—", !charge)}
          ${tile("forecast_gain", "mdi:cash-plus", t.gain, gain !== null ? this._money(gain) : "—", false, ib("gain"))}
          ${tile("monthly_savings", "mdi:piggy-bank-outline", t.savings, sav !== null ? this._money(sav) : "—", false, ib("savings"))}
        </div>
        ${hp("gain")}${hp("savings")}

        ${this._config.show_days && Array.isArray(a.days) && a.days.length ? this._days(a.days, ib, hp) : ""}
        ${this._config.show_chart && steps.length > 1 ? this._chart(steps, ib, hp) : ""}
        ${this._config.show_modes && steps.length > 1 ? this._modes(steps, ib, hp) : ""}
        ${this._config.show_settings ? this._settings(ib, hp) : ""}
      </ha-card>`;
    this.shadowRoot.innerHTML = html;
    this._wire(steps);
  }

  _money(v) {
    return new Intl.NumberFormat(this._hass.locale?.language || this._lang, { style: "currency", currency: "EUR" }).format(v);
  }

  /* --------------------------------- graphique des 48 h --------------------------------- */
  _chart(steps, ib, hp) {
    const t = this._t;
    const W = Math.max(280, Math.round(this._width || 600)), H = 210, L = 34, R = 44, T = 12, B = 26;
    const t0 = Date.parse(steps[0].start);
    const dt = Date.parse(steps[1].start) - t0;
    const t1 = Date.parse(steps[steps.length - 1].start) + dt;
    const x = (ms) => L + ((ms - t0) / (t1 - t0)) * (W - L - R);
    const ySoc = (v) => T + (1 - v / 100) * (H - T - B);
    const prices = steps.map((s) => s.price).filter((p) => p != null);
    const pMax = prices.length ? Math.max(...prices) * 1.1 : 1;
    const yP = (p) => T + (1 - p / pMax) * (H - T - B);

    // Bandes d'heures creuses
    let bands = "";
    let runStart = null;
    steps.forEach((s, i) => {
      const ms = Date.parse(s.start);
      if (s.off_peak && runStart === null) runStart = ms;
      const last = i === steps.length - 1;
      if (runStart !== null && (!s.off_peak || last)) {
        const end = s.off_peak && last ? ms + dt : ms;
        bands += `<rect x="${x(runStart)}" y="${T}" width="${x(end) - x(runStart)}" height="${H - T - B}" class="hc"/>`;
        runStart = null;
      }
    });
    // Courbe du SOC (aire) et segments en charge réseau
    const pts = steps.map((s) => [x(Date.parse(s.start) + dt), ySoc(s.soc)]);
    const first = [x(t0), ySoc(steps[0].soc)];
    const line = [first, ...pts].map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" ");
    const area = `${x(t0)},${ySoc(0)} ${line} ${x(t1)},${ySoc(0)}`;
    let charge = "";
    steps.forEach((s, i) => {
      if (s.mode === "grid_charge") {
        const prev = i ? pts[i - 1] : first;
        charge += `<line x1="${prev[0]}" y1="${prev[1]}" x2="${pts[i][0]}" y2="${pts[i][1]}" class="gc"/>`;
      }
    });
    // Prix en escalier
    let price = "";
    steps.forEach((s) => {
      if (s.price == null) return;
      const a = x(Date.parse(s.start)), b = a + (x(t0 + dt) - x(t0));
      price += `M${a.toFixed(1)},${yP(s.price).toFixed(1)}H${b.toFixed(1)}`;
    });
    // Graduations : toutes les 6 h, jour à minuit
    let ticks = "";
    const first6 = new Date(t0);
    first6.setMinutes(0, 0, 0);
    first6.setHours(Math.ceil(first6.getHours() / 6) * 6);
    for (let ms = first6.getTime(); ms < t1; ms += 6 * 3600e3) {
      const d = new Date(ms);
      const midnight = d.getHours() === 0;
      const lbl = midnight
        ? new Intl.DateTimeFormat(this._hass.locale?.language || this._lang, { weekday: "short" }).format(d)
        : `${d.getHours()} h`;
      ticks += `<line x1="${x(ms)}" x2="${x(ms)}" y1="${T}" y2="${H - B}" class="${midnight ? "mid" : "grid"}"/>
                <text x="${x(ms)}" y="${H - 8}" class="tick">${esc(this._lang === "fr" ? lbl : midnight ? lbl : `${d.getHours()}:00`)}</text>`;
    }
    const yTicks = [0, 50, 100].map((v) => `<text x="${L - 6}" y="${ySoc(v) + 4}" class="ax l">${v}%</text>`).join("");
    const pTicks = prices.length
      ? [0, pMax / 1.1].map((p) => `<text x="${W - R + 6}" y="${yP(p) + 4}" class="ax r">${this._nf(p, 2)}</text>`).join("")
      : "";
    return `
      <div class="section">
        <div class="sec-title">${esc(t.next48)}${ib("chart")}</div>${hp("chart")}
        <div class="chart">
          <svg viewBox="0 0 ${W} ${H}" id="svg">
            ${bands}${ticks}
            <polygon points="${area}" class="socA"/>
            <polyline points="${line}" class="socL"/>
            ${charge}
            <path d="${price}" class="price"/>
            <line x1="${x(Date.now())}" x2="${x(Date.now())}" y1="${T}" y2="${H - B}" class="now"/>
            ${yTicks}${pTicks}
            <line id="cursor" x1="0" x2="0" y1="${T}" y2="${H - B}" class="cursor" style="display:none"/>
            <rect id="hit" x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent"/>
          </svg>
          <div class="tip" id="tip"></div>
        </div>
        <div class="legend">
          <span><i class="sw soc"></i>${esc(t.soc)}</span>
          <span><i class="sw gc"></i>${esc(t.gridCharge)}</span>
          <span><i class="sw pr"></i>${esc(t.price)} (€/kWh)</span>
          <span><i class="sw hc"></i>${esc(t.offPeak)}</span>
        </div>
      </div>`;
  }

  /* ------------------------------------ frise des modes ------------------------------------ */
  _modes(steps, ib, hp) {
    const t = this._t;
    const runs = [];
    for (const s of steps) {
      const last = runs[runs.length - 1];
      if (last && last.mode === s.mode) last.n++;
      else runs.push({ mode: s.mode, n: 1, start: Date.parse(s.start) });
    }
    const used = [...new Set(steps.map((s) => s.mode))];
    return `
      <div class="section">
        <div class="sec-title">${esc(t.modes)}${ib("modes")}</div>${hp("modes")}
        <div class="strip">
          ${runs.map((r) => `<div style="flex:${r.n};background:${MODE_COLORS[r.mode] || "#777"}"
              title="${esc(this._time(new Date(r.start), true))} · ${esc(t.modeNames[r.mode] || r.mode)}"></div>`).join("")}
        </div>
        <div class="legend">
          ${used.map((m) => `<span><i class="sw" style="background:${MODE_COLORS[m] || "#777"}"></i>${esc(t.modeNames[m] || m)}</span>`).join("")}
        </div>
      </div>`;
  }

  /* ------------------------------ plan du jour et du lendemain ------------------------------ */
  _days(days, ib, hp) {
    const t = this._t;
    const c = (s, map) => Object.entries(map).reduce((acc, [k, v]) => acc.replace(`{${k}}`, v), s);
    const hm = (iso) => (iso ? this._time(new Date(iso)) : "—");
    const box = (d, i) => {
      if (!d || d.empty) return "";
      const start = new Date(d.start), end = new Date(d.end);
      const period = `${i ? esc(t.tomorrow) + " " : ""}${hm(d.start)} → ${hm(d.end)}`;
      const lines = [];
      if (d.charge_kwh > 0) {
        let l = c(t.chargeLine, { kwh: this._nf(d.charge_kwh, 1), from: hm(d.charge_start), to: hm(d.charge_end) });
        if (d.target_soc != null) l += `, ${c(t.targetSoc, { soc: this._nf(d.target_soc, 0) })}`;
        lines.push(["mdi:battery-charging-high", l]);
      } else if (d.night_decided) {
        const why = d.night_state && this._hass.formatEntityState ? this._hass.formatEntityState(this._st("night_plan"), d.night_state) : "";
        lines.push(["mdi:battery-off-outline", t.noCharge + (why ? ` : ${why}` : "")]);
      } else {
        lines.push(["mdi:calendar-clock", t.decidedEve]);
      }
      if (d.reserve_soc != null) lines.push(["mdi:battery-lock", c(t.reserveLine, { soc: this._nf(d.reserve_soc, 0), from: hm(d.reserve_from), to: hm(d.reserve_until) })]);
      if (d.night_floor_soc != null) lines.push(["mdi:weather-night", c(t.nightFloor, { soc: this._nf(d.night_floor_soc, 0) })]);
      lines.push(["mdi:battery-medium", c(t.socLine, { a: this._nf(d.soc_start, 0), b: this._nf(d.soc_min, 0), c: this._nf(d.soc_end, 0) })]);
      lines.push(["mdi:flash", c(t.energyLine, { s: this._nf(d.solar_kwh, 1), c: this._nf(d.consumption_kwh, 1), g: this._nf(d.charge_kwh, 1) })]);
      lines.push(["mdi:cash", `${t.cost} : ${d.cost != null ? this._money(d.cost) : "—"}`]);
      // Frise de la journée, à partir des changements de mode
      const span = end - start;
      const modes = Array.isArray(d.modes) ? d.modes : [];
      const stop = d.truncated_at ? new Date(d.truncated_at) : end;
      const strip = modes.map(([iso, m], k) => {
        const a0 = Math.max(new Date(iso) - start, 0);
        const a1 = (k + 1 < modes.length ? new Date(modes[k + 1][0]) : stop) - start;
        return `<div style="left:${(a0 / span) * 100}%;width:${(Math.max(a1 - a0, 0) / span) * 100}%;background:${MODE_COLORS[m] || "#777"}" title="${esc(t.modeNames[m] || m)}"></div>`;
      }).join("");
      return `
        <div class="day" data-more="night_plan">
          <div class="dhead"><b>${esc(i ? t.dayTomorrow : t.dayToday)}</b>${i ? `<span class="fc">${esc(t.forecast)}</span>` : ""}</div>
          <div class="dper">${period}${d.truncated_at ? ` · ${esc(c(t.truncated, { t: hm(d.truncated_at) }))}` : ""}</div>
          <div class="dstrip">${strip}</div>
          ${lines.map(([ic, l]) => `<div class="dl"><ha-icon icon="${ic}"></ha-icon><span>${esc(l)}</span></div>`).join("")}
        </div>`;
    };
    return `
      <div class="section">
        <div class="sec-title">${esc(t.dayToday)} · ${esc(t.dayTomorrow)}${ib("days")}</div>${hp("days")}
        <div class="days">${days.map((d, i) => box(d, i)).join("")}</div>
      </div>`;
  }

  _dayStartRow() {
    const t = this._t;
    const sel = this._st("day_start");
    if (!sel) return "";
    const opts = sel.attributes?.options || Object.keys(t.dayStarts);
    const tm = this._st("day_start_time")?.state;
    return `
          <div class="row">
            <span class="lbl">${esc(t.dayStart)}</span>
            <div class="chips">
              ${opts.map((o) => `<button class="chip ${sel.state === o ? "sel" : ""}" data-daystart="${esc(o)}">${esc(t.dayStarts[o] || o)}</button>`).join("")}
              ${sel.state === "fixed" ? `<input type="time" id="daytime" value="${esc((tm || "06:00").slice(0, 5))}"/>` : ""}
            </div>
          </div>`;
  }

  /* ----------------------------------- réglages rapides ----------------------------------- */
  _settings(ib, hp) {
    const t = this._t;
    const prof = this._st("profile");
    const thr = num(this._st("gain_threshold")?.state);
    const opts = prof?.attributes?.options || ["cautious", "balanced", "economical"];
    return `
      <div class="section">
        <div class="sec-title">${esc(t.settings)}${ib("settings")}</div>${hp("settings")}
        <div class="settings">
          <div class="row">
            <span class="lbl">${esc(t.profile)}</span>
            <div class="chips">
              ${opts.map((o) => `<button class="chip ${prof?.state === o ? "sel" : ""}" data-profile="${esc(o)}">${esc(t.profiles[o] || o)}</button>`).join("")}
            </div>
          </div>
          <div class="row">
            <span class="lbl">${esc(t.threshold)}</span>
            <div class="thr">
              <input type="number" id="thr" min="0" max="1" step="0.005" value="${thr ?? ""}"/><span>€/kWh</span>
            </div>
          </div>
          ${this._dayStartRow()}
          <button class="recalc" id="recalc"><ha-icon icon="mdi:refresh"></ha-icon>${esc(t.recalc)}</button>
        </div>
      </div>`;
  }

  /* ----------------------------------- interactions ----------------------------------- */
  _wire(steps) {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-more]").forEach((el) => el.addEventListener("click", () => this._more(el.dataset.more)));
    root.getElementById("auto")?.addEventListener("click", () =>
      this._call("switch", this._st("auto_control")?.state === "on" ? "turn_off" : "turn_on", { entity_id: this._ents.auto_control }));
    root.querySelectorAll("[data-profile]").forEach((el) =>
      el.addEventListener("click", () => this._call("select", "select_option", { entity_id: this._ents.profile, option: el.dataset.profile })));
    root.getElementById("thr")?.addEventListener("change", (ev) => {
      const v = num(ev.target.value);
      if (v !== null && v >= 0 && v <= 1) this._call("number", "set_value", { entity_id: this._ents.gain_threshold, value: v });
    });
    root.querySelectorAll("[data-daystart]").forEach((el) =>
      el.addEventListener("click", () => this._call("select", "select_option", { entity_id: this._ents.day_start, option: el.dataset.daystart })));
    root.getElementById("daytime")?.addEventListener("change", (ev) => {
      if (ev.target.value) this._call("time", "set_value", { entity_id: this._ents.day_start_time, time: `${ev.target.value}:00` });
    });
    // Boutons « i » : le texte s'ouvre sous le bloc, sans ouvrir la fenêtre de l'entité
    root.querySelectorAll(".ib").forEach((b) => b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const k = b.dataset.help;
      this._open = this._open || new Set();
      if (this._open.has(k)) this._open.delete(k); else this._open.add(k);
      root.querySelector(`.help[data-for="${k}"]`)?.classList.toggle("show", this._open.has(k));
    }));
    root.getElementById("recalc")?.addEventListener("click", () => this._call("button", "press", { entity_id: this._ents.recalculate }));

    const hit = root.getElementById("hit");
    const svg = root.getElementById("svg");
    const tip = root.getElementById("tip");
    const cursor = root.getElementById("cursor");
    if (!hit || !steps.length) return;
    const move = (ev) => {
      const box = svg.getBoundingClientRect();
      const hb = hit.getBoundingClientRect();
      const ratio = Math.min(Math.max((ev.clientX - hb.left) / hb.width, 0), 0.9999);
      const s = steps[Math.floor(ratio * steps.length)];
      const vbX = parseFloat(hit.getAttribute("x")) + ratio * parseFloat(hit.getAttribute("width"));
      cursor.setAttribute("x1", vbX);
      cursor.setAttribute("x2", vbX);
      cursor.style.display = "";
      const t = this._t;
      const c = this._lang === "fr" ? " :" : ":";
      tip.innerHTML = `<b>${esc(this._time(new Date(s.start), true))}</b><br>
        ${esc(t.soc)}${c} ${this._nf(s.soc, 0)} %<br>
        ${s.price != null ? `${esc(t.price)}${c} ${this._nf(s.price, 3)} €/kWh<br>` : ""}
        ${esc(t.modeNames[s.mode] || s.mode)}`;
      tip.style.display = "block";
      const left = ev.clientX - box.left;
      tip.style.left = `${Math.min(Math.max(left + 12, 0), box.width - 170)}px`;
    };
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerdown", move);
    hit.addEventListener("pointerleave", () => {
      tip.style.display = "none";
      cursor.style.display = "none";
    });
  }
}

class ChefOrchestreCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...(config || {}) };
    this._render();
  }
  set hass(hass) {
    this._hass = hass;
    this._render();
  }
  _render() {
    if (!this._hass || !this._config) return;
    const lang = (this._hass.locale?.language || "en").slice(0, 2);
    const t = (I18N[lang] || I18N.en).ed;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.schema = [
        { name: "name", selector: { text: {} } },
        { name: "show_chart", selector: { boolean: {} } },
        { name: "show_modes", selector: { boolean: {} } },
        { name: "show_settings", selector: { boolean: {} } },
        { name: "show_days", selector: { boolean: {} } },
      ];
      this._form.computeLabel = (s) => t[s.name] || s.name;
      this._form.addEventListener("value-changed", (ev) => {
        const cfg = { ...this._config, ...ev.detail.value };
        for (const k of Object.keys(cfg)) if (cfg[k] === "" || cfg[k] == null) delete cfg[k];
        this._config = cfg;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: cfg }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = { show_chart: true, show_modes: true, show_settings: true, show_days: true, ...this._config };
  }
}

const STYLE = `
  :host { display: block; --c-muted: var(--secondary-text-color); --c-panel: rgba(127,127,127,.12); --c-line: rgba(127,127,127,.22);
          --c-blue: #4a90d9; --c-teal: #26c6a8; --c-amber: #ffb300; --c-red: #ef5350; --c-orange: #ff9800; }
  ha-card { padding: 18px; display: flex; flex-direction: column; gap: 14px; overflow: hidden; container-type: inline-size;
    background: linear-gradient(160deg,
      color-mix(in srgb, var(--plan) 10%, var(--ha-card-background, var(--card-background-color))) 0%,
      var(--ha-card-background, var(--card-background-color)) 60%); }
  ha-card.empty { padding: 24px; color: var(--c-muted); text-align: center; }
  ha-icon { --mdc-icon-size: 18px; }
  button { font: inherit; color: inherit; cursor: pointer; }

  .head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .title { font-size: 1.15em; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .auto { display: flex; align-items: center; gap: 6px; padding: 5px 6px 5px 10px; border-radius: 999px; border: none;
          background: var(--c-panel); font-size: .8em; flex: none; }
  .auto i { width: 30px; height: 16px; border-radius: 8px; background: var(--c-line); position: relative; transition: background .2s; }
  .auto i::after { content: ""; position: absolute; top: 2px; left: 2px; width: 12px; height: 12px; border-radius: 50%;
                   background: #fff; transition: transform .2s; }
  .auto.on i { background: var(--c-teal); }
  .auto.on i::after { transform: translateX(14px); }
  .auto:not(.on) { color: var(--c-orange); }

  .plan { display: flex; align-items: center; gap: 14px; cursor: pointer; }
  .badge { width: 52px; height: 52px; border-radius: 16px; display: grid; place-items: center; flex: none;
           background: color-mix(in srgb, var(--plan) 20%, transparent); color: var(--plan); }
  .badge ha-icon { --mdc-icon-size: 30px; }
  .state { font-size: 1.45em; font-weight: 700; color: var(--plan); }
  .reason { color: var(--c-muted); font-size: .9em; margin-top: 2px; }

  .alert { display: flex; gap: 10px; align-items: flex-start; padding: 9px 12px; border-radius: 10px; font-size: .88em;
           background: color-mix(in srgb, var(--a) 14%, transparent); border-left: 3px solid var(--a); }
  .alert ha-icon { color: var(--a); flex: none; }
  .alert.crit { --a: var(--c-red); } .alert.warn { --a: var(--c-orange); } .alert.info { --a: var(--c-blue); }

  .tiles { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
  .tile { background: var(--c-panel); border-radius: 12px; padding: 10px 8px; display: flex; flex-direction: column;
          align-items: center; gap: 3px; cursor: pointer; text-align: center; min-width: 0; }
  .tile ha-icon { color: var(--c-muted); }
  .tile .v { font-weight: 700; font-size: 1.05em; white-space: nowrap; }
  .tile .l { color: var(--c-muted); font-size: .72em; line-height: 1.2; }
  .tile.dim .v { color: var(--c-muted); font-weight: 500; }

  .section { display: flex; flex-direction: column; gap: 8px; }
  .sec-title { font-size: .8em; text-transform: uppercase; letter-spacing: .06em; color: var(--c-muted); font-weight: 600; }

  .chart { position: relative; }
  .chart svg { width: 100%; height: auto; display: block; touch-action: pan-y; }
  .hc { fill: var(--c-blue); opacity: .12; }
  .grid { stroke: var(--c-line); stroke-width: .6; }
  .mid { stroke: var(--c-line); stroke-width: 1.2; stroke-dasharray: 3 3; }
  .tick, .ax { fill: var(--c-muted); font-size: 10px; text-anchor: middle; }
  .ax.l { text-anchor: end; } .ax.r { text-anchor: start; }
  .socA { fill: var(--c-teal); opacity: .18; }
  .socL { fill: none; stroke: var(--c-teal); stroke-width: 2; vector-effect: non-scaling-stroke; }
  .gc { stroke: var(--c-blue); stroke-width: 4; stroke-linecap: round; vector-effect: non-scaling-stroke; }
  .price { fill: none; stroke: var(--c-amber); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
  .now { stroke: var(--primary-text-color); stroke-width: 1; stroke-dasharray: 2 3; opacity: .6; vector-effect: non-scaling-stroke; }
  .cursor { stroke: var(--primary-text-color); stroke-width: 1; opacity: .5; vector-effect: non-scaling-stroke; }
  .tip { display: none; position: absolute; top: 6px; min-width: 150px; padding: 7px 10px; border-radius: 8px; font-size: .78em;
         line-height: 1.45; pointer-events: none; background: var(--ha-card-background, var(--card-background-color));
         border: 1px solid var(--c-line); box-shadow: 0 4px 14px rgba(0,0,0,.18); }

  .legend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: .76em; color: var(--c-muted); }
  .legend span { display: flex; align-items: center; gap: 5px; }
  .sw { display: inline-block; width: 12px; height: 8px; border-radius: 2px; }
  .sw.soc { background: var(--c-teal); } .sw.gc { background: var(--c-blue); }
  .sw.pr { background: var(--c-amber); height: 2px; } .sw.hc { background: var(--c-blue); opacity: .35; }

  .strip { display: flex; height: 16px; border-radius: 6px; overflow: hidden; }
  .strip div { min-width: 1px; }

  .settings { display: flex; flex-direction: column; gap: 10px; }
  .row { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
  .lbl { font-size: .9em; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .chip { border: 1px solid var(--c-line); background: none; border-radius: 999px; padding: 4px 12px; font-size: .82em; }
  .chip.sel { background: var(--c-teal); border-color: var(--c-teal); color: #fff; }
  .thr { display: flex; align-items: center; gap: 6px; font-size: .85em; color: var(--c-muted); }
  .thr input { width: 80px; padding: 5px 8px; border-radius: 8px; border: 1px solid var(--c-line); font: inherit;
               background: transparent; color: var(--primary-text-color); text-align: right; }
  .recalc { align-self: flex-start; display: flex; align-items: center; gap: 6px; background: none; border: none;
            color: var(--c-muted); font-size: .85em; padding: 2px 0; }
  .recalc:hover { color: var(--primary-text-color); }

  .ib { width: 17px; height: 17px; margin-left: 6px; border-radius: 50%; border: 1px solid currentColor; background: none;
        font-size: 11px; line-height: 15px; padding: 0; text-align: center; opacity: .6; vertical-align: middle; font-style: italic;
        text-transform: none; letter-spacing: 0; font-weight: 600; }
  .ib:hover { opacity: 1; }
  .help { display: none; font-size: .8em; line-height: 1.4; color: var(--c-muted); padding: 2px 4px; }
  .help.show { display: block; }
  .note { display: flex; gap: 8px; align-items: center; font-size: .88em; padding: 7px 10px; border-radius: 10px; background: var(--c-panel); }
  .note.ok { background: color-mix(in srgb, var(--c-teal) 14%, transparent); }
  .note ha-icon { flex: none; color: var(--c-muted); }
  .details { display: flex; flex-wrap: wrap; gap: 4px 16px; font-size: .8em; color: var(--c-muted); }
  .days { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .day { background: var(--c-panel); border-radius: 12px; padding: 10px 12px; display: flex; flex-direction: column; gap: 4px; cursor: pointer; min-width: 0; }
  .dhead { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
  .fc { font-size: .7em; padding: 1px 7px; border-radius: 999px; background: color-mix(in srgb, var(--c-blue) 22%, transparent); color: var(--c-blue); }
  .dper { font-size: .78em; color: var(--c-muted); }
  .dstrip { position: relative; height: 8px; border-radius: 4px; overflow: hidden; background: var(--c-line); margin: 2px 0 4px; }
  .dstrip div { position: absolute; top: 0; bottom: 0; }
  .dl { display: flex; gap: 6px; align-items: flex-start; font-size: .8em; }
  .dl ha-icon { --mdc-icon-size: 15px; color: var(--c-muted); flex: none; margin-top: 1px; }
  #daytime { padding: 3px 6px; border-radius: 8px; border: 1px solid var(--c-line); font: inherit; font-size: .82em;
             background: transparent; color: var(--primary-text-color); }

  @container (max-width: 460px) {
    .tiles { grid-template-columns: repeat(3, 1fr); }
    .auto span { display: none; }
    .days { grid-template-columns: 1fr; }
  }
`;

if (!customElements.get("chef-orchestre-card")) {
  customElements.define("chef-orchestre-card", ChefOrchestreCard);
  customElements.define("chef-orchestre-card-editor", ChefOrchestreCardEditor);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "chef-orchestre-card",
    name: "Chef d'orchestre énergie",
    description: "Plan de la nuit, prévision des 48 h et réglages du pilotage des batteries",
    preview: true,
    documentationURL: "https://github.com/JVmaisGpeur/ha-chef-orchestre-energie",
  });
  console.info(`%c CHEF-ORCHESTRE-CARD %c v${CARD_VERSION} `, "background:#4a90d9;color:#fff", "");
}
