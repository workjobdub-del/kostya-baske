"use strict";

const SERIES_COLORS = ["#b7beca", "#e8b84a"];
const FONT = "Oswald, sans-serif";

const state = { game: null, trend: null, news: "all", section: "", lastY: 0, chartPoints: [] };
let data = null;
let newsData = null;

const TAB_PAGES = [
  { id: "profile", href: "index.html" },
  { id: "career", href: "career.html" },
  { id: "team", href: "team.html" },
  { id: "mama", href: "mama.html" },
];
const TAB_SWIPE_MIN_DX = 70;
const TAB_SWIPE_MAX_MS = 600;
const TAB_SWIPE_EDGE_PX = 20;
const TAB_SWIPE_ANIM_MS = 200;

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

function formatPlusMinus(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  const sign = num > 0 ? "+" : "";
  return `${sign}${formatPlain(num)}`;
}

const PLUS_MINUS_HINT =
  "+/− — на сколько очков команда выиграла или проиграла, пока Костя был на площадке";

function plusMinusClass(value) {
  const num = Number(value);
  if (!Number.isFinite(num) || num === 0) return "is-even";
  return num > 0 ? "is-pos" : "is-neg";
}

function formatPlusMinusCell(value) {
  if (value == null) return "—";
  const cls = plusMinusClass(value);
  return `<span class="plus-minus ${cls}">${formatPlusMinus(value)}</span>`;
}

function normOppName(text) {
  return String(text || "").toLowerCase().replace(/ё/g, "е").trim();
}

function sameKpiMatch(a, b) {
  if (!a || !b) return false;
  if (a.gameId && b.gameId) return a.gameId === b.gameId;
  return a.date === b.date && normOppName(a.opponent) === normOppName(b.opponent);
}

function isMvpMatch(row) {
  const mvp = data.kpi && data.kpi.mvp;
  if (!mvp || !row) return false;
  return sameKpiMatch(mvp, row);
}

function mvpBadgeHtml() {
  return '<span class="match-mvp">🏅 MVP матча</span>';
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

function term(label, shown) {
  const text = String(shown || label);
  const hit = (data.glossary || []).find((item) => item.term === String(label));
  if (!hit) return esc(text);
  return `<abbr class="term" tabindex="0" role="button" aria-expanded="false" data-term="${esc(hit.text)}">${esc(text)}</abbr>`;
}

function objectTable(columns, rows, extraClass) {
  const head = columns
    .map((column) => {
      const extra = column.key === "scored" || column.key === "conceded" ? " col-extra" : "";
      return `<th class="${extra}" scope="col">${term(column.label)}</th>`;
    })
    .join("");
  const body = rows
    .map((row, index) => {
      const cells = columns
        .map((column) => {
          const extra = column.key === "scored" || column.key === "conceded" ? " col-extra" : "";
          let value;
          if (column.key === "score") value = scoreHtml(row[column.key]);
          else if (column.key === "plusMinus" || column.key === "plusMinusPerGame") value = formatPlusMinusCell(row[column.key]);
          else if (column.key === "kpi" || column.key === "kpiPerGame") value = row[column.key] == null ? "—" : formatPlain(row[column.key]);
          else value = formatCell(row[column.key], column.average);
          const mvp =
            column.key === "opponent" && isMvpMatch(row) ? ` ${mvpBadgeHtml()}` : "";
          return `<td class="${extra}">${value}${mvp}</td>`;
        })
        .join("");
      const fold = row.aiReview
        ? `<tr class="review-fold"><td colspan="${columns.length}"><button type="button" data-fold="review-${index}">Читать разбор</button><p class="game-review" hidden>${esc(row.aiReview)}</p></td></tr>`
        : "";
      return `<tr class="${row.highlight ? "highlight" : ""}">${cells}</tr>${fold}`;
    })
    .join("");
  const cls = extraClass ? ` ${extraClass}` : "";
  const hint = extraClass && extraClass.includes("standings") ? `<p class="scroll-hint only-phone">Листайте таблицу вбок.</p>` : "";
  return `${hint}<div class="table-scroll${cls}"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function arrayTable(columns, rows) {
  const head = columns
    .map((column) => `<th scope="col">${term(column, column === "Старт" ? "В стартовой пятёрке" : column)}</th>`)
    .join("");
  const body = rows
    .map((row) => `<tr>${row.map((cell) => `<td>${esc(cell)}</td>`).join("")}</tr>`)
    .join("");
  return `<div class="table-scroll only-desk"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function phoneStat(label, value) {
  const raw = String(value ?? "");
  if (String(label).startsWith("Подб") && raw.includes("(")) {
    const match = raw.match(/(\d+)\s*\((\d+)\)/);
    if (match) return `${match[1]}, из них ${match[2]} в нападении`;
  }
  const shot = raw.match(/^(\d+)\s*\/\s*(\d+)$/);
  if (shot) return `${shot[1]} из ${shot[2]}`;
  return raw;
}

function scoreCards(columns, rows) {
  const row = rows[0] || [];
  const groups = [
    ["Атака", ["Очки", "2-очк.", "Штраф"]],
    ["Борьба", ["Подб (нап)", "Перехв"]],
    ["Мяч", ["Пер", "Потери"]],
    ["Прочее", ["Старт", "Мин", "Фолы"]],
  ];
  const byLabel = new Map(columns.map((label, index) => [label, row[index]]));
  const blocks = groups
    .map(([title, labels]) => {
      const cards = labels
        .filter((label) => byLabel.has(label))
        .map((label) => {
          const shown = label === "Старт" ? "В стартовой пятёрке" : label;
          const valueText = phoneStat(label, byLabel.get(label));
          const wide = valueText.length > 16 || shown.length > 16 ? " is-wide" : "";
          return `<div class="stat-card${wide}"><b>${esc(valueText)}</b><span>${term(label, shown)}</span></div>`;
        })
        .join("");
      return cards ? `<section class="score-group"><h3>${esc(title)}</h3><div class="stat-cards">${cards}</div></section>` : "";
    })
    .join("");
  return `<div class="only-phone">${blocks}</div>`;
}

function gameCards(tournament) {
  const pointsCol = tournament.columns.find((column) => column.key === "points");
  const cards = tournament.rows
    .map((row) => {
      const title = tournament.columns
        .slice(0, 2)
        .map((column) => row[column.key])
        .filter((value) => value != null && value !== "")
        .join(" · ");
      const points = pointsCol ? formatCell(row.points, false) : "";
      const rest = tournament.columns
        .map((column) => {
          const plain = column.key === "score" ? String(row[column.key] ?? "") : phoneStat(column.label, row[column.key] ?? "");
          const value = column.key === "score" ? scoreHtml(row[column.key]) : esc(plain);
          const wide = plain.length > 18 ? " is-wide" : "";
          return `<div class="${wide.trim()}"><dt>${term(column.label)}</dt><dd>${value}</dd></div>`;
        })
        .join("");
      const review = row.aiReview ? `<p class="game-review">${esc(row.aiReview)}</p>` : "";
      const limited = row.minutes == null && row.fg2 == null ? `<p class="caption">Других цифр в протоколе этой лиги нет.</p>` : "";
      const mvp = isMvpMatch(row) ? ` ${mvpBadgeHtml()}` : "";
      return `<details class="game-card"><summary><span>${esc(title)}${mvp}</span><b>${points}</b></summary><dl>${rest}</dl>${ratioLine(row)}${shareLine(row)}${signalRow(row, tournament)}${limited}${review}</details>`;
    })
    .join("");
  return `<div class="game-cards only-phone">${cards}</div>`;
}

function paragraphs(list) {
  if (!list || !list.length) return "";
  return `<div class="prose">${list.map((text) => `<p>${esc(text)}</p>`).join("")}</div>`;
}

function factValue(item) {
  const parts = scoreParts(item.value);
  if (!parts.kind || !/\d+\s*:\s*\d+/.test(String(item.value))) return esc(item.value);
  const clean = String(item.value).replace(/,\s*победа/gi, "").replace(/,\s*поражение/gi, "");
  return `${esc(clean)} ${resultBadge(parts.kind, parts.word)}`;
}

function facts(items) {
  const cards = items
    .map((item) => {
      const wide = String(item.value).length > 24 ? " is-wide" : "";
      return `<div class="fact${wide}"><dt>${esc(item.label)}</dt><dd>${factValue(item)}</dd></div>`;
    })
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
    const score = String(row.score || "");
    return {
      label,
      date: rawLabel,
      opponent: String(row.opponent || ""),
      score,
      loss: score.includes("поражение"),
      value: Number.isFinite(value) ? value : 0,
      display: formatPlain(row[chart.valueKey]),
      review: row.aiReview || "",
    };
  });
  const fire = fireStreak(points);
  const mean = points.reduce((sum, point) => sum + point.value, 0) / points.length;
  const host = document.getElementById("game-panel");
  const width = boxWidth(host, 1040);
  const height = fire ? 256 : 240;
  const pad = { top: fire ? 42 : 26, right: 8, bottom: 32, left: 28 };
  const plotH = height - pad.top - pad.bottom;
  const plotW = width - pad.left - pad.right;
  const top = axisMax(Math.max(...points.map((point) => point.value), 0));
  const step = tickStep(top);
  const slot = plotW / points.length;
  const barW = Math.max(6, Math.min(28, slot - 10));
  let shapes = `<defs><linearGradient id="fire-fill" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#ff5a1f"></stop><stop offset="0.55" stop-color="#ffb21f"></stop><stop offset="1" stop-color="#fff1b8"></stop></linearGradient></defs>`;

  for (let tick = 0; tick <= top + 0.001; tick += step) {
    const y = pad.top + plotH - (tick / top) * plotH;
    const grid = tick === 0 ? "#3a3f4b" : "#2c313c";
    shapes += `<line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" stroke="${grid}"></line>`;
    shapes += `<text x="${pad.left - 6}" y="${y + 4}" text-anchor="end" fill="#c8c2b6" font-size="12" font-family="${FONT}">${formatTick(tick)}</text>`;
  }

  if (fire) {
    const left = pad.left + fire.start * slot + (slot - barW) / 2;
    const right = pad.left + fire.end * slot + (slot + barW) / 2;
    shapes += `<path class="fire-bracket" d="M${left} 30 V24 H${right} V30" fill="none" stroke="#ff7a2a" stroke-width="2"></path>`;
    shapes += `<text class="fire-label" x="${(left + right) / 2}" y="18" text-anchor="middle" fill="#ffb21f" font-size="13" font-weight="700" font-family="${FONT}" letter-spacing="1.5">В ОГНЕ</text>`;
  }

  const showEvery = slot < 36 ? 2 : 1;
  points.forEach((point, index) => {
    const barH = top === 0 ? 0 : (point.value / top) * plotH;
    const x = pad.left + index * slot + (slot - barW) / 2;
    const y = pad.top + plotH - barH;
    const hot = fire && index >= fire.start && index <= fire.end;
    const kind = hot ? "fire" : point.loss ? "loss" : "win";
    const color = hot ? "url(#fire-fill)" : point.loss ? "#6b717e" : "#e8b84a";
    if (barH > 0) {
      const radius = Math.min(4, barW / 2, barH);
      shapes += `<path class="bar is-${kind}" style="--d:${index * 45}ms" d="M${x} ${y + barH} V${y + radius} Q${x} ${y} ${x + radius} ${y} H${x + barW - radius} Q${x + barW} ${y} ${x + barW} ${y + radius} V${y + barH} Z" fill="${color}"></path>`;
    }
    shapes += `<text class="bar-value" style="--d:${index * 45 + 260}ms" x="${x + barW / 2}" y="${Math.max(pad.top - 4, y - 5)}" text-anchor="middle" fill="#f4efe4" font-size="13" font-weight="700" font-family="${FONT}">${esc(point.display)}</text>`;
    if (index % showEvery === 0) {
      shapes += `<text x="${x + barW / 2}" y="${height - 10}" text-anchor="middle" fill="#c8c2b6" font-size="12" font-family="${FONT}">${esc(point.label)}</text>`;
    }
    shapes += `<rect class="bar-hit" data-bar="${index}" x="${pad.left + index * slot}" y="${pad.top}" width="${slot}" height="${plotH}" fill="transparent"></rect>`;
  });

  if (top > 0) {
    const meanY = pad.top + plotH - (mean / top) * plotH;
    shapes += `<line class="mean-line" x1="${pad.left}" y1="${meanY}" x2="${width - pad.right}" y2="${meanY}" stroke="#f3d98a" stroke-width="1.5" stroke-dasharray="5 4"></line>`;
    shapes += `<text x="${width - pad.right}" y="${meanY - 5}" text-anchor="end" fill="#f3d98a" font-size="12" font-family="${FONT}">среднее ${formatAvg(mean)}</text>`;
  }

  state.chartPoints = points;
  const summary = points.map((point) => `${point.label}: ${point.display}`).join(", ");
  const legend = `<ul class="legend chart-key"><li><span class="swatch" style="background:#e8b84a"></span>Победа</li><li><span class="swatch" style="background:#6b717e"></span>Поражение</li><li><span class="swatch swatch-mean"></span>Пунктир — среднее за турнир</li>${
    fire ? `<li><span class="swatch swatch-fire"></span>${term("В ОГНЕ")}</li>` : ""
  }</ul>`;
  const readout = `<p class="chart-readout" id="chart-readout" aria-live="polite">Нажмите на столбец — покажу соперника и счёт.</p>`;
  return `${legend}${chartFrame("points", width, height, shapes, `Очки по играм. ${summary}`)}${readout}`;
}

