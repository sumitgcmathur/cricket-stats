"""
Cricket Stats Fetcher — T20 only (Cricsheet)
==========================================
Downloads ball-by-ball CSV data for T20 competitions from cricsheet.org.
Competition list, defaults, team aliases, and paths live in config.json (repository root).

Usage:
  python fetch_all_cricket.py                    # uses site.defaultFetchCodes from config.json
  python fetch_all_cricket.py --comp ipl wpl     # explicit codes from cricsheet.competitions in config.json
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

# Ensure Unicode output works on Windows consoles (avoid crashing on emoji).
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_ROOT = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_ROOT, "config.json")


def _load_project_config():
    if not os.path.isfile(_CONFIG_PATH):
        raise FileNotFoundError(f"Missing {_CONFIG_PATH} — create it or restore from the repo.")
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _build_fetch_globals(cfg):
    """Derive COMPETITIONS, paths, and aliases from config.json."""
    site = cfg.get("site") or {}
    cr = cfg.get("cricsheet") or {}
    competitions = []
    for c in cr.get("competitions") or []:
        row = {
            "code": c["code"],
            "name": c["name"],
            "format": c["format"],
            "type": c["type"],
        }
        zf = c.get("zipFile")
        if zf:
            row["zip_name"] = zf
        competitions.append(row)
    download_base = (cr.get("downloadBase") or "https://cricsheet.org/downloads/").rstrip("/") + "/"
    pattern = cr.get("maleCsvZipPattern") or "{code}_male_csv2.zip"
    stats_dir = site.get("statsOutputDirectory") or "stats"
    default_fetch = tuple(site.get("defaultFetchCodes") or ("t20s", "ipl", "bbl", "cpl"))
    aliases = dict(cfg.get("teamAliases") or {})
    base_url_template = download_base + pattern
    return competitions, download_base, base_url_template, stats_dir, default_fetch, aliases


_cfg = _load_project_config()
COMPETITIONS, DOWNLOAD_BASE, BASE_URL, STATS_DIR, DEFAULT_FETCH_CODES, TEAM_ALIASES = _build_fetch_globals(_cfg)


def norm_team(name: str) -> str:
    n = (name or "").strip()
    return TEAM_ALIASES.get(n, n)


def download_zip(comp):
    """comp is a competition dict (needs at least code; optional zip_name)."""
    if isinstance(comp, str):
        comp = {"code": comp}
    if comp.get("zip_name"):
        url = DOWNLOAD_BASE + comp["zip_name"]
    else:
        url = BASE_URL.format(code=comp["code"])
    print(f"  📥 {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "cricket-stats-fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


# ── SCORECARD BUILDER ────────────────────────────────────────────────────────
def build_scorecard(match_id, rows, match_winner="", match_win_margin="", match_outcome="", match_number="", match_stage="", match_teams=None):
    """Build a full match scorecard from ball-by-ball rows."""
    if not rows:
        return None

    r0 = rows[0]
    season   = r0.get("season", "")
    venue    = r0.get("venue", "")
    date     = r0.get("start_date", "") or r0.get("date", "")

    # Collect teams in batting order (ball rows may be empty for washouts)
    team_order = []
    for row in rows:
        t = norm_team(row.get("batting_team", ""))
        if t and t not in team_order:
            team_order.append(t)
    if (not team_order or len(team_order) < 2) and match_teams:
        for t in [norm_team(x) for x in match_teams]:
            if t and t not in team_order:
                team_order.append(t)

    winner     = norm_team(match_winner)
    win_margin = match_win_margin
    outcome    = match_outcome   # no result, tie, super over etc
    match_num  = match_number
    stage      = match_stage     # qualifier, eliminator, final etc

    innings_data = defaultdict(lambda: {
        "batting_team": "",
        "bowling_team": "",
        "batter_balls": {},
        "bowler_balls": {},
        "batters": defaultdict(lambda: {
            "runs": 0, "balls": 0, "fours": 0, "sixes": 0,
            "dismissal": "", "bowler": "", "order": 999
        }),
        "bowlers": defaultdict(lambda: {
            "overs": 0, "balls": 0, "maidens": 0,
            "runs": 0, "wickets": 0
        }),
        "extras": {"wides": 0, "noballs": 0, "byes": 0, "legbyes": 0, "penalty": 0},
        "total_runs": 0,
        "total_wickets": 0,
        "overs_bowled": 0,
        "fall_of_wickets": [],
        "batter_order": [],
    })

    # Track ball number per over for maiden detection
    over_runs = defaultdict(lambda: defaultdict(int))  # innings -> over -> runs

    for row in rows:
        inn        = int(row.get("innings", 1))
        batter     = row.get("striker", "").strip()
        non_str    = row.get("non_striker", "").strip()
        bowler     = row.get("bowler", "").strip()
        bat_team   = norm_team(row.get("batting_team", "").strip())
        bowl_team  = norm_team(row.get("bowling_team", "").strip())
        runs_bat   = int(row.get("runs_off_bat", 0) or 0)
        extras_tot = int(row.get("extras", 0) or 0)
        wides      = int(row.get("wides", 0) or 0)
        noballs    = int(row.get("noballs", 0) or 0)
        byes       = int(row.get("byes", 0) or 0)
        legbyes    = int(row.get("legbyes", 0) or 0)
        penalty    = int(row.get("penalty", 0) or 0)
        wicket_t   = row.get("wicket_type", "").strip()
        player_out = row.get("player_dismissed", "").strip()
        fielder    = row.get("fielders", "") or row.get("fielder", "")
        over_num   = row.get("ball", "0").split(".")[0] if "." in str(row.get("ball","")) else row.get("over","0")

        d = innings_data[inn]
        d["batting_team"]  = bat_team
        d["bowling_team"]  = bowl_team
        d["total_runs"]   += runs_bat + extras_tot

        # Batter order
        if batter and batter not in d["batter_order"]:
            d["batter_order"].append(batter)
        if non_str and non_str not in d["batter_order"]:
            d["batter_order"].append(non_str)

        # Batter stats (only count if not wide)
        if batter and not wides:
            b = d["batters"][batter]
            b["runs"]  += runs_bat
            b["balls"] += 1
            if runs_bat == 4: b["fours"] += 1
            if runs_bat == 6: b["sixes"] += 1
            # Ball-by-ball for chart
            if batter not in d["batter_balls"]:
                d["batter_balls"][batter] = []
            d["batter_balls"][batter].append(runs_bat)

        # Bowler stats
        if bowler:
            bl = d["bowlers"][bowler]
            bl["runs"] += runs_bat + wides + noballs
            if not wides and not noballs:
                bl["balls"] += 1
            over_runs[inn][str(over_num)] += runs_bat + wides + noballs
            # Ball-by-ball for bowler chart
            if bowler not in d["bowler_balls"]:
                d["bowler_balls"][bowler] = []
            is_wkt = 1 if (wicket_t and wicket_t not in ("run out","retired hurt","obstructing the field")) else 0
            d["bowler_balls"][bowler].append({"r":runs_bat,"w":is_wkt,"wide":1 if wides else 0,"nb":1 if noballs else 0})

            # Ball-by-ball for bowler chart
            if bowler not in d["bowler_balls"]:
                d["bowler_balls"][bowler] = []
            d["bowler_balls"][bowler].append({
                "r": runs_bat + (byes + legbyes if not wides and not noballs else 0),
                "w": 1 if (wicket_t and wicket_t not in ("run out","retired hurt","obstructing the field")) else 0,
                "wide": 1 if wides else 0,
                "nb": 1 if noballs else 0
            })

        # Wicket
        if wicket_t and player_out:
            d["total_wickets"] += 1
            if player_out in d["batters"]:
                dismissal_str = format_dismissal(wicket_t, bowler, fielder)
                d["batters"][player_out]["dismissal"] = dismissal_str
                d["batters"][player_out]["bowler"]    = bowler
            d["fall_of_wickets"].append({
                "wicket": d["total_wickets"],
                "player": player_out,
                "runs":   d["total_runs"],
            })

        # Extras breakdown
        d["extras"]["wides"]   += wides
        d["extras"]["noballs"] += noballs
        d["extras"]["byes"]    += byes
        d["extras"]["legbyes"] += legbyes
        d["extras"]["penalty"] += penalty

    # Calculate overs and maidens
    for inn, d in innings_data.items():
        max_over = 0
        for bowler, bl in d["bowlers"].items():
            overs_full = bl["balls"] // 6
            overs_part = bl["balls"] % 6
            bl["overs"] = overs_full + overs_part / 10
            bl["economy"] = round(bl["runs"] / bl["balls"] * 6, 2) if bl["balls"] else 0
        for over_str, runs in over_runs[inn].items():
            try:
                max_over = max(max_over, int(over_str) + 1)
                if runs == 0:
                    for bl in d["bowlers"].values():
                        pass  # maiden detection needs per-bowler over tracking; simplified here
            except:
                pass
        d["overs_bowled"] = max_over

    # Serialise
    def serialise_innings(inn_num, d):
        batters_out = []
        for name in d["batter_order"]:
            if name not in d["batters"]:
                continue
            b = d["batters"][name]
            sr = round(b["runs"] / b["balls"] * 100, 1) if b["balls"] else 0
            batters_out.append({
                "name":      name,
                "runs":      b["runs"],
                "balls":     b["balls"],
                "fours":     b["fours"],
                "sixes":     b["sixes"],
                "sr":        sr,
                "dismissal": b["dismissal"] or "not out",
                "bowler":    b["bowler"],
            })

        bowlers_out = sorted([
            {
                "name":     name,
                "overs":    round(bl["overs"], 1),
                "runs":     bl["runs"],
                "wickets":  bl["wickets"],
                "economy":  bl["economy"],
                "maidens":  bl["maidens"],
            }
            for name, bl in d["bowlers"].items()
        ], key=lambda x: -x["wickets"])

        extras = d["extras"]
        extras_total = sum(extras.values())

        # Build over_by_over from over_runs for this innings
        inn_over_by_over = []
        cumulative = 0
        for ov in sorted(over_runs[inn_num].keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
            r = over_runs[inn_num][ov]
            cumulative += r
            inn_over_by_over.append({"over": int(ov)+1, "runs": r, "cumulative": cumulative})

        return {
            "innings":        inn_num,
            "batting_team":   d["batting_team"],
            "bowling_team":   d["bowling_team"],
            "total_runs":     d["total_runs"],
            "total_wickets":  d["total_wickets"],
            "overs":          d["overs_bowled"],
            "extras":         extras,
            "extras_total":   extras_total,
            "batters":        batters_out,
            "bowlers":        bowlers_out,
            "fall_of_wickets": d["fall_of_wickets"],
            "over_by_over":   inn_over_by_over,
            "batter_balls":   d["batter_balls"],
            "bowler_balls":   d["bowler_balls"],
        }

    innings_list = [serialise_innings(k, v) for k, v in sorted(innings_data.items())]

    # Match summary for index
    teams_from_innings = [i["batting_team"] for i in innings_list if i.get("batting_team")]
    scores_from_innings = [f"{i['total_runs']}/{i['total_wickets']} ({i['overs']} ov)" for i in innings_list]

    # Prefer the teams collected from ball rows / info (handles washouts cleanly).
    teams = team_order[:2] if len(team_order) >= 2 else (teams_from_innings[:2] if len(teams_from_innings) >= 2 else team_order)
    # Scores only exist if innings exist; keep array aligned with teams.
    if len(scores_from_innings) >= 2:
        scores = scores_from_innings[:2]
    elif len(scores_from_innings) == 1 and len(teams) >= 2:
        scores = [scores_from_innings[0], ""]
    else:
        scores = scores_from_innings[:2]

    return {
        "match_id":    match_id,
        "season":      season,
        "date":        date,
        "venue":       venue,
        "teams":       teams,
        "scores":      scores,
        "winner":      winner,
        "win_margin":  win_margin,
        "outcome":     outcome,
        "match_number": match_num,
        "stage":       stage,
        "innings":     innings_list,
    }


def format_dismissal(wicket_type, bowler, fielder):
    wt = wicket_type.lower()
    if wt == "bowled":
        return f"b {bowler}"
    elif wt == "caught":
        f = fielder.split("|")[0].strip() if fielder else ""
        return f"c {f} b {bowler}" if f else f"c & b {bowler}"
    elif wt == "lbw":
        return f"lbw b {bowler}"
    elif wt == "run out":
        f = fielder.split("|")[0].strip() if fielder else ""
        return f"run out ({f})" if f else "run out"
    elif wt == "stumped":
        f = fielder.split("|")[0].strip() if fielder else ""
        return f"st {f} b {bowler}" if f else f"st b {bowler}"
    elif wt == "hit wicket":
        return f"hit wicket b {bowler}"
    elif wt == "caught and bowled":
        return f"c & b {bowler}"
    elif wt == "obstructing the field":
        return "obstructing the field"
    elif wt == "retired hurt":
        return "retired hurt"
    else:
        return wicket_type


def _inn_key(match_id, innings):
    return (match_id, str(innings))


def _bat_team_ssn_bucket():
    return {
        "runs": 0,
        "balls": 0,
        "fours": 0,
        "sixes": 0,
        "fifties": 0,
        "hundreds": 0,
        "mvp_pts": 0.0,
        "matches": set(),
        "dismissals": 0,
        "innings_ids": set(),
    }


def _bowl_team_ssn_bucket():
    return {"runs": 0, "balls": 0, "wickets": 0, "mvp_pts": 0.0, "matches": set(), "innings_ids": set()}


def _bat_team_season_bucket(b, team_name, season_key):
    """season_key may be '' when CSV season is missing."""
    if not team_name:
        return None
    bt_all = b.setdefault("by_team", {})
    tb = bt_all.setdefault(team_name, {"by_season": {}})
    sk = season_key if season_key is not None else ""
    bs_map = tb.setdefault("by_season", {})
    if sk not in bs_map:
        bs_map[sk] = _bat_team_ssn_bucket()
    return bs_map[sk]


def _bowl_team_season_bucket(bl, team_name, season_key):
    if not team_name:
        return None
    bt_all = bl.setdefault("by_team", {})
    tb = bt_all.setdefault(team_name, {"by_season": {}})
    sk = season_key if season_key is not None else ""
    bs_map = tb.setdefault("by_season", {})
    if sk not in bs_map:
        bs_map[sk] = _bowl_team_ssn_bucket()
    return bs_map[sk]


# ── MAIN PARSER ──────────────────────────────────────────────────────────────
def parse_zip(zip_bytes, comp):
    format_ = comp["format"]
    code    = comp["code"]

    batters  = defaultdict(lambda: {"runs":0,"balls":0,"fours":0,"sixes":0,"fifties":0,"hundreds":0,"matches":set(),"dismissals":0,"by_season":{}})
    bowlers  = defaultdict(lambda: {"runs":0,"balls":0,"wickets":0,"matches":set(),"by_season":{}})
    # Global style maps reduce misclassification when match info omits style rows.
    global_bowling_styles = {}
    global_batting_hands = {}
    teams    = defaultdict(lambda: {"wins":0,"matches":set(),"by_season":{}})
    team_won_matches = defaultdict(set)  # track per-match wins separately
    team_season_matches = defaultdict(lambda: defaultdict(set))  # team->season->match_ids
    # Official playing squad per match (Cricsheet info,player,Team,Player) — canonical "matches"
    xi_matches = defaultdict(set)  # player -> {match_id, ...}
    xi_by_season = defaultdict(lambda: defaultdict(set))  # player -> season -> {match_id}
    seasons  = set()
    match_index = []

    matches_dir = os.path.join(STATS_DIR, "matches", code)
    os.makedirs(matches_dir, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        all_files  = zf.namelist()
        csv_files  = [f for f in all_files if f.endswith(".csv") and "_info" not in f]
        info_files = {f.replace("_info.csv","").split("/")[-1]: f for f in all_files if f.endswith("_info.csv")}
        total = len(csv_files)
        print(f"  🔄 {total} matches ...")

        for fname in csv_files:
            with zf.open(fname) as f:
                try:
                    rows = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8")))
                except:
                    continue
                if not rows:
                    continue

                match_id = rows[0].get("match_id", fname.replace(".csv","").split("/")[-1])
                season   = rows[0].get("season","")
                if season:
                    seasons.add(season)

                # Read winner, margin and player styles from info file
                match_winner_from_info = ""
                match_margin_from_info = ""
                match_outcome_from_info = ""
                match_number_from_info = ""
                match_stage_from_info = ""
                match_event_from_info = ""
                match_teams_from_info = []
                match_bowling_styles = {}
                match_batting_hands = {}
                info_key = fname.replace(".csv","").split("/")[-1]
                if info_key in info_files:
                    try:
                        with zf.open(info_files[info_key]) as inf:
                            for line in io.TextIOWrapper(inf, encoding="utf-8"):
                                parts = [p.strip() for p in line.strip().split(",")]
                                if len(parts) >= 3 and parts[0] == "info":
                                    if parts[1] == "winner":
                                        match_winner_from_info = ",".join(parts[2:]).strip()
                                    elif parts[1] == "team":
                                        t = norm_team(",".join(parts[2:]).strip())
                                        if t and t not in match_teams_from_info:
                                            match_teams_from_info.append(t)
                                    elif parts[1] == "by":
                                        match_margin_from_info = ",".join(parts[2:]).strip()
                                    elif parts[1] == "outcome":
                                        outcome_val = ",".join(parts[2:]).strip()
                                        if not match_winner_from_info:
                                            match_outcome_from_info = outcome_val
                                    elif parts[1] == "event":
                                        # e.g. info,event,Indian Premier League
                                        match_event_from_info = ",".join(parts[2:]).strip()
                                    elif parts[1] == "match_number":
                                        # e.g. info,match_number,57
                                        match_number_from_info = ",".join(parts[2:]).strip()
                                    elif parts[1] == "stage":
                                        # Seen in some competitions
                                        match_stage_from_info = ",".join(parts[2:]).strip()
                                    elif parts[1] == "eliminator":
                                        # IPL CSV2 commonly exposes playoff marker this way
                                        match_stage_from_info = "Eliminator"
                                    elif parts[1] == "player_of_match" and len(parts) >= 3:
                                        pass  # could track this
                                    elif parts[1] == "bowling_style" and len(parts) >= 4:
                                        pname = parts[2].strip()
                                        bstyle = ",".join(parts[3:]).strip().lower()
                                        is_spin = any(x in bstyle for x in ["spin","finger","wrist","orthodox","chinaman","leg-break","off-break"])
                                        match_bowling_styles[pname] = "spin" if is_spin else "pace"
                                        global_bowling_styles[pname] = match_bowling_styles[pname]
                                    elif parts[1] == "batting_style" and len(parts) >= 4:
                                        pname = parts[2].strip()
                                        bstyle = ",".join(parts[3:]).strip().lower()
                                        hand = "left" if "left" in bstyle else "right"
                                        match_batting_hands[pname] = hand
                                        global_batting_hands[pname] = hand
                                    elif parts[1] == "player" and len(parts) >= 4:
                                        # info,player,TeamName,Player Name — playing squad (Cricsheet)
                                        pname = ",".join(parts[3:]).strip()
                                        if pname:
                                            xi_matches[pname].add(match_id)
                                            if season:
                                                xi_by_season[pname][season].add(match_id)
                    except:
                        pass

                # Track winner from info file
                match_winner_from_info = norm_team(match_winner_from_info)
                if match_winner_from_info and match_id not in team_won_matches[match_winner_from_info]:
                    team_won_matches[match_winner_from_info].add(match_id)
                    teams[match_winner_from_info]["wins"] += 1
                    if season:
                        if season not in teams[match_winner_from_info]["by_season"]:
                            teams[match_winner_from_info]["by_season"][season] = {"wins":0,"matches":0}
                        teams[match_winner_from_info]["by_season"][season]["wins"] += 1

                inn_runs = defaultdict(lambda: defaultdict(int))
                inn_bat_team = {}

                for row in rows:
                    batter     = row.get("striker","").strip()
                    bowler     = row.get("bowler","").strip()
                    bat_team   = norm_team(row.get("batting_team","").strip())
                    bowl_team  = norm_team(row.get("bowling_team","").strip())
                    runs_bat   = int(row.get("runs_off_bat",0) or 0)
                    extras     = int(row.get("extras",0) or 0)
                    # Needed for dot-ball logic (and some derived stats)
                    wides      = int(row.get("wides", 0) or 0)
                    noballs    = int(row.get("noballs", 0) or 0)
                    wicket_t   = row.get("wicket_type","").strip()
                    innings    = row.get("innings","1")
                    ball_str   = row.get("ball","0")
                    if bat_team:
                        inn_bat_team[(match_id, str(innings))] = bat_team
                    try:
                        over_num = int(float(ball_str))  # 0.1->0, 5.6->5, 15.3->15
                    except:
                        over_num = 0
                    phase = "powerplay" if over_num < 6 else "death" if over_num >= 15 else "middle"

                    for t in [bat_team, bowl_team]:
                        if t:
                            teams[t]["matches"].add(match_id)
                            if season:
                                team_season_matches[t][season].add(match_id)
                    # winner field in ball rows is empty - tracked from info file above
                    pass

                    if batter:
                        b = batters[batter]
                        b["runs"]  += runs_bat
                        b["balls"] += 1
                        b["matches"].add(match_id)
                        b.setdefault("innings_ids", set()).add(_inn_key(match_id, innings))
                        if runs_bat == 4: b["fours"] += 1
                        if runs_bat == 6: b["sixes"] += 1
                        inn_runs[innings][batter] += runs_bat
                        # MVP points: 4s=2.5, 6s=3.5
                        if "mvp_pts" not in b: b["mvp_pts"] = 0.0
                        if runs_bat == 4: b["mvp_pts"] += 2.5
                        elif runs_bat == 6: b["mvp_pts"] += 3.5
                        # Phase tracking (over_num already computed above)
                        if "phase_stats" not in b:
                            b["phase_stats"] = {"powerplay":{"r":0,"b":0},"middle":{"r":0,"b":0},"death":{"r":0,"b":0}}
                        b["phase_stats"][phase]["r"] += runs_bat
                        b["phase_stats"][phase]["b"] += 1
                        # vs bowler type (pace/spin)
                        if bowler:
                            bowl_type = match_bowling_styles.get(bowler) or global_bowling_styles.get(bowler)
                            if "vs_type" not in b:
                                b["vs_type"] = {"pace":{"r":0,"b":0},"spin":{"r":0,"b":0}}
                            if bowl_type in ("pace", "spin"):
                                b["vs_type"][bowl_type]["r"] += runs_bat
                                b["vs_type"][bowl_type]["b"] += 1
                        # Per-season tracking
                        if season:
                            if season not in b["by_season"]:
                                b["by_season"][season] = {
                                    "runs": 0,
                                    "balls": 0,
                                    "fours": 0,
                                    "sixes": 0,
                                    "fifties": 0,
                                    "hundreds": 0,
                                    "mvp_pts": 0.0,
                                    "matches": set(),
                                    "dismissals": 0,
                                    "innings_ids": set(),
                                }
                            bs = b["by_season"][season]
                            bs["runs"]  += runs_bat
                            bs["balls"] += 1
                            bs["matches"].add(match_id)
                            bs.setdefault("innings_ids", set()).add(_inn_key(match_id, innings))
                            if runs_bat == 4:
                                bs["fours"] += 1
                                bs["mvp_pts"] += 2.5
                            if runs_bat == 6:
                                bs["sixes"] += 1
                                bs["mvp_pts"] += 3.5
                        if bat_team:
                            sk_bt = season if season else ""
                            tss = _bat_team_season_bucket(b, bat_team, sk_bt)
                            tss["runs"] += runs_bat
                            tss["balls"] += 1
                            tss["matches"].add(match_id)
                            tss.setdefault("innings_ids", set()).add(_inn_key(match_id, innings))
                            if runs_bat == 4:
                                tss["fours"] += 1
                                tss["mvp_pts"] += 2.5
                            if runs_bat == 6:
                                tss["sixes"] += 1
                                tss["mvp_pts"] += 3.5

                    # Track dismissals for correct batting average
                    player_out = row.get("player_dismissed","").strip()
                    if player_out and wicket_t and wicket_t not in ("retired hurt",):
                        batters[player_out]["dismissals"] += 1
                        if season and season in batters[player_out]["by_season"]:
                            batters[player_out]["by_season"][season]["dismissals"] += 1
                        if bat_team:
                            sk_bt = season if season else ""
                            _bat_team_season_bucket(batters[player_out], bat_team, sk_bt)["dismissals"] += 1
                        # Fielding MVP (same scale as IPL broadcast table): catch / stumping = 2.5 pts
                        fld_raw = (row.get("fielders") or row.get("fielder") or "").strip()
                        wt_low = (wicket_t or "").strip().lower()
                        if fld_raw and wt_low in ("caught", "stumped"):
                            fname = fld_raw.split("|")[0].strip()
                            bowln = (bowler or "").strip().lower()
                            if fname:
                                fnamel = fname.lower()
                                # Caught by bowler (incl. caught & bowled): wicket already +3.5 to bowler — skip extra catch
                                if wt_low == "caught" and fnamel == bowln:
                                    pass
                                else:
                                    bf = batters[fname]
                                    if "mvp_pts" not in bf:
                                        bf["mvp_pts"] = 0.0
                                    bf["mvp_pts"] += 2.5
                                    bf["matches"].add(match_id)
                                    if season:
                                        if season not in bf["by_season"]:
                                            bf["by_season"][season] = {
                                                "runs": 0,
                                                "balls": 0,
                                                "fours": 0,
                                                "sixes": 0,
                                                "fifties": 0,
                                                "hundreds": 0,
                                                "mvp_pts": 0.0,
                                                "matches": set(),
                                                "dismissals": 0,
                                                "innings_ids": set(),
                                            }
                                        bs = bf["by_season"][season]
                                        bs["mvp_pts"] = bs.get("mvp_pts", 0) + 2.5
                                        bs["matches"].add(match_id)
                                    if bowl_team:
                                        sk_bt = season if season else ""
                                        fts = _bat_team_season_bucket(bf, bowl_team, sk_bt)
                                        fts["mvp_pts"] += 2.5
                                        fts["matches"].add(match_id)
                        # Track wickets per season and phase for bowling filter
                        if bowler and wicket_t not in ("run out","retired hurt","obstructing the field"):
                            if season and season in bowlers[bowler]["by_season"]:
                                bowlers[bowler]["by_season"][season]["wickets"] =                                     bowlers[bowler]["by_season"][season].get("wickets",0) + 1
                            if "phase_stats" in bowlers[bowler]:
                                bowlers[bowler]["phase_stats"][phase]["w"] += 1

                    if bowler:
                        bl = bowlers[bowler]
                        bl["runs"]  += runs_bat + extras
                        bl["balls"] += 1
                        bl["matches"].add(match_id)
                        bl.setdefault("innings_ids", set()).add(_inn_key(match_id, innings))
                        if wicket_t and wicket_t not in ("run out","retired hurt","obstructing the field"):
                            bl["wickets"] += 1
                        # Bowler split vs batter handedness
                        if "vs_hand" not in bl:
                            bl["vs_hand"] = {"left":{"runs":0,"balls":0,"wickets":0}, "right":{"runs":0,"balls":0,"wickets":0}}
                        batter_hand = match_batting_hands.get(batter) or global_batting_hands.get(batter)
                        if batter_hand in ("left", "right"):
                            hs = bl["vs_hand"][batter_hand]
                            hs["runs"] += runs_bat + extras
                            hs["balls"] += 1
                            if wicket_t and wicket_t not in ("run out","retired hurt","obstructing the field"):
                                hs["wickets"] += 1
                        # MVP points: wickets=3.5, dot balls=1
                        if "mvp_pts" not in bl: bl["mvp_pts"] = 0.0
                        if wicket_t and wicket_t not in ("run out","retired hurt","obstructing the field"):
                            bl["mvp_pts"] += 3.5
                        elif not wides and not noballs and runs_bat == 0 and not extras:
                            bl["mvp_pts"] += 1.0
                        # Phase and per-season tracking
                        if "phase_stats" not in bowlers[bowler]:
                            bowlers[bowler]["phase_stats"] = {
                                "powerplay":{"r":0,"b":0,"w":0},
                                "middle":{"r":0,"b":0,"w":0},
                                "death":{"r":0,"b":0,"w":0}
                            }
                        ps = bowlers[bowler]["phase_stats"][phase]
                        ps["r"] += runs_bat + extras
                        ps["b"] += 1
                        if wicket_t and wicket_t not in ("run out","retired hurt","obstructing the field"):
                            ps["w"] += 1
                        # Per-season tracking
                        if season:
                            if season not in bowlers[bowler]["by_season"]:
                                bowlers[bowler]["by_season"][season] = {
                                    "runs": 0,
                                    "balls": 0,
                                    "wickets": 0,
                                    "mvp_pts": 0.0,
                                    "matches": set(),
                                    "innings_ids": set(),
                                }
                            bs = bowlers[bowler]["by_season"][season]
                            bs["runs"]  += runs_bat + extras
                            bs["balls"] += 1
                            bs["matches"].add(match_id)
                            bs.setdefault("innings_ids", set()).add(_inn_key(match_id, innings))
                            # Per-season MVP points (must match overall logic above)
                            if wicket_t and wicket_t not in ("run out","retired hurt","obstructing the field"):
                                bs["mvp_pts"] += 3.5
                            elif not wides and not noballs and runs_bat == 0 and not extras:
                                bs["mvp_pts"] += 1.0
                        if bowl_team:
                            sk_bt = season if season else ""
                            bts = _bowl_team_season_bucket(bl, bowl_team, sk_bt)
                            bts["runs"] += runs_bat + extras
                            bts["balls"] += 1
                            bts["matches"].add(match_id)
                            bts.setdefault("innings_ids", set()).add(_inn_key(match_id, innings))
                            if wicket_t and wicket_t not in ("run out","retired hurt","obstructing the field"):
                                bts["wickets"] += 1
                            if wicket_t and wicket_t not in ("run out","retired hurt","obstructing the field"):
                                bts["mvp_pts"] += 3.5
                            elif not wides and not noballs and runs_bat == 0 and not extras:
                                bts["mvp_pts"] += 1.0

                for inn, bmap in inn_runs.items():
                    ibt = inn_bat_team.get((match_id, str(inn)))
                    sk_bt = season if season else ""
                    for batter, runs in bmap.items():
                        if runs >= 100:
                            batters[batter]["hundreds"] += 1
                            if season and season in batters[batter]["by_season"]:
                                batters[batter]["by_season"][season]["hundreds"] += 1
                            if ibt:
                                _bat_team_season_bucket(batters[batter], ibt, sk_bt)["hundreds"] += 1
                        elif runs >= 50:
                            batters[batter]["fifties"] += 1
                            if season and season in batters[batter]["by_season"]:
                                batters[batter]["by_season"][season]["fifties"] += 1
                            if ibt:
                                _bat_team_season_bucket(batters[batter], ibt, sk_bt)["fifties"] += 1

                # Build and save scorecard
                try:
                    sc = build_scorecard(
                        match_id,
                        rows,
                        match_winner_from_info,
                        match_margin_from_info,
                        match_outcome_from_info,
                        match_number_from_info,
                        match_stage_from_info,
                        match_teams_from_info,
                    )
                except Exception as _sc_err:
                    print(f"  ⚠️  Scorecard {match_id}: {_sc_err}")
                    sc = None
                if sc:
                    sc_path = os.path.join(matches_dir, f"{match_id}.json")
                    with open(sc_path, "w", encoding="utf-8") as sf:
                        json.dump(sc, sf, ensure_ascii=False, separators=(",",":"))
                    # Add to match index (lightweight)
                    norm_teams = [norm_team(t) for t in (sc.get("teams") or []) if t]
                    # ensure 2 teams when possible
                    if match_teams_from_info:
                        for t in [norm_team(x) for x in match_teams_from_info]:
                            if t and t not in norm_teams:
                                norm_teams.append(t)
                    norm_teams = norm_teams[:2]
                    match_index.append({
                        "id":      match_id,
                        "season":  sc["season"],
                        "date":    sc["date"],
                        "teams":   norm_teams,
                        "scores":  sc["scores"],
                        "winner":  norm_team(sc["winner"]),
                        "outcome": sc["outcome"],
                        "match_number": sc["match_number"],
                        "stage":   sc["stage"],
                        "venue":   sc["venue"],
                    })

    # Save match index
    match_index.sort(key=lambda x: x.get("date",""), reverse=True)
    with open(os.path.join(matches_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"matches": match_index}, f, ensure_ascii=False, separators=(",",":"))

    return batters, bowlers, teams, sorted(seasons), total, team_season_matches, xi_matches, xi_by_season


def _official_matches(name, ball_match_ids, xi_matches):
    """Cricsheet squad (info,player) when present; else ball-derived match IDs."""
    xs = xi_matches.get(name) if xi_matches else None
    if xs:
        return len(xs)
    return len(ball_match_ids)


def _official_matches_season(name, season, ball_season_ss, xi_by_season):
    inner = (xi_by_season or {}).get(name) or {}
    xs = inner.get(season) if hasattr(inner, "get") else None
    if xs:
        return len(xs)
    return len(ball_season_ss["matches"]) if isinstance(ball_season_ss.get("matches"), set) else int(
        ball_season_ss.get("matches", 0) or 0
    )


def _serialize_bat_by_team(s):
    out = {}
    for team, tb in (s.get("by_team") or {}).items():
        subs = {}
        for ssn, ss in (tb.get("by_season") or {}).items():
            sm = len(ss.get("matches") or [])
            if sm < 1 and not ss.get("balls"):
                continue
            sd = ss.get("dismissals", 0)
            inn_bt = len(ss.get("innings_ids") or [])
            mvp_bt = round(ss.get("mvp_pts", 0), 1)
            subs[ssn] = {
                "matches": sm,
                "runs": ss["runs"],
                "balls": ss["balls"],
                "dismissals": sd,
                "avg": round(ss["runs"] / sd, 2) if sd else ss["runs"],
                "sr": round(ss["runs"] / ss["balls"] * 100, 2) if ss["balls"] else 0,
                "fours": ss["fours"],
                "sixes": ss["sixes"],
                "fifties": ss["fifties"],
                "hundreds": ss["hundreds"],
                "mvp_pts": mvp_bt,
                "innings": inn_bt,
                "mvp_per_innings": round(mvp_bt / inn_bt, 2) if inn_bt else 0.0,
            }
        if subs:
            out[team] = {"by_season": subs}
    return out or None


def _serialize_bowl_by_team(s):
    out = {}
    for team, tb in (s.get("by_team") or {}).items():
        subs = {}
        for ssn, ss in (tb.get("by_season") or {}).items():
            sb = ss.get("balls", 0)
            if not sb:
                continue
            sw = ss.get("wickets", 0)
            sr = ss.get("runs", 0)
            sm = len(ss.get("matches") or [])
            secon = round(sr / sb * 6, 2) if sb else 0
            savg = round(sr / sw, 2) if sw else None
            sbi = round((sw / sm) * (6 / secon), 2) if secon > 0 and sm > 0 else 0
            inn_b = len(ss.get("innings_ids") or [])
            mvp_b = round(ss.get("mvp_pts", 0), 1)
            subs[ssn] = {
                "matches": sm,
                "wickets": sw,
                "runs": sr,
                "balls": sb,
                "economy": secon,
                "avg": savg,
                "bowl_index": sbi,
                "mvp_pts": mvp_b,
                "innings": inn_b,
                "mvp_per_innings": round(mvp_b / inn_b, 2) if inn_b else 0.0,
            }
        if subs:
            out[team] = {"by_season": subs}
    return out or None


def build_output(
    batters,
    bowlers,
    teams,
    seasons,
    total_matches,
    comp,
    team_season_matches=None,
    xi_matches=None,
    xi_by_season=None,
):
    if team_season_matches is None:
        team_season_matches = {}
    if xi_matches is None:
        xi_matches = {}
    if xi_by_season is None:
        xi_by_season = {}
    batting_list = []
    for name, s in batters.items():
        m = _official_matches(name, s["matches"], xi_matches)
        if m < 1 or s["balls"] < 6:
            continue  # min 1 match, min 1 over faced
        sr  = round(s["runs"] / s["balls"] * 100, 2) if s["balls"] else 0
        dismissals = s.get("dismissals", 0)
        avg = round(s["runs"]/dismissals, 2) if dismissals > 0 else s["runs"]  # not out avg
        # Build per-season summary
        by_season = {}
        for ssn, ss in s.get("by_season",{}).items():
            sm = _official_matches_season(name, ssn, ss, xi_by_season)
            if sm < 1:
                continue
            sd = ss.get("dismissals",0)
            inn_ct = len(ss.get("innings_ids") or [])
            mvp_v = round(ss.get("mvp_pts", 0), 1)
            by_season[ssn] = {
                "matches": sm, "runs": ss["runs"], "balls": ss["balls"],
                "dismissals": sd,
                "avg": round(ss["runs"]/sd,2) if sd else ss["runs"],
                "sr":  round(ss["runs"]/ss["balls"]*100,2) if ss["balls"] else 0,
                "fours": ss["fours"], "sixes": ss["sixes"],
                "fifties": ss["fifties"], "hundreds": ss["hundreds"],
                "mvp_pts": mvp_v,
                "innings": inn_ct,
                "mvp_per_innings": round(mvp_v / inn_ct, 2) if inn_ct else 0.0,
            }
        # Performance index: avg * (SR/100) - rewards both consistency and aggression
        perf_index = round(avg * (sr/100), 1) if sr > 0 else 0
        # Phase stats for batter
        raw_ps = s.get("phase_stats", {})
        phase_stats = {}
        for ph, ps in raw_ps.items():
            sr_ph = round(ps["r"]/ps["b"]*100, 1) if ps["b"] else 0
            phase_stats[ph] = {"runs":ps["r"],"balls":ps["b"],"sr":sr_ph}
        # vs bowler type
        vs_type = {}
        for bt, vt in s.get("vs_type",{}).items():
            vsr = round(vt["r"]/vt["b"]*100,1) if vt["b"] else 0
            vs_type[bt] = {"runs":vt["r"],"balls":vt["b"],"sr":vsr}
        inn_tot = len(s.get("innings_ids") or [])
        mvp_tot = round(s.get("mvp_pts", 0), 1)
        bat_row = {"name":name,"matches":m,"runs":s["runs"],"balls":s["balls"],
            "avg":avg,"sr":sr,"fours":s["fours"],"sixes":s["sixes"],
            "fifties":s["fifties"],"hundreds":s["hundreds"],
            "perf_index":perf_index,
            "mvp_pts": mvp_tot,
            "innings": inn_tot,
            "mvp_per_innings": round(mvp_tot / inn_tot, 2) if inn_tot else 0.0,
            "phase_stats":phase_stats,
            "vs_type":vs_type,
            "by_season":by_season}
        bt_ser = _serialize_bat_by_team(s)
        if bt_ser:
            bat_row["by_team"] = bt_ser
        batting_list.append(bat_row)
    batting_list.sort(key=lambda x: x["runs"], reverse=True)

    bowling_list = []
    for name, s in bowlers.items():
        m = _official_matches(name, s["matches"], xi_matches)
        if m < 1 or s["balls"] < 1:
            continue  # show anyone who bowled
        overs   = round(s["balls"]//6 + (s["balls"]%6)/10, 1)
        economy = round(s["runs"]/s["balls"]*6, 2) if s["balls"] else 0
        avg     = round(s["runs"]/s["wickets"], 2) if s["wickets"] else None
        # Bowling index: wickets per match / economy - rewards wicket taking economy
        bowl_index = round((s["wickets"]/m) * (6/economy), 2) if economy > 0 and m > 0 else 0
        # Build by_season for bowling
        bowl_by_season = {}
        for ssn, ss in s.get("by_season",{}).items():
            sm = _official_matches_season(name, ssn, ss, xi_by_season)
            if sm < 1:
                continue
            sw = ss.get("wickets",0)
            sb = ss.get("balls",0)
            sr = ss.get("runs",0)
            secon = round(sr/sb*6, 2) if sb else 0
            savg = round(sr/sw, 2) if sw else None
            sbi = round((sw/sm)*(6/secon), 2) if secon > 0 and sm > 0 else 0
            inn_b = len(ss.get("innings_ids") or [])
            mvp_b = round(ss.get("mvp_pts", 0), 1)
            bowl_by_season[ssn] = {
                "matches": sm,
                "wickets": sw,
                "runs": sr,
                "balls": sb,
                "economy": secon,
                "avg": savg,
                "bowl_index": sbi,
                "mvp_pts": mvp_b,
                "innings": inn_b,
                "mvp_per_innings": round(mvp_b / inn_b, 2) if inn_b else 0.0,
            }
        # Phase stats for bowler
        raw_bps = s.get("phase_stats",{})
        bowl_phase_stats = {}
        for ph, ps in raw_bps.items():
            econ_ph = round(ps["r"]/ps["b"]*6,2) if ps["b"] else 0
            bowl_phase_stats[ph] = {"runs":ps["r"],"balls":ps["b"],"wickets":ps["w"],"economy":econ_ph}
        # Bowler split vs batter handedness
        vs_hand = {}
        for hand, hs in s.get("vs_hand", {}).items():
            hecon = round(hs["runs"]/hs["balls"]*6, 2) if hs.get("balls") else 0
            vs_hand[hand] = {
                "runs": hs.get("runs", 0),
                "balls": hs.get("balls", 0),
                "wickets": hs.get("wickets", 0),
                "economy": hecon
            }
        inn_b_tot = len(s.get("innings_ids") or [])
        mvp_b_tot = round(s.get("mvp_pts", 0), 1)
        bowl_row = {"name":name,"matches":m,"wickets":s["wickets"],"runs":s["runs"],
            "overs":overs,"economy":economy,"avg":avg,"bowl_index":bowl_index,
            "mvp_pts": mvp_b_tot,
            "innings": inn_b_tot,
            "mvp_per_innings": round(mvp_b_tot / inn_b_tot, 2) if inn_b_tot else 0.0,
            "phase_stats":bowl_phase_stats,
            "vs_hand":vs_hand,
            "by_season":bowl_by_season}
        bteam_ser = _serialize_bowl_by_team(s)
        if bteam_ser:
            bowl_row["by_team"] = bteam_ser
        bowling_list.append(bowl_row)


    bowling_list.sort(key=lambda x: x["wickets"], reverse=True)

    sixes_list = sorted(
        [
            {
                "name": n,
                "sixes": s["sixes"],
                "matches": _official_matches(n, s["matches"], xi_matches),
                "by_season": {
                    ssn: {
                        "sixes": ss["sixes"],
                        "matches": _official_matches_season(n, ssn, ss, xi_by_season),
                    }
                    for ssn, ss in s.get("by_season", {}).items()
                    if ss.get("sixes", 0) > 0
                },
            }
            for n, s in batters.items()
            if s["sixes"] > 0
        ],
        key=lambda x: x["sixes"],
        reverse=True,
    )[:100]

    teams_list = []
    for name, s in teams.items():
        if not name: continue
        m = len(s["matches"])
        if m < 3: continue
        # Build by_season for teams
        by_season = {}
        for ssn, sm in team_season_matches[name].items():
            sw = s["by_season"].get(ssn,{}).get("wins",0)
            by_season[ssn] = {"matches":len(sm),"wins":sw,"win_pct":round(sw/len(sm)*100,1) if sm else 0}
        teams_list.append({"team":name,"matches":m,"wins":s["wins"],"win_pct":round(s["wins"]/m*100,1),"by_season":by_season})
    teams_list.sort(key=lambda x: x["wins"], reverse=True)

    return {
        "competition":   comp["name"],
        "code":          comp["code"],
        "format":        comp["format"],
        "type":          comp["type"],
        "total_matches": total_matches,
        "seasons":       seasons,
        "last_updated":  datetime.datetime.now().strftime("%d %b %Y, %H:%M"),
        "batting":       batting_list,
        "bowling":       bowling_list,
        "sixes":         sixes_list,
        "teams":         teams_list,
    }


def fetch_competition(comp):
    code = comp["code"]
    print(f"\n{'─'*50}\n🏏 {comp['name']} ({code})")
    try:
        zip_bytes = download_zip(comp)
        batters, bowlers, teams, seasons, total, tsm, xi_m, xi_bs = parse_zip(zip_bytes, comp)
        data = build_output(batters, bowlers, teams, seasons, total, comp, tsm, xi_m, xi_bs)
        out_path = os.path.join(STATS_DIR, f"{code}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",",":"))
        print(f"  ✅ {total} matches → {out_path}")
        return {"code":code,"name":comp["name"],"format":comp["format"],"type":comp["type"],
                "total_matches":total,"seasons":seasons}
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        return None


def build_index(results):
    index = {
        "last_updated":  datetime.datetime.now().strftime("%d %b %Y, %H:%M"),
        "competitions":  [r for r in results if r],
    }
    with open(os.path.join(STATS_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"\n📋 index.json — {len(index['competitions'])} competitions")


def main():
    os.makedirs(STATS_DIR, exist_ok=True)
    filter_codes = []
    if "--comp" in sys.argv:
        idx = sys.argv.index("--comp")
        filter_codes = sys.argv[idx+1:]

    if filter_codes:
        comps = [c for c in COMPETITIONS if c["code"] in filter_codes]
    else:
        comps = [c for c in COMPETITIONS if c["code"] in DEFAULT_FETCH_CODES]
    print(f"🚀 Fetching {len(comps)} competition(s) ...")

    results = [fetch_competition(c) for c in comps]
    build_index(results)
    print("\n✅ All done!")


if __name__ == "__main__":
    main()
