# DCF Valuation Skill

Professional DCF (Discounted Cash Flow) valuation model for stocks using FCFF (Free Cash Flow to Firm) methodology with real-time market reality checks.

## Features

- **Full DCF Valuation**: forecast projection with terminal value calculation
- **Probability-Weighted Scenarios**: Bear/Base/Bull in one JSON with weighted intrinsic value
- **WACC Calculation**: Using CAPM for cost of equity
- **Sensitivity Analysis**: Grid showing intrinsic value at different WACC and growth rates
- **Market Reality Check**: Compare DCF results with current market price, analyst consensus, and news
- **Automated Data Fetching**: Pull financial data directly from Finnhub API

## Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# Set up Finnhub API key (required for market reality check and automated data fetching)
export FINNHUB_API_KEY="your_api_key_here"
```

Get a free Finnhub API key at: https://finnhub.io/register

## Usage

### Option 1: Using the Skill Command

```bash
/dcf GOOGL
```

This will:
1. Check for existing input file (does NOT auto-update)
2. Run DCF calculation if inputs exist
3. Display DCF valuation report (single-scenario) or probability-weighted summary + scenario details (multi-scenario)

**Market reality check is opt-in:**
- Skill will NOT automatically fetch market data
- To get market reality, explicitly ask: "check market reality" or "compare with current market"
- If saved market data exists, it will be displayed (check timestamp)
- Fresh data is only fetched when explicitly requested

### Option 2: Manual Workflow

```bash
# Step 1: Fetch financial data from Finnhub (optional - only if needed)
python scripts/fetch_inputs.py GOOGL

# Step 2: Edit the input file to adjust assumptions
# File location: reference/inputs/GOOGL.json

# Step 3: Run DCF calculation
python scripts/dcf_calculator.py reference/inputs/GOOGL.json

# Step 4: Check current market quote (if exists)
cat reference/quotes/GOOGL_quote.json

# Step 5: Fetch fresh market quote (only when needed)
python scripts/fetch_quotes.py GOOGL
```

### File Structure

```
.claude/skills/dcf/
├── reference/           # All reference data
│   ├── inputs/          # DCF model inputs (manual or fetched)
│   │   ├── GOOGL.json
│   │   └── AAPL.json
│   ├── quotes/          # Real-time stock quotes
│   │   ├── GOOGL_quote.json
│   │   └── AAPL_quote.json
│   ├── news/            # Company news
│   │   ├── GOOGL_news_7d.json
│   │   └── AAPL_news_7d.json
│   └── sec_filings/     # Downloaded SEC reports (10-K, 10-Q)
│       ├── GOOGL/
│       │   ├── GOOGL_filings_index.json
│       │   ├── GOOGL_10-K_2023-02-03_*.html
│       │   └── GOOGL_10-K_2022-02-02_*.html
│       └── AAPL/
│           └── ...
└── scripts/             # All scripts
    ├── dcf_calculator.py
    ├── fetch_inputs.py
    ├── fetch_quotes.py
    ├── fetch_news.py
    └── fetch_sec_filings.py
