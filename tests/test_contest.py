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


class TestDynamicSizing:
    """Size is computed per entry, not configured once."""

    def test_cap_escalates_as_sessions_run_out(self):
        from filltrue.contest import survival_cap
        caps = [survival_cap(k) for k in (5, 4, 3, 2, 1)]
        assert caps == sorted(caps), f"cap must rise as k falls: {caps}"
        assert 0.20 < caps[0] < 0.30 and 0.70 < caps[-1] < 0.80

    def test_cap_survives_its_own_worst_case(self):
        """k total losses at the cap must leave the retained floor."""
        from filltrue.contest import RETAIN_AFTER_WORST_CASE, survival_cap
        for k in range(1, 8):
            f = survival_cap(k)
            assert (1 - f) ** k == __import__("pytest").approx(
                RETAIN_AFTER_WORST_CASE, rel=1e-9)

    def test_cap_never_reaches_full_deployment(self):
        from filltrue.contest import survival_cap
        assert all(survival_cap(k) < 1.0 for k in (1, 2, 5, 50))

    def test_neutral_signal_sizes_small_without_a_rule(self):
        from filltrue.contest import dynamic_risk_frac
        d = dynamic_risk_frac(equity=100_000, start_equity=100_000,
                              sessions_remaining=5, spy_above_200=False,
                              risk_on=False, ivp=50)
        assert d["risk_frac"] < 0.05

    def test_extreme_iv_either_direction_is_strong(self):
        from filltrue.contest import conviction
        lo = conviction(spy_above_200=True, risk_on=True, ivp=5)
        hi = conviction(spy_above_200=True, risk_on=True, ivp=95)
        assert lo == __import__("pytest").approx(hi, abs=0.02)

    def test_behind_pushes_and_ahead_eases(self):
        from filltrue.contest import tournament_tilt
        behind = tournament_tilt(equity=70_000, start_equity=100_000)
        flat = tournament_tilt(equity=100_000, start_equity=100_000)
        ahead = tournament_tilt(equity=150_000, start_equity=100_000)
        assert behind > flat > ahead
        assert ahead >= 0.6, "must not shrink to nothing while defending a lead"

    def test_tilt_is_bounded(self):
        from filltrue.contest import tournament_tilt
        assert tournament_tilt(equity=1, start_equity=100_000) <= 2.0
        assert tournament_tilt(equity=10_000_000, start_equity=100_000) >= 0.6

    def test_result_never_exceeds_its_own_cap(self):
        from filltrue.contest import dynamic_risk_frac, survival_cap
        for k in (1, 2, 3, 5):
            for eq in (10_000, 100_000, 250_000):
                d = dynamic_risk_frac(equity=eq, start_equity=100_000,
                                      sessions_remaining=k, spy_above_200=True,
                                      risk_on=True, ivp=2)
                assert d["risk_frac"] <= survival_cap(k) + 1e-9

    def test_degenerate_inputs_do_not_crash(self):
        from filltrue.contest import dynamic_risk_frac, tournament_tilt
        assert tournament_tilt(equity=100, start_equity=0) == 1.0
        d = dynamic_risk_frac(equity=0, start_equity=100_000, sessions_remaining=0,
                              spy_above_200=True, risk_on=True, ivp=12)
        assert d["risk_frac"] >= 0 and d["dollars"] == 0

    def test_every_size_explains_itself(self):
        from filltrue.contest import dynamic_risk_frac
        d = dynamic_risk_frac(equity=100_000, start_equity=100_000,
                              sessions_remaining=5, spy_above_200=True,
                              risk_on=True, ivp=12)
        assert {"survival_cap", "conviction", "tilt", "why"} <= set(d)
        assert "cap" in d["why"] and "conviction" in d["why"]
