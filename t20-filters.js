/**
 * Shared T20 filter helpers: tournament codes, season, year range,
 * aggregating stats JSON by season, and match-list filtering.
 */
(function (g) {
  'use strict';

  var T20_INDEX_CACHE = null;

  function t20FetchIndex() {
    if (T20_INDEX_CACHE) return Promise.resolve(T20_INDEX_CACHE);
    return fetch('stats/index.json')
      .then(function (res) {
        if (!res.ok) throw new Error('stats/index.json HTTP ' + res.status);
        return res.json();
      })
      .then(function (j) {
        T20_INDEX_CACHE = j;
        return j;
      });
  }

  function t20GetCachedIndex() {
    return T20_INDEX_CACHE;
  }

  /** Sync cache when the host page already fetched stats/index.json (avoids a duplicate fetch). */
  function t20PrimeIndexCache(idx) {
    T20_INDEX_CACHE = idx || null;
  }

  function t20GetT20Competitions(index) {
    var idx = index || T20_INDEX_CACHE;
    if (!idx || !idx.competitions) return [];
    return idx.competitions.filter(function (c) {
      return c.format === 'T20';
    });
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

  function t20ResolveCodesFromQS(qs, allCodes) {
    var raw = qs.get('comps');
    if (!raw || !String(raw).trim()) return allCodes.slice();
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
    return picked.length ? picked : allCodes.slice();
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
    return {
      codes: codes,
      activeSeason: season,
      yearFrom: yearFrom,
      yearTo: yearTo,
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
    return q;
  }

  function t20FilterBySeason(data, activeSeason, yearFrom, yearTo) {
    if (!data) return data;
    if (activeSeason === 'all' && !yearFrom && !yearTo) return data;

    function seasonMatches(season) {
      if (!season) return false;
      var yr = parseInt(season, 10);
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
          }
        );
        if (!agg.runs) return null;
        return Object.assign({}, p, {
          matches: agg.matches,
          runs: agg.runs,
          balls: agg.balls,
          fours: agg.fours,
          sixes: agg.sixes,
          fifties: agg.fifties,
          hundreds: agg.hundreds,
          mvp_pts: +agg.mvp_pts.toFixed(1),
          avg: agg.dismissals ? +(agg.runs / agg.dismissals).toFixed(2) : agg.runs,
          sr: agg.balls ? +((agg.runs / agg.balls) * 100).toFixed(2) : 0,
        });
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
            return acc;
          },
          { matches: 0, wickets: 0, runs: 0, balls: 0, mvp_pts: 0 }
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
        return Object.assign({}, p, {
          matches: agg.matches,
          wickets: agg.wickets,
          runs: agg.runs,
          balls: agg.balls,
          overs: +overs.toFixed(1),
          economy: economy,
          avg: avg,
          bowl_index: bowl_index,
          mvp_pts: +agg.mvp_pts.toFixed(1),
        });
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

  g.t20FetchIndex = t20FetchIndex;
  g.t20GetCachedIndex = t20GetCachedIndex;
  g.t20PrimeIndexCache = t20PrimeIndexCache;
  g.t20GetT20Competitions = t20GetT20Competitions;
  g.t20UnionSeasonsForCodes = t20UnionSeasonsForCodes;
  g.t20ReadFilterParams = t20ReadFilterParams;
  g.t20WriteFilterParams = t20WriteFilterParams;
  g.t20FilterQS = t20FilterQS;
  g.t20FilterBySeason = t20FilterBySeason;
  g.t20MatchPassesFilters = t20MatchPassesFilters;
})(typeof window !== 'undefined' ? window : globalThis);
