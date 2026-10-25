#!/usr/bin/env python3
"""Обновляет data.json и news.json из открытых источников.

Идентификатор игрока используется только в запросе к API и в файлы сайта
не записывается: ни числом, ни ссылкой. Отчество и точная дата рождения тоже.
Если источник молчит или ответ неожиданной формы, соответствующий блок
остаётся как был.
"""

from __future__ import annotations

import copy
import html
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://reg.infobasket.su"
PARENT_COMP = 142760
TEAM_ID = 38872
ONESIGNAL_APP_ID = "7a9c32d2-ee00-46aa-9cfd-009842e4dab4"
SITE = "https://workjobdub-del.github.io/kostya-baske/"
TAG_GAMES = "Игры"
TAG_NEWS = "Новости команды"
# Только для запроса. На сайт и в JSON игрока не попадает.
PERSON_ID = 424578
MSK = timezone(timedelta(hours=3))
UA = "Mozilla/5.0 (compatible; kostya-baske-update/1.0; +https://github.com/workjobdub-del/kostya-baske)"
MONTHS = [
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
]
MONTH_INDEX = {name: index + 1 for index, name in enumerate(MONTHS)}
NEWS_CAPTION = (
    "Короткие выжимки из открытых постов. Метка «2014» — в тексте есть команда 2014 года, "
    "иначе «клуб». Личные цифры Кости из новости не дописываем."
)
LOG_COLUMNS = [
    {"key": "date", "label": "Дата"},
    {"key": "opponent", "label": "Соперник"},
    {"key": "score", "label": "Счёт"},
    {"key": "minutes", "label": "Мин"},
    {"key": "points", "label": "Очки"},
    {"key": "fg2", "label": "2-очк."},
    {"key": "rebounds", "label": "Подб"},
    {"key": "assists", "label": "Пер"},
    {"key": "steals", "label": "Перехв"},
    {"key": "turnovers", "label": "Потери"},
]


def today() -> date:
    return datetime.now(MSK).date()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "*/*", "Connection": "close"},
    )
    last = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(0.8 * (attempt + 1))
    raise last


def get_json(url: str):
    raw = fetch(url)
    if raw.lstrip().startswith(b"<"):
        raise ValueError("html")
    body = json.loads(raw.decode("utf-8"))
    if isinstance(body, dict) and body.get("Message") and "GameStats" not in body and "Comps" not in body:
        raise ValueError("message")
    return body


def get_text(url: str) -> str:
    return fetch(url).decode("utf-8", "replace")


def api(path: str):
    time.sleep(0.35)
    return get_json(API + path)


def parse_ru_date(text: str):
    match = re.match(r"^(\d{2})\.(\d{2})\.(\d{2}|\d{4})$", str(text).strip())
    if not match:
        return None
    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def short_date(value: date) -> str:
    return f"{value.day:02d}.{value.month:02d}.{value.year % 100:02d}"


def long_date(value: date) -> str:
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def plain(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("ë", "ё").replace("Ë", "Ё")
    text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]+", "", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    return text.strip(" \n-—")


def letters(text: str) -> int:
    return len(re.findall(r"[A-Za-zА-Яа-яЁё]", text))


def tag_for(text: str) -> str:
    return "2014" if re.search(r"2014", text) else "клуб"


def one_decimal(values) -> float:
    if not values:
        return 0.0
    return math.floor((sum(values) / len(values)) * 10 + 0.5) / 10


def parse_shot(text: str):
    match = re.match(r"(\d+)\s*/\s*(\d+)", str(text or ""))
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def shot_line(pairs) -> str:
    made = sum(item[0] for item in pairs)
    attempts = sum(item[1] for item in pairs)
    if attempts <= 0:
        return "0/0"
    percent = int(math.floor(made * 100 / attempts + 0.5))
    return f"{made}/{attempts}, {percent}%"


def avg_minutes(rows) -> str:
    seconds = []
    for row in rows:
        match = re.match(r"^(\d+):(\d{2})$", str(row.get("minutes") or ""))
        if match:
            seconds.append(int(match.group(1)) * 60 + int(match.group(2)))
    if not seconds:
        return ""
    total = int(math.floor(sum(seconds) / len(seconds) + 0.5))
    return f"{total // 60}:{total % 60:02d}"


def extract_score(text: str):
    # «16:00» в расписании — время начала, не счёт. Счёт в этих текстах без нуля впереди: 62:37.
    for match in re.finditer(r"(?<!\d)(\d{1,3})\s*:\s*(\d{1,3})(?!\d)", text or ""):
        token = match.group(0).replace(" ", "")
        right = match.group(2)
        left = int(match.group(1))
        if re.fullmatch(r"\d{1,2}:\d{2}", token) and left <= 23 and right.startswith("0"):
            continue
        return left, int(right)
    return None


def result_word(ours: int, theirs: int) -> str:
    if ours > theirs:
        return "победа"
    if ours < theirs:
        return "поражение"
    return "ничья"


def ru_count(value, one, few, many) -> str:
    number = abs(int(value))
    n10 = number % 10
    n100 = number % 100
    if n10 == 1 and n100 != 11:
        word = one
    elif 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        word = few
    else:
        word = many
    return f"{value} {word}"


def walk_comps(nodes, found):
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        if node.get("CompType") == 0 and isinstance(node.get("CompID"), int):
            found.append(node["CompID"])
        walk_comps(node.get("Children"), found)


