"""Contest overlay vs lab spine. These MUST diverge — that is the point."""

from __future__ import annotations

from datetime import date

from filltrue.agent import Agent
from filltrue.broker import FakeBroker
from filltrue.contest import (
    CONTEST_END,
    ContestPlan,
    Regime,
    contest_decide_exit,
    contest_entry_ok,
    contracts_for_risk,
    plan,
    refuse_lab_book,
)
from filltrue.policy import decide_exit as lab_decide_exit


def test_lab_holds_50pct_credit_contest_banks_it():
    lab = lab_decide_exit(credit=2.0, mark=1.0, dte=40, peak_profit_frac=0.5)
    assert lab["should_close"] is False
    contest = contest_decide_exit(side="credit", entry=2.0, mark=1.0, dte=14, as_of=date(2026, 9, 1))
    assert contest["should_close"] is True
    assert contest["rule"] == "take_profit"


def test_crash_brake_no_new_shorts():
    p = plan(Regime(spy_above_200=False, risk_on=False, ivp=60))
    assert p.structure == "cash"
    cheap = plan(Regime(spy_above_200=False, risk_on=False, ivp=20))
    assert cheap.structure == "put_debit"


def test_risk_on_high_iv_is_bull_put_credit():
    p = plan(Regime(spy_above_200=True, risk_on=True, ivp=70))
    assert p.structure == "bull_put_credit"
    assert p.defined_risk is True
    assert p.side == "credit"


def test_risk_on_low_iv_buys_calls():
    p = plan(Regime(spy_above_200=True, risk_on=True, ivp=20))
    assert p.structure == "call_debit"
    assert p.side == "debit"


def test_refuses_0dte_and_lab_tenor():
    assert not contest_entry_ok(dte=0, abs_delta=0.30).ok
    assert not contest_entry_ok(dte=6, abs_delta=0.30).ok
    assert contest_entry_ok(dte=7, abs_delta=0.30).ok
    assert contest_entry_ok(dte=21, abs_delta=0.30).ok
    assert not contest_entry_ok(dte=45, abs_delta=0.18).ok  # lab tenor


def test_refuses_lab_16_delta():
    assert not contest_entry_ok(dte=14, abs_delta=0.18).ok
    assert contest_entry_ok(dte=14, abs_delta=0.25).ok


def test_friday_flatten():
    d = contest_decide_exit(
        side="credit",
        entry=2.0,
        mark=1.80,
        dte=10,
        as_of=CONTEST_END,
        contest_end=CONTEST_END,
    )
    assert d["should_close"] is True
    assert d["rule"] == "flatten"


def test_size_caps_at_2pct_and_20_contracts():
    # $120 max loss / contract, $100k, 2% = $2k → 16 contracts
    n = contracts_for_risk(equity=100_000, max_loss_per_contract=120, risk_frac=0.02)
    assert n == 16
    huge = contracts_for_risk(equity=100_000, max_loss_per_contract=10, risk_frac=0.02)
    assert huge == 20
    assert contracts_for_risk(equity=100_000, max_loss_per_contract=5000, risk_frac=0.02) == 0


def test_lab_etf_stock_positions_are_contamination():
    r = refuse_lab_book(["SPY", "VEA", "IWM261016P00220000"])
    assert not r.ok
    assert r.code == "lab_contamination"
    clean = refuse_lab_book(["IWM261016P00220000", "SPY260918P00450000"])
    assert clean.ok


def test_debit_stop_and_take_profit():
    stop = contest_decide_exit(side="debit", entry=2.0, mark=1.0, dte=10, as_of=date(2026, 9, 1))
    assert stop["rule"] == "stop_loss"
    bank = contest_decide_exit(side="debit", entry=2.0, mark=3.6, dte=10, as_of=date(2026, 9, 1))
    assert bank["rule"] == "take_profit"
    hold = contest_decide_exit(side="debit", entry=2.0, mark=2.2, dte=10, as_of=date(2026, 9, 1))
    assert hold["should_close"] is False


def test_agent_contest_skips_lab_tenor_candidate():
    from filltrue.ledger import Ledger
    from filltrue.replay import AS_OF, demo_candidate, demo_chain

    broker = FakeBroker(is_open=True, fill_mode="fill", chain=demo_chain())
    agent = Agent(
        broker,
        Ledger(),
        as_of=AS_OF,
        env={"ALPACA_PAPER_TRADE": "true", "FILLTRUE_CONTEST": "true"},
    )
    event = agent.open_csp(demo_candidate())
    assert event.kind == "SKIP"
    assert broker.submitted == []


def test_agent_contest_refuses_lab_etf_book():
    from filltrue.ledger import Ledger
    from filltrue.replay import AS_OF, demo_candidate, demo_chain
    from filltrue.types import BrokerPosition

    broker = FakeBroker(is_open=True, fill_mode="fill", chain=demo_chain())
    broker._held["SPY"] = BrokerPosition(symbol="SPY", qty=10, avg_entry_price=600)
    agent = Agent(
        broker,
        Ledger(),
        as_of=AS_OF,
        env={"ALPACA_PAPER_TRADE": "true", "FILLTRUE_CONTEST": "true"},
    )
    event = agent.open_csp(demo_candidate())
    assert event.kind == "REJECT"
    assert "lab" in event.detail.lower()


def test_plan_never_returns_naked_by_default():
    for ivp in (20, 40, 70, None):
        for brake in (True, False):
            p: ContestPlan = plan(Regime(spy_above_200=brake, risk_on=brake, ivp=ivp))
            if p.structure != "cash":
                assert p.defined_risk is True
