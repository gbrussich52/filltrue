#!/usr/bin/env python3
"""Flatten every open position into the contest deadline.

Why this exists: the monitor is deliberately read-only ("the human still
clicks"), and on the final session it names EXIT on every leg without
submitting anything. The score is a snapshot at 15:00 UTC on 2026-09-04, so
the flatten is a manual act performed inside a ~90-minute window. Doing that
by hand across N legs, under a clock, is how a leg gets missed.

Dry-run by default. Nothing is sent without --execute.

Keeps the project's one non-negotiable: a submitted order is not a closed
position. Every ticket is polled to a terminal broker state and the exit is
reported from `filled_qty` / `filled_avg_price`, never from the submit call.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from filltrue.gate import contest_account_ok, paper_mode_ok  # noqa: E402

TRADE = "https://paper-api.alpaca.markets/v2"
DATA = "https://data.alpaca.markets/v1beta1"
DEAD = {"filled", "expired", "canceled", "cancelled", "rejected", "replaced"}


def _headers() -> dict:
    k, s = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not k or not s:
        raise SystemExit("ALPACA_API_KEY / ALPACA_SECRET_KEY not set")
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}


def plan(positions: list[dict], quotes: dict) -> list[dict]:
    """Pure: positions + quotes -> one close ticket each. No network, no I/O.

    A long is sold at the bid, a short bought at the ask — the marketable side.
    Crossing the spread is the cost of certainty, and certainty is the whole
    point on the last morning: an unfilled limit at the deadline scores as an
    open position, not as the exit you intended.
    """
    out = []
    for p in positions:
        qty = float(p.get("qty") or 0)
        if qty == 0:
            continue
        sym = p["symbol"]
        q = (quotes.get(sym) or {}).get("latestQuote") or {}
        bid, ask = float(q.get("bp") or 0), float(q.get("ap") or 0)
        long_ = qty > 0
        limit = bid if long_ else ask
        out.append({
            "symbol": sym,
            "qty": int(abs(qty)),
            "side": "sell" if long_ else "buy",
            "position_intent": "sell_to_close" if long_ else "buy_to_close",
            "limit": round(limit, 2) if limit > 0 else None,
            "bid": bid, "ask": ask,
            "blocked": None if limit > 0 else "no quote on the close side",
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true",
                    help="actually submit; without it this only prints the plan")
    args = ap.parse_args()

    for gate in (paper_mode_ok(), contest_account_ok()):
        if not gate.ok:
            raise SystemExit(f"refused: {gate.reason}")

    h = _headers()
    pos = requests.get(f"{TRADE}/positions", headers=h, timeout=20).json()
    if not pos:
        print("no open positions — nothing to flatten")
        return 0
    syms = ",".join(p["symbol"] for p in pos)
    quotes = requests.get(f"{DATA}/options/snapshots", headers=h, timeout=30,
                          params={"symbols": syms, "feed": "indicative"}
                          ).json().get("snapshots", {})
    tickets = plan(pos, quotes)

    for t in tickets:
        mark = f"lim {t['limit']:.2f}" if t["limit"] else f"BLOCKED ({t['blocked']})"
        print(f"  {t['side'].upper():4s} {t['qty']:>4d} {t['symbol']}  "
              f"{mark}  (bid {t['bid']:.2f} / ask {t['ask']:.2f})")
    if not args.execute:
        print("\ndry run — nothing submitted. Re-run with --execute inside RTH.")
        return 0

    clock = requests.get(f"{TRADE}/clock", headers=h, timeout=15).json()
    if not clock.get("is_open"):
        raise SystemExit("market closed — a flatten must happen in RTH, not queued blind")

    today = dt.date.today().strftime("%Y%m%d")
    live = []
    for t in tickets:
        if t["blocked"]:
            print(f"SKIP {t['symbol']}: {t['blocked']}")
            continue
        body = {"symbol": t["symbol"], "qty": str(t["qty"]), "side": t["side"],
                "type": "limit", "limit_price": str(t["limit"]),
                "time_in_force": "day", "position_intent": t["position_intent"],
                "client_order_id": f"filltrue-flatten-{t['symbol']}-{today}"}
        r = requests.post(f"{TRADE}/orders", headers=h, json=body, timeout=20)
        if r.status_code == 422 and "client_order_id" in (r.text or "").lower():
            print(f"ALREADY SUBMITTED {t['symbol']} (duplicate id — idempotent)")
            continue
        if r.status_code >= 400:
            print(f"FAIL {t['symbol']}: http {r.status_code}: {r.text[:160]}")
            continue
        o = r.json()
        live.append((t["symbol"], o["id"]))
        print(f"SUBMIT {t['symbol']} -> {o['id']} status={o.get('status')}")

    # The rule the whole project exists for: poll. A submit is not an exit.
    print("\npolling fills:")
    for _ in range(12):
        pending = False
        rows = []
        for sym, oid in live:
            o = requests.get(f"{TRADE}/orders/{oid}", headers=h, timeout=15).json()
            st = str(o.get("status") or "").lower()
            rows.append((sym, st, o.get("filled_qty"), o.get("filled_avg_price")))
            if st not in DEAD:
                pending = True
        if not pending:
            break
        time.sleep(5)
    unfilled = 0
    for sym, st, fq, fp in rows:
        print(f"  {sym}: {st} filled={fq} @ {fp}")
        if st != "filled":
            unfilled += 1
    if unfilled:
        print(f"\n{unfilled} ticket(s) did NOT fill — re-run to re-price at the "
              "new marketable side. Do not record these as closed.")
        return 1
    print("\nflat — every ticket filled at the broker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
