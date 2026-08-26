"""Session, paper-only, leftover-long, take-profit refusal."""

from __future__ import annotations

from filltrue.gate import close_intent, gate_order, open_intent, paper_mode_ok
from filltrue.types import Clock, OrderIntent


OPEN = Clock(is_open=True)
CLOSED = Clock(is_open=False)


def test_paper_mode_refuses_live():
    assert paper_mode_ok({"ALPACA_PAPER_TRADE": "true"}).ok
    assert not paper_mode_ok({"ALPACA_PAPER_TRADE": "false"}).ok
    assert not paper_mode_ok({"ALPACA_PAPER_TRADE": "live"}).ok


def test_market_order_refused_when_closed():
    intent = close_intent("IWM261016P00220000", 1, reason="close:stop_loss")
    r = gate_order(intent, CLOSED, env={"ALPACA_PAPER_TRADE": "true"})
    assert not r.ok
    assert r.code == "session_closed"


def test_limit_open_refused_when_closed():
    intent = open_intent("IWM261016P00220000", 1.12)
    r = gate_order(intent, CLOSED, env={"ALPACA_PAPER_TRADE": "true"})
    assert not r.ok
    assert r.code == "session_closed"


def test_open_limit_allowed_when_open():
    intent = open_intent("IWM261016P00220000", 1.12)
    r = gate_order(intent, OPEN, env={"ALPACA_PAPER_TRADE": "true"})
    assert r.ok


def test_close_must_be_buy_to_close():
    bad = OrderIntent(
        symbol="IWM261016P00220000",
        side="buy",
        qty=1,
        type="market",
        position_intent="buy_to_open",
        reason="close:stop_loss",
    )
    r = gate_order(bad, OPEN, env={"ALPACA_PAPER_TRADE": "true"})
    assert not r.ok
    assert r.code == "leftover_long"


def test_close_intent_helper_is_buy_to_close():
    intent = close_intent("IWM261016P00220000", 1, reason="stop_loss")
    assert intent.side == "buy"
    assert intent.position_intent == "buy_to_close"
    r = gate_order(intent, OPEN, env={"ALPACA_PAPER_TRADE": "true"})
    assert r.ok


def test_take_profit_refused():
    intent = OrderIntent(
        symbol="X",
        side="buy",
        qty=1,
        type="market",
        position_intent="buy_to_close",
        reason="take_profit_50",
    )
    r = gate_order(intent, OPEN, env={"ALPACA_PAPER_TRADE": "true"})
    assert not r.ok
    assert r.code == "take_profit_refused"


def test_live_env_blocks_even_valid_intent():
    intent = open_intent("IWM261016P00220000", 1.12)
    r = gate_order(intent, OPEN, env={"ALPACA_PAPER_TRADE": "false"})
    assert not r.ok
    assert r.code == "live_refused"