function fireStreak(points) {
  if (points.length < 3) return null;
  const mean = points.reduce((sum, point) => sum + point.value, 0) / points.length;
  if (mean <= 0) return null;
  let best = null;
  let start = -1;
  points.forEach((point, index) => {
    if (point.value >= mean * 2) {
      if (start < 0) start = index;
      const length = index - start + 1;
      if (length >= 3 && (!best || length > best.end - best.start + 1)) best = { start, end: index };
    } else {
      start = -1;
    }
  });
  return best;
}

function showBar(index) {
  const point = state.chartPoints && state.chartPoints[index];
  const out = document.getElementById("chart-readout");
  if (!point || !out) return;
  const cut = point.review ? (point.review.length > 140 ? `${point.review.slice(0, 140).trim()}…` : point.review) : "";
  out.textContent = `${point.date} · ${point.opponent} · ${point.score} · ${ruCount(point.display, "очко", "очка", "очков")}${cut ? `. ${cut}` : ""}`;
  document.querySelectorAll("svg.points .bar-hit").forEach((rect) => {
    rect.classList.toggle("is-picked", rect.getAttribute("data-bar") === String(index));
  });
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
  const flat = series.flatMap((item) => item.values.map((v) => Number(v)));
  const minValue = view.signed ? Math.min(...flat, 0) : 0;
  const maxValue = Math.max(...flat, 0);
  const span = maxValue - minValue || 1;
  const top = view.signed ? span : axisMax(maxValue);
  const step = tickStep(top);
  const groupW = plotW / categories.length;
  const barW = Math.min(28, (groupW - 24) / series.length);
  let shapes = "";

  const zeroY = view.signed ? pad.top + plotH - ((0 - minValue) / span) * plotH : pad.top + plotH;
  for (let tick = minValue; tick <= maxValue + 0.001; tick += step) {
    const y = view.signed
      ? pad.top + plotH - ((tick - minValue) / span) * plotH
      : pad.top + plotH - (tick / top) * plotH;
    const grid = Math.abs(tick) < 0.001 ? "#3a3f4b" : "#2c313c";
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
      let barH;
      let y;
      if (view.signed) {
        barH = (Math.abs(safe) / span) * plotH;
        y = safe >= 0 ? zeroY - barH : zeroY;
      } else {
        barH = top === 0 ? 0 : (safe / top) * plotH;
        y = pad.top + plotH - barH;
      }
      const x = start + seriesIndex * (barW + 8);
      const color = SERIES_COLORS[seriesIndex % SERIES_COLORS.length];
      if (barH > 0) {
        const radius = Math.min(5, barW / 2, barH);
        const delay = (categoryIndex * series.length + seriesIndex) * 60;
        shapes += `<path class="bar" style="--d:${delay}ms" d="M${x} ${y + barH} V${y + radius} Q${x} ${y} ${x + radius} ${y} H${x + barW - radius} Q${x + barW} ${y} ${x + barW} ${y + radius} V${y + barH} Z" fill="${color}"></path>`;
      }
      const textDelay = (categoryIndex * series.length + seriesIndex) * 60 + 260;
      shapes += `<text class="bar-value" style="--d:${textDelay}ms" x="${x + barW / 2}" y="${Math.max(12, y - 6)}" text-anchor="middle" fill="#f4efe4" font-size="${valueSize}" font-weight="700" font-family="${FONT}">${formatAvg(safe)}</text>`;
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
  return `<div class="segmented" role="group" aria-label="${esc(label)}" data-noswipe>${buttons}</div>`;
}

function profileValue(label) {
  const item = data.profile.items.find((entry) => entry.label === label);
  return item ? item.value : "";
}

function ruCount(value, one, few, many) {
  const raw = typeof value === "string" ? Number(String(value).replace(",", ".")) : Number(value);
  const n = Math.abs(raw);
  let word = many;
  if (Number.isFinite(n) && !Number.isInteger(n)) word = few;
  else if (Number.isFinite(n)) {
    const n10 = n % 10;
    const n100 = n % 100;
    word = n10 === 1 && n100 !== 11 ? one : n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14) ? few : many;
  }
  const shown = typeof value === "number" && Number.isFinite(value) && !Number.isInteger(value) ? formatAvg(value) : value;
  return `${shown} ${word}`;
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
    const row = tournament.rows.find((item) => item.date === date || item.key === date);
    if (row) return row;
  }
  return null;
}

