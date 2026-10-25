"use strict";

const SERIES_COLORS = ["#b7beca", "#e8b84a"];
const FONT = "Oswald, sans-serif";

const state = { game: null, trend: null, news: "all" };
let data = null;
let newsData = null;

const MONTHS = [
  "января",
  "февраля",
  "марта",
  "апреля",
  "мая",
  "июня",
  "июля",
  "августа",
  "сентября",
  "октября",
  "ноября",
  "декабря",
];

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
  return `<div class="chart-scroll"><svg class="${className}" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}">${body}</svg></div>`;
}

function boxWidth(el, max) {
  if (!el || el.clientWidth < 40) return Math.min(max, 320);
  const style = getComputedStyle(el);
  const pad = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
  return Math.max(240, Math.min(max, Math.floor(el.clientWidth - pad)));
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
  const host = document.getElementById("game-panel");
  const width = boxWidth(host, 1040);
  const height = 240;
  const pad = { top: 26, right: 8, bottom: 32, left: 28 };
  const plotH = height - pad.top - pad.bottom;
  const plotW = width - pad.left - pad.right;
  const top = axisMax(Math.max(...points.map((point) => point.value), 0));
  const step = tickStep(top);
  const slot = plotW / points.length;
  let shapes = "";

  for (let tick = 0; tick <= top + 0.001; tick += step) {
    const y = pad.top + plotH - (tick / top) * plotH;
    const grid = tick === 0 ? "#3a3f4b" : "#2c313c";
    shapes += `<line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" stroke="${grid}"></line>`;
    shapes += `<text x="${pad.left - 6}" y="${y + 4}" text-anchor="end" fill="#c8c2b6" font-size="12" font-family="${FONT}">${formatTick(tick)}</text>`;
  }

  const showEvery = slot < 36 ? 2 : 1;
  points.forEach((point, index) => {
    const barH = top === 0 ? 0 : (point.value / top) * plotH;
    const barW = Math.max(6, Math.min(28, slot - 10));
    const x = pad.left + index * slot + (slot - barW) / 2;
    const y = pad.top + plotH - barH;
    if (barH > 0) {
      const radius = Math.min(4, barW / 2, barH);
      shapes += `<path d="M${x} ${y + barH} V${y + radius} Q${x} ${y} ${x + radius} ${y} H${x + barW - radius} Q${x + barW} ${y} ${x + barW} ${y + radius} V${y + barH} Z" fill="#e8b84a"></path>`;
    }
    shapes += `<text x="${x + barW / 2}" y="${Math.max(14, y - 5)}" text-anchor="middle" fill="#f4efe4" font-size="13" font-weight="700" font-family="${FONT}">${esc(point.display)}</text>`;
    if (index % showEvery === 0) {
      shapes += `<text x="${x + barW / 2}" y="${height - 10}" text-anchor="middle" fill="#c8c2b6" font-size="12" font-family="${FONT}">${esc(point.label)}</text>`;
    }
  });

  const summary = points.map((point) => `${point.label}: ${point.display}`).join(", ");
  return chartFrame("points", width, height, shapes, `Очки по играм. ${summary}`);
}

function groupedChart(view) {
  const host = document.getElementById("trend-panel") || document.getElementById("trend");
  const width = boxWidth(host, 560);
  const height = 260;
  const pad = { top: 24, right: 8, bottom: 36, left: 32 };
  const valueSize = 13;
  const labelSize = width < 420 ? 12 : 14;
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
    const grid = tick === 0 ? "#3a3f4b" : "#2c313c";
    shapes += `<line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" stroke="${grid}"></line>`;
    shapes += `<text x="${pad.left - 8}" y="${y + 4}" text-anchor="end" fill="#c8c2b6" font-size="12" font-family="${FONT}">${formatTick(tick)}</text>`;
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
      shapes += `<text x="${x + barW / 2}" y="${Math.max(12, y - 6)}" text-anchor="middle" fill="#f4efe4" font-size="${valueSize}" font-weight="700" font-family="${FONT}">${formatAvg(safe)}</text>`;
    });
    shapes += `<text x="${groupX + groupW / 2}" y="${height - 14}" text-anchor="middle" fill="#f4efe4" font-size="${labelSize}" font-family="${FONT}">${esc(category)}</text>`;
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
  const heads = series.map((item) => `<th>${esc(item.name)}</th>`).join("");
  const body = categories
    .map((category, index) => {
      const cells = series.map((item) => `<td>${formatAvg(item.values[index])}</td>`).join("");
      return `<tr><th scope="row">${esc(category)}</th>${cells}</tr>`;
    })
    .join("");
  const hidden = `<div class="sr-only"><table><caption>${esc(view.label)}</caption><thead><tr><th>Показатель</th>${heads}</tr></thead><tbody>${body}</tbody></table></div>`;
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

