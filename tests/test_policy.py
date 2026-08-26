"""Exits: no upside cap — only downside mitigation (trail, stop, time)."""

from __future__ import annotations

from datetime import date

from filltrue.policy import decide_exit, gate_entry, profit_frac
from filltrue.types import Candidate


def _cand(**kwargs) -> Candidate:
    base = dict(
        symbol="IWM261016P00220000",
        underlying="IWM",
        expiration=date(2026, 10, 16),
        strike=220,
        delta=-0.18,
        bid=1.12,
        dte=45,
        limit_price=1.12,
    )
    base.update(kwargs)
    return Candidate(**base)


def test_profit_frac():
    assert abs(profit_frac(2.0, 1.0) - 0.5) < 1e-9
    assert abs(profit_frac(2.0, 0.0) - 1.0) < 1e-9
    assert profit_frac(2.0, 3.0) < 0
    assert profit_frac(2.0, None) is None


def test_no_exit_at_50_or_80_or_95_if_still_running():
    for mark, peak in [(1.0, 0.5), (0.4, 0.8), (0.1, 0.95)]:
        d = decide_exit(credit=2.0, mark=mark, dte=40, peak_profit_frac=peak)
        assert d["should_close"] is False, f"mark={mark}"
        assert d["rule"] == "hold"


def test_take_profit_only_is_not_a_rule():
    d = decide_exit(credit=2.0, mark=0.01, dte=40, peak_profit_frac=0.995)
    assert d["should_close"] is False
    assert d["rule"] != "take_profit"


def test_trail_only_when_path_turns():
    d1 = decide_exit(credit=2.0, mark=0.4, dte=35, peak_profit_frac=0.0)
    assert d1["should_close"] is False
    assert abs(d1["peak_profit_frac"] - 0.8) < 1e-9
    d2 = decide_exit(credit=2.0, mark=0.8, dte=34, peak_profit_frac=0.8)
    assert d2["should_close"] is True
    assert d2["rule"] == "trail"


def test_below_trail_arm_no_trail():
    d = decide_exit(credit=2.0, mark=1.7, dte=40, peak_profit_frac=0.20)
    assert d["should_close"] is False


def test_trail_giveback_just_shy_of_threshold_holds():
    # peak 30% (armed), giveback 14 points → hold; 15 points → trail
    hold = decide_exit(credit=2.0, mark=1.68, dte=40, peak_profit_frac=0.30)
    # pf = (2-1.68)/2 = 0.16; peak-pf = 0.14
    assert hold["should_close"] is False
    fire = decide_exit(credit=2.0, mark=1.70, dte=40, peak_profit_frac=0.30)
    # pf = 0.15; peak-pf = 0.15
    assert fire["should_close"] is True
    assert fire["rule"] == "trail"


def test_stop_loss_underwater():
    d = decide_exit(credit=2.0, mark=3.0, dte=40, peak_profit_frac=0.0)
    assert d["should_close"] is True
    assert d["rule"] == "stop_loss"


def test_stop_at_exact_1_5x():
    d = decide_exit(credit=2.0, mark=3.0, dte=40)
    assert d["should_close"] is True
    just_under = decide_exit(credit=2.0, mark=2.99, dte=40)
    assert just_under["should_close"] is False
    # 1.12 × 1.5 is not a binary 1.68 — this is the live-shaped case
    messy = decide_exit(credit=1.12, mark=1.68, dte=40)
    assert messy["should_close"] is True
    assert messy["rule"] == "stop_loss"


def test_time_stop_at_21_not_22():
    hold = decide_exit(credit=2.0, mark=1.5, dte=22, peak_profit_frac=0.1)
    assert hold["should_close"] is False
    fire = decide_exit(credit=2.0, mark=1.5, dte=21, peak_profit_frac=0.1)
    assert fire["should_close"] is True
    assert fire["rule"] == "time_stop"


def test_gate_entry_band():
    assert gate_entry(_cand()).ok
    assert not gate_entry(_cand(delta=-0.15)).ok
    assert not gate_entry(_cand(delta=-0.21)).ok
    assert gate_entry(_cand(delta=-0.16)).ok
    assert gate_entry(_cand(delta=-0.20)).ok
    assert not gate_entry(_cand(dte=29)).ok
    assert gate_entry(_cand(dte=30)).ok
    assert gate_entry(_cand(dte=60)).ok
    assert not gate_entry(_cand(dte=61)).ok
    assert not gate_entry(_cand(bid=0)).ok
