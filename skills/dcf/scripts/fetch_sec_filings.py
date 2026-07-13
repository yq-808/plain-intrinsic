#!/usr/bin/env python3
"""
Fetch and download complete SEC filings (10-K, 10-Q) from SEC.gov.

This script provides access to complete annual and quarterly reports:
- Fetches filing URLs from Finnhub API
- Downloads complete HTML reports from SEC.gov
- Saves to local folder for analysis

Usage:
    python fetch_sec_filings.py GOOGL --form 10-K --limit 3
    python fetch_sec_filings.py AAPL --form 10-Q --limit 5

Requires:
    FINNHUB_API_KEY environment variable
    Get a free API key at: https://finnhub.io/register
"""

import json
import os
import sys
import time
from datetime import datetime
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


def fetch_filings_list(symbol: str, api_key: str, form: str = None, limit: int = 10) -> list:
    """Fetch list of SEC filings from Finnhub."""
    url = f"{FINNHUB_BASE_URL}/stock/filings?symbol={symbol}&token={api_key}"

    if form:
        url += f"&form={form}"

    resp = requests.get(url, timeout=15)
    data = resp.json()

    if "error" in data:
        print(f"Finnhub Error: {data['error']}")
        sys.exit(1)

    # Limit results
    return data[:limit] if isinstance(data, list) else []


def download_sec_report(report_url: str, output_path: Path) -> bool:
    """Download complete SEC report HTML from SEC.gov."""
    headers = {
        'User-Agent': 'open-invest dcf-analyzer contact@example.com'  # SEC requires User-Agent
    }

    try:
        resp = requests.get(report_url, headers=headers, timeout=30)

        if resp.status_code == 200:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(resp.content)
            return True
        else:
            print(f"  ✗ Failed to download: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Download error: {e}")
        return False


def save_filings_index(symbol: str, filings: list, output_dir: Path):
    """Save filings index as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    index_file = output_dir / f"{symbol}_filings_index.json"

    index_data = {
        "symbol": symbol,
        "fetched_at": datetime.now().isoformat(),
        "count": len(filings),
        "filings": filings
    }

    with open(index_file, 'w') as f:
        json.dump(index_data, f, indent=2)

    return index_file


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Fetch and download SEC filings (10-K, 10-Q)'
    )
    parser.add_argument('symbol', help='Stock symbol (e.g., GOOGL)')
    parser.add_argument('--form', default='10-K',
                       help='Form type: 10-K (annual), 10-Q (quarterly), or 8-K (default: 10-K)')
    parser.add_argument('--limit', type=int, default=3,
                       help='Maximum number of filings to download (default: 3)')
    parser.add_argument('--no-download', action='store_true',
                       help='Only fetch URLs, do not download reports')

    args = parser.parse_args()
    symbol = args.symbol.upper()

    api_key = get_finnhub_key()

    print(f"Fetching {args.form} filings for {symbol}...")
    filings = fetch_filings_list(symbol, api_key, form=args.form, limit=args.limit)

    if not filings:
        print("No filings found")
        sys.exit(1)

    print(f"Found {len(filings)} filings")
    print()

    # Determine output directory
    script_dir = Path(__file__).parent
    output_dir = script_dir.parent / "reference" / "sec_filings" / symbol

    # Save index
    index_file = save_filings_index(symbol, filings, output_dir)
    print(f"✓ Saved filings index to: {index_file}")
    print()

    if args.no_download:
        print("Skipping downloads (--no-download flag set)")
        print()
        print("Filing URLs:")
        for filing in filings:
            print(f"  {filing['form']} ({filing['filedDate'][:10]}): {filing['reportUrl']}")
        return

    # Download each report
    print("Downloading reports...")
    print()

    for i, filing in enumerate(filings, 1):
        form = filing['form']
        filed_date = filing['filedDate'][:10]  # YYYY-MM-DD
        report_url = filing['reportUrl']
        access_number = filing['accessNumber']

        # Create filename
        filename = f"{symbol}_{form}_{filed_date}_{access_number}.html"
        output_path = output_dir / filename

        print(f"[{i}/{len(filings)}] {form} filed {filed_date}")
        print(f"  URL: {report_url}")

        if output_path.exists():
            print(f"  ✓ Already downloaded: {output_path}")
        else:
            print(f"  ⬇ Downloading...")
            success = download_sec_report(report_url, output_path)

            if success:
                file_size = output_path.stat().st_size / 1024  # KB
                print(f"  ✓ Saved: {output_path} ({file_size:.1f} KB)")

            # Be nice to SEC.gov (rate limiting)
            time.sleep(0.2)

        print()

    print("=" * 80)
    print("DOWNLOAD COMPLETE")
    print("=" * 80)
    print(f"Symbol:          {symbol}")
    print(f"Form Type:       {args.form}")
    print(f"Reports Saved:   {len(filings)}")
    print(f"Output Folder:   {output_dir}")
    print(f"Index File:      {index_file}")
    print("=" * 80)
    print()
    print("Files downloaded:")
    for filing in filings:
        form = filing['form']
        filed_date = filing['filedDate'][:10]
        access_number = filing['accessNumber']
        filename = f"{symbol}_{form}_{filed_date}_{access_number}.html"
        file_path = output_dir / filename
        if file_path.exists():
            print(f"  ✓ {filename}")


if __name__ == "__main__":
    main()