def team_games(calendar):
    games = []
    if not isinstance(calendar, list):
        raise ValueError("calendar")
    for game in calendar:
        if not isinstance(game, dict):
            continue
        if TEAM_ID not in (game.get("TeamAid"), game.get("TeamBid")):
            continue
        when = parse_ru_date(str(game.get("GameDate") or ""))
        if not when:
            continue
        home = game.get("TeamAid") == TEAM_ID
        opponent = game.get("ShortTeamNameBru") if home else game.get("ShortTeamNameAru")
        our = game.get("ShortTeamNameAru") if home else game.get("ShortTeamNameBru")
        if not opponent or not our:
            continue
        games.append(
            {
                "id": game.get("GameID"),
                "date": when,
                "time": str(game.get("GameTimeMsk") or game.get("GameTime") or ""),
                "arena": str(game.get("ArenaRu") or ""),
                "opp": str(opponent),
                "our": str(our),
                "status": game.get("GameStatus") if isinstance(game.get("GameStatus"), int) else None,
                "score_a": game.get("ScoreA") if isinstance(game.get("ScoreA"), int) else None,
                "score_b": game.get("ScoreB") if isinstance(game.get("ScoreB"), int) else None,
                "home": home,
                "comp": str(game.get("CompNameRu") or ""),
            }
        )
    games.sort(key=lambda item: (item["date"], item["time"]))
    return games


def our_score_pair(game):
    if game["score_a"] is None or game["score_b"] is None:
        return None
    if game["home"]:
        return game["score_a"], game["score_b"]
    return game["score_b"], game["score_a"]


def count_stat(item, key) -> int:
    value = item.get(key)
    return int(value) if isinstance(value, int) else 0


def shots(item, key) -> str:
    return str(item.get(key) or "0/0").replace(" ", "")


def public_row(stat) -> dict:
    row = {
        "date": stat["date"],
        "opponent": stat["opponent"],
        "score": stat["score"],
        "minutes": stat["minutes"],
        "points": stat["points"],
        "fg2": stat["fg2"],
        "rebounds": stat["rebounds"],
        "assists": stat["assists"],
        "steals": stat["steals"],
        "turnovers": stat["turnovers"],
        "fg3": stat["fg3"],
        "ft": stat["ft"],
        "offRebounds": stat["offRebounds"],
        "started": stat["started"],
    }
    game_id = stat.get("gameId")
    if isinstance(game_id, int) and game_id != PERSON_ID:
        row["gameId"] = game_id
    return row


def stat_from_player(item, game):
    pair = our_score_pair(game) if game else None
    if pair is None:
        teams = (item.get("Game") or {}).get("GameTeams") or []
        number = item.get("TeamNumber")
        ours = next((team for team in teams if team.get("GameTeamNumber") == number), None)
        theirs = next((team for team in teams if team.get("GameTeamNumber") != number), None)
        if not ours or not theirs:
            return None
        our_score = ours.get("GameTeamScore")
        their_score = theirs.get("GameTeamScore")
        if not isinstance(our_score, int) or not isinstance(their_score, int):
            return None
        pair = (our_score, their_score)
        when = parse_ru_date(str(item.get("GameDate") or ""))
        block = item.get("TeamNameB") if number == 1 else item.get("TeamNameA")
        opponent = str((block or {}).get("CompTeamShortNameRu") or "")
        our_name = "Росток-2014"
        game_id = (item.get("Game") or {}).get("GameID")
        comp = ""
    else:
        when = game["date"]
        opponent = game["opp"]
        our_name = game["our"]
        game_id = game["id"]
        comp = game["comp"]
        our_score, their_score = pair
    if not when or not opponent:
        return None
    our_score, their_score = pair
    word = result_word(our_score, their_score)
    source = item
    return {
        "date": short_date(when),
        "when": when,
        "opponent": opponent,
        "our_name": our_name,
        "our": our_score,
        "their": their_score,
        "score": f"{our_score}:{their_score}, {word}",
        "result": word,
        "minutes": str(source.get("PlayedTime") or "0:00"),
        "points": count_stat(source, "Points"),
        "fg2": shots(source, "Shots2"),
        "fg3": shots(source, "Shots3"),
        "ft": shots(source, "Shots1"),
        "rebounds": count_stat(source, "Rebound"),
        "offRebounds": count_stat(source, "OffRebound"),
        "assists": count_stat(source, "Assist"),
        "steals": count_stat(source, "Steal"),
        "turnovers": count_stat(source, "Turnover"),
        "fouls": count_stat(source, "Foul"),
        "started": bool(source.get("IsStart")),
        "gameId": game_id,
        "comp": comp,
    }


def stat_from_log(item):
    if not isinstance(item, dict):
        return None
    return stat_from_player(item, None)


def calendar_for(comp_id):
    calendar = api(f"/Comp/GetCalendar/?comps={comp_id}&format=json")
    return team_games(calendar)


def choose_comps(saved):
    found = []
    try:
        games = calendar_for(saved)
        if games:
            found.append((saved, games))
            print(f"календарь {saved}: игр команды {len(games)}", flush=True)
    except Exception as exc:
        print(f"календарь {saved}: {type(exc).__name__}", flush=True)
    comp_ids = []
    try:
        issue = api(f"/Widget/CompIssue/{PARENT_COMP}?format=json")
        if not isinstance(issue, dict):
            raise ValueError("issue")
        walk_comps(issue.get("Comps"), comp_ids)
    except Exception as exc:
        print(f"сетка турнира: {type(exc).__name__}", flush=True)
    # Соседние группы и этапы — чтобы заметить переезд. Не больше шести запросов.
    for comp_id in [item for item in comp_ids if item != saved][:6]:
        try:
            games = calendar_for(comp_id)
        except Exception as exc:
            print(f"календарь {comp_id}: {type(exc).__name__}", flush=True)
            continue
        if games:
            found.append((comp_id, games))
            print(f"календарь {comp_id}: игр команды {len(games)}", flush=True)
    if not found:
        raise ValueError("team-comp")
    found.sort(key=lambda item: (max(game["date"] for game in item[1]), item[0] == saved, item[0]))
    return found


