# too-simple-val

Dated, back-of-the-envelope **intrinsic-value reports** for stocks — one HTML
page per stock, per date, published as a static site via GitHub Pages.

The numbers come from two portable valuation skills vendored under
[`skills/`](skills/); a small generator turns their output into clean,
shareable web pages.

## Layout

```
too-simple-val/
├── skills/
│   ├── dcf/                     # DCF (FCFF) valuation skill + engine
│   └── megawatt-pe-valuation/   # Earnings × P/E model for power / AI-infra
├── scripts/
│   └── generate_report.py       # renders a dated HTML report + rebuilds the index
└── docs/                        # ← GitHub Pages site root (serve from main /docs)
    ├── index.html               # landing page, lists every report by stock & date
    ├── assets/style.css
    └── reports/
        ├── manifest.json        # machine-readable list of all reports
        └── googl/2026-07-13.html
```

## Generate a report

```bash
# defaults to today's date
python3 scripts/generate_report.py GOOGL

# or pin the date on the page
python3 scripts/generate_report.py GOOGL --date 2026-07-13
```

Each run recomputes the DCF for the symbol using the engine in
`skills/dcf/scripts/dcf_calculator.py`, writes
`docs/reports/<symbol>/<date>.html`, records it in
`docs/reports/manifest.json`, and rebuilds `docs/index.html`. To post a report
for a new date, just run the command again with a new `--date` and commit.

The symbol must have an input file at
`skills/dcf/reference/inputs/<SYMBOL>.json` (GOOGL, MSFT, AAPL are included).
Market quotes are read from `skills/dcf/reference/quotes/<SYMBOL>_quote.json`;
each page labels the quote's snapshot date. Refreshing quotes/news/filings uses
the skill's own `fetch_*.py` scripts and requires the relevant API keys
(`FINNHUB_API_KEY` etc.).

## Publishing with GitHub Pages

The repo is private for now. When you're ready to publish:

1. Repo **Settings → Pages**.
2. **Source:** *Deploy from a branch*.
3. **Branch:** `main`, **Folder:** `/docs`.

The site then lives at `https://<owner>.github.io/too-simple-val/`. (While the
repo is private, GitHub Pages requires a paid plan; making the repo public will
serve it for free.)

## Disclaimer

Not investment advice. These are personal modeling exercises — a DCF is only as
good as its assumptions — not recommendations to buy or sell any security.
