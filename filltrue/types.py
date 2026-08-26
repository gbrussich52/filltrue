"""Shared types for FillTrue. Frozen shapes — policy, ledger, picker, agent all import these."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal


Side = Literal["buy", "sell"]
OrderType = Literal["limit", "market"]
PositionIntent = Literal[
    "buy_to_open",
    "buy_to_close",
    "sell_to_open",
    "sell_to_close",
]
EventKind = Literal[
    "SUBMIT",
    "WORKING",
    "OPEN",
    "UNFILLED",
    "CLOSE",
    "REJECT",
    "HOLD",
    "SKIP",
    "GHOST_CLEARED",
]


@dataclass(frozen=True)
class Clock:
    is_open: bool
    timestamp: str = ""


@dataclass(frozen=True)
class Contract:
    symbol: str
    underlying: str
    expiration: date
    strike: float
    option_type: Literal["put", "call"]
    delta: float | None
    bid: float | None
    ask: float | None
    iv: float | None = None


@dataclass(frozen=True)
class Candidate:
    symbol: str
    underlying: str
    expiration: date
    strike: float
    delta: float
    bid: float
    dte: int
    limit_price: float


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: Side
    qty: float
    type: OrderType
    time_in_force: str = "day"
    position_intent: PositionIntent = "sell_to_open"
    limit_price: float | None = None
    client_order_id: str | None = None
    reason: str = ""


@dataclass
class BrokerOrder:
    id: str
    client_order_id: str
    symbol: str
    side: str
    qty: float
    status: str
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    type: str = "limit"
    position_intent: str | None = None
    limit_price: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    qty: float  # signed: short puts are negative
    avg_entry_price: float | None = None


@dataclass
class Event:
    kind: EventKind
    symbol: str
    detail: str
    order_id: str | None = None
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    ts: str = ""


@dataclass
class OpenPosition:
    order_id: str
    symbol: str
    qty: float
    credit: float
    expiration: date
    strike: float
    underlying: str
    delta: float | None = None
    peak_profit_frac: float = 0.0
    filled_at: str = ""
    client_order_id: str = ""


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reason: str
    code: str = ""