def parse_standings(payload):
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError("standings")
    rows = []
    for item in payload:
        name = ((item.get("CompTeamName") or {}).get("CompTeamShortNameRu"))
        place = item.get("Place")
        table = item.get("Standings") or {}
        if not name or not isinstance(place, int):
            raise ValueError("row")
        values = [
            table.get("StandingGame"),
            table.get("StandingWin"),
            table.get("StandingLose"),
            table.get("StandingPoints"),
            table.get("StandingGoalPlus"),
            table.get("StandingGoalMinus"),
        ]
        if not all(isinstance(value, int) and value >= 0 for value in values):
            raise ValueError("numbers")
        rows.append(
            {
                "team": f"{place}. {name}",
                "played": str(values[0]),
                "wins": str(values[1]),
                "losses": str(values[2]),
                "points": str(values[3]),
                "scored": str(values[4]),
                "conceded": str(values[5]),
                "_place": place,
            }
        )
        if item.get("TeamID") == TEAM_ID:
            rows[-1]["highlight"] = True
    rows.sort(key=lambda row: row["_place"])
    for row in rows:
        del row["_place"]
    if sum(1 for row in rows if row.get("highlight")) != 1:
        raise ValueError("team")
    return rows


def format_match(game, has_protocol, now):
    when = f"{game['date'].day} {MONTHS[game['date'].month - 1]}"
    clock = f", {game['time']}" if game["time"] else ""
    arena = f", зал «{game['arena']}»" if game["arena"] else ""
    score = ""
    pair = our_score_pair(game) if game["status"] == 1 else None
    if pair:
        score = f" Счёт {pair[0]}:{pair[1]}, {result_word(*pair)}."
    if game["status"] == 1:
        status = "Личный протокол есть" if has_protocol else "Личного протокола нет"
    elif game["date"] < now:
        status = "Личного протокола нет"
    else:
        status = "Ещё не сыгран"
    detail = f"{when}{clock}{arena}.{score}"
    return {"title": f"{game['our']} — {game['opp']}", "detail": detail, "status": status}


def merge_matches(old, games, protocol_dates, now):
    merged = []
    for game in games:
        if game["status"] != 1 and game["date"] < now:
            kept = next(
                (
                    item
                    for item in old
                    if game["opp"] in str(item.get("title", "")) and extract_score(item.get("detail", ""))
                ),
                None,
            )
            if kept:
                merged.append(kept)
                continue
        merged.append(format_match(game, short_date(game["date"]) in protocol_dates, now))
    return merged


def plaque_for(rows, matches):
    ours = next(row for row in rows if row.get("highlight"))
    if int(ours["played"]) > 0:
        return ""
    for match in matches:
        score = extract_score(match.get("detail", ""))
        if not score:
            continue
        return f"Таблица ещё не обновлена: {result_word(*score)} {score[0]}:{score[1]}"
    return ""


def season_object(rows, group_name):
    letter = ""
    match = re.search(r"Группа\s+([АБВГA-D])", group_name or "")
    if match:
        letter = match.group(1).replace("A", "А").replace("B", "Б")
        letter = f", группа {letter}"
    starts = sum(1 for row in rows if row.get("started") is True)
    return {
        "id": "mos2627",
        "name": f"2026/27{letter}, Росток-2014",
        "games": f"{len(rows)} ({starts})",
        "minutes": avg_minutes(rows),
        "points": one_decimal([row["points"] for row in rows]),
        "rebounds": one_decimal([row["rebounds"] for row in rows]),
        "assists": one_decimal([row["assists"] for row in rows]),
        "steals": one_decimal([row["steals"] for row in rows]),
        "turnovers": one_decimal([row["turnovers"] for row in rows]),
        "fg2": shot_line([parse_shot(row.get("fg2")) for row in rows]),
        "fg3": shot_line([parse_shot(row.get("fg3")) for row in rows]),
        "ft": shot_line([parse_shot(row.get("ft")) for row in rows]),
        "highlight": True,
    }


def paragraphs_for(stat, rows):
    start = "Вышел в старте" if stat["started"] else "Вышел со скамейки"
    first = f"{start} и сыграл {stat['minutes']}."
    minutes = avg_minutes(rows)
    if minutes:
        first += f" В среднем за эти игры сезона — {minutes}."
    points = one_decimal([row["points"] for row in rows])
    if stat["points"] == 0:
        second = "Очков в протоколе нет."
    elif len(rows) > 1 and stat["points"] > points:
        second = f"Очков {stat['points']}: больше среднего {str(points).replace('.', ',')}."
    else:
        shown = str(points).replace(".", ",")
        second = f"Очков {stat['points']}. Среднее за эти игры — {shown}."
    bits = []
    if stat["offRebounds"]:
        best = len(rows) > 1 and stat["offRebounds"] >= max(row.get("offRebounds") or 0 for row in rows)
        tail = " Больше, чем в остальных играх этого журнала." if best else ""
        bits.append(f"Подборы {stat['rebounds']}, в нападении {stat['offRebounds']}.{tail}")
    if stat["assists"] or stat["turnovers"]:
        bits.append(f"Передачи {stat['assists']}, потери {stat['turnovers']}.")
    if stat["steals"]:
        bits.append(f"Перехваты {stat['steals']}.")
    parts = [first, second]
    if bits:
        parts.append(" ".join(bits))
    return parts


