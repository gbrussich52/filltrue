"""Order legality. Paper only. Session-aware. Intent-correct.

The leftover-long-put bug: a stop that `buy`s without `buy_to_close` opens a
long put on top of a short that never existed (or that you just closed).
FillTrue will not submit that order.
"""

from __future__ import annotations

import hashlib
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


LAB_ETFS = frozenset({"SPY", "VEA", "BND", "BIL", "VTI", "AGG"})


def key_fingerprint(api_key: str) -> str:
    """Stable, non-reversible id for an API key. Never logs the key itself."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:12]


def contest_account_ok(env: dict[str, str] | None = None) -> GateResult:
    """Refuse to trade an account listed as forbidden.

    The contest requires a dedicated $100k paper account. Pointing it at a
    research account instead silently contaminates that account's own
    experiment — options land in its equity denominator and a pre-registered
    paper gate cannot be re-run once polluted.

    Forbidden accounts are supplied as fingerprints via
    FILLTRUE_FORBIDDEN_KEY_FINGERPRINTS (comma-separated, from
    key_fingerprint()), never as keys and never hardcoded: this repo is
    public and must carry no account identity of its own.
    """
    src = env if env is not None else os.environ
    api_key = (src.get("ALPACA_API_KEY") or "").strip()
    raw = (src.get("FILLTRUE_FORBIDDEN_KEY_FINGERPRINTS") or "").strip()
    if not api_key or not raw:
        # Nothing to check: an unset key cannot reach a broker, and with no
        # forbidden list there is no account to protect. Missing credentials
        # are the broker layer's error, not an order-legality failure.
        return GateResult(True, "no account check applicable", "account_unchecked")

    forbidden = {f.strip().lower() for f in raw.split(",") if f.strip()}
    fp = key_fingerprint(api_key)
    if fp in forbidden:
        return GateResult(
            False,
            f"account {fp} is on the forbidden list — this is not the "
            "dedicated contest account; trading it would contaminate it",
            "forbidden_account",
        )
    return GateResult(True, f"account {fp}", "account_ok")


def lab_positions_detected(symbols: list[str]) -> GateResult:
    """Abort if the account holds research ETFs — it is not a clean account.

    Implements the abort rule the write-up has always claimed. Matching is on
    the underlying symbol, so an option on SPY does not trip it; a SPY *stock*
    position does.
    """
    hits = sorted({s.strip().upper() for s in symbols} & LAB_ETFS)
    if hits:
        return GateResult(
            False,
            f"account holds research ETF positions ({', '.join(hits)}) — "
            "wrong account, refusing to trade",
            "lab_account",
        )
    return GateResult(True, "no research ETF positions", "clean_account")


def gate_order(
    intent: OrderIntent,
    clock: Clock,
    *,
    env: dict[str, str] | None = None,
) -> GateResult:
    paper = paper_mode_ok(env)
    if not paper.ok:
        return paper

    account = contest_account_ok(env)
    if not account.ok:
        return account

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
