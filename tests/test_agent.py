from __future__ import annotations

from datetime import date

from filltrue.agent import Agent, mcp_place_payload
from filltrue.broker import FakeBroker
from filltrue.gate import open_intent
from filltrue.ledger import Ledger
from filltrue.replay import AS_OF, SYMBOL, demo_candidate, demo_chain, run_fill_then_stop, run_ghost


def _agent(broker: FakeBroker) -> Agent:
    return Agent(
        broker,
        Ledger(),
        as_of=AS_OF,
        env={"ALPACA_PAPER_TRADE": "true"},
    )


def test_fill_then_open():
    broker = FakeBroker(is_open=True, fill_mode="fill", chain=demo_chain())
    agent = _agent(broker)
    event = agent.open_csp(demo_candidate())
    assert event.kind == "OPEN"
    assert len(agent.ledger.open_positions()) == 1
    assert agent.ledger.open_positions()[0].credit == 1.12


def test_expire_stays_flat():
    ghost = run_ghost()
    assert ghost["naive_open"] == 1
    assert ghost["filltrue_open"] == 0
    assert ghost["filltrue_submit"]["kind"] == "WORKING"
    assert ghost["filltrue_sync"][-1]["kind"] == "UNFILLED"


def test_stop_uses_buy_to_close_not_buy_to_open():
    result = run_fill_then_stop()
    assert result["close_intent"]["position_intent"] == "buy_to_close"
    assert result["close_intent"]["side"] == "buy"
    assert result["open"] == 0


def test_live_env_cannot_open():
    broker = FakeBroker(is_open=True, fill_mode="fill", chain=demo_chain())
    agent = Agent(
        broker, Ledger(), as_of=AS_OF, env={"ALPACA_PAPER_TRADE": "false"}
    )
    event = agent.open_csp(demo_candidate())
    assert event.kind == "REJECT"
    assert agent.ledger.open_positions() == []
    assert broker.submitted == []


def test_closed_session_cannot_open():
    broker = FakeBroker(is_open=False, fill_mode="fill", chain=demo_chain())
    agent = _agent(broker)
    event = agent.open_csp(demo_candidate())
    assert event.kind == "REJECT"
    assert broker.submitted == []


def test_mcp_payload_is_limit_sell_to_open():
    intent = open_intent(SYMBOL, 1.12, client_order_id="filltrue-test")
    payload = mcp_place_payload(intent)
    assert payload["type"] == "limit"
    assert payload["side"] == "sell"
    assert payload["position_intent"] == "sell_to_open"
    assert payload["time_in_force"] == "day"
    assert payload["limit_price"] == "1.12"
    assert payload["qty"] == "1"


def test_max_open_skips_second():
    broker = FakeBroker(is_open=True, fill_mode="fill", chain=demo_chain())
    agent = _agent(broker)
    agent.max_open = 1
    assert agent.open_csp(demo_candidate()).kind == "OPEN"
    second = agent.open_csp(demo_candidate())
    assert second.kind == "SKIP"


def test_time_stop_closes():
    broker = FakeBroker(
        is_open=True,
        fill_mode="fill",
        chain=demo_chain(),
        marks={SYMBOL: 0.80},
    )
    agent = _agent(broker)
    agent.open_csp(demo_candidate())
    # Jump as_of to 21 DTE
    agent.as_of = date(2026, 9, 25)  # Oct 16 - 21 days
    events = agent.manage()
    kinds = {e.kind for e in events}
    assert "CLOSE" in kinds
    assert agent.ledger.open_positions() == []
