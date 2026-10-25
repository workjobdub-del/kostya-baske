"""KPI / PlusMinus sync from infobasket PlayerStats into data.json."""

from __future__ import annotations

import copy
import re
from typing import Any

PERSON_ID = 424578


def api(path: str):
    import update_stats

    return update_stats.api(path)


def short_date(when) -> str:
    import update_stats

    return update_stats.short_date(when)

KPI_SOURCES = [
    (108682, 53315, "u12"),
    (108871, 38431, "pm2526"),
    (153217, 38872, "mos2627"),
]

SEASON_2526 = {"id": "2526", "label": "2025/26", "tournamentIds": ("u12", "pm2526")}
SEASON_2627 = {"id": "2627", "label": "2026/27", "tournamentIds": ("mos2627",)}
SEASON_2425 = {"id": "2425", "label": "2024/25, «Быстрый прорыв»", "tournamentIds": ("fb",)}

FALLBACK_WAS_2425 = {
    "games": 10,
    "kpiGame": -2.2,
    "kpi20": -2.3,
    "ts": 0.25,
    "astTo": 0.14,
    "stl20": 0.6,
    "plusMinus": -16.4,
}

DEFAULT_MVP = {
    "date": "18.01.26",
    "opponent": "Тринта 2015 U12",
    "score": "35:37",
    "result": "победа на выезде",
    "tournament": "МЛБЛ-Дети U12 (1-й дивизион)",
    "line": "10 очков, 5 перехватов, 3 подбора, КПИ 12",
    "href": "https://moscow.ilovebasket.ru/games/936918",
    "gameId": 936918,
    "kpi": 12,
    "mvp": True,
}

LOG_KPI_COLUMNS = [
    {"key": "kpi", "label": "КПИ"},
    {"key": "plusMinus", "label": "+/−"},
]

METRIC_DEFS = [
    ("kpiGame", "КПИ за игру", "Общая польза за матч: очки, подборы, передачи, перехваты и блоки минус промахи, потери и свои фолы, плюс фолы на нём.", True),
    ("kpi20", "КПИ на 20 минут", "Тот же КПИ, но на 20 минут игры — удобно сравнивать, если минуты разные.", True),
    ("ts", "Меткость (TS%)", "Доля очков от всех бросков с учётом штрафных. Чем выше, тем эффективнее нападение.", True),
    ("astTo", "Передачи на потерю", "Сколько передач приходится на одну потерю. Больше — лучше для разыгрывающего.", True),
    ("stl20", "Перехваты на 20 минут", "Сколько перехватов в пересчёте на 20 минут.", True),
    ("plusMinus", "+/− за игру", "Разница очков команды, пока игрок был на площадке: плюс — команда выигрывала отрезок.", True),
]


def nz(value) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def kpi_from_row(row: dict) -> int:
    fga = nz(row.get("Shot2")) + nz(row.get("Shot3"))
    fgm = nz(row.get("Goal2")) + nz(row.get("Goal3"))
    base = (
        nz(row.get("Points"))
        + nz(row.get("Rebound"))
        + nz(row.get("Assist"))
        + nz(row.get("Steal"))
        + nz(row.get("Blocks"))
        - (fga - fgm)
        - (nz(row.get("Shot1")) - nz(row.get("Goal1")))
        - nz(row.get("Turnover"))
    )
    return base + nz(row.get("OpponentFoul")) - nz(row.get("Foul"))


def norm_opponent(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower().replace("ё", "е"))


def row_key(date: str, opponent: str) -> tuple[str, str]:
    return str(date or "").strip(), norm_opponent(opponent)


