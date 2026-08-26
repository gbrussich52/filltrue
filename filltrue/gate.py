"""Order legality. Paper only. Session-aware. Intent-correct.

The leftover-long-put bug: a stop that `buy`s without `buy_to_close` opens a
long put on top of a short that never existed (or that you just closed).
FillTrue will not submit that order.
"""

from __future__ import annotations

import os

from filltrue.types import Clock, GateResult, OrderIntent, PositionIntent


def paper_mode_ok(env: dict[str, str] | None = None) -> GateResult:
    src = env if env is not None else os.environ
    flag = (src.get("ALPACA_PAPER_TRADE") or "true").strip().lower()
    if flag in {"0", "false", "no", "live"}:
        return GateResult(
            False,
            "FillTrue refuses live capital. Set ALPACA_PAPER_TRADE=true.",
            "live_refused",
        )
    return GateResult(True, "paper", "paper")


def gate_order(
    intent: OrderIntent,
    clock: Clock,
    *,
    env: dict[str, str] | None = None,
) -> GateResult:
    paper = paper_mode_ok(env)
    if not paper.ok:
        return paper

    if intent.qty <= 0:
        return GateResult(False, "qty must be > 0", "qty")

    if intent.time_in_force.lower() != "day":
        return GateResult(
            False,
            "options TIF must be day",
            "tif",
        )

    if intent.type == "market" and not clock.is_open:
        return GateResult(
            False,
            "market order refused while session closed",
            "session_closed",
        )

    if intent.type == "limit":
        if intent.limit_price is None or intent.limit_price <= 0:
            return GateResult(False, "limit order needs a price", "no_limit")
        if not clock.is_open:
            return GateResult(
                False,
                "new entries refused while session closed (DAY limit would ghost)",
                "session_closed",
            )

    if intent.reason.startswith("close") or intent.reason.startswith("stop"):
        if intent.side != "buy":
            return GateResult(False, "closing a short put is a buy", "close_side")
        if intent.position_intent != "buy_to_close":
            return GateResult(
                False,
                "close must be buy_to_close — buy_to_open leaves a leftover long",
                "leftover_long",
            )

    if intent.reason.startswith("open") or intent.position_intent == "sell_to_open":
        if intent.side != "sell":
            return GateResult(False, "opening a CSP is a sell", "open_side")
        if intent.position_intent != "sell_to_open":
            return GateResult(False, "open must be sell_to_open", "open_intent")
        if intent.type != "limit":
            return GateResult(
                False,
                "open CSP must be a limit (market-on-close is not this agent)",
                "open_type",
            )

    if "take_profit" in intent.reason or intent.reason == "bank_it":
        return GateResult(
            False,
            "no take-profit cap — spine exits only",
            "take_profit_refused",
        )

    return GateResult(True, "allowed", "ok")


def close_intent(symbol: str, qty: float, *, reason: str) -> OrderIntent:
    return OrderIntent(
        symbol=symbol,
        side="buy",
        qty=qty,
        type="market",
        time_in_force="day",
        position_intent="buy_to_close",
        reason=reason if reason.startswith("close") or reason.startswith("stop")
        else f"close:{reason}",
    )


def open_intent(
    symbol: str,
    limit_price: float,
    *,
    qty: float = 1.0,
    client_order_id: str | None = None,
) -> OrderIntent:
    return OrderIntent(
        symbol=symbol,
        side="sell",
        qty=qty,
        type="limit",
        time_in_force="day",
        position_intent="sell_to_open",
        limit_price=limit_price,
        client_order_id=client_order_id,
        reason="open:csp",
    )


def require_intent(value: str, allowed: set[PositionIntent]) -> GateResult:
    if value not in allowed:
        return GateResult(False, f"position_intent {value} not in {sorted(allowed)}", "intent")
    return GateResult(True, "ok", "ok")