function scoreParts(score) {
  const text = String(score || "");
  const nums = text.match(/(\d+)\s*:\s*(\d+)/);
  let kind = "";
  if (text.includes("победа")) kind = "win";
  else if (text.includes("поражение")) kind = "loss";
  else if (nums) {
    const left = Number(nums[1]);
    const right = Number(nums[2]);
    kind = left > right ? "win" : left < right ? "loss" : "";
  }
  const clean = nums ? `${nums[1]}:${nums[2]}` : text.replace(/,\s*победа|,\s*поражение/g, "");
  const word = kind === "win" ? "Победа" : kind === "loss" ? "Поражение" : "Счёт";
  return { kind, clean, word, team: nums ? Number(nums[1]) : null };
}

function resultBadge(kind, word) {
  if (kind !== "win" && kind !== "loss") return "";
  return `<span class="badge is-${kind}">${esc(word)}</span>`;
}

function scoreHtml(score) {
  const parts = scoreParts(score);
  return `${esc(parts.clean)} ${resultBadge(parts.kind, parts.word)}`;
}

function shareLine(row) {
  const parts = scoreParts(row.score);
  const points = Number(row.points);
  if (!Number.isFinite(points) || parts.team == null || parts.team <= 0) return "";
  const pct = Math.round((points / parts.team) * 100);
  return `<p class="share">${esc(String(points))} из ${parts.team} очков команды (${pct}%)</p>`;
}

function ratioLine(row) {
  if (row.assists == null || row.turnovers == null) return "";
  const ok = Number(row.assists) >= Number(row.turnovers);
  return `<p class="ratio ${ok ? "is-good" : "is-bad"}">Передачи/потери: ${esc(String(row.assists))} : ${esc(String(row.turnovers))}${ok ? " ✓" : ""}</p>`;
}

function seasonFor(tournament) {
  const seasons = data.tournamentStats.seasons;
  if (!tournament) return seasons.find((season) => season.highlight) || null;
  if (tournament.id === "u12") {
    return (
      seasons.find((season) => String(season.name).includes("МЛБЛ")) ||
      seasons.find((season) => String(season.name).includes("U12")) ||
      null
    );
  }
  if (tournament.id === "pm2526") {
    return seasons.find((season) => season.id === "pm2526" || String(season.name).includes("Первенство Москвы")) || null;
  }
  if (tournament.id === "fb") return seasons.find((season) => season.name.includes("Быстрый")) || null;
  if (tournament.id === "mu") return seasons.find((season) => season.name.includes("Движение")) || null;
  if (tournament.id === "mos2627") return seasons.find((season) => season.id === "mos2627") || null;
  return null;
}

function signalRow(row, tournament) {
  const season = seasonFor(tournament);
  if (!season) return "";
  const bits = [
    ["Очки", "Очки", row.points, season.points, false],
    ["Подб", "Подборы", row.rebounds, season.rebounds, false],
    ["Пер", "Передачи", row.assists, season.assists, false],
    ["Перехв", "Перехваты", row.steals, season.steals, false],
    ["Потери", "Потери", row.turnovers, season.turnovers, true],
    ["Фолы", "Фолы", row.fouls, season.fouls, true],
  ];
  const marks = bits
    .filter((item) => item[2] != null && item[3] != null)
    .map(([label, shown, value, avg, invert]) => {
      const current = Number(value);
      const base = Number(avg);
      if (!Number.isFinite(current) || !Number.isFinite(base) || base === 0) return "";
      const ratio = current / base;
      let state = "even";
      if (ratio >= 1.2) state = "up";
      else if (ratio <= 0.8) state = "down";
      const good = invert ? state === "down" : state === "up";
      const bad = invert ? state === "up" : state === "down";
      const mark = state === "up" ? "▲" : state === "down" ? "▼" : "≈";
      const cls = good ? "is-good" : bad ? "is-bad" : "is-even";
      return `<span class="signal ${cls}"><b>${mark}</b> ${term(label, shown)} ${esc(formatPlain(current))}</span>`;
    })
    .filter(Boolean);
  return marks.length ? `<p class="signals">${marks.join("")}</p>` : "";
}

function mamaFacts(row) {
  const parts = scoreParts(row.score);
  const bits = [];
  if (row.points != null) bits.push(ruCount(row.points, "очко", "очка", "очков"));
  const shots = String(row.fg2 || "").match(/(\d+)\s*\/\s*(\d+)/);
  if (shots && row.fg2 != null) {
    bits.push(`${shots[1]} из ${shots[2]} двухочковых`);
  }
  if (row.rebounds != null) bits.push(ruCount(row.rebounds, "подбор", "подбора", "подборов"));
  if (row.assists != null) bits.push(ruCount(row.assists, "передача", "передачи", "передач"));
  if (row.steals != null) bits.push(ruCount(row.steals, "перехват", "перехвата", "перехватов"));
  if (row.turnovers != null) bits.push(ruCount(row.turnovers, "потеря", "потери", "потерь"));
  const minutes = row.minutes ? ` На площадке ${row.minutes}.` : "";
  const tail = bits.length ? ` ${bits.join(", ")}.` : "";
  return `${parts.word} ${parts.clean}.${minutes}${tail}`;
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
    .filter((item) => item.id !== "season")
    .map((item) => `<a href="#${esc(item.id)}">${esc(item.short || item.label)}</a>`)
    .join("");
}

function currentSeason() {
  const seasons = data.tournamentStats.seasons;
  const live = seasons.find((season) => {
    if (season.id !== "mos2627") return false;
    const games = Number(String(season.games).split(" ")[0]);
    return games > 0;
  });
  return live || seasons.find((season) => season.highlight) || seasons[seasons.length - 1];
}

function heightLine() {
  const match = String(profileValue("Рост и вес")).match(/(\d+)\s*см/);
  return match ? `${match[1]} см` : "";
}

function updatedLine() {
  if (!data.updated) return "";
  return `<p class="updated">Обновлено: ${esc(formatNewsDate(data.updated))}</p>`;
}

function heroStats() {
  const season = currentSeason();
  if (!season) return updatedLine();
  const cells = [
    ["Очки", season.points],
    ["Подборы", season.rebounds],
    ["Передачи", season.assists],
    ["Перехваты", season.steals],
  ]
    .map(
      ([label, value]) =>
        `<div class="hero-stat"><b>${esc(formatAvg(value))}</b><span>${esc(label)}</span></div>`
    )
    .join("");
  const sub = [heightLine(), season.name].filter(Boolean).join(" · ");
  return `<div class="hero-stats" aria-label="Средние за сезон">${cells}</div>
    <p class="hero-sub">${esc(sub)}</p>
    ${updatedLine()}`;
}

const ASSET_V = "2026-10-25-18";

function siteLogoMark() {
  return `<div class="player-logo"><img src="logo.png?v=${ASSET_V}" width="995" height="978" alt="DERBYSHEV 7"></div>`;
}

function kpiFormatMetric(metric) {
  const value = metric.value;
  if (value == null || value === "") return "—";
  if (metric.id === "ts") return `${Math.round(Number(value) * 100)}%`;
  if (metric.id === "astTo") return formatAvg(value);
  if (metric.id === "plusMinus") return formatPlusMinus(value);
  return formatPlain(value);
}

function kpiFormatWas(metric) {
  const value = metric.was;
  if (value == null || value === "") return "";
  if (metric.id === "ts") return `${Math.round(Number(value) * 100)}%`;
  if (metric.id === "plusMinus") return formatPlusMinus(value);
  return formatPlain(value);
}

function kpiDelta(metric) {
  if (metric.was == null || metric.value == null) return "";
  const cur = Number(metric.value);
  const was = Number(metric.was);
  if (!Number.isFinite(cur) || !Number.isFinite(was) || cur === was) return "";
  const improved = metric.higher ? cur > was : cur < was;
  const worse = metric.higher ? cur < was : cur > was;
  if (improved) return '<span class="kpi-delta is-up" aria-hidden="true">▲</span>';
  if (worse) return '<span class="kpi-delta is-down" aria-hidden="true">▼</span>';
  return "";
}

function renderKpiMatchBadge(match, isMvp) {
  if (!match) return "";
  const title = isMvp || match.mvp ? "🏅 MVP матча" : "🏅 Лучший игрок матча по КПИ";
  const href = safeUrl(match.href);
  const link = href
    ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">Страница матча</a>`
    : "";
  return `<article class="kpi-match-badge">
    <p class="kpi-match-title">${esc(title)}</p>
    <p><strong>${esc(match.date)}</strong> · ${esc(match.opponent)} · ${esc(match.score)}${match.result ? `, ${esc(match.result)}` : ""}</p>
    <p>${esc(match.tournament || "")}</p>
    <p>${esc(match.line || "")}</p>
    ${link}
  </article>`;
}

