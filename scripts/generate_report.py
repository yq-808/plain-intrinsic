#!/usr/bin/env python3
"""Generate a dated valuation report page and refresh the site index.

Usage:
    python scripts/generate_report.py GOOGL                  # dated today
    python scripts/generate_report.py GOOGL --date 2026-07-13

This generator does **no** financial math. Each report page ships the DCF
*inputs* (the scenario JSON) embedded in the page; the valuation table and the
probability-weighted intrinsic value are computed in the browser by
docs/assets/dcf.js — a faithful port of the dcf skill's engine. The pages are
valuation-only: there is no market price anywhere.

Every report is a **static daily snapshot**: each run freezes its own copy of
the inputs (including the scenario probabilities) *and* their evaluation notes,
so a published report never changes when the shared reference JSON is later
refreshed for a new date.

Each run:
  1. reads skills/dcf/reference/inputs/<SYMBOL>.json (+ notes sidecar),
  2. writes docs/reports/<symbol>/<date>.json — the frozen data copy of record
     ({input, notes}), the report's own inspectable snapshot,
  3. writes docs/reports/<symbol>/<date>.html (inputs+notes embedded, math in JS),
  4. records the run (inputs + snapshot path) in docs/reports/manifest.json,
  5. rebuilds docs/index.html, which computes each report's intrinsic in JS.
"""

import argparse
import datetime as dt
import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DCF_REF = ROOT / "skills" / "dcf" / "reference"
DOCS = ROOT / "docs"
REPORTS_DIR = DOCS / "reports"
MANIFEST = REPORTS_DIR / "manifest.json"

# Site conventions applied by docs/assets/dcf.js (shown on each page).
CONVENTIONS = "Mid-year discounting convention. Valuation only — no live market price is used."


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
def load_json(path):
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def method_for(data):
    """Human label for the model type — derivable without running the DCF."""
    if data.get("scenarios"):
        return "DCF — FCFF, probability-weighted scenarios"
    return "DCF — FCFF, single scenario"


def embed_json(data):
    """Serialize input for safe embedding inside a <script> element."""
    return json.dumps(data).replace("</", "<\\/")


# --------------------------------------------------------------------------- #
# HTML rendering — pages carry inputs only; dcf.js fills the numbers.
# --------------------------------------------------------------------------- #
def render_report(symbol, data, date_str, notes=None, snapshot_name=None):
    sym = escape(symbol)
    method = escape(method_for(data))
    notes = notes or {}
    snapshot_name = snapshot_name or f"{date_str}.json"

    drivers_section = ""
    if notes.get("drivers"):
        drivers_section = """
  <section>
    <h2>Assumptions &amp; how defensible</h2>
    <div id="dcf-drivers"></div>
  </section>
"""

    consensus_section = ""
    if data.get("consensus"):
        consensus_section = """
  <section>
    <h2>Street consensus — same engine</h2>
    <p class="meta">Analyst-consensus forecast run through the same DCF, for comparison — not part of the probability-weighted value above.</p>
    <div id="dcf-consensus"></div>
  </section>
"""

    wacc_section = ""
    if data.get("wacc_sensitivity"):
        wacc_section = """
  <section>
    <h2>Discount-rate sensitivity</h2>
    <p class="meta">Each scenario's intrinsic value at a range of uniform discount rates, holding all cash-flow assumptions fixed. Terminal value dominates, so WACC is the single biggest swing factor.</p>
    <div id="dcf-wacc"></div>
  </section>
"""

    buyback_section = ""
    if data.get("buyback"):
        buyback_section = """
  <section>
    <h2>Buyback &amp; share count</h2>
    <p class="meta">How the per-share figure moves as the share count shrinks — shown for completeness, with an important caveat below.</p>
    <div id="dcf-buyback"></div>
  </section>
"""

    notes_script = ""
    if notes:
        notes_script = f'\n<script type="application/json" id="dcf-notes">{embed_json(notes)}</script>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{sym} valuation — {date_str} · daily-intrinsic</title>