def aggregate_games(game_rows: list[dict]) -> dict[str, Any] | None:
    played = [g for g in game_rows if nz(g.get("Seconds"))]
    if not played:
        return None
    totals = {
        "games": len(played),
        "kpi": 0,
        "seconds": 0,
        "points": 0,
        "assists": 0,
        "steals": 0,
        "turnovers": 0,
        "plusMinus": 0,
        "fga": 0,
        "fta": 0,
    }
    for g in played:
        totals["kpi"] += kpi_from_row(g)
        totals["seconds"] += nz(g.get("Seconds"))
        totals["points"] += nz(g.get("Points"))
        totals["assists"] += nz(g.get("Assist"))
        totals["steals"] += nz(g.get("Steal"))
        totals["turnovers"] += nz(g.get("Turnover"))
        totals["plusMinus"] += nz(g.get("PlusMinus"))
        totals["fga"] += nz(g.get("Shot2")) + nz(g.get("Shot3"))
        totals["fta"] += nz(g.get("Shot1"))
    minutes = totals["seconds"] / 60 if totals["seconds"] else 0
    ts_den = 2 * (totals["fga"] + 0.44 * totals["fta"])
    return {
        "games": totals["games"],
        "kpiGame": round(totals["kpi"] / totals["games"], 1),
        "kpi20": round(totals["kpi"] / minutes * 20, 1) if minutes else 0,
        "ts": round(totals["points"] / ts_den, 3) if ts_den else 0,
        "astTo": round(totals["assists"] / totals["turnovers"], 2) if totals["turnovers"] else 0,
        "stl20": round(totals["steals"] / minutes * 20, 1) if minutes else 0,
        "plusMinus": round(totals["plusMinus"] / totals["games"], 1),
    }


def fetch_comp_games(comp_id: int, team_id: int) -> list[dict]:
    payload = api(f"/Widget/PlayerStats/{PERSON_ID}?format=json&compId={comp_id}&team={team_id}&filter=1")
    if not isinstance(payload, dict):
        raise ValueError("player-stats")
    rows = payload.get("GameStats") or []
    if not isinstance(rows, list):
        raise ValueError("game-stats")
    return rows


def build_index(game_rows: list[dict]) -> dict[tuple[str, str], dict]:
    index: dict[tuple[str, str], dict] = {}
    for item in game_rows:
        when = short_date(parse_game_date(item))
        if not when:
            continue
        game = item.get("Game") or {}
        opponent = opponent_from_item(item)
        if not opponent:
            continue
        kpi = item.get("KPI")
        if not isinstance(kpi, (int, float)):
            kpi = kpi_from_row(item)
        entry = {
            "kpi": round(float(kpi), 1) if isinstance(kpi, (int, float)) else kpi_from_row(item),
            "plusMinus": nz(item.get("PlusMinus")),
            "gameId": game.get("GameID") if isinstance(game.get("GameID"), int) else None,
        }
        index[row_key(when, opponent)] = entry
        opp_short = opponent.split(",")[0].strip()
        if opp_short != opponent:
            index[row_key(when, opp_short)] = entry
    return index


def parse_game_date(item: dict):
    import update_stats

    raw = item.get("GameDate") or (item.get("Game") or {}).get("GameDate")
    return update_stats.parse_ru_date(str(raw or ""))


def opponent_from_item(item: dict) -> str:
    block = item.get("TeamNameB") if item.get("TeamNumber") == 1 else item.get("TeamNameA")
    if isinstance(block, dict):
        name = block.get("CompTeamShortNameRu") or block.get("CompTeamNameRu")
        if name:
            return str(name)
    game = item.get("Game") or {}
    teams = game.get("GameTeams") or []
    number = item.get("TeamNumber")
    ours = next((t for t in teams if t.get("GameTeamNumber") == number), None)
    theirs = next((t for t in teams if t.get("GameTeamNumber") != number), None)
    if theirs:
        name = (theirs.get("TeamName") or {}).get("CompTeamShortNameRu")
        if name:
            return str(name)
    return ""


def ensure_log_columns(data: dict) -> None:
    for tournament in (data.get("gameLogs") or {}).get("tournaments") or []:
        columns = tournament.get("columns") or []
        keys = {c.get("key") for c in columns}
        for extra in LOG_KPI_COLUMNS:
            if extra["key"] not in keys:
                columns.append(copy.deepcopy(extra))
        tournament["columns"] = columns


