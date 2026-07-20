#!/usr/bin/env python3
"""Relative-valuation (peer multiples) calculator — parity oracle for comps.js.

A forward metric (EPS, EBITDA, revenue, book value) times a peer / re-rating
multiple (P/E, EV/EBITDA, P/B, EV/Sales), EV bridged to equity via net cash,
cross-checked across multiples and probability-weighted across scenarios. This
is the non-browser reference implementation of docs/assets/comps.js; the two must
agree.

Usage:
    python comps_calculator.py <input_json_file>
"""

import json
import sys
from pathlib import Path

# Multiple registry: kind "equity" applies to a per-share metric (price
# directly); kind "ev" applies to a firm-level metric (→ EV → equity via net
# cash → per share).
MULTIPLES = {
    "pe":        {"label": "P/E",       "kind": "equity", "metric": "eps"},
    "ev_ebitda": {"label": "EV/EBITDA", "kind": "ev",     "metric": "ebitda"},
    "pb":        {"label": "P/B",       "kind": "equity", "metric": "bvps"},
    "ev_sales":  {"label": "EV/Sales",  "kind": "ev",     "metric": "revenue"},
}


def parse_value(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().upper().replace(",", "")
    mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
    if raw and raw[-1] in mult:
        return float(raw[:-1]) * mult[raw[-1]]
    return float(raw)


def merge_scenario(data, scenario):
    merged = json.loads(json.dumps(scenario))
    for key in ("fundamentals", "multiples", "balance_sheet"):
        base = data.get(key)
        over = scenario.get(key)
        if isinstance(base, dict):
            out = dict(base)
            if isinstance(over, dict):
                out.update(over)
            merged[key] = out
        elif over is not None:
            merged[key] = over
    return merged


def implied_price(key, scenario, net_cash, shares):
    defn = MULTIPLES.get(key)
    m = (scenario.get("multiples") or {}).get(key)
    if defn is None or m is None:
        return None
    base = parse_value((scenario.get("fundamentals") or {}).get(defn["metric"]))
    if base is None:
        return None
    if defn["kind"] == "equity":
        return base * m
    ev = base * m
    return (ev + net_cash) / shares if shares else None


def normalize_probabilities(scenarios):
    total = sum(float(s["probability"]) for s in scenarios)
    if abs(total - 100.0) <= 0.1:
        for s in scenarios:
            s["probability"] = float(s["probability"]) / 100.0
        total = sum(s["probability"] for s in scenarios)
    if abs(total - 1.0) > 0.001:
        raise ValueError(f"Scenario probabilities must sum to 1.0 (or 100); got {total}")


def evaluate(data):
    keys = data.get("multiples") or list(MULTIPLES)
    core_keys = data.get("core_multiples") or keys
    scenarios = json.loads(json.dumps(data["scenarios"]))
    normalize_probabilities(scenarios)

    results = []
    for s in scenarios:
        raw = merge_scenario(data, s)
        bs = raw.get("balance_sheet") or {}
        net_cash = parse_value(bs.get("net_cash")) or 0.0
        shares = parse_value(bs.get("diluted_shares"))
        implied = {k: implied_price(k, raw, net_cash, shares) for k in keys}
        allv = [implied[k] for k in keys if implied[k] is not None]
        corev = [implied[k] for k in core_keys if implied.get(k) is not None]
        blended = sum(allv) / len(allv) if allv else None
        core = sum(corev) / len(corev) if corev else None
        results.append({
            "name": s.get("name", "Scenario"),
            "probability": s["probability"],
            "implied": implied,
            "blended": blended,
            "core": core,
            "low": min(allv) if allv else None,
            "high": max(allv) if allv else None,
            "contribution": (blended or 0) * s["probability"],
        })

    intrinsic = sum(r["contribution"] for r in results)
    core_weighted = sum((r["core"] or 0) * r["probability"] for r in results)
    return {"keys": keys, "scenarios": results, "intrinsic": intrinsic,
            "core_weighted": core_weighted, "peers": data.get("peers", [])}


def money(x):
    if x is None:
        return "N/A"
    ax = abs(x)
    for suf, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if ax >= div:
            return f"${x / div:.0f}{suf}"
    return f"${x:.0f}"


def peer_anchor(peers, key):
    vals = [p[key] for p in peers if p.get(key) is not None]
    if not vals:
        return "—"
    lo, hi = min(vals), max(vals)
    return f"{lo:.1f}×" if lo == hi else f"{lo:.1f}–{hi:.1f}×"


def main():
    if len(sys.argv) < 2:
        print("Usage: python comps_calculator.py <input_json_file>")
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Error: input file not found: {path}")
        sys.exit(1)

    data = json.loads(path.read_text())
    e = evaluate(data)
    keys = e["keys"]
    scen = e["scenarios"]
    anchor = data.get("anchor", "")

    print(f"RELATIVE VALUATION — PEER MULTIPLES  ·  {data.get('symbol', '?')}  ·  {anchor}")
    print(f"Peer group: {data.get('peer_group', '—')}\n")

    # Implied price by multiple × scenario.
    print("Implied price by multiple")
    head = f"{'Multiple':<12}{'Peer anchor':>14}" + "".join(f"{s['name']:>10}" for s in scen)
    print(head)
    for k in keys:
        row = f"{MULTIPLES[k]['label']:<12}{peer_anchor(e['peers'], k):>14}"
        row += "".join(f"${s['implied'][k]:>8.0f}" if s['implied'][k] is not None else f"{'—':>9}" for s in scen)
        print(row)
    print(f"{'Blended':<12}{'':>14}" + "".join(f"${s['blended']:>8.0f}" for s in scen))
    print(f"{'Core (PE+EVE)':<12}{'':>14}" + "".join(f"${s['core']:>8.0f}" for s in scen))

    # Scenario summary.
    print("\nScenario summary")
    print(f"{'Scenario':<10}{'Prob':>7}{'Blended':>10}{'Core':>9}{'Range':>16}{'Weighted':>11}")
    for s in scen:
        rng = f"${s['low']:.0f}-${s['high']:.0f}"
        print(f"{s['name']:<10}{s['probability'] * 100:>6.0f}%${s['blended']:>8.0f}${s['core']:>7.0f}{rng:>16}${s['contribution']:>9.0f}")

    print(f"\nProbability-weighted fair value (blended) : ${e['intrinsic']:.0f}")
    print(f"Core cross-check (P/E + EV/EBITDA)        : ${e['core_weighted']:.0f}")
    print("\nValuation only — no live market price is used.")


if __name__ == "__main__":
    main()
