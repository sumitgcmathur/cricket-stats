/**
 * Shared T20 filter helpers: tournament codes, season, year range,
 * aggregating stats JSON by season, and match-list filtering.
 */
(function (g) {
  'use strict';

  /** Populated from config.json (site.focusCompetitionCodes); order preserved. */
  var FOCUS_MENS_T20_CODES = [];
  var T20_SITE_CONFIG_PROMISE = null;
  var T20_SITE_CONFIG = null;
  /** IPL fallback until config loads */
  var T20_PREFERRED_DEFAULT_LEAGUE = 'ipl';

  function t20EnsureSiteConfig() {
    if (T20_SITE_CONFIG_PROMISE) return T20_SITE_CONFIG_PROMISE;
    var href =
      typeof location !== 'undefined' && location.href ? location.href : 'http://localhost/';
    T20_SITE_CONFIG_PROMISE = fetch(new URL('config.json', href).href)
      .then(function (res) {
        if (!res.ok) throw new Error('config.json HTTP ' + res.status);
        return res.json();
      })
      .then(function (cfg) {
        T20_SITE_CONFIG = cfg;
        var site = cfg.site || {};
        FOCUS_MENS_T20_CODES.length = 0;
        (site.focusCompetitionCodes || []).forEach(function (c) {
          FOCUS_MENS_T20_CODES.push(c);
        });
        if (site.preferredDefaultLeagueCode) {
          T20_PREFERRED_DEFAULT_LEAGUE = String(site.preferredDefaultLeagueCode);
        }
        return cfg;
      });
    return T20_SITE_CONFIG_PROMISE;
  }

  function t20GetFallbackCompetitions() {
    var fb =
      T20_SITE_CONFIG && T20_SITE_CONFIG.site && T20_SITE_CONFIG.site.fallbackCompetitions
        ? T20_SITE_CONFIG.site.fallbackCompetitions
        : [];
    return fb.map(function (c) {
      return {
        code: c.code,
        name: c.name,
        format: c.format || 'T20',
      };
    });
  }

  var T20_INDEX_CACHE = null;
  /** Set from stats/index.json last_updated so stats/*.json URLs change after nightly rebuild (CDN + browser cache). */
  var T20_STATS_CACHE_BUST = null;

  function t20SetStatsCacheBustFromIndex(idx) {
    T20_STATS_CACHE_BUST = idx && idx.last_updated != null ? String(idx.last_updated) : null;
  }

  /**
   * Fetch under stats/ without stale caches: no-store + optional ?v= from index last_updated (set after index load).
   */
  function t20FetchStatsJson(relativePath) {
    var base =
      typeof document !== 'undefined' && document.baseURI
        ? document.baseURI
        : typeof location !== 'undefined' && location.href
          ? location.href
          : 'http://localhost/';
    var u = new URL(relativePath, base).href;
    if (T20_STATS_CACHE_BUST) {
      u += (u.indexOf('?') >= 0 ? '&' : '?') + 'v=' + encodeURIComponent(T20_STATS_CACHE_BUST);
    }
    return fetch(u, { cache: 'no-store' });
  }

  /** Re-read stats/index.json (no query string) to pick up new last_updated after nightly jobs — tab back from background. */
  function t20RefreshStatsCacheBustFromNetwork() {
    var base =
      typeof document !== 'undefined' && document.baseURI
        ? document.baseURI
        : typeof location !== 'undefined' && location.href
          ? location.href
          : 'http://localhost/';
    return fetch(new URL('stats/index.json', base).href, { cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) return null;
        return res.json();
      })
      .then(function (j) {
        if (j && j.last_updated) t20SetStatsCacheBustFromIndex(j);
        return j;
      });
  }

  var _t20VisBustTimer = null;
  function t20BindStatsBustOnTabVisible() {
    if (typeof document === 'undefined' || g._t20VisibilityBustBound) return;
    g._t20VisibilityBustBound = true;
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState !== 'visible') return;
      clearTimeout(_t20VisBustTimer);
      _t20VisBustTimer = setTimeout(function () {
        t20RefreshStatsCacheBustFromNetwork();
      }, 400);
    });
  }
  t20BindStatsBustOnTabVisible();

  /** Escape text for safe insertion into HTML (stats names, team labels, etc.). */
  function t20EscapeHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function t20FetchIndex() {
    if (T20_INDEX_CACHE) return Promise.resolve(T20_INDEX_CACHE);
    return t20FetchStatsJson('stats/index.json')
      .then(function (res) {
        if (!res.ok) throw new Error('stats/index.json HTTP ' + res.status);
        return res.json();
      })
      .then(function (j) {
        T20_INDEX_CACHE = j;
        t20SetStatsCacheBustFromIndex(j);
        return j;
      });
  }

  function t20GetCachedIndex() {
    return T20_INDEX_CACHE;
  }

  /** Sync cache when the host page already fetched stats/index.json (avoids a duplicate fetch). */
  function t20PrimeIndexCache(idx) {
    T20_INDEX_CACHE = idx || null;
    t20SetStatsCacheBustFromIndex(idx);
  }

  /**
   * Build chip list for site.focusCompetitionCodes order.
   * Prefer stats/index.json rows when present; otherwise use config.json cricsheet/site fallback
   * so new leagues (e.g. sa20) appear before the next fetch run.
   */
  function t20SyntheticCompetition(code) {
    var cfg = T20_SITE_CONFIG;
    if (!cfg || !code) return null;
    var cr = (cfg.cricsheet && cfg.cricsheet.competitions) || [];
    var i;
    for (i = 0; i < cr.length; i++) {
      if (cr[i].code === code && String(cr[i].format || 'T20') === 'T20') {
        return {
          code: cr[i].code,
          name: cr[i].name,
          format: cr[i].format || 'T20',
          type: cr[i].type || 'league',
          total_matches: 0,
          seasons: [],
        };
      }
    }
    var fb = (cfg.site && cfg.site.fallbackCompetitions) || [];
    for (i = 0; i < fb.length; i++) {
      if (fb[i].code === code) {
        return {
          code: fb[i].code,
          name: fb[i].name,
          format: fb[i].format || 'T20',
          type: 'league',
          total_matches: 0,
          seasons: [],
        };
      }
    }
    return null;
  }

  function t20GetT20Competitions(index) {
    var idx = index || T20_INDEX_CACHE;
    var byCode = {};
    if (idx && idx.competitions) {
      idx.competitions.forEach(function (c) {
        if (c.format === 'T20') byCode[c.code] = c;
      });
    }
    var out = [];
    FOCUS_MENS_T20_CODES.forEach(function (code) {
      if (byCode[code]) {
        out.push(byCode[code]);
        return;
      }
      var syn = t20SyntheticCompetition(code);
      if (syn) out.push(syn);
    });
    return out;
  }

  function t20UnionSeasonsForCodes(index, codes) {
    var s = new Set();
    if (!index || !index.competitions) return [];
    (codes || []).forEach(function (code) {
      var c = index.competitions.find(function (x) {
        return x.code === code;
      });
      if (c && c.seasons) c.seasons.forEach(function (x) {
        s.add(x);
      });
    });
    return Array.from(s).sort(function (a, b) {
      return b.localeCompare(a);
    });
  }

  /** Default tournament reset uses site.preferredDefaultLeagueCode from config.json when loaded. */
  function t20DefaultFilterCodes(allCodes) {
    if (!allCodes || !allCodes.length) return [];
    var pref = T20_PREFERRED_DEFAULT_LEAGUE || 'ipl';
    var i = allCodes.indexOf(pref);
    return i >= 0 ? [pref] : [allCodes[0]];
  }

  function t20ResolveCodesFromQS(qs, allCodes) {
    var raw = qs.get('comps');
    if (!raw || !String(raw).trim()) return t20DefaultFilterCodes(allCodes);
    var parts = String(raw).split(',').map(function (x) {
      return x.trim();
    }).filter(Boolean);
    var valid = {};
    allCodes.forEach(function (c) {
      valid[c] = true;
    });
    var picked = parts.filter(function (c) {
      return valid[c];
    });
    return picked.length ? picked : t20DefaultFilterCodes(allCodes);
  }

  function t20ReadFilterParams(searchString, index) {
    var qs = new URLSearchParams(
      searchString || (typeof location !== 'undefined' ? location.search : '')
    );
    var allCodes = t20GetT20Competitions(index).map(function (c) {
      return c.code;
    });
    var codes = t20ResolveCodesFromQS(qs, allCodes);
    var season = qs.get('season') || 'all';
    var yf = parseInt(qs.get('yearFrom'), 10);
    var yt = parseInt(qs.get('yearTo'), 10);
    var yearFrom = Number.isFinite(yf) ? yf : null;
    var yearTo = Number.isFinite(yt) ? yt : null;
    if (season !== 'all') {
      yearFrom = null;
      yearTo = null;
    } else if (yearFrom || yearTo) {
      season = 'all';
    }
    /* forTeam = batting/bowling slice on index (distinct from team.html ?team=) */
    var teamRaw = (qs.get('forTeam') || '').trim();
    return {
      codes: codes,
      activeSeason: season,
      yearFrom: yearFrom,
      yearTo: yearTo,
      team: teamRaw || null,
    };
  }

  function t20WriteFilterParams(state, extraPreserve) {
    if (typeof location === 'undefined') return;
    var u = new URL(location.href);
    var index = T20_INDEX_CACHE;
    var allCodes = t20GetT20Competitions(index).map(function (c) {
      return c.code;
    });
    var full =
      allCodes.length > 0 &&
      state.codes.length === allCodes.length &&
      allCodes.every(function (c) {
        return state.codes.indexOf(c) >= 0;
      });
    if (full) u.searchParams.delete('comps');
    else if (state.codes && state.codes.length) u.searchParams.set('comps', state.codes.join(','));
    else u.searchParams.delete('comps');
    if (state.activeSeason && state.activeSeason !== 'all') {
      u.searchParams.set('season', state.activeSeason);
      u.searchParams.delete('yearFrom');
      u.searchParams.delete('yearTo');
    } else {
      u.searchParams.set('season', 'all');
      if (state.yearFrom) u.searchParams.set('yearFrom', String(state.yearFrom));
      else u.searchParams.delete('yearFrom');
      if (state.yearTo) u.searchParams.set('yearTo', String(state.yearTo));
      else u.searchParams.delete('yearTo');
    }
    if (state.team && String(state.team).trim()) u.searchParams.set('forTeam', String(state.team).trim());
    else u.searchParams.delete('forTeam');
    if (extraPreserve && typeof extraPreserve === 'object') {
      Object.keys(extraPreserve).forEach(function (k) {
        var v = extraPreserve[k];
        if (v == null || v === '') u.searchParams.delete(k);
        else u.searchParams.set(k, String(v));
      });
    }
    history.replaceState({}, '', u.toString());
  }

  function t20FilterQS(state, index) {
    var idx = index || T20_INDEX_CACHE;
    var q = new URLSearchParams();
    var allCodes = t20GetT20Competitions(idx).map(function (c) {
      return c.code;
    });
    var full =
      allCodes.length > 0 &&
      state.codes.length === allCodes.length &&
      allCodes.every(function (c) {
        return state.codes.indexOf(c) >= 0;
      });
    if (!full && state.codes && state.codes.length) q.set('comps', state.codes.join(','));
    if (state.activeSeason && state.activeSeason !== 'all') {
      q.set('season', state.activeSeason);
    } else {
      q.set('season', 'all');
      if (state.yearFrom) q.set('yearFrom', String(state.yearFrom));
      if (state.yearTo) q.set('yearTo', String(state.yearTo));
    }
    if (state.team && String(state.team).trim()) q.set('forTeam', String(state.team).trim());
    return q;
  }

  function t20FilterByTeamMap(teamMap, seasonMatchesFn) {
    if (!teamMap || typeof teamMap !== 'object') return null;
    var out = {};
    Object.keys(teamMap).forEach(function (team) {
      var tnode = teamMap[team];
      var src = (tnode && tnode.by_season) || {};
      var sub = {};
      Object.keys(src).forEach(function (ssn) {
        if (seasonMatchesFn(ssn)) sub[ssn] = src[ssn];
      });
      if (Object.keys(sub).length) out[team] = { by_season: sub };
    });
    return Object.keys(out).length ? out : null;
  }

  function t20SumBatTeamBranch(teamNode) {
    if (!teamNode || !teamNode.by_season) return null;
    var agg = {
      matches: 0,
      runs: 0,
      balls: 0,
      fours: 0,
      sixes: 0,
      fifties: 0,
      hundreds: 0,
      mvp_pts: 0,
      dismissals: 0,
      innings: 0,
    };
    Object.values(teamNode.by_season).forEach(function (s) {
      agg.matches += s.matches || 0;
      agg.runs += s.runs || 0;
      agg.balls += s.balls || 0;
      agg.fours += s.fours || 0;
      agg.sixes += s.sixes || 0;
      agg.fifties += s.fifties || 0;
      agg.hundreds += s.hundreds || 0;
      agg.mvp_pts += s.mvp_pts || 0;
      agg.dismissals += s.dismissals || 0;
      agg.innings += s.innings || 0;
    });
    if (!agg.balls && !agg.runs) return null;
    agg.mvp_pts = +agg.mvp_pts.toFixed(1);
    var avg = agg.dismissals ? +(agg.runs / agg.dismissals).toFixed(2) : agg.runs;
    var sr = agg.balls ? +((agg.runs / agg.balls) * 100).toFixed(2) : 0;
    var perf_index = sr > 0 ? +((avg * (sr / 100)).toFixed(1)) : 0;
    var innAgg = agg.innings || 0;
    return {
      matches: agg.matches,
      runs: agg.runs,
      balls: agg.balls,
      fours: agg.fours,
      sixes: agg.sixes,
      fifties: agg.fifties,
      hundreds: agg.hundreds,
      mvp_pts: agg.mvp_pts,
      innings: innAgg,
      mvp_per_innings: innAgg ? +(agg.mvp_pts / innAgg).toFixed(2) : 0,
      avg: avg,
      sr: sr,
      perf_index: perf_index,
    };
  }

  function t20SumBowlTeamBranch(teamNode) {
    if (!teamNode || !teamNode.by_season) return null;
    var agg = { matches: 0, wickets: 0, runs: 0, balls: 0, mvp_pts: 0, innings: 0 };
    Object.values(teamNode.by_season).forEach(function (s) {
      agg.matches += s.matches || 0;
      agg.wickets += s.wickets || 0;
      agg.runs += s.runs || 0;
      agg.balls += s.balls || 0;
      agg.mvp_pts += s.mvp_pts || 0;
      agg.innings += s.innings || 0;
    });
    if (!agg.balls) return null;
    agg.mvp_pts = +agg.mvp_pts.toFixed(1);
    var economy = agg.balls ? +((agg.runs / agg.balls) * 6).toFixed(2) : 0;
    var avg = agg.wickets ? +(agg.runs / agg.wickets).toFixed(2) : null;
    var overs = Math.floor(agg.balls / 6) + (agg.balls % 6) / 10;
    var bowl_index =
      economy > 0 && agg.matches > 0 ? +((agg.wickets / agg.matches) * (6 / economy)).toFixed(2) : 0;
    var innB = agg.innings || 0;
    return {
      matches: agg.matches,
      wickets: agg.wickets,
      runs: agg.runs,
      balls: agg.balls,
      overs: +overs.toFixed(1),
      economy: economy,
      avg: avg,
      bowl_index: bowl_index,
      mvp_pts: agg.mvp_pts,
      innings: innB,
      mvp_per_innings: innB ? +(agg.mvp_pts / innB).toFixed(2) : 0,
    };
  }

  /** Slice merged batting/bowling to one franchise (ball rows while batting / bowling for that side). */
  function t20ApplyTeamFilter(data, teamName) {
    if (!data || !teamName || teamName === 'all') return data;
    var nm = String(teamName).trim();
    if (!nm) return data;
    var bat = (data.batting || [])
      .map(function (p) {
        var t = p.by_team && p.by_team[nm];
        var agg = t20SumBatTeamBranch(t);
        if (!agg) return null;
        var o = Object.assign({}, p, agg);
        delete o.by_team;
        return o;
      })
      .filter(Boolean)
      .sort(function (a, b) {
        return b.runs - a.runs;
      });
    var bowl = (data.bowling || [])
      .map(function (p) {
        var t = p.by_team && p.by_team[nm];
        var agg = t20SumBowlTeamBranch(t);
        if (!agg) return null;
        var o = Object.assign({}, p, agg);
        delete o.by_team;
        return o;
      })
      .filter(Boolean)
      .sort(function (a, b) {
        return b.wickets - a.wickets;
      });
    return Object.assign({}, data, { batting: bat, bowling: bowl });
  }

  function t20FilterBySeason(data, activeSeason, yearFrom, yearTo) {
    if (!data) return data;
    if (activeSeason === 'all' && !yearFrom && !yearTo) return data;

    function seasonMatches(season) {
      if (!season) return false;
      var yr = parseInt(season, 10);
      if (!Number.isFinite(yr)) return false;
      if (activeSeason !== 'all') return season === activeSeason;
      if (yearFrom && yr < yearFrom) return false;
      if (yearTo && yr > yearTo) return false;
      return true;
    }

    var filteredBatting = (data.batting || [])
      .map(function (p) {
        if (!p.by_season) return null;
        var matchingSeasons = Object.entries(p.by_season).filter(function (ent) {
          return seasonMatches(ent[0]);
        });
        if (!matchingSeasons.length) return null;
        var agg = matchingSeasons.reduce(
          function (acc, tuple) {
            var s = tuple[1];
            acc.matches += s.matches || 0;
            acc.runs += s.runs || 0;
            acc.balls += s.balls || 0;
            acc.fours += s.fours || 0;
            acc.sixes += s.sixes || 0;
            acc.fifties += s.fifties || 0;
            acc.hundreds += s.hundreds || 0;
            acc.mvp_pts += s.mvp_pts || 0;
            acc.dismissals += s.dismissals || 0;
            acc.innings += s.innings || 0;
            return acc;
          },
          {
            matches: 0,
            runs: 0,
            balls: 0,
            fours: 0,
            sixes: 0,
            fifties: 0,
            hundreds: 0,
            mvp_pts: 0,
            dismissals: 0,
            innings: 0,
          }
        );
        /* Keep row if any batting activity in window (e.g. 0 runs but balls faced). */
        if (!agg.matches && !agg.balls && !agg.runs) return null;
        var mvpBat = +agg.mvp_pts.toFixed(1);
        var innBat = agg.innings || 0;
        var row = Object.assign({}, p, {
          matches: agg.matches,
          runs: agg.runs,
          balls: agg.balls,
          fours: agg.fours,
          sixes: agg.sixes,
          fifties: agg.fifties,
          hundreds: agg.hundreds,
          mvp_pts: mvpBat,
          innings: innBat,
          mvp_per_innings: innBat ? +(mvpBat / innBat).toFixed(2) : 0,
          avg: agg.dismissals ? +(agg.runs / agg.dismissals).toFixed(2) : agg.runs,
          sr: agg.balls ? +((agg.runs / agg.balls) * 100).toFixed(2) : 0,
        });
        var byTeamF = p.by_team ? t20FilterByTeamMap(p.by_team, seasonMatches) : null;
        if (byTeamF) row.by_team = byTeamF;
        else delete row.by_team;
        row.perf_index =
          row.sr > 0 ? +((row.avg * (row.sr / 100)).toFixed(1)) : +(row.perf_index || 0) || 0;
        return row;
      })
      .filter(Boolean)
      .sort(function (a, b) {
        return b.runs - a.runs;
      });

    var filteredSixes = (data.sixes || [])
      .map(function (p) {
        if (!p.by_season) return null;
        var matching = Object.entries(p.by_season).filter(function (ent) {
          return seasonMatches(ent[0]);
        });
        if (!matching.length) return null;
        var totalSixes = matching.reduce(function (sum, tuple) {
          var v = tuple[1];
          return sum + (v && v.sixes != null ? v.sixes : v || 0);
        }, 0);
        var totalMatches = matching.reduce(function (sum, tuple) {
          var v = tuple[1];
          return sum + ((v && v.matches) || 0);
        }, 0);
        if (!totalSixes) return null;
        return Object.assign({}, p, {
          sixes: totalSixes,
          matches: totalMatches || p.matches,
        });
      })
      .filter(Boolean)
      .sort(function (a, b) {
        return b.sixes - a.sixes;
      });

    var filteredTeams = (data.teams || [])
      .map(function (t) {
        if (!t.by_season) return t;
        var matchingSeasons = Object.entries(t.by_season).filter(function (ent) {
          return seasonMatches(ent[0]);
        });
        if (!matchingSeasons.length) return null;
        var totalMatches = matchingSeasons.reduce(function (sum, tuple) {
          return sum + (tuple[1].matches || 0);
        }, 0);
        var totalWins = matchingSeasons.reduce(function (sum, tuple) {
          return sum + (tuple[1].wins || 0);
        }, 0);
        return Object.assign({}, t, {
          matches: totalMatches,
          wins: totalWins,
          win_pct: totalMatches ? +((totalWins / totalMatches) * 100).toFixed(1) : 0,
        });
      })
      .filter(Boolean)
      .sort(function (a, b) {
        return b.wins - a.wins;
      });

    var filteredBowling = (data.bowling || [])
      .map(function (p) {
        if (!p.by_season || !Object.keys(p.by_season).length) return null;
        var matchingSeasons = Object.entries(p.by_season).filter(function (ent) {
          return seasonMatches(ent[0]);
        });
        if (!matchingSeasons.length) return null;
        var agg = matchingSeasons.reduce(
          function (acc, tuple) {
            var s = tuple[1];
            var sm = typeof s.matches === 'number' ? s.matches : 0;
            acc.matches += sm;
            acc.wickets += s.wickets || 0;
            acc.runs += s.runs || 0;
            acc.balls += s.balls || 0;
            acc.mvp_pts += s.mvp_pts || 0;
            acc.innings += s.innings || 0;
            return acc;
          },
          { matches: 0, wickets: 0, runs: 0, balls: 0, mvp_pts: 0, innings: 0 }
        );
        if (!agg.balls) return null;
        if (!agg.matches) agg.matches = Math.ceil(agg.balls / 24);
        var economy = +((agg.runs / agg.balls) * 6).toFixed(2);
        var avg = agg.wickets ? +(agg.runs / agg.wickets).toFixed(2) : null;
        var overs = Math.floor(agg.balls / 6) + (agg.balls % 6) / 10;
        var bowl_index =
          economy > 0 && agg.matches > 0
            ? +((agg.wickets / agg.matches) * (6 / economy)).toFixed(2)
            : 0;
        var mvpBwl = +agg.mvp_pts.toFixed(1);
        var innBwl = agg.innings || 0;
        var row = Object.assign({}, p, {
          matches: agg.matches,
          wickets: agg.wickets,
          runs: agg.runs,
          balls: agg.balls,
          overs: +overs.toFixed(1),
          economy: economy,
          avg: avg,
          bowl_index: bowl_index,
          mvp_pts: mvpBwl,
          innings: innBwl,
          mvp_per_innings: innBwl ? +(mvpBwl / innBwl).toFixed(2) : 0,
        });
        var byTeamF = p.by_team ? t20FilterByTeamMap(p.by_team, seasonMatches) : null;
        if (byTeamF) row.by_team = byTeamF;
        else delete row.by_team;
        return row;
      })
      .filter(Boolean)
      .sort(function (a, b) {
        return b.wickets - a.wickets;
      });

    return Object.assign({}, data, {
      batting: filteredBatting,
      bowling: filteredBowling,
      sixes: filteredSixes,
      teams: filteredTeams,
    });
  }

  /** Sum per-franchise rows from merged `by_team` (all seasons) for charts. */
  function t20RollupBatByTeamFranchises(byTeam) {
    if (!byTeam || typeof byTeam !== 'object') return [];
    var out = [];
    Object.keys(byTeam).forEach(function (team) {
      var tb = byTeam[team];
      var subs = (tb && tb.by_season) || {};
      var runs = 0,
        balls = 0,
        dismissals = 0,
        matches = 0;
      Object.keys(subs).forEach(function (ssn) {
        var ss = subs[ssn];
        runs += +ss.runs || 0;
        balls += +ss.balls || 0;
        dismissals += +ss.dismissals || 0;
        matches += +ss.matches || 0;
      });
      if (runs < 1 && balls < 1) return;
      out.push({
        team: team,
        runs: runs,
        balls: balls,
        dismissals: dismissals,
        matches: matches,
        avg: dismissals ? +((runs / dismissals).toFixed(2)) : runs,
        sr: balls ? +(((runs / balls) * 100).toFixed(1)) : 0,
      });
    });
    out.sort(function (a, b) {
      return b.runs - a.runs;
    });
    return out;
  }

  function t20RollupBowlByTeamFranchises(byTeam) {
    if (!byTeam || typeof byTeam !== 'object') return [];
    var out = [];
    Object.keys(byTeam).forEach(function (team) {
      var tb = byTeam[team];
      var subs = (tb && tb.by_season) || {};
      var wickets = 0,
        runs = 0,
        balls = 0,
        matches = 0;
      Object.keys(subs).forEach(function (ssn) {
        var ss = subs[ssn];
        wickets += +ss.wickets || 0;
        runs += +ss.runs || 0;
        balls += +ss.balls || 0;
        matches += +ss.matches || 0;
      });
      if (!balls) return;
      out.push({
        team: team,
        wickets: wickets,
        runs: runs,
        balls: balls,
        matches: matches,
        economy: balls ? +(((runs / balls) * 6).toFixed(2)) : 0,
      });
    });
    out.sort(function (a, b) {
      return b.wickets - a.wickets;
    });
    return out;
  }

  function t20MatchPassesFilters(m, activeSeason, yearFrom, yearTo) {
    if (!m) return false;
    if (activeSeason !== 'all') {
      return String(m.season || '') === String(activeSeason);
    }
    if (yearFrom || yearTo) {
      var yr = null;
      if (m.date) {
        var d = new Date(m.date);
        if (!isNaN(d.getTime())) yr = d.getFullYear();
      }
      if (yr == null && m.season != null) {
        var n = parseInt(String(m.season).slice(0, 4), 10);
        if (Number.isFinite(n)) yr = n;
      }
      if (yr == null) return true;
      if (yearFrom && yr < yearFrom) return false;
      if (yearTo && yr > yearTo) return false;
    }
    return true;
  }

  g.t20EnsureSiteConfig = t20EnsureSiteConfig;
  g.t20GetFallbackCompetitions = t20GetFallbackCompetitions;
  g.t20FetchIndex = t20FetchIndex;
  g.t20GetCachedIndex = t20GetCachedIndex;
  g.t20PrimeIndexCache = t20PrimeIndexCache;
  g.t20FetchStatsJson = t20FetchStatsJson;
  g.t20RefreshStatsCacheBustFromNetwork = t20RefreshStatsCacheBustFromNetwork;
  g.t20GetT20Competitions = t20GetT20Competitions;
  g.t20UnionSeasonsForCodes = t20UnionSeasonsForCodes;
  g.t20ReadFilterParams = t20ReadFilterParams;
  g.t20WriteFilterParams = t20WriteFilterParams;
  g.t20FilterQS = t20FilterQS;
  g.t20FilterBySeason = t20FilterBySeason;
  g.t20ApplyTeamFilter = t20ApplyTeamFilter;
  g.t20MatchPassesFilters = t20MatchPassesFilters;
  g.t20DefaultFilterCodes = t20DefaultFilterCodes;
  g.t20EscapeHtml = t20EscapeHtml;
  g.t20RollupBatByTeamFranchises = t20RollupBatByTeamFranchises;
  g.t20RollupBowlByTeamFranchises = t20RollupBowlByTeamFranchises;
  g.FOCUS_MENS_T20_CODES = FOCUS_MENS_T20_CODES;
})(typeof window !== 'undefined' ? window : globalThis);
