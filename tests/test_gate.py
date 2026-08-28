"""Session, paper-only, leftover-long. Take-profit closes are allowed."""

from __future__ import annotations

from filltrue.gate import close_intent, gate_order, open_intent, paper_mode_ok
from filltrue.types import Clock, OrderIntent


OPEN = Clock(is_open=True)
CLOSED = Clock(is_open=False)


def test_paper_mode_refuses_live():
    assert paper_mode_ok({"ALPACA_PAPER_TRADE": "true"}).ok
    assert not paper_mode_ok({"ALPACA_PAPER_TRADE": "false"}).ok
    assert not paper_mode_ok({"ALPACA_PAPER_TRADE": "live"}).ok


def test_market_order_refused_when_closed():
    intent = close_intent("IWM261016P00220000", 1, reason="close:stop_loss")
    r = gate_order(intent, CLOSED, env={"ALPACA_PAPER_TRADE": "true"})
    assert not r.ok
    assert r.code == "session_closed"


def test_limit_open_refused_when_closed():
    intent = open_intent("IWM261016P00220000", 1.12)
    r = gate_order(intent, CLOSED, env={"ALPACA_PAPER_TRADE": "true"})
    assert not r.ok
    assert r.code == "session_closed"


def test_open_limit_allowed_when_open():
    intent = open_intent("IWM261016P00220000", 1.12)
    r = gate_order(intent, OPEN, env={"ALPACA_PAPER_TRADE": "true"})
    assert r.ok


def test_close_must_be_buy_to_close():
    bad = OrderIntent(
        symbol="IWM261016P00220000",
        side="buy",
        qty=1,
        type="market",
        position_intent="buy_to_open",
        reason="close:stop_loss",
    )
    r = gate_order(bad, OPEN, env={"ALPACA_PAPER_TRADE": "true"})
    assert not r.ok
    assert r.code == "leftover_long"


def test_close_intent_helper_is_buy_to_close():
    intent = close_intent("IWM261016P00220000", 1, reason="stop_loss")
    assert intent.side == "buy"
    assert intent.position_intent == "buy_to_close"
    r = gate_order(intent, OPEN, env={"ALPACA_PAPER_TRADE": "true"})
    assert r.ok


def test_take_profit_close_allowed():
    intent = OrderIntent(
        symbol="X",
        side="buy",
        qty=1,
        type="market",
        position_intent="buy_to_close",
        reason="close:take_profit",
    )
    r = gate_order(intent, OPEN, env={"ALPACA_PAPER_TRADE": "true"})
    assert r.ok


def test_live_env_blocks_even_valid_intent():
    intent = open_intent("IWM261016P00220000", 1.12)
    r = gate_order(intent, OPEN, env={"ALPACA_PAPER_TRADE": "false"})
    assert not r.ok
    assert r.code == "live_refused"


class TestContestAccountGuard:
    """The contest must not run on a research account. 2026-08-28: the Alpaca
    MCP was found pointed at the live lab account (identical key)."""

    from filltrue.gate import key_fingerprint as _fp

    def _env(self, key="PKCONTEST0000000000000000", forbidden=""):
        return {
            "ALPACA_API_KEY": key,
            "ALPACA_PAPER_TRADE": "true",
            "FILLTRUE_FORBIDDEN_KEY_FINGERPRINTS": forbidden,
        }

    def test_forbidden_account_refused(self):
        from filltrue.gate import contest_account_ok, key_fingerprint
        lab = "PKLAB1111111111111111111"
        r = contest_account_ok(self._env(key=lab, forbidden=key_fingerprint(lab)))
        assert not r.ok and r.code == "forbidden_account"

    def test_clean_account_allowed(self):
        from filltrue.gate import contest_account_ok, key_fingerprint
        r = contest_account_ok(
            self._env(key="PKCONTEST999", forbidden=key_fingerprint("PKLAB000")))
        assert r.ok

    def test_fingerprint_never_contains_the_key(self):
        from filltrue.gate import contest_account_ok, key_fingerprint
        secret = "PKSUPERSECRET1234567890"
        r = contest_account_ok(self._env(key=secret, forbidden=key_fingerprint(secret)))
        assert secret not in r.reason, "guard leaked the API key into its message"

    def test_case_and_whitespace_tolerant_list(self):
        from filltrue.gate import contest_account_ok, key_fingerprint
        lab = "PKLAB222"
        fp = key_fingerprint(lab)
        listed = f" aaaa , {fp.upper()} ,bbbb "
        assert not contest_account_ok(self._env(key=lab, forbidden=listed)).ok

    def test_unchecked_when_no_forbidden_list(self):
        from filltrue.gate import contest_account_ok
        assert contest_account_ok(self._env(forbidden="")).ok

    def test_unchecked_when_no_key(self):
        from filltrue.gate import contest_account_ok
        assert contest_account_ok(self._env(key="", forbidden="abc")).ok

    def test_gate_order_blocks_forbidden_account(self):
        from filltrue.gate import contest_account_ok, gate_order, key_fingerprint
        from filltrue.types import Clock, OrderIntent
        lab = "PKLAB333"
        intent = OrderIntent(
            symbol="IWM260918C00250000", qty=1, side="buy", type="limit",
            limit_price=1.00, time_in_force="day", position_intent="buy_to_open")
        r = gate_order(intent, Clock(is_open=True),
                       env=self._env(key=lab, forbidden=key_fingerprint(lab)))
        assert not r.ok and r.code == "forbidden_account"

    def test_live_refusal_still_wins_over_account_check(self):
        from filltrue.gate import gate_order, key_fingerprint
        from filltrue.types import Clock, OrderIntent
        env = self._env(key="PKX", forbidden=key_fingerprint("PKX"))
        env["ALPACA_PAPER_TRADE"] = "false"
        intent = OrderIntent(
            symbol="IWM260918C00250000", qty=1, side="buy", type="limit",
            limit_price=1.00, time_in_force="day", position_intent="buy_to_open")
        r = gate_order(intent, Clock(is_open=True), env=env)
        assert r.code == "live_refused", "live-capital refusal must be checked first"


class TestLabPositionAbort:
    def test_research_etf_stock_aborts(self):
        from filltrue.gate import lab_positions_detected
        r = lab_positions_detected(["IWM", "SPY"])
        assert not r.ok and "SPY" in r.reason

    def test_clean_account_passes(self):
        from filltrue.gate import lab_positions_detected
        assert lab_positions_detected(["IWM", "QQQ"]).ok

    def test_empty_account_passes(self):
        from filltrue.gate import lab_positions_detected
        assert lab_positions_detected([]).ok

    def test_case_insensitive(self):
        from filltrue.gate import lab_positions_detected
        assert not lab_positions_detected(["  bil  "]).ok