def kind_line(stat) -> str:
    bits = []
    if stat["points"]:
        bits.append(ru_count(stat["points"], "очко", "очка", "очков"))
    if stat["rebounds"]:
        bits.append(ru_count(stat["rebounds"], "подбор", "подбора", "подборов"))
    if stat["assists"]:
        bits.append(ru_count(stat["assists"], "передача", "передачи", "передач"))
    if stat["steals"]:
        bits.append(ru_count(stat["steals"], "перехват", "перехвата", "перехватов"))
    if not bits:
        return "В протоколе за эту игру очков нет, выход на площадку есть."
    return "По протоколу: " + ", ".join(bits) + "."


def ensure_log(data):
    tournaments = data["gameLogs"]["tournaments"]
    found = next((item for item in tournaments if item.get("id") == "mos2627"), None)
    if found:
        return found
    found = {
        "id": "mos2627",
        "label": "Росток-2014, 26/27",
        "chart": {"labelKey": "date", "labelPrefix": 5, "valueKey": "points"},
        "columns": LOG_COLUMNS,
        "rows": [],
    }
    tournaments.insert(0, found)
    return found


def apply_protocols(data, stats, notes):
    if not stats:
        notes.append("личный протокол: в API пока нет строк игрока, блок «Последний матч» не трогал")
        return set()
    log = ensure_log(data)
    known = {row.get("date") for row in log["rows"]}
    added = 0
    for stat in sorted(stats, key=lambda item: item["when"]):
        if stat["date"] in known:
            continue
        log["rows"].append(public_row(stat))
        known.add(stat["date"])
        added += 1
    if added:
        notes.append(f"личный протокол: новых игр {added}")
    else:
        notes.append("личный протокол: новых игр нет")
    if not log["rows"]:
        return {stat["date"] for stat in stats}
    group = next((stat.get("comp") or "" for stat in reversed(stats) if stat.get("comp")), "")
    season = season_object(log["rows"], group)
    seasons = data["tournamentStats"]["seasons"]
    for item in seasons:
        if item.get("id") == "mos2627" or str(item.get("name", "")).startswith("2026/27"):
            item.clear()
            item.update(season)
            break
    else:
        seasons.append(season)
    for item in seasons:
        if item.get("id") != "mos2627" and not str(item.get("name", "")).startswith("2026/27"):
            item.pop("highlight", None)
    data["gameLogs"]["defaultId"] = "mos2627"
    latest = max(stats, key=lambda item: item["when"])
    rows = log["rows"]
    data["lastMatch"] = {
        "caption": f"Последний личный протокол: {long_date(latest['when'])}, {latest['opponent']}, {latest['our']}:{latest['their']}.",
        "facts": [
            {"label": "Матч", "value": f"{latest['our_name']} — {latest['opponent']}, {latest['our']}:{latest['their']}"},
            {"label": "Дата и стадия", "value": long_date(latest["when"]) + (f", {latest['comp']}" if latest.get("comp") else "")},
            {"label": "Результат", "value": latest["result"].capitalize()},
        ],
        "columns": ["Старт", "Мин", "Очки", "2-очк.", "Штраф", "Подб (нап)", "Пер", "Перехв", "Потери", "Фолы"],
        "rows": [[
            "да" if latest["started"] else "нет",
            latest["minutes"],
            str(latest["points"]),
            latest["fg2"],
            latest["ft"],
            f"{latest['rebounds']} ({latest['offRebounds']})",
            str(latest["assists"]),
            str(latest["steals"]),
            str(latest["turnovers"]),
            str(latest["fouls"]),
        ]],
        "paragraphs": paragraphs_for(latest, rows),
    }
    mama = data["mama"]["games"]
    have = {item.get("date") for item in mama}
    for stat in sorted(stats, key=lambda item: item["when"], reverse=True):
        if stat["date"] in have:
            continue
        mama.insert(0, {"date": stat["date"], "plus": kind_line(stat)})
        have.add(stat["date"])
    mama.sort(key=lambda item: parse_ru_date(item.get("date") or "") or date.min, reverse=True)
    del mama[5:]
    return {stat["date"] for stat in stats}


def refresh_body(data, notes):
    try:
        page = api(f"/Widget/PlayerPage/{PERSON_ID}?format=json")
    except Exception:
        notes.append("рост: источник не ответил, строка профиля прежняя")
        return
    height = page.get("PersonHeight") if isinstance(page, dict) else None
    weight = page.get("PersonWeight") if isinstance(page, dict) else None
    if not (isinstance(height, int) and isinstance(weight, int) and 120 <= height <= 220 and 25 <= weight <= 120):
        notes.append("рост: в ответе нет понятных роста и веса, строка прежняя")
        return
    value = f"{height} см, {weight} кг"
    for item in data["profile"]["items"]:
        if item.get("label") == "Рост и вес" and item.get("value") != value:
            item["value"] = value
            notes.append("рост: строка профиля обновлена")
            return
    notes.append("рост: без изменений")