function renderKpiBlock() {
  const block = data.kpi;
  if (!block || !block.metrics || !block.metrics.length) return "";
  const badges = [];
  if (block.mvp) badges.push(renderKpiMatchBadge(block.mvp, true));
  if (block.best && !sameKpiMatch(block.best, block.mvp)) badges.push(renderKpiMatchBadge(block.best, false));
  const tiles = block.metrics
    .map((metric) => {
      const was = kpiFormatWas(metric);
      const team =
        metric.team != null && metric.team !== ""
          ? `<span class="kpi-team">в среднем по команде: ${esc(String(metric.id === "ts" ? `${metric.team}%` : metric.team))}</span>`
          : "";
      return `<article class="kpi-tile">
        <h3>${term(metric.label, metric.label)} ${metric.hint ? `<abbr class="term kpi-hint" tabindex="0" role="button" aria-expanded="false" data-term="${esc(metric.hint)}">?</abbr>` : ""}</h3>
        <p class="kpi-value">${kpiFormatMetric(metric)} ${kpiDelta(metric)}</p>
        ${was ? `<p class="kpi-was">было ${esc(was)}</p>` : ""}
        ${team}
      </article>`;
    })
    .join("");
  const tour =
    block.tournaments && block.tournaments.length
      ? `<p class="kpi-split">${block.tournaments
          .map((item) => `${esc(item.label)}: КПИ ${formatPlain(item.kpiGame)} (${item.games} игр)`)
          .join(" · ")}</p>`
      : "";
  return `<section class="block" id="kpi">
    <h2>Ключевые показатели (KPI)</h2>
    ${block.caption ? `<p class="caption">${esc(block.caption)}</p>` : ""}
    ${badges.join("")}
    <div class="kpi-profile-grid">${tiles}</div>
    ${tour}
  </section>`;
}

function renderHero() {
  const player = data.player;
  const year = profileValue("Год рождения");
  return `<section class="player-card" id="top"${numberAttr()}>
    <p class="kicker">Карточка игрока${year ? ` · ${esc(year)}` : ""}</p>
    <div class="player-card-main">
      ${siteLogoMark()}
      <div class="player-card-copy">
        <h1>${esc(player.name)}</h1>
        <p class="hero-meta"><span class="chip">${esc(player.team)}</span><span class="pos">${esc(player.position)}</span></p>
        <p class="summary">${esc(player.summary)}</p>
        ${heroStats()}
      </div>
    </div>
  </section>
  ${ticker()}`;
}

function numberAttr() {
  const number = data.player.number;
  return number ? ` data-number="${esc(number)}"` : "";
}

function ticker() {
  const career = collectCareer();
  const items = [];
  if (data.player.number) items.push(`№ ${data.player.number}`);
  items.push(ruCount(career.games, "игра", "игры", "игр"));
  items.push(ruCount(career.points, "очко", "очка", "очков"));
  if (career.best) items.push(`Лучшая игра — ${ruCount(career.best.points, "очко", "очка", "очков")}`);
  const achievement = (data.achievements || [])[0];
  if (achievement) items.push(`${achievement.value}-е место`);
  if (career.latest) items.push(`${formatAvg(career.latest.steals)} перехвата за игру (${seasonYear(career.latest.name) || "сезон"})`);
  const run = items.map((item) => `<span>${esc(item)}</span>`).join("");
  return `<div class="ticker" aria-hidden="true"><div class="ticker-track">${run}${run}</div></div>`;
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
  const achievement = (data.achievements || [])[0];
  return { games, points, best, peakPoints, peakSteals, latest, achievement };
}

function trendValue(viewId, category, seriesName) {
  const view = data.trend.views.find((item) => item.id === viewId);
  if (!view) return null;
  const index = view.categories.indexOf(category);
  const series = view.series.find((item) => item.name === seriesName);
  if (index < 0 || !series) return null;
  return series.values[index];
}

function seasonYear(name) {
  const match = String(name).match(/\d{4}\/\d{2}/);
  return match ? match[0] : "";
}

function kpiCard(value, label, detail) {
  return `<article class="kpi">
    <b>${esc(value)}</b>
    <span>${esc(label)}</span>
    ${detail ? `<small>${esc(detail)}</small>` : ""}
  </article>`;
}

function renderCareerCards(career) {
  const assistsThen = trendValue("avg", "Передачи", "Быстрый прорыв, 2024/25");
  const reboundsThen = trendValue("avg", "Подборы", "Быстрый прорыв, 2024/25");
  const bestDetail = [career.best.opponent, career.best.when, career.best.tournament]
    .filter(Boolean)
    .join(" · ");
  const cards = [
    kpiCard(String(career.games), "Игры", "Все матчи из трёх турниров"),
    kpiCard(String(career.points), "Очков за карьеру (в базе)", "Сумма очков из журналов"),
    kpiCard(String(career.best.points), "Лучшая игра", bestDetail),
    kpiCard(
      career.achievement ? career.achievement.value : "—",
      "Место",
      career.achievement ? `${career.achievement.value}-е место · ${career.achievement.detail}` : ""
    ),
    kpiCard(formatAvg(career.peakPoints.points), "Лучшее среднее за турнир", `очка за игру · ${career.peakPoints.name}`),
    kpiCard(formatAvg(career.peakSteals.steals), "Лучшее среднее по перехватам", career.peakSteals.name),
    kpiCard(
      formatAvg(career.latest.rebounds),
      `Подборы, ${seasonYear(career.latest.name) || "сезон"}`,
      seasonYear(career.latest.name) === "2025/26" && reboundsThen !== null
        ? `Год назад было ${formatAvg(reboundsThen)}`
        : career.latest.name
    ),
    kpiCard(
      formatAvg(career.latest.assists),
      `Передачи, ${seasonYear(career.latest.name) || "сезон"}`,
      seasonYear(career.latest.name) === "2025/26" && assistsThen !== null
        ? `Год назад было ${formatAvg(assistsThen)}`
        : career.latest.name
    ),
  ];
  return `<div class="kpi-grid">${cards.join("")}</div>`;
}

function shotPhrase(label, value) {
  const match = String(value).match(/(\d+)\s*\/\s*(\d+)(?:,\s*(\d+)%)?/);
  if (!match) return `<span>${term(label)}: ${esc(value)}</span>`;
  const percent = match[3] ? ` (${match[3]}%)` : "";
  return `<span>${term(label)}: ${match[1]} из ${match[2]}${percent}</span>`;
}

function renderSeasonCards() {
  const cards = data.tournamentStats.seasons
    .map((season) => {
      const games = String(season.games).match(/(\d+)\s*\((\d+)\)/);
      const gamesText = games ? `${games[1]} игр, ${games[2]} в старте` : `${season.games} игр`;
      return `<article class="season-card${season.highlight ? " is-current" : ""}">
        <p>${esc(season.name)}</p>
        <strong>${formatAvg(season.points)}</strong>
        <span>очка за игру · ${esc(gamesText)} · ${esc(season.minutes)} мин в среднем</span>
        <ul>
          <li><b>${formatAvg(season.rebounds)}</b> ${term("Подб")}</li>
          <li><b>${formatAvg(season.assists)}</b> ${term("Пер")}</li>
          <li><b>${formatAvg(season.steals)}</b> ${term("Перехв")}</li>
          <li><b>${formatAvg(season.turnovers)}</b> ${term("Потери")}</li>
          ${season.kpiPerGame != null ? `<li><b>${formatPlain(season.kpiPerGame)}</b> ${term("КПИ")}</li>` : ""}
          ${season.plusMinusPerGame != null ? `<li>${formatPlusMinusCell(season.plusMinusPerGame)} <span class="plus-minus-label">${term("+/−")}</span></li>` : ""}
        </ul>
        <small class="shoot-lines">${shotPhrase("2-очк.", season.fg2)}${shotPhrase("3-очк.", season.fg3)}${shotPhrase("Штраф", season.ft)}</small>
      </article>`;
    })
    .join("");
  return `<div class="season-grid">${cards}</div>`;
}

function careerSeasonColumns() {
  const cols = (data.tournamentStats.averageColumns || []).slice();
  if (!cols.some((column) => column.key === "kpiPerGame")) {
    cols.push({ key: "kpiPerGame", label: "КПИ", average: true });
  }
  if (!cols.some((column) => column.key === "plusMinusPerGame")) {
    cols.push({ key: "plusMinusPerGame", label: "+/−", average: true });
  }
  return cols;
}

