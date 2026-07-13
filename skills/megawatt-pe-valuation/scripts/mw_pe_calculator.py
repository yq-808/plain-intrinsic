#!/usr/bin/env python3
"""
Megawatt P/E Valuation Calculator

Usage:
    python mw_pe_calculator.py <input_json_file>
"""

import json
import sys
from pathlib import Path


HOURS_PER_YEAR = 24 * 365


def parse_value(value):
    """Parse value with unit suffix (K, M, B, T) into a number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip().upper().replace(",", "")
        multipliers = {
            'K': 1_000,
            'M': 1_000_000,
            'B': 1_000_000_000,
            'T': 1_000_000_000_000,
        }
        for suffix, mult in multipliers.items():
            if raw.endswith(suffix):
                return float(raw[:-1]) * mult
        return float(raw)
    return None


def to_decimal(value):
    """Allow percentages to be entered as decimals or whole numbers."""
    if value is None:
        return None
    v = float(value)
    if v > 1:
        return v / 100
    return v


def format_currency(value, decimals=1):
    """Format large numbers with B/M suffix."""
    if value is None:
        return "N/A"
    abs_val = abs(value)
    sign = "-" if value < 0 else ""
    if abs_val >= 1_000_000_000_000:
        return f"{sign}${abs_val / 1_000_000_000_000:.{decimals}f}T"
    if abs_val >= 1_000_000_000:
        return f"{sign}${abs_val / 1_000_000_000:.{decimals}f}B"
    if abs_val >= 1_000_000:
        return f"{sign}${abs_val / 1_000_000:.{decimals}f}M"
    if abs_val >= 1_000:
        return f"{sign}${abs_val / 1_000:.{decimals}f}K"
    return f"{sign}${abs_val:.{decimals}f}"


def format_percent(value):
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def format_number(value, decimals=2):
    if value is None:
        return "N/A"
    return f"{value:,.{decimals}f}"


def validate_inputs(data):
    missing = []

    load = data.get("load", {})
    input_mode = load.get("input_mode")
    if input_mode not in ("total", "direct"):
        missing.append("load.input_mode")

    if input_mode == "total":
        if load.get("total_load_mw") is None:
            missing.append("load.total_load_mw")
        if load.get("pue") is None:
            missing.append("load.pue")
    elif input_mode == "direct":
        if load.get("it_load_mw") is None:
            missing.append("load.it_load_mw")

    if load.get("utilization") is None:
        missing.append("load.utilization")

    revenue = data.get("revenue", {})
    revenue_mode = revenue.get("mode")
    if revenue_mode not in ("gpu_hourly", "revenue_per_mw"):
        missing.append("revenue.mode")
    if revenue_mode == "gpu_hourly":
        if revenue.get("gpu_hourly_rate") is None:
            missing.append("revenue.gpu_hourly_rate")
        if revenue.get("gpus_per_mw") is None and revenue.get("gpu_power_kw") is None:
            missing.append("revenue.gpus_per_mw or revenue.gpu_power_kw")
    elif revenue_mode == "revenue_per_mw":
        if revenue.get("revenue_per_mw") is None:
            missing.append("revenue.revenue_per_mw")

    earnings = data.get("earnings", {})
    for field in ["ebit_margin", "sga", "tax_rate"]:
        if earnings.get(field) is None:
            missing.append(f"earnings.{field}")

    valuation = data.get("valuation", {})
    for field in ["pe_multiple", "diluted_shares"]:
        if valuation.get(field) is None:
            missing.append(f"valuation.{field}")

    sensitivity = data.get("sensitivity", {})
    for field in ["pe_range", "mw_range"]:
        if sensitivity.get(field) is None:
            missing.append(f"sensitivity.{field}")

    return missing


def resolve_load(load, override_mw=None):
    input_mode = load.get("input_mode")
    pue = float(load.get("pue") or 1)

    if input_mode == "total":
        base_total = parse_value(load.get("total_load_mw"))
        total_load_mw = float(override_mw) if override_mw is not None else float(base_total)
        it_load_mw = total_load_mw / pue
    else:
        base_it = parse_value(load.get("it_load_mw"))
        it_load_mw = float(override_mw) if override_mw is not None else float(base_it)
        total_load_mw = it_load_mw * pue

    utilization = to_decimal(load.get("utilization"))
    effective_it_load = it_load_mw * utilization

    return {
        "input_mode": input_mode,
        "total_load_mw": total_load_mw,
        "it_load_mw": it_load_mw,
        "pue": pue,
        "utilization": utilization,
        "effective_it_load": effective_it_load,
    }


def resolve_revenue(revenue, effective_it_load):
    mode = revenue.get("mode")
    hours_per_year = revenue.get("hours_per_year") or HOURS_PER_YEAR
    hours_per_year = float(hours_per_year)

    if mode == "gpu_hourly":
        gpus_per_mw = revenue.get("gpus_per_mw")
        if gpus_per_mw is None:
            gpu_power_kw = float(revenue.get("gpu_power_kw"))
            gpus_per_mw = 1000 / gpu_power_kw
        else:
            gpus_per_mw = float(gpus_per_mw)

        gpu_count = effective_it_load * gpus_per_mw
        hourly_rate = float(revenue.get("gpu_hourly_rate"))
        revenue_value = gpu_count * hourly_rate * hours_per_year
        return {
            "mode": mode,
            "gpus_per_mw": gpus_per_mw,
            "gpu_count": gpu_count,
            "gpu_hourly_rate": hourly_rate,
            "hours_per_year": hours_per_year,
            "revenue": revenue_value,
        }

    revenue_per_mw = parse_value(revenue.get("revenue_per_mw"))
    revenue_value = effective_it_load * revenue_per_mw
    return {
        "mode": mode,
        "revenue_per_mw": revenue_per_mw,
        "revenue": revenue_value,
    }


def compute_case(data, override_mw=None, override_pe=None):
    load = resolve_load(data["load"], override_mw)
    revenue_data = resolve_revenue(data["revenue"], load["effective_it_load"])

    earnings = data["earnings"]
    ebit_margin = to_decimal(earnings["ebit_margin"])
    sga = parse_value(earnings["sga"])
    tax_rate = to_decimal(earnings["tax_rate"])

    revenue_value = revenue_data["revenue"]
    ebit = revenue_value * ebit_margin
    pre_tax = ebit - sga
    taxes = pre_tax * tax_rate
    net_income = pre_tax - taxes

    valuation = data["valuation"]
    pe_multiple = float(override_pe) if override_pe is not None else float(valuation["pe_multiple"])
    shares = parse_value(valuation["diluted_shares"])

    market_cap = net_income * pe_multiple
    price = market_cap / shares if shares else None

    return {
        "load": load,
        "revenue": revenue_data,
        "ebit_margin": ebit_margin,
        "sga": sga,
        "tax_rate": tax_rate,
        "revenue_value": revenue_value,
        "ebit": ebit,
        "pre_tax": pre_tax,
        "taxes": taxes,
        "net_income": net_income,
        "pe_multiple": pe_multiple,
        "shares": shares,
        "market_cap": market_cap,
        "price": price,
    }


def print_title(title, width):
    print("╔" + "═" * (width - 2) + "╗")
    print("║" + title.center(width - 2) + "║")
    print("╚" + "═" * (width - 2) + "╝")


def print_box(title, lines, width):
    print("┌" + "─" * (width - 2) + "┐")
    print("│" + f" {title}".ljust(width - 2) + "│")
    print("├" + "─" * (width - 2) + "┤")
    for line in lines:
        print("│" + line.ljust(width - 2) + "│")
    print("└" + "─" * (width - 2) + "┘")


def print_sensitivity(data, base_case, width):
    sensitivity = data["sensitivity"]
    mw_range = sensitivity["mw_range"]
    pe_range = sensitivity["pe_range"]

    base_load = base_case["load"]
    base_mw = base_load["total_load_mw"] if base_load["input_mode"] == "total" else base_load["it_load_mw"]
    base_pe = base_case["pe_multiple"]

    print("┌" + "─" * (width - 2) + "┐")
    print("│" + " SENSITIVITY ANALYSIS".ljust(width - 2) + "│")
    print("│" + " Share Price at different MW and P/E combinations".ljust(width - 2) + "│")
    print("├" + "─" * (width - 2) + "┤")

    header = f"│ {'MW \\ P/E':<10}"
    for pe in pe_range:
        header += f"{float(pe):>10.0f}"
    print(header.ljust(width - 1) + "│")
    print("├" + "─" * (width - 2) + "┤")

    for mw in mw_range:
        row = f"│ {format_number(float(mw), 0):>8}"
        for pe in pe_range:
            case = compute_case(data, override_mw=mw, override_pe=pe)
            price = case["price"]
            cell = "N/A" if price is None else f"${price:.2f}"
            is_base = abs(float(mw) - base_mw) < 1e-6 and abs(float(pe) - base_pe) < 1e-6
            if is_base:
                row += f" [{cell:>7}]"
            else:
                row += f"  {cell:>8}"
        print(row.ljust(width - 1) + "│")

    print("├" + "─" * (width - 2) + "┤")
    print("│" + "  [ ] = Base case (current assumptions)".ljust(width - 2) + "│")
    print("│" + f"  MW range uses input_mode='{base_load['input_mode']}'".ljust(width - 2) + "│")
    print("└" + "─" * (width - 2) + "┘")


def print_value_ladder(data, base_case, width):
    ladder = data.get("ladder")
    if not ladder:
        return

    items = ladder.get("items") or []
    if not items:
        return

    tax_rate = base_case["tax_rate"]
    sga = base_case["sga"]
    pe_multiple = base_case["pe_multiple"]
    shares = base_case["shares"]

    print()
    print("┌" + "─" * (width - 2) + "┐")
    print("│" + " VALUE LADDER".ljust(width - 2) + "│")
    print("│" + " Cumulative valuation as sites are added".ljust(width - 2) + "│")
    print("├" + "─" * (width - 2) + "┤")

    header = (
        "│ "
        + f"{'Step':<28}"
        + f"{'Cum Profit':>12}"
        + f"{'Net Income':>12}"
        + f"{'Price':>10}"
        + f"{'Delta':>10}"
    )
    print(header.ljust(width - 1) + "│")
    print("├" + "─" * (width - 2) + "┤")

    cumulative_profit = 0
    cumulative_revenue = 0
    prev_price = None

    for idx, item in enumerate(items, start=1):
        label = item.get("name") or f"Step {idx}"
        label = label[:28]

        site_profit = parse_value(item.get("site_profit")) or 0
        site_revenue = parse_value(item.get("site_revenue")) if item.get("site_revenue") is not None else None

        cumulative_profit += site_profit
        if site_revenue is not None:
            cumulative_revenue += site_revenue

        pre_tax = cumulative_profit - sga
        taxes = pre_tax * tax_rate
        net_income = pre_tax - taxes
        market_cap = net_income * pe_multiple
        price = market_cap / shares if shares else 0

        delta = None if prev_price is None else price - prev_price
        prev_price = price

        price_text = f"${price:.2f}"
        delta_text = "N/A" if delta is None else f"${delta:+.2f}"

        row = (
            "│ "
            + f"{label:<28}"
            + f"{format_currency(cumulative_profit, 1):>12}"
            + f"{format_currency(net_income, 1):>12}"
            + f"{price_text:>10}"
            + f"{delta_text:>10}"
        )
        print(row.ljust(width - 1) + "│")

    if cumulative_revenue > 0:
        implied_margin = cumulative_profit / cumulative_revenue
        print("├" + "─" * (width - 2) + "┤")
        note = f" Implied EBIT margin from ladder: {format_percent(implied_margin)}"
        print("│" + note.ljust(width - 2) + "│")

    print("└" + "─" * (width - 2) + "┘")


def main():
    if len(sys.argv) < 2:
        print("Usage: python mw_pe_calculator.py <input_json_file>")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)

    with open(input_file, "r") as f:
        data = json.load(f)

    symbol = data.get("symbol", "UNKNOWN")
    missing = validate_inputs(data)
    if missing:
        print(f"Error: Missing required inputs for {symbol}:")
        for field in missing:
            print(f"  - {field}")
        print("\nPlease provide values for these fields in the input file.")
        sys.exit(1)

    base_case = compute_case(data)

    width = 100
    print_title(f"MEGAWATT P/E VALUATION - {symbol}", width)
    print()

    load = base_case["load"]
    revenue = base_case["revenue"]

    step1 = [
        f"Input Mode: {load['input_mode']}",
        f"Total Load: {format_number(load['total_load_mw'], 2)} MW",
        f"PUE: {format_number(load['pue'], 2)}",
        f"IT Load: {format_number(load['it_load_mw'], 2)} MW",
        f"Utilization: {format_percent(load['utilization'])}",
        f"Effective IT Load: {format_number(load['effective_it_load'], 2)} MW",
        "",
        f"Revenue Mode: {revenue['mode']}",
    ]

    if revenue["mode"] == "gpu_hourly":
        step1 += [
            f"GPUs per MW: {format_number(revenue['gpus_per_mw'], 2)}",
            f"Effective GPU Count: {format_number(revenue['gpu_count'], 0)}",
            f"Hourly Rate: ${revenue['gpu_hourly_rate']:.2f}",
            f"Hours/Year: {format_number(revenue['hours_per_year'], 0)}",
        ]
    else:
        step1 += [
            f"Revenue per MW-yr: {format_currency(revenue['revenue_per_mw'])}",
        ]

    step1.append(f"Annual Revenue: {format_currency(base_case['revenue_value'])}")
    print_box("STEP 1: POWER -> REVENUE", step1, width)
    print()

    step2 = [
        f"EBIT Margin: {format_percent(base_case['ebit_margin'])}",
        f"EBIT: {format_currency(base_case['ebit'])}",
        f"SG&A: {format_currency(base_case['sga'])}",
        f"Pre-tax Income: {format_currency(base_case['pre_tax'])}",
        f"Tax Rate: {format_percent(base_case['tax_rate'])}",
        f"Taxes: {format_currency(base_case['taxes'])}",
        f"Net Income: {format_currency(base_case['net_income'])}",
    ]
    print_box("STEP 2: EARNINGS", step2, width)
    print()

    step3 = [
        f"P/E Multiple: {format_number(base_case['pe_multiple'], 2)}x",
        f"Market Cap: {format_currency(base_case['market_cap'])}",
        f"Diluted Shares: {format_number(base_case['shares'], 0)}",
        f"Implied Share Price: ${base_case['price']:.2f}",
    ]
    print_box("STEP 3: VALUATION", step3, width)

    print_title(f"IMPLIED PRICE PER SHARE: ${base_case['price']:.2f}", width)
    print()

    print_sensitivity(data, base_case, width)
    print_value_ladder(data, base_case, width)


if __name__ == "__main__":
    main()