<link rel="stylesheet" href="../../assets/style.css">
</head>
<body>
<main class="wrap">
  <p class="crumb"><a href="../../index.html">← All reports</a></p>

  <header class="rpt-head">
    <div>
      <h1>{sym} <span class="sub">valuation</span></h1>
      <p class="meta" id="dcf-method">{method}</p>
    </div>
    <div class="date-badge">{date_str}</div>
  </header>

  <section>
    <h2>Scenario breakdown</h2>
    <div class="table-scroll">
      <table>
        <thead>
          <tr><th>Scenario</th><th class="num">Prob.</th><th class="num">WACC</th>
              <th class="num">Term. g</th><th class="num">Intrinsic</th><th class="num">Weighted</th></tr>
        </thead>
        <tbody id="dcf-scenario-rows"></tbody>
        <tfoot>
          <tr><td colspan="4" class="name">Probability-weighted intrinsic value</td>
              <td colspan="2" class="num strong" id="dcf-weighted">…</td></tr>
        </tfoot>
      </table>
    </div>
    <noscript><p class="meta">This report computes its valuation in the browser;
    enable JavaScript to see the numbers.</p></noscript>
  </section>
{consensus_section}{wacc_section}{buyback_section}{drivers_section}
  <section>
    <h2>Key inputs</h2>
    <div class="table-scroll">
      <table class="compact">
        <tbody id="dcf-key-inputs"></tbody>
      </table>
    </div>
  </section>

  <footer class="disclaimer">
    <p><strong>Not investment advice.</strong> A DCF is only as good as its
    assumptions. The valuation is computed in your browser from an embedded input
    snapshot using the <code>dcf</code> engine; it is a personal modeling
    exercise, not a recommendation to buy or sell any security.</p>
    <p class="meta">{escape(CONVENTIONS)}</p>
    <p class="snapshot">This report is a frozen daily snapshot. →
    <a href="{escape(snapshot_name)}">Inputs, probabilities &amp; evaluation behind this page</a></p>
    <p class="gen">Generated {date_str} · daily-intrinsic</p>
  </footer>