function renderMeters() {
  const seasons = data.tournamentStats.seasons;
  const metrics = [
    { key: "points", label: "Очки" },
    { key: "rebounds", label: "Подборы" },
    { key: "assists", label: "Передачи" },
    { key: "steals", label: "Перехваты" },
    { key: "plusMinusPerGame", label: "+/−", signed: true },
  ];
  return metrics
    .map((metric) => {
      const values = seasons.map((season) => Number(season[metric.key]));
      const max = metric.signed
        ? Math.max(...values.map((value) => (Number.isFinite(value) ? Math.abs(value) : 0)), 0.1)
        : Math.max(...values.filter((value) => Number.isFinite(value)), 0.1);
      const lines = seasons
        .map((season) => {
          const value = Number(season[metric.key]);
          const safe = Number.isFinite(value) ? value : 0;
          const width = max > 0 ? Math.max(safe === 0 && !metric.signed ? 0 : 6, (Math.abs(safe) / max) * 100) : 0;
          const valueHtml = metric.signed ? formatPlusMinusCell(season[metric.key]) : `<b>${formatAvg(safe)}</b>`;
          const barClass = metric.signed
            ? `meter ${plusMinusClass(safe)} ${season.highlight ? "is-current" : ""}`
            : `meter ${season.highlight ? "is-current" : ""}`;
          return `<div class="meter-line">
            <span title="${esc(season.name)}">${esc(season.name)}</span>
            <span class="${barClass}"><span style="width:${width.toFixed(1)}%"></span></span>
            ${metric.signed ? valueHtml : `<b>${formatAvg(safe)}</b>`}
          </div>`;
        })
        .join("");
      return `<section class="meter-block"><h3>${term(metric.label, metric.label)}</h3>${lines}</section>`;
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
        `<li class="${String(item.value).length > 24 ? "is-wide" : ""}"><span>${esc(item.label)}</span><strong>${esc(item.value)}</strong></li>`
    )
    .join("");
  document.getElementById("app").innerHTML = `<section class="player-card" id="top"${numberAttr()}>
      <p class="kicker">Карьера${year ? ` · ${esc(year)}` : ""}</p>
      <div class="player-card-main">
        ${siteLogoMark()}
        <div class="shield"><strong>${esc(String(career.best.points))}</strong><em>лучшая игра</em></div>
        <div class="player-card-copy">
          <h1>${esc(player.name)}</h1>
          <p class="hero-meta"><span class="chip">${esc(player.team)}</span><span class="pos">${esc(player.position)}</span></p>
          <p class="summary">${esc(ruCount(career.games, "игра", "игры", "игр"))}, ${esc(ruCount(career.points, "очко", "очка", "очков"))}. Ниже — лучшие матчи и средние из этих журналов.</p>
          ${updatedLine()}
          <p class="card-link"><a href="#kpis">Достижения</a><a href="#seasons">Турниры</a><a href="#badges">Оценка</a><a href="team.html#news">Новости</a><a href="index.html#glossary">Что значат цифры?</a><a href="mama.html">Для мамы</a></p>
        </div>
      </div>
    </section>
    ${ticker()}
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
      <p class="caption">${esc(data.tournamentStats.caption)} ${esc(PLUS_MINUS_HINT)}</p>
      ${renderSeasonCards()}
      ${objectTable(careerSeasonColumns(), data.tournamentStats.seasons, "only-desk career-season-table")}
    </section>
    <section class="block" id="meters">
      <h2>Сравнение средних</h2>
      <p class="caption">Полоска — доля от лучшего среднего в этих турнирах (для +/− — от наибольшего по модулю). Это не оценка от 0 до 99.</p>
      <div class="meter-grid">${renderMeters()}</div>
    </section>
    <section class="block" id="badges">
      <h2>${esc(heading("notes"))}</h2>
      ${renderBadges()}
      <aside class="callout">
        <p class="callout-lead">${esc(data.notes.conclusionLead)}</p>
        <p>${esc(data.notes.conclusion)}</p>
      </aside>
    </section>`;
}

function renderTeamPage() {
  document.getElementById("app").innerHTML = `${renderSeason()}${renderNewsSection()}`;
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
  const plus = row && row.aiMama ? row.aiMama : entry.plus;
  return `<article class="review">
    <h3>${esc(title)}</h3>
    <p>${esc(facts)}</p>
    <p class="plus"><span>Плюс.</span> ${esc(plus)}</p>
  </article>`;
}

function gameStamp(tournament, row, index) {
  const match = String(row.date || "").match(/^(\d{2})\.(\d{2})\.(\d{2})$/);
  if (match) return new Date(2000 + Number(match[3]), Number(match[2]) - 1, Number(match[1])).getTime() + index;
  return (tournament.id === "u12" ? 20250000 : 20240000) + index;
}

function mamaArticle(tournament, row) {
  const parts = scoreParts(row.score);
  const title = row.date
    ? `${fullDate(row.date)} · ${row.opponent}`
    : `${row.stage ? `${row.stage} · ` : ""}${row.opponent}`;
  const plus = row.aiMama || "";
  const limited = row.minutes == null && row.fg2 == null ? `<p class="caption">Других цифр в протоколе этой лиги нет.</p>` : "";
  const mvp = isMvpMatch(row) ? ` ${mvpBadgeHtml()}` : "";
  return `<article class="review">
    <h3>${esc(title)} ${resultBadge(parts.kind, parts.word)}${mvp}</h3>
    <p>${esc(mamaFacts(row))}</p>
    ${shareLine(row)}
    ${limited}
    ${plus ? `<p class="plus"><span>Что порадовало:</span> ${esc(plus)}</p>` : ""}
  </article>`;
}

function renderMamaPage() {
  const mama = data.mama;
  const player = data.player;
  const year = profileValue("Год рождения");
  const flat = [];
  data.gameLogs.tournaments.forEach((tournament) => {
    tournament.rows.forEach((row, index) => flat.push({ tournament, row, index, stamp: gameStamp(tournament, row, index) }));
  });
  flat.sort((a, b) => b.stamp - a.stamp);
  const latestItems = flat.slice(0, 5);
  const latestKeys = new Set(latestItems.map((item) => `${item.tournament.id}:${item.index}`));
  const latest = latestItems.map((item) => mamaArticle(item.tournament, item.row)).join("");
  const groups = data.gameLogs.tournaments
    .map((tournament) => {
      const cards = tournament.rows
        .map((row, index) => (latestKeys.has(`${tournament.id}:${index}`) ? "" : mamaArticle(tournament, row)))
        .join("");
      if (!cards) return "";
      return `<section class="mama-group"><h3>${esc(tournament.mamaTitle || tournament.label)}</h3>${cards}</section>`;
    })
    .join("");
  const list = (items) => items.map((item) => `<li>${esc(item)}</li>`).join("");
  document.getElementById("app").innerHTML = `<section class="player-card" id="top"${numberAttr()}>
      <p class="kicker">Для мамы${year ? ` · ${esc(year)}` : ""}</p>
      ${siteLogoMark()}
      <h1>${esc(player.name)}</h1>
      <p class="hero-meta"><span class="chip">${esc(player.team)}</span><span class="pos">${esc(player.position)}</span></p>
      <p class="summary">${esc(mama.summary)}</p>
      ${
        data.kpi && data.kpi.mvp
          ? `<p class="caption">В матче ${esc(data.kpi.mvp.date)} против «${esc(String(data.kpi.mvp.opponent).split(",")[0])}» у Кости звание <strong>MVP матча</strong> — его назвали лучшим по общей пользе на площадке.</p>`
          : ""
      }
      ${updatedLine()}
      <p class="card-link"><a href="#path">Весь путь</a><a href="#recent">Игры</a><a href="#mama-notes">Что видно</a><a href="team.html#news">Новости</a><a href="index.html#glossary">Что значат цифры?</a></p>
    </section>
    <section class="block" id="path">
      <h2>Весь путь</h2>
      <aside class="callout"><p>${esc(mama.seasonSummary || "")}</p></aside>
    </section>
    <section class="block" id="recent">
      <h2>Последние игры</h2>
      <p class="caption">Пять последних матчей с личным текстом. Остальные — под кнопкой, по турнирам.</p>
      <div class="reviews">${latest}</div>
      <p class="card-link"><button type="button" id="show-all-games">Показать все игры</button></p>
      <div id="all-mama-games" hidden>${groups}</div>
      ${
        mama.pending && mama.pending.title
          ? `<article class="review"><h3>${esc(mama.pending.title)}</h3><p>${esc(mama.pending.text)}</p></article>`
          : ""
      }
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
    </section>`;
}

function renderLast() {
  const block = data.lastMatch;
  const row = findLogRow("21.02.26") || findLogRow("u12-9");
  const tournament = data.gameLogs.tournaments.find((item) => item.id === "u12");
  return `<section class="block" id="last">
    <h2>${esc(heading("last"))}</h2>
    ${block.notice ? `<p class="plaque">${esc(block.notice)}</p>` : ""}
    <p class="caption">${esc(block.caption)}</p>
    ${facts(block.facts)}
    ${scoreCards(block.columns, block.rows)}
    ${arrayTable(block.columns, block.rows)}
    ${row ? ratioLine(row) : ""}
    ${row ? shareLine(row) : ""}
    ${row ? signalRow(row, tournament) : ""}
    ${block.aiReview ? `<div class="prose"><p>${esc(block.aiReview)}</p></div>` : paragraphs(block.paragraphs)}
  </section>`;
}

function renderGuard() {
  const season = data.tournamentStats.seasons.find((item) => item.highlight) || data.tournamentStats.seasons[data.tournamentStats.seasons.length - 1];
  return `<section class="block" id="guard">
    <h2>Что важно для разыгрывающего</h2>
    <ul class="guard-list">
      <li>Передачи не меньше потерь. Сейчас в среднем ${esc(formatAvg(season.assists))} : ${esc(formatAvg(season.turnovers))}.</li>
      <li>Мало потерь: разыгрывающий держит мяч дольше всех.</li>
      <li>Перехваты и подборы — вклад в защиту.</li>
      <li>Очки — бонус, не главное.</li>
    </ul>
  </section>`;
}

function renderGlossary() {
  if (!data.glossary || !data.glossary.length) return "";
  const items = data.glossary
    .map((item) => `<article class="glossary-item"><h3>${esc(item.term)}</h3><p>${esc(item.text)}</p></article>`)
    .join("");
  return `<section class="block" id="glossary"><h2>Словарик</h2><div class="glossary">${items}</div></section>`;
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
    ${block.plaque ? `<p class="plaque">${esc(block.plaque)}</p>` : ""}
    ${objectTable(block.standings.columns, block.standings.rows, "standings")}
  </section>`;
}

function renderStats() {
  const block = data.tournamentStats;
  return `<section class="block" id="stats">
    <h2>${esc(heading("stats"))}</h2>
    <p class="caption">${esc(block.caption)}</p>
    <div class="only-phone">${renderSeasonCards()}</div>
    ${objectTable(block.averageColumns, block.seasons, "only-desk")}
    ${objectTable(block.shootingColumns, block.seasons, "only-desk")}
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
      const body = `<strong>${esc(link.title)}</strong><span>${esc(link.site)}</span>${link.note ? `<small>${esc(link.note)}</small>` : ""}`;
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
  )}${tournament.blurb ? `<p class="caption">${esc(tournament.blurb)}</p>` : ""}${pointsChart(tournament)}${gameCards(tournament)}${objectTable(tournament.columns, tournament.rows, "only-desk")}`;
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
  )}${view.hint ? `<p class="caption">${esc(view.hint)}</p>` : ""}${groupedChart(view)}`;
  if (restoreFocus) {
    const button = document.querySelector(`[data-trend="${CSS.escape(state.trend)}"]`);
    if (button) button.focus();
  }
}

