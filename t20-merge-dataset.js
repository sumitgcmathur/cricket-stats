/**
 * Merge per-competition stats JSON into one dashboard dataset (batting, bowling, sixes, teams).
 * Used by index.html and compare.html. Depends on t20-filters.js only for types, not calls.
 */
(function (g) {
  'use strict';

  function estDismissalsBat(p) {
    var r = +p.runs || 0;
    var a = p.avg;
    if (!r) return 0;
    if (a == null || a === '—' || a === '') return 0;
    var av = +a;
    if (!Number.isFinite(av) || av <= 0) return 0;
    if (Math.abs(av - r) < 0.01) return 0;
    return Math.max(1, Math.round(r / av));
  }

  function mergeBattingLists(lists) {
    var m = {};
    lists.forEach(function (list) {
      (list || []).forEach(function (p) {
        if (!m[p.name]) {
          m[p.name] = {
            name: p.name,
            _d: 0,
            _piw: 0,
            matches: 0,
            runs: 0,
            balls: 0,
            fours: 0,
            sixes: 0,
            fifties: 0,
            hundreds: 0,
            mvp_pts: 0,
          };
        }
        var x = m[p.name];
        x.matches += +p.matches || 0;
        x.runs += +p.runs || 0;
        x.balls += +p.balls || 0;
        x.fours += +p.fours || 0;
        x.sixes += +p.sixes || 0;
        x.fifties += +p.fifties || 0;
        x.hundreds += +p.hundreds || 0;
        x.mvp_pts = +((parseFloat(x.mvp_pts) || 0) + (parseFloat(p.mvp_pts) || 0)).toFixed(1);
        x._d += estDismissalsBat(p);
        var pi = parseFloat(p.perf_index);
        if (Number.isFinite(pi)) x._piw += pi * (+p.runs || 0);
      });
    });
    return Object.keys(m)
      .map(function (k) {
        var p = m[k];
        var sr = p.balls ? +((p.runs / p.balls) * 100).toFixed(2) : 0;
        var avg = p._d ? +((p.runs / p._d).toFixed(2)) : p.runs;
        var perf_index = p.runs > 0 && p._piw ? +((p._piw / p.runs).toFixed(1)) : 0;
        delete p._d;
        delete p._piw;
        return Object.assign({}, p, { avg: avg, sr: sr, perf_index: perf_index });
      })
      .filter(function (p) {
        return p.runs > 0;
      })
      .sort(function (a, b) {
        return b.runs - a.runs;
      });
  }

  function oversNotationToBalls(overs) {
    if (overs == null || overs === '') return 0;
    var o = +overs;
    if (!Number.isFinite(o) || o < 0) return 0;
    var whole = Math.floor(o + 1e-9);
    var frac = +(o - whole).toFixed(3);
    var partial = Math.min(5, Math.max(0, Math.round(frac * 10 + 1e-9)));
    return whole * 6 + partial;
  }

  function bowlingBallsFromRow(p) {
    var b = +p.balls;
    if (Number.isFinite(b) && b > 0) return b;
    var fromOvers = oversNotationToBalls(p.overs);
    if (fromOvers > 0) return fromOvers;
    if (p.by_season && typeof p.by_season === 'object') {
      var s = 0;
      Object.values(p.by_season).forEach(function (v) {
        var bb = v && +v.balls;
        if (Number.isFinite(bb)) s += bb;
      });
      return s;
    }
    return 0;
  }

  function mergeBowlingLists(lists) {
    var m = {};
    lists.forEach(function (list) {
      (list || []).forEach(function (p) {
        if (!m[p.name]) {
          m[p.name] = { name: p.name, matches: 0, wickets: 0, runs: 0, balls: 0, mvp_pts: 0 };
        }
        var x = m[p.name];
        x.matches += +p.matches || 0;
        x.wickets += +p.wickets || 0;
        x.runs += +p.runs || 0;
        x.balls += bowlingBallsFromRow(p);
        x.mvp_pts = +((parseFloat(x.mvp_pts) || 0) + (parseFloat(p.mvp_pts) || 0)).toFixed(1);
      });
    });
    return Object.keys(m)
      .map(function (k) {
        var p = m[k];
        var economy = p.balls ? +((p.runs / p.balls) * 6).toFixed(2) : 0;
        var avg = p.wickets ? +((p.runs / p.wickets).toFixed(2)) : null;
        var overs = Math.floor(p.balls / 6) + (p.balls % 6) / 10;
        var bowl_index =
          economy > 0 && p.matches > 0 ? +((p.wickets / p.matches) * (6 / economy)).toFixed(2) : 0;
        return Object.assign({}, p, {
          overs: +overs.toFixed(1),
          economy: economy,
          avg: avg,
          bowl_index: bowl_index,
        });
      })
      .filter(function (p) {
        return p.balls > 0;
      })
      .sort(function (a, b) {
        return b.wickets - a.wickets;
      });
  }

  function mergeSixesLists(lists) {
    var m = {};
    lists.forEach(function (list) {
      (list || []).forEach(function (p) {
        if (!m[p.name]) m[p.name] = { name: p.name, sixes: 0, matches: 0 };
        m[p.name].sixes += +p.sixes || 0;
        m[p.name].matches += +p.matches || 0;
      });
    });
    return Object.values(m)
      .filter(function (p) {
        return p.sixes > 0;
      })
      .sort(function (a, b) {
        return b.sixes - a.sixes;
      });
  }

  function mergeTeamsLists(lists) {
    var m = {};
    lists.forEach(function (list) {
      (list || []).forEach(function (t) {
        var k = t.team;
        if (!m[k]) m[k] = { team: k, matches: 0, wins: 0 };
        m[k].matches += +t.matches || 0;
        m[k].wins += +t.wins || 0;
      });
    });
    return Object.values(m)
      .map(function (t) {
        return Object.assign({}, t, {
          win_pct: t.matches ? +((t.wins / t.matches) * 100).toFixed(1) : 0,
        });
      })
      .sort(function (a, b) {
        return b.wins - a.wins;
      });
  }

  function t20MergeDatasets(list) {
    if (!list || !list.length) return null;
    return {
      competition: 'Combined T20',
      code: 'merged',
      format: 'T20',
      type: 'merged',
      total_matches: list.reduce(function (s, d) {
        return s + (+d.total_matches || 0);
      }, 0),
      seasons: Array.from(
        new Set(
          list.flatMap(function (d) {
            return d.seasons || [];
          })
        )
      ).sort(function (a, b) {
        return b.localeCompare(a);
      }),
      batting: mergeBattingLists(
        list.map(function (d) {
          return d.batting;
        })
      ),
      bowling: mergeBowlingLists(
        list.map(function (d) {
          return d.bowling;
        })
      ),
      sixes: mergeSixesLists(
        list.map(function (d) {
          return d.sixes;
        })
      ),
      teams: mergeTeamsLists(
        list.map(function (d) {
          return d.teams;
        })
      ),
    };
  }

  g.t20MergeDatasets = t20MergeDatasets;
})(typeof window !== 'undefined' ? window : globalThis);
