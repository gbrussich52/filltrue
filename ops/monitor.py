"""Re-evaluate every open contest position against live data.

Not a status printer. Each poll re-asks the entry question with today's
numbers and returns a decision: HOLD, TRIM, ADD, or EXIT — plus why. "No
change" is a verdict the loop must reach on evidence, not a default it falls
into by not looking.

    ../automated-trading/.venv/bin/python ops/monitor.py
    ... --json          machine-readable, for the launchd loop
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from filltrue.contest import dynamic_risk_frac, survival_cap  # noqa: E402
from ops.ivp import ivp as real_ivp  # noqa: E402

TRADE = "https://paper-api.alpaca.markets/v2"
DATA = "https://data.alpaca.markets/v1beta1"
START_EQUITY = 100_000.0
CONTEST_END = dt.date(2026, 9, 4)

# Thesis-death triggers. Each answers "is the reason we entered still true?"
TAKE_PROFIT_MULT = 1.80      # debit up 80% — bank it, the snapshot is what scores
STOP_FRAC = 0.50             # premium halved — the move did not come
# Exit on IVP LEVEL, not on a ratio to entry IV. Backtest over 868 IVP<10
# entries (IWM, 180-DTE calls, 2004-2026): exiting at IVP>=50 returned +7.6%
# mean / -3.0% median and exiting at IVP>=75 returned +10.1% / -4.8% — both
# WORSE than no exit rule at all (+14.5% on a dumb 90-day hold). Only IVP>=90
# paid: +25.9% mean, +19.7% median, 59% win. Vol spikes are right-skewed, so
# selling into a partial recovery harvests the small half of the distribution
# and forfeits the large half. The old 1.6x-entry-IV trigger fired around
# IVP 40-55 — precisely the worst threshold.
IVP_EXIT = 90.0
TREND_BREAK = "spy_below_200"


def _h() -> dict:
    k, s = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not k or not s:
        raise SystemExit("ALPACA_API_KEY / ALPACA_SECRET_KEY not set")
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}


def sessions_left(today: dt.date | None = None) -> int:
    """Cash sessions remaining including today, contest ends 9/4."""
    d = today or dt.date.today()
    n = 0
    while d <= CONTEST_END:
        if d.weekday() < 5:
            n += 1
        d += dt.timedelta(days=1)
    return max(1, n)


def regime(h: dict) -> dict:
    import numpy as np
    import yfinance as yf

    out = {}
    for t in ("SPY", "IWM"):
        px = yf.Ticker(t).history(period="3y")["Close"].astype(float)
        # yfinance appends a row for the current calendar day with a NaN close
        # outside RTH. float(NaN) > float(NaN) is False, which silently flipped
        # above_200 to False and made the monitor emit EXIT on the whole book
        # with the reason "SPY lost its 200d". A missing price must never be
        # read as a regime change.
        px = px.dropna()
        if len(px) < 200:
            raise RuntimeError(
                f"{t}: only {len(px)} usable closes after dropna — refusing to "
                "produce a verdict on incomplete data")
        spot, sma = float(px.iloc[-1]), float(px.rolling(200).mean().iloc[-1])
        if not (np.isfinite(spot) and np.isfinite(sma)):
            raise RuntimeError(f"{t}: non-finite spot/sma ({spot}/{sma})")
        r = np.log(px).diff()
        hv = (r.rolling(20).std() * np.sqrt(252)).dropna()
        out[t] = {
            "spot": round(spot, 2),
            "sma200": round(sma, 2),
            "above_200": spot > sma,
            "hv20": round(float(hv.iloc[-1]) * 100, 1),
            "hv_pct_1y": round(float(100 * (hv.tail(252) < hv.iloc[-1]).mean())),
        }
    return out


def evaluate(pos: dict, snap: dict, reg: dict, k: int, equity: float,
             ivp_now: float | None = None) -> dict:
    """Decide on one position. Every branch names the trigger it fired on."""
    entry = float(pos["avg_entry_price"])
    mark = float(pos["current_price"])
    qty = float(pos["qty"])
    pnl = (mark - entry) * qty * 100
    ratio = mark / entry if entry else 0.0
    iv_now = (snap.get("impliedVolatility") or 0) * 100
    iv_entry = float(pos.get("_iv_entry") or 0)

    if ratio >= TAKE_PROFIT_MULT:
        act, why = "EXIT", f"debit at {ratio:.2f}x entry (>= {TAKE_PROFIT_MULT}x) — bank it"
    elif ratio <= STOP_FRAC:
        act, why = "EXIT", f"premium halved ({ratio:.2f}x) — the move did not come"
    elif not reg["SPY"]["above_200"]:
        act, why = "EXIT", "SPY lost its 200d — the risk-on reason for a call debit is gone"
    elif ivp_now is not None and ivp_now >= IVP_EXIT:
        act, why = "EXIT", f"IVP {ivp_now:.0f} >= {IVP_EXIT:.0f} — vol is extreme, sell it"
    elif ivp_now is None:
        # The IVP exit is the primary profit-taking rule. If its input is
        # missing, the position is UNMONITORED for that rule — say so instead
        # of reporting "thesis intact", which reads as an all-clear the loop
        # is not entitled to give.
        act, why = "DEGRADED", ("IVP unavailable — the IVP>=90 exit is NOT being "
                                "evaluated; check ops/logs/monitor.err")
    elif k == 1:
        act, why = "EXIT", "final session — the score is a snapshot, do not hold through it"
    else:
        act, why = "HOLD", f"thesis intact ({ratio:.2f}x, SPY above 200d, IV {iv_now:.1f}%)"

    return {
        "symbol": pos["symbol"], "qty": qty, "entry": entry, "mark": mark,
        "ratio": round(ratio, 3), "pnl": round(pnl, 2), "iv_now": round(iv_now, 1),
        "action": act, "why": why,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    h = _h()

    acct = requests.get(f"{TRADE}/account", headers=h, timeout=20).json()
    equity = float(acct["equity"])
    pos = requests.get(f"{TRADE}/positions", headers=h, timeout=20).json()
    k = sessions_left()
    reg = regime(h)

    snaps = {}
    if pos:
        syms = ",".join(p["symbol"] for p in pos)
        snaps = requests.get(f"{DATA}/options/snapshots", headers=h, timeout=30,
                             params={"symbols": syms, "feed": "indicative"}
                             ).json().get("snapshots", {})

    pre_iv = real_ivp("IWM") or {}
    _ivp = pre_iv.get("ivp_1y")
    if _ivp is None:
        # Realized-vol percentile is not implied vol, but it moves with it and
        # is computed from price data we already hold. Better a labelled proxy
        # than an exit rule that quietly stops existing.
        _ivp = reg["IWM"]["hv_pct_1y"]
        pre_iv = dict(pre_iv, degraded=True, proxy="realized-vol percentile")
    calls = [evaluate(p, snaps.get(p["symbol"], {}), reg, k, equity, _ivp) for p in pos]

    # Real implied-vol percentile beats the realized proxy: it is what an
    # option buyer is actually charged. Falls back to realized if FRED is down.
    iv_iwm = pre_iv
    ivp_used = iv_iwm.get("ivp_1y")
    ivp_src = f"RVX {iv_iwm.get('level')} ({iv_iwm.get('as_of')})"
    if ivp_used is None:
        ivp_used, ivp_src = reg["IWM"]["hv_pct_1y"], "realized-vol proxy (RVX unavailable)"

    size = dynamic_risk_frac(
        equity=equity, start_equity=START_EQUITY, sessions_remaining=k,
        spy_above_200=reg["SPY"]["above_200"], risk_on=reg["SPY"]["above_200"],
        ivp=ivp_used)
    size["ivp_used"] = ivp_used
    size["ivp_source"] = ivp_src
    deployed = sum(abs(float(p["market_value"])) for p in pos)
    report = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "sessions_left": k, "equity": equity,
        "pnl_total": round(equity - START_EQUITY, 2),
        "deployed_pct": round(deployed / equity * 100, 1) if equity else 0,
        "headroom_pct": round(survival_cap(k) * 100, 1),
        "regime": reg, "iv": iv_iwm, "positions": calls, "next_size": size,
        "actions": [c for c in calls if c["action"] != "HOLD"],
    }
    if args.json:
        # One record per line: the log is .jsonl and tail -1 must yield a whole
        # verdict. indent=2 here silently produced un-parseable append-only logs.
        print(json.dumps(report, separators=(",", ":"))); return 0

    print(f"  {report['ts']}   sessions left {k}   equity ${equity:,.0f} "
          f"({report['pnl_total']:+,.0f})")
    s, i = reg["SPY"], reg["IWM"]
    print(f"  SPY {s['spot']} vs 200d {s['sma200']} above={s['above_200']} | "
          f"IWM {i['spot']} HV20 {i['hv20']}% (1y pct {i['hv_pct_1y']})")
    print(f"  IVP {ivp_used} (1y) via {ivp_src}"
          + (f"  |  3y {iv_iwm.get('ivp_3y')}  10y {iv_iwm.get('ivp_10y')}"
             if iv_iwm.get("ivp_3y") is not None else ""))
    print(f"  deployed {report['deployed_pct']}%  next-entry cap {report['headroom_pct']}%"
          f"  next-size {size['risk_frac']:.1%} (${size['dollars']:,.0f})")
    if not calls:
        print("  no open positions")
    for c in calls:
        print(f"  {c['action']:<5} {c['symbol']}  {c['qty']:.0f} @ {c['entry']:.2f} "
              f"-> {c['mark']:.2f} ({c['ratio']:.2f}x) P&L {c['pnl']:+,.0f} | {c['why']}")
    if iv_iwm.get("degraded"):
        print(f"  !! DEGRADED — RVX unavailable ({iv_iwm.get('error','no data')[:60]}); "
              f"IVP exit running on {iv_iwm.get('proxy')}")
    if not report["actions"]:
        print("  VERDICT: no action — checked, not assumed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