def patch_log_rows(data: dict, index: dict[tuple[str, str], dict]) -> int:
    touched = 0
    for tournament in (data.get("gameLogs") or {}).get("tournaments") or []:
        for row in tournament.get("rows") or []:
            hit = index.get(row_key(row.get("date", ""), row.get("opponent", "")))
            if not hit:
                for alt in fuzzy_keys(row.get("date", ""), row.get("opponent", "")):
                    hit = index.get(alt)
                    if hit:
                        break
            if not hit:
                continue
            row["kpi"] = hit["kpi"]
            row["plusMinus"] = hit["plusMinus"]
            if hit.get("gameId"):
                row["gameId"] = hit["gameId"]
            touched += 1
    return touched


def fuzzy_keys(date: str, opponent: str) -> list[tuple[str, str]]:
    base = norm_opponent(opponent)
    keys = []
    for part in re.split(r"[,·]", opponent):
        part = part.strip()
        if part:
            keys.append(row_key(date, part))
    if "тринта" in base:
        keys.append(row_key(date, "Тринта 2015 U12"))
    return keys


def season_metrics(data: dict, season: dict) -> dict[str, Any] | None:
    ids = season.get("tournamentIds") or ()
    rows = []
    for tournament in (data.get("gameLogs") or {}).get("tournaments") or []:
        if tournament.get("id") not in ids:
            continue
        for row in tournament.get("rows") or []:
            if row.get("kpi") is None:
                continue
            rows.append(row)
    if not rows:
        return None
    fake = []
    for row in rows:
        fake.append(
            {
                "Seconds": 1200,
                "Points": 0,
                "Rebound": 0,
                "Assist": 0,
                "Steal": 0,
                "Turnover": 0,
                "Shot1": 0,
                "Shot2": 0,
                "Shot3": 0,
                "Goal1": 0,
                "Goal2": 0,
                "Goal3": 0,
                "OpponentFoul": 0,
                "Foul": 0,
                "PlusMinus": nz(row.get("plusMinus")),
                "KPI": row.get("kpi"),
            }
        )
    # Re-aggregate from per-game kpi/pm when raw shots missing
    games = len(rows)
    kpi_sum = sum(float(r.get("kpi") or 0) for r in rows)
    pm_sum = sum(nz(r.get("plusMinus")) for r in rows)
    return {
        "games": games,
        "kpiGame": round(kpi_sum / games, 1),
        "kpi20": None,
        "ts": None,
        "astTo": None,
        "stl20": None,
        "plusMinus": round(pm_sum / games, 1),
    }


def season_metrics_from_api(aggregates: dict[str, dict]) -> dict[str, dict]:
    out = {}
    if "u12" in aggregates and "pm2526" in aggregates:
        combined = []
        for key in ("u12", "pm2526"):
            combined.extend(aggregates[key].get("_raw") or [])
        agg = aggregate_games(combined)
        if agg:
            out["2526"] = agg
    if "mos2627" in aggregates:
        agg = aggregate_games(aggregates["mos2627"].get("_raw") or [])
        if agg:
            out["2627"] = agg
    if "fb" in aggregates:
        agg = aggregate_games(aggregates["fb"].get("_raw") or [])
        if agg:
            out["2425"] = agg
    return out