def update_basket(data, notes):
    saved = data.get("sync", {}).get("compId") or 153217
    try:
        comps = choose_comps(saved)
    except Exception as exc:
        notes.append(f"календарь: источник не принят ({type(exc).__name__}), матчи и таблица прежние")
        refresh_body(data, notes)
        return
    chosen, games = comps[-1]
    data.setdefault("sync", {})["compId"] = chosen
    if chosen != saved:
        notes.append(f"команда переехала в другой этап, comp {chosen}")
    stats = []
    read_any = False
    seen = set()
    for comp_id, comp_games in comps:
        try:
            payload = api(
                f"/Widget/PlayerStats/{PERSON_ID}?format=json&compId={comp_id}&team={TEAM_ID}&filter=1"
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("GameStats"), list):
                raise ValueError("player-stats")
            read_any = True
        except Exception as exc:
            notes.append(f"журнал comp {comp_id}: не прочитан ({type(exc).__name__}), старые строки журнала на месте")
            continue
        by_id = {game["id"]: game for game in comp_games}
        for item in payload["GameStats"]:
            stat = stat_from_log(item)
            if not stat or stat.get("gameId") in seen:
                continue
            calendar_game = by_id.get(stat.get("gameId"))
            if calendar_game:
                stat["comp"] = calendar_game["comp"]
                stat["our_name"] = calendar_game["our"]
                stat["opponent"] = calendar_game["opp"]
            seen.add(stat.get("gameId"))
            stats.append(stat)
    if read_any:
        finished = [game for game in games if game["status"] == 1 and game["id"] not in seen]
        for game in sorted(finished, key=lambda item: item["date"], reverse=True)[:4]:
            try:
                online = api(f"/Widget/GetOnline/{game['id']}?format=json")
            except Exception:
                continue
            player = None
            for team in (online or {}).get("GameTeams") or []:
                for person in team.get("Players") or []:
                    if person.get("PersonID") == PERSON_ID:
                        player = person
            if not player:
                continue
            stat = stat_from_player(player, game)
            if stat and stat.get("gameId") not in seen:
                stats.append(stat)
                seen.add(stat.get("gameId"))
    protocol_dates = apply_protocols(data, stats, notes) if read_any else set()
    if not read_any:
        notes.append("личный протокол: журнал не прочитан, прежние строки на месте")
    try:
        rows = parse_standings(api(f"/Widget/CompTeamResults/{chosen}?format=json"))
    except Exception:
        notes.append("таблица: источник не принят, прежние строки на месте")
        rows = None
    now = today()
    old_matches = data["season"].get("matches") or []
    try:
        matches = merge_matches(old_matches, games, protocol_dates, now)
    except Exception:
        notes.append("матчи: не собрал, список прежний")
        matches = None
    if rows is not None and rows != data["season"]["standings"]["rows"]:
        data["season"]["standings"]["rows"] = rows
        ours = next(row for row in rows if row["highlight"])
        data["season"]["caption"] = (
            f"На {long_date(now)}. В таблице группы у «Ростка» {ours['wins']} побед и {ours['losses']} поражений."
        )
        notes.append("таблица: обновлена")
    elif rows is not None:
        notes.append("таблица: без изменений")
    if matches is not None and matches != old_matches:
        data["season"]["matches"] = matches
        notes.append("календарь: список матчей обновлён")
    elif matches is not None:
        notes.append("календарь: новых матчей нет")
    if rows is not None and matches is not None:
        data["season"]["plaque"] = plaque_for(rows, matches)
    pending = pending_game(games, protocol_dates, old_matches, now)
    if pending and pending != data["mama"].get("pending"):
        old = data["mama"].get("pending") or {}
        same_score = extract_score(old.get("text", "")) == extract_score(pending["text"])
        if old.get("title") == pending["title"] and same_score:
            notes.append("игра без протокола: текст оставлен как был")
        else:
            data["mama"]["pending"] = pending
            notes.append("игра без протокола: плашка обновлена")
    refresh_body(data, notes)


def pending_game(games, protocol_dates, old_matches, now):
    past = [game for game in games if game["date"] <= now and short_date(game["date"]) not in protocol_dates]
    if not past:
        return {"title": "", "text": ""}
    game = past[-1]
    pair = our_score_pair(game) if game["status"] == 1 else None
    if pair is None:
        for item in old_matches:
            if game["opp"] in str(item.get("title", "")):
                pair = extract_score(item.get("detail", ""))
                break
    title = f"{game['date'].strftime('%d.%m.%Y')} · {game['opp'].split('-')[0]}"
    if pair:
        text = (
            f"Команда сыграла {pair[0]}:{pair[1]}. Это счёт команды, не личная строка. "
            "Очков Кости за этот матч на сайте нет."
        )
    else:
        text = "Матч уже в календаре, личного протокола на сайте нет. Счёт команды отсюда не дописываю."
    return {"title": title, "text": text}


def make_title(text: str) -> str:
    line = text.split("\n", 1)[0].strip()
    sentence = re.split(r"(?<=[.!])\s", line)[0].strip()
    if len(sentence) > 90:
        sentence = sentence[:87].rstrip() + "…"
    return sentence or "Пост клуба"


def make_excerpt(text: str) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    if len(flat) > 280:
        flat = flat[:277].rstrip() + "…"
    return flat


def parse_telegram(page: str):
    posts = []
    for part in re.split(r'<div class="tgme_widget_message_wrap', page)[1:]:
        post = re.search(r'data-post="(rostokmsk/\d+)"', part)
        stamp = re.search(r'<time datetime="(\d{4}-\d{2}-\d{2})', part)
        body = re.search(r'<div class="tgme_widget_message_text js-message_text"[^>]*>(.*?)</div>', part, re.S)
        if not post or not stamp or not body:
            continue
        raw = re.sub(r"<br\s*/?>", "\n", body.group(1))
        raw = plain(re.sub(r"<[^>]+>", "", raw))
        if letters(raw) < 20:
            continue
        message_id = int(post.group(1).split("/")[1])
        posts.append(
            {
                "id": message_id,
                "link": f"https://t.me/{post.group(1)}",
                "date": stamp.group(1),
                "title": make_title(raw),
                "text": make_excerpt(raw),
                "tag": tag_for(raw),
                "sort": message_id,
            }
        )
    return posts


