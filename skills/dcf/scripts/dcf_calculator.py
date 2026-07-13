#!/usr/bin/env python3
"""
DCF (Discounted Cash Flow) Calculator

Calculates intrinsic stock value using FCFF (Free Cash Flow to Firm) methodology.

Usage:
    python dcf_calculator.py <input_json_file>
"""

import json
import sys
from copy import deepcopy
from pathlib import Path


def parse_value(value):
    """Parse value with unit suffix (K, M, B, T) into a number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip().upper()
        multipliers = {
            'K': 1_000,
            'M': 1_000_000,
            'B': 1_000_000_000,
            'T': 1_000_000_000_000,
        }
        for suffix, mult in multipliers.items():
            if value.endswith(suffix):
                return float(value[:-1]) * mult
        return float(value)
    return None


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
    """Format decimal as percentage."""
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def normalize_scenarios(raw_scenarios):
    """Validate and normalize scenario probabilities."""
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ValueError("'scenarios' must be a non-empty list")

    scenarios = []
    for idx, scenario in enumerate(raw_scenarios):
        if not isinstance(scenario, dict):
            raise ValueError(f"scenarios[{idx}] must be an object")
        if "probability" not in scenario:
            raise ValueError(f"scenarios[{idx}] is missing 'probability'")

        try:
            probability = float(scenario["probability"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"scenarios[{idx}].probability must be a number") from exc

        if probability < 0:
            raise ValueError(f"scenarios[{idx}].probability cannot be negative")

        normalized = deepcopy(scenario)
        normalized["probability"] = probability
        scenarios.append(normalized)

    total = sum(s["probability"] for s in scenarios)
    if total <= 0:
        raise ValueError("Scenario probability sum must be > 0")

    # Support either decimal probabilities (sum=1.0) or percentages (sum=100)
    if total > 1.0001:
        if abs(total - 100.0) <= 0.1:
            for scenario in scenarios:
                scenario["probability"] /= 100.0
            total = sum(s["probability"] for s in scenarios)
        else:
            raise ValueError("Scenario probabilities must sum to 1.0 (or 100)")

    if abs(total - 1.0) > 0.001:
        raise ValueError(f"Scenario probabilities must sum to 1.0; got {total:.4f}")

    return scenarios


def build_scenario_data(base_data, scenario):
    """Build a concrete input dict for a specific scenario."""
    scenario_data = deepcopy(base_data)
    scenario_data.pop("scenarios", None)

    for key in ["base_year", "assumptions", "wacc_inputs", "terminal", "balance_sheet"]:
        if key in scenario:
            base_section = scenario_data.get(key, {})
            override_section = scenario[key]

            if isinstance(base_section, dict) and isinstance(override_section, dict):
                merged_section = deepcopy(base_section)
                merged_section.update(override_section)
                scenario_data[key] = merged_section
            else:
                scenario_data[key] = override_section

    return scenario_data


def validate_inputs(data):
    """Validate all required fields are present and non-null."""
    missing = []

    # Check base_year fields
    base_year = data.get("base_year", {})
    for field in ["revenue", "ebit_margin", "da_percent", "nwc_percent"]:
        if base_year.get(field) is None:
            missing.append(f"base_year.{field}")

    # Check assumptions
    assumptions = data.get("assumptions", {})
    for field in ["tax_rate", "growth_rates", "ebit_margins"]:
        if assumptions.get(field) is None:
            missing.append(f"assumptions.{field}")
    if assumptions.get("capex_percent") is None and base_year.get("capex_percent") is None:
        missing.append("assumptions.capex_percent (or legacy base_year.capex_percent)")

    # Check WACC inputs
    wacc = data.get("wacc_inputs", {})
    for field in ["risk_free_rate", "equity_risk_premium", "beta",
                  "cost_of_debt", "debt_weight", "equity_weight"]:
        if wacc.get(field) is None:
            missing.append(f"wacc_inputs.{field}")

    # Check terminal
    terminal = data.get("terminal", {})
    if terminal.get("growth_rate") is None:
        missing.append("terminal.growth_rate")

    # Check balance sheet
    balance = data.get("balance_sheet", {})
    for field in ["cash", "debt", "diluted_shares"]:
        if balance.get(field) is None:
            missing.append(f"balance_sheet.{field}")

    return missing


def validate_series_lengths(capex_percent, growth_rates, ebit_margins):
    """Validate list inputs match the forecast horizon length."""
    issues = []
    years = len(growth_rates)
    if isinstance(capex_percent, list) and len(capex_percent) != years:
        issues.append(f"capex_percent length ({len(capex_percent)}) != growth_rates length ({years})")
    if len(ebit_margins) != years:
        issues.append(f"ebit_margins length ({len(ebit_margins)}) != growth_rates length ({years})")
    return issues


def calculate_wacc(wacc_inputs, tax_rate):
    """Calculate WACC using CAPM for cost of equity."""
    rf = wacc_inputs["risk_free_rate"]
    erp = wacc_inputs["equity_risk_premium"]
    beta = wacc_inputs["beta"]
    rd = wacc_inputs["cost_of_debt"]
    wd = wacc_inputs["debt_weight"]
    we = wacc_inputs["equity_weight"]

    # Cost of equity using CAPM
    re = rf + beta * erp

    # WACC formula
    wacc = we * re + wd * rd * (1 - tax_rate)

    return wacc, re


def calculate_dcf(data):
    """Perform full DCF calculation."""
    # Parse inputs
    base_revenue = parse_value(data["base_year"]["revenue"])
    base_ebit_margin = data["base_year"]["ebit_margin"]
    da_percent = data["base_year"]["da_percent"]
    nwc_percent = data["base_year"]["nwc_percent"]

    tax_rate = data["assumptions"]["tax_rate"]
    growth_rates = data["assumptions"]["growth_rates"]
    ebit_margins = data["assumptions"]["ebit_margins"]
    capex_percent = data["assumptions"].get("capex_percent")
    if capex_percent is None:
        # Backward compatibility: legacy input used base_year.capex_percent
        capex_percent = data["base_year"].get("capex_percent")

    length_issues = validate_series_lengths(capex_percent, growth_rates, ebit_margins)
    if length_issues:
        raise ValueError("Invalid series lengths: " + "; ".join(length_issues))

    terminal_growth = data["terminal"]["growth_rate"]

    cash = parse_value(data["balance_sheet"]["cash"])
    debt = parse_value(data["balance_sheet"]["debt"])
    shares = parse_value(data["balance_sheet"]["diluted_shares"])

    # Calculate WACC
    wacc, cost_of_equity = calculate_wacc(data["wacc_inputs"], tax_rate)

    # Forecast period based on growth_rates length
    years = len(growth_rates)

    # Initialize arrays
    revenues = []
    ebits = []
    nopats = []
    das = []
    capexs = []
    nwcs = []
    delta_nwcs = []
    fcffs = []
    discount_factors = []
    pv_fcffs = []

    # Base year NWC for delta calculation
    prev_nwc = base_revenue * nwc_percent

    # Forecast each year
    prev_revenue = base_revenue
    for i in range(years):
        # Revenue
        revenue = prev_revenue * (1 + growth_rates[i])
        revenues.append(revenue)

        # EBIT
        ebit = revenue * ebit_margins[i]
        ebits.append(ebit)

        # NOPAT
        nopat = ebit * (1 - tax_rate)
        nopats.append(nopat)

        # D&A
        da = revenue * da_percent
        das.append(da)

        # Capex
        capex_rate = capex_percent[i] if isinstance(capex_percent, list) else capex_percent
        capex = revenue * capex_rate
        capexs.append(capex)

        # NWC and change
        nwc = revenue * nwc_percent
        nwcs.append(nwc)
        delta_nwc = nwc - prev_nwc
        delta_nwcs.append(delta_nwc)

        # FCFF
        fcff = nopat + da - capex - delta_nwc
        fcffs.append(fcff)

        # Discount factor
        df = 1 / ((1 + wacc) ** (i + 1))
        discount_factors.append(df)

        # PV of FCFF
        pv_fcff = fcff * df
        pv_fcffs.append(pv_fcff)

        # Update for next iteration
        prev_revenue = revenue
        prev_nwc = nwc

    # Terminal Value
    terminal_fcff = fcffs[-1] * (1 + terminal_growth)
    terminal_value = terminal_fcff / (wacc - terminal_growth)
    pv_terminal = terminal_value * discount_factors[-1]

    # Enterprise Value
    sum_pv_fcff = sum(pv_fcffs)
    enterprise_value = sum_pv_fcff + pv_terminal

    # Equity Value
    equity_value = enterprise_value + cash - debt

    # Intrinsic Price per Share
    intrinsic_price = equity_value / shares

    return {
        "years": years,
        "revenues": revenues,
        "ebits": ebits,
        "nopats": nopats,
        "das": das,
        "capexs": capexs,
        "nwcs": nwcs,
        "delta_nwcs": delta_nwcs,
        "fcffs": fcffs,
        "discount_factors": discount_factors,
        "pv_fcffs": pv_fcffs,
        "wacc": wacc,
        "cost_of_equity": cost_of_equity,
        "terminal_value": terminal_value,
        "pv_terminal": pv_terminal,
        "sum_pv_fcff": sum_pv_fcff,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "intrinsic_price": intrinsic_price,
        "cash": cash,
        "debt": debt,
        "shares": shares,
        "terminal_growth": terminal_growth,
    }


def calculate_sensitivity(data, base_wacc, base_terminal_growth):
    """Generate sensitivity analysis grid."""
    # WACC range: -1.5% to +1.5% in 0.5% steps
    wacc_range = [base_wacc + delta for delta in [-0.015, -0.010, -0.005, 0, 0.005, 0.010, 0.015]]

    # Terminal growth range: -1% to +1% in 0.5% steps
    tg_range = [base_terminal_growth + delta for delta in [-0.010, -0.005, 0, 0.005, 0.010]]

    # Parse necessary values
    base_revenue = parse_value(data["base_year"]["revenue"])
    da_percent = data["base_year"]["da_percent"]
    nwc_percent = data["base_year"]["nwc_percent"]
    tax_rate = data["assumptions"]["tax_rate"]
    growth_rates = data["assumptions"]["growth_rates"]
    ebit_margins = data["assumptions"]["ebit_margins"]
    capex_percent = data["assumptions"].get("capex_percent")
    if capex_percent is None:
        # Backward compatibility: legacy input used base_year.capex_percent
        capex_percent = data["base_year"].get("capex_percent")

    length_issues = validate_series_lengths(capex_percent, growth_rates, ebit_margins)
    if length_issues:
        raise ValueError("Invalid series lengths: " + "; ".join(length_issues))
    cash = parse_value(data["balance_sheet"]["cash"])
    debt = parse_value(data["balance_sheet"]["debt"])
    shares = parse_value(data["balance_sheet"]["diluted_shares"])

    # Calculate final year FCFF (doesn't change with WACC/TG)
    prev_revenue = base_revenue
    prev_nwc = base_revenue * nwc_percent

    for i in range(len(growth_rates)):
        revenue = prev_revenue * (1 + growth_rates[i])
        ebit = revenue * ebit_margins[i]
        nopat = ebit * (1 - tax_rate)
        da = revenue * da_percent
        capex_rate = capex_percent[i] if isinstance(capex_percent, list) else capex_percent
        capex = revenue * capex_rate
        nwc = revenue * nwc_percent
        delta_nwc = nwc - prev_nwc
        fcff = nopat + da - capex - delta_nwc
        prev_revenue = revenue
        prev_nwc = nwc

    final_fcff = fcff
    years = len(growth_rates)

    # Build sensitivity grid
    grid = []
    for tg in tg_range:
        row = []
        for w in wacc_range:
            # Recalculate PV of FCFFs with new WACC
            prev_rev = base_revenue
            prev_nwc_calc = base_revenue * nwc_percent
            sum_pv = 0
            for i in range(years):
                rev = prev_rev * (1 + growth_rates[i])
                eb = rev * ebit_margins[i]
                nop = eb * (1 - tax_rate)
                d_a = rev * da_percent
                cap_rate = capex_percent[i] if isinstance(capex_percent, list) else capex_percent
                cap = rev * cap_rate
                nwc_calc = rev * nwc_percent
                d_nwc = nwc_calc - prev_nwc_calc
                fc = nop + d_a - cap - d_nwc
                df = 1 / ((1 + w) ** (i + 1))
                sum_pv += fc * df
                prev_rev = rev
                prev_nwc_calc = nwc_calc

            # Terminal value with new parameters
            term_fcff = final_fcff * (1 + tg)
            if w <= tg:
                # Invalid - WACC must be greater than terminal growth
                row.append(None)
                continue
            tv = term_fcff / (w - tg)
            pv_tv = tv / ((1 + w) ** years)

            ev = sum_pv + pv_tv
            eq_val = ev + cash - debt
            price = eq_val / shares
            row.append(price)
        grid.append(row)

    return wacc_range, tg_range, grid


def calculate_probability_weighted_results(data):
    """Run DCF for each scenario and compute probability-weighted value."""
    scenarios = normalize_scenarios(data.get("scenarios"))

    scenario_results = []
    for idx, scenario in enumerate(scenarios):
        name = scenario.get("name") or f"Scenario {idx + 1}"
        scenario_data = build_scenario_data(data, scenario)

        missing = validate_inputs(scenario_data)
        if missing:
            fields = ", ".join(missing)
            raise ValueError(f"{name}: missing required inputs: {fields}")

        growth_rates = scenario_data["assumptions"]["growth_rates"]
        ebit_margins = scenario_data["assumptions"]["ebit_margins"]
        capex_percent = scenario_data["assumptions"].get("capex_percent")
        if capex_percent is None:
            # Backward compatibility: legacy input used base_year.capex_percent
            capex_percent = scenario_data["base_year"].get("capex_percent")
        length_issues = validate_series_lengths(capex_percent, growth_rates, ebit_margins)
        if length_issues:
            raise ValueError(f"{name}: invalid series lengths: {'; '.join(length_issues)}")

        result = calculate_dcf(scenario_data)
        probability = scenario["probability"]

        scenario_results.append({
            "name": name,
            "probability": probability,
            "data": scenario_data,
            "results": result,
            "contribution": result["intrinsic_price"] * probability,
        })

    weighted_price = sum(item["contribution"] for item in scenario_results)
    return scenario_results, weighted_price


def print_probability_weighted_summary(symbol, scenario_results, weighted_price):
    """Print compact summary for scenario-weighted valuation."""
    header = "│ {name:<20} {prob:>8} {wacc:>8} {growth:>8} {price:>12} {weighted:>12} │"
    W = len(header.format(
        name="Scenario",
        prob="Prob",
        wacc="WACC",
        growth="g",
        price="Price",
        weighted="Weighted",
    ))

    print("╔" + "═" * (W - 2) + "╗")
    title = f"PROBABILITY-WEIGHTED DCF: {symbol}"
    print("║" + title.center(W - 2) + "║")
    print("╚" + "═" * (W - 2) + "╝")
    print()

    print("┌" + "─" * (W - 2) + "┐")
    print(header.format(
        name="Scenario",
        prob="Prob",
        wacc="WACC",
        growth="g",
        price="Price",
        weighted="Weighted",
    ))
    print("├" + "─" * (W - 2) + "┤")

    for item in scenario_results:
        result = item["results"]
        print(header.format(
            name=item["name"][:20],
            prob=format_percent(item["probability"]),
            wacc=format_percent(result["wacc"]),
            growth=format_percent(result["terminal_growth"]),
            price=f"${result['intrinsic_price']:.2f}",
            weighted=f"${item['contribution']:.2f}",
        ))

    print("├" + "─" * (W - 2) + "┤")
    weighted_line = f"Probability-weighted intrinsic value: ${weighted_price:.2f}"
    print("│ " + weighted_line.ljust(W - 4) + " │")
    print("└" + "─" * (W - 2) + "┘")
    print()


def print_results(symbol, data, results):
    """Print formatted DCF results."""
    years = results["years"]
    base_label = f"│ {'NOPAT':<8}"
    row_hint = "  ← EBIT×(1-T)"
    table_width = len(base_label) + years * 10 + len(row_hint)
    W = max(86, table_width + 1)  # Total width

    # Title box
    print("╔" + "═" * (W-2) + "╗")
    title = f"DCF VALUATION REPORT: {symbol}"
    print("║" + title.center(W-2) + "║")
    print("╚" + "═" * (W-2) + "╝")
    print()

    # =========================================================================
    # WACC CALCULATION
    # =========================================================================
    print("┌" + "─" * (W-2) + "┐")
    print("│" + " STEP 1: WACC CALCULATION".ljust(W-2) + "│")
    print("├" + "─" * (W-2) + "┤")

    wacc_inputs = data["wacc_inputs"]
    tax_rate = data["assumptions"]["tax_rate"]
    rf = wacc_inputs["risk_free_rate"]
    erp = wacc_inputs["equity_risk_premium"]
    beta = wacc_inputs["beta"]
    rd = wacc_inputs["cost_of_debt"]
    wd = wacc_inputs["debt_weight"]
    we = wacc_inputs["equity_weight"]

    print("│" + "".ljust(W-2) + "│")
    print("│" + "  Cost of Equity (CAPM):".ljust(W-2) + "│")
    print("│" + f"    Re = Rf + β × ERP".ljust(W-2) + "│")
    print("│" + f"    Re = {format_percent(rf)} + {beta:.2f} × {format_percent(erp)}".ljust(W-2) + "│")
    print("│" + f"    Re = {format_percent(results['cost_of_equity'])}".ljust(W-2) + "│")
    print("│" + "".ljust(W-2) + "│")
    print("│" + "  Weighted Average Cost of Capital:".ljust(W-2) + "│")
    print("│" + f"    WACC = We × Re + Wd × Rd × (1 - T)".ljust(W-2) + "│")
    print("│" + f"    WACC = {format_percent(we)} × {format_percent(results['cost_of_equity'])} + {format_percent(wd)} × {format_percent(rd)} × (1 - {format_percent(tax_rate)})".ljust(W-2) + "│")
    print("│" + "".ljust(W-2) + "│")
    wacc_result = f"    ► WACC = {format_percent(results['wacc'])}"
    print("│" + wacc_result.ljust(W-2) + "│")
    print("│" + "".ljust(W-2) + "│")
    print("└" + "─" * (W-2) + "┘")
    print()

    # =========================================================================
    # FORECAST TABLE
    # =========================================================================
    print("┌" + "─" * (W-2) + "┐")
    print("│" + f" STEP 2: FORECAST FREE CASH FLOW ({years}-Year Projection)".ljust(W-2) + "│")
    print("├" + "─" * (W-2) + "┤")
    print("│" + "".ljust(W-2) + "│")
    print("│" + "  FCFF = NOPAT + D&A - Capex - ΔNWC".ljust(W-2) + "│")
    print("│" + "  where NOPAT = EBIT × (1 - Tax Rate)".ljust(W-2) + "│")
    print("│" + "".ljust(W-2) + "│")
    print("├" + "─" * (W-2) + "┤")

    # Header
    header = f"│ {'Year':<8}"
    for i in range(results["years"]):
        header += f"{'Y' + str(i+1):>10}"
    print(header.ljust(W-1) + "│")
    print("├" + "─" * (W-2) + "┤")

    # Revenue
    row = f"│ {'Rev':<8}"
    for rev in results["revenues"]:
        row += f"{format_currency(rev, 0):>10}"
    print(row.ljust(W-1) + "│")

    # EBIT
    row = f"│ {'EBIT':<8}"
    for ebit in results["ebits"]:
        row += f"{format_currency(ebit, 0):>10}"
    print(row.ljust(W-1) + "│")

    print("│" + " " * (W-2) + "│")

    # NOPAT with formula hint
    row = f"│ {'NOPAT':<8}"
    for nopat in results["nopats"]:
        row += f"{format_currency(nopat, 0):>10}"
    row += "  ← EBIT×(1-T)"
    print(row.ljust(W-1) + "│")

    # D&A (add)
    row = f"│ {'+ D&A':<8}"
    for da in results["das"]:
        row += f"{format_currency(da, 0):>10}"
    print(row.ljust(W-1) + "│")

    # Capex (subtract)
    row = f"│ {'- Capex':<8}"
    for capex in results["capexs"]:
        row += f"{format_currency(capex, 0):>10}"
    print(row.ljust(W-1) + "│")

    # Delta NWC (subtract)
    row = f"│ {'- dNWC':<8}"
    for dnwc in results["delta_nwcs"]:
        row += f"{format_currency(dnwc, 0):>10}"
    print(row.ljust(W-1) + "│")

    print("├" + "─" * (W-2) + "┤")

    # FCFF (result)
    row = f"│ {'► FCFF':<8}"
    for fcff in results["fcffs"]:
        row += f"{format_currency(fcff, 0):>10}"
    print(row.ljust(W-1) + "│")

    print("└" + "─" * (W-2) + "┘")
    print()

    # =========================================================================
    # DISCOUNTING
    # =========================================================================
    print("┌" + "─" * (W-2) + "┐")
    print("│" + " STEP 3: DISCOUNT TO PRESENT VALUE".ljust(W-2) + "│")
    print("├" + "─" * (W-2) + "┤")
    print("│" + "".ljust(W-2) + "│")
    print("│" + f"  PV = FCFF ÷ (1 + WACC)^n    where WACC = {format_percent(results['wacc'])}".ljust(W-2) + "│")
    print("│" + "".ljust(W-2) + "│")
    print("├" + "─" * (W-2) + "┤")

    # Discount factors
    row = f"│ {'DF':<8}"
    for i, df in enumerate(results["discount_factors"]):
        row += f"{df:>10.4f}"
    row += "  ← 1/(1+r)^n"
    print(row.ljust(W-1) + "│")

    # PV FCFF
    row = f"│ {'PV':<8}"
    for pv in results["pv_fcffs"]:
        row += f"{format_currency(pv, 0):>10}"
    print(row.ljust(W-1) + "│")

    print("├" + "─" * (W-2) + "┤")
    sum_line = f"│  ► Sum of PV(FCFF) = {format_currency(results['sum_pv_fcff'])}"
    print(sum_line.ljust(W-1) + "│")
    print("└" + "─" * (W-2) + "┘")
    print()

    # =========================================================================
    # TERMINAL VALUE
    # =========================================================================
    print("┌" + "─" * (W-2) + "┐")
    print("│" + " STEP 4: TERMINAL VALUE (Gordon Growth Model)".ljust(W-2) + "│")
    print("├" + "─" * (W-2) + "┤")
    print("│" + "".ljust(W-2) + "│")

    final_fcff = results["fcffs"][-1]
    terminal_fcff = final_fcff * (1 + results["terminal_growth"])
    years = results["years"]

    print("│" + f"  TV = FCFF_n × (1 + g) ÷ (WACC - g)".ljust(W-2) + "│")
    print("│" + "".ljust(W-2) + "│")
    print("│" + f"     = {format_currency(final_fcff)} × (1 + {format_percent(results['terminal_growth'])}) ÷ ({format_percent(results['wacc'])} - {format_percent(results['terminal_growth'])})".ljust(W-2) + "│")
    print("│" + f"     = {format_currency(terminal_fcff)} ÷ {format_percent(results['wacc'] - results['terminal_growth'])}".ljust(W-2) + "│")
    print("│" + f"  ► TV = {format_currency(results['terminal_value'])}".ljust(W-2) + "│")
    print("│" + "".ljust(W-2) + "│")
    print("├" + "─" * (W-2) + "┤")
    print("│" + "".ljust(W-2) + "│")
    print("│" + f"  PV(TV) = TV ÷ (1 + WACC)^{years}".ljust(W-2) + "│")
    print("│" + f"         = {format_currency(results['terminal_value'])} ÷ (1 + {format_percent(results['wacc'])})^{years}".ljust(W-2) + "│")
    print("│" + f"  ► PV(TV) = {format_currency(results['pv_terminal'])}".ljust(W-2) + "│")
    print("│" + "".ljust(W-2) + "│")
    print("└" + "─" * (W-2) + "┘")
    print()

    # =========================================================================
    # ENTERPRISE TO EQUITY VALUE
    # =========================================================================
    print("┌" + "─" * (W-2) + "┐")
    print("│" + " STEP 5: VALUATION BRIDGE".ljust(W-2) + "│")
    print("├" + "─" * (W-2) + "┤")
    print("│" + "".ljust(W-2) + "│")

    # Enterprise Value calculation
    print("│" + "  Enterprise Value:".ljust(W-2) + "│")
    print("│" + f"      Sum of PV(FCFF)         {format_currency(results['sum_pv_fcff']):>12}".ljust(W-2) + "│")
    print("│" + f"    + PV(Terminal Value)      {format_currency(results['pv_terminal']):>12}".ljust(W-2) + "│")
    print("│" + f"    ─────────────────────────────────────".ljust(W-2) + "│")
    print("│" + f"    = Enterprise Value        {format_currency(results['enterprise_value']):>12}".ljust(W-2) + "│")
    print("│" + "".ljust(W-2) + "│")

    # Equity Value calculation
    print("│" + "  Equity Value:".ljust(W-2) + "│")
    print("│" + f"      Enterprise Value        {format_currency(results['enterprise_value']):>12}".ljust(W-2) + "│")
    print("│" + f"    + Cash                    {format_currency(results['cash']):>12}".ljust(W-2) + "│")
    print("│" + f"    - Debt                    {format_currency(results['debt']):>12}".ljust(W-2) + "│")
    print("│" + f"    ─────────────────────────────────────".ljust(W-2) + "│")
    print("│" + f"    = Equity Value            {format_currency(results['equity_value']):>12}".ljust(W-2) + "│")
    print("│" + "".ljust(W-2) + "│")

    # Per share calculation
    print("│" + "  Per Share:".ljust(W-2) + "│")
    print("│" + f"      Equity Value            {format_currency(results['equity_value']):>12}".ljust(W-2) + "│")
    print("│" + f"    ÷ Shares Outstanding      {results['shares'] / 1_000_000_000:>11.2f}B".ljust(W-2) + "│")
    print("│" + f"    ─────────────────────────────────────".ljust(W-2) + "│")
    print("│" + "".ljust(W-2) + "│")
    print("└" + "─" * (W-2) + "┘")

    # Final result box
    print("╔" + "═" * (W-2) + "╗")
    result_line = f"INTRINSIC VALUE PER SHARE:  ${results['intrinsic_price']:.2f}"
    print("║" + result_line.center(W-2) + "║")
    print("╚" + "═" * (W-2) + "╝")

    # Sensitivity Analysis
    print()
    print("┌" + "─" * (W-2) + "┐")
    print("│" + " SENSITIVITY ANALYSIS".ljust(W-2) + "│")
    print("│" + " Intrinsic Price at different WACC and Terminal Growth combinations".ljust(W-2) + "│")
    print("├" + "─" * (W-2) + "┤")

    wacc_range, tg_range, grid = calculate_sensitivity(
        data, results["wacc"], results["terminal_growth"]
    )

    # Header with WACC values
    header = f"│ {'g \\ WACC':<8}"
    for w in wacc_range:
        header += f"{format_percent(w):>10}"
    print(header.ljust(W-1) + "│")
    print("├" + "─" * (W-2) + "┤")

    # Grid rows
    for i, tg in enumerate(tg_range):
        is_base_row = abs(tg - results["terminal_growth"]) < 0.001
        row = f"│ {format_percent(tg):<8}"
        for j, price in enumerate(grid[i]):
            is_base_col = j == 3  # Middle column
            if price is None:
                cell = "N/A"
            else:
                cell = f"${price:.0f}"
            # Highlight base case
            if is_base_row and is_base_col:
                row += f" [{cell:>5}]"
            else:
                row += f"  {cell:>6} "
        print(row.ljust(W-1) + "│")

    print("├" + "─" * (W-2) + "┤")
    print("│" + "  [ ] = Base case (current assumptions)".ljust(W-2) + "│")
    print("└" + "─" * (W-2) + "┘")
    print()


def main():
    if len(sys.argv) < 2:
        print("Usage: python dcf_calculator.py <input_json_file>")
        sys.exit(1)

    input_file = Path(sys.argv[1])

    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)

    # Load JSON
    with open(input_file, "r") as f:
        data = json.load(f)

    symbol = data.get("symbol", "UNKNOWN")

    # Multi-scenario mode: run probability-weighted valuation
    if data.get("scenarios"):
        try:
            scenario_results, weighted_price = calculate_probability_weighted_results(data)
        except ValueError as exc:
            print(f"Error: {exc}")
            sys.exit(1)

        print_probability_weighted_summary(symbol, scenario_results, weighted_price)

        # Print detailed report for each scenario for full transparency.
        for item in scenario_results:
            scenario_name = item["name"]
            probability = item["probability"]

            print("=" * 100)
            print(f"SCENARIO DETAIL: {scenario_name} ({format_percent(probability)})")
            print("=" * 100)
            print()

            print_results(
                f"{symbol} [{scenario_name}]",
                item["data"],
                item["results"],
            )
        return

    # Validate inputs
    missing = validate_inputs(data)
    if missing:
        print(f"Error: Missing required inputs for {symbol}:")
        for field in missing:
            print(f"  - {field}")
        print()
        print("Please provide values for these fields in the input file.")
        sys.exit(1)

    # Validate series lengths (growth, margins, and optional capex array)
    growth_rates = data["assumptions"]["growth_rates"]
    ebit_margins = data["assumptions"]["ebit_margins"]
    capex_percent = data["assumptions"].get("capex_percent")
    if capex_percent is None:
        # Backward compatibility: legacy input used base_year.capex_percent
        capex_percent = data["base_year"].get("capex_percent")
    length_issues = validate_series_lengths(capex_percent, growth_rates, ebit_margins)
    if length_issues:
        print("Error: Invalid series lengths:")
        for issue in length_issues:
            print(f"  - {issue}")
        sys.exit(1)

    # Run DCF calculation
    results = calculate_dcf(data)

    # Print results
    print_results(symbol, data, results)


if __name__ == "__main__":
    main()