function profileValue(label) {
  const item = data.profile.items.find((entry) => entry.label === label);
  return item ? item.value : "";
}

function firstNumber(text) {
  const match = String(text).match(/\d+/);
  return match ? match[0] : "";
}

function ruCount(value, one, few, many) {
  const n = Math.abs(Number(value));
  const n10 = n % 10;
  const n100 = n % 100;
  const word = n10 === 1 && n100 !== 11 ? one : n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14) ? few : many;
  return `${value} ${word}`;
}

function fullDate(short) {
  const match = String(short).match(/^(\d{2})\.(\d{2})\.(\d{2})$/);
  return match ? `${match[1]}.${match[2]}.20${match[3]}` : String(short);
}

function formatNewsDate(iso) {
  const match = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return String(iso);
  const month = MONTHS[Number(match[2]) - 1];
  return month ? `${Number(match[3])} ${month} ${match[1]}` : String(iso);
}

function findLogRow(date) {
  for (const tournament of data.gameLogs.tournaments) {
    const row = tournament.rows.find((item) => item.date === date);
    if (row) return row;
  }
  return null;
}

function mamaFacts(row) {
  const score = String(row.score);
  const result = score.includes("победа") ? "Победа" : score.includes("поражение") ? "Поражение" : "Счёт";
  const clean = score.replace(/,\s*победа|,\s*поражение/g, "");
  const bits = [ruCount(row.points, "очко", "очка", "очков")];
  const shots = String(row.fg2 || "").match(/(\d+)\s*\/\s*(\d+)/);
  if (shots) {
    const total = Number(shots[2]);
    const n10 = total % 10;
    const n100 = total % 100;
    const word = n10 === 1 && n100 !== 11 ? "двухочкового" : "двухочковых";
    bits.push(`${shots[1]} из ${shots[2]} ${word}`);
  }
  if (row.rebounds != null) bits.push(ruCount(row.rebounds, "подбор", "подбора", "подборов"));
  if (row.assists != null) bits.push(ruCount(row.assists, "передача", "передачи", "передач"));
  if (row.steals != null) bits.push(ruCount(row.steals, "перехват", "перехвата", "перехватов"));
  if (row.turnovers != null) bits.push(ruCount(row.turnovers, "потеря", "потери", "потерь"));
  const minutes = row.minutes ? ` На площадке ${row.minutes}.` : "";
  return `${result} ${clean}.${minutes} ${bits.join(", ")}.`;
}

function renderNav() {
  const nav = document.getElementById("nav");
  if (!nav) return;
  if (document.body.dataset.page !== "profile") {
    nav.hidden = true;
    return;
  }
  nav.hidden = false;
  nav.innerHTML = data.nav
    .map((item) => `<a href="#${esc(item.id)}">${esc(item.label)}</a>`)
    .join("");
}

function renderHero() {
  const player = data.player;
  const height = firstNumber(profileValue("Рост и вес"));
  const year = profileValue("Год рождения");
  const shield = height
    ? `<div class="shield"><strong>${esc(height)}</strong><em>рост, см</em></div>`
    : "";
  return `<section class="player-card" id="top">
    <p class="kicker">Карточка игрока${year ? ` · ${esc(year)}` : ""}</p>
    <div class="player-card-main">
      ${shield}
      <div class="player-card-copy">
        <h1>${esc(player.name)}</h1>
        <p class="hero-meta"><span class="chip">${esc(player.team)}</span><span class="pos">${esc(player.position)}</span></p>
        <p class="summary">${esc(player.summary)}</p>
        <p class="card-link"><a href="career.html">Карьера</a><a href="mama.html">Для мамы</a></p>
      </div>
    </div>
  </section>`;
}

function collectCareer() {
  let games = 0;
  let points = 0;
  let best = null;
  data.gameLogs.tournaments.forEach((tournament) => {
    tournament.rows.forEach((row) => {
      const value = Number(row.points);
      if (!Number.isFinite(value)) return;
      games += 1;
      points += value;
      if (!best || value > best.points) {
        best = {
          points: value,
          opponent: row.opponent || "",
          tournament: tournament.label,
          when: row.date || row.stage || "",
        };
      }
    });
  });
  const seasons = data.tournamentStats.seasons;
  const peakPoints = seasons.reduce((bestSeason, season) =>
    season.points > bestSeason.points ? season : bestSeason
  );
  const peakSteals = seasons.reduce((bestSeason, season) =>
    season.steals > bestSeason.steals ? season : bestSeason
  );
  const latest = seasons.find((season) => season.highlight) || seasons[seasons.length - 1];
  const placeFact = data.lastMatch.facts.find((fact) => fact.label === "Результат");
  const placeMatch = placeFact ? String(placeFact.value).match(/(\d+)-е/) : null;
  return { games, points, best, peakPoints, peakSteals, latest, placeFact, place: placeMatch ? placeMatch[1] : "" };
}

