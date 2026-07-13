#!/usr/bin/env python3
"""
Fetch real-time stock quotes from Finnhub.

Usage:
    python fetch_quotes.py GOOGL
    python fetch_quotes.py AAPL MSFT TSLA  # Multiple symbols

Requires:
    FINNHUB_API_KEY environment variable
    Get a free API key at: https://finnhub.io/register
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests


FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def load_env_file():
    """Load environment variables from .env file."""
    env_path = Path(__file__).parent.parent.parent.parent / ".env"

    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    value = value.strip().strip('"').strip("'")
                    os.environ[key.strip()] = value


def get_finnhub_key() -> str:
    """Get Finnhub API key from environment."""
    load_env_file()

    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        print("Error: FINNHUB_API_KEY not found in environment or .env file")
        print("Add FINNHUB_API_KEY=your_key to .env file in project root")
        print("Get a free API key at: https://finnhub.io/register")
        sys.exit(1)
    return key


def fetch_quote(symbol: str, api_key: str) -> dict:
    """Fetch real-time stock quote."""
    url = f"{FINNHUB_BASE_URL}/quote?symbol={symbol}&token={api_key}"
    resp = requests.get(url, timeout=15)
    return resp.json()


def format_currency(value: float) -> str:
    """Format currency value."""
    if value is None:
        return "N/A"
    return f"${value:.2f}"


def print_quote(symbol: str, quote: dict):
    """Print formatted quote."""
    current = quote.get("c", 0)
    change = quote.get("d", 0)
    change_pct = quote.get("dp", 0)
    high = quote.get("h", 0)
    low = quote.get("l", 0)
    open_price = quote.get("o", 0)
    prev_close = quote.get("pc", 0)

    W = 70

    print("┌" + "─" * (W-2) + "┐")
    print("│" + f" {symbol} - REAL-TIME QUOTE".ljust(W-2) + "│")
    print("├" + "─" * (W-2) + "┤")
    print("│" + "".ljust(W-2) + "│")
    print("│" + f"  Current Price:    {format_currency(current)}".ljust(W-2) + "│")
    print("│" + f"  Change:           {format_currency(change)} ({change_pct:+.2f}%)".ljust(W-2) + "│")
    print("│" + "".ljust(W-2) + "│")
    print("│" + f"  Day High:         {format_currency(high)}".ljust(W-2) + "│")
    print("│" + f"  Day Low:          {format_currency(low)}".ljust(W-2) + "│")
    print("│" + f"  Open:             {format_currency(open_price)}".ljust(W-2) + "│")
    print("│" + f"  Previous Close:   {format_currency(prev_close)}".ljust(W-2) + "│")
    print("│" + "".ljust(W-2) + "│")
    print("└" + "─" * (W-2) + "┘")
    print()


def save_quote(symbol: str, quote: dict, output_dir: Path) -> Path:
    """Save quote data to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{symbol}_quote.json"

    output_data = {
        "symbol": symbol,
        "fetched_at": datetime.now().isoformat(),
        "quote": quote
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    return output_file


def main():
    if len(sys.argv) < 2:
        print("Usage: python fetch_quotes.py SYMBOL [SYMBOL2 ...]")
        print("Example: python fetch_quotes.py GOOGL")
        print("Example: python fetch_quotes.py AAPL MSFT TSLA")
        sys.exit(1)

    symbols = [s.upper() for s in sys.argv[1:]]
    api_key = get_finnhub_key()

    script_dir = Path(__file__).parent
    output_dir = script_dir.parent / "reference" / "quotes"

    print(f"Fetching quotes for {len(symbols)} symbol(s)...")
    print()

    for symbol in symbols:
        print(f"Fetching {symbol}...")
        quote = fetch_quote(symbol, api_key)

        if "error" in quote:
            print(f"  Error: {quote['error']}")
            print()
            continue

        # Save
        output_file = save_quote(symbol, quote, output_dir)
        print(f"  ✓ Saved to: {output_file}")
        print()

        # Display
        print_quote(symbol, quote)


if __name__ == "__main__":
    main()
