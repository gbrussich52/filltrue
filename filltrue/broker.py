"""Broker protocol + FakeBroker. Alpaca adapter is optional (alpaca-py)."""

from __future__ import annotations

import itertools
from typing import Protocol

from filltrue.types import (
    BrokerOrder,
    BrokerPosition,
    Clock,
    Contract,
    OrderIntent,
)


class Broker(Protocol):
    def clock(self) -> Clock: ...
    def submit(self, intent: OrderIntent) -> BrokerOrder: ...
    def get_order(self, order_id: str) -> BrokerOrder: ...
    def positions(self) -> list[BrokerPosition]: ...
    def chain(self, underlying: str) -> list[Contract]: ...
    def quote_mark(self, symbol: str) -> float | None: ...


class FakeBroker:
    """Deterministic broker for tests and the public demo.

    fill_mode:
      fill     — submit comes back filled
      expire   — submit is accepted, sync returns expired / qty 0 (the ghost)
      working  — stays new until you call `expire(id)` or `fill(id)`
      lie      — status=filled, filled_qty=0 (status-word trap)
    """

    def __init__(
        self,
        *,
        is_open: bool = True,
        fill_mode: str = "working",
        chain: list[Contract] | None = None,
        marks: dict[str, float] | None = None,
    ) -> None:
        self._is_open = is_open
        self.fill_mode = fill_mode
        self._chain = chain or []
        self.marks = marks or {}
        self.orders: dict[str, BrokerOrder] = {}
        self._held: dict[str, BrokerPosition] = {}
        self._ids = itertools.count(1)
        self.submitted: list[OrderIntent] = []

    def clock(self) -> Clock:
        return Clock(is_open=self._is_open, timestamp="fake")

    def set_open(self, is_open: bool) -> None:
        self._is_open = is_open

    def submit(self, intent: OrderIntent) -> BrokerOrder:
        self.submitted.append(intent)
        oid = f"ord-{next(self._ids)}"
        cid = intent.client_order_id or oid
        order = BrokerOrder(
            id=oid,
            client_order_id=cid,
            symbol=intent.symbol,
            side=intent.side,
            qty=intent.qty,
            status="new",
            filled_qty=0.0,
            filled_avg_price=None,
            type=intent.type,
            position_intent=intent.position_intent,
            limit_price=intent.limit_price,
        )
        closing = intent.position_intent == "buy_to_close"
        if self.fill_mode == "lie" and not closing:
            order.status = "filled"
            order.filled_qty = 0.0
            order.filled_avg_price = None
        elif self.fill_mode == "fill" or (closing and self._is_open and self.fill_mode != "expire"):
            order.status = "filled"
            order.filled_qty = intent.qty
            order.filled_avg_price = intent.limit_price or self.marks.get(intent.symbol) or 1.0
            if intent.side == "sell":
                self._held[intent.symbol] = BrokerPosition(
                    symbol=intent.symbol,
                    qty=-intent.qty,
                    avg_entry_price=order.filled_avg_price,
                )
            elif intent.side == "buy":
                self._held.pop(intent.symbol, None)
        self.orders[oid] = order
        return order

    def get_order(self, order_id: str) -> BrokerOrder:
        return self.orders[order_id]

    def positions(self) -> list[BrokerPosition]:
        return list(self._held.values())

    def chain(self, underlying: str) -> list[Contract]:
        return [c for c in self._chain if c.underlying == underlying]

    def quote_mark(self, symbol: str) -> float | None:
        return self.marks.get(symbol)

    def expire(self, order_id: str) -> BrokerOrder:
        o = self.orders[order_id]
        o.status = "expired"
        o.filled_qty = 0.0
        o.filled_avg_price = None
        return o

    def fill(self, order_id: str, *, price: float) -> BrokerOrder:
        o = self.orders[order_id]
        o.status = "filled"
        o.filled_qty = o.qty
        o.filled_avg_price = price
        if o.side == "sell":
            self._held[o.symbol] = BrokerPosition(
                symbol=o.symbol, qty=-o.qty, avg_entry_price=price
            )
        elif o.side == "buy":
            self._held.pop(o.symbol, None)
        return o
