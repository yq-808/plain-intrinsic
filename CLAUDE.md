# daily-val — project rules

A static site of dated, valuation-only reports: one HTML page per stock, per
date, published via GitHub Pages from `main` `/docs`.

## Two valuation methods, one pipeline

Each report's input carries a **method**; the generator and the shared landing
page dispatch on it. Same snapshot rules, same "generator does no math", same
"valuation only — no market price" for both.

- **DCF** (default, no `method` field) — FCFF, port in `docs/assets/dcf.js`,
  inputs under `skills/dcf/reference/`. For durable compounders.
- **Relative comps** (`"method": "comps"`) — peer/re-rating multiples (P/E,
  EV/EBITDA, P/B, EV/Sales) on a forward metric, port in `docs/assets/comps.js`,
  inputs under `skills/relative-comps/reference/`. For cyclicals / "new-paradigm"
  re-ratings where a smooth FCFF stream is a poor fit (e.g. MU).

The generator resolves `<SYM>.json` from either reference root; the input's
`method` selects the engine, the page template, and the conventions line.

## Core principle: reports are static daily snapshots

**Every generated report is a frozen, self-contained copy of its own data on the
day it was generated.** It is never recomputed from live data, and it must not
change when the shared reference JSON is later updated.

- The frozen copy of record for each report is `docs/reports/<symbol>/<date>.json`
  = `{ symbol, date, generated, conventions, input, notes }`. It carries the full
  inputs (including `scenarios[].probability`) **and** the evaluation notes
  (including the read on the probabilities). The same data is embedded in the
  report HTML so the page is self-contained.
- `skills/<method>/reference/inputs/<SYM>.json` and `.../notes/<SYM>.json`
  (`<method>` = `dcf` or `relative-comps`) are **mutable working drafts**. Edit
  them to prepare the *next* date's report, then run the generator to freeze a new
  snapshot. Editing them does not — and must not — retroactively alter
  already-published reports.

### Do / Don't
- **Do** produce a new report by editing the reference JSON and running
  `python3 scripts/generate_report.py <SYM> --date <YYYY-MM-DD>`.
- **Don't** hand-edit files under `docs/reports/<symbol>/` to change a past
  report's numbers. A published snapshot is immutable.
- **Exception:** a one-off, content-neutral migration across all reports (e.g. a
  site-wide rebrand or a template change that leaves every intrinsic value
  identical) may regenerate existing dates. Anything that would change a past
  report's *valuation* is not allowed.

## Conventions
- The generator does **no** financial math; all valuation runs client-side in
  the method's engine — `docs/assets/dcf.js` (port of
  `skills/dcf/scripts/dcf_calculator.py`, mid-year discounting) or
  `docs/assets/comps.js` (port of
  `skills/relative-comps/scripts/comps_calculator.py`, peer multiples). The
  landing page loads both and headlines each report with its own engine.
- Pages are **valuation only** — never add a live market price. For comps this
  means no current price, no upside/%-to-target, and no sell-side price targets;
  peer *multiples* and forward fundamentals are inputs, not a market price.
- Each input's evaluation lives in the notes `drivers[]` array; the `probability`
  driver is a first-class input and every probability-weighted report should
  carry an honest read on how good its scenario weights are.
