"""
IPL Stats Data Fetcher - Using Cricsheet
Downloads IPL ball-by-ball CSV data from cricsheet.org
and processes it into a clean stats.json for your webpage.

Run this script after each IPL match week to refresh the data.
Usage: python fetch_ipl_data.py
"""

import urllib.request
import zipfile
import io
import csv
import json
from collections import defaultdict

CRICSHEET_IPL_URL = "https://cricsheet.org/downloads/ipl_male_csv2.zip"

def download_data():
    print("📥 Downloading IPL data from Cricsheet...")
    with urllib.request.urlopen(CRICSHEET_IPL_URL) as response:
        return response.read()

def parse_ipl_data(zip_bytes):
    print("🔄 Parsing ball-by-ball data...")

    batters = defaultdict(lambda: {"runs": 0, "balls": 0, "innings": 0,
                                    "fours": 0, "sixes": 0, "fifties": 0,
                                    "hundreds": 0, "matches": set()})
    bowlers = defaultdict(lambda: {"runs": 0, "balls": 0, "wickets": 0,
                                    "innings": 0, "matches": set(),
                                    "four_wkt": 0, "five_wkt": 0})
    season_winners = {}
    team_wins = defaultdict(int)
    team_matches = defaultdict(int)

    # Track innings per match per batter for milestone counting
    innings_runs = defaultdict(lambda: defaultdict(int))  # match_id+innings -> batter -> runs

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        files = [f for f in zf.namelist() if f.endswith('.csv') and 'info' not in f]
        print(f"   Found {len(files)} match files")

        for fname in files:
            with zf.open(fname) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8'))
                rows = list(reader)
                if not rows:
                    continue

                match_id = rows[0].get('match_id', fname)
                season = rows[0].get('season', 'Unknown')

                # Track match results for team wins
                match_teams = set()
                match_winner = None

                for row in rows:
                    batter = row.get('striker', '')
                    bowler = row.get('bowler', '')
                    batting_team = row.get('batting_team', '')
                    bowling_team = row.get('bowling_team', '')
                    runs_off_bat = int(row.get('runs_off_bat', 0) or 0)
                    extras = int(row.get('extras', 0) or 0)
                    wicket_type = row.get('wicket_type', '')
                    innings = row.get('innings', '1')
                    winner = row.get('winner', '')

                    if winner:
                        match_winner = winner
                    match_teams.add(batting_team)
                    match_teams.add(bowling_team)

                    # Batter stats
                    if batter:
                        b = batters[batter]
                        b["runs"] += runs_off_bat
                        b["balls"] += 1
                        b["matches"].add(match_id)
                        if runs_off_bat == 4:
                            b["fours"] += 1
                        if runs_off_bat == 6:
                            b["sixes"] += 1
                        innings_key = f"{match_id}_{innings}"
                        innings_runs[innings_key][batter] += runs_off_bat

                    # Bowler stats
                    if bowler:
                        bl = bowlers[bowler]
                        bl["runs"] += runs_off_bat + extras
                        bl["balls"] += 1
                        bl["matches"].add(match_id)
                        if wicket_type and wicket_type not in ('run out', 'retired hurt', 'obstructing the field'):
                            bl["wickets"] += 1

                # Count innings milestones
                for inn_key, inn_batters in innings_runs.items():
                    if match_id in inn_key:
                        for batter, runs in inn_batters.items():
                            if runs >= 100:
                                batters[batter]["hundreds"] += 1
                            elif runs >= 50:
                                batters[batter]["fifties"] += 1

                # Team wins
                for team in match_teams:
                    if team:
                        team_matches[team] += 1
                if match_winner:
                    team_wins[match_winner] += 1

    return batters, bowlers, team_wins, team_matches

def build_stats(batters, bowlers, team_wins, team_matches):
    print("📊 Building stats...")

    # Top run scorers
    top_batters = []
    for name, s in batters.items():
        if s["balls"] > 0 and len(s["matches"]) >= 5:
            sr = round((s["runs"] / s["balls"]) * 100, 2)
            top_batters.append({
                "name": name,
                "runs": s["runs"],
                "matches": len(s["matches"]),
                "balls": s["balls"],
                "strike_rate": sr,
                "fours": s["fours"],
                "sixes": s["sixes"],
                "fifties": s["fifties"],
                "hundreds": s["hundreds"],
                "avg": round(s["runs"] / max(len(s["matches"]), 1), 2)
            })
    top_batters.sort(key=lambda x: x["runs"], reverse=True)

    # Top wicket takers
    top_bowlers = []
    for name, s in bowlers.items():
        if s["balls"] > 0 and len(s["matches"]) >= 5:
            overs = s["balls"] // 6 + (s["balls"] % 6) / 10
            economy = round((s["runs"] / s["balls"]) * 6, 2) if s["balls"] > 0 else 0
            top_bowlers.append({
                "name": name,
                "wickets": s["wickets"],
                "matches": len(s["matches"]),
                "runs": s["runs"],
                "overs": round(overs, 1),
                "economy": economy,
                "avg": round(s["runs"] / max(s["wickets"], 1), 2)
            })
    top_bowlers.sort(key=lambda x: x["wickets"], reverse=True)

    # Most sixes
    top_six_hitters = sorted(
        [{"name": n, "sixes": s["sixes"], "matches": len(s["matches"])}
         for n, s in batters.items() if s["sixes"] > 0],
        key=lambda x: x["sixes"], reverse=True
    )

    # Team win %
    team_stats = []
    for team, wins in team_wins.items():
        if team and team_matches[team] >= 10:
            team_stats.append({
                "team": team,
                "wins": wins,
                "matches": team_matches[team],
                "win_pct": round((wins / team_matches[team]) * 100, 1)
            })
    team_stats.sort(key=lambda x: x["wins"], reverse=True)

    return {
        "top_batters": top_batters[:20],
        "top_bowlers": top_bowlers[:20],
        "top_six_hitters": top_six_hitters[:15],
        "team_stats": team_stats,
        "last_updated": __import__('datetime').datetime.now().strftime("%d %b %Y, %H:%M")
    }

def main():
    try:
        zip_bytes = download_data()
        batters, bowlers, team_wins, team_matches = parse_ipl_data(zip_bytes)
        stats = build_stats(batters, bowlers, team_wins, team_matches)

        with open("stats.json", "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

        print(f"✅ Done! stats.json generated.")
        print(f"   Top batter: {stats['top_batters'][0]['name']} - {stats['top_batters'][0]['runs']} runs")
        print(f"   Top bowler: {stats['top_bowlers'][0]['name']} - {stats['top_bowlers'][0]['wickets']} wickets")

    except Exception as e:
        print(f"❌ Error: {e}")
        raise

if __name__ == "__main__":
    main()
