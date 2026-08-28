"""Scan a universe for names that can actually move before the contest snapshot.

A 5-session scored window does not reward "poised to run" in the general
sense. Mean reversion has no schedule; an earnings date does. This ranks
candidates by whether something *forces* a repricing inside the window, then
by setup quality, and reports the vol regime so the instrument choice is
informed rather than assumed.

    ../automated-trading/.venv/bin/python ops/catalyst_scan.py
    ... --universe sp500 --workers 12 --json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

# The S&P 500 constituent list lives in a sibling research repo that is not
# public. Import it when present, otherwise fall back to an explicit ticker
# list — this repo must not hardcode a path into a private one, and must run
# for anyone who clones it.
_SIBLING = pathlib.Path(__file__).resolve().parents[2] / "automated-trading"
if _SIBLING.exists():
    sys.path.insert(0, str(_SIBLING))

try:
    from src.universe import resolve  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover - exercised only outside the author's tree
    def resolve(name: str) -> list[dict]:
        """Comma-separated tickers, or a small liquid default universe."""
        if name.strip().lower() in {"sp500", "mega100", ""}:
            fallback = (
                "AAPL MSFT NVDA AMZN GOOGL META AVGO TSLA LLY JPM XOM UNH V MA "
                "COST HD PG JNJ ABBV WMT CRM AMD ORCL NFLX ADBE INTC MU PANW "
                "DELL HPE NTAP CIEN MDT LULU KR"
            ).split()
            return [{"ticker": t} for t in fallback]
        return [{"ticker": t.strip().upper()} for t in name.split(",") if t.strip()]

SNAPSHOT = dt.date(2026, 9, 4)


def one(ticker: str) -> dict | None:
    import yfinance as yf

    try:
        tk = yf.Ticker(ticker)
        h = tk.history(period="1y")["Close"].astype(float)
        if len(h) < 200:
            return None
        spot = float(h.iloc[-1])
        sma50 = float(h.rolling(50).mean().iloc[-1])
        sma200 = float(h.rolling(200).mean().iloc[-1])
        d = h.diff()
        gain = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
        loss = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
        rsi = 100 - 100 / (1 + gain / loss) if loss > 0 else 100.0
        r = np.log(h).diff()
        hv = (r.rolling(20).std() * np.sqrt(252)).dropna()
        hv20 = float(hv.iloc[-1])
        hv_pct = float(100 * (hv.tail(252) < hv.iloc[-1]).mean())

        er = None
        try:
            cal = tk.calendar or {}
            dates = cal.get("Earnings Date") or []
            dates = [e if isinstance(e, dt.date) else pd.Timestamp(e).date() for e in dates]
            fut = [e for e in dates if e >= dt.date.today()]
            er = min(fut) if fut else None
        except Exception:
            pass

        return {
            "ticker": ticker, "spot": round(spot, 2),
            "above_200": spot > sma200, "above_50": spot > sma50,
            "rsi14": round(rsi, 1),
            "off_52w_high": round((spot / float(h.max()) - 1) * 100, 1),
            "ret_5d": round((spot / float(h.iloc[-6]) - 1) * 100, 2),
            "ret_20d": round((spot / float(h.iloc[-21]) - 1) * 100, 2),
            "hv20": round(hv20 * 100, 1), "hv_pct_1y": round(hv_pct),
            "earnings": str(er) if er else None,
            "days_to_er": (er - dt.date.today()).days if er else None,
            "er_in_window": bool(er and dt.date.today() <= er <= SNAPSHOT),
        }
    except Exception:
        return None


def score(r: dict) -> float:
    """Catalyst first, then trend quality, then a dip that can snap back.

    Weighted so a name with a dated catalyst outranks a better-looking chart
    with nothing to force it — the scoring window is five sessions, and a
    setup without a schedule is a bet on timing we have no edge in.
    """
    s = 0.0
    if r["er_in_window"]:
        s += 50
    elif r["days_to_er"] is not None and r["days_to_er"] <= 14:
        s += 15
    if r["above_200"]:
        s += 12
    if r["above_50"]:
        s += 5
    rsi = r["rsi14"]
    if 30 <= rsi <= 45:               # oversold but not broken
        s += 12
    elif 45 < rsi <= 60:
        s += 6
    elif rsi > 75:
        s -= 8                        # already extended
    if r["hv_pct_1y"] <= 25:
        s += 8                        # cheap vol: premium is buyable
    elif r["hv_pct_1y"] >= 80:
        s -= 5
    s += max(-10.0, min(10.0, r["ret_20d"] / 2))
    return round(s, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="sp500")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    tickers = [x["ticker"] for x in resolve(a.universe)]
    out = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(one, t): t for t in tickers}
        for n, f in enumerate(as_completed(futs), 1):
            r = f.result()
            if r:
                r["score"] = score(r)
                out.append(r)
            if n % 100 == 0 and not a.json:
                print(f"  ...{n}/{len(tickers)}", file=sys.stderr, flush=True)

    out.sort(key=lambda r: -r["score"])
    in_win = [r for r in out if r["er_in_window"]]
    if a.json:
        print(json.dumps({"scanned": len(out), "in_window": len(in_win),
                          "top": out[: a.top]}, indent=2))
        return 0

    print(f"\n  scanned {len(out)} names   |   {len(in_win)} report before {SNAPSHOT}\n")
    print(f"  {'tkr':<7}{'score':>6}{'px':>10}{'>200':>6}{'RSI':>5}{'52wH':>8}"
          f"{'20d%':>7}{'HVpct':>7}{'earnings':>12}{'d':>4}")
    for r in out[: a.top]:
        tag = "  <-- IN WINDOW" if r["er_in_window"] else ""
        print(f"  {r['ticker']:<7}{r['score']:>6.1f}{r['spot']:>10.2f}"
              f"{('Y' if r['above_200'] else 'n'):>6}{r['rsi14']:>5.0f}"
              f"{r['off_52w_high']:>7.1f}%{r['ret_20d']:>+7.1f}{r['hv_pct_1y']:>7}"
              f"{str(r['earnings'] or '-'):>12}{str(r['days_to_er'] if r['days_to_er'] is not None else '-'):>4}{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
