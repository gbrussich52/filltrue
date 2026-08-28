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


def test_contest_harvests_when_thesis_dies_green():
    d = contest_decide_exit(
        side="credit",
        entry=2.0,
        mark=1.6,
        dte=14,
        as_of=date(2026, 9, 1),
        conditions_still_fit=False,
    )
    assert d["should_close"] is True
    assert d["rule"] == "condition_invalidation"


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


class TestRiskDials:
    """Caps were hardcoded lab numbers; a 5-session tournament needs its own."""

    @staticmethod
    def _reload(**env):
        import importlib, os
        for k in ("FILLTRUE_RISK_FRAC", "FILLTRUE_MAX_GROSS",
                  "FILLTRUE_MAX_TICKETS", "FILLTRUE_MAX_CONTRACTS"):
            os.environ.pop(k, None)
        os.environ.update({k: str(v) for k, v in env.items()})
        import filltrue.contest as c
        return importlib.reload(c)

    def teardown_method(self):
        self._reload()

    def test_lab_defaults_when_unset(self):
        c = self._reload()
        assert (c.RISK_FRAC_PER_TICKET, c.MAX_GROSS_RISK_FRAC) == (0.02, 0.08)
        assert (c.MAX_TICKETS, c.MAX_CONTRACTS) == (4, 20)

    def test_contest_posture_applies(self):
        c = self._reload(FILLTRUE_RISK_FRAC=0.35, FILLTRUE_MAX_GROSS=0.90,
                         FILLTRUE_MAX_TICKETS=3, FILLTRUE_MAX_CONTRACTS=500)
        assert c.RISK_FRAC_PER_TICKET == 0.35
        assert c.MAX_GROSS_RISK_FRAC == 0.90
        assert (c.MAX_TICKETS, c.MAX_CONTRACTS) == (3, 500)

    def test_sizing_scales_with_the_dial(self):
        lab = self._reload()
        n_lab = lab.contracts_for_risk(equity=100_000, max_loss_per_contract=500)
        hot = self._reload(FILLTRUE_RISK_FRAC=0.35, FILLTRUE_MAX_CONTRACTS=500)
        n_hot = hot.contracts_for_risk(equity=100_000, max_loss_per_contract=500)
        assert n_lab == 4 and n_hot == 70, f"{n_lab=} {n_hot=}"

    def test_max_contracts_still_binds(self):
        c = self._reload(FILLTRUE_RISK_FRAC=0.90, FILLTRUE_MAX_CONTRACTS=10)
        assert c.contracts_for_risk(equity=100_000, max_loss_per_contract=100) == 10

    def test_garbage_and_negative_fall_back_to_default(self):
        for bad in ("abc", "-0.5", "0", ""):
            c = self._reload(FILLTRUE_RISK_FRAC=bad)
            assert c.RISK_FRAC_PER_TICKET == 0.02, f"{bad!r} was accepted"

    def test_sizing_never_negative(self):
        c = self._reload(FILLTRUE_RISK_FRAC=0.50)
        assert c.contracts_for_risk(equity=100_000, max_loss_per_contract=1e9) == 0
        assert c.contracts_for_risk(equity=0, max_loss_per_contract=500) == 0
