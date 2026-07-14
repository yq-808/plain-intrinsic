/*
 * plain-intrinsic — client-side DCF engine + comps cross-check.
 *
 * A faithful port of skills/dcf/scripts/dcf_calculator.py (FCFF methodology),
 * with two professional refinements applied in the browser:
 *   - mid-year discounting convention (cash flows arrive mid-year on average),
 *   - a relative-valuation (comps) cross-check: forward EPS x peer P/E.
 *
 * The static pages ship the *inputs* only; this script turns them into the
 * final valuation. Valuation only — no live market price.
 */
(function (global) {
  "use strict";

  // ----------------------------------------------------------------- parsing
  function parseValue(value) {
    if (value === null || value === undefined) return null;
    if (typeof value === "number") return value;
    if (typeof value === "string") {
      var v = value.trim().toUpperCase();
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
    return (x * 100).toFixed(2) + "%";
  }

  function price(x) {
    if (x === null || x === undefined || isNaN(x)) return "—";
    return "$" + x.toFixed(2);
  }

  function multipleFmt(x) {
    if (x === null || x === undefined || isNaN(x)) return "—";
    return x.toFixed(1) + "×";
  }

  // -------------------------------------------------------------------- WACC
  function calculateWacc(waccInputs, taxRate) {
    var rf = waccInputs.risk_free_rate;
    var erp = waccInputs.equity_risk_premium;
    var beta = waccInputs.beta;
    var rd = waccInputs.cost_of_debt;
    var wd = waccInputs.debt_weight;
    var we = waccInputs.equity_weight;
    var re = rf + beta * erp; // CAPM cost of equity
    var wacc = we * re + wd * rd * (1 - taxRate);
    return { wacc: wacc, costOfEquity: re };
  }

  // --------------------------------------------------------------- core DCF
  // Mid-year convention: a cash flow booked "in year n" is received, on
  // average, half-way through it, so it is discounted at (n - 0.5) rather than
  // n. For a Gordon-growth terminal value the continuing value is likewise
  // discounted at (N - 0.5). Net effect ~ +(1+WACC)^0.5, about +4%.
  function calculateDcf(data) {
    var by = data.base_year;
    var a = data.assumptions;

    var baseRevenue = parseValue(by.revenue);
    var daPercent = by.da_percent;
    var nwcPercent = by.nwc_percent;

    var taxRate = a.tax_rate;
    var growthRates = a.growth_rates;
    var ebitMargins = a.ebit_margins;
    var capexPercent = a.capex_percent;
    if (capexPercent === undefined || capexPercent === null) {
      capexPercent = by.capex_percent; // legacy fallback
    }

    var terminalGrowth = data.terminal.growth_rate;

    var bs = data.balance_sheet;
    var cash = parseValue(bs.cash);
    var debt = parseValue(bs.debt);
    var shares = parseValue(bs.diluted_shares);

    var w = calculateWacc(data.wacc_inputs, taxRate);
    var wacc = w.wacc;

    var years = growthRates.length;
    var fcffs = [];
    var discountFactors = [];
    var pvFcffs = [];

    var prevRevenue = baseRevenue;
    var prevNwc = baseRevenue * nwcPercent;

    for (var i = 0; i < years; i++) {
      var revenue = prevRevenue * (1 + growthRates[i]);
      var ebit = revenue * ebitMargins[i];
      var nopat = ebit * (1 - taxRate);
      var da = revenue * daPercent;
      var capexRate = Array.isArray(capexPercent) ? capexPercent[i] : capexPercent;
      var capex = revenue * capexRate;
      var nwc = revenue * nwcPercent;
      var deltaNwc = nwc - prevNwc;
      var fcff = nopat + da - capex - deltaNwc;
      var df = 1 / Math.pow(1 + wacc, i + 0.5); // mid-year convention

      fcffs.push(fcff);
      discountFactors.push(df);
      pvFcffs.push(fcff * df);

      prevRevenue = revenue;
      prevNwc = nwc;
    }

    var terminalFcff = fcffs[years - 1] * (1 + terminalGrowth);
    var terminalValue = terminalFcff / (wacc - terminalGrowth);
    // Gordon-growth terminal value discounted at the final mid-year factor.
    var pvTerminal = terminalValue * discountFactors[years - 1];

    var sumPvFcff = pvFcffs.reduce(function (s, v) { return s + v; }, 0);
    var enterpriseValue = sumPvFcff + pvTerminal;
    var equityValue = enterpriseValue + cash - debt;
    var intrinsicPrice = equityValue / shares;

    return {
      years: years,
      wacc: wacc,
      costOfEquity: w.costOfEquity,
      terminalValue: terminalValue,
      pvTerminal: pvTerminal,
      sumPvFcff: sumPvFcff,
      enterpriseValue: enterpriseValue,
      equityValue: equityValue,
      intrinsicPrice: intrinsicPrice,
      cash: cash,
      debt: debt,
      shares: shares,
      terminalGrowth: terminalGrowth
    };
  }

  // --------------------------------------------------------------- scenarios
  function normalizeScenarios(rawScenarios) {
    if (!Array.isArray(rawScenarios) || rawScenarios.length === 0) {
      throw new Error("'scenarios' must be a non-empty list");
    }
    var scenarios = rawScenarios.map(function (s, idx) {
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

    // Accept either decimal probabilities (sum 1.0) or percentages (sum 100).
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

  function buildScenarioData(baseData, scenario) {
    var scenarioData = JSON.parse(JSON.stringify(baseData));
    delete scenarioData.scenarios;
    ["base_year", "assumptions", "wacc_inputs", "terminal", "balance_sheet"].forEach(function (key) {
      if (key in scenario) {
        var base = scenarioData[key];
        var override = scenario[key];
        if (base && typeof base === "object" && !Array.isArray(base) &&
            override && typeof override === "object" && !Array.isArray(override)) {
          var merged = JSON.parse(JSON.stringify(base));
          for (var k in override) { if (override.hasOwnProperty(k)) merged[k] = override[k]; }
          scenarioData[key] = merged;
        } else {
          scenarioData[key] = override;
        }
      }
    });
    return scenarioData;
  }

  function calculateProbabilityWeighted(data) {
    var scenarios = normalizeScenarios(data.scenarios);
    var results = scenarios.map(function (scenario, idx) {
      var name = scenario.name || "Scenario " + (idx + 1);
      var scenarioData = buildScenarioData(data, scenario);
      var result = calculateDcf(scenarioData);
      return {
        name: name,
        probability: scenario.probability,
        input: scenarioData, // merged inputs, so callers can show assumptions
        results: result,
        contribution: result.intrinsicPrice * scenario.probability
      };
    });
    var weighted = results.reduce(function (s, r) { return s + r.contribution; }, 0);
    return { scenarioResults: results, weightedPrice: weighted };
  }

  /**
   * Normalize any input doc into { method, scenarios[], intrinsic }.
   * Each scenario carries `raw` = the merged inputs behind it.
   */
  function evaluate(data) {
    var scenarios, intrinsic, method;
    if (data.scenarios) {
      var pw = calculateProbabilityWeighted(data);
      scenarios = pw.scenarioResults.map(function (item) {
        return {
          name: item.name,
          probability: item.probability,
          wacc: item.results.wacc,
          terminalGrowth: item.results.terminalGrowth,
          intrinsicPrice: item.results.intrinsicPrice,
          contribution: item.contribution,
          raw: item.input
        };
      });
      intrinsic = pw.weightedPrice;
      method = "DCF — FCFF, probability-weighted scenarios (mid-year)";
    } else {
      var r = calculateDcf(data);
      scenarios = [{
        name: "Base",
        probability: 1.0,
        wacc: r.wacc,
        terminalGrowth: r.terminalGrowth,
        intrinsicPrice: r.intrinsicPrice,
        contribution: r.intrinsicPrice,
        raw: data
      }];
      intrinsic = r.intrinsicPrice;
      method = "DCF — FCFF, single scenario (mid-year)";
    }
    return { method: method, scenarios: scenarios, intrinsic: intrinsic };
  }

  // ---------------------------------------------------- driver value getters
  // Map an assumption key -> a formatted value pulled from a merged scenario.
  var DRIVERS = {
    growth_y1: { label: "Revenue growth · Yr 1", get: function (r) { return pct(r.assumptions.growth_rates[0]); } },
    growth_yN: { label: "Revenue growth · Yr N", get: function (r) { var g = r.assumptions.growth_rates; return pct(g[g.length - 1]); } },
    margin_yN: { label: "EBIT margin · Yr N", get: function (r) { var m = r.assumptions.ebit_margins; return pct(m[m.length - 1]); } },
    wacc: { label: "WACC", get: function (r, s) { return pct(s.wacc); } },
    terminal_g: { label: "Terminal growth", get: function (r, s) { return pct(s.terminalGrowth); } },
    capex_y1: {
      label: "Capex · Yr 1 (% rev)",
      get: function (r) {
        var c = (r.assumptions.capex_percent != null) ? r.assumptions.capex_percent : r.base_year.capex_percent;
        return pct(Array.isArray(c) ? c[0] : c);
      }
    },
    nwc: { label: "Net working capital (% rev)", get: function (r) { return pct(r.base_year.nwc_percent); } },
    probability: { label: "Scenario probability", get: function (r, s) { return pct(s.probability); } }
  };

  // ------------------------------------------------------------- DOM helpers
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function renderScenarioTable(scenarios, intrinsic) {
    var tbody = document.getElementById("dcf-scenario-rows");
    if (tbody) {
      tbody.innerHTML = "";
      scenarios.forEach(function (s) {
        var tr = document.createElement("tr");
        tr.appendChild(el("td", "name", s.name));
        tr.appendChild(el("td", "num", pct(s.probability)));
        tr.appendChild(el("td", "num", pct(s.wacc)));
        tr.appendChild(el("td", "num", pct(s.terminalGrowth)));
        tr.appendChild(el("td", "num strong", price(s.intrinsicPrice)));
        tr.appendChild(el("td", "num", price(s.contribution)));
        tbody.appendChild(tr);
      });
    }
    var weightedEl = document.getElementById("dcf-weighted");
    if (weightedEl) weightedEl.textContent = price(intrinsic);
  }

  function renderKeyInputs(data) {
    var kbody = document.getElementById("dcf-key-inputs");
    if (!kbody) return;
    kbody.innerHTML = "";
    var bs = data.balance_sheet || {};
    var rows = [];
    var baseRev = data.base_year && data.base_year.revenue;
    if (baseRev) rows.push(["Base-year revenue", money(parseValue(baseRev))]);
    if (bs.cash !== undefined) rows.push(["Cash", money(parseValue(bs.cash))]);
    if (bs.debt !== undefined) rows.push(["Debt", money(parseValue(bs.debt))]);
    if (bs.diluted_shares !== undefined) {
      rows.push(["Diluted shares", (parseValue(bs.diluted_shares) / 1e9).toFixed(3) + "B"]);
    }
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.appendChild(el("td", null, r[0]));
      tr.appendChild(el("td", "num", r[1]));
      kbody.appendChild(tr);
    });
  }

  // Assumptions table with a plain-English "how defensible" read per driver.
  function renderDrivers(driverNotes, scenarios) {
    var mount = document.getElementById("dcf-drivers");
    if (!mount || !Array.isArray(driverNotes) || driverNotes.length === 0) return;

    var byName = {};
    scenarios.forEach(function (s) { byName[s.name] = s; });

    var table = document.createElement("table");
    var thead = document.createElement("thead");
    var htr = document.createElement("tr");
    htr.appendChild(el("th", null, "Assumption"));
    scenarios.forEach(function (s) { htr.appendChild(el("th", "num", s.name)); });
    htr.appendChild(el("th", null, "Read"));
    thead.appendChild(htr);
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    driverNotes.forEach(function (dn) {
      var def = DRIVERS[dn.key];
      if (!def) return;
      var tr = document.createElement("tr");
      tr.appendChild(el("td", "name", dn.label || def.label));
      scenarios.forEach(function (s) {
        var val;
        try { val = def.get(s.raw, s); } catch (e) { val = "—"; }
        tr.appendChild(el("td", "num", val));
      });
      var read = el("td", "read");
      if (dn.verdict) read.appendChild(el("span", "verdict", dn.verdict));
      if (dn.comment) read.appendChild(el("span", "read-note", dn.comment));
      tr.appendChild(read);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    mount.innerHTML = "";
    var scroll = el("div", "table-scroll");
    scroll.appendChild(table);
    mount.appendChild(scroll);
  }

  // Relative-valuation cross-check: forward EPS x a range of peer multiples.
  // The chosen multiple is where "market hotness" legitimately enters.
  function renderComps(comps, dcfIntrinsic) {
    var mount = document.getElementById("dcf-comps");
    if (!mount || !comps || !Array.isArray(comps.multiples)) return;
    var eps = comps.forward_eps;

    var table = document.createElement("table");
    var thead = document.createElement("thead");
    var htr = document.createElement("tr");
    htr.appendChild(el("th", null, "Multiple"));
    htr.appendChild(el("th", "num", "P/E"));
    htr.appendChild(el("th", "num", "Implied value / share"));
    thead.appendChild(htr);
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    comps.multiples.forEach(function (m) {
      var tr = document.createElement("tr");
      tr.appendChild(el("td", "name", m.label));
      tr.appendChild(el("td", "num", multipleFmt(m.pe)));
      tr.appendChild(el("td", "num strong", price(eps * m.pe)));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    // Footer: where the DCF sits in P/E terms, so the two methods can be
    // compared on one scale.
    if (dcfIntrinsic && eps) {
      var tfoot = document.createElement("tfoot");
      var ftr = document.createElement("tr");
      ftr.appendChild(el("td", "name", "DCF value implies"));
      ftr.appendChild(el("td", "num strong", multipleFmt(dcfIntrinsic / eps)));
      ftr.appendChild(el("td", "num strong", price(dcfIntrinsic)));
      tfoot.appendChild(ftr);
      table.appendChild(tfoot);
    }

    mount.innerHTML = "";
    if (comps.eps_basis) mount.appendChild(el("p", "meta", "Earnings basis: " + comps.eps_basis));
    var scroll = el("div", "table-scroll");
    scroll.appendChild(table);
    mount.appendChild(scroll);
    if (comps.note) mount.appendChild(el("p", "panel-note", comps.note));
  }

  function renderReport(data, notes) {
    notes = notes || {};
    var evald = evaluate(data);

    var methodEl = document.getElementById("dcf-method");
    if (methodEl) methodEl.textContent = evald.method;
    var intrinsicEl = document.getElementById("dcf-intrinsic");
    if (intrinsicEl) intrinsicEl.textContent = price(evald.intrinsic);

    renderScenarioTable(evald.scenarios, evald.intrinsic);
    renderComps(notes.comps, evald.intrinsic);
    renderDrivers(notes.drivers, evald.scenarios);
    renderKeyInputs(data);
    return evald;
  }

  function renderIndex(entries) {
    var mount = document.getElementById("dcf-index");
    if (!mount) return;

    var bySymbol = {};
    entries.forEach(function (e) {
      (bySymbol[e.symbol] = bySymbol[e.symbol] || []).push(e);
    });
    Object.keys(bySymbol).forEach(function (sym) {
      bySymbol[sym].sort(function (a, b) { return a.date < b.date ? 1 : -1; });
    });

    mount.innerHTML = "";
    if (entries.length === 0) {
      mount.appendChild(el("p", "empty", "No reports yet."));
      return;
    }

    Object.keys(bySymbol).sort().forEach(function (sym) {
      var section = el("section", "sym-group");
      section.appendChild(el("h2", null, sym));
      bySymbol[sym].forEach(function (e) {
        var a = document.createElement("a");
        a.className = "report-row";
        a.href = e.path;
        a.appendChild(el("span", "rr-date", e.date));
        a.appendChild(el("span", "rr-method", e.method || ""));
        var metric = el("span", "rr-metric", "intrinsic ");
        var b = el("b");
        try { b.textContent = price(evaluate(e.input).intrinsic); }
        catch (err) { b.textContent = "—"; }
        metric.appendChild(b);
        a.appendChild(metric);
        section.appendChild(a);
      });
      mount.appendChild(section);
    });
  }

  // ------------------------------------------------------------------ public
  var DCF = {
    parseValue: parseValue,
    money: money,
    pct: pct,
    price: price,
    calculateWacc: calculateWacc,
    calculateDcf: calculateDcf,
    calculateProbabilityWeighted: calculateProbabilityWeighted,
    evaluate: evaluate,
    renderReport: renderReport,
    renderIndex: renderIndex
  };

  function readJson(id) {
    var node = document.getElementById(id);
    if (!node) return null;
    try { return JSON.parse(node.textContent); } catch (e) { return null; }
  }

  function boot() {
    var input = readJson("dcf-input");
    if (input) {
      try {
        renderReport(input, readJson("dcf-notes"));
      } catch (err) {
        var box = document.getElementById("dcf-intrinsic");
        if (box) box.textContent = "error";
        if (global.console) console.error("DCF report render failed:", err);
      }
    }
    var manifest = readJson("dcf-manifest");
    if (manifest) {
      try { renderIndex(manifest); }
      catch (err) { if (global.console) console.error("DCF index render failed:", err); }
    }
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = DCF; // Node (validation harness)
  } else {
    global.DCF = DCF;
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", boot);
    } else {
      boot();
    }
  }
})(typeof window !== "undefined" ? window : this);
