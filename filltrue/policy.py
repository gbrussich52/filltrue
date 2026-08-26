"""Entry band + spine exits. No take-profit upside cap.

A short put's P&L cannot exceed the credit. That is math, not a rule.
We only mitigate downside / path risk:

1. Stop-loss when mark ≥ 1.5× credit.
2. Trail giveback after a real run (arm 30%, giveback 15 points).
3. Time / gamma stop at 21 DTE.

Never close solely because profit is large.
"""

from __future__ import annotations

from typing import Any

from filltrue.types import Candidate, GateResult

TRAIL_ARM = 0.30
TRAIL_GIVEBACK = 0.15
STOP_LOSS_MARK_MULT = 1.50
CLOSE_DTE = 21
# Float slack so 1.12 × 1.5 vs mark 1.68 (and a 15-point trail) actually fire.
_EPS = 1e-9

DELTA_LO = 0.16
DELTA_HI = 0.20
DTE_MIN = 30
DTE_MAX = 60
DTE_TARGET = 45
TARGET_DELTA = 0.18


def profit_frac(credit: float, mark: float | None) -> float | None:
    """Fraction of credit harvested. 0 = flat, 1.0 = full (mark≈0). None if unknown."""
    if mark is None or credit is None or credit <= 0:
        return None
    if mark < 0:
        mark = 0.0
    return (credit - mark) / credit


def decide_exit(
    *,
    credit: float,
    mark: float | None,
    dte: int,
    peak_profit_frac: float = 0.0,
) -> dict[str, Any]:
    """Return should_close / rule. Never closes solely because profit is large."""
    pf = profit_frac(credit, mark)
    peak = float(peak_profit_frac or 0.0)
    if pf is not None and pf > peak:
        peak = pf

    if dte <= CLOSE_DTE:
        return {
            "should_close": True,
            "reason": f"21-DTE window: {dte} DTE left (risk stop, not profit cap)",
            "peak_profit_frac": peak,
            "profit_frac": pf,
            "rule": "time_stop",
        }

    if mark is None or pf is None:
        return {
            "should_close": False,
            "reason": "no mark — hold (upside open)",
            "peak_profit_frac": peak,
            "profit_frac": pf,
            "rule": "no_mark",
        }

    if mark + _EPS >= credit * STOP_LOSS_MARK_MULT:
        return {
            "should_close": True,
            "reason": (
                f"stop-loss: mark {mark:.2f} ≥ {STOP_LOSS_MARK_MULT:.2f}× credit "
                f"{credit:.2f}"
            ),
            "peak_profit_frac": peak,
            "profit_frac": pf,
            "rule": "stop_loss",
        }

    if peak + _EPS >= TRAIL_ARM and (peak - pf) + _EPS >= TRAIL_GIVEBACK:
        return {
            "should_close": True,
            "reason": (
                f"trail: peak {peak:.0%} → now {pf:.0%}; "
                f"mark {mark:.2f} vs credit {credit:.2f}"
            ),
            "peak_profit_frac": peak,
            "profit_frac": pf,
            "rule": "trail",
        }

    return {
        "should_close": False,
        "reason": (
            f"hold (no upside cap): profit {pf:.0%} peak {peak:.0%} "
            f"({dte} DTE) mark {mark:.2f}/{credit:.2f}"
        ),
        "peak_profit_frac": peak,
        "profit_frac": pf,
        "rule": "hold",
    }


def gate_entry(candidate: Candidate) -> GateResult:
    """Hard entry band. Out-of-band candidates never become orders."""
    if candidate.bid is None or candidate.bid <= 0:
        return GateResult(False, "no bid — cannot set a limit", "no_bid")
    abs_delta = abs(candidate.delta)
    if abs_delta < DELTA_LO or abs_delta > DELTA_HI:
        return GateResult(
            False,
            f"delta {abs_delta:.3f} outside {DELTA_LO:.2f}–{DELTA_HI:.2f}",
            "delta_band",
        )
    if candidate.dte < DTE_MIN or candidate.dte > DTE_MAX:
        return GateResult(
            False,
            f"DTE {candidate.dte} outside {DTE_MIN}–{DTE_MAX}",
            "dte_band",
        )
    return GateResult(True, "in band", "ok")