function trendValue(viewId, category, seriesName) {
  const view = data.trend.views.find((item) => item.id === viewId);
  if (!view) return null;
  const index = view.categories.indexOf(category);
  const series = view.series.find((item) => item.name === seriesName);
  if (index < 0 || !series) return null;
  return series.values[index];
}

function kpiCard(value, label, detail) {
  return `<article class="kpi">
    <b>${esc(value)}</b>
    <span>${esc(label)}</span>
    ${detail ? `<small>${esc(detail)}</small>` : ""}
  </article>`;
}

function renderCareerCards(career) {
  const assistsThen = trendValue("avg", "Передачи", "2024/25");
  const reboundsThen = trendValue("avg", "Подборы", "2024/25");
  const bestDetail = [career.best.opponent, career.best.when, career.best.tournament]
    .filter(Boolean)
    .join(" · ");
  const cards = [
    kpiCard(String(career.games), "Игры", "Все матчи из трёх турниров"),
    kpiCard(String(career.points), "Очки", "Сколько набрал в этих матчах"),
    kpiCard(String(career.best.points), "Лучшая игра", bestDetail),
    kpiCard(career.place || "—", "Место", career.placeFact ? career.placeFact.value : ""),
    kpiCard(formatAvg(career.peakPoints.points), "Больше всего очков", career.peakPoints.name),
    kpiCard(formatAvg(career.peakSteals.steals), "Больше всего перехватов", career.peakSteals.name),
    kpiCard(
      formatAvg(career.latest.rebounds),
      "Подборы, 2025/26",
      reboundsThen === null ? career.latest.name : `Год назад было ${formatAvg(reboundsThen)}`
    ),
    kpiCard(
      formatAvg(career.latest.assists),
      "Передачи, 2025/26",
      assistsThen === null ? career.latest.name : `Год назад было ${formatAvg(assistsThen)}`
    ),
  ];
  return `<div class="kpi-grid">${cards.join("")}</div>`;
}

function renderSeasonCards() {
  const cards = data.tournamentStats.seasons
    .map((season) => {
      return `<article class="season-card${season.highlight ? " is-current" : ""}">
        <p>${esc(season.name)}</p>
        <strong>${formatAvg(season.points)}</strong>
        <span>за игру · ${esc(season.games)} игр · ${esc(season.minutes)}</span>
        <ul>
          <li><b>${formatAvg(season.rebounds)}</b> подб</li>
          <li><b>${formatAvg(season.assists)}</b> пер</li>
          <li><b>${formatAvg(season.steals)}</b> перехв</li>
          <li><b>${formatAvg(season.turnovers)}</b> потери</li>
        </ul>
        <small>${esc(season.fg2)} 2-очк. · ${esc(season.fg3)} 3-очк. · ${esc(season.ft)} штраф</small>
      </article>`;
    })
    .join("");
  return `<div class="season-grid">${cards}</div>`;
}

function renderMeters() {
  const seasons = data.tournamentStats.seasons;
  const metrics = [
    { key: "points", label: "Очки" },
    { key: "rebounds", label: "Подборы" },
    { key: "assists", label: "Передачи" },
    { key: "steals", label: "Перехваты" },
  ];
  return metrics
    .map((metric) => {
      const max = Math.max(...seasons.map((season) => Number(season[metric.key])));
      const lines = seasons
        .map((season) => {
          const value = Number(season[metric.key]);
          const width = max > 0 ? Math.max(6, (value / max) * 100) : 0;
          return `<div class="meter-line">
            <span title="${esc(season.name)}">${esc(season.name)}</span>
            <span class="meter ${season.highlight ? "is-current" : ""}"><span style="width:${width.toFixed(1)}%"></span></span>
            <b>${formatAvg(value)}</b>
          </div>`;
        })
        .join("");
      return `<section class="meter-block"><h3>${esc(metric.label)}</h3>${lines}</section>`;
    })
    .join("");
}