def fetch_telegram(notes):
    cutoff = (today() - timedelta(days=90)).isoformat()
    before = None
    found = []
    try:
        for _ in range(3):
            url = "https://t.me/s/rostokmsk" + (f"?before={before}" if before else "")
            page = get_text(url)
            batch = parse_telegram(page)
            if not batch:
                break
            found.extend(batch)
            before = min(item["id"] for item in batch)
            if min(item["date"] for item in batch) < cutoff:
                break
            time.sleep(0.4)
    except Exception:
        notes.append("Telegram: страница не прочитана, прежние новости на месте")
        return []
    fresh = [item for item in found if item["date"] >= cutoff]
    notes.append(f"Telegram: прочитано постов {len(fresh)}")
    return fresh


def parse_club(page: str, now: date):
    articles = re.findall(r"<article class=\"page-news-item\">(.*?)</article>", page, re.S)
    cutoff = now - timedelta(days=60)
    year = now.year
    last = None
    posts = []
    for article in articles:
        stamp = re.search(r"page-news-item-dt\">(.*?)</div>", article, re.S)
        link = re.search(r'href="/news\?id=(\d+)"[^>]*>([^<]+)</a>', article)
        paragraph = re.search(r"<p>(.*?)</p>", article, re.S)
        if not stamp or not link:
            continue
        cleaned = plain(re.sub(r"<[^>]+>", " ", stamp.group(1)))
        found = re.search(r"(\d{1,2})\s+([А-Яа-яЁё]+)", cleaned)
        if not found or found.group(2).lower() not in MONTH_INDEX:
            continue
        month = MONTH_INDEX[found.group(2).lower()]
        try:
            candidate = date(year, month, int(found.group(1)))
        except ValueError:
            continue
        if last and candidate > last + timedelta(days=2):
            year -= 1
            candidate = date(year, month, int(found.group(1)))
        if candidate > now + timedelta(days=1):
            year -= 1
            try:
                candidate = date(year, month, int(found.group(1)))
            except ValueError:
                continue
        last = candidate
        if candidate < cutoff:
            break
        title = plain(link.group(2))
        excerpt = plain(re.sub(r"<[^>]+>", " ", paragraph.group(1))) if paragraph else title
        text = f"{title}. {excerpt}".strip() if excerpt and excerpt not in title else title
        if letters(text) < 20:
            continue
        posts.append(
            {
                "id": int(link.group(1)),
                "link": f"https://rostokmsk.ru/news?id={link.group(1)}",
                "date": candidate.isoformat(),
                "title": make_title(title),
                "text": make_excerpt(text),
                "tag": tag_for(f"{title} {excerpt}"),
                "sort": int(link.group(1)),
            }
        )
    return posts


def fetch_club(notes):
    try:
        page = get_text("https://rostokmsk.ru/news/")
        posts = parse_club(page, today())
    except Exception:
        notes.append("сайт клуба: страница не прочитана, прежние новости на месте")
        return []
    notes.append(f"сайт клуба: свежих заметок {len(posts)}")
    return posts


def merge_posts(news, incoming, notes):
    posts = news["posts"]
    by_link = {item.get("link"): item for item in posts}
    added = 0
    for item in incoming:
        current = by_link.get(item["link"])
        if current:
            if current.get("sort") != item["sort"]:
                current["sort"] = item["sort"]
            continue
        posts.append(
            {
                "date": item["date"],
                "sort": item["sort"],
                "tag": item["tag"],
                "title": item["title"],
                "text": item["text"],
                "link": item["link"],
            }
        )
        by_link[item["link"]] = posts[-1]
        added += 1
        if added >= 80:
            notes.append("новости: за один заход беру не больше 80 записей")
            break
    if news.get("caption") != NEWS_CAPTION:
        news["caption"] = NEWS_CAPTION
    notes.append(f"новости: новых записей {added}")


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def assert_safe(data, news, u12_before):
    blob = json.dumps({"data": data, "news": news}, ensure_ascii=False)
    for forbidden in ("424578", "Кириллович", "26.03.2014"):
        if forbidden in blob:
            raise SystemExit(f"остановка: в данных оказалось «{forbidden}», файлы не записал")
    if data["player"]["name"] != "Костя Дербышев" or str(data["player"].get("number")) != "7":
        raise SystemExit("остановка: имя или номер изменились бы, файлы не записал")
    u12 = next(item for item in data["gameLogs"]["tournaments"] if item.get("id") == "u12")
    if u12["rows"] != u12_before:
        raise SystemExit("остановка: журнал U12 изменился бы, файлы не записал")
    for post in news["posts"]:
        if post.get("tag") not in ("2014", "клуб") or not str(post.get("link", "")).startswith("https://"):
            raise SystemExit("остановка: новость без метки или нормальной ссылки, файлы не записал")


