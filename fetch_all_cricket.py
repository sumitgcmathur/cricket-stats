"""
Cricket Stats Fetcher — All Cricsheet Data
==========================================
Downloads ball-by-ball CSV data for ALL competitions from cricsheet.org
and generates one JSON file per competition + a master index.json

Output structure:
  stats/
    index.json          ← list of all competitions
    tests.json
    odis.json
    t20is.json
    ipl.json
    bbl.json
    psl.json
    ... (one per competition)

Usage:
  python fetch_all_cricket.py              # fetch everything
  python fetch_all_cricket.py --comp ipl  # fetch one competition only
"""

import urllib.request
import zipfile
import io
import csv
import json
import os
import sys
import datetime
from collections import defaultdict

# ── All Cricsheet competitions ───────────────────────────────────────────────
COMPETITIONS = [
    # International
    {"code": "tests",   "name": "Test Matches",           "format": "Test",  "type": "international"},
    {"code": "odis",    "name": "One Day Internationals", "format": "ODI",   "type": "international"},
    {"code": "t20is",   "name": "T20 Internationals",     "format": "T20",   "type": "international"},

    # T20 Leagues
    {"code": "ipl",     "name": "Indian Premier League",        "format": "T20", "type": "league"},
    {"code": "bbl",     "name": "Big Bash League",              "format": "T20", "type": "league"},
    {"code": "psl",     "name": "Pakistan Super League",        "format": "T20", "type": "league"},
    {"code": "cpl",     "name": "Caribbean Premier League",     "format": "T20", "type": "league"},
    {"code": "sa20",    "name": "SA20",                         "format": "T20", "type": "league"},
    {"code": "lpl",     "name": "Lanka Premier League",         "format": "T20", "type": "league"},
    {"code": "hundred", "name": "The Hundred",                  "format": "T20", "type": "league"},
    {"code": "ilt20",   "name": "International League T20",     "format": "T20", "type": "league"},
    {"code": "mlc",     "name": "Major League Cricket",         "format": "T20", "type": "league"},
    {"code": "wbbl",    "name": "Women's Big Bash League",      "format": "T20", "type": "league"},
    {"code": "wcpl",    "name": "Women's CPL",                  "format": "T20", "type": "league"},

    # Domestic
    {"code": "ntb",     "name": "County Championship",          "format": "Test", "type": "domestic"},
    {"code": "nto",     "name": "One-Day Cup (England)",        "format": "ODI",  "type": "domestic"},
    {"code": "ntt",     "name": "T20 Blast",                    "format": "T20",  "type": "domestic"},
    {"code": "shield",  "name": "Sheffield Shield",             "format": "Test", "type": "domestic"},
    {"code": "smat",    "name": "Syed Mushtaq Ali Trophy",      "format": "T20",  "type": "domestic"},
    {"code": "super50", "name": "Super 50 Cup",                 "format": "ODI",  "type": "domestic"},
]

BASE_URL = "https://cricsheet.org/downloads/{code}_male_csv2.zip"
STATS_DIR = "stats"


