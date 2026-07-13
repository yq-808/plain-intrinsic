#!/usr/bin/env python3
"""
Fetch financial data from Finnhub and generate DCF input file.

Data Sources (all from Finnhub free tier):
  - /stock/financials-reported: SEC filings (income statement, balance sheet, cash flow)
  - /stock/profile2: Company profile (total shares outstanding across all classes)
  - /stock/metric: Basic metrics (beta)

Usage:
    python fetch_inputs.py GOOGL

Requires:
    FINNHUB_API_KEY environment variable
    Get a free API key at: https://finnhub.io/register
"""

import json
import os
import sys
from pathlib import Path

import requests


FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def load_env_file():
    """Load environment variables from .env file."""
    # Look for .env in project root (3 levels up from this script)
    env_path = Path(__file__).parent.parent.parent.parent / ".env"

    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip().strip('"').strip("'")
                    os.environ[key.strip()] = value


def get_finnhub_key() -> str:
    """Get Finnhub API key from environment."""
    # Try to load from .env first
    load_env_file()

    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        print("Error: FINNHUB_API_KEY not found in environment or .env file")
        print("Add FINNHUB_API_KEY=your_key to .env file in project root")
        print("Get a free API key at: https://finnhub.io/register")
        sys.exit(1)
    return key


# =============================================================================
# Finnhub API Endpoints
# =============================================================================

def fetch_financials_reported(symbol: str, api_key: str) -> dict:
    """Fetch SEC filings (income statement, balance sheet, cash flow)."""
    url = f"{FINNHUB_BASE_URL}/stock/financials-reported?symbol={symbol}&freq=annual&token={api_key}"
    resp = requests.get(url, timeout=15)
    return resp.json()


def fetch_profile(symbol: str, api_key: str) -> dict:
    """Fetch company profile (includes total shares outstanding)."""
    url = f"{FINNHUB_BASE_URL}/stock/profile2?symbol={symbol}&token={api_key}"
    resp = requests.get(url, timeout=15)
    return resp.json()


def fetch_metrics(symbol: str, api_key: str) -> dict:
    """Fetch basic financials/metrics (includes beta)."""
    url = f"{FINNHUB_BASE_URL}/stock/metric?symbol={symbol}&metric=all&token={api_key}"
    resp = requests.get(url, timeout=15)
    return resp.json()


# =============================================================================
# Parsing Helpers
# =============================================================================

def parse_sec_report(report_items: list) -> dict:
    """Convert SEC report list format to dict keyed by concept."""
    return {item["concept"]: item["value"] for item in report_items if "concept" in item}


def get_value(data: dict, *keys, default=0) -> float:
    """Get first available value from multiple possible keys."""
    for key in keys:
        if key in data and data[key] is not None:
            return float(data[key])
    return default


def format_billions(value: float) -> str:
    """Format large numbers with B/M/K suffix."""
    abs_val = abs(value)
    if abs_val >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.1f}T"
    elif abs_val >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    elif abs_val >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    elif abs_val >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(int(value))


# =============================================================================
# Main Logic
# =============================================================================

