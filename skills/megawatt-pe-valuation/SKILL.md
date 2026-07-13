# Megawatt P/E Valuation Skill

name: megawatt-pe-valuation
description: Earnings × P/E valuation model based on MW (power) inputs for data center / AI infra businesses
argument-hint: [SYMBOL]

## Instructions

When invoked with `/megawatt-pe-valuation [SYMBOL]`:

### 1. Check Local Input File

```bash
ls -la .claude/skills/megawatt-pe-valuation/reference/inputs/{SYMBOL}.json 2>/dev/null
```

### 2. Handle Missing Inputs

If the input file does NOT exist, create a blank template:

```bash
python .claude/skills/megawatt-pe-valuation/scripts/create_template.py {SYMBOL}
```

Then ask the user to fill in required fields.

### 3. Run Valuation Calculation

```bash
python .claude/skills/megawatt-pe-valuation/scripts/mw_pe_calculator.py .claude/skills/megawatt-pe-valuation/reference/inputs/{SYMBOL}.json
```

**Display the COMPLETE output** - includes power -> revenue, earnings bridge, implied price, sensitivity table, and optional value ladder.

### 4. Interpretation Checklist

Provide short commentary on:
- **Load & Utilization**: IT load and effective utilization
- **Revenue Path**: GPU hourly vs revenue per MW
- **Earnings Drivers**: EBIT margin, SG&A, tax rate
- **Valuation Multiple**: P/E sensitivity vs MW sensitivity

## Input File Format

**Large numbers:** Use suffixes K/M/B/T (e.g., "138M")
**Percentages:** Accept decimals (0.35) or whole numbers (35)

```json
{
  "symbol": "IREN",
  "load": {
    "input_mode": "total",
    "total_load_mw": 1400,
    "it_load_mw": null,
    "pue": 1.5,
    "utilization": 0.85
  },
  "revenue": {
    "mode": "gpu_hourly",
    "gpus_per_mw": 120,
    "gpu_power_kw": null,
    "gpu_hourly_rate": 3.0,
    "revenue_per_mw": null,
    "hours_per_year": 8760
  },
  "earnings": {
    "ebit_margin": 0.35,
    "sga": "138M",
    "tax_rate": 0.21
  },
  "valuation": {
    "pe_multiple": 30,
    "diluted_shares": "654.6M"
  },
  "ladder": {
    "items": [
      { "name": "Canada base", "site_profit": "490M", "site_revenue": "1.50B" },
      { "name": "+ Horizon 1-4", "site_profit": "194M", "site_revenue": "1.94B" },
      { "name": "+ SW1 300MW", "site_profit": "672M", "site_revenue": "2.75B" }
    ]
  },
  "sensitivity": {
    "pe_range": [20, 25, 30, 35, 40],
    "mw_range": [300, 600, 900, 1200, 1400]
  }
}
```

### Revenue Modes

- **gpu_hourly**: Uses GPU count and hourly rate
  - GPUs per MW can be given directly (`gpus_per_mw`) or derived from GPU power (`gpu_power_kw`)
- **revenue_per_mw**: Uses `$ / MW-year` directly

### MW Range Interpretation

- If `input_mode = "total"`, `mw_range` uses **Total Load (MW)**
- If `input_mode = "direct"`, `mw_range` uses **IT Load (MW)**

### Optional Value Ladder

Use `ladder.items` to show how valuation changes as sites are added. Each item is an incremental site contribution:

- `site_profit`: earnings before tax & SG&A for that site (same unit as model, e.g. "210M")
- `site_revenue` (optional): if provided, the ladder prints implied EBIT margin

The ladder uses **base** SG&A, tax rate, P/E, and share count from the input file.

## Key Formulas

| Formula | Description |
|---------|-------------|
| IT Load = Total Load / PUE | Converts total site load to IT load |
| Effective IT Load = IT Load × Utilization | Apply utilization factor |
| Revenue (GPU) = GPUs × Rate × 8,760 | Annual revenue from GPU-hours |
| Revenue (MW) = Effective IT Load × Revenue per MW | Annual revenue from MW pricing |
| EBIT = Revenue × EBIT Margin | Operating profit |
| Net Income = (EBIT − SG&A) × (1 − Tax Rate) | Earnings after tax |
| Market Cap = Net Income × P/E | Valuation multiple |
| Price = Market Cap / Shares | Implied share price |