def team_avg_mlbl(raw_games: list[dict], cache: dict, notes: list[str]) -> dict[str, Any] | None:
    player_totals: dict[int, dict[str, float]] = {}
    for item in raw_games:
        game = item.get("Game") or {}
        game_id = game.get("GameID")
        if not isinstance(game_id, int):
            continue
        key = str(game_id)
        if key not in cache:
            try:
                online = api(f"/Widget/GetOnline/{game_id}?format=json")
            except Exception:
                notes.append(f"kpi: протокол {game_id} для среднего по команде не прочитан")
                continue
            cache[key] = online
        online = cache.get(key)
        if not isinstance(online, dict):
            continue
        for team in online.get("GameTeams") or []:
            if team.get("TeamID") != 53315:
                continue
            for person in team.get("Players") or []:
                sec = nz(person.get("Seconds"))
                if sec <= 0:
                    continue
                pid = nz(person.get("PersonID"))
                slot = player_totals.setdefault(pid, {"kpi": 0.0, "seconds": 0.0, "points": 0, "ast": 0, "to": 0, "stl": 0, "fga": 0, "fta": 0})
                slot["kpi"] += float(kpi_from_row(person))
                slot["seconds"] += sec
                slot["points"] += nz(person.get("Points"))
                slot["ast"] += nz(person.get("Assist"))
                slot["to"] += nz(person.get("Turnover"))
                slot["stl"] += nz(person.get("Steal"))
                slot["fga"] += nz(person.get("Shot2")) + nz(person.get("Shot3"))
                slot["fta"] += nz(person.get("Shot1"))
    if not player_totals:
        return None
    per20 = []
    ts_vals = []
    astto = []
    stl20 = []
    for slot in player_totals.values():
        minutes = slot["seconds"] / 60
        if minutes <= 0:
            continue
        per20.append(slot["kpi"] / minutes * 20)
        den = 2 * (slot["fga"] + 0.44 * slot["fta"])
        if den:
            ts_vals.append(slot["points"] / den)
        if slot["to"]:
            astto.append(slot["ast"] / slot["to"])
        stl20.append(slot["stl"] / minutes * 20)
    if not per20:
        return None
    return {
        "label": "Росток U12 в МЛБЛ",
        "kpi20": round(sum(per20) / len(per20), 1),
        "ts": round(sum(ts_vals) / len(ts_vals), 3) if ts_vals else None,
        "astTo": round(sum(astto) / len(astto), 2) if astto else None,
        "stl20": round(sum(stl20) / len(stl20), 1) if stl20 else None,
    }


def match_same(a: dict | None, b: dict | None) -> bool:
    if not a or not b:
        return False
    if a.get("gameId") and b.get("gameId"):
        return a.get("gameId") == b.get("gameId")
    return a.get("date") == b.get("date") and norm_opponent(a.get("opponent")) == norm_opponent(b.get("opponent"))


def maybe_update_best(kpi: dict, index: dict, raw_by_game: dict[int, dict], cache: dict, notes: list[str]) -> None:
    best = kpi.get("best") or {}
    best_kpi = float(best.get("kpi") or -999)
    for (_d, _o), entry in index.items():
        game_id = entry.get("gameId")
        if not game_id:
            continue
        raw = raw_by_game.get(game_id)
        if not raw:
            continue
        try:
            online = cache.get(str(game_id))
            if online is None:
                online = api(f"/Widget/GetOnline/{game_id}?format=json")
                cache[str(game_id)] = online
        except Exception:
            continue
        max_kpi = None
        ours = None
        for team in (online or {}).get("GameTeams") or []:
            for person in team.get("Players") or []:
                if nz(person.get("Seconds")) <= 0:
                    continue
                val = float(kpi_from_row(person))
                if max_kpi is None or val > max_kpi:
                    max_kpi = val
                if person.get("PersonID") == PERSON_ID:
                    ours = val
        if ours is None or max_kpi is None or ours < max_kpi:
            continue
        if ours <= best_kpi:
            continue
        kpi["best"] = {
            "date": _d,
            "opponent": _o,
            "score": raw.get("score", ""),
            "result": raw.get("result", ""),
            "tournament": raw.get("tournament", ""),
            "line": raw.get("line", ""),
            "href": raw.get("href", ""),
            "gameId": game_id,
            "kpi": round(ours, 1),
            "mvp": False,
        }
        best_kpi = ours
        notes.append(f"kpi: лучший матч по КПИ обновлён ({_d})")