```

## Input File Format

The calculator supports two modes:
- **Single-scenario**: one set of assumptions (legacy mode)
- **Multi-scenario**: `scenarios` array with probabilities and per-scenario overrides

```json
{
  "symbol": "GOOGL",
  "base_year": {
    "revenue": "350B",
    "ebit_margin": 0.28,
    "da_percent": 0.05,
    "capex_percent": 0.10,
    "nwc_percent": 0.02
  },
  "assumptions": {
    "tax_rate": 0.21,
    "growth_rates": [0.12, 0.10, 0.08, 0.07, 0.06, 0.05, 0.04],
    "ebit_margins": [0.28, 0.28, 0.29, 0.29, 0.30, 0.30, 0.30]
  },
  "wacc_inputs": {
    "risk_free_rate": 0.045,
    "equity_risk_premium": 0.05,
    "beta": 1.05,
    "cost_of_debt": 0.05,
    "debt_weight": 0.02,
    "equity_weight": 0.98
  },
  "terminal": {
    "growth_rate": 0.025
  },
  "balance_sheet": {
    "cash": "120B",
    "debt": "15B",
    "diluted_shares": "12.5B"
  }
}
```

### Multi-Scenario Example (Probability-Weighted)

```json
{
  "symbol": "GOOGL",
  "base_year": {
    "revenue": "350B",
    "ebit_margin": 0.32,
    "da_percent": 0.05,
    "capex_percent": 0.15,
    "nwc_percent": 0.15
  },
  "assumptions": {
    "tax_rate": 0.21,
    "growth_rates": [0.11, 0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.03],
    "ebit_margins": [0.32, 0.322, 0.324, 0.326, 0.328, 0.33, 0.333, 0.336, 0.338, 0.34]
  },
  "wacc_inputs": {
    "risk_free_rate": 0.041,
    "equity_risk_premium": 0.042,
    "beta": 1.10,
    "cost_of_debt": 0.048,
    "debt_weight": 0.03,
    "equity_weight": 0.97
  },
  "terminal": {"growth_rate": 0.03},
  "balance_sheet": {
    "cash": "195.53B",
    "debt": "46.547B",
    "diluted_shares": "12.097B"
  },
  "scenarios": [
    {"name": "Bear", "probability": 0.25, "terminal": {"growth_rate": 0.025}, "wacc_inputs": {"beta": 1.15}},
    {"name": "Base", "probability": 0.50},
    {"name": "Bull", "probability": 0.25, "terminal": {"growth_rate": 0.035}, "wacc_inputs": {"beta": 1.00}}
  ]
}
```

Probability rules:
- Sum can be `1.0` (e.g., `0.25 + 0.50 + 0.25`) or `100` (e.g., `25 + 50 + 25`)
- Scenario fields are merged over top-level defaults

### Value Formats

- **Large numbers**: Use suffixes K (thousands), M (millions), B (billions), T (trillions)
- **Percentages**: Use decimals (0.28 = 28%, 0.05 = 5%)

## Scripts

### dcf_calculator.py

Core DCF valuation engine that calculates intrinsic value using FCFF methodology.

**Output includes:**
- Probability-weighted scenario summary table (when `scenarios` exists)
- Full detailed report for each scenario (when `scenarios` exists)
- WACC calculation breakdown
- Forecast table (Revenue, EBIT, NOPAT, D&A, Capex, NWC, FCFF)
- Discounting to present value
- Terminal value calculation (Gordon Growth Model)
- Valuation bridge (Enterprise Value → Equity Value → Price per Share)
- Sensitivity analysis grid

### fetch_inputs.py

Automated data fetcher that pulls financial data from Finnhub API.

**Fetches:**
- SEC filings (income statement, balance sheet, cash flow)
- Company profile (shares outstanding)
- Basic metrics (beta)
- Historical growth rates

**Generates:** Pre-filled input JSON file with calculated metrics.

### fetch_quotes.py

Fetch real-time stock quotes from Finnhub.

**Usage:**
```bash
python scripts/fetch_quotes.py GOOGL
python scripts/fetch_quotes.py AAPL MSFT TSLA  # Multiple symbols
```

**Provides:**
- Current price, change, percent change
- Day high/low, open, previous close
- Saves to `reference/quotes/{SYMBOL}_quote.json`

### fetch_news.py

Fetch company news headlines and summaries.

**Usage:**
```bash
python scripts/fetch_news.py GOOGL
python scripts/fetch_news.py GOOGL --days 30  # Last 30 days
```

**Provides:**
- Recent news headlines (past 7 days by default)
- Article dates, headlines, summaries, URLs
- Saves to `reference/news/{SYMBOL}_news_{DAYS}d.json`


### fetch_sec_filings.py

Download complete SEC filings (10-K annual reports, 10-Q quarterly reports) from SEC.gov.

**Usage:**
```bash
# Download 3 most recent 10-K annual reports
python scripts/fetch_sec_filings.py GOOGL --form 10-K --limit 3

# Download 5 most recent 10-Q quarterly reports
python scripts/fetch_sec_filings.py AAPL --form 10-Q --limit 5

# Just fetch URLs without downloading
python scripts/fetch_sec_filings.py TSLA --form 10-K --no-download
```

**Features:**
- Fetches filing URLs from Finnhub API
- Downloads complete HTML reports from SEC.gov
- Saves to `reference/sec_filings/{SYMBOL}/` folder
- Creates index JSON file with all filing metadata
- Respects SEC.gov rate limits

## Key Formulas

| Formula | Description |
|---------|-------------|
| FCFF = NOPAT + D&A - Capex - ΔNWC | Free Cash Flow to Firm |
| NOPAT = EBIT × (1 - Tax Rate) | Net Operating Profit After Tax |
| WACC = We × Re + Wd × Rd × (1 - T) | Weighted Average Cost of Capital |
| Re = Rf + β × ERP | Cost of Equity (CAPM) |
| TV = FCFF_n × (1 + g) / (WACC - g) | Terminal Value (Gordon Growth) |
| EV = Σ PV(FCFF) + PV(TV) | Enterprise Value |
| Equity Value = EV + Cash - Debt | |
| Intrinsic Price = Equity Value / Shares | |

## Example Output

### DCF Valuation Report

```
╔════════════════════════════════════════════════════════════════════════════════════╗
║                         INTRINSIC VALUE PER SHARE:  $91.05                         ║
╚════════════════════════════════════════════════════════════════════════════════════╝
```

### Market Reality Check

```
╔════════════════════════════════════════════════════════════════════════════════════╗
║                          MARKET REALITY CHECK: GOOGL                               ║
╚════════════════════════════════════════════════════════════════════════════════════╝

┌────────────────────────────────────────────────────────────────────────────────────┐
│ DCF VALUATION GAP ANALYSIS                                                         │
├────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                    │
│  DCF Intrinsic Value:  $91.05                                                      │
│  Current Market Price: $175.50                                                     │
│  Valuation Gap:        -48.12%                                                     │
│                                                                                    │
│  ► Assessment: OVERVALUED (Market may be overpricing)                              │
│                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────┘
```

## Data Sources

- **DCF Inputs**: Finnhub API (SEC filings, company profile, metrics)
- **Quotes**: Finnhub API (real-time stock quotes) - Free tier
- **News**: Finnhub API (company news headlines & summaries) - Free tier
- **SEC Filings**: Finnhub API (filing URLs) + SEC.gov (complete reports)
- **Alternative**: Manual input from financial statements or Yahoo Finance

## Notes

- Free Finnhub API tier has rate limits (60 calls/minute)
- Premium endpoints (news sentiment, detailed estimates) require paid subscription
- DCF model is sensitive to assumptions - always review and adjust inputs
- Market reality check shows the gap between fundamental value and market perception

## Contributing

This skill is part of the open-invest project. See main project README for contribution guidelines.
