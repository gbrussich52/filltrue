"""FillTrue agent loop. Paper only. Ledger is source of local truth."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import os

from filltrue.broker import Broker
from filltrue.contest import (
    DELTA_HI as CONTEST_DELTA_HI,
    DELTA_LO as CONTEST_DELTA_LO,
    DTE_MAX as CONTEST_DTE_MAX,
    DTE_MIN as CONTEST_DTE_MIN,
    DTE_TARGET as CONTEST_DTE_TARGET,
    MAX_TICKETS,
    TARGET_DELTA as CONTEST_TARGET_DELTA,
    contest_decide_exit,
    contest_entry_ok,
    refuse_lab_book,
)
from filltrue.gate import close_intent, gate_order, open_intent, paper_mode_ok
from filltrue.ledger import Ledger
from filltrue.occ import parse_occ
from filltrue.picker import pick_csp
from filltrue.policy import decide_exit, gate_entry
from filltrue.types import Candidate, Clock, Event, OrderIntent


def client_order_id(symbol: str) -> str:
    return f"filltrue-{symbol[-10:]}-{uuid4().hex[:8]}"


class Agent:
    def __init__(
        self,
        broker: Broker,
        ledger: Ledger | None = None,
        *,
        underlying: str = "IWM",
        max_open: int | None = None,
        as_of: date | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.broker = broker
        self.ledger = ledger or Ledger()
        self.underlying = underlying
        self.as_of = as_of or date.today()
        self.env = env
        if max_open is None:
            self.max_open = MAX_TICKETS if self.contest_mode else 1
        else:
            self.max_open = max_open

    @property
    def contest_mode(self) -> bool:
        src = self.env if self.env is not None else os.environ
        flag = (src.get("FILLTRUE_CONTEST") or "true").strip().lower()
        return flag not in {"0", "false", "no"}

    def clock(self) -> Clock:
        return self.broker.clock()

    def propose(self) -> Candidate | None:
        chain = self.broker.chain(self.underlying)
        if self.contest_mode:
            return pick_csp(
                chain,
                as_of=self.as_of,
                underlying=self.underlying,
                delta_lo=CONTEST_DELTA_LO,
                delta_hi=CONTEST_DELTA_HI,
                dte_lo=CONTEST_DTE_MIN,
                dte_hi=CONTEST_DTE_MAX,
                target_delta=CONTEST_TARGET_DELTA,
                target_dte=CONTEST_DTE_TARGET,
            )
        return pick_csp(chain, as_of=self.as_of, underlying=self.underlying)

    def open_csp(self, candidate: Candidate | None = None) -> Event:
        paper = paper_mode_ok(self.env)
        if not paper.ok:
            return Event(kind="REJECT", symbol="", detail=paper.reason)

        contaminated = refuse_lab_book([p.symbol for p in self.broker.positions()])
        if not contaminated.ok:
            return Event(kind="REJECT", symbol="", detail=contaminated.reason)

        if len(self.ledger.open_positions()) >= self.max_open:
            return Event(
                kind="SKIP",
                symbol=self.underlying,
                detail=f"max_open={self.max_open}",
            )

        cand = candidate or self.propose()
        if cand is None:
            return Event(kind="SKIP", symbol=self.underlying, detail="no candidate")

        if self.contest_mode:
            entry = contest_entry_ok(dte=cand.dte, abs_delta=abs(cand.delta))
        else:
            entry = gate_entry(cand)
        if not entry.ok:
            return Event(kind="SKIP", symbol=cand.symbol, detail=entry.reason)

        intent = open_intent(
            cand.symbol,
            cand.limit_price,
            client_order_id=client_order_id(cand.symbol),
        )
        gated = gate_order(intent, self.clock(), env=self.env)
        if not gated.ok:
            return Event(kind="REJECT", symbol=cand.symbol, detail=gated.reason)

        order = self.broker.submit(intent)
        meta = parse_occ(cand.symbol)
        return self.ledger.record_submit(order)

    def sync(self) -> list[Event]:
        events: list[Event] = []
        for oid, working in list(self.ledger.working.items()):
            broker_order = self.broker.get_order(oid)
            meta = None
            try:
                meta = parse_occ(broker_order.symbol)
            except ValueError:
                meta = None
            events.append(
                self.ledger.sync_order(
                    broker_order,
                    expiration=None if meta is None else meta["expiration"],
                    strike=None if meta is None else meta["strike"],
                    underlying=None if meta is None else meta["underlying"],
                )
            )
        events.extend(self.ledger.reconcile(self.broker.positions()))
        return events

    def manage(self) -> list[Event]:
        events: list[Event] = []
        clock = self.clock()
        for pos in list(self.ledger.open_positions()):
            dte = (pos.expiration - self.as_of).days
            mark = self.broker.quote_mark(pos.symbol)
            if self.contest_mode:
                decision = contest_decide_exit(
                    side="credit",
                    entry=pos.credit,
                    mark=mark,
                    dte=dte,
                    as_of=self.as_of,
                )
                decision.setdefault("peak_profit_frac", pos.peak_profit_frac)
            else:
                decision = decide_exit(
                    credit=pos.credit,
                    mark=mark,
                    dte=dte,
                    peak_profit_frac=pos.peak_profit_frac,
                )
            pos.peak_profit_frac = float(decision.get("peak_profit_frac") or pos.peak_profit_frac)
            if not decision["should_close"]:
                events.append(
                    Event(
                        kind="HOLD",
                        symbol=pos.symbol,
                        detail=decision["reason"],
                        order_id=pos.order_id,
                    )
                )
                continue
            intent = close_intent(
                pos.symbol, pos.qty, reason=f"close:{decision['rule']}"
            )
            gated = gate_order(intent, clock, env=self.env)
            if not gated.ok:
                events.append(
                    Event(
                        kind="HOLD",
                        symbol=pos.symbol,
                        detail=f"close deferred: {gated.reason}",
                        order_id=pos.order_id,
                    )
                )
                continue
            close_order = self.broker.submit(intent)
            # Closing is only real after a fill too.
            if close_order.filled_qty >= pos.qty and close_order.filled_avg_price:
                events.append(
                    self.ledger.record_close(
                        pos.order_id, reason=decision["reason"]
                    )
                )
            else:
                events.append(
                    Event(
                        kind="WORKING",
                        symbol=pos.symbol,
                        detail=(
                            f"close submitted {close_order.id} "
                            f"status={close_order.status} — not CLOSED until fill"
                        ),
                        order_id=close_order.id,
                    )
                )
        return events

    def step(self) -> list[Event]:
        out: list[Event] = []
        out.extend(self.sync())
        out.extend(self.manage())
        if len(self.ledger.open_positions()) < self.max_open:
            event = self.open_csp()
            out.append(event)
        return out


def mcp_place_payload(intent: OrderIntent) -> dict:
    """Exact `place_option_order` body for Alpaca MCP v2."""
    payload = {
        "qty": str(int(intent.qty) if intent.qty == int(intent.qty) else intent.qty),
        "type": intent.type,
        "time_in_force": "day",
        "symbol": intent.symbol,
        "side": intent.side,
        "position_intent": intent.position_intent,
        "client_order_id": intent.client_order_id,
    }
    if intent.type == "limit":
        payload["limit_price"] = str(intent.limit_price)
    return payload
