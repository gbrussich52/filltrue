"""OCC option symbol parse / build. No network."""

from __future__ import annotations

import re
from datetime import date

_OCC = re.compile(
    r"^([A-Z]{1,6})(\d{2})(\d{2})(\d{2})([PC])(\d{8})$"
)


def parse_occ(symbol: str) -> dict:
    m = _OCC.match(symbol.replace(" ", "").upper())
    if not m:
        raise ValueError(f"not an OCC symbol: {symbol}")
    und, yy, mm, dd, pc, strike_raw = m.groups()
    year = 2000 + int(yy)
    return {
        "underlying": und,
        "expiration": date(year, int(mm), int(dd)),
        "option_type": "put" if pc == "P" else "call",
        "strike": int(strike_raw) / 1000.0,
    }


def build_occ(underlying: str, expiration: date, option_type: str, strike: float) -> str:
    pc = "P" if option_type.lower().startswith("p") else "C"
    strike_i = int(round(strike * 1000))
    return (
        f"{underlying.upper()}{expiration.strftime('%y%m%d')}{pc}{strike_i:08d}"
    )
