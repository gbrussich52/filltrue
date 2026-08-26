"""Pick a cash-secured put from a chain snapshot. Pure function, no network."""

from __future__ import annotations

from datetime import date

from filltrue.policy import (
    DELTA_HI,
    DELTA_LO,
    DTE_MAX,
    DTE_MIN,
    DTE_TARGET,
    TARGET_DELTA,
    gate_entry,
)
from filltrue.types import Candidate, Contract


def pick_csp(
    chain: list[Contract],
    *,
    as_of: date,
    underlying: str = "IWM",
    delta_lo: float = DELTA_LO,
    delta_hi: float = DELTA_HI,
    dte_lo: int = DTE_MIN,
    dte_hi: int = DTE_MAX,
    target_delta: float = TARGET_DELTA,
    target_dte: int = DTE_TARGET,
) -> Candidate | None:
    """Return the put nearest 18Δ / 45 DTE with a real bid, or None."""
    scored: list[tuple[float, float, Candidate]] = []
    for c in chain:
        if c.underlying.upper() != underlying.upper():
            continue
        if c.option_type != "put":
            continue
        if c.delta is None or c.bid is None or c.bid <= 0:
            continue
        dte = (c.expiration - as_of).days
        if dte < dte_lo or dte > dte_hi:
            continue
        abs_delta = abs(c.delta)
        if abs_delta < delta_lo or abs_delta > delta_hi:
            continue
        cand = Candidate(
            symbol=c.symbol,
            underlying=c.underlying,
            expiration=c.expiration,
            strike=c.strike,
            delta=c.delta,
            bid=c.bid,
            dte=dte,
            limit_price=round(c.bid, 2),
        )
        if not gate_entry(cand).ok:
            continue
        scored.append(
            (abs(abs_delta - target_delta), abs(dte - target_dte), cand)
        )
    if not scored:
        return None
    scored.sort(key=lambda t: (t[0], t[1], -t[2].bid))
    return scored[0][2]
