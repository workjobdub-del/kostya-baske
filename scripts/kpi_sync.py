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


def norm_opponent_key(text: str) -> str:
    s = norm_opponent(text)
    s = re.sub(r'[«»"\'\u201c\u201d]', "", s)
    s = re.sub(r"\s*,\s*.*$", "", s)
    s = re.sub(r"\s+(полуфинал|финал|матч за|за \d+[-–].*).*$", "", s, flags=re.I)
    s = re.sub(r"\b(u12|u13|u14|2012|2013|2014|2015|2016|2017)\b", " ", s)
    s = re.sub(r"[-–—]\s*\d+\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def opponent_tokens(text: str) -> set[str]:
    key = norm_opponent_key(text)
    return {t for t in re.split(r"[\s\-–—]+", key) if len(t) >= 3}


def opponents_match(site: str, source: str) -> bool:
    a = norm_opponent_key(site)
    b = norm_opponent_key(source)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    ta, tb = opponent_tokens(site), opponent_tokens(source)
    if not ta or not tb:
        return False
    return bool(ta & tb)


def journal_score_parts(score_text: str) -> tuple[int, int] | None:
    match = re.search(r"(\d+)\s*:\s*(\d+)", str(score_text or ""))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def entry_from_api_row(item: dict) -> dict | None:
    if nz(item.get("Seconds")) <= 0:
        return None
    when = short_date(parse_game_date(item))
    if not when:
        return None
    game = item.get("Game") or {}
    gid = game.get("GameID")
    opponent = opponent_from_item(item)
    kpi = item.get("KPI")
    if not isinstance(kpi, (int, float)):
        kpi = kpi_from_row(item)
    return {
        "date": when,
        "sourceOpponent": opponent,
        "kpi": round(float(kpi), 1),
        "plusMinus": nz(item.get("PlusMinus")),
        "gameId": gid if isinstance(gid, int) else None,
        "points": nz(item.get("Points")),
    }


def build_match_index(game_rows: list[dict]) -> dict[str, Any]:
    by_id: dict[int, dict] = {}
    by_date: dict[str, list[dict]] = {}
    for item in game_rows:
        entry = entry_from_api_row(item)
        if not entry:
            continue
        gid = entry.get("gameId")
        if isinstance(gid, int):
            by_id[gid] = entry
        by_date.setdefault(entry["date"], []).append(entry)
    return {"by_id": by_id, "by_date": by_date}


def match_log_row(row: dict, index: dict[str, Any], used: set[int] | None = None) -> dict | None:
    used = used if used is not None else set()
    gid = row.get("gameId")
    if isinstance(gid, int) and gid in index["by_id"]:
        return index["by_id"][gid]
    date = str(row.get("date") or "").strip()
    pool = [c for c in (index["by_date"].get(date) or []) if c.get("gameId") not in used]
    if not pool:
        pool = list(index["by_date"].get(date) or [])
    if not pool:
        return None
    if len(pool) == 1:
        return pool[0]
    site_opp = str(row.get("opponent") or "")
    matched = [c for c in pool if opponents_match(site_opp, c.get("sourceOpponent") or "")]
    if len(matched) == 1:
        return matched[0]
    if not matched:
        matched = pool
    if len(matched) == 1:
        return matched[0]
    points = row.get("points")
    if isinstance(points, (int, float)):
        by_pts = [c for c in matched if c.get("points") == int(points)]
        if len(by_pts) == 1:
            return by_pts[0]
    best = None
    best_hits = 0
    site_tokens = opponent_tokens(site_opp)
    for c in matched:
        hits = len(site_tokens & opponent_tokens(c.get("sourceOpponent") or ""))
        if hits > best_hits:
            best_hits = hits
            best = c
    return best if best is not None else matched[0]


def patch_log_rows(data: dict, indices: dict[str, dict[str, Any]]) -> int:
    touched = 0
    for tournament in (data.get("gameLogs") or {}).get("tournaments") or []:
        tid = tournament.get("id")
        index = indices.get(tid)
        if not index:
            continue
        used: set[int] = set()
        protocol = 0
        for row in tournament.get("rows") or []:
            hit = match_log_row(row, index, used)
            if not hit:
                continue
            row["kpi"] = hit["kpi"]
            row["plusMinus"] = hit["plusMinus"]
            if hit.get("gameId"):
                row["gameId"] = hit["gameId"]
                used.add(int(hit["gameId"]))
            protocol += 1
            touched += 1
        tournament["protocolGames"] = protocol
    return touched


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


def tournament_metrics_from_api(aggregates: dict[str, dict]) -> dict[str, dict]:
    """Per-tournament aggregates from the same PlayerStats rows as the journal."""
    out: dict[str, dict] = {}
    for tid in ("u12", "pm2526", "mos2627", "fb"):
        if tid not in aggregates:
            continue
        agg = aggregate_games(aggregates[tid].get("_raw") or [])
        if agg:
            out[tid] = agg
    return out


def season_metrics_from_api(aggregates: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    tour = tournament_metrics_from_api(aggregates)
    out.update(tour)
    if "u12" in aggregates and "pm2526" in aggregates:
        combined = []
        for key in ("u12", "pm2526"):
            combined.extend(aggregates[key].get("_raw") or [])
        agg = aggregate_games(combined)
        if agg:
            out["2526"] = agg
    if "mos2627" in tour:
        out["2627"] = tour["mos2627"]
    if "fb" in tour:
        out["2425"] = tour["fb"]
    return out


def scope_season(label: str, games: int) -> str:
    return f"Сезон {label}, {games} игр"


def scope_tournament(label: str, games: int) -> str:
    return f"{label}, {games} игр"


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


def journal_row_for_game(data: dict, game_id: int) -> dict | None:
    for tournament in (data.get("gameLogs") or {}).get("tournaments") or []:
        for row in tournament.get("rows") or []:
            if row.get("gameId") == game_id:
                return row
    return None


def maybe_update_best(
    kpi: dict, by_id: dict[int, dict], data: dict, cache: dict, notes: list[str]
) -> None:
    best = kpi.get("best") or {}
    best_kpi = float(best.get("kpi") or -999)
    mvp_id = (kpi.get("mvp") or {}).get("gameId")
    for game_id, entry in by_id.items():
        if mvp_id and game_id == mvp_id:
            continue
        ours = float(entry.get("kpi") or 0)
        if ours <= best_kpi:
            continue
        row = journal_row_for_game(data, game_id)
        try:
            online = cache.get(str(game_id))
            if online is None:
                online = api(f"/Widget/GetOnline/{game_id}?format=json")
                cache[str(game_id)] = online
        except Exception:
            continue
        max_kpi = None
        player_kpi = None
        for team in (online or {}).get("GameTeams") or []:
            for person in team.get("Players") or []:
                if nz(person.get("Seconds")) <= 0:
                    continue
                val = float(kpi_from_row(person))
                if max_kpi is None or val > max_kpi:
                    max_kpi = val
                if person.get("PersonID") == PERSON_ID:
                    player_kpi = val
        if player_kpi is None or max_kpi is None or player_kpi < max_kpi:
            continue
        best_kpi = ours
        kpi["best"] = {
            "date": entry.get("date") or (row or {}).get("date", ""),
            "opponent": (row or {}).get("opponent") or entry.get("sourceOpponent", ""),
            "score": (row or {}).get("score", ""),
            "result": "",
            "tournament": "",
            "line": "",
            "href": f"https://moscow.ilovebasket.ru/games/{game_id}",
            "gameId": game_id,
            "kpi": round(ours, 1),
            "mvp": False,
        }
        notes.append(f"kpi: лучший матч по КПИ обновлён ({kpi['best']['date']})")


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
        elif "МЛБЛ" in name and "u12" in season_api:
            kpi_val = season_api["u12"].get("kpiGame")
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
        ("Быстрый прорыв, 2024/25", "2425", None),
        ("МЛБЛ-Дети U12, 2025/26", "u12", season_api.get("u12")),
    ]
    for label, sid, metrics in mapping:
        if metrics is None:
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


def season_games_count(season: dict) -> int:
    text = str(season.get("games") or "")
    match = re.match(r"(\d+)", text)
    if match:
        return int(match.group(1))
    return 0


def apply_season_plus_minus(season: dict, tournament: dict | None, tournament_id: str) -> None:
    rows = (tournament or {}).get("rows") or []
    pm_vals = [r.get("plusMinus") for r in rows if r.get("plusMinus") is not None]
    if pm_vals:
        total = sum(nz(v) for v in pm_vals)
        season["plusMinusPerGame"] = round(total / len(pm_vals), 1)
        season["plusMinusTotal"] = int(total)
        return
    if tournament_id == "fb" or "Быстрый прорыв" in str(season.get("name") or ""):
        games = season_games_count(season) or len(rows) or int(FALLBACK_WAS_2425["games"])
        avg = float(FALLBACK_WAS_2425["plusMinus"])
        season["plusMinusPerGame"] = round(avg, 1)
        season["plusMinusTotal"] = int(round(avg * games))


def refresh_career_notes(data: dict) -> None:
    seasons = (data.get("tournamentStats") or {}).get("seasons") or []
    fb = next((s for s in seasons if "Быстрый прорыв" in str(s.get("name") or "")), None)
    mlbl = next(
        (s for s in seasons if "МЛБЛ" in str(s.get("name") or "") and s.get("highlight")),
        None,
    )
    if not fb or not mlbl:
        return
    notes = data.setdefault("notes", {})

    def num(value) -> str:
        if value is None:
            return "—"
        return str(value).replace(".", ",")

    pros = [
        f"Передачи: было {num(fb.get('assists'))} за игру, стало {num(mlbl.get('assists'))}",
        f"Подборы: было {num(fb.get('rebounds'))}, стало {num(mlbl.get('rebounds'))}",
        f"Перехваты: {num(mlbl.get('steals'))} за игру, почти вдвое больше",
        "Фолов меньше: 0,6 против 1,4. Соперники фолят на нём чаще",
    ]
    if mlbl.get("kpiPerGame") is not None:
        pros.append(f"КПИ за игру в МЛБЛ: {num(mlbl.get('kpiPerGame'))} (все {mlbl.get('protocolGames') or 10} игр с протоколом)")
    notes["pros"] = pros

    cons = list(notes.get("cons") or [])
    if mlbl.get("kpiPerGame") is not None and cons:
        cons[0] = (
            f"Потери: {num(mlbl.get('turnovers'))} за игру при {num(mlbl.get('assists'))} передачи. "
            f"КПИ за игру в МЛБЛ — {num(mlbl.get('kpiPerGame'))}"
        )
        notes["cons"] = cons


def refresh_season_cards(data: dict, aggregates: dict[str, dict]) -> None:
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
        if season.get("id") == "mos2627":
            tid = "mos2627"
        if not tid or tid not in aggregates:
            if tid:
                apply_season_plus_minus(season, _tournament(data, tid), tid)
            continue
        agg = aggregate_games(aggregates[tid].get("_raw") or [])
        if agg:
            n = agg["games"]
            season["kpiPerGame"] = agg["kpiGame"]
            season["plusMinusPerGame"] = agg["plusMinus"]
            season["plusMinusTotal"] = int(round(agg["plusMinus"] * agg["games"]))
            season["protocolGames"] = n
            season["games"] = f"{n} ({n})"
        else:
            apply_season_plus_minus(season, _tournament(data, tid), tid)


def _tournament(data: dict, tid: str) -> dict | None:
    return next((t for t in data["gameLogs"]["tournaments"] if t.get("id") == tid), None)


def build_metrics(
    active: dict,
    was: dict,
    team: dict | None,
    *,
    active_scope: str,
    was_scope: str,
    team_scope: str | None,
) -> list[dict]:
    items = []
    for key, label, hint, higher in METRIC_DEFS:
        entry = {
            "id": key,
            "label": label,
            "hint": hint,
            "value": active.get(key),
            "was": was.get(key) if was else None,
            "higher": higher,
            "scope": active_scope,
        }
        if was and was.get(key) is not None:
            entry["wasScope"] = was_scope
        if key == "kpi20" and team and team.get("kpi20") is not None:
            entry["team"] = team.get("kpi20")
            if team_scope:
                entry["teamScope"] = team_scope
        if key == "ts" and team and team.get("ts") is not None:
            entry["team"] = round(team["ts"] * 100)
            if team_scope:
                entry["teamScope"] = team_scope
        if key == "astTo" and team and team.get("astTo") is not None:
            entry["team"] = team.get("astTo")
            if team_scope:
                entry["teamScope"] = team_scope
        if key == "stl20" and team and team.get("stl20") is not None:
            entry["team"] = team.get("stl20")
            if team_scope:
                entry["teamScope"] = team_scope
        items.append(entry)
    return items


def refresh_kpi(data: dict, notes: list[str]) -> None:
    old_kpi = copy.deepcopy(data.get("kpi") or {})
    old_mvp = old_kpi.get("mvp")
    # Протоколы GetOnline не пишем в JSON — там есть PersonID.
    cache: dict[str, Any] = {}

    indices: dict[str, dict[str, Any]] = {}
    aggregates: dict[str, dict] = {}
    all_by_id: dict[int, dict] = {}

    for comp_id, team_id, tournament_id in KPI_SOURCES:
        try:
            rows = fetch_comp_games(comp_id, team_id)
        except Exception as exc:
            notes.append(f"kpi: comp {comp_id} не прочитан ({type(exc).__name__})")
            continue
        aggregates[tournament_id] = {"_raw": rows}
        idx = build_match_index(rows)
        indices[tournament_id] = idx
        all_by_id.update(idx["by_id"])

    if not indices:
        notes.append("kpi: индекс игр пуст, прежние значения на месте")
        return

    ensure_log_columns(data)
    patched = patch_log_rows(data, indices)
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
    active_games = int(active.get("games") or 0)
    was_games = int(was.get("games") or 0)
    active_scope = scope_season(kpi["activeLabel"], active_games)
    was_scope = scope_season(kpi["wasLabel"].split(",")[0].strip(), was_games) if was_id == "2425" else scope_season(kpi["wasLabel"], was_games)
    team_scope = scope_tournament("МЛБЛ-Дети U12", season_api.get("u12", {}).get("games") or 0) if team else None

    if games_2627 < 3:
        kpi["caption"] = f"Пока в сезоне 2026/27 мало игр с протоколом — цифры за {kpi['activeLabel']} ({active_games} игр, МЛБЛ + ПМ)."
    else:
        kpi["caption"] = f"Сезон {kpi['activeLabel']}. «Было» — {kpi['wasLabel']}."

    kpi["scopeHeadline"] = active_scope
    kpi["wasScopeHeadline"] = was_scope

    kpi["metrics"] = build_metrics(
        active,
        was,
        team or old_kpi.get("teamAvg"),
        active_scope=active_scope,
        was_scope=was_scope,
        team_scope=team_scope,
    )
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
            kpi["tournaments"].append(
                {
                    "id": tid,
                    "label": label,
                    "games": agg["games"],
                    "kpiGame": agg["kpiGame"],
                    "kpi20": agg["kpi20"],
                    "scope": scope_tournament(label, agg["games"]),
                }
            )

    kpi.pop("sync", None)

    if old_mvp:
        kpi["mvp"] = old_mvp
    else:
        kpi["mvp"] = copy.deepcopy(DEFAULT_MVP)

    if not kpi.get("best"):
        kpi["best"] = copy.deepcopy(kpi["mvp"])
        kpi["best"]["mvp"] = False

    if not match_same(kpi.get("best"), kpi.get("mvp")):
        maybe_update_best(kpi, all_by_id, data, cache, notes)

    refresh_trend(data, season_api)
    refresh_season_cards(data, aggregates)
    try:
        from update_stats import refresh_mama_notes

        refresh_mama_notes(data)
        refresh_career_notes(data)
    except Exception:
        pass