function render() {
  clearLoadState(document.getElementById("load-state"));
  const page = document.body.dataset.page;
  const titles = {
    career: `${data.player.name} — карьера`,
    mama: `${data.player.name} — для мамы`,
    team: `${data.player.team} — команда`,
  };
  document.title = titles[page] || `${data.player.name} — профиль`;
  renderNav();
  if (page === "career") {
    renderCareerPage();
  } else if (page === "mama") {
    renderMamaPage();
  } else if (page === "team") {
    renderTeamPage();
  } else {
    document.getElementById("app").innerHTML = [
      renderHero(),
      renderKpiBlock(),
      renderLast(),
      renderGuard(),
      renderProfile(),
      renderStats(),
      renderGamesSection(),
      renderTrendSection(),
      renderNotes(),
      renderSources(),
      renderGlossary(),
    ].join("");
    document.getElementById("load-state").hidden = true;
    document.getElementById("app").hidden = false;
    renderGamePanel(false);
    renderTrendPanel(false);
  }
  document.getElementById("load-state").hidden = true;
  document.getElementById("app").hidden = false;
  animateIn();
  renderNotify();
  syncChrome();
  scrollToHash();
}

const REVEAL =
  ".block, .ticker, .kpi, .season-card, .meter-block, .review, .news-card, .fact, .bio-strip li, .match-row, .source-card, .panel";
const COUNT = ".kpi b, .shield strong, .season-card strong, .hero-stat b";
let revealer = null;

function motionOk() {
  return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function countUp(el) {
  if (el.dataset.counted) return;
  const final = el.textContent.trim();
  const match = final.match(/^(\d+)(?:,(\d+))?$/);
  if (!match) return;
  el.dataset.counted = "1";
  const decimals = match[2] ? match[2].length : 0;
  const target = Number(match[1] + (match[2] ? `.${match[2]}` : ""));
  const started = performance.now();
  const duration = 700;
  const frame = (now) => {
    const t = Math.min(1, (now - started) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = t < 1 ? (target * eased).toFixed(decimals).replace(".", ",") : final;
    if (t < 1) requestAnimationFrame(frame);
    else el.classList.add("is-landed");
  };
  el.textContent = (0).toFixed(decimals).replace(".", ",");
  requestAnimationFrame(frame);
}

function animateIn() {
  const root = document.getElementById("app");
  if (!motionOk() || !("IntersectionObserver" in window)) return;
  document.documentElement.classList.add("jam");
  if (revealer) revealer.disconnect();
  revealer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        el.classList.add("in");
        if (el.matches(COUNT)) countUp(el);
        el.querySelectorAll(COUNT).forEach(countUp);
        revealer.unobserve(el);
      });
    },
    { rootMargin: "0px 0px -6% 0px", threshold: 0.06 }
  );
  root.querySelectorAll(REVEAL).forEach((el) => {
    const parent = el.parentElement;
    const index = parent ? Array.prototype.indexOf.call(parent.children, el) : 0;
    el.classList.add("reveal");
    el.style.setProperty("--i", String(Math.min(index, 7)));
    revealer.observe(el);
  });
  root.querySelectorAll(".player-card .shield strong, .hero-stat b").forEach(countUp);
}

function phoneLayout() {
  return window.matchMedia("(max-width: 720px)").matches;
}

function syncChrome() {
  const header = document.querySelector(".topbar");
  const nav = document.getElementById("nav");
  const toTop = document.getElementById("to-top");
  const y = window.scrollY;
  const hero = document.getElementById("top");
  const pastHero = hero ? hero.getBoundingClientRect().bottom <= 1 : y > 200;
  const showNav = document.body.dataset.page === "profile" && nav && !nav.hidden && (pastHero || !phoneLayout());
  if (nav) nav.classList.toggle("is-shown", Boolean(showNav));
  if (header) {
    if (!phoneLayout()) {
      header.classList.remove("is-hidden");
    } else if (showNav) {
      header.classList.add("is-hidden");
    } else {
      const down = y > state.lastY + 8;
      const up = y < state.lastY - 8;
      if (y < 12 || up) header.classList.remove("is-hidden");
      else if (down && y > 40) header.classList.add("is-hidden");
    }
    document.body.classList.toggle("header-hidden", header.classList.contains("is-hidden"));
  }
  document.body.classList.toggle("nav-open", Boolean(showNav));
  if (toTop) toTop.hidden = y < window.innerHeight;
  state.lastY = y;
  updateActiveNav();
}

