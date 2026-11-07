/**
 * NextEnergy price card: today's / tomorrow's hourly prices from the NextEnergy integration.
 *
 *   type: custom:nextenergy-price-card
 *   entity: sensor.nextenergy_current_price   # optional
 *   decimals: 2                                # optional, decimals of hourly prices
 */

const DEFAULT_ENTITY = "sensor.nextenergy_current_price";

// Relative to the day's average price.
const CHEAP_BELOW = -0.1;
const EXPENSIVE_ABOVE = 0.05;

const STYLE = `
  :host {
    --ne-text: #16301f;
    --ne-muted: #5f6661;
    --ne-subtle: #f4f6f3;
    --ne-line: #e6e8e4;
    --ne-bar: #f1ca7d;
    --ne-bar-expensive: #e2a63e;
    --ne-bar-cheap: #9fd0a6;
    --ne-badge: #f1ca7d;
    --ne-badge-expensive: #e2a63e;
    --ne-badge-cheap: #cbe8cf;
    --ne-tab-bg: #f4f6f3;
    --ne-tab-active: #ffffff;
  }
  :host([dark]) {
    --ne-text: var(--primary-text-color, #e8ece9);
    --ne-muted: var(--secondary-text-color, #a3aaa5);
    --ne-subtle: rgba(255, 255, 255, 0.05);
    --ne-line: var(--divider-color, rgba(255, 255, 255, 0.12));
    --ne-tab-bg: rgba(255, 255, 255, 0.06);
    --ne-tab-active: rgba(255, 255, 255, 0.16);
  }
  ha-card { padding: 28px; color: var(--ne-text); }
  .top { display: flex; justify-content: flex-end; }
  .tabs { display: inline-flex; padding: 4px; border-radius: 999px; background: var(--ne-tab-bg); }
  .tab {
    border: 0; background: none; font: inherit; font-size: 15px; color: var(--ne-muted);
    padding: 8px 18px; border-radius: 999px; cursor: pointer;
  }
  .tab[aria-selected="true"] {
    background: var(--ne-tab-active); color: var(--ne-text); font-weight: 500;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  }
  .tab:disabled { cursor: default; opacity: 0.7; }
  .hour {
    text-align: right; margin-top: 12px; font-size: 13px; letter-spacing: 0.08em;
    color: var(--ne-muted); font-variant-numeric: tabular-nums;
  }
  .headline { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 16px; margin-top: 4px; }
  .price {
    font-size: clamp(42px, 10vw, 64px); font-weight: 500; letter-spacing: -0.02em; line-height: 1.1;
    font-variant-numeric: tabular-nums;
  }
  .unit { font-size: 0.42em; font-weight: 400; color: var(--ne-muted); letter-spacing: 0; margin-left: 4px; }
  .meta { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 20px; margin-top: 10px; }
  .badge {
    font-size: 14px; font-weight: 500; padding: 6px 14px; border-radius: 999px; background: var(--ne-badge);
    color: #16301f; white-space: nowrap;
  }
  .badge.expensive { background: var(--ne-badge-expensive); }
  .badge.cheap { background: var(--ne-badge-cheap); }
  .chart {
    display: flex; align-items: flex-end; gap: 4px; height: 190px; margin-top: 28px; touch-action: pan-y;
  }
  .bar {
    flex: 1; min-width: 0; height: var(--h); background: var(--ne-bar); border-radius: 2px; cursor: pointer;
    position: relative; box-sizing: border-box; transition: filter 0.15s;
  }
  .bar.expensive { background: var(--ne-bar-expensive); }
  .bar.cheap { background: var(--ne-bar-cheap); }
  .bar.selected::after {
    content: ""; position: absolute; inset: -3px; border: 2.5px solid var(--ne-text); border-radius: 6px;
  }
  .stats {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 28px; padding-top: 24px;
    border-top: 1px solid var(--ne-line);
  }
  .label { font-size: 12px; letter-spacing: 0.08em; color: var(--ne-muted); text-transform: uppercase; }
  .value { margin-top: 8px; font-size: 20px; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .value small { font-size: 15px; color: var(--ne-muted); }
  .footer {
    display: flex; align-items: center; gap: 28px; margin-top: 20px; padding: 18px 24px; border-radius: 14px;
    background: var(--ne-subtle); width: 100%; box-sizing: border-box; border: 0; font: inherit;
    color: inherit; text-align: left;
  }
  button.footer { cursor: pointer; }
  .footer .text { font-size: 16px; color: var(--ne-muted); font-style: italic; }
  .footer .text.data { font-style: normal; color: var(--ne-text); font-variant-numeric: tabular-nums; }
  .empty { padding: 24px 0; color: var(--ne-muted); }
  @media (max-width: 420px) {
    ha-card { padding: 20px; }
    .stats { grid-template-columns: 1fr 1fr; }
    .value { font-size: 17px; }
    .chart { gap: 2px; height: 150px; }
  }
`;

class NextEnergyPriceCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._day = "today";
    this._picked = null; // {day, start} chosen by tap
    this._hover = null; // index under the pointer
    this._renderKey = null;
  }

  static getStubConfig() {
    return { entity: DEFAULT_ENTITY };
  }

  setConfig(config) {
    this._config = { entity: DEFAULT_ENTITY, decimals: 2, ...config };
    this._renderKey = null;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const state = hass.states[this._config.entity];
    // Re-render only when the prices or the hour change.
    const key = [state?.last_updated, state?.state, new Date().getHours(), hass.themes?.darkMode].join("|");
    if (key !== this._renderKey) {
      this._renderKey = key;
      this._render();
    }
  }

  getCardSize() {
    return 7;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  // --- data ---------------------------------------------------------------

  _prices(day) {
    const attrs = this._hass.states[this._config.entity]?.attributes || {};
    return (attrs[day === "today" ? "raw_today" : "raw_tomorrow"] || []).map((p) => ({
      start: new Date(p.start),
      value: Number(p.value),
    }));
  }

  _currentIndex(prices) {
    const now = Date.now();
    return prices.findIndex((p) => p.start.getTime() <= now && now < p.start.getTime() + 3600e3);
  }

  _selectedIndex(prices) {
    if (this._hover !== null && this._hover < prices.length) return this._hover;
    if (this._picked && this._picked.day === this._day) {
      const index = prices.findIndex((p) => p.start.getTime() === this._picked.start);
      if (index >= 0) return index;
    }
    const current = this._day === "today" ? this._currentIndex(prices) : -1;
    if (current >= 0) return current;
    // Tomorrow: start at the cheapest hour.
    return prices.reduce((best, p, i) => (p.value < prices[best].value ? i : best), 0);
  }

  _summary(prices) {
    const average = prices.reduce((sum, p) => sum + p.value, 0) / prices.length;
    const min = prices.reduce((a, b) => (b.value < a.value ? b : a));
    const max = prices.reduce((a, b) => (b.value > a.value ? b : a));
    return { average, min, max };
  }

  _level(value, average) {
    const delta = (value - average) / average;
    if (delta < CHEAP_BELOW) return "cheap";
    if (delta > EXPENSIVE_ABOVE) return "expensive";
    return "average";
  }

  // --- formatting ---------------------------------------------------------

  _euro(value, decimals = this._config.decimals) {
    return `€ ${value.toLocaleString("nl-NL", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
  }

  _time(date) {
    return date.toLocaleTimeString("nl-NL", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: this._hass.config?.time_zone,
    });
  }

  _percent(fraction) {
    const text = Math.abs(fraction * 100).toLocaleString("nl-NL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    return `${fraction < 0 ? "−" : "+"}${text}%`;
  }

  // --- rendering ----------------------------------------------------------

  _render() {
    if (!this._config || !this._hass) return;
    this.toggleAttribute("dark", Boolean(this._hass.themes?.darkMode));

    const state = this._hass.states[this._config.entity];
    const today = this._prices("today");
    const tomorrow = this._prices("tomorrow");
    if (this._day === "tomorrow" && !tomorrow.length) this._day = "today";
    const prices = this._day === "today" ? today : tomorrow;

    if (!state || !prices.length) {
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><div class="empty">${
        state ? "Nog geen prijzen beschikbaar." : `Entiteit ${this._config.entity} niet gevonden.`
      }</div></ha-card>`;
      return;
    }

    const index = this._selectedIndex(prices);
    const selected = prices[index];
    const { average, min, max } = this._summary(prices);
    const level = this._level(selected.value, average);
    const levelText = { cheap: "goedkoop", average: "gemiddeld", expensive: "duur" }[level];
    const current = this._day === "today" ? this._currentIndex(prices) : -1;
    const dayWord = this._day === "today" ? "vandaag" : "morgen";

    const top = Math.max(...prices.map((p) => p.value));
    const bottom = Math.min(0, ...prices.map((p) => p.value));
    const bars = prices
      .map((p, i) => {
        const height = 12 + (88 * (p.value - bottom)) / (top - bottom || 1);
        const classes = ["bar", this._level(p.value, average)];
        if (i === index) classes.push("selected");
        return `<div class="${classes.join(" ")}" style="--h:${height.toFixed(1)}%" data-index="${i}"
          role="button" tabindex="-1" aria-label="${this._time(p.start)} ${this._euro(p.value)}"></div>`;
      })
      .join("");

    let footer;
    if (this._day === "today" && !tomorrow.length) {
      footer = `<div class="footer"><span class="label">Morgen</span>
        <span class="text">Wordt rond 13:00 gepubliceerd</span></div>`;
    } else {
      const other = this._day === "today" ? tomorrow : today;
      const s = this._summary(other);
      footer = `<button class="footer" data-day="${this._day === "today" ? "tomorrow" : "today"}">
        <span class="label">${this._day === "today" ? "Morgen" : "Vandaag"}</span>
        <span class="text data">gem. ${this._euro(s.average, 3)} · goedkoopst ${this._euro(s.min.value)} om ${this._time(s.min.start)} ›</span>
      </button>`;
    }

    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="top">
          <div class="tabs" role="tablist">
            <button class="tab" role="tab" data-day="today" aria-selected="${this._day === "today"}">Vandaag</button>
            <button class="tab" role="tab" data-day="tomorrow" aria-selected="${this._day === "tomorrow"}"
              ${tomorrow.length ? "" : "disabled title='Wordt rond 13:00 gepubliceerd'"}>Morgen</button>
          </div>
        </div>
        <div class="hour">UUR ${this._time(selected.start)}</div>
        <div class="headline">
          <div class="price">${this._euro(selected.value)}<span class="unit">/kWh</span></div>
        </div>
        <div class="meta">
          <span class="badge ${level}">${levelText} · ${this._percent((selected.value - average) / average)} vs dag-gem.</span>
        </div>
        <div class="chart">${bars}</div>
        <div class="stats">
          <div><div class="label">Dag-gemiddelde</div><div class="value">${this._euro(average, 3)}</div></div>
          <div><div class="label">Goedkoopst ${dayWord}</div>
            <div class="value">${this._euro(min.value)} <small>· ${this._time(min.start)}</small></div></div>
          <div><div class="label">Duurst ${dayWord}</div>
            <div class="value">${this._euro(max.value)} <small>· ${this._time(max.start)}</small></div></div>
        </div>
        ${footer}
      </ha-card>`;

    this._bind(prices);
  }

  _bind(prices) {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-day]").forEach((el) =>
      el.addEventListener("click", () => {
        this._day = el.dataset.day;
        this._picked = null;
        this._hover = null;
        this._render();
      })
    );

    const chart = root.querySelector(".chart");
    const indexAt = (event) => {
      const bar = event.target.closest?.(".bar");
      return bar ? Number(bar.dataset.index) : null;
    };
    chart.addEventListener("pointerover", (event) => {
      if (event.pointerType !== "mouse") return;
      const i = indexAt(event);
      if (i !== null && i !== this._hover) {
        this._hover = i;
        this._render();
      }
    });
    chart.addEventListener("pointerleave", () => {
      if (this._hover !== null) {
        this._hover = null;
        this._render();
      }
    });
    chart.addEventListener("click", (event) => {
      const i = indexAt(event);
      if (i === null) return;
      this._picked = { day: this._day, start: prices[i].start.getTime() };
      this._hover = null;
      this._render();
    });
  }
}

customElements.define("nextenergy-price-card", NextEnergyPriceCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "nextenergy-price-card",
  name: "NextEnergy prijzen",
  description: "Uurprijzen van vandaag en morgen van NextEnergy.",
  preview: true,
});