</main>
<script type="application/json" id="dcf-input">{embed_json(data)}</script>{notes_script}
<script src="../../assets/dcf.js"></script>
</body>
</html>
"""


def render_index(entries):
    updated = dt.date.today().isoformat()
    manifest_json = embed_json(entries)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>daily-intrinsic · valuation reports</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<main class="wrap">
  <header class="site-head">
    <h1>daily&#8209;intrinsic</h1>
    <p class="tagline">Dated, back-of-the-envelope intrinsic-value reports.
    One page per stock, per date — each a frozen daily snapshot. Valuation only —
    no market price.</p>
  </header>

  <div id="dcf-index"></div>
  <noscript><p class="empty">Enable JavaScript to list reports and their
  intrinsic values.</p></noscript>

  <footer class="disclaimer">
    <p><strong>Not investment advice.</strong> These are personal modeling
    exercises, not recommendations. Last built {updated}.</p>
  </footer>
</main>
<script type="application/json" id="dcf-manifest">{manifest_json}</script>
<script src="assets/dcf.js"></script>
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
  --shadow: 0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.10);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1115; --panel: #171a21; --border: #262b34; --text: #e6e8ec;
    --muted: #98a2b3; --accent: #5a8dff; --shadow: none;
  }
}
:root[data-theme="dark"] {
  --bg: #0f1115; --panel: #171a21; --border: #262b34; --text: #e6e8ec;
  --muted: #98a2b3; --accent: #5a8dff; --shadow: none;
}
:root[data-theme="light"] {
  --bg: #ffffff; --panel: #f6f7f9; --border: #e4e7ec; --text: #1a1d23;
  --muted: #667085; --accent: #2f6feb;
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
.tagline { color: var(--muted); max-width: 52ch; }
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
.rr-metric b { color: var(--text); font-variant-numeric: tabular-nums; }
.empty { color: var(--muted); }

/* Report header */
.rpt-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.meta { color: var(--muted); margin: 6px 0 0; font-size: 14px; }
.date-badge {
  font-variant-numeric: tabular-nums; font-weight: 600; font-size: 14px;
  padding: 6px 12px; border: 1px solid var(--border); border-radius: 999px;
  background: var(--panel); white-space: nowrap;
}

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

/* Consensus cross-check */
.consensus-head { display: flex; align-items: baseline; justify-content: space-between;
  gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.consensus-label { color: var(--muted); font-size: 14px; }
.consensus-value { font-weight: 700; font-size: 24px; font-variant-numeric: tabular-nums; }
#dcf-consensus .read-note { display: block; margin: 12px 0 0; max-width: 72ch; }

/* verdict pill + plain-English note */
.verdict { display: inline-block; font-weight: 700; font-size: 12px;
  padding: 1px 8px; border-radius: 999px; background: var(--panel); border: 1px solid var(--border); }
.read-note { color: var(--muted); font-size: 13px; }

/* Assumptions: one table per input, three scenario rows (Bear/Base/Bull) */
.assump { padding: 18px 0; border-bottom: 1px solid var(--border); }
.assump:last-child { border-bottom: 0; }
.assump-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.assump-label { font-weight: 600; }
.assump .read-note { display: block; margin: 10px 0 0; max-width: 72ch; }
.reads { margin-top: 12px; }
.read-line { margin: 8px 0; font-size: 14px; line-height: 1.5; }
.read-key { font-weight: 600; }
.read-line .read-note { display: inline; margin: 0; }

/* Footer */
.disclaimer { margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--border);
  color: var(--muted); font-size: 13px; }
.disclaimer code { background: var(--panel); padding: 1px 5px; border-radius: 4px; }
.snapshot { margin-top: 12px; }
.gen { margin-top: 8px; font-variant-numeric: tabular-nums; }

@media (max-width: 560px) {
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
    ap = argparse.ArgumentParser(description="Generate a dated valuation report page.")
    ap.add_argument("symbol", help="Ticker, e.g. GOOGL (must have a DCF input file)")
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    args = ap.parse_args()

    symbol = args.symbol.upper()
    date_str = args.date

    input_path = DCF_REF / "inputs" / f"{symbol}.json"
    data = load_json(input_path)
    if data is None:
        sys.exit(f"Error: no DCF input file for {symbol} at {input_path}")

    # Optional commentary sidecar (drives the assumptions panel + the
    # scenario-probability evaluation).
    notes = load_json(DCF_REF / "notes" / f"{symbol}.json")

    out_dir = REPORTS_DIR / symbol.lower()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Freeze this report's own data copy: inputs (incl. scenario
    #    probabilities) + their evaluation notes. This is the snapshot of
    #    record — a published report never changes when the shared reference
    #    JSON is later refreshed for a new date.
    snapshot_name = f"{date_str}.json"
    snapshot = {
        "symbol": symbol,
        "date": date_str,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "conventions": CONVENTIONS,
        "input": data,
        "notes": notes,
    }
    snapshot_file = out_dir / snapshot_name
    snapshot_file.write_text(json.dumps(snapshot, indent=2))

    # 2. Write report page (inputs+notes embedded; math runs in the browser).
    out_file = out_dir / f"{date_str}.html"
    out_file.write_text(render_report(symbol, data, date_str, notes, snapshot_name))

    # 3. Update manifest + rebuild index + refresh stylesheet.
    entry = {
        "symbol": symbol,
        "date": date_str,
        "method": method_for(data),
        "path": f"reports/{symbol.lower()}/{date_str}.html",
        "snapshot": f"reports/{symbol.lower()}/{snapshot_name}",
        "input": data,
    }
    entries = upsert_manifest(entry)
    (DOCS / "index.html").write_text(render_index(entries))
    (DOCS / "assets").mkdir(parents=True, exist_ok=True)
    (DOCS / "assets" / "style.css").write_text(STYLE)

    print(f"✓ Snapshot: {snapshot_file.relative_to(ROOT)}")
    print(f"✓ Report:   {out_file.relative_to(ROOT)}")
    print(f"✓ Index:    {(DOCS / 'index.html').relative_to(ROOT)}")
    print(f"  {symbol}  {method_for(data)}  (intrinsic computed client-side)")


if __name__ == "__main__":
    main()