function updateActiveNav() {
  if (!data || document.body.dataset.page !== "profile") return;
  const header = document.querySelector(".topbar");
  const nav = document.getElementById("nav");
  const headerH = header && !header.classList.contains("is-hidden") ? header.offsetHeight : 0;
  const navH = nav && nav.classList.contains("is-shown") ? nav.offsetHeight : 0;
  const offset = headerH + navH + 8;
  let current = data.nav[0].id;
  data.nav.forEach((item) => {
    const section = document.getElementById(item.id);
    if (section && section.getBoundingClientRect().top <= offset) current = item.id;
  });
  document.querySelectorAll("#nav a").forEach((link) => {
    link.classList.toggle("active", link.getAttribute("href") === `#${current}`);
  });
  if (current !== state.section && nav) {
    state.section = current;
    const link = nav.querySelector("a.active");
    if (link) {
      const left = link.offsetLeft - (nav.clientWidth - link.offsetWidth) / 2;
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      nav.scrollTo({ left: Math.max(0, left), behavior: reduce ? "auto" : "smooth" });
    }
  }
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

function closeTerm() {
  const pop = document.getElementById("term-pop");
  if (pop) pop.hidden = true;
  document.querySelectorAll(".term[aria-expanded='true']").forEach((node) => node.setAttribute("aria-expanded", "false"));
}

function openTerm(node) {
  let pop = document.getElementById("term-pop");
  if (!pop) {
    pop = document.createElement("div");
    pop.id = "term-pop";
    pop.className = "term-pop";
    pop.setAttribute("role", "tooltip");
    document.body.appendChild(pop);
  }
  closeTerm();
  pop.textContent = node.getAttribute("data-term") || "";
  pop.hidden = false;
  node.setAttribute("aria-expanded", "true");
  const rect = node.getBoundingClientRect();
  const width = Math.min(280, window.innerWidth - 24);
  pop.style.width = `${width}px`;
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
  const popHeight = pop.offsetHeight || 72;
  let top = rect.bottom + 8;
  if (top + popHeight > window.innerHeight - 8) top = Math.max(8, rect.top - popHeight - 8);
  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;
}

document.addEventListener("click", (event) => {
  const termNode = event.target.closest(".term");
  if (termNode) {
    event.preventDefault();
    if (termNode.getAttribute("aria-expanded") === "true") closeTerm();
    else openTerm(termNode);
    return;
  }
  if (!event.target.closest("#term-pop")) closeTerm();
  const fold = event.target.closest("[data-fold]");
  if (fold) {
    const text = fold.parentElement.querySelector(".game-review");
    if (text) text.hidden = !text.hidden;
    return;
  }
  if (event.target.closest("#show-all-games")) {
    const box = document.getElementById("all-mama-games");
    if (box) {
      box.hidden = !box.hidden;
      event.target.textContent = box.hidden ? "Показать все игры" : "Скрыть остальные игры";
    }
    return;
  }
  const bar = event.target.closest("[data-bar]");
  if (bar) {
    showBar(Number(bar.getAttribute("data-bar")));
    return;
  }
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

document.addEventListener("pointerover", (event) => {
  if (event.pointerType !== "mouse" || !event.target.closest) return;
  const bar = event.target.closest("[data-bar]");
  if (bar) showBar(Number(bar.getAttribute("data-bar")));
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeTerm();
  const termNode = event.target.closest && event.target.closest(".term");
  if (termNode && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    if (termNode.getAttribute("aria-expanded") === "true") closeTerm();
    else openTerm(termNode);
  }
});

document.addEventListener("scroll", syncChrome, { passive: true });

const toTop = document.getElementById("to-top");
if (toTop) {
  toTop.addEventListener("click", () => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
  });
}

let resizeTimer = 0;
let lastWidth = window.innerWidth;
window.addEventListener("resize", () => {
  window.clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => {
    if (!data || window.innerWidth === lastWidth) return;
    lastWidth = window.innerWidth;
    if (document.getElementById("game-panel")) renderGamePanel(false);
    if (document.getElementById("trend-panel")) renderTrendPanel(false);
  }, 150);
});

const ONESIGNAL_APP_ID = "7a9c32d2-ee00-46aa-9cfd-009842e4dab4";
const TAG_GAMES = "Игры";
const TAG_NEWS = "Новости команды";

function workerTarget() {
  const path = location.pathname;
  const marker = "/kostya-baske";
  const at = path.indexOf(marker);
  const scope =
    at >= 0 ? `${path.slice(at, at + marker.length)}/` : path.slice(0, path.lastIndexOf("/") + 1) || "/";
  return { path: `${scope.replace(/^\//, "")}sw.js`, scope };
}

function siteBase() {
  const { scope } = workerTarget();
  return new URL(scope, location.origin).href;
}

function dataUrl(name) {
  return new URL(name, siteBase()).href;
}

function clearLoadState(status) {
  if (!status) return;
  status.hidden = true;
  status.classList.remove("error");
  status.textContent = "";
}

function loadErrorMessage(error) {
  if (location.protocol === "file:") {
    return "Не удалось загрузить data.json. Откройте страницу через локальный сервер или GitHub Pages, не как файл с диска.";
  }
  return "Не удалось загрузить данные с сайта. Проверьте интернет и обновите страницу (кнопка «Обновить» в плашке или Ctrl+F5).";
}

const LIVE_DATA_BASE = "https://workjobdub-del.github.io/kostya-baske/";

async function loadJson(name, attempts = 3) {
  const urls = [dataUrl(name)];
  if (location.protocol === "file:" && !urls[0].startsWith(LIVE_DATA_BASE)) {
    urls.push(new URL(name, LIVE_DATA_BASE).href);
  }
  let lastError = null;
  for (const url of urls) {
    for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      const response = await fetch(url, { cache: "no-store", credentials: "same-origin" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const type = (response.headers.get("content-type") || "").toLowerCase();
      if (type && !type.includes("json") && !type.includes("text/plain")) {
        throw new Error(`unexpected type ${type}`);
      }
      const text = await response.text();
      return JSON.parse(text);
    } catch (error) {
      lastError = error;
      if (attempt + 1 < attempts) await new Promise((resolve) => window.setTimeout(resolve, 300));
    }
    }
  }
  throw lastError;
}

function renderNotify() {
  const app = document.getElementById("app");
  if (!app || app.hidden) return;
  let box = document.getElementById("notify");
  if (!box) {
    box = document.createElement("section");
    box.id = "notify";
    box.className = "block notify";
    app.appendChild(box);
  }
  const OneSignal = window.oneSignal;
  const opted = Boolean(OneSignal && OneSignal.User.PushSubscription.optedIn);
  const gamesOn = box.querySelector("[data-tag='games']");
  const newsOn = box.querySelector("[data-tag='news']");
  const keepGames = gamesOn ? gamesOn.checked : true;
  const keepNews = newsOn ? newsOn.checked : false;
  const status = opted
    ? "Уведомления включены. Игры приходят сразу, новости команды — если отметить вторую галочку."
    : "Браузер спросит разрешение только после кнопки. Сам при первом заходе не спрашивает.";
  box.innerHTML = `<h2>Уведомления</h2>
    <p>${status}</p>
    <div class="notify-options">
      <label><input type="checkbox" data-tag="games" ${keepGames ? "checked" : ""}> Игры</label>
      <label><input type="checkbox" data-tag="news" ${keepNews ? "checked" : ""}> Новости команды</label>
    </div>
    <div class="notify-actions">
      ${
        opted
          ? `<button type="button" class="is-off" data-notify="off">Выключить уведомления</button>`
          : `<button type="button" class="is-on" data-notify="on">Включить уведомления</button>`
      }
    </div>
    <p class="notify-note" data-notify-note hidden></p>`;
  if (OneSignal && opted) {
    OneSignal.User.getTags()
      .then((tags) => {
        const tagMap = tags && typeof tags === "object" ? tags : {};
        const games = box.querySelector("[data-tag='games']");
        const news = box.querySelector("[data-tag='news']");
        const hasOurTags = Object.prototype.hasOwnProperty.call(tagMap, TAG_GAMES)
          || Object.prototype.hasOwnProperty.call(tagMap, TAG_NEWS);
        if (!hasOurTags) {
          if (games) games.checked = true;
          void saveNotifyTagsWithRetry().catch(() => {});
          return;
        }
        if (games && Object.prototype.hasOwnProperty.call(tagMap, TAG_GAMES)) {
          games.checked = tagMap[TAG_GAMES] === "1";
        }
        if (news && Object.prototype.hasOwnProperty.call(tagMap, TAG_NEWS)) {
          news.checked = tagMap[TAG_NEWS] === "1";
        }
      })
      .catch(() => {});
  }
}

async function saveNotifyTags() {
  const OneSignal = window.oneSignal;
  const box = document.getElementById("notify");
  if (!OneSignal || !box) return;
  const games = box.querySelector("[data-tag='games']").checked;
  const news = box.querySelector("[data-tag='news']").checked;
  if (games) await OneSignal.User.addTag(TAG_GAMES, "1");
  else await OneSignal.User.removeTag(TAG_GAMES);
  if (news) await OneSignal.User.addTag(TAG_NEWS, "1");
  else await OneSignal.User.removeTag(TAG_NEWS);
}

async function saveNotifyTagsWithRetry() {
  try {
    await saveNotifyTags();
  } catch (firstError) {
    await new Promise((resolve) => window.setTimeout(resolve, 400));
    await saveNotifyTags();
  }
}

function waitForOptedIn(OneSignal, timeoutMs = 5000) {
  const sub = OneSignal.User.PushSubscription;
  if (sub.optedIn) return Promise.resolve(true);
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      sub.removeEventListener("change", onChange);
      window.clearInterval(poll);
      window.clearTimeout(timer);
      resolve(value);
    };
    const onChange = () => {
      if (sub.optedIn) finish(true);
    };
    sub.addEventListener("change", onChange);
    const started = Date.now();
    const poll = window.setInterval(() => {
      if (sub.optedIn) finish(true);
      else if (Date.now() - started >= timeoutMs) finish(false);
    }, 200);
    const timer = window.setTimeout(() => finish(Boolean(sub.optedIn)), timeoutMs);
  });
}

async function enableNotifications(OneSignal) {
  notifyNote("");
  try {
    await OneSignal.User.PushSubscription.optIn();
  } catch (error) {
    renderNotify();
    if (!OneSignal.User.PushSubscription.optedIn) {
      notifyNote("Не удалось включить уведомления.");
    }
    return;
  }
  const opted = await waitForOptedIn(OneSignal);
  renderNotify();
  if (!opted) {
    notifyNote("Браузер не разрешил уведомления. Включите их в настройках сайта.");
    return;
  }
  try {
    await saveNotifyTagsWithRetry();
  } catch (error) {
    notifyNote(
      "Уведомления включены, но темы не сохранились. Переключите галочки «Игры» / «Новости» ещё раз."
    );
  }
}

function notifyNote(text) {
  const note = document.querySelector("[data-notify-note]");
  if (!note) return;
  note.hidden = !text;
  note.textContent = text || "";
}

