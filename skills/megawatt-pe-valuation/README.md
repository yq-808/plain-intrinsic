# Megawatt P/E Valuation Skill

Earnings × P/E valuation model driven by MW (power) inputs for data center / AI infrastructure businesses.

## Features

- **Power -> Revenue Bridge**: MW / PUE / utilization into revenue
- **Earnings Bridge**: EBIT -> Net Income
- **Multiple Valuation**: Net Income × P/E
- **Sensitivity Table**: P/E × MW grid for implied price
- **Value Ladder**: Optional cumulative valuation as sites are added

## Installation

```bash
# No external dependencies
pip install -r requirements.txt
```

## Usage

### Option 1: Using the Skill Command

```bash
/megawatt-pe-valuation IREN
```

This will:
1. Check for an input file
2. Create a template if missing
3. Run the valuation calculator
4. Display the full report and sensitivity table

### Option 2: Manual Workflow

```bash
# Step 1: Create a template input
python scripts/create_template.py IREN

# Step 2: Edit the input file to set assumptions
# File location: reference/inputs/IREN.json

# Step 3: Run the valuation
python scripts/mw_pe_calculator.py reference/inputs/IREN.json
```

### File Structure

```
.claude/skills/megawatt-pe-valuation/
├── reference/
│   ├── inputs/            # Input files per symbol
│   ├── quotes/            # (unused) reserved for future
│   ├── news/              # (unused) reserved for future
│   └── sec_filings/        # (unused) reserved for future
└── scripts/
    ├── mw_pe_calculator.py
    └── create_template.py
```

## Input File Format

See `SKILL.md` for full schema and examples.

Example input file:
`reference/inputs/EXAMPLE.json`
`reference/inputs/IREN_LADDER.json`
