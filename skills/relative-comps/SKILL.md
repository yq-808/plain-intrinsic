# Relative Valuation (Peer Multiples) Skill

name: relative-comps
description: Relative valuation via peer/re-rating multiples (P/E, EV/EBITDA, P/B, EV/Sales) — for cyclical or "new-paradigm" businesses where a smooth FCFF DCF is a poor fit
argument-hint: [SYMBOL]

## When to use this instead of the DCF skill

Use relative-comps for **cyclical, commodity, or early-supercycle** businesses
where value is a forward-earnings × peer-multiple story rather than a smooth
mid-cycle free-cash-flow stream — memory (MU), commodities, deep cyclicals, or a
name being re-rated into a "new paradigm" (e.g. an AI-infrastructure beneficiary)
where the honest comparison set is *today's* peer multiples, not the stock's own
history. For durable compounders with predictable cash flows, use the `dcf` skill.

## Method (what pros do)

1. **Anchor a forward metric** (a target fiscal year, e.g. FY2027): EPS, EBITDA,
   revenue, and book value per share.
2. **Apply a peer / re-rating multiple** per metric:
   - `pe`  → price = EPS × P/E                                (equity multiple)
   - `pb`  → price = BVPS × P/B                               (equity multiple)
   - `ev_ebitda` → EV = EBITDA × mult; price = (EV + net cash) / shares
   - `ev_sales`  → EV = Revenue × mult; price = (EV + net cash) / shares
3. **Cross-check across multiples** — take the equal-weight blend and a "core"
   subset (the multiples that anchor best), and show the min–max range.
4. **Scenario-weight** bear / base / bull, jointly varying the metric *and* the
   multiple, then probability-weight for a single fair value.

The multiples are peer-anchored and stable; the forward **metric** is usually the
real swing factor, so the notes must carry an honest read on consensus dispersion.

## Run the calculation (parity oracle)

```bash
python3 skills/relative-comps/scripts/comps_calculator.py skills/relative-comps/reference/inputs/{SYMBOL}.json
```

This is the non-browser reference implementation of `docs/assets/comps.js`; the
two must agree. To publish a dated report, run the site generator, which embeds
the inputs and computes the numbers client-side in `comps.js`:

```bash
python3 scripts/generate_report.py {SYMBOL} --date {YYYY-MM-DD}
```

The generator resolves inputs from `skills/relative-comps/reference/inputs/` (and
notes from `.../notes/`) when the input's `"method"` is `"comps"`.

## Input file format

`skills/relative-comps/reference/inputs/{SYMBOL}.json`

**Large numbers:** K/M/B/T suffixes (e.g. `"150B"`). **Multiples:** plain numbers
(`8` = 8×). `net_cash` may be negative (net debt). Per-share metrics (`eps`,
`bvps`) are in dollars; firm-level metrics (`ebitda`, `revenue`) use suffixes.

```json
{
  "symbol": "MU",
  "method": "comps",
  "anchor": "FY2027",
  "peer_group": "Legacy memory (SK Hynix, Samsung)",
  "peers": [
    { "name": "SK Hynix", "pe": 5.4, "ev_ebitda": 7.7, "pb": 3.5, "ev_sales": 6.1 },
    { "name": "Samsung",  "pe": 4.9, "ev_ebitda": 8.6, "pb": 2.0, "ev_sales": 4.0 }
  ],
  "balance_sheet": { "net_cash": "25B", "diluted_shares": "1.13B" },
  "multiples": ["pe", "ev_ebitda", "pb", "ev_sales"],
  "core_multiples": ["pe", "ev_ebitda"],
  "scenarios": [
    {
      "name": "Base", "probability": 0.45,
      "fundamentals": { "eps": 115, "ebitda": "150B", "revenue": "195B", "bvps": 160 },
      "multiples": { "pe": 10, "ev_ebitda": 8, "pb": 4, "ev_sales": 5 }
    }
  ]
}
```

Rules:
- `scenarios` is a non-empty list; each carries `probability` (sum `1.0` or `100`).
- Top-level `fundamentals` / `multiples` / `balance_sheet` act as defaults; each
  scenario provides partial overrides and inherits the rest.
- `multiples` lists which multiples to compute and their display order.
  `core_multiples` is the subset used for the "core" cross-check (defaults to all).
- Only multiples present in a scenario's `multiples` map are computed.

## Notes (evaluation) file format

`skills/relative-comps/reference/notes/{SYMBOL}.json` — a `drivers[]` array of
`{ key, label, verdict, comment }`, one per input, each a plain-English "how
defensible" read. Recognized keys: `eps`, `ebitda`, `revenue`, `bvps`,
`mult_pe`, `mult_ev_ebitda`, `mult_pb`, `mult_ev_sales`, `net_cash`, `shares`,
`probability`. The `probability` read is a first-class input — every
probability-weighted report should carry an honest read on its scenario weights.

## Key formulas

| Formula | Description |
|---------|-------------|
| price = EPS × P/E | Equity multiple (earnings) |
| price = BVPS × P/B | Equity multiple (book value) |
| EV = EBITDA × (EV/EBITDA) | Enterprise value from operating cash proxy |
| EV = Revenue × (EV/Sales) | Enterprise value from sales |
| Equity = EV + Net cash | EV → equity bridge (net cash = cash − debt) |
| Price = Equity / Diluted shares | Per-share value for EV multiples |
| Blended = mean(all multiples) | Cross-check headline per scenario |
| Fair value = Σ probability × Blended | Probability-weighted fair value |

Valuation only — the page never shows a live market price.
