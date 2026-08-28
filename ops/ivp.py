"""Real implied-volatility percentile from CBOE vol indices.

The local IV store needs 60 daily observations before IVP arms (~2026-11-18).
CBOE already publishes the series we were waiting to accumulate: RVX is the
Russell 2000 (IWM) volatility index, VIX the S&P 500 (SPY) one, both with
~20 years of daily history, free from FRED with no key.

This replaces the realized-vol proxy for underlyings that have an index.
Realized vol answers "how much has it moved"; these answer "what is the market
charging" — which is the number an option buyer actually pays.

IVP and IVR are both returned. IVR is a range measure, so a single spike
anywhere in the lookback inflates its denominator permanently: on a 10-year
window IWM currently prints IVP 24 against IVR 9, and the gap is one COVID-era
print, not information about today.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pandas as pd
import requests

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"
INDEX_FOR = {"IWM": "RVXCLS", "SPY": "VIXCLS", "QQQ": "VXNCLS", "DIA": "VXDCLS"}
CACHE = Path(__file__).resolve().parent / "logs" / "ivp_cache.json"
CACHE_TTL_SEC = 6 * 3600


def _fetch(series_id: str) -> pd.Series:
    r = requests.get(FRED, params={"id": series_id}, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "v"]
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    df = df.dropna()
    if len(df) < 300:
        raise ValueError(f"{series_id}: only {len(df)} rows, looks truncated")
    return pd.Series(df["v"].values, index=pd.to_datetime(df["date"]))


def ivp(underlying: str, *, use_cache: bool = True) -> dict | None:
    """IVP/IVR for an underlying with a CBOE index. None if it has none."""
    sid = INDEX_FOR.get(underlying.upper())
    if not sid:
        return None

    if use_cache and CACHE.exists():
        try:
            blob = json.loads(CACHE.read_text())
            hit = blob.get(sid)
            if hit and time.time() - hit["fetched"] < CACHE_TTL_SEC:
                return hit["data"]
        except Exception:
            pass

    try:
        s = _fetch(sid)
    except Exception as exc:
        return {"underlying": underlying.upper(), "index": sid, "error": str(exc)}

    cur = float(s.iloc[-1])
    out = {"underlying": underlying.upper(), "index": sid, "level": round(cur, 2),
           "as_of": str(s.index[-1].date()), "obs": len(s)}
    for n, lbl in ((252, "1y"), (756, "3y"), (2520, "10y")):
        if len(s) < n:
            continue
        w = s.tail(n)
        lo, hi = float(w.min()), float(w.max())
        out[f"ivp_{lbl}"] = round(100 * float((w < cur).mean()), 1)
        out[f"ivr_{lbl}"] = round(100 * (cur - lo) / (hi - lo), 1) if hi > lo else None

    blob = {}
    if CACHE.exists():
        try:
            blob = json.loads(CACHE.read_text())
        except Exception:
            blob = {}
    blob[sid] = {"fetched": time.time(), "data": out}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(blob))
    return out


if __name__ == "__main__":
    import sys
    for u in (sys.argv[1:] or ["IWM", "SPY"]):
        print(json.dumps(ivp(u), indent=2))