function renderBadges() {
  const pros = data.notes.pros.map((item) => `<li>${esc(item)}</li>`).join("");
  const cons = data.notes.cons.map((item) => `<li>${esc(item)}</li>`).join("");
  return `<div class="split">
    <section class="panel good">
      <h3>${esc(data.notes.prosHeading)}</h3>
      <ul class="badges">${pros}</ul>
    </section>
    <section class="panel work">
      <h3>${esc(data.notes.consHeading)}</h3>
      <ul class="badges">${cons}</ul>
    </section>
  </div>`;
}

function renderCareerPage() {
  const player = data.player;
  const career = collectCareer();
  if (!career.best) {
    career.best = { points: 0, opponent: "", tournament: "", when: "" };
  }
  const year = profileValue("Год рождения");
  const bio = data.profile.items
    .map(
      (item) =>
        `<li><span>${esc(item.label)}</span><strong>${esc(item.value)}</strong></li>`
    )
    .join("");
  document.getElementById("app").innerHTML = `<section class="player-card" id="top">
      <p class="kicker">Карьера${year ? ` · ${esc(year)}` : ""}</p>
      <div class="player-card-main">
        <div class="shield"><strong>${esc(String(career.best.points))}</strong><em>лучшая игра</em></div>
        <div class="player-card-copy">
          <h1>${esc(player.name)}</h1>
          <p class="hero-meta"><span class="chip">${esc(player.team)}</span><span class="pos">${esc(player.position)}</span></p>
          <p class="summary">${esc(player.summary)}</p>
          <p class="card-link"><a href="mama.html">Для мамы</a></p>
        </div>
      </div>
    </section>
    <section class="block" id="kpis">
      <h2>Достижения</h2>
      <p class="caption">Цифры из журналов матчей и средних. Отдельный рейтинг не придумываем.</p>
      ${renderCareerCards(career)}
    </section>
    <section class="block" id="bio">
      <h2>Коротко</h2>
      <ul class="bio-strip">${bio}</ul>
    </section>
    <section class="block" id="seasons">
      <h2>Турниры</h2>
      <p class="caption">${esc(data.tournamentStats.caption)}</p>
      ${renderSeasonCards()}
    </section>
    <section class="block" id="meters">
      <h2>Сравнение средних</h2>
      <p class="caption">Полоска — доля от лучшего среднего в этих трёх турнирах. Это не оценка от 0 до 99.</p>
      <div class="meter-grid">${renderMeters()}</div>
    </section>
    <section class="block" id="badges">
      <h2>${esc(heading("notes"))}</h2>
      ${renderBadges()}
      <aside class="callout">
        <p class="callout-lead">${esc(data.notes.conclusionLead)}</p>
        <p>${esc(data.notes.conclusion)}</p>
      </aside>
    </section>
    ${renderNewsSection()}`;
  renderNewsPanel(false);
}

function newsIntro() {
  if (!newsData) {
    return `<p class="caption">Файл news.json не загрузился. Остальная страница на месте.</p>`;
  }
  const links = (newsData.sources || [])
    .map((source) => {
      const href = safeUrl(source.href);
      if (!href) return "";
      return `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(source.title)}</a>`;
    })
    .join("");
  return `<p class="caption">${esc(newsData.caption || "")}</p><p class="news-links">${links}</p>`;
}

function renderNewsSection() {
  return `<section class="block" id="news">
    <h2>Новости команды</h2>
    ${newsIntro()}
    <div id="news-panel"></div>
  </section>`;
}

function newsCard(post) {
  const href = safeUrl(post.link);
  const tag = post.tag === "2014" ? "Команда 2014" : post.tag === "клуб" ? "Клуб" : post.tag;
  const link = href
    ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">Пост в Telegram</a>`
    : "";
  return `<article class="news-card">
    <p class="news-meta"><span class="tag">${esc(tag)}</span><time datetime="${esc(post.date)}">${esc(formatNewsDate(post.date))}</time></p>
    <h3>${esc(post.title)}</h3>
    <p>${esc(post.text)}</p>
    ${link}
  </article>`;
}

function renderNewsPanel(restoreFocus) {
  const root = document.getElementById("news-panel");
  if (!root || !newsData) return;
  const filters = [
    { id: "all", label: "Все" },
    { id: "2014", label: "2014" },
    { id: "клуб", label: "Клуб" },
  ];
  if (!filters.some((item) => item.id === state.news)) state.news = "all";
  const posts = newsData.posts
    .filter((post) => state.news === "all" || post.tag === state.news)
    .slice()
    .sort((a, b) => {
      if (a.date === b.date) return (b.sort || 0) - (a.sort || 0);
      return a.date < b.date ? 1 : -1;
    });
  const cards = posts.length
    ? posts.map(newsCard).join("")
    : `<p class="caption">Таких записей нет.</p>`;
  root.innerHTML = `${segmented(filters, state.news, "news", "Какие новости показать")}<div class="news-list">${cards}</div>`;
  if (restoreFocus) {
    const button = document.querySelector(`[data-news="${CSS.escape(state.news)}"]`);
    if (button) button.focus();
  }
}

