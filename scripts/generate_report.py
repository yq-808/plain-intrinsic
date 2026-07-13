#!/usr/bin/env python3
"""Generate a dated HTML valuation report and refresh the site index.

Usage:
    python scripts/generate_report.py GOOGL                  # dated today
    python scripts/generate_report.py GOOGL --date 2026-07-13

The report reuses the DCF engine in skills/dcf/scripts/dcf_calculator.py so the
numbers on the page always match the skill's own output. Each run:

  1. computes the (probability-weighted) DCF for the symbol,
  2. writes docs/reports/<symbol>/<date>.html,
  3. records the run in docs/reports/manifest.json,
  4. rebuilds docs/index.html from that manifest.

Adding a new dated report later is a single command; the landing page updates
itself.
"""

import argparse
import datetime as dt
import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DCF_SCRIPTS = ROOT / "skills" / "dcf" / "scripts"
DCF_REF = ROOT / "skills" / "dcf" / "reference"
DOCS = ROOT / "docs"
REPORTS_DIR = DOCS / "reports"
MANIFEST = REPORTS_DIR / "manifest.json"

sys.path.insert(0, str(DCF_SCRIPTS))
import dcf_calculator as dcf  # noqa: E402


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def money(x):
    """Compact currency, e.g. 1.63T / 472.6B / 195.5M."""
    ax = abs(x)
    for unit, scale in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if ax >= scale:
            return f"${x / scale:,.2f}{unit}"
    return f"${x:,.0f}"


def pct(x):
    return f"{x * 100:.2f}%"


def price(x):
    return f"${x:,.2f}"


# --------------------------------------------------------------------------- #
# Data loading + computation
# --------------------------------------------------------------------------- #
def load_json(path):
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def compute(symbol):
    """Return a normalized dict of everything the template needs."""
    input_path = DCF_REF / "inputs" / f"{symbol}.json"
    data = load_json(input_path)
    if data is None:
        sys.exit(f"Error: no DCF input file for {symbol} at {input_path}")

    quote_doc = load_json(DCF_REF / "quotes" / f"{symbol}_quote.json")
    market_price = None
    snapshot_date = None
    if quote_doc:
        market_price = quote_doc.get("quote", {}).get("c")
        fetched = quote_doc.get("fetched_at", "")
        snapshot_date = fetched[:10] if fetched else None

    scenarios = []
    if data.get("scenarios"):
        scenario_results, weighted_price = dcf.calculate_probability_weighted_results(data)
        for item in scenario_results:
            r = item["results"]
            scenarios.append(
                {
                    "name": item["name"],
                    "probability": item["probability"],
                    "wacc": r["wacc"],
                    "terminal_growth": r["terminal_growth"],
                    "intrinsic_price": r["intrinsic_price"],
                    "enterprise_value": r["enterprise_value"],
                    "equity_value": r["equity_value"],
                    "contribution": item["contribution"],
                }
            )
        intrinsic = weighted_price
        method = "DCF — FCFF, probability-weighted scenarios"
    else:
        r = dcf.calculate_dcf(data)
        scenarios.append(
            {
                "name": "Base",
                "probability": 1.0,
                "wacc": r["wacc"],
                "terminal_growth": r["terminal_growth"],
                "intrinsic_price": r["intrinsic_price"],
                "enterprise_value": r["enterprise_value"],
                "equity_value": r["equity_value"],
                "contribution": r["intrinsic_price"],
            }
        )
        intrinsic = r["intrinsic_price"]
        method = "DCF — FCFF, single scenario"

    gap = None
    if market_price:
        gap = (market_price - intrinsic) / intrinsic

    bs = data.get("balance_sheet", {})
    return {
        "symbol": symbol,
        "method": method,
        "intrinsic": intrinsic,
        "market_price": market_price,
        "snapshot_date": snapshot_date,
        "gap": gap,
        "scenarios": scenarios,
        "balance_sheet": bs,
        "base_revenue": dcf.parse_value(data.get("base_year", {}).get("revenue", 0))
        if data.get("base_year", {}).get("revenue")
        else None,
    }


