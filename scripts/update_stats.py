#!/usr/bin/env python3
"""Обновляет data.json и news.json из открытых источников.

Идентификатор игрока используется только в запросе к API и в файлы сайта
не записывается: ни числом, ни ссылкой. Отчество и точная дата рождения тоже.
Если источник молчит или ответ неожиданной формы, соответствующий блок
остаётся как был.

Ручные рост и вес лежат в data.json → manualBody. Пока там заданы height и
weight, строка профиля не затирается ответом PlayerPage.
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
U14_TEAM_ID = 79167
U14_COMP_ID = 144801
U14_LOG_ID = "u14circ2627"
MOS_LOG_ID = "mos2627"
PROTOCOL_LOG_IDS = (MOS_LOG_ID, U14_LOG_ID)
U14_COMP_LABEL = "МЛБЛ U14, 26/27"
U14_OUR_NAME = "Росток-2014"
LOG_LABELS = {
    MOS_LOG_ID: "Росток-2014, 26/27",
    U14_LOG_ID: U14_COMP_LABEL,
}
REVIEW_1088400 = (
    "Вторая игра Кости после перелома ноги в августе и первая в МЛБЛ в этом сезоне. "
    "Он вышел со скамейки и провёл на площадке почти 11 минут: после долгого перерыва это нормальный объём, "
    "до привычных 19 минут за игру ещё предстоит вернуться. Команда уступила Takeshot Academy 63:84. "
    "В цифрах пока пусто: один неточный двухочковый и одна потеря. Зато без фолов, а за его минуты команда "
    "проиграла 10 очков, меньше половины итогового отставания. Главное сейчас — спокойно втянуться "
    "и постепенно набирать минуты."
)
MAMA_1088400 = (
    "Костя снова на площадке после перелома! Вторая игра после травмы: он сыграл почти 11 минут против сильного "
    "соперника, держался спокойно и не нарушал правила. Дальше будет только увереннее!"
)
FIXED_GAME_REVIEWS = {
    1088400: {"aiReview": REVIEW_1088400, "aiMama": MAMA_1088400},
}

MANUAL_GAME_TEMPLATES = {
    1130166: {
        "gameId": 1130166,
        "date": "24.10.26",
        "logId": MOS_LOG_ID,
        "oppToken": "Гольяново",
        "title": "Росток-2014 — Гольяново-2014-2",
        "detail": "24 октября, 16:00, зал «Росток». Победа 62:37.",
        "status": "У Кости 6 очков — по данным семьи, официального протокола пока нет",
        "points": 6,
        "source": "семья",
        "noPush": True,
        "aiReview": (
            "Первая игра Кости после перелома ноги в августе и старт Первенства Москвы. "
            "Команда уверенно обыграла «Гольяново» 62:37, а Костя набрал 6 очков — хорошее возвращение. "
            "Остальные цифры появятся, когда выйдет официальный протокол."
        ),
        "aiMama": (
            "Костя вернулся после перелома сразу с победы и сам забил 6 очков — отличное начало сезона!"
        ),
    },
}
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


def strip_u14_suffix(name: str) -> str:
    text = str(name or "").strip()
    if text.endswith(" U14"):
        return text[:-4].strip()
    return text


def normalize_u14_side(name: str, *, our_team: bool = False) -> str:
    text = strip_u14_suffix(str(name or ""))
    if text == U14_OUR_NAME:
        return U14_OUR_NAME
    if our_team and re.search(r"2014", text) and ("ШВСМ" in text or "Росток" in text):
        return U14_OUR_NAME
    if re.search(r"2013", text) and ("ШВСМ" in text or "Росток" in text):
        return "Росток-2013"
    return text


def normalize_u14_opponent(name: str) -> str:
    return normalize_u14_side(name, our_team=False)


def normalize_u14_match_title(title: str) -> str:
    if " — " not in title:
        return title
    left, right = title.split(" — ", 1)
    return f"{normalize_u14_side(left, our_team=True)} — {normalize_u14_side(right, our_team=False)}"


def normalize_u14_game(game: dict) -> None:
    game["our"] = U14_OUR_NAME
    game["opp"] = normalize_u14_opponent(game.get("opp"))
    game["comp"] = U14_COMP_LABEL


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


WORD = {
    1: "один",
    2: "два",
    3: "три",
    4: "четыре",
    5: "пять",
    6: "шесть",
}
WORD_FEM = {1: "одна", 2: "две", 3: "три", 4: "четыре", 5: "пять", 6: "шесть"}
WORD_GEN = {1: "одного", 2: "двух", 3: "трёх", 4: "четырёх", 5: "пяти", 6: "шести"}
WORD_PREP_GAMES = {
    2: "двух матчах",
    3: "трёх матчах",
    4: "четырёх матчах",
    5: "пяти матчах",
    6: "шести матчах",
}


def rate_bucket(value):
    if value is None or value <= 0:
        return "none", 0
    if value < 0.75:
        games = max(2, min(6, int(round(1 / value))))
        return "rare", games
    if value < 1.35:
        return "about_one", 1
    nearest = int(round(value))
    nearest = max(2, min(6, nearest))
    if value < nearest and nearest - value <= 0.45:
        return "almost", nearest
    return "about", nearest


def soft_count(value, with_unit=False):
    kind, number = rate_bucket(value)
    if kind == "almost":
        shown = str(number) if number >= 4 else WORD_FEM.get(number, str(number))
        phrase = f"почти {shown}"
        if with_unit:
            phrase += " раза" if 2 <= number <= 4 else " раз"
        return phrase
    if kind == "about":
        phrase = f"около {WORD_GEN.get(number, str(number))}"
        if with_unit:
            phrase += " раз"
        return phrase
    if kind == "rare":
        games = WORD_FEM.get(number, str(number))
        tail = "игры" if number < 5 else "игр"
        return f"примерно за {games} {tail}"
    return ""


def fold_less(now, before):
    if not before:
        return ""
    ratio = now / before
    if 0.4 <= ratio <= 0.6:
        return "вдвое реже"
    if ratio <= 0.75:
        return "реже"
    return ""


def fold_more(now, before):
    if not before:
        return ""
    ratio = now / before
    if 1.7 <= ratio <= 2.4:
        return "почти вдвое больше"
    if ratio >= 1.25:
        return "больше"
    return ""


def as_float(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def season_games(season) -> int:
    match = re.match(r"(\d+)", str((season or {}).get("games") or ""))
    return int(match.group(1)) if match else 0


def minutes_number(text) -> float:
    match = re.match(r"^(\d+):(\d{2})$", str(text or ""))
    if not match:
        return 0.0
    return int(match.group(1)) + int(match.group(2)) / 60


def shot_percent(text):
    made, attempts = parse_shot(text)
    match = re.search(r"(\d+)\s*%", str(text or ""))
    if match:
        return int(match.group(1)), made, attempts
    if attempts:
        return int(round(made * 100 / attempts)), made, attempts
    return None, made, attempts


def season_token(name: str) -> str:
    low = str(name or "").lower()
    if "первенство москвы" in low:
        return "pm25"
    if "млбл" in low or "u12" in low:
        return "u12"
    if "быстр" in low:
        return "быстр"
    if "движен" in low:
        return "движен"
    if "2026/27" in low or "26/27" in low:
        return "2627"
    return ""


def current_and_previous(data):
    seasons = (data.get("tournamentStats") or {}).get("seasons") or []
    current = next((item for item in seasons if item.get("highlight")), None)
    if current is None and seasons:
        current = seasons[-1]
    if not current:
        return None, None
    index = seasons.index(current)
    previous = seasons[index - 1] if index else None
    return current, previous


def trend_number(data, view_id, category, token):
    for view in (data.get("trend") or {}).get("views") or []:
        if view.get("id") != view_id:
            continue
        try:
            index = view["categories"].index(category)
        except (ValueError, KeyError):
            return None
        for series in view.get("series") or []:
            if token and token in season_token(series.get("name")):
                try:
                    return float(series["values"][index])
                except (TypeError, ValueError, IndexError, KeyError):
                    return None
    return None


def fouls_pair(data, current, previous):
    now = trend_number(data, "ctrl", "Фолы", season_token((current or {}).get("name")))
    before = trend_number(data, "ctrl", "Фолы", season_token((previous or {}).get("name")))
    return now, before


def log_rows(data, season):
    token = season_token((season or {}).get("name"))
    if (season or {}).get("id") == "mos2627":
        token = "2627"
    wanted = {
        "u12": "u12",
        "pm25": "pm2526",
        "быстр": "fb",
        "движен": "mu",
        "2627": MOS_LOG_ID,
        "u14": U14_LOG_ID,
        "кругов": U14_LOG_ID,
    }.get(token)
    if (season or {}).get("id") == MOS_LOG_ID or str((season or {}).get("name") or "").startswith("2026/27"):
        rows = []
        for tournament in (data.get("gameLogs") or {}).get("tournaments") or []:
            if tournament.get("id") in PROTOCOL_LOG_IDS:
                rows.extend(tournament.get("rows") or [])
        return rows
    for tournament in (data.get("gameLogs") or {}).get("tournaments") or []:
        if tournament.get("id") == wanted:
            return tournament.get("rows") or []
    return []


def is_playoff(row) -> bool:
    text = f"{row.get('opponent') or ''} {row.get('stage') or ''}".lower()
    return any(mark in text for mark in ("полуфинал", "финал", "плей-офф", "плейофф", "за 3-е", "за третье"))


def assist_line(now, before):
    if now is None or before is None or before <= 0 or now < before * 1.15:
        return None
    kind, number = rate_bucket(before)
    if kind == "rare":
        games = WORD_FEM.get(number, str(number))
        tail = "игры" if number < 5 else "игр"
        earlier = f"раньше одна передача примерно за {games} {tail}"
    elif kind == "about_one":
        earlier = "раньше около одной передачи за матч"
    else:
        earlier = f"раньше было {soft_count(before)}"
    if now >= 1.05:
        later = "теперь больше одной за матч"
    elif now >= 0.85:
        later = "теперь около одной за матч"
    else:
        later = "теперь чуть чаще"
    return f"Стал чаще отдавать пас партнёрам: {earlier}, {later}."


def rebound_line(now, before):
    if now is None or before is None or now < before * 1.15:
        return None
    return (
        "Активнее борется под щитом: забирает отскок "
        f"{soft_count(now, True)} за игру, раньше — {soft_count(before)}."
    )


def steal_line(now, before):
    if now is None or before is None or before <= 0 or now < before * 1.15:
        return None
    if 0.85 <= now < 1.35 and 1.7 <= now / before <= 2.4:
        return "Чаще отбирает мяч у соперника: в среднем перехват за игру, это почти вдвое больше прежнего."
    if 0.85 <= now < 1.35:
        return "Чаще отбирает мяч у соперника: в среднем перехват за игру."
    return f"Чаще отбирает мяч у соперника: {soft_count(now, True)} за игру."


def foul_line(now, before):
    if now is None or before is None or before <= 0:
        return None
    change = fold_less(now, before)
    if change == "вдвое реже":
        return "Играет аккуратнее: фолит вдвое реже, чем раньше."
    if change == "реже":
        return "Играет аккуратнее: фолит реже, чем раньше."
    if now >= before * 1.3:
        return "work:Фолит чаще, чем раньше."
    return None


def turnover_line(turnovers, assists):
    if turnovers is None or assists is None or assists <= 0:
        return None
    ratio = turnovers / assists
    if ratio < 1.15:
        return "good:Передач примерно столько же, сколько потерь."
    number = max(2, min(6, int(round(ratio))))
    if ratio < number and number - ratio <= 0.45:
        word = WORD.get(number, str(number))
        noun = "потери" if number < 5 else "потерь"
        core = f"почти {word} {noun}"
    else:
        noun = "потери" if number < 5 else "потерь"
        core = f"около {WORD_GEN.get(number, str(number))} {noun}"
    return f"Пока чаще теряет мяч, чем отдаёт пас: {core} на одну передачу."


def shooting_line(percent, strong):
    if not percent:
        return None
    share = max(2, min(8, int(round(100 / percent))))
    of = WORD_GEN.get(share, str(share))
    if percent <= 35:
        where = "Против сильных команд забить трудно" if strong else "Забить пока трудно"
        return f"{where}: попадает примерно один бросок из {of}."
    if percent >= 45:
        return f"good:Бросок уже идёт: попадает примерно один из {of}."
    return None


def playoff_line(rows):
    games = [row for row in rows if is_playoff(row) and isinstance(row.get("points"), (int, float))]
    if len(games) < 2:
        return None
    points = int(sum(row["points"] for row in games))
    if points / len(games) >= 6:
        return None
    where = WORD_PREP_GAMES.get(len(games), f"{len(games)} матчах")
    if points == 0:
        scored = "ни одного очка"
    elif points == 1:
        scored = "одно очко"
    elif points == 2:
        scored = "два очка"
    else:
        scored = ru_count(points, "очко", "очка", "очков")
    return f"В {where} плей-офф набрал всего {scored} — в решающих играх пока тяжело."


def three_line(text, games):
    if not str(text or "").strip() or games <= 0:
        return None
    _made, attempts = parse_shot(text)
    if attempts <= 0:
        return None
    if attempts / games < 0.8:
        return "Из-за дуги почти не бросает — это следующий навык, который стоит освоить."
    return None


def split_side(text):
    if not text:
        return None, None
    if text.startswith("good:"):
        return "good", text[5:]
    if text.startswith("work:"):
        return "work", text[5:]
    return None, text


def mama_closing(current, assists, turnovers, steals, rebounds, before_rebounds):
    parts = []
    if minutes_number(current.get("minutes")) >= 15:
        parts.append("Тренер ему доверяет и даёт много игрового времени.")
    elif minutes_number(current.get("minutes")) >= 8:
        parts.append("Игрового времени уже достаточно, чтобы проявить себя.")
    defense = (steals or 0) >= 0.8 or (
        rebounds is not None and before_rebounds is not None and rebounds > before_rebounds
    )
    learning = turnovers is not None and assists is not None and turnovers > assists
    if defense and learning:
        parts.append("В защите от него уже есть польза, а в нападении он учится беречь мяч и точнее бросать.")
    elif defense:
        parts.append("В защите от него уже есть польза, и в нападении мяч он бережёт лучше.")
    elif learning:
        parts.append("В нападении он учится беречь мяч и точнее бросать.")
    if (steals or 0) >= 0.8 or learning or defense:
        parts.append("Это нормальный этап роста.")
    return " ".join(parts[:3])


def build_mama_notes(data):
    current, previous = current_and_previous(data)
    if not current:
        return [], [], ""
    before = previous or {}
    assists = as_float(current.get("assists"))
    rebounds = as_float(current.get("rebounds"))
    steals = as_float(current.get("steals"))
    turnovers = as_float(current.get("turnovers"))
    old_assists = as_float(before.get("assists"))
    old_rebounds = as_float(before.get("rebounds"))
    old_steals = as_float(before.get("steals"))
    fouls_now, fouls_before = fouls_pair(data, current, previous)
    percent, _made, _attempts = shot_percent(current.get("fg2"))
    strong = season_token(current.get("name")) in ("u12", "быстр")
    if season_token(current.get("name")) == "2627" and season_games(current) < 3:
        strong = False
    goods = []
    works = []

    def put(text, default):
        side, line = split_side(text)
        if not line:
            return
        bucket = goods if (side or default) == "good" else works
        if line not in bucket:
            bucket.append(line)

    put(assist_line(assists, old_assists), "good")
    put(rebound_line(rebounds, old_rebounds), "good")
    put(steal_line(steals, old_steals), "good")
    put(foul_line(fouls_now, fouls_before), "good")
    put(turnover_line(turnovers, assists), "work")
    put(shooting_line(percent, strong), "work")
    put(playoff_line(log_rows(data, current)), "work")
    put(three_line(current.get("fg3"), season_games(current)), "work")
    closing = mama_closing(current, assists, turnovers, steals, rebounds, old_rebounds)
    return goods[:4], works[:4], closing


def refresh_mama_notes(data):
    good, work, closing = build_mama_notes(data)
    mama = data.setdefault("mama", {})
    if len(good) >= 3:
        mama["good"] = good
    if len(work) >= 3:
        mama["work"] = work
    if closing:
        mama["closing"] = closing
    return good, work, closing


def walk_comps(nodes, found):
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        if node.get("CompType") == 0 and isinstance(node.get("CompID"), int):
            found.append(node["CompID"])
        walk_comps(node.get("Children"), found)


def team_games(calendar, team_id=TEAM_ID):
    games = []
    if not isinstance(calendar, list):
        raise ValueError("calendar")
    for game in calendar:
        if not isinstance(game, dict):
            continue
        if team_id not in (game.get("TeamAid"), game.get("TeamBid")):
            continue
        when = parse_ru_date(str(game.get("GameDate") or ""))
        if not when:
            continue
        home = game.get("TeamAid") == team_id
        opponent = game.get("ShortTeamNameBru") if home else game.get("ShortTeamNameAru")
        our = game.get("ShortTeamNameAru") if home else game.get("ShortTeamNameBru")
        if not opponent or not our:
            continue
        entry = {
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
        if team_id == U14_TEAM_ID:
            normalize_u14_game(entry)
        games.append(entry)
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


def calendar_for(comp_id, team_id=TEAM_ID):
    calendar = api(f"/Comp/GetCalendar/?comps={comp_id}&format=json")
    return team_games(calendar, team_id)


def team_games_widget(team_id: int):
    calendar = api(f"/Widget/TeamGames/{team_id}?format=json")
    return team_games(calendar, team_id)


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


U14_STANDINGS_COLUMNS = [
    {"key": "team", "label": "МЛБЛ U14"},
    {"key": "played", "label": "И"},
    {"key": "wins", "label": "В"},
    {"key": "losses", "label": "П"},
    {"key": "points", "label": "Турн. очки"},
    {"key": "scored", "label": "Забито"},
    {"key": "conceded", "label": "Пропущено"},
]


def parse_u14_standings(payload):
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError("standings")
    rows = []
    for item in payload:
        raw_name = ((item.get("CompTeamName") or {}).get("CompTeamShortNameRu"))
        place = item.get("Place")
        table = item.get("Standings") or {}
        if not raw_name or not isinstance(place, int):
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
        ours = item.get("TeamID") == U14_TEAM_ID
        name = U14_OUR_NAME if ours else normalize_u14_side(raw_name, our_team=False)
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
        if ours:
            rows[-1]["highlight"] = True
    rows.sort(key=lambda row: row["_place"])
    for row in rows:
        del row["_place"]
    if sum(1 for row in rows if row.get("highlight")) != 1:
        raise ValueError("team")
    return rows


def _fmt_num(value) -> str:
    number = round(float(value) + 1e-9, 1)
    if abs(number - round(number)) < 0.05:
        return str(int(round(number)))
    return f"{number:.1f}".replace(".", ",")


def _avg(item) -> tuple:
    table = item.get("Standings") or {}
    plus = table.get("AvgGoalPlus")
    minus = table.get("AvgGoalMinus")
    played = table.get("StandingGame")
    if not isinstance(played, int) or played <= 0:
        return None, None
    if not isinstance(plus, (int, float)):
        scored = table.get("StandingGoalPlus")
        plus = scored / played if isinstance(scored, int) else None
    if not isinstance(minus, (int, float)):
        conceded = table.get("StandingGoalMinus")
        minus = conceded / played if isinstance(conceded, int) else None
    if not isinstance(plus, (int, float)) or not isinstance(minus, (int, float)):
        return None, None
    return round(float(plus) + 1e-9, 1), round(float(minus) + 1e-9, 1)


def _team_name(item, *, u14: bool) -> str:
    raw = str(((item.get("CompTeamName") or {}).get("CompTeamShortNameRu")) or "").strip()
    if u14:
        if item.get("TeamID") == U14_TEAM_ID:
            return U14_OUR_NAME
        return normalize_u14_side(raw, our_team=False)
    return raw


def _recent_games(item, names, *, u14: bool) -> list:
    games = []
    for result in item.get("Results") or []:
        if not isinstance(result, dict):
            continue
        when = parse_ru_date(str(result.get("GameDate") or ""))
        score_a, score_b = result.get("ScoreA"), result.get("ScoreB")
        if not when or not isinstance(score_a, int) or not isinstance(score_b, int):
            continue
        if result.get("IsFirstTeam"):
            opp_id = result.get("TeamBid")
            ours, theirs = score_a, score_b
        else:
            opp_id = result.get("TeamAid")
            ours, theirs = score_b, score_a
        opponent = names.get(opp_id) or ""
        if not opponent:
            continue
        word = "победа" if result.get("IsWon") else "поражение" if result.get("IsLost") else result_word(ours, theirs)
        games.append(
            {
                "date": short_date(when),
                "opponent": opponent,
                "score": f"{ours}:{theirs}",
                "result": word,
                "_when": when,
            }
        )
    games.sort(key=lambda row: row["_when"], reverse=True)
    for row in games:
        del row["_when"]
    return games[:3]


def _form_sentence(recent: list) -> str:
    last = recent[:3]
    if not last:
        return ""
    wins = sum(1 for item in last if item.get("result") == "победа")
    count = len(last)
    if count == 1:
        return f"Последняя игра в турнире — {last[0]['result']}."
    word = {2: "две", 3: "три"}.get(count, str(count))
    if wins == count:
        return f"Последние {word} игры в турнире выиграла."
    if wins == 0:
        return f"Последние {word} игры в турнире проиграла."
    win_word = "победа" if wins == 1 else "победы" if 2 <= wins <= 4 else "побед"
    return f"Из {count} последних игр в турнире — {wins} {win_word}."


def _style_sentence(scored, conceded, mean_scored, mean_conceded) -> str:
    if scored is None or conceded is None or mean_scored is None or mean_conceded is None:
        return ""
    line = f"В среднем {_fmt_num(scored)} забитых и {_fmt_num(conceded)} пропущенных за игру."
    hot_attack = scored >= mean_scored + 8
    cold_attack = scored <= mean_scored - 8
    hot_defense = conceded >= mean_conceded + 8
    cold_defense = conceded <= mean_conceded - 8
    if hot_attack and hot_defense:
        tone = "Игры результативные: и забивает, и пропускает больше среднего по турниру."
    elif cold_attack and cold_defense:
        tone = "Игра вязкая: и забивает, и пропускает меньше среднего по турниру."
    else:
        attack = "В атаке около среднего по турниру"
        if hot_attack:
            attack = "Атака результативнее среднего по турниру"
        elif cold_attack:
            attack = "Атака скромнее среднего по турниру"
        defense = "защита около среднего"
        if cold_defense:
            defense = "защита держит лучше среднего"
        elif hot_defense:
            defense = "защита пропускает больше среднего"
        tone = f"{attack}, {defense}."
    diff = scored - conceded
    if diff >= 15:
        tone += " Разница мячей крупная, в плюсе."
    elif diff <= -15:
        tone += " Пропускает заметно больше, чем забивает."
    return f"{line} {tone}"


def _ru_count(number: int, one: str, few: str, many: str) -> str:
    value = abs(int(number))
    if value % 10 == 1 and value % 100 != 11:
        word = one
    elif 2 <= value % 10 <= 4 and not 12 <= value % 100 <= 14:
        word = few
    else:
        word = many
    return f"{value} {word}"


def _place_sentence(place, total, wins, losses, played) -> str:
    if played <= 0:
        return "В официальной таблице этого турнира у команды пока 0 игр. Средние и серию считать рано."
    wins_text = _ru_count(wins, "победа", "победы", "побед")
    losses_text = _ru_count(losses, "поражение", "поражения", "поражений")
    balance = f"{wins_text} и {losses_text}"
    if place == 1 and losses == 0:
        return f"Сейчас лидер турнира, без поражений: {wins_text}."
    if place == 1:
        return f"Сейчас на первом месте: {balance}."
    if place <= 3:
        return f"Держится в верхней части таблицы, {place}-е место: {balance}."
    if total and place >= max(total - 2, 1):
        return f"Идёт в нижней части таблицы, {place}-е место из {total}: {balance}."
    if losses == 0:
        return f"{place}-е место из {total}, пока без поражений: {wins_text}."
    return f"В середине таблицы, {place}-е место из {total}: {balance}."


def opponent_cards(payload, tournament: str, *, u14: bool) -> list:
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError("opponents")
    names = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        names[item.get("TeamID")] = _team_name(item, u14=u14)
    averages = [pair for pair in (_avg(item) for item in payload if isinstance(item, dict)) if pair[0] is not None]
    mean_scored = round(sum(pair[0] for pair in averages) / len(averages), 1) if averages else None
    mean_conceded = round(sum(pair[1] for pair in averages) / len(averages), 1) if averages else None
    total = len(payload)
    cards = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        team_id = item.get("TeamID")
        if u14 and team_id == U14_TEAM_ID:
            continue
        if not u14 and team_id == TEAM_ID:
            continue
        name = names.get(team_id) or ""
        if not name or name == U14_OUR_NAME:
            continue
        table = item.get("Standings") or {}
        played = table.get("StandingGame")
        wins = table.get("StandingWin")
        losses = table.get("StandingLose")
        place = item.get("Place")
        if not all(isinstance(value, int) and value >= 0 for value in (played, wins, losses)) or not isinstance(place, int):
            continue
        scored, conceded = _avg(item)
        recent = _recent_games(item, names, u14=u14)
        place_line = _place_sentence(place, total, wins, losses, played)
        style_line = _style_sentence(scored, conceded, mean_scored, mean_conceded) if played else ""
        form_line = _form_sentence(recent) if played else ""
        summary = " ".join(part for part in (place_line, style_line, form_line) if part)
        city = str(((item.get("CompTeamName") or {}).get("CompTeamRegionNameRu")) or "").strip()
        card = {
            "name": name,
            "tournament": tournament,
            "place": place,
            "played": played,
            "wins": wins,
            "losses": losses,
            "summary": summary,
            "recent": recent,
        }
        if city:
            card["city"] = city
        if scored is not None:
            card["scoredAvg"] = scored
            card["concededAvg"] = conceded
        cards.append(card)
    cards.sort(key=lambda card: (card["tournament"], card["place"], card["name"]))
    return cards


def refresh_opponents(data, notes) -> None:
    saved = (data.get("sync") or {}).get("compId") or 153217
    blocks = []
    try:
        moscow = api(f"/Widget/CompTeamResults/{saved}?format=json")
        blocks.extend(opponent_cards(moscow, "Первенство Москвы", u14=False))
    except Exception as exc:
        notes.append(f"соперники: Первенство Москвы не прочитано ({type(exc).__name__})")
        moscow = None
    try:
        u14 = api(f"/Widget/CompTeamResults/{U14_COMP_ID}?format=json")
        blocks.extend(opponent_cards(u14, "МЛБЛ U14", u14=True))
    except Exception as exc:
        notes.append(f"соперники: МЛБЛ U14 не прочитано ({type(exc).__name__})")
        u14 = None
    if moscow is None and u14 is None:
        notes.append("соперники: справочник оставлен прежним")
        return
    blob = json.dumps(blocks, ensure_ascii=False)
    for forbidden in ("424578", "Кириллович", "26.03.2014", "http://", "https://"):
        if forbidden in blob:
            notes.append(f"соперники: в тексте оказалось «{forbidden}», справочник не менял")
            return
    current = data.get("opponents") if isinstance(data.get("opponents"), dict) else {}
    fresh = {"teams": blocks}
    if current.get("teams") != blocks:
        data["opponents"] = fresh
        notes.append(f"соперники: карточек {len(blocks)}")
    else:
        notes.append("соперники: без изменений")


def format_match(game, has_protocol, now, *, away_host_first=False):
    when = f"{game['date'].day} {MONTHS[game['date'].month - 1]}"
    if away_host_first and not game["home"]:
        title = f"{game['opp']} — {game['our']}"
    else:
        title = f"{game['our']} — {game['opp']}"
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
    return {"title": title, "detail": detail, "status": status}


def merge_matches(old, games, protocol_dates, now, *, away_host_first=False):
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
        merged.append(format_match(game, short_date(game["date"]) in protocol_dates, now, away_host_first=away_host_first))
    return merged


def plaque_for(rows, matches):
    ours = next((row for row in rows if row.get("highlight")), None)
    if ours is None or int(ours["played"]) > 0:
        return ""
    for match in matches:
        score = extract_score(match.get("detail", ""))
        if not score:
            continue
        return f"Таблица ещё не обновлена: {result_word(*score)} {score[0]}:{score[1]}"
    return ""


def season_object(rows, group_name, *, season_id=MOS_LOG_ID):
    letter = ""
    match = re.search(r"Группа\s+([АБВГA-D])", group_name or "")
    if match:
        letter = match.group(1).replace("A", "А").replace("B", "Б")
        letter = f", группа {letter}"
    starts = sum(1 for row in rows if row.get("started") is True)
    return {
        "id": season_id,
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


def clean_ai_text(text) -> str:
    text = str(text or "")
    text = re.sub(r"```(?:json)?", "", text, flags=re.I)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\[\d{1,2}\]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \n`\"")


def parse_ai_answer(content):
    raw = clean_ai_text(content)
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    review = clean_ai_text(payload.get("review"))
    mama = clean_ai_text(payload.get("mama"))
    if len(review) < 40 or len(mama) < 8 or len(review) > 900 or len(mama) > 280:
        return None
    blob = f"{review} {mama}"
    for forbidden in ("424578", "Кириллович", "26.03.2014", "http://", "https://"):
        if forbidden in blob:
            return None
    if re.search(r"\[\d+\]", blob):
        return None
    return {"review": review, "mama": mama}


def row_brief(row) -> dict:
    return {
        "дата": row.get("date"),
        "соперник": row.get("opponent"),
        "счёт": row.get("score"),
        "минуты": row.get("minutes"),
        "старт": "да" if row.get("started") else "нет",
        "очки": row.get("points"),
        "двухочковые": row.get("fg2"),
        "трёхочковые": row.get("fg3"),
        "штрафные": row.get("ft"),
        "подборы": row.get("rebounds"),
        "подборы в нападении": row.get("offRebounds"),
        "передачи": row.get("assists"),
        "перехваты": row.get("steals"),
        "потери": row.get("turnovers"),
    }


def season_brief(data) -> dict:
    for season in data.get("tournamentStats", {}).get("seasons") or []:
        if season.get("id") == "mos2627" or str(season.get("name", "")).startswith("2026/27"):
            return {
                key: season.get(key)
                for key in (
                    "name",
                    "games",
                    "minutes",
                    "points",
                    "rebounds",
                    "assists",
                    "steals",
                    "turnovers",
                    "fg2",
                    "fg3",
                    "ft",
                )
            }
    return {}


def review_prompt(data, row, previous) -> str:
    player = data.get("player") or {}
    payload = {
        "игрок": "Костя",
        "амплуа": player.get("position") or "Разыгрывающий",
        "номер": player.get("number") or "7",
        "этот матч": row_brief(row),
        "средние сезона": season_brief(data),
        "предыдущие игры": [row_brief(item) for item in previous],
    }
    return json.dumps(payload, ensure_ascii=False)


def ask_perplexity(prompt: str):
    key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
    if not key:
        return None
    messages = [
        {
            "role": "system",
            "content": (
                "Ты разбираешь детский баскетбольный матч. Пиши только по цифрам из сообщения пользователя. "
                "Не добавляй факты, которых там нет: ни настроение, ни травмы, ни слова тренера, ни чужие игроки. "
                "Игрока называй только Костя. Без ссылок и без сносок в квадратных скобках. "
                "Ответ — один JSON-объект с ключами review и mama, без markdown. "
                "review — 3–5 коротких предложений, конкретно по цифрам. "
                "mama — одна тёплая фраза для мамы, тоже только по этим цифрам, без упрёка."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    bodies = [
        {"model": "sonar", "temperature": 0.1, "max_tokens": 450, "disable_search": True, "messages": messages},
        {"model": "sonar", "temperature": 0.1, "max_tokens": 450, "messages": messages},
    ]
    for body in bodies:
        request = urllib.request.Request(
            "https://api.perplexity.ai/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            parsed = parse_ai_answer(content)
            if parsed:
                return parsed
        except urllib.error.HTTPError as exc:
            if exc.code != 400 or "disable_search" not in body:
                return None
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, TypeError, json.JSONDecodeError):
            return None
    return None


def attach_review(data):
    rows = season_rows(data)
    last = data.get("lastMatch")
    if not rows or not isinstance(last, dict):
        return
    latest = rows[-1]
    fact = ""
    for item in last.get("facts") or []:
        if item.get("label") == "Матч":
            fact = str(item.get("value") or "")
    opponent = str(latest.get("opponent") or "")
    if latest.get("aiReview") and opponent and opponent in fact:
        last["aiReview"] = latest["aiReview"]
    else:
        last.pop("aiReview", None)


def review_games(data, notes, ask=None):
    ask = ask or ask_perplexity
    rows = season_rows(data)
    force = os.environ.get("AI_REGEN") == "1"
    if not rows:
        if force:
            notes.append("разбор: личного протокола ещё нет, шаблон на месте")
        attach_review(data)
        return
    if force and rows[-1].get("aiReview") and rows[-1].get("aiMama"):
        notes.append("разбор: у последней игры уже есть текст, не перезаписываю")
    targets = [row for row in rows if not row.get("aiReview") or not row.get("aiMama")]
    if not targets:
        attach_review(data)
        return
    if ask is ask_perplexity and not os.environ.get("PERPLEXITY_API_KEY", "").strip():
        notes.append("разбор: секрет PERPLEXITY_API_KEY не задан, оставлен шаблон")
        attach_review(data)
        return
    for row in targets:
        index = rows.index(row)
        previous = rows[max(0, index - 3) : index]
        prompt = review_prompt(data, row, previous)
        for forbidden in ("424578", "Кириллович", "26.03.2014"):
            if forbidden in prompt:
                notes.append("разбор: в запрос попали лишние данные, запрос не отправлен")
                attach_review(data)
                return
        try:
            answer = ask(prompt)
        except Exception:
            answer = None
        if not answer:
            notes.append(f"разбор: {row.get('date')} — API не ответил, оставлен шаблон")
            continue
        row["aiReview"] = answer["review"]
        row["aiMama"] = answer["mama"]
        notes.append(f"разбор: {row.get('date')}")
    attach_review(data)


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


def apply_fixed_review(row: dict) -> None:
    game_id = row.get("gameId")
    if not isinstance(game_id, int):
        return
    fixed = FIXED_GAME_REVIEWS.get(game_id)
    if not fixed:
        return
    for key, value in fixed.items():
        if value:
            row[key] = value


def sync_fixed_reviews(data: dict) -> None:
    for tournament in (data.get("gameLogs") or {}).get("tournaments") or []:
        for row in tournament.get("rows") or []:
            apply_fixed_review(row)
    last = data.get("lastMatch")
    rows = season_rows(data)
    if last and rows:
        latest = rows[-1]
        if latest.get("aiReview") and last.get("facts"):
            fact = next((f.get("value") or "" for f in last.get("facts") or [] if f.get("label") == "Матч"), "")
            if str(latest.get("opponent") or "") in fact:
                last["aiReview"] = latest["aiReview"]


def protocol_row_for_game(data: dict, log_id: str, game_id: int) -> dict | None:
    tournament = next((t for t in (data.get("gameLogs") or {}).get("tournaments") or [] if t.get("id") == log_id), None)
    if not tournament:
        return None
    for row in tournament.get("rows") or []:
        if row.get("gameId") == game_id:
            return row
    return None


def sync_manual_games_storage(data: dict, notes: list[str]) -> None:
    manual = data.setdefault("manualGames", {})
    for game_id, template in MANUAL_GAME_TEMPLATES.items():
        key = str(game_id)
        row = protocol_row_for_game(data, template.get("logId") or MOS_LOG_ID, game_id)
        if row:
            if key in manual:
                del manual[key]
                notes.append(f"ручная игра {game_id}: есть официальный протокол, запись снята")
            continue
        if key not in manual:
            manual[key] = copy.deepcopy(template)
            notes.append(f"ручная игра {game_id}: запись семьи на месте")
        else:
            for field, value in template.items():
                manual[key][field] = value


def mark_manual_games_no_push(data: dict) -> None:
    sent = data.setdefault("pushSent", {"games": [], "news": [], "seeded": False})
    sent.setdefault("games", [])
    for entry in (data.get("manualGames") or {}).values():
        if not entry.get("noPush"):
            continue
        game_id = entry.get("gameId")
        if not isinstance(game_id, int):
            continue
        key = f"id:{game_id}"
        if key not in sent["games"]:
            sent["games"].append(key)


def overlay_manual_on_matches(matches: list[dict], manual: dict) -> None:
    for match in matches:
        title = str(match.get("title") or "")
        for entry in manual.values():
            if not isinstance(entry, dict):
                continue
            token = str(entry.get("oppToken") or "")
            if not token or token not in title:
                continue
            match["gameId"] = entry.get("gameId")
            match["detail"] = entry.get("detail") or match.get("detail")
            match["status"] = entry.get("status") or match.get("status")
            if entry.get("aiReview"):
                match["aiReview"] = entry["aiReview"]
            if entry.get("aiMama"):
                match["aiMama"] = entry["aiMama"]
            break


def refresh_mama_pending_manual(data: dict) -> None:
    entry = (data.get("manualGames") or {}).get("1130166")
    if not entry:
        return
    pending = (data.get("mama") or {}).get("pending") or {}
    if "Гольяново" not in str(pending.get("title") or ""):
        return
    points = entry.get("points")
    shown = f"{points} очков" if isinstance(points, int) else "очки"
    data.setdefault("mama", {})["pending"] = {
        "title": pending.get("title") or "24.10.2026 · Гольяново",
        "text": (
            f"Команда выиграла 62:37. У Кости {shown} — по данным семьи; "
            "официального личного протокола на сайте пока нет."
        ),
    }


def apply_manual_games(data: dict, notes: list[str]) -> None:
    sync_manual_games_storage(data, notes)
    mark_manual_games_no_push(data)
    overlay_manual_on_matches((data.get("season") or {}).get("matches") or [], data.get("manualGames") or {})
    refresh_mama_pending_manual(data)


def ensure_log(data, log_id=MOS_LOG_ID, label: str | None = None):
    label = label or LOG_LABELS[log_id]
    tournaments = data["gameLogs"]["tournaments"]
    found = next((item for item in tournaments if item.get("id") == log_id), None)
    if found:
        if label:
            found["label"] = label
        elif log_id in LOG_LABELS:
            found["label"] = LOG_LABELS[log_id]
        return found
    found = {
        "id": log_id,
        "label": label,
        "chart": {"labelKey": "date", "labelPrefix": 5, "valueKey": "points"},
        "columns": LOG_COLUMNS,
        "rows": [],
    }
    tournaments.insert(0, found)
    return found


def protocol_dates_for_log(data, log_id: str) -> set[str]:
    log = next((t for t in data["gameLogs"]["tournaments"] if t.get("id") == log_id), None)
    if not log:
        return set()
    return {str(row.get("date")) for row in log.get("rows") or [] if row.get("date")}


def upsert_season_card(seasons: list, card_id: str, rows: list[dict], name: str, group_name: str, *, highlight: bool) -> None:
    if rows:
        season = season_object(rows, group_name, season_id=card_id)
        season["name"] = name
        season["highlight"] = highlight
    else:
        season = {
            "id": card_id,
            "name": name,
            "games": "0 (0)",
            "minutes": "—",
            "points": 0.0,
            "rebounds": 0.0,
            "assists": 0.0,
            "steals": 0.0,
            "turnovers": 0.0,
            "fg2": "0/0",
            "fg3": "0/0",
            "ft": "0/0",
            "highlight": False,
            "protocolGames": 0,
        }
        for key in ("kpiPerGame", "plusMinusPerGame", "plusMinusTotal"):
            season.pop(key, None)
    for item in seasons:
        if item.get("id") == card_id:
            for key, value in season.items():
                item[key] = value
            for key in ("kpiPerGame", "plusMinusPerGame", "plusMinusTotal"):
                if key not in season:
                    item.pop(key, None)
            return
    seasons.append(season)


def sync_season_2627_cards(data) -> None:
    seasons = data["tournamentStats"]["seasons"]
    mos_log = next((t for t in data["gameLogs"]["tournaments"] if t.get("id") == MOS_LOG_ID), None)
    u14_log = next((t for t in data["gameLogs"]["tournaments"] if t.get("id") == U14_LOG_ID), None)
    mos_rows = list((mos_log or {}).get("rows") or [])
    u14_rows = list((u14_log or {}).get("rows") or [])
    upsert_season_card(
        seasons,
        MOS_LOG_ID,
        mos_rows,
        "2026/27, Первенство Москвы (Мосбаскет), Росток-2014",
        "Группа А, Первенство Москвы",
        highlight=len(mos_rows) >= 5,
    )
    upsert_season_card(
        seasons,
        U14_LOG_ID,
        u14_rows,
        "2026/27, МЛБЛ U14, 26/27",
        "",
        highlight=False,
    )
    if any(item.get("highlight") for item in seasons if item.get("id") in (MOS_LOG_ID, U14_LOG_ID)):
        for item in seasons:
            if item.get("id") not in (MOS_LOG_ID, U14_LOG_ID) and not str(item.get("name", "")).startswith("2026/27"):
                item.pop("highlight", None)


def apply_protocols(data, stats, notes):
    if not stats:
        notes.append("личный протокол: в API пока нет строк игрока, блок «Последний матч» не трогал")
        return set()
    added = 0
    logs: dict[str, dict] = {}
    known: dict[str, set] = {}
    for stat in sorted(stats, key=lambda item: item["when"]):
        log_id = stat.get("logId") or MOS_LOG_ID
        log = logs.get(log_id) or ensure_log(data, log_id, LOG_LABELS.get(log_id))
        logs[log_id] = log
        keys = known.setdefault(log_id, {row.get("gameId") or row.get("date") for row in log["rows"]})
        key = stat.get("gameId") or stat["date"]
        if key in keys:
            continue
        row = public_row(stat)
        apply_fixed_review(row)
        log["rows"].append(row)
        keys.add(key)
        added += 1
    if added:
        notes.append(f"личный протокол: новых игр {added}")
    else:
        notes.append("личный протокол: новых игр нет")
    if not any(
        (log or {}).get("rows")
        for log in (
            next((t for t in data["gameLogs"]["tournaments"] if t.get("id") == lid), None)
            for lid in PROTOCOL_LOG_IDS
        )
    ):
        return {stat["date"] for stat in stats}
    sync_season_2627_cards(data)
    latest = max(stats, key=lambda item: item["when"])
    latest_log = logs.get(latest.get("logId") or MOS_LOG_ID) or ensure_log(data)
    rows = latest_log["rows"]
    data["lastMatch"] = {
        "caption": (
            f"Последний личный протокол: {long_date(latest['when'])}, {latest['opponent']}, "
            f"{latest['our']}:{latest['their']}."
        ),
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
    data["lastMatch"]["notice"] = (
        f"Это последний матч, по которому есть личная статистика ({latest['date']}, {latest.get('comp') or latest_log.get('label')})."
    )
    mama = data["mama"]["games"]
    have = {item.get("date") for item in mama}
    for stat in sorted(stats, key=lambda item: item["when"], reverse=True):
        if stat["date"] in have:
            continue
        mama.insert(0, {"date": stat["date"], "plus": kind_line(stat)})
        have.add(stat["date"])
    mama.sort(key=lambda item: parse_ru_date(item.get("date") or "") or date.min, reverse=True)
    del mama[5:]
    attach_review(data)
    return {stat["date"] for stat in stats}


HEIGHT_MIN = 120
HEIGHT_MAX = 220
WEIGHT_MIN = 25
WEIGHT_MAX = 120
OTHER_GUARD_CM = (139, 140)
TEAM_HEIGHT_CM = 149
TEAM_WEIGHT_KG = 41


def as_body_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        return int(value.strip())
    return None


def valid_body(height, weight) -> bool:
    return (
        isinstance(height, int)
        and isinstance(weight, int)
        and HEIGHT_MIN <= height <= HEIGHT_MAX
        and WEIGHT_MIN <= weight <= WEIGHT_MAX
    )


def body_value(height: int, weight: int) -> str:
    return f"{height} см, {weight} кг"


def body_paragraph(height: int, weight: int) -> str:
    tallest = max(OTHER_GUARD_CM)
    if height > tallest:
        lead = f"Из трёх разыгрывающих он самый высокий: {height} см при {weight} кг."
    elif height == tallest:
        lead = f"Из трёх разыгрывающих он делит самый высокий рост: {height} см при {weight} кг."
    else:
        lead = f"Из трёх разыгрывающих он не самый высокий: {height} см при {weight} кг."
    if height > TEAM_HEIGHT_CM:
        compared = f"Это выше среднего роста команды (около {TEAM_HEIGHT_CM} см)."
    elif height < TEAM_HEIGHT_CM:
        compared = f"Это ниже среднего роста команды (около {TEAM_HEIGHT_CM} см)."
    else:
        compared = f"Это как раз средний рост команды (около {TEAM_HEIGHT_CM} см)."
    return (
        f"{lead} Двое других — {OTHER_GUARD_CM[0]} и {OTHER_GUARD_CM[1]} см. "
        f"{compared} Средний вес команды около {TEAM_WEIGHT_KG} кг."
    )


def profile_body_text_ok(text: str, height: int, weight: int) -> bool:
    if not isinstance(text, str):
        return False
    centimeters = [int(item) for item in re.findall(r"(\d+)\s*см", text)]
    allowed = {height, OTHER_GUARD_CM[0], OTHER_GUARD_CM[1], TEAM_HEIGHT_CM}
    if height not in centimeters or any(item not in allowed for item in centimeters):
        return False
    tallest = max(OTHER_GUARD_CM)
    if height > tallest:
        if "не самый высокий" in text or "самый высокий" not in text:
            return False
    elif height < tallest:
        if "не самый высокий" not in text:
            return False
    elif "делит" not in text or "не самый высокий" in text:
        return False
    if "выше среднего" in text and height <= TEAM_HEIGHT_CM:
        return False
    if "ниже среднего" in text and height >= TEAM_HEIGHT_CM:
        return False
    for item in re.findall(r"при\s+(\d+)\s*кг", text):
        if int(item) != weight:
            return False
    return True


def sync_profile_body(data, height: int, weight: int, notes: list, changed_note: str) -> None:
    value = body_value(height, weight)
    paragraph = body_paragraph(height, weight)
    changed = False
    profile = data.setdefault("profile", {})
    items = profile.setdefault("items", [])
    found = False
    for item in items:
        if item.get("label") != "Рост и вес":
            continue
        found = True
        if item.get("value") != value:
            item["value"] = value
            changed = True
    if not found:
        items.append({"label": "Рост и вес", "value": value})
        changed = True
    paragraphs = profile.setdefault("paragraphs", [])
    index = next(
        (
            i
            for i, text in enumerate(paragraphs)
            if isinstance(text, str) and "см" in text and "разыгр" in text.lower()
        ),
        None,
    )
    if index is None:
        paragraphs.insert(0, paragraph)
        changed = True
    elif not profile_body_text_ok(paragraphs[index], height, weight):
        paragraphs[index] = paragraph
        changed = True
    notes.append(changed_note if changed else "рост: без изменений")


def refresh_body_from_api(data, notes):
    try:
        page = api(f"/Widget/PlayerPage/{PERSON_ID}?format=json")
    except Exception:
        notes.append("рост: источник не ответил, строка профиля прежняя")
        return
    height = as_body_int(page.get("PersonHeight")) if isinstance(page, dict) else None
    weight = as_body_int(page.get("PersonWeight")) if isinstance(page, dict) else None
    if not valid_body(height, weight):
        notes.append("рост: в ответе нет понятных роста и веса, строка прежняя")
        return
    sync_profile_body(data, height, weight, notes, "рост: строка профиля обновлена")


def refresh_body(data, notes):
    manual = data.get("manualBody") if isinstance(data.get("manualBody"), dict) else None
    if manual and manual.get("reset") is True:
        refresh_body_from_api(data, notes)
        return
    if manual:
        height = as_body_int(manual.get("height"))
        weight = as_body_int(manual.get("weight"))
        if valid_body(height, weight):
            sync_profile_body(data, height, weight, notes, "рост: ручные значения на месте")
            return
        notes.append("рост: manualBody задан, но значения вне диапазона, строка прежняя")
        return
    refresh_body_from_api(data, notes)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def option_value(flag: str, env: str) -> str:
    if flag in sys.argv:
        index = sys.argv.index(flag)
        if index + 1 < len(sys.argv) and not str(sys.argv[index + 1]).startswith("--"):
            return str(sys.argv[index + 1]).strip()
    return os.environ.get(env, "").strip()


def clear_manual_requested() -> bool:
    if "--clear-manual-body" in sys.argv:
        return True
    return os.environ.get("CLEAR_MANUAL_BODY", "").strip().lower() in {"1", "true", "yes"}


def apply_manual_body_inputs(data, notes, height_raw=None, weight_raw=None, clear=None) -> None:
    if clear is None:
        clear = clear_manual_requested()
    if clear:
        data["manualBody"] = {"reset": True, "updatedAt": utc_stamp()}
        notes.append("рост: ручные значения сброшены, дальше снова из протокола")
        return
    if height_raw is None and weight_raw is None:
        height_raw = option_value("--height-cm", "HEIGHT_CM")
        weight_raw = option_value("--weight-kg", "WEIGHT_KG")
    height_raw = "" if height_raw is None else str(height_raw).strip()
    weight_raw = "" if weight_raw is None else str(weight_raw).strip()
    if height_raw == "" and weight_raw == "":
        return
    height = as_body_int(height_raw)
    weight = as_body_int(weight_raw)
    if not valid_body(height, weight):
        notes.append("рост: нужны оба значения, рост 120–220 см и вес 25–120 кг")
        return
    current = data.get("manualBody") if isinstance(data.get("manualBody"), dict) else {}
    if (
        current.get("height") == height
        and current.get("weight") == weight
        and current.get("reset") is not True
    ):
        notes.append("рост: ручные значения те же")
        return
    data["manualBody"] = {"height": height, "weight": weight, "updatedAt": utc_stamp()}
    notes.append("рост: записаны ручные значения")


def update_basket(data, notes):
    saved = data.get("sync", {}).get("compId") or 153217
    try:
        comps = choose_comps(saved)
    except Exception as exc:
        notes.append(f"календарь: источник не принят ({type(exc).__name__}), матчи и таблица прежние")
        apply_manual_games(data, notes)
        refresh_body(data, notes)
        return []
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
            stat["logId"] = MOS_LOG_ID
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
                stat["logId"] = MOS_LOG_ID
                stats.append(stat)
                seen.add(stat.get("gameId"))
    protocol_dates = {stat["date"] for stat in stats} | protocol_dates_for_log(data, MOS_LOG_ID)
    if not read_any:
        notes.append("личный протокол Мосбаскет: журнал не прочитан, прежние строки на месте")
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
        ours = next((row for row in rows if row.get("highlight")), None)
        if ours is not None:
            plaque = plaque_for(rows, matches or old_matches)
            if int(ours["played"]) == 0 and plaque:
                data["season"]["caption"] = (
                    f"Официальная таблица ещё не обновилась. Первая игра — {plaque.split(': ', 1)[-1]} (по новости клуба)."
                )
            else:
                data["season"]["caption"] = (
                    f"На {long_date(now)}. В таблице группы у «Ростка» {ours['wins']} побед и {ours['losses']} поражений."
                )
        else:
            notes.append("таблица: строка «Ростка» не найдена, caption не менял")
        notes.append("таблица: обновлена")
    elif rows is not None:
        notes.append("таблица: без изменений")
    if matches is not None and matches != old_matches:
        data["season"]["matches"] = matches
        notes.append("календарь: список матчей обновлён")
    elif matches is not None:
        notes.append("календарь: новых матчей нет")
    apply_manual_games(data, notes)
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
    return stats if read_any else []


def fetch_u14_stats(games, notes) -> list:
    stats = []
    seen = set()
    by_id = {game["id"]: game for game in games}
    try:
        payload = api(
            f"/Widget/PlayerStats/{PERSON_ID}?format=json&compId={U14_COMP_ID}&team={U14_TEAM_ID}&filter=1"
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("GameStats"), list):
            raise ValueError("player-stats")
    except Exception as exc:
        notes.append(f"МЛБЛ U14: протокол не прочитан ({type(exc).__name__})")
        return stats
    for item in payload["GameStats"]:
        stat = stat_from_log(item)
        if not stat or stat.get("gameId") in seen:
            continue
        calendar_game = by_id.get(stat.get("gameId"))
        if calendar_game:
            stat["comp"] = calendar_game.get("comp") or U14_COMP_LABEL
            stat["our_name"] = calendar_game["our"]
            stat["opponent"] = calendar_game["opp"]
            pair = our_score_pair(calendar_game)
            if pair:
                stat["our"], stat["their"] = pair
                stat["score"] = f"{pair[0]}:{pair[1]}, {result_word(*pair)}"
                stat["result"] = result_word(*pair)
        else:
            stat["comp"] = U14_COMP_LABEL
            stat["our_name"] = U14_OUR_NAME
            stat["opponent"] = normalize_u14_opponent(stat.get("opponent"))
        stat["logId"] = U14_LOG_ID
        seen.add(stat.get("gameId"))
        stats.append(stat)
    if stats:
        notes.append(f"МЛБЛ U14: игр с протоколом {len(stats)}")
    return stats


def refresh_u14_schedule(data, games, notes) -> None:
    schedule = data.setdefault("u14Schedule", {})
    schedule["label"] = U14_COMP_LABEL
    schedule["caption"] = "Расписание «Росток-2014» в МЛБЛ U14."
    data.setdefault("sync", {})["u14CompId"] = U14_COMP_ID
    try:
        rows = parse_u14_standings(api(f"/Widget/CompTeamResults/{U14_COMP_ID}?format=json"))
    except Exception as exc:
        notes.append(f"МЛБЛ U14: таблица не принята ({type(exc).__name__}), прежние строки на месте")
        rows = None
    if rows is not None:
        standings = schedule.setdefault("standings", {})
        standings["columns"] = U14_STANDINGS_COLUMNS
        if standings.get("rows") != rows:
            standings["rows"] = rows
            notes.append("МЛБЛ U14: таблица обновлена")
        else:
            notes.append("МЛБЛ U14: таблица без изменений")
    if not games:
        return
    now = today()
    old_matches = schedule.get("matches") or []
    protocol_dates = protocol_dates_for_log(data, U14_LOG_ID)
    try:
        matches = merge_matches(old_matches, games, protocol_dates, now, away_host_first=True)
    except Exception:
        notes.append("МЛБЛ U14: расписание не собрал")
        return
    for match in matches:
        title = match.get("title")
        if title:
            match["title"] = normalize_u14_match_title(str(title))
    schedule["matches"] = matches
    if matches != old_matches or schedule.get("label") != U14_COMP_LABEL:
        notes.append("МЛБЛ U14: расписание обновлено")


def load_u14_games(notes) -> list:
    try:
        games = team_games_widget(U14_TEAM_ID)
    except Exception as exc:
        notes.append(f"МЛБЛ U14: календарь не прочитан ({type(exc).__name__})")
        return []
    print(f"МЛБЛ U14: игр команды {len(games)}", flush=True)
    return games


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


def _log_row_core(row: dict) -> dict:
    """Журнал без полей, которые дописывает kpi_sync из PlayerStats."""
    core = {k: v for k, v in row.items() if k not in ("kpi", "plusMinus", "gameId")}
    return core


def assert_safe(data, news, u12_before):
    blob = json.dumps({"data": data, "news": news}, ensure_ascii=False)
    for forbidden in ("424578", "Кириллович", "26.03.2014"):
        if forbidden in blob:
            raise SystemExit(f"остановка: в данных оказалось «{forbidden}», файлы не записал")
    if data["player"]["name"] != "Костя Д." or str(data["player"].get("number")) != "7":
        raise SystemExit("остановка: имя или номер изменились бы, файлы не записал")
    u12 = next(item for item in data["gameLogs"]["tournaments"] if item.get("id") == "u12")
    before_core = [_log_row_core(row) for row in u12_before]
    after_core = [_log_row_core(row) for row in u12["rows"]]
    if after_core != before_core:
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
    u14_rows = parse_u14_standings(
        [
            {
                "Place": 2,
                "TeamID": 1,
                "CompTeamName": {"CompTeamShortNameRu": "Соперник U14"},
                "Standings": {"StandingGame": 1, "StandingWin": 1, "StandingLose": 0, "StandingPoints": 2, "StandingGoalPlus": 40, "StandingGoalMinus": 30},
            },
            {
                "Place": 9,
                "TeamID": U14_TEAM_ID,
                "CompTeamName": {"CompTeamShortNameRu": "ШВСМ Росток U14"},
                "Standings": {"StandingGame": 3, "StandingWin": 1, "StandingLose": 2, "StandingPoints": 4, "StandingGoalPlus": 150, "StandingGoalMinus": 170},
            },
            {
                "Place": 3,
                "TeamID": 2,
                "CompTeamName": {"CompTeamShortNameRu": "ШВСМ Росток-2013 U14"},
                "Standings": {"StandingGame": 2, "StandingWin": 1, "StandingLose": 1, "StandingPoints": 3, "StandingGoalPlus": 80, "StandingGoalMinus": 75},
            },
        ]
    )
    ours = next(row for row in u14_rows if row.get("highlight"))
    assert ours["team"] == "9. Росток-2014" and ours["wins"] == "1" and ours["losses"] == "2"
    assert next(row["team"] for row in u14_rows if row["team"].startswith("3.")) == "3. Росток-2013"
    assert next(row["team"] for row in u14_rows if row["team"].startswith("2.")) == "2. Соперник"
    assert "ШВСМ" not in json.dumps(u14_rows, ensure_ascii=False) and "U14" not in json.dumps(u14_rows, ensure_ascii=False)
    sample_cards = opponent_cards(
        [
            {
                "Place": 1,
                "TeamID": 5,
                "CompTeamName": {"CompTeamShortNameRu": "Багратион U14", "CompTeamRegionNameRu": "Можайск"},
                "Standings": {"StandingGame": 3, "StandingWin": 3, "StandingLose": 0, "StandingPoints": 6, "StandingGoalPlus": 210, "StandingGoalMinus": 120, "AvgGoalPlus": 70, "AvgGoalMinus": 40},
                "Results": [
                    {"GameDate": "01.11.2026", "TeamAid": 5, "TeamBid": U14_TEAM_ID, "ScoreA": 80, "ScoreB": 50, "IsFirstTeam": True, "IsWon": True, "IsLost": False},
                ],
            },
            {
                "Place": 9,
                "TeamID": U14_TEAM_ID,
                "CompTeamName": {"CompTeamShortNameRu": "ШВСМ Росток U14", "CompTeamRegionNameRu": "Москва"},
                "Standings": {"StandingGame": 3, "StandingWin": 1, "StandingLose": 2, "StandingPoints": 4, "StandingGoalPlus": 150, "StandingGoalMinus": 180, "AvgGoalPlus": 50, "AvgGoalMinus": 60},
                "Results": [],
            },
            {
                "Place": 11,
                "TeamID": 8,
                "CompTeamName": {"CompTeamShortNameRu": "Новички U14", "CompTeamRegionNameRu": "Москва"},
                "Standings": {"StandingGame": 0, "StandingWin": 0, "StandingLose": 0, "StandingPoints": 0, "StandingGoalPlus": 0, "StandingGoalMinus": 0},
                "Results": [],
            },
        ],
        "МЛБЛ U14",
        u14=True,
    )
    bag = next(card for card in sample_cards if card["name"] == "Багратион")
    assert bag["city"] == "Можайск" and bag["place"] == 1 and "без поражений" in bag["summary"]
    assert bag["recent"][0]["opponent"] == "Росток-2014" and bag["recent"][0]["score"] == "80:50"
    assert all(card["name"] != "Росток-2014" for card in sample_cards)
    zero = next(card for card in sample_cards if card["name"] == "Новички")
    assert "0 игр" in zero["summary"] and "scoredAvg" not in zero
    assert "ШВСМ" not in json.dumps(sample_cards, ensure_ascii=False) and "424578" not in json.dumps(sample_cards, ensure_ascii=False)
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
    dirty = 'Разбор [1] смотри https://example.com/a и ещё [12].'
    assert "[" not in clean_ai_text(dirty) and "http" not in clean_ai_text(dirty)
    parsed = parse_ai_answer(
        '```json\n{"review": "Костя набрал 8 очков за 18 минут и забил 3 из 7 двухочковых. Это выше его среднего за сезон.", "mama": "Восемь очков и четыре подбора — спокойная полезная игра."}\n```'
    )
    assert parsed and parsed["review"].startswith("Костя") and "http" not in parsed["mama"]
    assert parse_ai_answer('{"review": "Кириллович набрал очень много очков в этом длинном матче сегодня.", "mama": "Молодец."}') is None
    basket = {
        "player": {"position": "Разыгрывающий", "number": "7"},
        "tournamentStats": {"seasons": [{"id": "mos2627", "name": "2026/27", "points": 4.3, "rebounds": 3.6, "games": "1 (1)", "minutes": "18:02", "assists": 1.2, "steals": 1.1, "turnovers": 3.0, "fg2": "3/7, 43%", "fg3": "0/1", "ft": "2/2, 100%"}]},
        "gameLogs": {"tournaments": [{"id": "mos2627", "rows": [
            {"date": "18.01.26", "opponent": "Тринта", "score": "37:35, победа", "minutes": "22:16", "points": 10, "fg2": "3/5", "fg3": "0/0", "ft": "4/4", "rebounds": 3, "offRebounds": 1, "assists": 0, "steals": 5, "turnovers": 4, "started": True, "aiReview": "Уже готово и достаточно длинное, чтобы не звать API снова.", "aiMama": "Уже есть."},
            {"date": "24.10.26", "opponent": "Гольяново-2014-2", "score": "62:37, победа", "minutes": "18:02", "points": 8, "fg2": "3/7", "fg3": "0/1", "ft": "2/2", "rebounds": 4, "offRebounds": 1, "assists": 2, "steals": 1, "turnovers": 3, "started": True},
        ]}]},
        "lastMatch": {"facts": [{"label": "Матч", "value": "Росток-2014 — Гольяново-2014-2, 62:37"}], "paragraphs": ["Шаблон."]},
    }
    prompt = review_prompt(basket, basket["gameLogs"]["tournaments"][0]["rows"][1], basket["gameLogs"]["tournaments"][0]["rows"][:1])
    assert "424578" not in prompt and "Кириллович" not in prompt and "26.03.2014" not in prompt
    assert "Гольяново-2014-2" in prompt and "Разыгрывающий" in prompt
    calls = []

    def fake_ask(text):
        calls.append(text)
        return {"review": "Костя набрал 8 очков за 18 минут. Двухочковые 3 из 7, подборов 4. Это конкретно по протоколу этого матча.", "mama": "Восемь очков и четыре подбора в победном матче."}

    review_games(basket, [], ask=fake_ask)
    row = basket["gameLogs"]["tournaments"][0]["rows"][1]
    assert row["aiReview"].startswith("Костя") and row["aiMama"].startswith("Восемь")
    assert basket["lastMatch"]["aiReview"] == row["aiReview"]
    review_games(basket, [], ask=fake_ask)
    assert len(calls) == 1
    os.environ["AI_REGEN"] = "1"
    try:
        review_games(basket, [], ask=fake_ask)
    finally:
        os.environ.pop("AI_REGEN", None)
    assert len(calls) == 1
    kept_old = basket["gameLogs"]["tournaments"][0]["rows"][0]["aiReview"]
    kept_u12 = "Разбор U12 остаётся при обновлении протокола и достаточно длинный."
    basket["mama"] = {
        "seasonSummary": "KEEP",
        "games": [{"date": "01.01.26", "plus": "старое"}],
        "good": ["KEEP-GOOD"],
        "work": ["KEEP-WORK"],
        "closing": "KEEP-CLOSING",
    }
    basket["glossary"] = [{"term": "Мин", "text": "минуты"}]
    basket["achievements"] = [{"value": "3", "label": "Место", "detail": "МЛБЛ-Дети U12, 2025/26"}]
    basket["tournamentStats"]["seasons"][0]["place"] = "3"
    basket["gameLogs"]["tournaments"].append(
        {
            "id": "u12",
            "rows": [
                {
                    "date": "21.02.26",
                    "opponent": "Тимирязевская",
                    "score": "52:31, победа",
                    "points": 1,
                    "key": "u12-9",
                    "place": 3,
                    "aiReview": kept_u12,
                    "aiMama": "Тёплая фраза про бронзу.",
                }
            ],
        }
    )
    new_stat = {
        "date": "25.10.26",
        "when": date(2026, 10, 25),
        "opponent": "Соперник",
        "our": 40,
        "their": 30,
        "our_name": "Росток-2014",
        "started": True,
        "minutes": "12:00",
        "points": 4,
        "fg2": "2/4",
        "fg3": "0/0",
        "ft": "0/0",
        "rebounds": 2,
        "offRebounds": 0,
        "assists": 1,
        "steals": 1,
        "turnovers": 1,
        "fouls": 1,
        "result": "победа",
        "comp": "Группа А",
        "score": "40:30, победа",
    }
    apply_protocols(basket, [new_stat], [])
    u12_row = basket["gameLogs"]["tournaments"][1]["rows"][0]
    assert u12_row["aiReview"] == kept_u12
    assert u12_row["aiMama"] == "Тёплая фраза про бронзу."
    assert u12_row["key"] == "u12-9" and u12_row["place"] == 3
    assert basket["mama"]["seasonSummary"] == "KEEP"
    assert basket["glossary"][0]["term"] == "Мин"
    assert basket["achievements"][0]["value"] == "3"
    season = basket["tournamentStats"]["seasons"][0]
    assert season["place"] == "3" and season["id"] == "mos2627"
    old_row = next(row for row in basket["gameLogs"]["tournaments"][0]["rows"] if row["date"] == "18.01.26")
    assert old_row["aiReview"] == kept_old and old_row["aiMama"] == "Уже есть."
    added = next(row for row in basket["gameLogs"]["tournaments"][0]["rows"] if row["date"] == "25.10.26")
    assert "aiReview" not in added and added["score"].startswith("40:30")
    match = next(item["value"] for item in basket["lastMatch"]["facts"] if item["label"] == "Матч")
    assert match.startswith("Росток-2014 — Соперник, 40:30")
    review_games(basket, [], ask=fake_ask)
    assert old_row["aiReview"] == kept_old
    assert added["aiReview"].startswith("Костя") and added["aiMama"].startswith("Восемь")
    assert u12_row["aiReview"] == kept_u12
    again = json.loads(json.dumps(basket, ensure_ascii=False))
    assert again["mama"]["seasonSummary"] == "KEEP"
    assert again["glossary"][0]["text"] == "минуты"
    assert again["achievements"][0]["label"] == "Место"
    assert again["gameLogs"]["tournaments"][1]["rows"][0]["aiReview"] == kept_u12
    assert again["tournamentStats"]["seasons"][0]["place"] == "3"
    os.environ.pop("PERPLEXITY_API_KEY", None)
    assert ask_perplexity("тест") is None
    sample = {
        "tournamentStats": {"seasons": [
            {"name": "2024/25, «Быстрый прорыв», Зоркий", "games": "10 (5)", "minutes": "18:44", "assists": 0.5, "rebounds": 2.3, "steals": 0.6, "turnovers": 3.5, "fg2": "18/73, 25%", "fg3": "0/1"},
            {"name": "2025/26, МЛБЛ-Дети U12 (1-й дивизион), Росток", "games": "10 (3)", "minutes": "18:59", "assists": 1.2, "rebounds": 3.6, "steals": 1.1, "turnovers": 3.2, "fg2": "14/57, 25%", "fg3": "2/4", "highlight": True},
        ]},
        "trend": {"views": [{"id": "ctrl", "categories": ["Потери", "Фолы", "Фолы на нём"], "series": [
            {"name": "Быстрый прорыв, 2024/25", "values": [3.5, 1.4, 1.3]},
            {"name": "МЛБЛ-Дети U12, 2025/26", "values": [3.2, 0.6, 1.5]},
        ]}]},
        "gameLogs": {"tournaments": [{"id": "u12", "rows": [
            {"opponent": "Тринта, полуфинал", "points": 0},
            {"opponent": "Тимирязевская, за 3-е", "points": 1},
        ]}]},
        "mama": {"good": ["Передачи: 1,2"], "work": ["Потери: 3,2"], "closing": "старое"},
    }
    good, work, closing = refresh_mama_notes(sample)
    assert good == [
        "Стал чаще отдавать пас партнёрам: раньше одна передача примерно за две игры, теперь больше одной за матч.",
        "Активнее борется под щитом: забирает отскок почти 4 раза за игру, раньше — около двух.",
        "Чаще отбирает мяч у соперника: в среднем перехват за игру, это почти вдвое больше прежнего.",
        "Играет аккуратнее: фолит вдвое реже, чем раньше.",
    ]
    assert work == [
        "Пока чаще теряет мяч, чем отдаёт пас: почти три потери на одну передачу.",
        "Против сильных команд забить трудно: попадает примерно один бросок из четырёх.",
        "В двух матчах плей-офф набрал всего одно очко — в решающих играх пока тяжело.",
        "Из-за дуги почти не бросает — это следующий навык, который стоит освоить.",
    ]
    assert closing == "Тренер ему доверяет и даёт много игрового времени. В защите от него уже есть польза, а в нападении он учится беречь мяч и точнее бросать. Это нормальный этап роста."
    for line in good + work:
        assert not re.search(r":\s*\d", line)
        assert len(line) > 20
    assert 3 <= len(good) <= 4 and 3 <= len(work) <= 4
    assert "не оценка" not in closing and "НБА" not in closing
    sample["trend"]["views"][0]["series"][1]["values"][1] = None
    short_good, _short_work, _short_close = build_mama_notes(sample)
    assert all("фолит" not in line for line in short_good)
    assert len(short_good) == 3
    test_manual_body()


def test_manual_body():
    global api
    saved_api = api
    saved_env = {key: os.environ.get(key) for key in ("HEIGHT_CM", "WEIGHT_KG", "CLEAR_MANUAL_BODY")}
    calls = []
    base_paragraph = (
        "Из трёх разыгрывающих он самый высокий: 150 см. "
        "Двое других — 139 и 140 см. Средний рост команды около 149 см, средний вес около 41 кг."
    )

    def profile(value="150 см, 42 кг", paragraph=base_paragraph):
        return {
            "profile": {
                "items": [{"label": "Рост и вес", "value": value}],
                "paragraphs": [paragraph],
            }
        }

    try:
        api = lambda path: calls.append(path) or {"PersonHeight": 150, "PersonWeight": 42}
        data = profile()
        data["manualBody"] = {"height": 158, "weight": 45, "updatedAt": "2026-11-06T15:58:00Z"}
        notes = []
        refresh_body(data, notes)
        assert calls == []
        assert data["profile"]["items"][0]["value"] == "158 см, 45 кг"
        text = data["profile"]["paragraphs"][0]
        assert text == body_paragraph(158, 45)
        assert "158 см" in text and "при 45 кг" in text
        assert "150" not in text
        assert "не самый высокий" not in text and "самый высокий" in text
        assert "выше среднего" in text and "139 и 140" in text
        saved_text = text
        refresh_body(data, notes)
        assert data["profile"]["paragraphs"][0] == saved_text
        assert calls == []
        assert notes[-1] == "рост: без изменений"

        short = profile()
        short["manualBody"] = {"height": 138, "weight": 40, "updatedAt": "2026-11-06T15:58:00Z"}
        refresh_body(short, [])
        short_text = short["profile"]["paragraphs"][0]
        assert "не самый высокий" in short_text and "138 см" in short_text and "ниже среднего" in short_text
        assert "150" not in short_text

        tied = profile()
        tied["manualBody"] = {"height": 140, "weight": 40, "updatedAt": "2026-11-06T15:58:00Z"}
        refresh_body(tied, [])
        assert "делит самый высокий рост" in tied["profile"]["paragraphs"][0]

        bad = profile()
        bad["manualBody"] = {"height": 300, "weight": 10}
        bad_notes = []
        refresh_body(bad, bad_notes)
        assert bad["profile"]["items"][0]["value"] == "150 см, 42 кг"
        assert any("вне диапазона" in line for line in bad_notes)
        assert calls == []

        calls.clear()
        plain = profile()
        api = lambda path: calls.append(path) or {"PersonHeight": 151, "PersonWeight": 44}
        plain_notes = []
        refresh_body(plain, plain_notes)
        assert calls
        assert plain["profile"]["items"][0]["value"] == "151 см, 44 кг"
        assert "151 см" in plain["profile"]["paragraphs"][0]
        assert any("обновлена" in line for line in plain_notes)

        weird = profile()
        api = lambda path: {"PersonHeight": 90, "PersonWeight": 10}
        weird_notes = []
        refresh_body(weird, weird_notes)
        assert weird["profile"]["items"][0]["value"] == "150 см, 42 кг"
        assert any("нет понятных" in line for line in weird_notes)

        offline = profile()
        api = lambda path: (_ for _ in ()).throw(OSError("offline"))
        offline_notes = []
        refresh_body(offline, offline_notes)
        assert offline["profile"]["items"][0]["value"] == "150 см, 42 кг"
        assert any("не ответил" in line for line in offline_notes)

        calls.clear()
        reset = profile()
        reset["manualBody"] = {"reset": True, "updatedAt": "2026-11-06T16:00:00Z"}
        api = lambda path: calls.append(path) or {"PersonHeight": 152, "PersonWeight": 46}
        refresh_body(reset, [])
        assert calls
        assert reset["manualBody"]["reset"] is True
        assert "height" not in reset["manualBody"]
        assert reset["profile"]["items"][0]["value"] == "152 см, 46 кг"

        entered = profile()
        entered_notes = []
        apply_manual_body_inputs(entered, entered_notes, height_raw="158", weight_raw="45", clear=False)
        assert entered["manualBody"]["height"] == 158 and entered["manualBody"]["weight"] == 45
        stamp = entered["manualBody"]["updatedAt"]
        apply_manual_body_inputs(entered, entered_notes, height_raw="158", weight_raw="45", clear=False)
        assert entered["manualBody"]["updatedAt"] == stamp
        apply_manual_body_inputs(entered, entered_notes, height_raw="10", weight_raw="10", clear=False)
        assert entered["manualBody"]["height"] == 158
        assert any("120–220" in line for line in entered_notes)
        apply_manual_body_inputs(entered, entered_notes, clear=True)
        assert entered["manualBody"].get("reset") is True and "height" not in entered["manualBody"]

        os.environ["HEIGHT_CM"] = "161"
        os.environ["WEIGHT_KG"] = "47"
        os.environ.pop("CLEAR_MANUAL_BODY", None)
        env_data = profile()
        apply_manual_body_inputs(env_data, [])
        assert env_data["manualBody"]["height"] == 161 and env_data["manualBody"]["weight"] == 47

        canonical = body_paragraph(158, 45)
        assert profile_body_text_ok(canonical, 158, 45)
        assert not profile_body_text_ok(base_paragraph, 158, 45)
        assert "150" not in canonical
    finally:
        api = saved_api
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def game_key(row) -> str:
    game_id = row.get("gameId")
    if isinstance(game_id, int):
        return f"id:{game_id}"
    return f"date:{row.get('date')}:{row.get('opponent')}"


def season_rows(data):
    rows = []
    for log_id in PROTOCOL_LOG_IDS:
        tournament = next((item for item in data["gameLogs"]["tournaments"] if item.get("id") == log_id), None)
        if tournament:
            rows.extend(tournament.get("rows") or [])
    rows.sort(key=lambda row: parse_ru_date(row.get("date") or "") or date.min)
    return rows


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
        result = sender("Новость команды", news_push_text(post), f"{SITE}team.html#news", "news")
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


PROFILE_TOURNAMENT = "Первенство Москвы (Мосбаскет, группа А) и МЛБЛ U14, сезон 2026/27"
STATS_PARAGRAPH_2627 = (
    "«Движение вверх» — любительская лига, соперники там слабее. «Быстрый прорыв» — сильный турнир своего года. "
    "Сезон 2025/26 — два турнира: МЛБЛ-Дети U12 и Первенство Москвы (юноши 2014 г.р.). "
    "Сезон 2026/27 — Первенство Москвы (Мосбаскет, группа А) и МЛБЛ U14. "
    "В базе 35 игр с личными протоколами или очками. Раньше сезона 2024/25 записей нет."
)
MAMA_SEASON_SUMMARY = (
    "За два с небольшим сезона в базе 35 игр Кости и 194 очка. В 2024/25 за «Зоркий» он набирал в любительской лиге "
    "«Движение вверх» по 11,3 очка за игру, лучшая игра 16 очков, и дошёл с командой до финала. В том же сезоне "
    "в сильнейшем турнире своего года, «Быстром прорыве», было трудно всей команде, но там у него лучшая игра — "
    "13 очков из 19 командных. В 2025/26 он играл сразу в двух турнирах: в МЛБЛ-Дети U12 (1-й дивизион) стал чаще "
    "отдавать пас, подбирать и перехватывать, выдал три игры подряд по 9–11 очков, а команда взяла бронзу; "
    "в Первенстве Москвы на 1-м этапе сыграл пять матчей подряд в октябре — там соперники сильнее, в среднем "
    "2 очка за игру. В 2026/27 после перелома ноги в августе он снова выходит за «Росток-2014»: в Мосбаскете "
    "первая игра после травмы — победа над «Гольяново» 24 октября (6 очков по данным семьи); в МЛБЛ U14 — "
    "разобранный личный протокол 31 октября, поражение 63:84 от Takeshot Academy (вторая игра после травмы, "
    "почти 11 минут со скамейки)."
)
U14_SOURCE_TITLE = "МЛБЛ U14, 26/27"
U14_SOURCE_NOTE = "Расписание и протоколы «Росток-2014» в МЛБЛ U14."


def refresh_display_copy(data: dict) -> None:
    profile = data.setdefault("profile", {})
    for item in profile.get("items") or []:
        if item.get("label") == "Турнир":
            item["value"] = PROFILE_TOURNAMENT
        elif item.get("label") == "Команда":
            item["value"] = "Росток-2014, группа А, Первенство Москвы (Мосбаскет)"
    stats = data.setdefault("tournamentStats", {})
    paragraphs = stats.get("paragraphs") or []
    if paragraphs:
        paragraphs[0] = STATS_PARAGRAPH_2627
    for tournament in (data.get("gameLogs") or {}).get("tournaments") or []:
        tid = tournament.get("id")
        if tid in LOG_LABELS:
            tournament["label"] = LOG_LABELS[tid]
        if tid != U14_LOG_ID:
            continue
        for row in tournament.get("rows") or []:
            row["opponent"] = normalize_u14_opponent(row.get("opponent"))
            apply_fixed_review(row)
    for link in (data.get("sources") or {}).get("links") or []:
        href = str(link.get("href") or "")
        if "144801" in href:
            link["title"] = U14_SOURCE_TITLE
            link["note"] = U14_SOURCE_NOTE
    schedule = data.get("u14Schedule") or {}
    schedule["label"] = U14_COMP_LABEL
    schedule["caption"] = "Расписание «Росток-2014» в МЛБЛ U14."
    for match in schedule.get("matches") or []:
        title = match.get("title")
        if title:
            match["title"] = normalize_u14_match_title(str(title))
    mama = data.setdefault("mama", {})
    if not str(mama.get("seasonSummary") or "").startswith("KEEP"):
        mama["seasonSummary"] = MAMA_SEASON_SUMMARY


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
    apply_manual_body_inputs(data, notes)
    u14_games = load_u14_games(notes)
    mos_stats = update_basket(data, notes)
    u14_stats = fetch_u14_stats(u14_games, notes) if u14_games else []
    combined_stats = (mos_stats or []) + (u14_stats or [])
    if combined_stats:
        apply_protocols(data, combined_stats, notes)
    refresh_u14_schedule(data, u14_games, notes)
    refresh_opponents(data, notes)
    sync_fixed_reviews(data)
    apply_manual_games(data, notes)
    try:
        from kpi_sync import refresh_kpi

        refresh_kpi(data, notes)
    except Exception as exc:
        notes.append(f"kpi: не обновил ({type(exc).__name__})")
    refresh_mama_notes(data)
    refresh_display_copy(data)
    review_games(data, notes)
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
