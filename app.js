"use strict";

const SERIES_COLORS = ["#1f3a5f", "#e85d04"];
const FONT = "system-ui, Segoe UI, sans-serif";

const state = { game: null, trend: null };
let data = null;

function esc(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatAvg(value) {
  return Number(value).toFixed(1).replace(".", ",");
}

function formatPlain(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return esc(value);
  if (Number.isInteger(number)) return String(number);
  return formatAvg(number);
}

function formatCell(value, average) {
  if (average) return esc(formatAvg(value));
  if (typeof value === "number") return formatPlain(value);
  return esc(value);
}

function safeUrl(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.href;
  } catch (error) {
    return "";
  }
  return "";
}

function heading(id) {
  const item = data.nav.find((entry) => entry.id === id);
  return item ? item.label : id;
}

function objectTable(columns, rows) {
  const head = columns.map((column) => `<th scope="col">${esc(column.label)}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map((column) => `<td>${formatCell(row[column.key], column.average)}</td>`)
        .join("");
      return `<tr class="${row.highlight ? "highlight" : ""}">${cells}</tr>`;
    })
    .join("");
  return `<div class="table-scroll"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function arrayTable(columns, rows) {
  const head = columns.map((column) => `<th scope="col">${esc(column)}</th>`).join("");
  const body = rows
    .map((row) => `<tr>${row.map((cell) => `<td>${esc(cell)}</td>`).join("")}</tr>`)
    .join("");
  return `<div class="table-scroll"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function paragraphs(list) {
  if (!list || !list.length) return "";
  return `<div class="prose">${list.map((text) => `<p>${esc(text)}</p>`).join("")}</div>`;
}

function facts(items) {
  const cards = items
    .map(
      (item) =>
        `<div class="fact"><dt>${esc(item.label)}</dt><dd>${esc(item.value)}</dd></div>`
    )
    .join("");
  return `<dl class="facts">${cards}</dl>`;
}

function axisMax(value) {
  if (!Number.isFinite(value) || value <= 1) return 1;
  if (value <= 5) return Math.ceil(value);
  if (value <= 10) return Math.ceil(value);
  return Math.ceil(value / 2) * 2;
}

function tickStep(top) {
  if (top <= 6) return 1;
  if (top <= 12) return 2;
  return Math.ceil(top / 5);
}

function formatTick(value) {
  if (Number.isInteger(value)) return String(value);
  return formatAvg(value);
}

function chartFrame(className, width, height, body, label) {
  return `<div class="chart-scroll"><svg class="${className}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}">${body}</svg></div>`;
}

function pointsChart(tournament) {
  const chart = tournament.chart;
  if (!chart) return "";
  const points = tournament.rows.map((row) => {
    const rawLabel = String(row[chart.labelKey] ?? "");
    const prefix = chart.labelPrefix;
    const label = prefix ? rawLabel.slice(0, prefix) : rawLabel;
    const value = Number(row[chart.valueKey]);
    return {
      label,
      value: Number.isFinite(value) ? value : 0,
      display: formatPlain(row[chart.valueKey]),
    };
  });
  const width = Math.max(640, 56 + points.length * 62);
  const height = 268;
  const pad = { top: 28, right: 16, bottom: 40, left: 40 };
  const plotH = height - pad.top - pad.bottom;
  const plotW = width - pad.left - pad.right;
  const top = axisMax(Math.max(...points.map((point) => point.value), 0));
  const step = tickStep(top);
  const slot = plotW / points.length;
  let shapes = "";

  for (let tick = 0; tick <= top + 0.001; tick += step) {
    const y = pad.top + plotH - (tick / top) * plotH;
    const grid = tick === 0 ? "#d9d1c7" : "#eee6dc";
    shapes += `<line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" stroke="${grid}"></line>`;
    shapes += `<text x="${pad.left - 8}" y="${y + 4}" text-anchor="end" fill="#5c6775" font-size="12" font-family="${FONT}">${formatTick(tick)}</text>`;
  }

  points.forEach((point, index) => {
    const barH = top === 0 ? 0 : (point.value / top) * plotH;
    const barW = Math.min(32, slot - 18);
    const x = pad.left + index * slot + (slot - barW) / 2;
    const y = pad.top + plotH - barH;
    if (barH > 0) {
      const radius = Math.min(5, barW / 2, barH);
      shapes += `<path d="M${x} ${y + barH} V${y + radius} Q${x} ${y} ${x + radius} ${y} H${x + barW - radius} Q${x + barW} ${y} ${x + barW} ${y + radius} V${y + barH} Z" fill="#e85d04"></path>`;
    }
    shapes += `<text x="${x + barW / 2}" y="${Math.max(14, y - 6)}" text-anchor="middle" fill="#142033" font-size="12" font-weight="700" font-family="${FONT}">${esc(point.display)}</text>`;
    shapes += `<text x="${x + barW / 2}" y="${height - 14}" text-anchor="middle" fill="#5c6775" font-size="12" font-family="${FONT}">${esc(point.label)}</text>`;
  });

  const summary = points.map((point) => `${point.label}: ${point.display}`).join(", ");
  return chartFrame("points", width, height, shapes, `Очки по играм. ${summary}`);
}

function groupedChart(view) {
  const width = 720;
  const height = 300;
  const pad = { top: 32, right: 16, bottom: 46, left: 42 };
  const plotH = height - pad.top - pad.bottom;
  const plotW = width - pad.left - pad.right;
  const categories = view.categories;
  const series = view.series;
  const maxValue = Math.max(...series.flatMap((item) => item.values), 0);
  const top = axisMax(maxValue);
  const step = tickStep(top);
  const groupW = plotW / categories.length;
  const barW = Math.min(28, (groupW - 24) / series.length);
  let shapes = "";

  for (let tick = 0; tick <= top + 0.001; tick += step) {
    const y = pad.top + plotH - (tick / top) * plotH;
    const grid = tick === 0 ? "#d9d1c7" : "#eee6dc";
    shapes += `<line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" stroke="${grid}"></line>`;
    shapes += `<text x="${pad.left - 8}" y="${y + 4}" text-anchor="end" fill="#5c6775" font-size="12" font-family="${FONT}">${formatTick(tick)}</text>`;
  }

  categories.forEach((category, categoryIndex) => {
    const groupX = pad.left + categoryIndex * groupW;
    const barsWidth = series.length * barW + (series.length - 1) * 8;
    const start = groupX + (groupW - barsWidth) / 2;
    series.forEach((item, seriesIndex) => {
      const value = Number(item.values[categoryIndex]);
      const safe = Number.isFinite(value) ? value : 0;
      const barH = top === 0 ? 0 : (safe / top) * plotH;
      const x = start + seriesIndex * (barW + 8);
      const y = pad.top + plotH - barH;
      const color = SERIES_COLORS[seriesIndex % SERIES_COLORS.length];
      if (barH > 0) {
        const radius = Math.min(5, barW / 2, barH);
        shapes += `<path d="M${x} ${y + barH} V${y + radius} Q${x} ${y} ${x + radius} ${y} H${x + barW - radius} Q${x + barW} ${y} ${x + barW} ${y + radius} V${y + barH} Z" fill="${color}"></path>`;
      }
      shapes += `<text x="${x + barW / 2}" y="${Math.max(14, y - 6)}" text-anchor="middle" fill="#142033" font-size="11" font-weight="700" font-family="${FONT}">${formatAvg(safe)}</text>`;
    });
    shapes += `<text x="${groupX + groupW / 2}" y="${height - 16}" text-anchor="middle" fill="#142033" font-size="13" font-family="${FONT}">${esc(category)}</text>`;
  });

  const summary = series
    .map((item) => `${item.name}: ${item.values.map((value) => formatAvg(value)).join(", ")}`)
    .join(". ");
  const legend = `<ul class="legend">${series
    .map(
      (item, index) =>
        `<li><span class="swatch" style="background:${SERIES_COLORS[index % SERIES_COLORS.length]}"></span>${esc(item.name)}</li>`
    )
    .join("")}</ul>`;
  const hidden = `<table class="sr-only"><caption>${esc(view.label)}</caption><thead><tr><th>Показатель</th>${series
    .map((item) => `<th>${esc(item.name)}</th>`)
    .join("")}</tr></thead><tbody>${categories
    .map(
      (category, index) =>
        `<tr><th scope="row">${esc(category)}</th>${series
          .map((item) => `<td>${formatAvg(item.values[index])}</td>`)
          .join("")}</tr>`
    )
    .join("")}</tbody></table>`;
  return `${legend}${chartFrame("groups", width, height, shapes, `${view.label}. ${categories.join(", ")}. ${summary}`)}${hidden}`;
}

function segmented(options, current, attr, label) {
  const buttons = options
    .map(
      (option) =>
        `<button type="button" aria-pressed="${option.id === current}" data-${attr}="${esc(option.id)}">${esc(option.label)}</button>`
    )
    .join("");
  return `<div class="segmented" role="group" aria-label="${esc(label)}">${buttons}</div>`;
}

function renderNav() {
  document.getElementById("nav").innerHTML = data.nav
    .map((item) => `<a href="#${esc(item.id)}">${esc(item.label)}</a>`)
    .join("");
}

function renderHero() {
  const player = data.player;
  return `<section class="hero" id="top">
    <h1>${esc(player.name)}</h1>
    <p class="hero-meta"><span class="chip">${esc(player.team)}</span><span class="pos">${esc(player.position)}</span></p>
    <p class="summary">${esc(player.summary)}</p>
  </section>`;
}

function renderLast() {
  const block = data.lastMatch;
  return `<section class="block" id="last">
    <h2>${esc(heading("last"))}</h2>
    <p class="caption">${esc(block.caption)}</p>
    ${facts(block.facts)}
    ${arrayTable(block.columns, block.rows)}
    ${paragraphs(block.paragraphs)}
  </section>`;
}

function renderProfile() {
  const block = data.profile;
  return `<section class="block" id="profile">
    <h2>${esc(heading("profile"))}</h2>
    ${facts(block.items)}
    ${paragraphs(block.paragraphs)}
  </section>`;
}

function renderSeason() {
  const block = data.season;
  const matches = block.matches
    .map(
      (match) => `<article class="match-row">
        <div>
          <h3>${esc(match.title)}</h3>
          <p>${esc(match.detail)}</p>
        </div>
        ${match.status ? `<span class="status">${esc(match.status)}</span>` : ""}
      </article>`
    )
    .join("");
  return `<section class="block" id="season">
    <h2>${esc(heading("season"))}</h2>
    <p class="caption">${esc(block.caption)}</p>
    <div class="match-list">${matches}</div>
    ${objectTable(block.standings.columns, block.standings.rows)}
  </section>`;
}

function renderStats() {
  const block = data.tournamentStats;
  return `<section class="block" id="stats">
    <h2>${esc(heading("stats"))}</h2>
    <p class="caption">${esc(block.caption)}</p>
    ${objectTable(block.averageColumns, block.seasons)}
    ${objectTable(block.shootingColumns, block.seasons)}
    ${paragraphs(block.paragraphs)}
  </section>`;
}

function renderGamesSection() {
  return `<section class="block" id="games">
    <h2>${esc(heading("games"))}</h2>
    <div id="game-panel"></div>
  </section>`;
}

function renderTrendSection() {
  const block = data.trend;
  return `<section class="block" id="trend">
    <h2>${esc(heading("trend"))}</h2>
    <p class="caption">${esc(block.caption)}</p>
    <div id="trend-panel"></div>
  </section>`;
}

function renderNotes() {
  const block = data.notes;
  const list = (items) => items.map((item) => `<li>${esc(item)}</li>`).join("");
  return `<section class="block" id="notes">
    <h2>${esc(heading("notes"))}</h2>
    <div class="split">
      <section class="panel good">
        <h3>${esc(block.prosHeading)}</h3>
        <ul>${list(block.pros)}</ul>
      </section>
      <section class="panel work">
        <h3>${esc(block.consHeading)}</h3>
        <ul>${list(block.cons)}</ul>
      </section>
    </div>
    <aside class="callout">
      <p class="callout-lead">${esc(block.conclusionLead)}</p>
      <p>${esc(block.conclusion)}</p>
    </aside>
  </section>`;
}

function renderSources() {
  const cards = data.sources.links
    .map((link) => {
      const href = safeUrl(link.href);
      const body = `<strong>${esc(link.title)}</strong><span>${esc(link.site)}</span>`;
      if (!href) return `<div class="source-card">${body}</div>`;
      return `<a class="source-card" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${body}</a>`;
    })
    .join("");
  return `<section class="block" id="sources">
    <h2>${esc(heading("sources"))}</h2>
    <div class="sources">${cards}</div>
  </section>`;
}

function renderGamePanel(restoreFocus) {
  const tournament =
    data.gameLogs.tournaments.find((item) => item.id === state.game) ||
    data.gameLogs.tournaments[0];
  state.game = tournament.id;
  document.getElementById("game-panel").innerHTML = `${segmented(
    data.gameLogs.tournaments,
    state.game,
    "game",
    "Турнир"
  )}${pointsChart(tournament)}${objectTable(tournament.columns, tournament.rows)}`;
  if (restoreFocus) {
    const button = document.querySelector(`[data-game="${CSS.escape(state.game)}"]`);
    if (button) button.focus();
  }
}

function renderTrendPanel(restoreFocus) {
  const view = data.trend.views.find((item) => item.id === state.trend) || data.trend.views[0];
  state.trend = view.id;
  document.getElementById("trend-panel").innerHTML = `${segmented(
    data.trend.views,
    state.trend,
    "trend",
    "Показатель"
  )}${groupedChart(view)}`;
  if (restoreFocus) {
    const button = document.querySelector(`[data-trend="${CSS.escape(state.trend)}"]`);
    if (button) button.focus();
  }
}

function render() {
  document.title = `${data.player.name} — профиль игрока`;
  document.getElementById("brand-name").textContent = data.player.name;
  renderNav();
  document.getElementById("app").innerHTML = [
    renderHero(),
    renderLast(),
    renderProfile(),
    renderSeason(),
    renderStats(),
    renderGamesSection(),
    renderTrendSection(),
    renderNotes(),
    renderSources(),
  ].join("");
  renderGamePanel(false);
  renderTrendPanel(false);
  document.getElementById("load-state").hidden = true;
  document.getElementById("app").hidden = false;
  updateActiveNav();
  scrollToHash();
}

function updateActiveNav() {
  if (!data) return;
  const offset = 78;
  let current = data.nav[0].id;
  data.nav.forEach((item) => {
    const section = document.getElementById(item.id);
    if (section && section.getBoundingClientRect().top <= offset) current = item.id;
  });
  document.querySelectorAll("#nav a").forEach((link) => {
    link.classList.toggle("active", link.getAttribute("href") === `#${current}`);
  });
}

function scrollToHash() {
  const hash = location.hash;
  if (!hash || hash.length > 40) return;
  let id = "";
  try {
    id = decodeURIComponent(hash.slice(1));
  } catch (error) {
    return;
  }
  if (!/^[a-z0-9-]+$/i.test(id)) return;
  const node = document.getElementById(id);
  if (node) node.scrollIntoView();
}

document.addEventListener("click", (event) => {
  const gameButton = event.target.closest("[data-game]");
  if (gameButton) {
    state.game = gameButton.getAttribute("data-game");
    renderGamePanel(true);
    return;
  }
  const trendButton = event.target.closest("[data-trend]");
  if (trendButton) {
    state.trend = trendButton.getAttribute("data-trend");
    renderTrendPanel(true);
  }
});

document.addEventListener("scroll", updateActiveNav, { passive: true });

async function init() {
  const status = document.getElementById("load-state");
  try {
    const response = await fetch("data.json");
    if (!response.ok) throw new Error(String(response.status));
    data = await response.json();
    state.game = data.gameLogs.defaultId;
    state.trend = data.trend.defaultId;
    render();
  } catch (error) {
    status.hidden = false;
    status.classList.add("error");
    status.textContent =
      "Не удалось загрузить data.json. Откройте страницу через GitHub Pages или локальный HTTP-сервер.";
  }
}

init();
