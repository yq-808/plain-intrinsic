/*
 * daily-val — client-side relative-valuation (peer multiples) engine.
 *
 * A sibling to docs/assets/dcf.js, for cyclical / commodity businesses where a
 * forward-earnings × peer-multiple story is the honest model and a smooth FCFF
 * DCF is not. It anchors a forward metric (EPS, EBITDA, revenue, book value),
 * applies a peer/re-rating multiple (P/E, EV/EBITDA, P/B, EV/Sales), bridges
 * EV→equity via net cash where needed, and averages across multiples.
 *
 * The static pages ship the *inputs* only; this script turns them into the
 * final valuation. Valuation only — no live market price.
 *
 * The report reads as a simple three-step walkthrough:
 *   1. what the peers trade at,
 *   2. our forward figure × chosen multiple for this stock,
 *   3. each multiple's implied price, averaged into the fair value.
 */
(function (global) {
  "use strict";

  // ----------------------------------------------------------------- parsing
  function parseValue(value) {
    if (value === null || value === undefined) return null;
    if (typeof value === "number") return value;
    if (typeof value === "string") {
      var v = value.trim().toUpperCase().replace(/,/g, "");
      var mult = { K: 1e3, M: 1e6, B: 1e9, T: 1e12 };
      var suffix = v.slice(-1);
      if (mult[suffix] !== undefined) return parseFloat(v.slice(0, -1)) * mult[suffix];
      return parseFloat(v);
    }
    return null;
  }

  // -------------------------------------------------------------- formatting
  function money(x, decimals) {
    if (x === null || x === undefined || isNaN(x)) return "N/A";
    if (decimals === undefined) decimals = 2;
    var ax = Math.abs(x);
    var units = [["T", 1e12], ["B", 1e9], ["M", 1e6], ["K", 1e3]];
    for (var i = 0; i < units.length; i++) {
      if (ax >= units[i][1]) return "$" + (x / units[i][1]).toFixed(decimals) + units[i][0];
    }
    return "$" + x.toFixed(0);
  }

  function price(x) {
    if (x === null || x === undefined || isNaN(x)) return "—";
    return "$" + Math.round(x).toLocaleString("en-US");
  }

  function multx(x) {
    if (x === null || x === undefined || isNaN(x)) return "—";
    return (x % 1 === 0 ? x.toFixed(0) : x.toFixed(1)) + "×";
  }

  function shareCount(x) {
    return (x === null || isNaN(x)) ? "—" : (x / 1e9).toFixed(2) + "B";
  }

  // ----------------------------------------------------------- multiples map
  // Each multiple maps a forward figure + a chosen multiple to an implied share
  // price. Two kinds: "equity" applies to a per-share figure (price directly);
  // "ev" applies to a firm-level figure → enterprise value, bridged to equity
  // via net cash, then divided by shares.
  var MULTIPLES = {
    pe:        { label: "P/E",       kind: "equity", metric: "eps",     metricLabel: "EPS",                fmt: function (v) { return price(v); } },
    ev_ebitda: { label: "EV/EBITDA", kind: "ev",     metric: "ebitda",  metricLabel: "EBITDA",             fmt: function (v) { return money(v, 0); } },
    pb:        { label: "P/B",       kind: "equity", metric: "bvps",    metricLabel: "Book value / share", fmt: function (v) { return price(v); } },
    ev_sales:  { label: "EV/Sales",  kind: "ev",     metric: "revenue", metricLabel: "Revenue",            fmt: function (v) { return money(v, 0); } },
  };

  function metricValue(key, fundamentals) {
    var def = MULTIPLES[key];
    return def ? parseValue((fundamentals || {})[def.metric]) : null;
  }

  function impliedPrice(key, scenario, ctx) {
    var def = MULTIPLES[key];
    if (!def) return null;
    var m = scenario.multiples ? scenario.multiples[key] : null;
    if (m === null || m === undefined) return null;
    var base = metricValue(key, scenario.fundamentals);
    if (base === null || isNaN(base)) return null;
    if (def.kind === "equity") return base * m;
    var equity = base * m + ctx.netCash; // EV + net cash
    return ctx.shares ? equity / ctx.shares : null;
  }

  // Plain-English calculation for one multiple, e.g. "$115 × 10" or
  // "$150B × 8, + $25B net cash, ÷ 1.13B shares".
  function calcString(key, scenario, ctx) {
    var def = MULTIPLES[key];
    var m = scenario.multiples[key];
    var base = metricValue(key, scenario.fundamentals);
    if (def.kind === "equity") return def.fmt(base) + " × " + multx(m);
    return money(base, 0) + " × " + multx(m) + ", + " + money(ctx.netCash, 0) +
      " net cash, ÷ " + shareCount(ctx.shares) + " shares";
  }

  function mean(xs) {
    var v = xs.filter(function (x) { return x !== null && !isNaN(x); });
    return v.length ? v.reduce(function (s, x) { return s + x; }, 0) / v.length : null;
  }

  // --------------------------------------------------------------- scenarios
  function normalizeScenarios(raw) {
    if (!Array.isArray(raw) || raw.length === 0) throw new Error("'scenarios' must be a non-empty list");
    var scenarios = raw.map(function (s, idx) {
      if (typeof s !== "object" || s === null) throw new Error("scenarios[" + idx + "] must be an object");
      if (!("probability" in s)) throw new Error("scenarios[" + idx + "] is missing 'probability'");
      var p = Number(s.probability);
      if (isNaN(p) || p < 0) throw new Error("scenarios[" + idx + "].probability must be a non-negative number");
      var copy = JSON.parse(JSON.stringify(s));
      copy.probability = p;
      return copy;
    });
    var total = scenarios.reduce(function (s, x) { return s + x.probability; }, 0);
    if (total <= 0) throw new Error("Scenario probability sum must be > 0");
    if (total > 1.0001) {
      if (Math.abs(total - 100.0) <= 0.1) {
        scenarios.forEach(function (s) { s.probability /= 100.0; });
        total = scenarios.reduce(function (s, x) { return s + x.probability; }, 0);
      } else {
        throw new Error("Scenario probabilities must sum to 1.0 (or 100)");
      }
    }
    if (Math.abs(total - 1.0) > 0.001) throw new Error("Scenario probabilities must sum to 1.0; got " + total.toFixed(4));
    return scenarios;
  }

  // Merge top-level defaults (fundamentals / multiples / balance_sheet) with a
  // scenario's overrides.
  function mergeScenario(baseData, scenario) {
    var merged = JSON.parse(JSON.stringify(scenario));
    ["fundamentals", "multiples", "balance_sheet"].forEach(function (key) {
      var base = baseData[key], over = scenario[key];
      if (base && typeof base === "object" && !Array.isArray(base)) {
        var out = JSON.parse(JSON.stringify(base));
        if (over && typeof over === "object" && !Array.isArray(over)) {
          for (var k in over) { if (over.hasOwnProperty(k)) out[k] = over[k]; }
        }
        merged[key] = out;
      } else if (over !== undefined) {
        merged[key] = over;
      }
    });
    return merged;
  }

  /**
   * Normalize a comps input into { method, anchor, multiples, scenarios[],
   * intrinsic }. Each scenario carries its implied price per multiple, the
   * average (fair value), and `raw` = the merged inputs behind it. The headline
   * intrinsic is the probability-weighted average (a single case → its average).
   */
  function evaluate(data) {
    var keys = data.multiples || Object.keys(MULTIPLES);
    var scen = normalizeScenarios(data.scenarios);
    var results = scen.map(function (s, idx) {
      var raw = mergeScenario(data, s);
      var bs = raw.balance_sheet || {};
      var ctx = { netCash: parseValue(bs.net_cash) || 0, shares: parseValue(bs.diluted_shares) };
      var implied = {};
      keys.forEach(function (k) { implied[k] = impliedPrice(k, raw, ctx); });
      var vals = keys.map(function (k) { return implied[k]; }).filter(function (x) { return x !== null && !isNaN(x); });
      var avg = mean(keys.map(function (k) { return implied[k]; }));
      return {
        name: s.name || "Scenario " + (idx + 1),
        probability: s.probability,
        ctx: ctx,
        implied: implied,
        average: avg,
        low: vals.length ? Math.min.apply(null, vals) : null,
        high: vals.length ? Math.max.apply(null, vals) : null,
        contribution: avg * s.probability,
        raw: raw,
      };
    });
    var intrinsic = results.reduce(function (s, r) { return s + r.contribution; }, 0);
    return {
      method: "Relative valuation — peer multiples" + (data.anchor ? " (" + data.anchor + ")" : ""),
      anchor: data.anchor || null,
      multiples: keys,
      scenarios: results,
      intrinsic: intrinsic,
      peers: data.peers || [],
    };
  }

  function peerAnchor(peers, key) {
    var vals = (peers || []).map(function (p) { return p[key]; })
      .filter(function (x) { return x !== null && x !== undefined && !isNaN(x); });
    if (!vals.length) return "—";
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    return lo === hi ? multx(lo) : lo.toFixed(1) + "–" + multx(hi);
  }

  // ------------------------------------------------------------- DOM helpers
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  // rows: array of arrays; each cell is a string or { text, cls }.
  function tableFrom(headers, rows) {
    var scroll = el("div", "table-scroll");
    var table = document.createElement("table");
    var thead = document.createElement("thead");
    var htr = document.createElement("tr");
    headers.forEach(function (h, i) { htr.appendChild(el("th", i === 0 ? null : "num", h)); });
    thead.appendChild(htr);
    table.appendChild(thead);
    var tbody = document.createElement("tbody");
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      row.forEach(function (cell, i) {
        var isObj = cell && typeof cell === "object";
        var cls = isObj && cell.cls ? cell.cls : (i === 0 ? "name" : "num");
        tr.appendChild(el("td", cls, isObj ? cell.text : cell));
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    scroll.appendChild(table);
    return scroll;
  }

  // The report is built from the single (base) case. If several scenarios are
  // present, the highest-probability one drives this simple view.
  function primaryScenario(evald) {
    return evald.scenarios.slice().sort(function (a, b) { return b.probability - a.probability; })[0];
  }

  // Step 1 — what the peers trade at.
  function renderPeers(evald) {
    var mount = document.getElementById("cmp-peers");
    if (!mount) return;
    mount.innerHTML = "";
    var keys = evald.multiples;
    var headers = ["Peer"].concat(keys.map(function (k) { return MULTIPLES[k] ? MULTIPLES[k].label : k; }));
    var rows = (evald.peers || []).map(function (p) {
      return [p.name].concat(keys.map(function (k) { return multx(p[k]); }));
    });
    rows.push([{ text: "Peer range", cls: "name muted-cell" }].concat(
      keys.map(function (k) { return { text: peerAnchor(evald.peers, k), cls: "num muted-cell" }; })));
    mount.appendChild(tableFrom(headers, rows));
  }

  // Step 2 — our forward figure × chosen multiple, with the peer range beside it.
  function renderInputs(evald, notes) {
    var mount = document.getElementById("cmp-inputs");
    if (!mount) return;
    mount.innerHTML = "";
    var s = primaryScenario(evald);
    var headers = ["Multiple", "MU's FY figure", "Our multiple", "Peer range"];
    var rows = evald.multiples.map(function (k) {
      var def = MULTIPLES[k];
      var mv = metricValue(k, s.raw.fundamentals);
      return [
        def.label,
        { text: def.metricLabel + " " + def.fmt(mv), cls: "num" },
        { text: multx(s.raw.multiples[k]), cls: "num strong" },
        { text: peerAnchor(evald.peers, k), cls: "num muted-cell" },
      ];
    });
    mount.appendChild(tableFrom(headers, rows));

    if (notes && Array.isArray(notes.drivers) && notes.drivers.length) {
      var list = el("div", "reads");
      notes.drivers.forEach(function (d) {
        var p = el("p", "read-line");
        if (d.label) p.appendChild(el("span", "read-key", d.label));
        if (d.comment) p.appendChild(el("span", "read-note", (d.label ? " — " : "") + d.comment));
        list.appendChild(p);
      });
      mount.appendChild(list);
    }
  }

  // Step 3 — each multiple's implied price, averaged into the fair value.
  function renderCalc(evald) {
    var mount = document.getElementById("cmp-calc");
    if (!mount) return;
    mount.innerHTML = "";
    var s = primaryScenario(evald);
    var headers = ["Multiple", "Calculation", "Implied price"];
    var rows = evald.multiples.map(function (k) {
      return [MULTIPLES[k].label, { text: calcString(k, s.raw, s.ctx), cls: "num muted-cell" }, { text: price(s.implied[k]), cls: "num" }];
    });
    rows.push([
      { text: "Fair value", cls: "name strong" },
      { text: "average of the " + evald.multiples.length + " prices", cls: "num muted-cell" },
      { text: price(s.average), cls: "num strong" },
    ]);
    mount.appendChild(tableFrom(headers, rows));
  }

  function renderKeyInputs(data, evald) {
    var kbody = document.getElementById("cmp-key-inputs");
    if (!kbody) return;
    kbody.innerHTML = "";
    var bs = data.balance_sheet || {};
    var rows = [];
    if (data.anchor) rows.push(["Forward year", data.anchor]);
    if (data.peer_group) rows.push(["Peer group", data.peer_group]);
    if (bs.net_cash !== undefined) rows.push(["Net cash (cash − debt)", money(parseValue(bs.net_cash))]);
    if (bs.diluted_shares !== undefined) rows.push(["Diluted shares", shareCount(parseValue(bs.diluted_shares))]);
    rows.push(["Multiples used", evald.multiples.map(function (k) { return MULTIPLES[k] ? MULTIPLES[k].label : k; }).join(", ")]);
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.appendChild(el("td", null, r[0]));
      tr.appendChild(el("td", "num", r[1]));
      kbody.appendChild(tr);
    });
  }

  function renderReport(data, notes) {
    notes = notes || {};
    var evald = evaluate(data);
    var methodEl = document.getElementById("cmp-method");
    if (methodEl) methodEl.textContent = evald.method;
    var fvEl = document.getElementById("cmp-fairvalue");
    if (fvEl) fvEl.textContent = price(evald.intrinsic);
    renderPeers(evald);
    renderInputs(evald, notes);
    renderCalc(evald);
    renderKeyInputs(data, evald);
    return evald;
  }

  // ------------------------------------------------------------------ public
  var COMPS = {
    parseValue: parseValue, money: money, price: price, multx: multx,
    impliedPrice: impliedPrice, evaluate: evaluate, renderReport: renderReport,
  };

  function readJson(id) {
    var node = document.getElementById(id);
    if (!node) return null;
    try { return JSON.parse(node.textContent); } catch (e) { return null; }
  }

  function boot() {
    var input = readJson("cmp-input");
    if (!input) return;
    try {
      renderReport(input, readJson("cmp-notes"));
    } catch (err) {
      var box = document.getElementById("cmp-fairvalue");
      if (box) box.textContent = "error";
      if (global.console) console.error("Comps report render failed:", err);
    }
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = COMPS; // Node (validation harness)
  } else {
    global.COMPS = COMPS;
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", boot);
    } else {
      boot();
    }
  }
})(typeof window !== "undefined" ? window : this);
