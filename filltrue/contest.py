"""Hackathon contest overlay. Different game from the 90-day lab.

Lab (automated-trading): 45 DTE 16–20Δ CSPs, no take-profit, scientific gate.
Contest (this file): ~5 RTH sessions, $100k fresh paper, judged on P&L.

Signals we KEEP: SPY 200d crash brake, dual-momentum risk-on/off, IVP bucket,
fill-sync. What CHANGES: tenor, delta, defined-risk default, take-profit,
Friday flatten, size.

Official Alpaca submission rules (tweet 2092250645458047162, 2026-08-25):
1. Dedicated competition paper account (one per email)
2. Starting balance $100,000
3. One-page write-up
4. Strategy must include options
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from filltrue.types import GateResult

CONTEST_START = date(2026, 8, 28)
CONTEST_END = date(2026, 9, 4)
STARTING_EQUITY = 100_000.0

# Short window: gamma has to print. 45 DTE is the lab, not this race.
DTE_MIN = 7
DTE_MAX = 21
DTE_TARGET = 14
# Closer to the money than the lab's 16–20Δ.
DELTA_LO = 0.25
DELTA_HI = 0.35
TARGET_DELTA = 0.30

# Credit: bank 50% of credit (snapshot contest — sitting on a winner is how you lose).
CREDIT_TAKE_PROFIT = 0.50
CREDIT_STOP_MULT = 1.50
# Debit: bank ~80% gain; cut half.
DEBIT_TAKE_PROFIT_MULT = 1.80
DEBIT_STOP_FRAC = 0.50
# Flatten into the submission deadline; don't gift a Friday gap.
FLATTEN_DTE = 3

RISK_FRAC_PER_TICKET = 0.02
MAX_TICKETS = 4
MAX_GROSS_RISK_FRAC = 0.08
MAX_CONTRACTS = 20

IVP_HIGH = 50.0
IVP_LOW = 30.0

# Equity symbols that mean "this is the lab book, abort."
LAB_STOCK_MARKERS = frozenset({"SPY", "VEA", "BND", "BIL"})

Structure = Literal[
    "cash",
    "bull_put_credit",
    "call_debit",
    "put_debit",
    "bear_call_credit",
]


@dataclass(frozen=True)
class Regime:
    spy_above_200: bool
    risk_on: bool
    ivp: float | None
    as_of: date = CONTEST_START


@dataclass(frozen=True)
class ContestPlan:
    structure: Structure
    reason: str
    underlying: str
    dte_target: int
    delta_target: float
    defined_risk: bool
    risk_frac: float
    side: Literal["credit", "debit", "none"]


def contest_open() -> bool:
    """True on contest calendar dates (inclusive)."""
    today = date.today()
    return CONTEST_START <= today <= CONTEST_END


def plan(regime: Regime) -> ContestPlan:
    """Map lab signals onto a 5-day options structure. Cash is a valid plan."""
    und = "IWM"
    if not regime.spy_above_200:
        # Crash brake from E1: no new short premium.
        if regime.ivp is not None and regime.ivp < IVP_LOW:
            return ContestPlan(
                structure="put_debit",
                reason="crash brake on + cheap IV → small put debit, not a short",
                underlying=und,
                dte_target=DTE_TARGET,
                delta_target=TARGET_DELTA,
                defined_risk=True,
                risk_frac=RISK_FRAC_PER_TICKET,
                side="debit",
            )
        return ContestPlan(
            structure="cash",
            reason="crash brake (SPY < 200d) — no new short premium",
            underlying=und,
            dte_target=DTE_TARGET,
            delta_target=TARGET_DELTA,
            defined_risk=True,
            risk_frac=0.0,
            side="none",
        )

    ivp = regime.ivp
    if ivp is not None and ivp >= IVP_HIGH:
        return ContestPlan(
            structure="bull_put_credit",
            reason="risk-on + rich IV → bull put credit (defined risk)",
            underlying=und,
            dte_target=DTE_TARGET,
            delta_target=TARGET_DELTA,
            defined_risk=True,
            risk_frac=RISK_FRAC_PER_TICKET,
            side="credit",
        )
    if ivp is not None and ivp < IVP_LOW:
        return ContestPlan(
            structure="call_debit",
            reason="risk-on + cheap IV → call debit (buy premium, don't sell it)",
            underlying=und,
            dte_target=DTE_TARGET,
            delta_target=TARGET_DELTA,
            defined_risk=True,
            risk_frac=RISK_FRAC_PER_TICKET,
            side="debit",
        )
    # Mid IV, risk-on: still credit, half size. Don't force a lottery.
    return ContestPlan(
        structure="bull_put_credit",
        reason="risk-on + mid IV → bull put credit, half size",
        underlying=und,
        dte_target=DTE_TARGET,
        delta_target=TARGET_DELTA,
        defined_risk=True,
        risk_frac=RISK_FRAC_PER_TICKET / 2,
        side="credit",
    )


def contest_decide_exit(
    *,
    side: Literal["credit", "debit"],
    entry: float,
    mark: float | None,
    dte: int,
    as_of: date | None = None,
    contest_end: date = CONTEST_END,
) -> dict[str, Any]:
    """Contest exits. Take-profit IS a rule here. It is not a rule in the lab."""
    today = as_of or date.today()
    days_left = (contest_end - today).days
    if days_left <= 0 or dte <= FLATTEN_DTE:
        return {
            "should_close": True,
            "rule": "flatten",
            "reason": f"contest flatten (dte={dte}, days_left={days_left})",
        }
    if mark is None or entry <= 0:
        return {"should_close": False, "rule": "no_mark", "reason": "no mark"}

    if side == "credit":
        pf = (entry - mark) / entry
        if mark + 1e-9 >= entry * CREDIT_STOP_MULT:
            return {
                "should_close": True,
                "rule": "stop_loss",
                "reason": f"contest stop: mark {mark:.2f} ≥ {CREDIT_STOP_MULT}× {entry:.2f}",
            }
        if pf + 1e-9 >= CREDIT_TAKE_PROFIT:
            return {
                "should_close": True,
                "rule": "take_profit",
                "reason": f"contest bank {pf:.0%} of credit (lab would hold)",
            }
        return {"should_close": False, "rule": "hold", "reason": f"credit pf {pf:.0%}"}

    # debit
    if mark <= entry * DEBIT_STOP_FRAC + 1e-9:
        return {
            "should_close": True,
            "rule": "stop_loss",
            "reason": f"debit stop: mark {mark:.2f} ≤ {DEBIT_STOP_FRAC:.0%} of {entry:.2f}",
        }
    if mark + 1e-9 >= entry * DEBIT_TAKE_PROFIT_MULT:
        return {
            "should_close": True,
            "rule": "take_profit",
            "reason": f"debit bank: mark {mark:.2f} ≥ {DEBIT_TAKE_PROFIT_MULT}× {entry:.2f}",
        }
    return {"should_close": False, "rule": "hold", "reason": f"debit mark {mark:.2f}/{entry:.2f}"}


def contracts_for_risk(
    *,
    equity: float,
    max_loss_per_contract: float,
    risk_frac: float = RISK_FRAC_PER_TICKET,
) -> int:
    """Integer contracts so one ticket cannot exceed risk_frac of equity."""
    if max_loss_per_contract <= 0 or equity <= 0 or risk_frac <= 0:
        return 0
    n = int((equity * risk_frac) // max_loss_per_contract)
    return max(0, min(n, MAX_CONTRACTS))


def contest_entry_ok(*, dte: int, abs_delta: float, zero_dte: bool = False) -> GateResult:
    if zero_dte or dte < DTE_MIN:
        return GateResult(False, f"contest refuses DTE {dte} (< {DTE_MIN}); no 0DTE", "dte")
    if dte > DTE_MAX:
        return GateResult(
            False,
            f"contest refuses DTE {dte} (> {DTE_MAX}); that is the lab tenor",
            "dte_lab",
        )
    if abs_delta < DELTA_LO or abs_delta > DELTA_HI:
        return GateResult(
            False,
            f"contest delta {abs_delta:.2f} outside {DELTA_LO:.2f}–{DELTA_HI:.2f}",
            "delta",
        )
    return GateResult(True, "contest band", "ok")


def refuse_lab_book(positions: list[str]) -> GateResult:
    """If the broker is holding E1 ETFs as stock, this is the wrong account."""
    # Stock tickers are 1–5 letters. OCC symbols contain digits — those are fine.
    stocks = {p.upper() for p in positions if p.isalpha() and 1 <= len(p) <= 5}
    hit = stocks & LAB_STOCK_MARKERS
    if hit:
        return GateResult(
            False,
            f"lab book markers {sorted(hit)} — open a NEW paper account, do not reset the lab",
            "lab_contamination",
        )
    return GateResult(True, "contest account looks clean", "ok")
