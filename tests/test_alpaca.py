"""AlpacaBroker: protocol conformance and refusals. No network."""

from __future__ import annotations

import datetime as dt

import pytest

from filltrue.alpaca import AlpacaBroker, parse_occ
from filltrue.types import BrokerOrder, OrderIntent


class TestOCC:
    def test_three_and_four_char_roots(self):
        assert parse_occ("IWM260918C00300000") == ("IWM", dt.date(2026, 9, 18), "C", 300.0)
        assert parse_occ("AVGO260904P00330000") == ("AVGO", dt.date(2026, 9, 4), "P", 330.0)

    def test_fractional_strike(self):
        assert parse_occ("SPY260918C00512500")[3] == 512.5

    def test_rejects_non_option(self):
        for bad in ("IWM", "", "iwm260918C00300000", "IWM260918X00300000"):
            with pytest.raises(ValueError):
                parse_occ(bad)


class TestKeyRefusal:
    def test_live_key_refused(self):
        with pytest.raises(RuntimeError, match="non-paper"):
            AlpacaBroker(key="AKLIVE0000000000", secret="s")

    def test_missing_creds_refused(self, monkeypatch):
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="not set"):
            AlpacaBroker()

    def test_paper_key_accepted(self):
        assert AlpacaBroker(key="PKTEST000000", secret="s").key.startswith("PK")


def _stub(b: AlpacaBroker, mapping: dict):
    def fake(host, path, *, method="GET", params=None, body=None):
        for frag, resp in mapping.items():
            if frag in path:
                return resp(body) if callable(resp) else resp
        raise AssertionError(f"unstubbed path {path}")
    b._req = fake
    return b


class TestProtocolShapes:
    def _b(self):
        return AlpacaBroker(key="PKTEST000000", secret="s")

    def test_submit_never_reports_open_on_a_new_order(self):
        b = _stub(self._b(), {"/v2/orders": {
            "id": "abc", "client_order_id": "c1", "symbol": "IWM260918C00300000",
            "side": "buy", "qty": "5", "status": "new", "filled_qty": "0",
            "filled_avg_price": None, "type": "limit"}})
        o = b.submit(OrderIntent(symbol="IWM260918C00300000", side="buy", qty=5,
                                 type="limit", limit_price=1.0,
                                 position_intent="buy_to_open"))
        assert isinstance(o, BrokerOrder)
        assert o.filled_qty == 0 and o.filled_avg_price is None
        assert o.status == "new", "a submitted order is not a position"

    def test_filled_avg_price_empty_string_becomes_none(self):
        """Alpaca returns '' not null on unfilled orders; float('') raises."""
        b = _stub(self._b(), {"/v2/orders": {
            "id": "a", "client_order_id": "c", "symbol": "X", "side": "buy",
            "qty": "1", "status": "canceled", "filled_qty": "0",
            "filled_avg_price": "", "type": "limit"}})
        assert b.get_order("a").filled_avg_price is None

    def test_positions_preserve_sign_for_shorts(self):
        b = _stub(self._b(), {"/v2/positions": [
            {"symbol": "IWM260918P00280000", "qty": "-3", "avg_entry_price": "1.10"}]})
        p = b.positions()[0]
        assert p.qty == -3.0, "short positions must stay negative"

    def test_empty_positions(self):
        assert _stub(self._b(), {"/v2/positions": []}).positions() == []

    def test_quote_mark_falls_back_to_last_trade(self):
        b = _stub(self._b(), {"/options/snapshots": {"snapshots": {"S": {
            "latestQuote": {"bp": 0, "ap": 0}, "latestTrade": {"p": 4.25}}}}})
        assert b.quote_mark("S") == 4.25

    def test_quote_mark_missing_symbol_is_none(self):
        assert _stub(self._b(), {"/options/snapshots": {"snapshots": {}}}).quote_mark("Z") is None

    def test_chain_skips_unparseable_symbols(self):
        b = self._b()
        b.underlying_price = lambda s: 300.0
        _stub(b, {"/options/snapshots/IWM": {"snapshots": {
            "IWM260918C00300000": {"latestQuote": {"bp": 1, "ap": 2},
                                   "greeks": {"delta": 0.3}, "impliedVolatility": 0.14},
            "GARBAGE": {"latestQuote": {"bp": 1, "ap": 2}}}}})
        ch = b.chain("IWM")
        assert len(ch) == 2 and all(c.symbol != "GARBAGE" for c in ch)

    def test_underlying_price_raises_rather_than_guessing(self):
        b = _stub(self._b(), {"/stocks/snapshots": {"IWM": {}}})
        with pytest.raises(RuntimeError, match="no usable price"):
            b.underlying_price("IWM")


class TestBrokerSatisfiesProtocol:
    def test_all_protocol_methods_present(self):
        from filltrue.broker import Broker
        required = [m for m in dir(Broker) if not m.startswith("_")]
        missing = [m for m in required if not hasattr(AlpacaBroker, m)]
        assert not missing, f"AlpacaBroker missing protocol methods: {missing}"
