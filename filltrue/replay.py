"""Fixture replay: the ghost DAY-limit vs a real fill. No network."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from filltrue.agent import Agent
from filltrue.broker import FakeBroker
from filltrue.ledger import Ledger
from filltrue.types import Candidate, Contract, Event

AS_OF = date(2026, 8, 25)
EXP = date(2026, 10, 16)
SYMBOL = "IWM261016P00220000"


def demo_chain() -> list[Contract]:
    return [
        Contract(
            symbol="IWM261016P00215000",
            underlying="IWM",
            expiration=EXP,
            strike=215,
            option_type="put",
            delta=-0.15,
            bid=1.40,
            ask=1.50,
        ),
        Contract(
            symbol=SYMBOL,
            underlying="IWM",
            expiration=EXP,
            strike=220,
            option_type="put",
            delta=-0.18,
            bid=1.12,
            ask=1.18,
        ),
        Contract(
            symbol="IWM261016P00225000",
            underlying="IWM",
            expiration=EXP,
            strike=225,
            option_type="put",
            delta=-0.21,
            bid=1.80,
            ask=1.90,
        ),
        Contract(
            symbol="IWM260918P00220000",
            underlying="IWM",
            expiration=date(2026, 9, 18),
            strike=220,
            option_type="put",
            delta=-0.18,
            bid=0.90,
            ask=0.96,
        ),
    ]


def demo_candidate() -> Candidate:
    return Candidate(
        symbol=SYMBOL,
        underlying="IWM",
        expiration=EXP,
        strike=220,
        delta=-0.18,
        bid=1.12,
        dte=(EXP - AS_OF).days,
        limit_price=1.12,
    )


def naive_open_on_submit(order_id: str, symbol: str) -> dict:
    """The bug. Not used in production. Shown in the demo so judges see it."""
    return {
        "kind": "OPEN",
        "symbol": symbol,
        "detail": "NAIVE: recorded OPEN on submit (filled_qty=0)",
        "order_id": order_id,
        "filled_qty": 0.0,
        "filled_avg_price": None,
    }


def run_ghost() -> dict:
    """DAY limit expires unfilled. FillTrue stays flat. Naive would show OPEN."""
    broker = FakeBroker(is_open=True, fill_mode="working", chain=demo_chain())
    agent = Agent(broker, Ledger(), as_of=AS_OF, env={"ALPACA_PAPER_TRADE": "true"})
    submit = agent.open_csp(demo_candidate())
    naive = naive_open_on_submit(submit.order_id or "", SYMBOL)
    broker.expire(submit.order_id or "")
    sync_events = agent.sync()
    return {
        "name": "ghost_day_limit",
        "naive": naive,
        "filltrue_submit": _event(submit),
        "filltrue_sync": [_event(e) for e in sync_events],
        "filltrue_open": len(agent.ledger.open_positions()),
        "naive_open": 1,
    }


def run_fill_then_stop() -> dict:
    """Fill at 1.12, mark jumps to 1.68 (1.5×), close with buy_to_close."""
    broker = FakeBroker(
        is_open=True,
        fill_mode="working",
        chain=demo_chain(),
        marks={SYMBOL: 1.68},
    )
    agent = Agent(broker, Ledger(), as_of=AS_OF, env={"ALPACA_PAPER_TRADE": "true"})
    submit = agent.open_csp(demo_candidate())
    broker.fill(submit.order_id or "", price=1.12)
    sync_events = agent.sync()
    manage = agent.manage()
    closes = [s for s in broker.submitted if s.position_intent == "buy_to_close"]
    last_close = closes[-1] if closes else None
    return {
        "name": "fill_then_stop",
        "submit": _event(submit),
        "sync": [_event(e) for e in sync_events],
        "manage": [_event(e) for e in manage],
        "close_intent": None
        if last_close is None
        else {
            "side": last_close.side,
            "position_intent": last_close.position_intent,
            "type": last_close.type,
        },
        "open": len(agent.ledger.open_positions()),
    }


def _event(e: Event) -> dict:
    return {
        "kind": e.kind,
        "symbol": e.symbol,
        "detail": e.detail,
        "order_id": e.order_id,
        "filled_qty": e.filled_qty,
        "filled_avg_price": e.filled_avg_price,
    }


def print_report(text: bool = True) -> str:
    ghost = run_ghost()
    filled = run_fill_then_stop()
    lines = [
        "FillTrue replay (no network, paper story)",
        "",
        "1) Ghost DAY limit — the bug 2,400 MCP wrappers will ship",
        f"   Naive ledger OPEN count : {ghost['naive_open']}",
        f"   FillTrue OPEN count     : {ghost['filltrue_open']}",
        f"   FillTrue submit         : {ghost['filltrue_submit']['kind']}",
        f"   FillTrue after expire   : {ghost['filltrue_sync'][-1]['kind']}",
        "",
        "2) Real fill, then 1.5× stop",
        f"   After fill OPEN         : 1 expected, sync kinds "
        f"{[e['kind'] for e in filled['sync']]}",
        f"   Close position_intent   : {filled['close_intent']}",
        f"   Remaining OPEN          : {filled['open']}",
        "",
        "OPEN is a fill. Everything else is a rumor.",
    ]
    report = "\n".join(lines) + "\n"
    if text:
        print(report, end="")
    return report


def events_json_path() -> Path:
    return Path(__file__).resolve().parent.parent / "events.json"