# --------------------------------------------------------------------------- #
# HTML rendering
# --------------------------------------------------------------------------- #
def verdict(gap):
    """Human label for the market-vs-intrinsic gap (from a valuation lens)."""
    if gap is None:
        return ("No quote", "neutral")
    if gap <= -0.15:
        return ("Market well below model", "good")
    if gap < -0.03:
        return ("Market modestly below model", "good")
    if gap <= 0.03:
        return ("Roughly fair vs model", "neutral")
    if gap <= 0.15:
        return ("Market modestly above model", "warn")
    return ("Market well above model", "warn")


def render_report(ctx, date_str):
    sym = escape(ctx["symbol"])
    gap = ctx["gap"]
    v_label, v_class = verdict(gap)

    gap_str = "—" if gap is None else f"{gap * 100:+.1f}%"
    mkt_str = "—" if ctx["market_price"] is None else price(ctx["market_price"])
    snap = ctx["snapshot_date"] or "n/a"

    rows = ""
    for s in ctx["scenarios"]:
        rows += f"""        <tr>
          <td class="name">{escape(s['name'])}</td>
          <td class="num">{pct(s['probability'])}</td>
          <td class="num">{pct(s['wacc'])}</td>
          <td class="num">{pct(s['terminal_growth'])}</td>
          <td class="num strong">{price(s['intrinsic_price'])}</td>
          <td class="num">{price(s['contribution'])}</td>
        </tr>\n"""

    bs = ctx["balance_sheet"]
    bs_rows = ""
    for label, key in (("Cash", "cash"), ("Debt", "debt"), ("Diluted shares", "diluted_shares")):
        if key in bs:
            val = dcf.parse_value(bs[key])
            disp = money(val) if key != "diluted_shares" else f"{val / 1e9:,.3f}B"
            bs_rows += f"        <tr><td>{label}</td><td class='num'>{disp}</td></tr>\n"
    if ctx["base_revenue"]:
        bs_rows = (
            f"        <tr><td>Base-year revenue</td><td class='num'>{money(ctx['base_revenue'])}</td></tr>\n"
            + bs_rows
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{sym} DCF — {date_str} · too-simple-val</title>
<link rel="stylesheet" href="../../assets/style.css">
</head>
<body>
<main class="wrap">
  <p class="crumb"><a href="../../index.html">← All reports</a></p>

  <header class="rpt-head">
    <div>
      <h1>{sym} <span class="sub">valuation</span></h1>
      <p class="meta">{escape(ctx['method'])}</p>
    </div>
    <div class="date-badge">{date_str}</div>
  </header>

  <section class="cards">
    <div class="card">
      <div class="card-label">Intrinsic value / share</div>
      <div class="card-value">{price(ctx['intrinsic'])}</div>
      <div class="card-foot">probability-weighted</div>
    </div>
    <div class="card">
      <div class="card-label">Market price</div>
      <div class="card-value">{mkt_str}</div>
      <div class="card-foot">snapshot {escape(snap)}</div>
    </div>
    <div class="card {v_class}">
      <div class="card-label">Market vs model</div>
      <div class="card-value">{gap_str}</div>
      <div class="card-foot">{escape(v_label)}</div>
    </div>
  </section>

  <section>
    <h2>Scenario breakdown</h2>
    <div class="table-scroll">
      <table>
        <thead>
          <tr><th>Scenario</th><th class="num">Prob.</th><th class="num">WACC</th>
              <th class="num">Term. g</th><th class="num">Intrinsic</th><th class="num">Weighted</th></tr>
        </thead>
        <tbody>
{rows}        </tbody>
        <tfoot>
          <tr><td colspan="4" class="name">Probability-weighted intrinsic value</td>
              <td colspan="2" class="num strong">{price(ctx['intrinsic'])}</td></tr>
        </tfoot>
      </table>
    </div>
  </section>

  <section>
    <h2>Key inputs</h2>
    <div class="table-scroll">
      <table class="compact">
        <tbody>
{bs_rows}        </tbody>
      </table>
    </div>
  </section>

  <footer class="disclaimer">
    <p><strong>Not investment advice.</strong> A DCF is only as good as its
    assumptions. Figures are generated by the <code>dcf</code> skill from an input
    snapshot (market quote dated {escape(snap)}); they are a personal modeling
    exercise, not a recommendation to buy or sell any security.</p>
    <p class="gen">Generated {date_str} · too-simple-val</p>
  </footer>
</main>
</body>
</html>
"""


def render_index(entries):
    # Group by symbol, newest date first within each group.
    by_symbol = {}
    for e in entries:
        by_symbol.setdefault(e["symbol"], []).append(e)
    for lst in by_symbol.values():
        lst.sort(key=lambda e: e["date"], reverse=True)

    groups_html = ""
    for symbol in sorted(by_symbol):
        cards = ""
        for e in by_symbol[symbol]:
            gap = e.get("gap")
            _, v_class = verdict(gap)
            gap_str = "—" if gap is None else f"{gap * 100:+.1f}%"
            mkt = "—" if e.get("price") is None else price(e["price"])
            cards += f"""      <a class="report-row" href="{escape(e['path'])}">
        <span class="rr-date">{escape(e['date'])}</span>
        <span class="rr-method">{escape(e.get('method',''))}</span>
        <span class="rr-metric">intrinsic <b>{price(e['intrinsic'])}</b></span>
        <span class="rr-metric">market {mkt}</span>
        <span class="rr-gap {v_class}">{gap_str}</span>
      </a>\n"""
        groups_html += f"""    <section class="sym-group">
      <h2>{escape(symbol)}</h2>
{cards}    </section>\n"""

    if not entries:
        groups_html = '    <p class="empty">No reports yet.</p>\n'

    updated = dt.date.today().isoformat()
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>too-simple-val · valuation reports</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<main class="wrap">
  <header class="site-head">
    <h1>too&#8209;simple&#8209;val</h1>
    <p class="tagline">Dated, back-of-the-envelope intrinsic-value reports.
    One page per stock, per date.</p>
  </header>
{groups_html}
  <footer class="disclaimer">
    <p><strong>Not investment advice.</strong> These are personal modeling
    exercises, not recommendations. Last built {updated}.</p>
  </footer>
</main>
</body>
</html>
"""


STYLE = """:root {
  --bg: #ffffff;
  --panel: #f6f7f9;
  --border: #e4e7ec;
  --text: #1a1d23;
  --muted: #667085;
  --accent: #2f6feb;
  --good: #17864a;
  --good-bg: #e7f6ee;
  --warn: #b4540a;
  --warn-bg: #fdf0e6;
  --neutral: #475467;
  --neutral-bg: #eef1f5;
  --shadow: 0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.10);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1115; --panel: #171a21; --border: #262b34; --text: #e6e8ec;
    --muted: #98a2b3; --accent: #5a8dff;
    --good: #4ade80; --good-bg: #10261a; --warn: #f0a860; --warn-bg: #2a1c0e;
    --neutral: #cbd5e1; --neutral-bg: #1c2230;
    --shadow: none;
  }
}
:root[data-theme="dark"] {
  --bg: #0f1115; --panel: #171a21; --border: #262b34; --text: #e6e8ec;
  --muted: #98a2b3; --accent: #5a8dff;
  --good: #4ade80; --good-bg: #10261a; --warn: #f0a860; --warn-bg: #2a1c0e;
  --neutral: #cbd5e1; --neutral-bg: #1c2230; --shadow: none;
}
:root[data-theme="light"] {
  --bg: #ffffff; --panel: #f6f7f9; --border: #e4e7ec; --text: #1a1d23;
  --muted: #667085; --accent: #2f6feb;
  --good: #17864a; --good-bg: #e7f6ee; --warn: #b4540a; --warn-bg: #fdf0e6;
  --neutral: #475467; --neutral-bg: #eef1f5;
  --shadow: 0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.10);
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 860px; margin: 0 auto; padding: 40px 20px 80px; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
h1 { font-size: 30px; margin: 0; letter-spacing: -.02em; }
h2 { font-size: 18px; margin: 36px 0 12px; letter-spacing: -.01em; }
.sub { color: var(--muted); font-weight: 500; }
.crumb { margin: 0 0 20px; font-size: 14px; }

/* Landing */
.site-head { margin-bottom: 12px; }
.tagline { color: var(--muted); max-width: 46ch; }
.sym-group { margin-top: 28px; }
.report-row {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 18px;
  padding: 14px 16px; margin: 8px 0; border: 1px solid var(--border);
  border-radius: 10px; background: var(--panel); color: var(--text);
  box-shadow: var(--shadow);
}
.report-row:hover { text-decoration: none; border-color: var(--accent); }
.rr-date { font-variant-numeric: tabular-nums; font-weight: 600; min-width: 96px; }
.rr-method { color: var(--muted); font-size: 13px; flex: 1 1 200px; }
.rr-metric { font-size: 14px; color: var(--muted); }
.rr-metric b { color: var(--text); }
.rr-gap { font-weight: 700; font-variant-numeric: tabular-nums; padding: 2px 8px; border-radius: 999px; }
.empty { color: var(--muted); }

/* Report header */
.rpt-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.meta { color: var(--muted); margin: 6px 0 0; font-size: 14px; }
.date-badge {
  font-variant-numeric: tabular-nums; font-weight: 600; font-size: 14px;
  padding: 6px 12px; border: 1px solid var(--border); border-radius: 999px;
  background: var(--panel); white-space: nowrap;
}

/* Summary cards */
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 24px; }
.card {
  border: 1px solid var(--border); border-radius: 12px; padding: 16px;
  background: var(--panel); box-shadow: var(--shadow);
}
.card-label { font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.card-value { font-size: 26px; font-weight: 700; margin: 6px 0 2px; font-variant-numeric: tabular-nums; }
.card-foot { font-size: 12px; color: var(--muted); }
.card.good .card-value { color: var(--good); }
.card.warn .card-value { color: var(--warn); }

/* pill / card status colors */
.good { color: var(--good); background: var(--good-bg); }
.warn { color: var(--warn); background: var(--warn-bg); }
.neutral { color: var(--neutral); background: var(--neutral-bg); }
.card.good, .card.warn, .card.neutral { background: var(--panel); }

/* Tables */
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 15px; }
th, td { padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; }
thead th { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.name { font-weight: 600; }
.strong { font-weight: 700; }
tfoot td { border-top: 2px solid var(--border); border-bottom: none; font-weight: 600; }
table.compact td { padding: 8px 12px; }

/* Footer */
.disclaimer { margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--border);
  color: var(--muted); font-size: 13px; }
.disclaimer code { background: var(--panel); padding: 1px 5px; border-radius: 4px; }
.gen { margin-top: 8px; font-variant-numeric: tabular-nums; }

@media (max-width: 560px) {
  .cards { grid-template-columns: 1fr; }
  .rpt-head { flex-direction: column; }
}
"""


# --------------------------------------------------------------------------- #
# Manifest + orchestration
# --------------------------------------------------------------------------- #
def upsert_manifest(entry):
    entries = load_json(MANIFEST) or []
    entries = [e for e in entries if not (e["symbol"] == entry["symbol"] and e["date"] == entry["date"])]
    entries.append(entry)
    entries.sort(key=lambda e: (e["symbol"], e["date"]))
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST, "w") as f:
        json.dump(entries, f, indent=2)
    return entries