def self_test():
    page = """
    <div class="tgme_widget_message_wrap"><div data-post="rostokmsk/3110">
      <time datetime="2026-10-25T12:00:00+00:00"></time>
      <div class="tgme_widget_message_text js-message_text">Команда 2014 г.р. обыграла «Гольяново» 70:50.</div>
    </div></div>
    <div class="tgme_widget_message_wrap"><div data-post="rostokmsk/3111">
      <time datetime="2026-10-25T13:00:00+00:00"></time>
      <div class="tgme_widget_message_text js-message_text">🚀</div>
    </div></div>
    """
    posts = parse_telegram(page)
    assert len(posts) == 1 and posts[0]["tag"] == "2014" and posts[0]["link"].endswith("/3110")
    assert tag_for("набор 2016 года") == "клуб"
    rows = parse_standings(
        [
            {
                "Place": 2,
                "TeamID": 1,
                "CompTeamName": {"CompTeamShortNameRu": "Соперник"},
                "Standings": {"StandingGame": 1, "StandingWin": 0, "StandingLose": 1, "StandingPoints": 1, "StandingGoalPlus": 30, "StandingGoalMinus": 40},
            },
            {
                "Place": 1,
                "TeamID": TEAM_ID,
                "CompTeamName": {"CompTeamShortNameRu": "Росток-2014"},
                "Standings": {"StandingGame": 0, "StandingWin": 0, "StandingLose": 0, "StandingPoints": 0, "StandingGoalPlus": 0, "StandingGoalMinus": 0},
            },
        ]
    )
    assert rows[0]["highlight"] is True and rows[0]["team"].startswith("1.")
    old = [{"title": "Росток-2014 — Гольяново-2014-2", "detail": "По новости клуба команда выиграла 62:37.", "status": "Личного протокола нет"}]
    game = {
        "id": 1,
        "date": date(2026, 10, 24),
        "time": "16:00",
        "arena": "Росток",
        "opp": "Гольяново-2014-2",
        "our": "Росток-2014",
        "status": 0,
        "score_a": 0,
        "score_b": 0,
        "home": True,
        "comp": "Группа А",
    }
    merged = merge_matches(old, [game], set(), date(2026, 10, 25))
    assert merged == old
    assert extract_score("24 октября, 16:00, зал. Команда выиграла 62:37.") == (62, 37)
    assert extract_score("Счёт 16:8, победа.") == (16, 8)
    assert plaque_for(rows, old) == "Таблица ещё не обновлена: победа 62:37"
    stat = stat_from_log(
        {
            "GameDate": "24.10.2026",
            "TeamNumber": 1,
            "TeamNameA": {"CompTeamShortNameRu": "Росток-2014"},
            "TeamNameB": {"CompTeamShortNameRu": "Гольяново-2014-2"},
            "Game": {"GameID": 5, "GameTeams": [{"GameTeamNumber": 1, "GameTeamScore": 62}, {"GameTeamNumber": 2, "GameTeamScore": 37}]},
            "PlayedTime": "18:02",
            "Points": 8,
            "Shots2": "3/7",
            "Shots3": "0/1",
            "Shots1": "2/2",
            "Rebound": 4,
            "OffRebound": 1,
            "Assist": 2,
            "Steal": 1,
            "Turnover": 3,
            "Foul": 1,
            "IsStart": True,
            "PersonID": PERSON_ID,
            "PersonBirth": "26.03.2014",
        }
    )
    blob = json.dumps(public_row(stat), ensure_ascii=False)
    assert "424578" not in blob and "26.03.2014" not in blob and "Кириллович" not in blob
    assert stat["points"] == 8 and stat["score"].startswith("62:37")
    assert shot_line([(3, 7), (1, 3)]) == "4/10, 40%"
    club = parse_club(
        """<article class="page-news-item"><div class="page-news-item-dt">20<br>сентября</div>
        <h3><a href="/news?id=204">Приглашаем детей 2017–2021 г.р. на занятия баскетболом!</a></h3>
        <div><p>Тренировки в Строгино для новых групп.</p></div></article>""",
        date(2026, 10, 25),
    )
    assert club and club[0]["date"] == "2026-09-20" and club[0]["tag"] == "клуб"
    sample_row = {
        "opponent": "Гольяново-2014-2",
        "score": "62:37, победа",
        "points": 8,
        "rebounds": 3,
        "gameId": 99,
    }
    assert game_push_text(sample_row) == "Новый протокол: Росток 62:37 Гольяново. Костя: 8 очков, 3 подбора"
    calls = []

    def fake_sender(heading, text, url, mode):
        calls.append((heading, text, url, mode))
        return "sent"

    basket = {
        "gameLogs": {"tournaments": [{"id": "mos2627", "rows": [sample_row]}]},
        "pushSent": {"games": [], "news": [], "seeded": True},
    }
    feed = {"posts": [{"tag": "2014", "title": "Победа", "link": "https://t.me/rostokmsk/4000"}]}
    deliver_pushes(basket, feed, [], [], [], sender=fake_sender)
    assert len(calls) == 2 and calls[0][3] == "games" and calls[0][2].endswith("#last")
    assert calls[1][3] == "news" and "4000" not in basket["pushSent"]["games"]
    assert "id:99" in basket["pushSent"]["games"]
    assert feed["posts"][0]["link"] in basket["pushSent"]["news"]
    again = []
    deliver_pushes(basket, feed, [], [], [], sender=lambda *args: again.append(args) or "sent")
    assert again == []
    assert "424578" not in game_push_text(sample_row)


def game_key(row) -> str:
    game_id = row.get("gameId")
    if isinstance(game_id, int):
        return f"id:{game_id}"
    return f"date:{row.get('date')}:{row.get('opponent')}"


def season_rows(data):
    for tournament in data["gameLogs"]["tournaments"]:
        if tournament.get("id") == "mos2627":
            return tournament.get("rows") or []
    return []


def game_push_text(row) -> str:
    pair = extract_score(str(row.get("score") or ""))
    shown = f"{pair[0]}:{pair[1]}" if pair else str(row.get("score") or "").split(",")[0].strip()
    opponent = str(row.get("opponent") or "соперник").split("-")[0].strip() or "соперник"
    bits = [ru_count(row.get("points") or 0, "очко", "очка", "очков")]
    if row.get("rebounds"):
        bits.append(ru_count(row["rebounds"], "подбор", "подбора", "подборов"))
    return f"Новый протокол: Росток {shown} {opponent}. Костя: {', '.join(bits)}"


