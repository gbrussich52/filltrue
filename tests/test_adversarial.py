"""Aim to break it. If these pass, the obvious lies are closed."""

from __future__ import annotations

from filltrue.agent import Agent
from filltrue.broker import FakeBroker
from filltrue.ledger import Ledger, is_true_fill
from filltrue.replay import AS_OF, SYMBOL, demo_candidate, demo_chain
from filltrue.types import BrokerOrder


def test_partial_fill_does_not_open_full_qty():
    assert not is_true_fill(qty=1, filled_qty=0.5, filled_avg_price=1.12)


def test_string_zero_qty_is_not_a_fill():
    assert not is_true_fill(qty=1, filled_qty="0", filled_avg_price="0")
    assert not is_true_fill(qty=1, filled_qty="0.0", filled_avg_price=1.12)


def test_negative_price_is_not_a_fill():
    assert not is_true_fill(qty=1, filled_qty=1, filled_avg_price=-1.12)


def test_double_sync_does_not_duplicate_open():
    broker = FakeBroker(is_open=True, fill_mode="working", chain=demo_chain())
    agent = Agent(
        broker, Ledger(), as_of=AS_OF, env={"ALPACA_PAPER_TRADE": "true", "FILLTRUE_CONTEST": "false"}
    )
    submit = agent.open_csp(demo_candidate())
    broker.fill(submit.order_id, price=1.12)
    agent.sync()
    agent.sync()
    assert len(agent.ledger.open_positions()) == 1
    opens = [e for e in agent.ledger.events if e.kind == "OPEN"]
    assert len(opens) == 1


def test_lie_mode_status_filled_qty_zero():
    broker = FakeBroker(is_open=True, fill_mode="lie", chain=demo_chain())
    agent = Agent(
        broker, Ledger(), as_of=AS_OF, env={"ALPACA_PAPER_TRADE": "true", "FILLTRUE_CONTEST": "false"}
    )
    event = agent.open_csp(demo_candidate())
    assert event.kind != "OPEN"
    assert agent.ledger.open_positions() == []


def test_empty_string_fill_fields():
    order = BrokerOrder(
        id="x",
        client_order_id="x",
        symbol=SYMBOL,
        side="sell",
        qty=1,
        status="filled",
        filled_qty="",
        filled_avg_price="",
    )
    ledger = Ledger()
    ledger.record_submit(order)
    assert ledger.open_positions() == []


def test_sync_unknown_order_does_not_crash():
    ledger = Ledger()
    event = ledger.sync_order(
        BrokerOrder(
            id="never-submitted",
            client_order_id="x",
            symbol=SYMBOL,
            side="sell",
            qty=1,
            status="expired",
        )
    )
    assert event.kind == "UNFILLED"


def test_close_unknown_is_reject():
    ledger = Ledger()
    event = ledger.record_close("nope", reason="stop")
    assert event.kind == "REJECT"
