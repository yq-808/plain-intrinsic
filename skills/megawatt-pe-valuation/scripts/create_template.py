#!/usr/bin/env python3
"""
Create a blank input template for Megawatt P/E Valuation.

Usage:
    python create_template.py <SYMBOL>
"""

import json
import sys
from pathlib import Path


TEMPLATE = {
    "symbol": None,
    "load": {
        "input_mode": "total",
        "total_load_mw": None,
        "it_load_mw": None,
        "pue": None,
        "utilization": None
    },
    "revenue": {
        "mode": "gpu_hourly",
        "gpus_per_mw": None,
        "gpu_power_kw": None,
        "gpu_hourly_rate": None,
        "revenue_per_mw": None,
        "hours_per_year": 8760
    },
    "earnings": {
        "ebit_margin": None,
        "sga": None,
        "tax_rate": None
    },
    "valuation": {
        "pe_multiple": None,
        "diluted_shares": None
    },
    "sensitivity": {
        "pe_range": [20, 25, 30, 35, 40],
        "mw_range": [300, 600, 900, 1200, 1400]
    }
}


def main():
    if len(sys.argv) < 2:
        print("Usage: python create_template.py <SYMBOL>")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    output_dir = Path(__file__).resolve().parents[1] / "reference" / "inputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{symbol}.json"

    if output_file.exists():
        print(f"Error: Input file already exists: {output_file}")
        sys.exit(1)

    data = dict(TEMPLATE)
    data["symbol"] = symbol

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Created template: {output_file}")


if __name__ == "__main__":
    main()