def download_zip(code):
    url = BASE_URL.format(code=code)
    print(f"  📥 Downloading {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "cricket-stats-fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def parse_zip(zip_bytes, comp):
    """Parse ball-by-ball CSV zip and return aggregated stats."""
    format_ = comp["format"]

    batters  = defaultdict(lambda: {
        "runs": 0, "balls": 0, "fours": 0, "sixes": 0,
        "fifties": 0, "hundreds": 0, "matches": set(), "innings_list": []
    })
    bowlers  = defaultdict(lambda: {
        "runs": 0, "balls": 0, "wickets": 0, "matches": set()
    })
    teams    = defaultdict(lambda: {"wins": 0, "matches": set()})
    seasons  = set()
    total_matches = 0

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_files = [f for f in zf.namelist() if f.endswith(".csv") and "info" not in f]
        total_matches = len(csv_files)
        print(f"  🔄 Processing {total_matches} matches ...")

        for fname in csv_files:
            with zf.open(fname) as f:
                try:
                    rows = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8")))
                except Exception:
                    continue
                if not rows:
                    continue

                match_id = rows[0].get("match_id", fname)
                season   = rows[0].get("season", "")
                if season:
                    seasons.add(season)

                # per-innings run tracker for milestones
                inn_runs = defaultdict(int)  # (innings, batter) -> runs

                for row in rows:
                    batter      = row.get("striker", "").strip()
                    bowler      = row.get("bowler", "").strip()
                    bat_team    = row.get("batting_team", "").strip()
                    bowl_team   = row.get("bowling_team", "").strip()
                    runs_bat    = int(row.get("runs_off_bat", 0) or 0)
                    extras      = int(row.get("extras", 0) or 0)
                    wicket_type = row.get("wicket_type", "").strip()
                    innings     = row.get("innings", "1")
                    winner      = row.get("winner", "").strip()

                    # Teams
                    for t in [bat_team, bowl_team]:
                        if t:
                            teams[t]["matches"].add(match_id)
                    if winner:
                        teams[winner]["wins"] += 1

                    # Batter
                    if batter:
                        b = batters[batter]
                        b["runs"]   += runs_bat
                        b["balls"]  += 1
                        b["matches"].add(match_id)
                        if runs_bat == 4: b["fours"] += 1
                        if runs_bat == 6: b["sixes"] += 1
                        inn_runs[(innings, batter)] += runs_bat

                    # Bowler
                    if bowler and format_ != "Test":  # skip Test bowling aggregation complexity
                        bl = bowlers[bowler]
                        bl["runs"]  += runs_bat + extras
                        bl["balls"] += 1
                        bl["matches"].add(match_id)
                        if wicket_type and wicket_type not in (
                            "run out", "retired hurt", "obstructing the field"
                        ):
                            bl["wickets"] += 1
                    elif bowler and format_ == "Test":
                        bl = bowlers[bowler]
                        bl["runs"]  += runs_bat + extras
                        bl["balls"] += 1
                        bl["matches"].add(match_id)
                        if wicket_type and wicket_type not in (
                            "run out", "retired hurt", "obstructing the field"
                        ):
                            bl["wickets"] += 1

                # Milestones
                for (inn, batter), runs in inn_runs.items():
                    if batter in batters:
                        if runs >= 100:
                            batters[batter]["hundreds"] += 1
                        elif runs >= 50:
                            batters[batter]["fifties"]  += 1

    return batters, bowlers, teams, sorted(seasons), total_matches


def build_output(batters, bowlers, teams, seasons, total_matches, comp):
    format_ = comp["format"]

    # ── Batting ──────────────────────────────────────────────────────────────
    batting_list = []
    for name, s in batters.items():
        m = len(s["matches"])
        if m < 3 or s["balls"] < 10:
            continue
        sr  = round(s["runs"] / s["balls"] * 100, 2) if s["balls"] else 0
        avg = round(s["runs"] / max(m, 1), 2)
        batting_list.append({
            "name": name,
            "matches": m,
            "runs": s["runs"],
            "balls": s["balls"],
            "avg": avg,
            "sr": sr,
            "fours": s["fours"],
            "sixes": s["sixes"],
            "fifties": s["fifties"],
            "hundreds": s["hundreds"],
        })
    batting_list.sort(key=lambda x: x["runs"], reverse=True)

    # ── Bowling ───────────────────────────────────────────────────────────────
    bowling_list = []
    for name, s in bowlers.items():
        m = len(s["matches"])
        if m < 3 or s["balls"] < 12:
            continue
        overs   = round(s["balls"] // 6 + (s["balls"] % 6) / 10, 1)
        economy = round(s["runs"] / s["balls"] * 6, 2) if s["balls"] else 0
        avg     = round(s["runs"] / s["wickets"], 2) if s["wickets"] else None
        bowling_list.append({
            "name": name,
            "matches": m,
            "wickets": s["wickets"],
            "runs": s["runs"],
            "balls": s["balls"],
            "overs": overs,
            "economy": economy,
            "avg": avg,
        })
    bowling_list.sort(key=lambda x: x["wickets"], reverse=True)

    # ── Sixes ─────────────────────────────────────────────────────────────────
    sixes_list = sorted(
        [{"name": n, "sixes": s["sixes"], "matches": len(s["matches"])}
         for n, s in batters.items() if s["sixes"] > 0],
        key=lambda x: x["sixes"], reverse=True
    )[:30]

    # ── Teams ─────────────────────────────────────────────────────────────────
    teams_list = []
    for name, s in teams.items():
        if not name:
            continue
        m = len(s["matches"])
        if m < 3:
            continue
        win_pct = round(s["wins"] / m * 100, 1)
        teams_list.append({
            "team": name,
            "matches": m,
            "wins": s["wins"],
            "win_pct": win_pct,
        })
    teams_list.sort(key=lambda x: x["wins"], reverse=True)

    return {
        "competition": comp["name"],
        "code": comp["code"],
        "format": format_,
        "type": comp["type"],
        "total_matches": total_matches,
        "seasons": seasons,
        "last_updated": datetime.datetime.now().strftime("%d %b %Y, %H:%M"),
        "batting":  batting_list[:50],
        "bowling":  bowling_list[:50],
        "sixes":    sixes_list,
        "teams":    teams_list,
    }


def fetch_competition(comp):
    code = comp["code"]
    print(f"\n{'─'*50}")
    print(f"🏏 {comp['name']} ({code})")
    try:
        zip_bytes = download_zip(code)
        batters, bowlers, teams, seasons, total = parse_zip(zip_bytes, comp)
        data = build_output(batters, bowlers, teams, seasons, total, comp)
        out_path = os.path.join(STATS_DIR, f"{code}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  ✅ {total} matches → {out_path}")
        return {
            "code": code,
            "name": comp["name"],
            "format": comp["format"],
            "type": comp["type"],
            "total_matches": total,
            "seasons": seasons,
        }
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        return None


def build_index(results):
    index = {
        "last_updated": datetime.datetime.now().strftime("%d %b %Y, %H:%M"),
        "competitions": [r for r in results if r],
    }
    with open(os.path.join(STATS_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"\n📋 index.json written with {len(index['competitions'])} competitions")


def main():
    os.makedirs(STATS_DIR, exist_ok=True)

    # Allow filtering: python fetch_all_cricket.py --comp ipl psl
    filter_codes = []
    if "--comp" in sys.argv:
        idx = sys.argv.index("--comp")
        filter_codes = sys.argv[idx+1:]

    comps = [c for c in COMPETITIONS if not filter_codes or c["code"] in filter_codes]
    print(f"🚀 Fetching {len(comps)} competition(s) from Cricsheet...")

    results = []
    for comp in comps:
        result = fetch_competition(comp)
        results.append(result)

    build_index(results)
    print("\n✅ All done!")


if __name__ == "__main__":
    main()
