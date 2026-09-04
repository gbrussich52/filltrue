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
BUMP_ROUNDS = 3      # re-price attempts before giving up on a limit
WAIT_SECONDS = 20    # how long a price is given to work before the next bump


def _headers() -> dict:
    k, s = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not k or not s:
        raise SystemExit("ALPACA_API_KEY / ALPACA_SECRET_KEY not set")
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}


def _quotes(h: dict, syms: list[str]) -> dict:
    return requests.get(f"{DATA}/options/snapshots", headers=h, timeout=30,
                        params={"symbols": ",".join(syms), "feed": "indicative"}
                        ).json().get("snapshots", {})


def _marketable(snap: dict | None, long_: bool) -> tuple[float, float, float]:
    """(price to hit, bid, ask). A long exits at the bid, a short at the ask."""
    q = (snap or {}).get("latestQuote") or {}
    bid, ask = float(q.get("bp") or 0), float(q.get("ap") or 0)
    return (bid if long_ else ask), bid, ask


def bump_price(limit: float, long_: bool, rnd: int) -> float:
    """Pure: the marketable price, crossed `rnd` ticks further.

    Each successive round gives up one more tick so that a market drifting
    away is chased rather than followed at a polite distance. A sell crosses
    down, a buy crosses up. Never below the $0.01 minimum an option can trade.
    """
    tick = 0.05 if limit >= 3 else 0.01
    out = limit - tick * rnd if long_ else limit + tick * rnd
    return max(round(out, 2), 0.01)


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
    quotes = _quotes(h, [p["symbol"] for p in pos])
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
    live: list[dict] = []
    by_sym = {t["symbol"]: {"long": t["side"] == "sell", "qty": t["qty"],
                            "side": t["side"], "position_intent": t["position_intent"]}
              for t in tickets}
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
            # A second run today. The id keeps us from double-selling, but
            # skipping here would strand that order unmanaged — and "re-run to
            # re-price" was the printed remedy, so the skip defeated its own
            # advice. Adopt the existing order and let the bump logic work it.
            g = requests.get(f"{TRADE}/orders:by_client_order_id", headers=h, timeout=15,
                             params={"client_order_id": body["client_order_id"]})
            if g.status_code < 400:
                o = g.json()
                print(f"ADOPT {t['symbol']} -> {o['id']} status={o.get('status')} (already submitted today)")
                live.append({"symbol": t["symbol"], "oid": o["id"],
                             "status": str(o.get("status") or "").lower(),
                             "filled_qty": o.get("filled_qty"),
                             "filled_price": o.get("filled_avg_price")})
            else:
                print(f"ALREADY SUBMITTED {t['symbol']} but could not re-read it: http {g.status_code}")
            continue
        if r.status_code >= 400:
            print(f"FAIL {t['symbol']}: http {r.status_code}: {r.text[:160]}")
            continue
        o = r.json()
        live.append({"symbol": t["symbol"], "oid": o["id"],
                     "status": str(o.get("status") or "").lower(),
                     "filled_qty": o.get("filled_qty"),
                     "filled_price": o.get("filled_avg_price")})
        print(f"SUBMIT {t['symbol']} -> {o['id']} status={o.get('status')}")

    # The rule the whole project exists for: poll. A submit is not an exit.
    #
    # But polling alone is not enough on the last morning. A limit priced at a
    # quote that was already stale on arrival simply sits at `new` forever —
    # that is the same defect that left 6 of 11 sleeve entries unfilled in the
    # lab, and it reproduced by hand on 2026-09-03. So: re-price into the
    # current marketable side, then take certainty over price on the last pass.
    if not live:
        # Every ticket was blocked or rejected. Reporting "flat" here would be
        # the project's own cardinal sin: a close that never happened.
        print(f"\nno order is working for any of {len(tickets)} position(s) — "
              "nothing was closed. This is open exposure, not a flat book.")
        return 1
    return _work(h, live, by_sym)


def _work(h: dict, live: list[dict], by_sym: dict) -> int:
    """Drive every ticket to a terminal broker state, re-pricing as it goes.

    Rounds of a marketable limit, each re-priced against a freshly fetched
    NBBO, then a market sweep for anything still open. An unfilled limit at
    the deadline scores as an open position, so the last pass trades price for
    certainty on purpose.
    """
    def poll(seconds: int) -> None:
        """Refresh each live ticket's status for up to `seconds`."""
        for _ in range(max(1, seconds // 5)):
            for t in live:
                if t["status"] in DEAD:
                    continue
                o = requests.get(f"{TRADE}/orders/{t['oid']}", headers=h, timeout=15).json()
                t["status"] = str(o.get("status") or "").lower()
                t["filled_qty"], t["filled_price"] = o.get("filled_qty"), o.get("filled_avg_price")
            if all(t["status"] in DEAD for t in live):
                return
            time.sleep(5)

    def still_open() -> list[dict]:
        return [t for t in live if t["status"] not in DEAD]

    print("\npolling fills:")
    poll(WAIT_SECONDS)

    for rnd in range(1, BUMP_ROUNDS + 1):
        open_ = still_open()
        if not open_:
            break
        snaps = _quotes(h, [t["symbol"] for t in open_])
        print(f"\nbump {rnd}/{BUMP_ROUNDS} — re-pricing {len(open_)} unfilled "
              "ticket(s) at the current marketable side:")
        for t in open_:
            side = by_sym[t["symbol"]]
            limit, bid, ask = _marketable(snaps.get(t["symbol"]), side["long"])
            if limit <= 0:
                print(f"  {t['symbol']}: no quote on the close side — leaving as is")
                continue
            limit = bump_price(limit, side["long"], rnd)
            r = requests.patch(f"{TRADE}/orders/{t['oid']}", headers=h, timeout=20,
                               json={"limit_price": str(limit)})
            if r.status_code >= 400:
                print(f"  {t['symbol']}: replace failed http {r.status_code}: {r.text[:120]}")
                continue
            t["oid"] = r.json()["id"]          # a replace returns a NEW order id
            t["status"] = "new"
            print(f"  {t['symbol']}: -> {limit:.2f} (bid {bid:.2f} / ask {ask:.2f})")
        poll(WAIT_SECONDS)

    # Last resort. Certainty beats price: whatever is still working gets
    # cancelled and swept at the market.
    for t in still_open():
        side = by_sym[t["symbol"]]
        print(f"\nMARKET SWEEP {t['symbol']} — limit never filled, taking certainty")
        requests.delete(f"{TRADE}/orders/{t['oid']}", headers=h, timeout=15)
        time.sleep(2)
        r = requests.post(f"{TRADE}/orders", headers=h, timeout=20, json={
            "symbol": t["symbol"], "qty": str(side["qty"]), "side": side["side"],
            "type": "market", "time_in_force": "day",
            "position_intent": side["position_intent"]})
        if r.status_code >= 400:
            print(f"  FAIL {t['symbol']}: http {r.status_code}: {r.text[:160]}")
            continue
        t["oid"], t["status"] = r.json()["id"], "new"
    if still_open():
        poll(WAIT_SECONDS)

    print("\nfinal broker state:")
    unfilled = 0
    for t in live:
        print(f"  {t['symbol']}: {t['status']} filled={t['filled_qty']} @ {t['filled_price']}")
        if t["status"] != "filled":
            unfilled += 1
    if unfilled:
        print(f"\n{unfilled} ticket(s) did NOT fill, market sweep included. "
              "Do not record these as closed — they are still open exposure.")
        return 1
    print("\nflat — every ticket filled and confirmed at the broker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