function renderMamaGame(entry) {
  const row = findLogRow(entry.date);
  const title = row ? `${fullDate(entry.date)} · ${row.opponent}` : fullDate(entry.date);
  const facts = row ? mamaFacts(row) : "Этой строки нет в журнале матчей.";
  return `<article class="review">
    <h3>${esc(title)}</h3>
    <p>${esc(facts)}</p>
    <p class="plus"><span>Плюс.</span> ${esc(entry.plus)}</p>
  </article>`;
}

function renderMamaPage() {
  const mama = data.mama;
  const player = data.player;
  const year = profileValue("Год рождения");
  const anchor = mama.anchor.map((line) => `<p>${esc(line)}</p>`).join("");
  const games = mama.games.map(renderMamaGame).join("");
  const list = (items) => items.map((item) => `<li>${esc(item)}</li>`).join("");
  document.getElementById("app").innerHTML = `<section class="player-card" id="top">
      <p class="kicker">Для мамы${year ? ` · ${esc(year)}` : ""}</p>
      <h1>${esc(player.name)}</h1>
      <p class="hero-meta"><span class="chip">${esc(player.team)}</span><span class="pos">${esc(player.position)}</span></p>
      <p class="summary">${esc(mama.summary)}</p>
      <aside class="callout">${anchor}</aside>
    </section>
    <section class="block" id="recent">
      <h2>Последние игры</h2>
      <p class="caption">Пять последних матчей сезона U12, с конца. Цифры из журнала.</p>
      <div class="reviews">${games}</div>
      <article class="review">
        <h3>${esc(mama.pending.title)}</h3>
        <p>${esc(mama.pending.text)}</p>
      </article>
    </section>
    <section class="block" id="mama-notes">
      <h2>Что видно по цифрам</h2>
      <div class="split">
        <section class="panel good">
          <h3>${esc(mama.goodHeading)}</h3>
          <ul>${list(mama.good)}</ul>
        </section>
        <section class="panel work">
          <h3>${esc(mama.workHeading)}</h3>
          <ul>${list(mama.work)}</ul>
        </section>
      </div>
      <aside class="callout"><p>${esc(mama.closing)}</p></aside>
    </section>
    ${renderNewsSection()}`;
  renderNewsPanel(false);
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
  const page = document.body.dataset.page;
  const titles = {
    career: `${data.player.name} — карьера`,
    mama: `${data.player.name} — для мамы`,
  };
  document.title = titles[page] || `${data.player.name} — профиль`;
  document.getElementById("brand-name").textContent = data.player.name;
  renderNav();
  if (page === "career") {
    renderCareerPage();
  } else if (page === "mama") {
    renderMamaPage();
  } else {
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
    document.getElementById("load-state").hidden = true;
    document.getElementById("app").hidden = false;
    renderGamePanel(false);
    renderTrendPanel(false);
  }
  document.getElementById("load-state").hidden = true;
  document.getElementById("app").hidden = false;
  updateActiveNav();
  scrollToHash();
}

function updateActiveNav() {
  if (!data || document.body.dataset.page !== "profile") return;
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
    return;
  }
  const newsButton = event.target.closest("[data-news]");
  if (newsButton) {
    state.news = newsButton.getAttribute("data-news");
    renderNewsPanel(true);
  }
});

document.addEventListener("scroll", updateActiveNav, { passive: true });

let resizeTimer = 0;
window.addEventListener("resize", () => {
  window.clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => {
    if (!data) return;
    if (document.getElementById("game-panel")) renderGamePanel(false);
    if (document.getElementById("trend-panel")) renderTrendPanel(false);
  }, 150);
});

async function init() {
  const status = document.getElementById("load-state");
  try {
    const response = await fetch("data.json");
    if (!response.ok) throw new Error(String(response.status));
    data = await response.json();
    state.game = data.gameLogs.defaultId;
    state.trend = data.trend.defaultId;
    try {
      const newsResponse = await fetch("news.json");
      if (newsResponse.ok) newsData = await newsResponse.json();
    } catch (newsError) {
      newsData = null;
    }
    render();
  } catch (error) {
    status.hidden = false;
    status.classList.add("error");
    status.textContent =
      "Не удалось загрузить data.json. Откройте страницу через локальный сервер или GitHub Pages, не как файл с диска.";
  }
}

init();