def refresh_trend(data: dict, season_api: dict[str, dict]) -> None:
    trend = data.setdefault("trend", {})
    views = trend.get("views") or []
    avg = next((v for v in views if v.get("id") == "avg"), None)
    if not avg:
        return
    cats = list(avg.get("categories") or [])
    if "КПИ" not in cats:
        cats.append("КПИ")
    avg["categories"] = cats
    for series in avg.get("series") or []:
        name = str(series.get("name") or "")
        values = list(series.get("values") or [])
        while len(values) < len(cats) - 1:
            values.append(0)
        kpi_val = None
        if "Быстрый" in name and "2425" in season_api:
            kpi_val = season_api["2425"].get("kpiGame")
        elif "МЛБЛ" in name and "2526" in season_api:
            kpi_val = season_api["2526"].get("kpiGame")
        elif "2627" in name and "2627" in season_api:
            kpi_val = season_api["2627"].get("kpiGame")
        if kpi_val is not None:
            if len(values) < len(cats):
                values.append(kpi_val)
            else:
                values[len(cats) - 1] = kpi_val
        series["values"] = values

    eff = next((v for v in views if v.get("id") == "efficiency"), None)
    if not eff:
        eff = {"id": "efficiency", "label": "КПИ", "signed": True, "categories": ["КПИ за игру", "+/−"], "series": []}
        views.append(eff)
    eff["signed"] = True
    eff["categories"] = ["КПИ за игру", "+/−"]
    eff["series"] = []
    mapping = [
        ("Быстрый прорыв, 2024/25", "2425"),
        ("МЛБЛ-Дети U12, 2025/26", "2526"),
    ]
    for label, sid in mapping:
        metrics = season_api.get(sid) or (FALLBACK_WAS_2425 if sid == "2425" else None)
        if not metrics:
            continue
        eff["series"].append(
            {
                "name": label,
                "values": [metrics.get("kpiGame"), metrics.get("plusMinus")],
            }
        )
    trend["views"] = views


def refresh_season_cards(data: dict) -> None:
    name_map = [
        ("Быстрый прорыв", "fb"),
        ("МЛБЛ-Дети", "u12"),
        ("Первенство Москвы", "pm2526"),
        ("2026/27", "mos2627"),
        ("Движение", "mu"),
    ]
    for season in (data.get("tournamentStats") or {}).get("seasons") or []:
        name = str(season.get("name") or "")
        tid = None
        for needle, tournament_id in name_map:
            if needle in name:
                tid = tournament_id
                break
        if not tid:
            continue
        tournament = next((t for t in data["gameLogs"]["tournaments"] if t.get("id") == tid), None)
        if not tournament:
            continue
        vals = [r.get("kpi") for r in tournament.get("rows") or [] if r.get("kpi") is not None]
        if vals:
            season["kpiPerGame"] = round(sum(float(v) for v in vals) / len(vals), 1)


def build_metrics(active: dict, was: dict, team: dict | None) -> list[dict]:
    items = []
    for key, label, hint, higher in METRIC_DEFS:
        entry = {
            "id": key,
            "label": label,
            "hint": hint,
            "value": active.get(key),
            "was": was.get(key) if was else None,
            "higher": higher,
        }
        if key == "kpi20" and team and team.get("kpi20") is not None:
            entry["team"] = team.get("kpi20")
        if key == "ts" and team and team.get("ts") is not None:
            entry["team"] = round(team["ts"] * 100)
        if key == "astTo" and team and team.get("astTo") is not None:
            entry["team"] = team.get("astTo")
        if key == "stl20" and team and team.get("stl20") is not None:
            entry["team"] = team.get("stl20")
        items.append(entry)
    return items


