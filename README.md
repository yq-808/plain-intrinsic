# daily-intrinsic

Dated, back-of-the-envelope **intrinsic-value reports** for stocks — one HTML
page per stock, per date, published as a static site via GitHub Pages.

Each report is **valuation only** — no market price. The page ships the DCF
*inputs* and computes the intrinsic value in your browser, so the numbers on the
page are always a live function of the assumptions it carries.

## Every report is a frozen daily snapshot

The whole point of the name: **each report is a static, self-contained copy of
its own data on the day it was generated.** A published report never changes when
the shared reference JSON is later refreshed. Concretely, each run freezes:

- the **inputs** — base-year facts, per-scenario assumptions, and the **scenario
  probabilities**; and
- the **evaluation notes** — the plain-English "how defensible" read on every
  input, *including the read on the probabilities themselves*.

Both are written to a snapshot file, `docs/reports/<symbol>/<date>.json`
(`{ input, notes }`), and embedded into the report HTML. The reference files
under `skills/dcf/reference/` are just the mutable working drafts you edit before
generating tomorrow's report; the snapshot is the copy of record.

## Layout

```
daily-intrinsic/
├── CLAUDE.md                    # project rules (reports are static daily snapshots)
├── skills/
│   ├── dcf/                     # DCF (FCFF) valuation skill + engine
│   │   └── reference/
│   │       ├── inputs/<SYM>.json   # working-draft inputs (mutable)
│   │       └── notes/<SYM>.json    # working-draft evaluation notes (mutable)
│   └── megawatt-pe-valuation/   # Earnings × P/E model for power / AI-infra
├── scripts/
│   └── generate_report.py       # freezes a dated snapshot + page, rebuilds the index
└── docs/                        # ← GitHub Pages site root (serve from main /docs)
    ├── index.html               # landing page, lists every report by stock & date
    ├── assets/
    │   ├── style.css
    │   └── dcf.js               # client-side DCF engine (port of the dcf skill)
    └── reports/
        ├── manifest.json        # reports + their embedded inputs + snapshot paths
        └── <symbol>/
            ├── <date>.json      # frozen data copy of record ({ input, notes })
            └── <date>.html      # the report page (inputs+notes embedded, math in JS)
```

## Generate a report

```bash
# defaults to today's date
python3 scripts/generate_report.py AAPL

# or pin the date on the page
python3 scripts/generate_report.py AAPL --date 2026-07-15
```

The generator does **no** financial math. Each run freezes the symbol's input
JSON *and* its evaluation notes into `docs/reports/<symbol>/<date>.json`, embeds
the same data into `docs/reports/<symbol>/<date>.html`, records the run in
`docs/reports/manifest.json`, and rebuilds `docs/index.html`. The valuation table
and the probability-weighted intrinsic value are computed in the browser by
[`docs/assets/dcf.js`](docs/assets/dcf.js) — a faithful port of the `dcf` skill's
engine (`skills/dcf/scripts/dcf_calculator.py`). To post a report for a new date,
run the command again with a new `--date` and commit.

The symbol must have an input file at
`skills/dcf/reference/inputs/<SYMBOL>.json` (GOOGL, MSFT, AAPL are included), and
optionally an evaluation sidecar at
`skills/dcf/reference/notes/<SYMBOL>.json`. Refreshing the underlying financials
uses the skill's own `fetch_*.py` scripts and requires an API key
(`FINNHUB_API_KEY` in a gitignored `.env`).

## Publishing with GitHub Pages

The repo is **public** and GitHub Pages serves from `main` `/docs`, so the live
site is:

**https://yq-808.github.io/daily-intrinsic/**

Pushing to `main` redeploys it automatically.

## Disclaimer

Not investment advice. These are personal modeling exercises — a DCF is only as
good as its assumptions — not recommendations to buy or sell any security.