document.addEventListener("change", (event) => {
  const input = event.target.closest("[data-tag]");
  if (!input || !window.oneSignal || !window.oneSignal.User.PushSubscription.optedIn) return;
  saveNotifyTags().catch(() => notifyNote("Не удалось сохранить выбор тем."));
});

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-notify]");
  if (!button) return;
  const OneSignal = window.oneSignal;
  if (!OneSignal) {
    notifyNote("Сервис уведомлений ещё не ответил. Откройте сайт по HTTPS и попробуйте ещё раз.");
    return;
  }
  const action = button.getAttribute("data-notify");
  if (action === "off") {
    OneSignal.User.PushSubscription.optOut().then(() => renderNotify()).catch(() => notifyNote("Не удалось выключить."));
    return;
  }
  void enableNotifications(OneSignal);
});

function genuineWaiting(reg) {
  const waiting = reg && reg.waiting;
  if (!waiting || !navigator.serviceWorker.controller) return null;
  const active = reg.active && reg.active.scriptURL;
  if (active && active.includes("appId=") && !waiting.scriptURL.includes("appId=")) return null;
  return waiting;
}

function showUpdateBanner(reg) {
  if (document.getElementById("update-banner") || !genuineWaiting(reg)) return;
  const bar = document.createElement("div");
  bar.id = "update-banner";
  bar.className = "update-banner";
  bar.setAttribute("role", "status");
  bar.innerHTML = `<p>Доступно обновление</p><button type="button">Обновить</button>`;
  bar.querySelector("button").addEventListener("click", () => {
    const waiting = genuineWaiting(reg) || reg.waiting;
    if (!waiting) {
      bar.remove();
      return;
    }
    let done = false;
    const reloadOnce = () => {
      if (done) return;
      done = true;
      const token = waiting.scriptURL;
      if (sessionStorage.getItem("kostya-sw-reload") === token) return;
      sessionStorage.setItem("kostya-sw-reload", token);
      location.reload();
    };
    navigator.serviceWorker.addEventListener("controllerchange", reloadOnce, { once: true });
    waiting.postMessage({ type: "SKIP_WAITING" });
    window.setTimeout(reloadOnce, 1200);
  });
  document.body.appendChild(bar);
}

async function attachUpdateWatch() {
  if (!("serviceWorker" in navigator) || window.__kostyaSwWatch) return;
  const scopeUrl = new URL(workerTarget().scope, location.origin).href;
  let reg = null;
  for (let attempt = 0; attempt < 5; attempt++) {
    reg = await navigator.serviceWorker.getRegistration(scopeUrl);
    if (reg) break;
    await new Promise((resolve) => window.setTimeout(resolve, 200));
  }
  if (!reg) return;
  window.__kostyaSwWatch = true;
  const arm = () => showUpdateBanner(reg);
  arm();
  reg.addEventListener("updatefound", () => {
    const worker = reg.installing;
    if (!worker) return;
    worker.addEventListener("statechange", () => {
      if (worker.state === "installed") arm();
    });
  });
  if (!navigator.serviceWorker.controller) {
    const worker = reg.installing || reg.waiting;
    if (worker) {
      const kick = () => {
        if (worker.state === "installed") worker.postMessage({ type: "SKIP_WAITING" });
      };
      worker.addEventListener("statechange", kick);
      kick();
    }
  }
}

function setupNotifications() {
  if (!window.OneSignalDeferred) window.OneSignalDeferred = [];
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      resolve();
    };
    window.OneSignalDeferred.push(async (OneSignal) => {
      const target = workerTarget();
      try {
        await OneSignal.init({
          appId: ONESIGNAL_APP_ID,
          serviceWorkerPath: target.path,
          serviceWorkerParam: { scope: target.scope },
          notifyButton: { enable: false },
          welcomeNotification: { disable: true },
          promptOptions: { slidedown: { prompts: [{ type: "push", autoPrompt: false }] } },
        });
        window.oneSignal = OneSignal;
        OneSignal.User.PushSubscription.addEventListener("change", () => renderNotify());
      } catch (error) {
        window.oneSignal = null;
      }
      try {
        await attachUpdateWatch();
      } catch (error) {}
      renderNotify();
      finish();
    });
    window.setTimeout(finish, 4000);
  });
}

function currentTabIndex() {
  const page = document.body.dataset.page;
  const index = TAB_PAGES.findIndex((item) => item.id === page);
  return index >= 0 ? index : 0;
}

function tabSwipeReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function isNoSwipeTarget(node) {
  let el = node instanceof Element ? node : null;
  while (el && el !== document.body && el !== document.documentElement) {
    if (el.hasAttribute("data-noswipe")) return true;
    const tag = el.tagName;
    if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return true;
    if (tag === "CANVAS") return true;
    if (tag === "SVG" && (el.closest("#trend-panel") || el.closest("svg.points"))) return true;
    if (el.closest("#trend-panel, .table-scroll, svg.points, .chart-scroll, .segmented, .news-list")) return true;
    const style = window.getComputedStyle(el);
    const ox = style.overflowX;
    if ((ox === "auto" || ox === "scroll" || ox === "overlay") && el.scrollWidth > el.clientWidth + 2) {
      return true;
    }
    el = el.parentElement;
  }
  return false;
}

let tabSwipeNavigating = false;

function navigateTabSwipe(direction) {
  if (tabSwipeNavigating) return;
  const index = currentTabIndex();
  const nextIndex = direction === "next" ? index + 1 : index - 1;
  if (nextIndex < 0 || nextIndex >= TAB_PAGES.length) return;
  tabSwipeNavigating = true;
  const enter = direction === "next" ? "from-right" : "from-left";
  try {
    sessionStorage.setItem("tabSwipeEnter", enter);
  } catch (error) {}
  const reduced = tabSwipeReducedMotion();
  const content = document.getElementById("content");
  if (content && !reduced) {
    content.classList.add(direction === "next" ? "page-exit-to-left" : "page-exit-to-right");
  }
  const target = TAB_PAGES[nextIndex].href;
  const go = () => {
    location.href = target;
  };
  if (reduced || !content) go();
  else window.setTimeout(go, TAB_SWIPE_ANIM_MS);
}

function applyTabSwipeEnter() {
  let enter = "";
  try {
    enter = sessionStorage.getItem("tabSwipeEnter") || "";
    sessionStorage.removeItem("tabSwipeEnter");
  } catch (error) {
    return;
  }
  if (!enter || tabSwipeReducedMotion()) return;
  const content = document.getElementById("content");
  if (!content) return;
  content.classList.add(enter === "from-right" ? "page-enter-from-right" : "page-enter-from-left");
  requestAnimationFrame(() => {
    content.classList.add("page-enter-active");
  });
  const clear = () => {
    content.classList.remove("page-enter-from-right", "page-enter-from-left", "page-enter-active");
  };
  content.addEventListener("animationend", clear, { once: true });
  window.setTimeout(clear, TAB_SWIPE_ANIM_MS + 80);
}

function setupTabSwipe() {
  let start = null;
  let blocked = false;

  document.addEventListener(
    "touchstart",
    (event) => {
      if (tabSwipeNavigating || event.touches.length !== 1) return;
      const touch = event.touches[0];
      const w = window.innerWidth;
      if (touch.clientX < TAB_SWIPE_EDGE_PX || touch.clientX > w - TAB_SWIPE_EDGE_PX) {
        blocked = true;
        start = null;
        return;
      }
      if (isNoSwipeTarget(event.target)) {
        blocked = true;
        start = null;
        return;
      }
      blocked = false;
      start = { x: touch.clientX, y: touch.clientY, time: Date.now() };
    },
    { passive: true }
  );

  document.addEventListener(
    "touchend",
    (event) => {
      if (blocked || !start || tabSwipeNavigating) {
        start = null;
        blocked = false;
        return;
      }
      const touch = event.changedTouches[0];
      if (!touch) {
        start = null;
        return;
      }
      const dx = touch.clientX - start.x;
      const dy = touch.clientY - start.y;
      const dt = Date.now() - start.time;
      start = null;
      blocked = false;
      if (dt > TAB_SWIPE_MAX_MS) return;
      if (Math.abs(dx) < TAB_SWIPE_MIN_DX) return;
      if (Math.abs(dx) < 1.5 * Math.abs(dy)) return;
      if (dx < 0) navigateTabSwipe("next");
      else navigateTabSwipe("prev");
    },
    { passive: true }
  );
}

async function init() {
  const status = document.getElementById("load-state");
  if (status && !status.hidden && !status.classList.contains("error")) {
    status.textContent = "Загрузка…";
  }
  try {
    data = await loadJson("data.json");
    state.game = data.gameLogs.defaultId;
    state.trend = data.trend.defaultId;
    try {
      newsData = await loadJson("news.json");
    } catch (newsError) {
      newsData = null;
    }
    render();
    clearLoadState(status);
  } catch (error) {
    if (status) {
      status.hidden = false;
      status.classList.add("error");
      status.textContent = loadErrorMessage(error);
    }
    const app = document.getElementById("app");
    if (app) app.hidden = true;
  }
  void setupNotifications();
}

applyTabSwipeEnter();
setupTabSwipe();
init();
window.addEventListener("pageshow", (event) => {
  if (event.persisted) init();
});