def refresh_kpi(data: dict, notes: list[str]) -> None:
    old_kpi = copy.deepcopy(data.get("kpi") or {})
    old_mvp = old_kpi.get("mvp")
    # Протоколы GetOnline не пишем в JSON — там есть PersonID.
    cache: dict[str, Any] = {}

    index: dict[tuple[str, str], dict] = {}
    aggregates: dict[str, dict] = {}
    raw_by_game: dict[int, dict] = {}

    for comp_id, team_id, tournament_id in KPI_SOURCES:
        try:
            rows = fetch_comp_games(comp_id, team_id)
        except Exception as exc:
            notes.append(f"kpi: comp {comp_id} не прочитан ({type(exc).__name__})")
            continue
        aggregates[tournament_id] = {"_raw": rows}
        index.update(build_index(rows))
        for item in rows:
            game = item.get("Game") or {}
            gid = game.get("GameID")
            if isinstance(gid, int):
                when = short_date(parse_game_date(item))
                opp = opponent_from_item(item)
                raw_by_game[gid] = {
                    "score": "",
                    "result": "",
                    "tournament": "",
                    "line": "",
                    "href": f"https://moscow.ilovebasket.ru/games/{gid}",
                }

    if not index:
        notes.append("kpi: индекс игр пуст, прежние значения на месте")
        return

    ensure_log_columns(data)
    patched = patch_log_rows(data, index)
    notes.append(f"kpi: строк журнала с КПИ — {patched}")

    season_api = season_metrics_from_api(aggregates)
    if "2425" not in season_api:
        season_api["2425"] = copy.deepcopy(FALLBACK_WAS_2425)

    games_2627 = len([g for g in aggregates.get("mos2627", {}).get("_raw") or [] if nz(g.get("Seconds"))])
    if games_2627 >= 3 and "2627" in season_api:
        active_id, was_id = "2627", "2526"
    else:
        active_id, was_id = "2526", "2425"

    active = season_api.get(active_id) or season_api.get("2526") or FALLBACK_WAS_2425
    was = season_api.get(was_id) or FALLBACK_WAS_2425

    team = None
    try:
        team = team_avg_mlbl(aggregates.get("u12", {}).get("_raw") or [], cache, notes)
    except Exception:
        notes.append("kpi: среднее по команде не посчитал")

    kpi = data.setdefault("kpi", {})
    kpi["activeSeasonId"] = active_id
    kpi["activeLabel"] = SEASON_2627["label"] if active_id == "2627" else SEASON_2526["label"]
    kpi["wasSeasonId"] = was_id
    kpi["wasLabel"] = SEASON_2425["label"] if was_id == "2425" else SEASON_2526["label"]
    if games_2627 < 3:
        kpi["caption"] = f"Пока в сезоне 2026/27 мало игр с протоколом — цифры за {kpi['activeLabel']}."
    else:
        kpi["caption"] = f"Сезон {kpi['activeLabel']}. «Было» — {kpi['wasLabel']}."

    kpi["metrics"] = build_metrics(active, was, team or old_kpi.get("teamAvg"))
    if team:
        kpi["teamAvg"] = team
    elif old_kpi.get("teamAvg"):
        kpi["teamAvg"] = old_kpi["teamAvg"]

    kpi["tournaments"] = []
    labels = {"u12": "МЛБЛ-Дети U12", "pm2526": "Первенство Москвы", "mos2627": "2026/27"}
    for tid, label in labels.items():
        raw = aggregates.get(tid, {}).get("_raw") or []
        agg = aggregate_games(raw)
        if agg:
            kpi["tournaments"].append({"id": tid, "label": label, "games": agg["games"], "kpiGame": agg["kpiGame"]})

    kpi.pop("sync", None)

    if old_mvp:
        kpi["mvp"] = old_mvp
    else:
        kpi["mvp"] = copy.deepcopy(DEFAULT_MVP)

    if not kpi.get("best"):
        kpi["best"] = copy.deepcopy(kpi["mvp"])
        kpi["best"]["mvp"] = False

    if not match_same(kpi.get("best"), kpi.get("mvp")):
        maybe_update_best(kpi, index, raw_by_game, cache, notes)

    refresh_trend(data, season_api)
    refresh_season_cards(data)
