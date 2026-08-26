"""THE test. A DAY limit that expires unfilled must never become an open short.

This is the bug FillTrue exists to kill. A naive agent does:

    order = submit_order(...)
    ledger.status = "OPEN"          # lie

Alpaca returns status=new/accepted, filled_qty=0. At 16:00 the DAY order
expires. The naive ledger still shows a short. FillTrue cannot.
"""

from __future__ import annotations

from filltrue.agent import Agent
from filltrue.broker import FakeBroker
from filltrue.ledger import Ledger, is_true_fill
from filltrue.replay import SYMBOL, demo_candidate, demo_chain, naive_open_on_submit
from filltrue.types import BrokerOrder, BrokerPosition


def _order(**kwargs) -> BrokerOrder:
    base = dict(
        id="ord-ghost",
        client_order_id="filltrue-ghost",
        symbol=SYMBOL,
        side="sell",
        qty=1.0,
        status="new",
        filled_qty=0.0,
        filled_avg_price=None,
        type="limit",
        position_intent="sell_to_open",
        limit_price=1.12,
    )
    base.update(kwargs)
    return BrokerOrder(**base)


def test_is_true_fill_ignores_status_word():
    assert not is_true_fill(qty=1, filled_qty=0, filled_avg_price=None, status="filled")
    assert not is_true_fill(qty=1, filled_qty=0, filled_avg_price=1.12, status="filled")
    assert not is_true_fill(qty=1, filled_qty=1, filled_avg_price=None, status="filled")
    assert is_true_fill(qty=1, filled_qty=1, filled_avg_price=1.12, status="new")
    assert is_true_fill(qty=1, filled_qty="1", filled_avg_price="1.12", status="accepted")


def test_submit_is_working_not_open():
    ledger = Ledger()
    event = ledger.record_submit(_order())
    assert event.kind == "WORKING"
    assert ledger.open_positions() == []


def test_day_limit_expired_unfilled_does_not_open():
    ledger = Ledger()
    ledger.record_submit(_order())
    event = ledger.sync_order(_order(status="expired", filled_qty=0, filled_avg_price=None))
    assert event.kind == "UNFILLED"
    assert ledger.open_positions() == []
    assert "OPEN" not in {e.kind for e in ledger.events}


def test_status_filled_with_qty_zero_is_not_a_fill():
    ledger = Ledger()
    ledger.record_submit(_order())
    event = ledger.sync_order(_order(status="filled", filled_qty=0, filled_avg_price=None))
    assert event.kind == "UNFILLED"
    assert ledger.open_positions() == []


def test_real_fill_opens():
    ledger = Ledger()
    ledger.record_submit(_order())
    event = ledger.sync_order(_order(status="filled", filled_qty=1, filled_avg_price=1.12))
    assert event.kind == "OPEN"
    assert len(ledger.open_positions()) == 1
    assert ledger.open_positions()[0].credit == 1.12


def test_naive_would_have_shown_open():
    naive = naive_open_on_submit("ord-ghost", SYMBOL)
    assert naive["kind"] == "OPEN"
    assert naive["filled_qty"] == 0.0
    ledger = Ledger()
    ledger.record_submit(_order())
    assert ledger.open_positions() == []


def test_agent_ghost_path_end_to_end():
    broker = FakeBroker(is_open=True, fill_mode="working", chain=demo_chain())
    agent = Agent(
        broker, Ledger(), env={"ALPACA_PAPER_TRADE": "true"},
        as_of=demo_candidate().expiration.replace(year=2026, month=8, day=25),
    )
    # as_of in replay is 2026-08-25; don't depend on today()
    from datetime import date

    agent.as_of = date(2026, 8, 25)
    submit = agent.open_csp(demo_candidate())
    assert submit.kind == "WORKING"
    assert agent.ledger.open_positions() == []
    broker.expire(submit.order_id)
    synced = agent.sync()
    assert synced[-1].kind == "UNFILLED"
    assert agent.ledger.open_positions() == []


def test_reconcile_clears_local_open_missing_at_broker():
    ledger = Ledger()
    ledger.record_submit(_order())
    ledger.sync_order(_order(status="filled", filled_qty=1, filled_avg_price=1.12))
    assert len(ledger.open_positions()) == 1
    events = ledger.reconcile([])  # broker holds nothing
    assert events[0].kind == "GHOST_CLEARED"
    assert ledger.open_positions() == []


def test_reconcile_keeps_real_short():
    ledger = Ledger()
    ledger.record_submit(_order())
    ledger.sync_order(_order(status="filled", filled_qty=1, filled_avg_price=1.12))
    events = ledger.reconcile(
        [BrokerPosition(symbol=SYMBOL, qty=-1, avg_entry_price=1.12)]
    )
    assert events == []
    assert len(ledger.open_positions()) == 1
