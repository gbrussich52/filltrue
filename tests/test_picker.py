from __future__ import annotations

from datetime import date

from filltrue.occ import build_occ, parse_occ
from filltrue.picker import pick_csp
from filltrue.replay import AS_OF, SYMBOL, demo_chain


def test_pick_18_delta_45ish_dte():
    cand = pick_csp(demo_chain(), as_of=AS_OF, underlying="IWM")
    assert cand is not None
    assert cand.symbol == SYMBOL
    assert abs(abs(cand.delta) - 0.18) < 1e-9
    assert cand.limit_price == 1.12


def test_skips_15_and_21_delta_and_short_dte():
    cand = pick_csp(demo_chain(), as_of=AS_OF, underlying="IWM")
    assert cand is not None
    assert cand.symbol != "IWM261016P00215000"
    assert cand.symbol != "IWM261016P00225000"
    assert cand.symbol != "IWM260918P00220000"


def test_no_bid_skipped():
    chain = demo_chain()
    dead = [
        c
        if c.symbol != SYMBOL
        else type(c)(
            **{**c.__dict__, "bid": None},
        )
        for c in chain
    ]
    assert pick_csp(dead, as_of=AS_OF, underlying="IWM") is None


def test_wrong_underlying_ignored():
    assert pick_csp(demo_chain(), as_of=AS_OF, underlying="SPY") is None


def test_occ_roundtrip():
    exp = date(2026, 10, 16)
    sym = build_occ("IWM", exp, "put", 220)
    assert sym == "IWM261016P00220000"
    parsed = parse_occ(sym)
    assert parsed["underlying"] == "IWM"
    assert parsed["expiration"] == exp
    assert parsed["strike"] == 220.0
    assert parsed["option_type"] == "put"