def news_push_text(post) -> str:
    title = str(post.get("title") or "Новость команды").strip()
    return f"Новость команды 2014: {title}"


def send_notification(heading, text, url, mode):
    key = os.environ.get("ONESIGNAL_REST_API_KEY", "").strip()
    if not key:
        return "no-key"
    body = {
        "app_id": ONESIGNAL_APP_ID,
        "target_channel": "push",
        "headings": {"en": heading, "ru": heading},
        "contents": {"en": text, "ru": text},
        "url": url,
    }
    if mode == "games":
        body["filters"] = [{"field": "tag", "key": TAG_GAMES, "relation": "=", "value": "1"}]
    elif mode == "news":
        body["filters"] = [{"field": "tag", "key": TAG_NEWS, "relation": "=", "value": "1"}]
    else:
        body["included_segments"] = ["Total Subscriptions"]
    raw = json.dumps(body).encode("utf-8")
    last = None
    for scheme in (f"Key {key}", f"Basic {key}"):
        request = urllib.request.Request(
            "https://api.onesignal.com/notifications",
            data=raw,
            headers={"Authorization": scheme, "Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict) and payload.get("errors"):
                return "failed"
            return "sent"
        except urllib.error.HTTPError as exc:
            last = exc.code
            if exc.code not in (401, 403):
                return "failed"
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return "failed"
    return "failed" if last else "failed"


def deliver_pushes(data, news, before_games, before_news, notes, sender=None):
    sender = sender or send_notification
    sent = data.setdefault("pushSent", {"games": [], "news": [], "seeded": False})
    sent.setdefault("games", [])
    sent.setdefault("news", [])
    if not sent.get("seeded"):
        sent["games"] = sorted(set(sent["games"]) | set(before_games))
        sent["news"] = sorted(set(sent["news"]) | set(before_news))
        sent["seeded"] = True
        notes.append("пуш: старые игры и новости отмечены без рассылки")
    known_games = set(sent["games"])
    known_news = set(sent["news"])
    fresh_games = [row for row in season_rows(data) if game_key(row) not in known_games]
    fresh_news = [
        post
        for post in news.get("posts") or []
        if post.get("tag") == "2014" and post.get("link") not in known_news
    ]
    test = os.environ.get("PUSH_TEST") == "1"
    if not fresh_games and not fresh_news and not test:
        return
    if sender is send_notification and not os.environ.get("ONESIGNAL_REST_API_KEY", "").strip():
        notes.append("пуш: секрет ONESIGNAL_REST_API_KEY не задан, отправку пропустил")
        return
    for row in fresh_games:
        result = sender("Новый протокол", game_push_text(row), f"{SITE}#last", "games")
        if result == "no-key":
            notes.append("пуш: секрет ONESIGNAL_REST_API_KEY не задан, отправку пропустил")
            return
        if result == "sent":
            sent["games"].append(game_key(row))
            notes.append(f"пуш: протокол {game_key(row)}")
        else:
            notes.append(f"пуш: протокол {game_key(row)} не ушёл, повторю в следующий раз")
    for post in fresh_news:
        result = sender("Новость команды", news_push_text(post), f"{SITE}mama.html#news", "news")
        if result == "no-key":
            notes.append("пуш: секрет ONESIGNAL_REST_API_KEY не задан, отправку пропустил")
            return
        if result == "sent":
            sent["news"].append(post["link"])
            notes.append("пуш: новость 2014")
        else:
            notes.append("пуш: новость 2014 не ушла, повторю в следующий раз")
    if test:
        result = sender(
            "Проверка",
            "Проверка уведомлений. Если вы это видите, пуши с сайта Кости работают.",
            SITE,
            "test",
        )
        if result == "sent":
            notes.append("пуш: тестовое уведомление отправлено")
        elif result == "no-key":
            notes.append("пуш: секрет ONESIGNAL_REST_API_KEY не задан, тест пропущен")
        else:
            notes.append("пуш: тестовое уведомление не ушло")


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main():
    self_test()
    if "--self-test" in sys.argv:
        print("self-test ok")
        return
    dry = "--dry-run" in sys.argv
    data = load("data.json")
    news = load("news.json")
    before_games = [game_key(row) for row in season_rows(data)]
    before_news = [post.get("link") for post in news.get("posts") or [] if post.get("tag") == "2014"]
    u12_before = copy.deepcopy(next(item["rows"] for item in data["gameLogs"]["tournaments"] if item["id"] == "u12"))
    notes = []
    update_basket(data, notes)
    merge_posts(news, fetch_telegram(notes) + fetch_club(notes), notes)
    deliver_pushes(data, news, before_games, before_news, notes)
    assert_safe(data, news, u12_before)
    fresh_data = canonical(load("data.json"))
    fresh_news = canonical(load("news.json"))
    data_changed = canonical(data) != fresh_data
    news_changed = canonical(news) != fresh_news
    if data_changed or news_changed:
        data["updated"] = today().isoformat()
        data_changed = canonical(data) != fresh_data or data.get("updated") != load("data.json").get("updated")
    assert_safe(data, news, u12_before)
    for line in notes:
        print(line, flush=True)
    if not data_changed and not news_changed:
        print("Изменений нет, файлы не трогал.")
        return
    if dry:
        print("dry-run: файлы не записал.")
        return
    if data_changed:
        (ROOT / "data.json").write_text(dump(data), encoding="utf-8")
    if news_changed:
        (ROOT / "news.json").write_text(dump(news), encoding="utf-8")
    written = " ".join(name for name, flag in (("data.json", data_changed), ("news.json", news_changed)) if flag)
    print(f"Записал {written}. Обновлено: {data['updated']}.")


if __name__ == "__main__":
    main()
