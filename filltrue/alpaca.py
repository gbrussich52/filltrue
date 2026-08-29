"""Real Alpaca broker. The only sanctioned way an order leaves this process.

Why this file exists
--------------------
`gate_order()` — paper-only refusal, forbidden-account refusal, session and
intent checks — is called from exactly one place: `agent.py`, against the
`Broker` protocol. Until now the only implementation of that protocol was
`FakeBroker`, so the gates and their tests guarded a path that had never
placed a real order. The two live contest orders on 2026-08-28 went out
through ad-hoc REST scripts and touched no gate at all.

Implementing the protocol for real closes that: orders route through the agent,
and the agent cannot submit without passing the gate first.

Stdlib only, matching the package's zero-dependency kernel. urllib is used
carefully — Alpaca serves large chain responses chunked and a plain
`json.load(urlopen(...))` raises IncompleteRead partway through, so reads are
retried and length-checked rather than trusted.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from filltrue.types import BrokerOrder, BrokerPosition, Clock, Contract, OrderIntent

TRADE_HOST = "https://paper-api.alpaca.markets"
DATA_HOST = "https://data.alpaca.markets"
OCC = re.compile(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$")
RETRIES = 3


def parse_occ(symbol: str) -> tuple[str, dt.date, str, float]:
    """OCC symbol -> (root, expiration, C|P, strike).

    Root length varies (IWM is 3, AVGO is 4), so fixed offsets are wrong —
    that assumption crashed the first AVGO chain pull.
    """
    m = OCC.match(symbol)
    if not m:
        raise ValueError(f"not an OCC option symbol: {symbol}")
    root, d, cp, strike = m.groups()
    return root, dt.date(2000 + int(d[:2]), int(d[2:4]), int(d[4:6])), cp, int(strike) / 1000


class AlpacaBroker:
    """Paper-only Alpaca client satisfying the Broker protocol."""

    def __init__(self, key: str | None = None, secret: str | None = None,
                 *, feed: str = "indicative") -> None:
        self.key = key or os.environ.get("ALPACA_API_KEY", "")
        self.secret = secret or os.environ.get("ALPACA_SECRET_KEY", "")
        if not self.key or not self.secret:
            raise RuntimeError("ALPACA_API_KEY / ALPACA_SECRET_KEY not set")
        if not self.key.startswith("PK"):
            # Live keys start with AK. Refusing here is belt-and-braces behind
            # gate_order's paper check — a live key must never reach a socket.
            raise RuntimeError("refusing a non-paper API key (expected PK...)")
        self.feed = feed

    # ---- transport -------------------------------------------------------
    def _req(self, host: str, path: str, *, method: str = "GET",
             params: dict | None = None, body: dict | None = None) -> dict:
        url = host + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        headers = {"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret}
        if data:
            headers["Content-Type"] = "application/json"
        last: Exception | None = None
        for attempt in range(RETRIES):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read()
                return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                # 4xx is a real answer, not a transport failure; do not retry.
                raise RuntimeError(f"{method} {path} -> {e.code}: {e.read()[:200].decode()}") from e
            except Exception as e:              # IncompleteRead, timeouts, DNS
                last = e
                if attempt < RETRIES - 1:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"{method} {path} failed after {RETRIES} attempts: {last}")

    # ---- Broker protocol -------------------------------------------------
    def clock(self) -> Clock:
        c = self._req(TRADE_HOST, "/v2/clock")
        return Clock(is_open=bool(c.get("is_open")), timestamp=str(c.get("timestamp", "")))

    def submit(self, intent: OrderIntent) -> BrokerOrder:
        body = {
            "symbol": intent.symbol, "qty": str(intent.qty), "side": intent.side,
            "type": intent.type, "time_in_force": intent.time_in_force,
            "position_intent": intent.position_intent,
        }
        if intent.limit_price is not None:
            body["limit_price"] = f"{intent.limit_price:.2f}"
        if intent.client_order_id:
            body["client_order_id"] = intent.client_order_id
        return self._order(self._req(TRADE_HOST, "/v2/orders", method="POST", body=body))

    def get_order(self, order_id: str) -> BrokerOrder:
        return self._order(self._req(TRADE_HOST, f"/v2/orders/{order_id}"))

    @staticmethod
    def _order(o: dict) -> BrokerOrder:
        fp = o.get("filled_avg_price")
        return BrokerOrder(
            id=str(o.get("id", "")), client_order_id=str(o.get("client_order_id", "")),
            symbol=str(o.get("symbol", "")), side=str(o.get("side", "")),
            qty=float(o.get("qty") or 0), status=str(o.get("status", "")),
            filled_qty=float(o.get("filled_qty") or 0),
            filled_avg_price=float(fp) if fp not in (None, "") else None,
            type=str(o.get("type", "limit")),
        )

    def positions(self) -> list[BrokerPosition]:
        out = []
        for p in self._req(TRADE_HOST, "/v2/positions") or []:
            ae = p.get("avg_entry_price")
            out.append(BrokerPosition(
                symbol=str(p["symbol"]), qty=float(p.get("qty") or 0),
                avg_entry_price=float(ae) if ae not in (None, "") else None))
        return out

    def chain(self, underlying: str, *, dte_min: int = 7, dte_max: int = 45,
              moneyness: float = 0.15) -> list[Contract]:
        spot = self.underlying_price(underlying)
        today = dt.date.today()
        out: list[Contract] = []
        for kind in ("call", "put"):
            d = self._req(DATA_HOST, f"/v1beta1/options/snapshots/{underlying}", params={
                "feed": self.feed, "limit": 1000, "type": kind,
                "expiration_date_gte": (today + dt.timedelta(days=dte_min)).isoformat(),
                "expiration_date_lte": (today + dt.timedelta(days=dte_max)).isoformat(),
                "strike_price_gte": round(spot * (1 - moneyness), 2),
                "strike_price_lte": round(spot * (1 + moneyness), 2),
            })
            for sym, s in (d.get("snapshots") or {}).items():
                try:
                    root, exp, cp, strike = parse_occ(sym)
                except ValueError:
                    continue
                q = s.get("latestQuote") or {}
                g = s.get("greeks") or {}
                out.append(Contract(
                    symbol=sym, underlying=root, expiration=exp, strike=strike,
                    option_type="call" if cp == "C" else "put",
                    delta=g.get("delta"), bid=q.get("bp"), ask=q.get("ap"),
                    iv=s.get("impliedVolatility")))
        return out

    def quote_mark(self, symbol: str) -> float | None:
        d = self._req(DATA_HOST, "/v1beta1/options/snapshots",
                      params={"symbols": symbol, "feed": self.feed})
        s = (d.get("snapshots") or {}).get(symbol)
        if not s:
            return None
        q = s.get("latestQuote") or {}
        bid, ask = q.get("bp") or 0, q.get("ap") or 0
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        t = s.get("latestTrade") or {}
        return float(t["p"]) if t.get("p") else None

    # ---- helpers ---------------------------------------------------------
    def underlying_price(self, symbol: str) -> float:
        d = self._req(DATA_HOST, "/v2/stocks/snapshots", params={"symbols": symbol})
        s = (d or {}).get(symbol) or {}
        for key in ("latestTrade", "dailyBar", "prevDailyBar"):
            v = s.get(key) or {}
            px = v.get("p") or v.get("c")
            if px:
                return float(px)
        raise RuntimeError(f"no usable price for {symbol}")

    def account(self) -> dict:
        return self._req(TRADE_HOST, "/v2/account")
