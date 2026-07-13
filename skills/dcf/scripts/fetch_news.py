#!/usr/bin/env python3
"""
Fetch company news from Finnhub.

Usage:
    python fetch_news.py GOOGL
    python fetch_news.py GOOGL --days 30  # Last 30 days

Requires:
    FINNHUB_API_KEY environment variable
    Get a free API key at: https://finnhub.io/register
"""

import json
import os
import sys
from datetime import datetime, timedelta
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


def fetch_company_news(symbol: str, api_key: str, days: int = 7) -> list:
    """Fetch recent company news."""
    today = datetime.now()
    from_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")

    url = f"{FINNHUB_BASE_URL}/company-news?symbol={symbol}&from={from_date}&to={to_date}&token={api_key}"
    resp = requests.get(url, timeout=15)
    return resp.json()


def print_news(symbol: str, news: list, days: int):
    """Print formatted news."""
    W = 86

    print("┌" + "─" * (W-2) + "┐")
    print("│" + f" {symbol} - COMPANY NEWS (Past {days} Days)".ljust(W-2) + "│")
    print("├" + "─" * (W-2) + "┤")
    print("│" + "".ljust(W-2) + "│")

    if not news:
        print("│" + "  No news found".ljust(W-2) + "│")
    else:
        for i, article in enumerate(news[:10], 1):  # Show top 10
            headline = article.get("headline", "")
            if len(headline) > 78:
                headline = headline[:75] + "..."

            date = datetime.fromtimestamp(article.get("datetime", 0))
            date_str = date.strftime("%Y-%m-%d")

            print("│" + f"  {i}. [{date_str}] {headline}".ljust(W-2) + "│")

        print("│" + "".ljust(W-2) + "│")
        print("│" + f"  Total articles: {len(news)}".ljust(W-2) + "│")

    print("│" + "".ljust(W-2) + "│")
    print("└" + "─" * (W-2) + "┘")
    print()


def save_news(symbol: str, news: list, days: int, output_dir: Path) -> Path:
    """Save news data to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{symbol}_news_{days}d.json"

    output_data = {
        "symbol": symbol,
        "fetched_at": datetime.now().isoformat(),
        "days": days,
        "count": len(news),
        "news": news
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    return output_file


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Fetch company news from Finnhub'
    )
    parser.add_argument('symbol', help='Stock symbol (e.g., GOOGL)')
    parser.add_argument('--days', type=int, default=7,
                       help='Number of days to fetch (default: 7)')

    args = parser.parse_args()
    symbol = args.symbol.upper()

    api_key = get_finnhub_key()

    print(f"Fetching news for {symbol} (past {args.days} days)...")

    news = fetch_company_news(symbol, api_key, args.days)

    if isinstance(news, dict) and "error" in news:
        print(f"Error: {news['error']}")
        sys.exit(1)

    # Save
    script_dir = Path(__file__).parent
    output_dir = script_dir.parent / "reference" / "news"
    output_file = save_news(symbol, news, args.days, output_dir)

    print(f"✓ Saved to: {output_file}")
    print()

    # Display
    print_news(symbol, news, args.days)


if __name__ == "__main__":
    main()