def main():
    ap = argparse.ArgumentParser(description="Generate a dated DCF report page.")
    ap.add_argument("symbol", help="Ticker, e.g. GOOGL (must have a DCF input file)")
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    args = ap.parse_args()

    symbol = args.symbol.upper()
    date_str = args.date

    ctx = compute(symbol)

    # Write report
    out_dir = REPORTS_DIR / symbol.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{date_str}.html"
    out_file.write_text(render_report(ctx, date_str))

    # Update manifest + rebuild index + ensure stylesheet
    entry = {
        "symbol": symbol,
        "date": date_str,
        "method": ctx["method"],
        "intrinsic": round(ctx["intrinsic"], 2),
        "price": round(ctx["market_price"], 2) if ctx["market_price"] else None,
        "gap": ctx["gap"],
        "snapshot_date": ctx["snapshot_date"],
        "path": f"reports/{symbol.lower()}/{date_str}.html",
    }
    entries = upsert_manifest(entry)
    (DOCS / "index.html").write_text(render_index(entries))
    (DOCS / "assets").mkdir(parents=True, exist_ok=True)
    (DOCS / "assets" / "style.css").write_text(STYLE)

    print(f"✓ Report:  {out_file.relative_to(ROOT)}")
    print(f"✓ Index:   {(DOCS / 'index.html').relative_to(ROOT)}")
    print(f"  {symbol}  intrinsic {price(ctx['intrinsic'])}  "
          f"market {price(ctx['market_price']) if ctx['market_price'] else '—'}  "
          f"gap {('%+.1f%%' % (ctx['gap']*100)) if ctx['gap'] is not None else '—'}")


if __name__ == "__main__":
    main()
