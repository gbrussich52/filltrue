"""Hackathon contest overlay. Different game from the 90-day lab.

Lab (automated-trading): 45 DTE 16–20Δ CSPs, harvest at the right time
(trail / thesis-dead-while-green / 21 DTE) — not a 50% coupon, not never.
Contest (this file): ~5 RTH sessions, $100k fresh paper, judged on P&L.
The *right time* here includes a snapshot harvest (50% of credit / Friday flatten).

Signals we KEEP: SPY 200d crash brake, dual-momentum risk-on/off, IVP bucket,
fill-sync. What CHANGES: tenor, delta, defined-risk default, deadline-aware
harvest, size.

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

def _envf(name: str, default: float) -> float:
    """Read a risk dial from the environment, falling back to the lab default.

    These were hardcoded. They are the research lab's numbers, sized for a
    90-day pre-registered gate where surviving to the end is the point. A
    5-session tournament has the opposite shape: second place pays a third of
    first, so the objective is P(finish first), not expected return, and a
    conservative book cannot win one.

    Made dials rather than raised outright, so the lab keeps its calibration
    and the contest sets its own via FILLTRUE_* — one binary, two postures.
    """
    import os

    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        v = float(raw)
    except ValueError:
        return default
    return v if v > 0 else default


# Loss caps stay. Profit is uncapped by construction: long premium has no
# upper bound, and the exit rules close on thesis death, not on a target.
RISK_FRAC_PER_TICKET = _envf("FILLTRUE_RISK_FRAC", 0.02)
MAX_TICKETS = int(_envf("FILLTRUE_MAX_TICKETS", 4))
MAX_GROSS_RISK_FRAC = _envf("FILLTRUE_MAX_GROSS", 0.08)
MAX_CONTRACTS = int(_envf("FILLTRUE_MAX_CONTRACTS", 20))

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
    conditions_still_fit: bool | None = None,
) -> dict[str, Any]:
    """Contest exits. Harvest when the reason to hold is gone.

    Deadline is a reason (snapshot P&L). 50% of credit is a reason here
    because the clock is 5 sessions, not because 50% is sacred.
    Thesis-dead-while-green is always a reason.
    """
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
        if conditions_still_fit is False and pf > 0:
            return {
                "should_close": True,
                "rule": "condition_invalidation",
                "reason": f"thesis dead while green: profit {pf:.0%}",
            }
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


# --- dynamic sizing -------------------------------------------------------
#
# No fixed percentage survives contact with five different sessions. Size is
# derived each entry from three live measurements:
#
#   survival_cap()     how much can be risked and still leave capital to act
#   conviction()       how strongly the signals agree, right now
#   tournament_tilt()  ahead or behind, with how long left to fix it
#
# The product is the fraction of equity risked on this ticket. Nothing here is
# a preference; each term answers a question with a number.

RETAIN_AFTER_WORST_CASE = 0.25


def survival_cap(sessions_remaining: int, retain: float = RETAIN_AFTER_WORST_CASE) -> float:
    """Largest fraction riskable per entry that survives a worst-case streak.

    A long option can lose 100% of premium, so 'risked' means 'gone'. Losing
    fraction f on each of k entries leaves (1-f)^k. Requiring that to stay
    above `retain` gives f <= 1 - retain**(1/k).

    The curve escalates on its own as the contest closes — 24% with five
    sessions left, 75% on the last one — because capital held back for
    adaptation is only worth holding while there are decisions left to make.
    A fully-deployed book cannot act on new information; it can only hold.
    """
    k = max(1, int(sessions_remaining))
    retain = min(max(retain, 1e-6), 0.999999)
    return 1.0 - retain ** (1.0 / k)


def conviction(*, spy_above_200: bool, risk_on: bool, ivp: float) -> float:
    """Signal agreement in [0,1]. Neutral conditions size small by themselves.

    IV contributes by distance from neutral, not direction: IVP 12 and IVP 88
    are both strong, they just imply opposite structures. The structure choice
    is contest_plan's job; this only measures how loud the signal is.
    """
    iv_edge = min(1.0, abs(float(ivp) - 50.0) / 50.0)
    if spy_above_200 and risk_on:
        trend = 1.0
    elif spy_above_200 or risk_on:
        trend = 0.5
    else:
        trend = 0.2
    return round(0.5 * iv_edge + 0.5 * trend, 4)


def tournament_tilt(*, equity: float, start_equity: float) -> float:
    """Scale risk by standing. Second place pays a fraction of first.

    Behind: variance is the only way back, so push (up to 2x).
    Ahead: the lead is the asset, so ease off — but never below 0.6x, because
    protecting a small lead into a five-day finish is how a winner becomes a
    third-place finisher.
    """
    if start_equity <= 0:
        return 1.0
    r = equity / start_equity - 1.0
    if r >= 0:
        return round(max(0.6, 1.0 - min(0.4, r * 2.0)), 4)
    return round(min(2.0, 1.0 + (-r) * 3.0), 4)


def dynamic_risk_frac(
    *,
    equity: float,
    start_equity: float,
    sessions_remaining: int,
    spy_above_200: bool,
    risk_on: bool,
    ivp: float,
) -> dict:
    """Fraction of equity to risk on this ticket, with its own derivation.

    Returns the inputs alongside the answer so a size can always be explained
    after the fact — an unexplainable size is one nobody can learn from.
    """
    cap = survival_cap(sessions_remaining)
    conv = conviction(spy_above_200=spy_above_200, risk_on=risk_on, ivp=ivp)
    tilt = tournament_tilt(equity=equity, start_equity=start_equity)
    raw = cap * conv * tilt
    frac = min(cap, max(0.0, raw))
    return {
        "risk_frac": round(frac, 4),
        "survival_cap": round(cap, 4),
        "conviction": conv,
        "tilt": tilt,
        "dollars": round(equity * frac, 2),
        "why": (
            f"cap {cap:.1%} (k={sessions_remaining}) x conviction {conv:.2f} "
            f"x tilt {tilt:.2f} -> {frac:.1%}"
        ),
    }


def sized_plan(
    regime: Regime,
    *,
    equity: float,
    start_equity: float,
    sessions_remaining: int,
) -> dict:
    """plan() picks the structure; dynamic_risk_frac() sizes it. Kept separate.

    plan() also expresses its own confidence by returning a fraction of the
    per-ticket cap (full, half for mid-IV, zero for cash). That is a signal
    about the *setup*, independent of standing and sessions left, so it is
    carried through as a multiplier rather than discarded — otherwise a
    half-conviction structure would be sized like a full-conviction one.
    """
    p = plan(regime)
    structure_mult = (
        p.risk_frac / RISK_FRAC_PER_TICKET if RISK_FRAC_PER_TICKET > 0 else 0.0
    )
    d = dynamic_risk_frac(
        equity=equity,
        start_equity=start_equity,
        sessions_remaining=sessions_remaining,
        spy_above_200=regime.spy_above_200,
        risk_on=regime.risk_on,
        ivp=regime.ivp if regime.ivp is not None else 50.0,
    )
    frac = round(d["risk_frac"] * structure_mult, 4)
    return {
        "structure": p.structure,
        "reason": p.reason,
        "underlying": p.underlying,
        "dte_target": p.dte_target,
        "delta_target": p.delta_target,
        "defined_risk": p.defined_risk,
        "side": p.side,
        "risk_frac": frac,
        "risk_dollars": round(equity * frac, 2),
        "sizing": {
            **d,
            "structure_mult": round(structure_mult, 3),
            "why": f"{d['why']} x structure {structure_mult:.2f} -> {frac:.1%}",
        },
    }
