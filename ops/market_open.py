#!/usr/bin/env python3
"""Is the options market open right now? Exit code is the answer.

  0  — open, trade
 10  — closed, do not trade and do not page anyone about it
 20  — unknown (the clock call failed), treat as a real problem

Why this is its own file: the runner needs to tell three states apart, and
`flatten.py` collapses two of them. Its market-closed refusal is a SystemExit,
which exits 1 — the same code it returns when a leg genuinely did not fill.
On 2026-09-04 that made a self-inflicted script error page as though the book
had failed to flatten. A refusal is not a failure.

Listed equity and ETF options trade regular hours only; there is no
pre-market or after-hours options session the way there is for stocks. So
"closed" here is a hard stop, not something to retry through.
"""
from __future__ import annotations

import os
import sys

import requests

TRADE = "https://paper-api.alpaca.markets/v2"


def main() -> int:
    k, s = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not k or not s:
        print("no credentials in the environment")
        return 20
    try:
        c = requests.get(f"{TRADE}/clock", headers={
            "APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}, timeout=15).json()
    except Exception as ex:                      # noqa: BLE001 — any failure is "unknown"
        print(f"clock call failed: {ex}")
        return 20
    if c.get("is_open"):
        print(f"open (now {c.get('timestamp')}, closes {c.get('next_close')})")
        return 0
    print(f"closed (now {c.get('timestamp')}, next open {c.get('next_open')})")
    return 10


if __name__ == "__main__":
    sys.exit(main())