def generate_dcf_inputs(symbol: str) -> dict:
    """Fetch all data from Finnhub and generate DCF input structure."""
    api_key = get_finnhub_key()

    print(f"Fetching data for {symbol} from Finnhub...")

    # Fetch all data from Finnhub
    print("  - SEC filings (financials-reported)...")
    financials = fetch_financials_reported(symbol, api_key)

    print("  - Company profile...")
    profile = fetch_profile(symbol, api_key)

    print("  - Basic metrics...")
    metrics = fetch_metrics(symbol, api_key)

    # Check for API errors
    if "error" in financials:
        print(f"Finnhub Error (financials): {financials['error']}")
        sys.exit(1)
    if "error" in profile:
        print(f"Finnhub Error (profile): {profile['error']}")
        sys.exit(1)

    # Get SEC filings data
    reports = financials.get("data", [])
    if not reports:
        print("Error: No SEC filings data available")
        sys.exit(1)

    # Get latest annual report (10-K)
    latest = reports[0]
    report = latest.get("report", {})

    # Parse SEC report sections
    ic = parse_sec_report(report.get("ic", []))  # Income statement
    bs = parse_sec_report(report.get("bs", []))  # Balance sheet
    cf = parse_sec_report(report.get("cf", []))  # Cash flow

    # Extract income statement metrics
    revenue = get_value(
        ic,
        "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap_Revenues",
        "us-gaap_SalesRevenueNet"
    )
    operating_income = get_value(
        ic,
        "us-gaap_OperatingIncomeLoss",
        "us-gaap_OperatingIncome"
    )

    # Calculate EBIT margin
    ebit_margin = operating_income / revenue if revenue > 0 else 0.0

    # Extract cash flow metrics
    depreciation = get_value(
        cf,
        "us-gaap_Depreciation",
        "us-gaap_DepreciationDepletionAndAmortization",
        "us-gaap_DepreciationAndAmortization"
    )
    capex = abs(get_value(
        cf,
        "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment",
        "us-gaap_CapitalExpendituresIncurredButNotYetPaid"
    ))

    # Calculate D&A and Capex as % of revenue
    da_percent = depreciation / revenue if revenue > 0 else 0.05
    capex_percent = capex / revenue if revenue > 0 else 0.10

    # Extract balance sheet items - Cash-like assets
    # Include: Cash & Equivalents + Short-term Investments + Long-term Marketable Securities
    cash_and_equivalents = get_value(
        bs,
        "us-gaap_CashAndCashEquivalentsAtCarryingValue"
    )
    short_term_investments = get_value(
        bs,
        "us-gaap_MarketableSecuritiesCurrent",
        "us-gaap_ShortTermInvestments",
        "us-gaap_AvailableForSaleSecuritiesCurrent"
    )
    long_term_investments = get_value(
        bs,
        "us-gaap_OtherLongTermInvestments",
        "us-gaap_MarketableSecuritiesNoncurrent",
        "us-gaap_LongTermInvestments",
        "us-gaap_AvailableForSaleSecuritiesNoncurrent"
    )
    # Total cash-like assets for DCF equity bridge
    cash = cash_and_equivalents + short_term_investments + long_term_investments

    # Get debt (long-term + short-term)
    long_term_debt = get_value(
        bs,
        "us-gaap_LongTermDebtAndCapitalLeaseObligations",
        "us-gaap_LongTermDebt",
        "us-gaap_LongTermDebtNoncurrent"
    )
    short_term_debt = get_value(
        bs,
        "us-gaap_ShortTermBorrowings",
        "us-gaap_DebtCurrent"
    )
    total_debt = long_term_debt + short_term_debt

    # Get current assets/liabilities for NWC
    current_assets = get_value(bs, "us-gaap_AssetsCurrent")
    current_liabilities = get_value(bs, "us-gaap_LiabilitiesCurrent")
    nwc = current_assets - current_liabilities
    nwc_percent = nwc / revenue if revenue > 0 else 0.02
    nwc_percent = max(0, min(nwc_percent, 0.15))  # Cap between 0% and 15%

    # Get shares outstanding from Finnhub profile (in millions, total for all share classes)
    shares_millions = profile.get("shareOutstanding", 0) or 0
    shares = shares_millions * 1_000_000  # Convert to actual shares

    # Get beta from Finnhub metrics
    metric_data = metrics.get("metric", {})
    beta = metric_data.get("beta", 1.0) or 1.0

    # Calculate historical growth rates from SEC filings
    growth_rates = [0.10, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03]  # Default
    if len(reports) >= 2:
        # Get previous year's revenue
        prev_report = reports[1].get("report", {})
        prev_ic = parse_sec_report(prev_report.get("ic", []))
        prev_revenue = get_value(
            prev_ic,
            "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap_Revenues",
            "us-gaap_SalesRevenueNet"
        )

        if prev_revenue > 0:
            yoy_growth = (revenue - prev_revenue) / prev_revenue
            # Create declining growth trajectory
            base_growth = min(max(yoy_growth, 0.02), 0.25)  # Cap between 2% and 25%
            growth_rates = []
            for i in range(7):
                rate = base_growth * (0.85 ** i)  # Decline by 15% each year
                growth_rates.append(round(max(rate, 0.02), 3))  # Floor at 2%

    # Build DCF input structure
    dcf_inputs = {
        "symbol": symbol,
        "base_year": {
            "revenue": format_billions(revenue),
            "ebit_margin": round(ebit_margin, 3),
            "da_percent": round(da_percent, 3),
            "capex_percent": round(capex_percent, 3),
            "nwc_percent": round(nwc_percent, 3)
        },
        "assumptions": {
            "tax_rate": 0.21,  # US corporate tax rate
            "growth_rates": growth_rates,
            "ebit_margins": [round(ebit_margin, 3)] * 7  # Assume stable margins
        },
        "wacc_inputs": {
            "risk_free_rate": 0.045,  # ~10-year Treasury yield
            "equity_risk_premium": 0.05,
            "beta": round(beta, 2),
            "cost_of_debt": 0.05,
            "debt_weight": 0.02,  # Default
            "equity_weight": 0.98
        },
        "terminal": {
            "growth_rate": 0.025  # Long-term GDP growth
        },
        "balance_sheet": {
            "cash": format_billions(cash),
            "debt": format_billions(total_debt),
            "diluted_shares": format_billions(shares)
        }
    }

    return dcf_inputs


def main():
    if len(sys.argv) < 2:
        print("Usage: python fetch_inputs.py SYMBOL")
        print("Example: python fetch_inputs.py GOOGL")
        sys.exit(1)

    symbol = sys.argv[1].upper()

    # Generate inputs
    dcf_inputs = generate_dcf_inputs(symbol)

    # Determine output path
    script_dir = Path(__file__).parent
    output_dir = script_dir.parent / "reference" / "inputs"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{symbol}.json"

    # Save to file
    with open(output_file, "w") as f:
        json.dump(dcf_inputs, f, indent=2)

    print(f"\nDCF inputs saved to: {output_file}")
    print("\n" + "=" * 60)
    print("GENERATED DCF INPUTS")
    print("=" * 60)
    print(json.dumps(dcf_inputs, indent=2))
    print("\n" + "=" * 60)
    print("Data Source: Finnhub (free tier)")
    print("  - SEC filings: /stock/financials-reported")
    print("  - Shares outstanding: /stock/profile2 (total across all classes)")
    print("  - Beta: /stock/metric")
    print("=" * 60)
    print("Note: Review and adjust the following assumptions:")
    print("  - growth_rates: Based on YoY revenue growth, may need adjustment")
    print("  - ebit_margins: Assumed stable, adjust for expected changes")
    print("  - wacc_inputs: Risk-free rate may need updating")
    print("  - terminal.growth_rate: Default 2.5%, adjust as needed")
    print("=" * 60)


if __name__ == "__main__":
    main()
