"""Broker-truth ledger.

The whole product is this file.

Naive agents record OPEN the moment `submit_order` returns. Alpaca will happily
hand you an order id with status `new` / `accepted` and `filled_qty=0`. A DAY
limit that expires unfilled is then a ghost short: the ledger thinks you are
short premium the broker never sold.

FillTrue:

* submit → WORKING, never OPEN
* OPEN only when `is_true_fill` — filled_qty covers the order AND there is a
  real average fill price
* expired / canceled / rejected / done_for_day with no fill → UNFILLED
* `status=filled` with qty 0 is not a fill (broker-word vs broker-qty)
* reconcile: a local OPEN missing from broker positions is GHOST_CLEARED
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable

from filltrue.occ import parse_occ
from filltrue.types import (
    BrokerOrder,
    BrokerPosition,
    Event,
    OpenPosition,
)

_DEAD = frozenset(
    {
        "expired",
        "canceled",
        "cancelled",
        "rejected",
        "done_for_day",
        "replaced",
    }
)


def _qty(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _price(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return n


def is_true_fill(
    *,
    qty: float,
    filled_qty: Any,
    filled_avg_price: Any,
    status: str | None = None,
) -> bool:
    """OPEN requires a real fill, not a status word.

    `status=filled` with qty 0 is a lie. `status=new` with qty filled is truth.
    Status is ignored on purpose.
    """
    del status  # status is a rumor; qty+price are the fill
    want = _qty(qty)
    got = _qty(filled_qty)
    avg = _price(filled_avg_price)
    if want <= 0:
        return False
    if got + 1e-12 < want:
        return False
    return avg is not None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Ledger:
    """Durable-enough in-memory ledger. Serialize with `to_dict` / `from_dict`."""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self.working: dict[str, BrokerOrder] = {}
        self.open: dict[str, OpenPosition] = {}
        self.closed: list[OpenPosition] = []
        self.unfilled: list[BrokerOrder] = []

    def open_positions(self) -> list[OpenPosition]:
        return list(self.open.values())

    def record_submit(
        self,
        order: BrokerOrder,
        *,
        ts: str | None = None,
    ) -> Event:
        """Submit is WORKING. Calling this never creates an OPEN position."""
        event = Event(
            kind="WORKING",
            symbol=order.symbol,
            detail=(
                f"submitted {order.side} {order.qty} {order.symbol} "
                f"status={order.status} filled_qty={_qty(order.filled_qty)}"
            ),
            order_id=order.id,
            filled_qty=_qty(order.filled_qty),
            filled_avg_price=_price(order.filled_avg_price),
            ts=ts or _now(),
        )
        self.working[order.id] = order
        self.events.append(event)
        if is_true_fill(
            qty=order.qty,
            filled_qty=order.filled_qty,
            filled_avg_price=order.filled_avg_price,
            status=order.status,
        ):
            return self._promote(order, ts=event.ts)
        return event

    def sync_order(
        self,
        broker_order: BrokerOrder,
        *,
        expiration: date | None = None,
        strike: float | None = None,
        underlying: str | None = None,
        delta: float | None = None,
        ts: str | None = None,
    ) -> Event:
        """Bring one order up to broker truth."""
        oid = broker_order.id
        self.working[oid] = broker_order
        stamp = ts or _now()

        if is_true_fill(
            qty=broker_order.qty,
            filled_qty=broker_order.filled_qty,
            filled_avg_price=broker_order.filled_avg_price,
            status=broker_order.status,
        ):
            if oid in self.open:
                return Event(
                    kind="HOLD",
                    symbol=broker_order.symbol,
                    detail="already OPEN — idempotent sync",
                    order_id=oid,
                    ts=stamp,
                )
            return self._promote(
                broker_order,
                expiration=expiration,
                strike=strike,
                underlying=underlying,
                delta=delta,
                ts=stamp,
            )

        status = (broker_order.status or "").lower()
        if status in _DEAD or status == "filled":
            # filled-without-qty falls through here too
            return self._unfilled(broker_order, ts=stamp)

        event = Event(
            kind="WORKING",
            symbol=broker_order.symbol,
            detail=(
                f"still working status={broker_order.status} "
                f"filled_qty={_qty(broker_order.filled_qty)}"
            ),
            order_id=oid,
            filled_qty=_qty(broker_order.filled_qty),
            ts=stamp,
        )
        self.events.append(event)
        return event

    def reconcile(
        self,
        broker_positions: Iterable[BrokerPosition],
        *,
        ts: str | None = None,
    ) -> list[Event]:
        """Local OPEN that the broker does not hold is a ghost. Clear it."""
        stamp = ts or _now()
        held = {
            p.symbol: p
            for p in broker_positions
            if _qty(p.qty) < 0  # short options
        }
        out: list[Event] = []
        for oid, pos in list(self.open.items()):
            broker = held.get(pos.symbol)
            if broker is None:
                event = Event(
                    kind="GHOST_CLEARED",
                    symbol=pos.symbol,
                    detail=(
                        "local OPEN not present at broker — "
                        "cleared (never a real short)"
                    ),
                    order_id=oid,
                    ts=stamp,
                )
                self.events.append(event)
                del self.open[oid]
                out.append(event)
        return out

    def record_close(
        self,
        order_id: str,
        *,
        reason: str,
        ts: str | None = None,
    ) -> Event:
        stamp = ts or _now()
        pos = self.open.pop(order_id, None)
        if pos is None:
            event = Event(
                kind="REJECT",
                symbol="",
                detail=f"close of unknown OPEN {order_id}",
                order_id=order_id,
                ts=stamp,
            )
            self.events.append(event)
            return event
        self.closed.append(pos)
        event = Event(
            kind="CLOSE",
            symbol=pos.symbol,
            detail=reason,
            order_id=order_id,
            ts=stamp,
        )
        self.events.append(event)
        return event

    def to_dict(self) -> dict[str, Any]:
        def pos(p: OpenPosition) -> dict[str, Any]:
            return {
                "order_id": p.order_id,
                "symbol": p.symbol,
                "qty": p.qty,
                "credit": p.credit,
                "expiration": p.expiration.isoformat(),
                "strike": p.strike,
                "underlying": p.underlying,
                "delta": p.delta,
                "peak_profit_frac": p.peak_profit_frac,
                "filled_at": p.filled_at,
                "client_order_id": p.client_order_id,
            }

        return {
            "events": [e.__dict__ for e in self.events],
            "open": [pos(p) for p in self.open.values()],
            "closed": [pos(p) for p in self.closed],
            "working": [o.__dict__ for o in self.working.values()],
        }

    def _promote(
        self,
        order: BrokerOrder,
        *,
        expiration: date | None = None,
        strike: float | None = None,
        underlying: str | None = None,
        delta: float | None = None,
        ts: str = "",
    ) -> Event:
        credit = _price(order.filled_avg_price) or 0.0
        if expiration is None or strike is None or not underlying:
            try:
                meta = parse_occ(order.symbol)
            except ValueError:
                meta = None
            if meta is not None:
                expiration = expiration or meta["expiration"]
                strike = strike if strike is not None else meta["strike"]
                underlying = underlying or meta["underlying"]
        exp = expiration or date.max
        pos = OpenPosition(
            order_id=order.id,
            symbol=order.symbol,
            qty=_qty(order.qty),
            credit=credit,
            expiration=exp,
            strike=strike or 0.0,
            underlying=underlying or "",
            delta=delta,
            filled_at=ts,
            client_order_id=order.client_order_id,
        )
        self.open[order.id] = pos
        self.working.pop(order.id, None)
        event = Event(
            kind="OPEN",
            symbol=order.symbol,
            detail=f"broker filled {pos.qty} @ {credit:.2f}",
            order_id=order.id,
            filled_qty=_qty(order.filled_qty),
            filled_avg_price=credit,
            ts=ts,
        )
        self.events.append(event)
        return event

    def _unfilled(self, order: BrokerOrder, *, ts: str) -> Event:
        self.working.pop(order.id, None)
        self.unfilled.append(order)
        event = Event(
            kind="UNFILLED",
            symbol=order.symbol,
            detail=(
                f"no fill — status={order.status} "
                f"filled_qty={_qty(order.filled_qty)} "
                f"(not OPEN)"
            ),
            order_id=order.id,
            filled_qty=_qty(order.filled_qty),
            filled_avg_price=_price(order.filled_avg_price),
            ts=ts,
        )
        self.events.append(event)
        return event
