/*
 * daily-val — client-side relative-valuation (peer multiples) engine.
 *
 * A sibling to docs/assets/dcf.js, for cyclical / commodity businesses where a
 * forward-earnings × peer-multiple story is the honest model and a smooth FCFF
 * DCF is not. It anchors a forward metric (EPS, EBITDA, revenue, book value),
 * applies a peer/re-rating multiple (P/E, EV/EBITDA, P/B, EV/Sales), bridges
 * EV→equity via net cash where needed, and cross-checks across multiples,
 * probability-weighted across bear/base/bull scenarios.
 *
 * The static pages ship the *inputs* only; this script turns them into the
 * final valuation. Valuation only — no live market price.
 *
 * Like dcf.js, evaluate(data) returns a normalized
 *   { method, scenarios[], intrinsic }
 * so the shared landing page can headline either engine's number.
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
      if (mult[suffix] !== undefined) {
        return parseFloat(v.slice(0, -1)) * mult[suffix];
      }
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
      if (ax >= units[i][1]) {
        return "$" + (x / units[i][1]).toFixed(decimals) + units[i][0];
      }
    }
    return "$" + x.toFixed(0);
  }

  function pct(x) {
    if (x === null || x === undefined || isNaN(x)) return "N/A";
    return (x * 100).toFixed(1) + "%";
  }

  function price(x) {
    if (x === null || x === undefined || isNaN(x)) return "—";
    return "$" + x.toFixed(0);
  }

  function mult(x) {
    if (x === null || x === undefined || isNaN(x)) return "—";
    return x.toFixed(1) + "×"; // e.g. 8.0×
  }

  // ----------------------------------------------------------- multiples map
  // Each multiple maps a scenario's forward fundamentals + an applied multiple
  // to an implied share price. Two kinds:
  //   equity: the multiple is applied to a per-share metric → price directly.
  //   ev:     the multiple is applied to a firm-level metric → enterprise
  //           value, bridged to equity via net cash, then divided by shares.
  var MULTIPLES = {
    pe: {
      label: "P/E", kind: "equity", metric: "eps",
      apply: function (f) { return parseValue(f.eps); }, // × multiple below
    },
    pb: {
      label: "P/B", kind: "equity", metric: "bvps",
      apply: function (f) { return parseValue(f.bvps); },
    },
    ev_ebitda: {
      label: "EV/EBITDA", kind: "ev", metric: "ebitda",
      apply: function (f) { return parseValue(f.ebitda); },
    },
    ev_sales: {
      label: "EV/Sales", kind: "ev", metric: "revenue",
      apply: function (f) { return parseValue(f.revenue); },
    },
  };

  // Implied price for one multiple in one (merged) scenario.
  function impliedPrice(key, scenario, ctx) {
    var def = MULTIPLES[key];
    if (!def) return null;
    var m = scenario.multiples ? scenario.multiples[key] : null;
    if (m === null || m === undefined) return null;
    var base = def.apply(scenario.fundamentals || {});
    if (base === null || base === undefined || isNaN(base)) return null;
    if (def.kind === "equity") return base * m;
    // ev: EV = metric × multiple; equity = EV + net cash; per share.
    var ev = base * m;
    var equity = ev + ctx.netCash;
    return ctx.shares ? equity / ctx.shares : null;
  }

  function mean(xs) {
    var v = xs.filter(function (x) { return x !== null && !isNaN(x); });
    if (!v.length) return null;
    return v.reduce(function (s, x) { return s + x; }, 0) / v.length;
  }

  // --------------------------------------------------------------- scenarios
  function normalizeScenarios(raw) {
    if (!Array.isArray(raw) || raw.length === 0) {
      throw new Error("'scenarios' must be a non-empty list");
    }
    var scenarios = raw.map(function (s, idx) {
      if (typeof s !== "object" || s === null) {
        throw new Error("scenarios[" + idx + "] must be an object");
      }
      if (!("probability" in s)) {
        throw new Error("scenarios[" + idx + "] is missing 'probability'");
      }
      var p = Number(s.probability);
      if (isNaN(p)) throw new Error("scenarios[" + idx + "].probability must be a number");
      if (p < 0) throw new Error("scenarios[" + idx + "].probability cannot be negative");
      var copy = JSON.parse(JSON.stringify(s));
      copy.probability = p;
      return copy;
    });
    var total = scenarios.reduce(function (s, x) { return s + x.probability; }, 0);
    if (total <= 0) throw new Error("Scenario probability sum must be > 0");
    // Accept decimal probabilities (sum 1.0) or percentages (sum 100).
    if (total > 1.0001) {
      if (Math.abs(total - 100.0) <= 0.1) {
        scenarios.forEach(function (s) { s.probability /= 100.0; });
        total = scenarios.reduce(function (s, x) { return s + x.probability; }, 0);
      } else {
        throw new Error("Scenario probabilities must sum to 1.0 (or 100)");
      }
    }
    if (Math.abs(total - 1.0) > 0.001) {
      throw new Error("Scenario probabilities must sum to 1.0; got " + total.toFixed(4));
    }
    return scenarios;
  }

  // Merge top-level defaults (fundamentals / multiples / balance_sheet) with a
  // scenario's overrides, so a scenario need only carry what differs.
  function mergeScenario(baseData, scenario) {
    var merged = JSON.parse(JSON.stringify(scenario));
    ["fundamentals", "multiples", "balance_sheet"].forEach(function (key) {
      var base = baseData[key];
      var over = scenario[key];
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
   * Normalize a comps input doc into { method, anchor, multiples, scenarios[],
   * intrinsic }. Each scenario carries the implied price per multiple, its
   * blended (equal-weight) and "core" values, the min–max range, its
   * probability contribution, and `raw` = the merged inputs behind it.
   */
  function evaluate(data) {
    var keys = data.multiples || Object.keys(MULTIPLES);
    var coreKeys = data.core_multiples || keys;
    var scen = normalizeScenarios(data.scenarios);

    var results = scen.map(function (s, idx) {
      var raw = mergeScenario(data, s);
      var bs = raw.balance_sheet || {};
      var ctx = {
        netCash: parseValue(bs.net_cash) || 0,
        shares: parseValue(bs.diluted_shares),
      };
      var implied = {};
      keys.forEach(function (k) { implied[k] = impliedPrice(k, raw, ctx); });

      var all = keys.map(function (k) { return implied[k]; });
      var core = coreKeys.map(function (k) { return implied[k]; });
      var present = all.filter(function (x) { return x !== null && !isNaN(x); });
      var blended = mean(all);

      return {
        name: s.name || "Scenario " + (idx + 1),
        probability: s.probability,
        implied: implied,
        blended: blended,
        core: mean(core),
        low: present.length ? Math.min.apply(null, present) : null,
        high: present.length ? Math.max.apply(null, present) : null,
        contribution: blended * s.probability,
        raw: raw,
      };
    });

    var intrinsic = results.reduce(function (s, r) { return s + r.contribution; }, 0);
    var coreWeighted = results.reduce(function (s, r) { return s + (r.core || 0) * r.probability; }, 0);
    var anchor = data.anchor ? " (" + data.anchor + ")" : "";

    return {
      method: "Relative valuation — peer multiples, probability-weighted" + anchor,
      anchor: data.anchor || null,
      multiples: keys,
      coreMultiples: coreKeys,
      scenarios: results,
      intrinsic: intrinsic,
      coreWeighted: coreWeighted,
      peers: data.peers || [],
    };
  }

  // Peer multiple anchor as a "lo–hi×" string for a given multiple key.
  function peerAnchor(peers, key) {
    var vals = (peers || []).map(function (p) { return p[key]; })
      .filter(function (x) { return x !== null && x !== undefined && !isNaN(x); });
    if (!vals.length) return null;
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    return lo === hi ? mult(lo) : lo.toFixed(1) + "–" + mult(hi);
  }

  // ---------------------------------------------------- driver value getters
  // Map a note key -> value pulled from a merged scenario. `group` buckets
  // drivers into readable tables. `multKey` marks applied-multiple drivers so
  // the header can carry the peer anchor.
  var DRIVERS = {
    eps:     { group: "fund", label: "FY EPS", short: "EPS", get: function (r) { return price(parseValue(r.fundamentals.eps)); } },
    ebitda:  { group: "fund", label: "FY EBITDA", short: "EBITDA", get: function (r) { return money(parseValue(r.fundamentals.ebitda), 0); } },
    revenue: { group: "fund", label: "FY revenue", short: "Revenue", get: function (r) { return money(parseValue(r.fundamentals.revenue), 0); } },
    bvps:    { group: "fund", label: "FY book value / share", short: "BVPS", get: function (r) { return price(parseValue(r.fundamentals.bvps)); } },
    mult_pe:        { group: "mult", multKey: "pe",        label: "P/E multiple", short: "P/E", get: function (r) { return mult(r.multiples.pe); } },
    mult_ev_ebitda: { group: "mult", multKey: "ev_ebitda", label: "EV/EBITDA multiple", short: "EV/EBITDA", get: function (r) { return mult(r.multiples.ev_ebitda); } },
    mult_pb:        { group: "mult", multKey: "pb",        label: "P/B multiple", short: "P/B", get: function (r) { return mult(r.multiples.pb); } },
    mult_ev_sales:  { group: "mult", multKey: "ev_sales",  label: "EV/Sales multiple", short: "EV/Sales", get: function (r) { return mult(r.multiples.ev_sales); } },
    net_cash:    { group: "meta", label: "Net cash (cash − debt)", short: "Net cash", get: function (r) { return money(parseValue((r.balance_sheet || {}).net_cash)); } },
    shares:      { group: "meta", label: "Diluted shares", short: "Shares", get: function (r) { var s = parseValue((r.balance_sheet || {}).diluted_shares); return s ? (s / 1e9).toFixed(2) + "B" : "—"; } },
    probability: { group: "meta", label: "Scenario probability", short: "Prob.", get: function (r, s) { return pct(s.probability); } },
  };

  // ------------------------------------------------------------- DOM helpers
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function tableFrom(headerCells, rows) {
    var scroll = el("div", "table-scroll");
    var table = document.createElement("table");
    var thead = document.createElement("thead");
    var htr = document.createElement("tr");
    headerCells.forEach(function (h, i) { htr.appendChild(el("th", i === 0 ? null : "num", h)); });
    thead.appendChild(htr);
    table.appendChild(thead);
    var tbody = document.createElement("tbody");
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      row.forEach(function (cell, i) {
        var c = el("td", i === 0 ? "name" : (cell.cls || "num"), cell.text !== undefined ? cell.text : cell);
        tr.appendChild(c);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    scroll.appendChild(table);
    return scroll;
  }

  // Scenario breakdown: one row per scenario, blended + core + range, with the
  // probability-weighted fair value in the footer and the core cross-check note.
  function renderScenarioTable(evald) {
    var tbody = document.getElementById("cmp-scenario-rows");
    if (tbody) {
      tbody.innerHTML = "";
      evald.scenarios.forEach(function (s) {
        var tr = document.createElement("tr");
        tr.appendChild(el("td", "name", s.name));
        tr.appendChild(el("td", "num", pct(s.probability)));
        tr.appendChild(el("td", "num strong", price(s.blended)));
        tr.appendChild(el("td", "num", price(s.core)));
        tr.appendChild(el("td", "num", price(s.low) + "–" + price(s.high)));
        tr.appendChild(el("td", "num", price(s.contribution)));
        tbody.appendChild(tr);
      });
    }
    var w = document.getElementById("cmp-weighted");
    if (w) w.textContent = price(evald.intrinsic);
    var core = document.getElementById("cmp-core");
    if (core) {
      core.textContent = "Core cross-check (P/E + EV/EBITDA only), probability-weighted: "
        + price(evald.coreWeighted) + ". The blended headline equal-weights all four "
        + "multiples; the core view drops P/B and EV/Sales, the two that anchor least well for a memory maker.";
    }
  }

  // Implied price by multiple × scenario, with a peer-anchor column and blended
  // / core summary rows at the foot.
  function renderMatrix(evald) {
    var mount = document.getElementById("cmp-matrix");
    if (!mount) return;
    mount.innerHTML = "";
    var scen = evald.scenarios;
    var header = ["Multiple", "Peer anchor"].concat(scen.map(function (s) { return s.name; }));
    var rows = evald.multiples.map(function (k) {
      var def = MULTIPLES[k];
      var row = [def ? def.label : k, { text: peerAnchor(evald.peers, k) || "—", cls: "num muted-cell" }];
      scen.forEach(function (s) { row.push(price(s.implied[k])); });
      return row;
    });
    // Blended (all four) + core (P/E + EV/EBITDA) summary rows.
    var blendRow = [{ text: "Blended (equal-wt)", cls: "name strong" }, { text: "", cls: "num" }];
    scen.forEach(function (s) { blendRow.push({ text: price(s.blended), cls: "num strong" }); });
    rows.push(blendRow);
    var coreRow = [{ text: "Core (P/E + EV/EBITDA)", cls: "name" }, { text: "", cls: "num" }];
    scen.forEach(function (s) { coreRow.push({ text: price(s.core), cls: "num" }); });
    rows.push(coreRow);
    mount.appendChild(tableFrom(header, rows));
  }

  // Assumptions "how defensible": grouped tables (forward fundamentals, applied
  // multiples, other), one column per driver, one row per scenario, with the
  // plain-English reads from the notes sidecar beneath each group.
  function renderDrivers(driverNotes, evald) {
    var mount = document.getElementById("cmp-drivers");
    if (!mount || !Array.isArray(driverNotes) || driverNotes.length === 0) return;
    mount.innerHTML = "";

    var enriched = driverNotes.map(function (dn) {
      var def = DRIVERS[dn.key];
      return def ? { dn: dn, def: def } : null;
    }).filter(Boolean);

    var GROUPS = [
      { id: "fund", title: "Forward fundamentals" + (evald.anchor ? " (" + evald.anchor + ")" : "") },
      { id: "mult", title: "Applied multiples vs peers" },
      { id: "meta", title: "Bridge & probability" },
    ];

    GROUPS.forEach(function (g) {
      var items = enriched.filter(function (e) { return e.def.group === g.id; });
      if (!items.length) return;

      var block = el("div", "assump");
      block.appendChild(el("div", "assump-head")).appendChild(el("span", "assump-label", g.title));

      var headers = ["Scenario"].concat(items.map(function (e) {
        var h = e.def.short || e.dn.label || e.def.label;
        if (e.def.multKey) {
          var anchor = peerAnchor(evald.peers, e.def.multKey);
          if (anchor) h += " (peers " + anchor + ")";
        }
        return h;
      }));
      var rows = evald.scenarios.map(function (s) {
        var row = [s.name];
        items.forEach(function (e) {
          var v;
          try { v = e.def.get(s.raw, s); } catch (err) { v = "—"; }
          row.push(v);
        });
        return row;
      });
      block.appendChild(tableFrom(headers, rows));

      var reads = items.filter(function (e) { return e.dn.verdict || e.dn.comment; });
      if (reads.length) {
        var list = el("div", "reads");
        reads.forEach(function (e) {
          var p = el("p", "read-line");
          p.appendChild(el("span", "read-key", e.dn.label || e.def.label));
          if (e.dn.verdict) { p.appendChild(document.createTextNode(" ")); p.appendChild(el("span", "verdict", e.dn.verdict)); }
          if (e.dn.comment) p.appendChild(el("span", "read-note", " " + e.dn.comment));
          list.appendChild(p);
        });
        block.appendChild(list);
      }
      mount.appendChild(block);
    });
  }

  function renderKeyInputs(data, evald) {
    var kbody = document.getElementById("cmp-key-inputs");
    if (!kbody) return;
    kbody.innerHTML = "";
    var bs = data.balance_sheet || {};
    var rows = [];
    if (data.anchor) rows.push(["Forward anchor", data.anchor]);
    if (data.peer_group) rows.push(["Peer group", data.peer_group]);
    if (bs.net_cash !== undefined) rows.push(["Net cash (cash − debt)", money(parseValue(bs.net_cash))]);
    if (bs.diluted_shares !== undefined) {
      rows.push(["Diluted shares", (parseValue(bs.diluted_shares) / 1e9).toFixed(2) + "B"]);
    }
    rows.push(["Multiples used", evald.multiples.map(function (k) { return MULTIPLES[k] ? MULTIPLES[k].label : k; }).join(", ")]);
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.appendChild(el("td", null, r[0]));
      tr.appendChild(el("td", "num", r[1]));
      kbody.appendChild(tr);
    });

    // Peer multiples reference table, if peers are supplied.
    var pmount = document.getElementById("cmp-peers");
    if (pmount && (data.peers || []).length) {
      pmount.innerHTML = "";
      var header = ["Peer"].concat(evald.multiples.map(function (k) { return MULTIPLES[k] ? MULTIPLES[k].label : k; }));
      var rows2 = data.peers.map(function (p) {
        return [p.name].concat(evald.multiples.map(function (k) { return mult(p[k]); }));
      });
      pmount.appendChild(tableFrom(header, rows2));
    }
  }

  function renderReport(data, notes) {
    notes = notes || {};
    var evald = evaluate(data);
    var methodEl = document.getElementById("cmp-method");
    if (methodEl) methodEl.textContent = evald.method;
    renderScenarioTable(evald);
    renderMatrix(evald);
    renderDrivers(notes.drivers, evald);
    renderKeyInputs(data, evald);
    return evald;
  }

  // ------------------------------------------------------------------ public
  var COMPS = {
    parseValue: parseValue,
    money: money,
    pct: pct,
    price: price,
    mult: mult,
    impliedPrice: impliedPrice,
    evaluate: evaluate,
    renderReport: renderReport,
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
      var box = document.getElementById("cmp-weighted");
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
