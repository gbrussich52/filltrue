# FillTrue — solo trees

Trunk: [`grand-plan.md`](grand-plan.md). Each chunk is independently shippable. Interface named first.

**Shared types (frozen):** `Clock`, `Contract`, `Candidate`, `OrderIntent`, `BrokerOrder`, `Event`, `GateResult`. Defined in `filltrue/types.py`.

## 1. Policy kernel
- Files: `filltrue/policy.py`, `tests/test_policy.py`
- Built: entry band (put, |Δ| 0.16–0.20, DTE 30–60) + spine exits (stop 1.5×, trail 30/15, 21 DTE). No take-profit cap.
- Done-when: tests refuse 50/80/95% “bank it”; stop and time-stop fire; 22 DTE holds.

## 2. Fill-sync + ledger
- Files: `filltrue/ledger.py`, `filltrue/gate.py`, `tests/test_ledger.py`, `tests/test_ghost.py`
- Built: submit → WORKING, never OPEN. OPEN only if `filled_qty >= qty` **and** `filled_avg_price > 0`. Expired DAY limit → UNFILLED. Reconcile drops local OPEN missing at the broker. Close intent is `buy_to_close`.
- Done-when: the ghost case (status expired, filled_qty 0) cannot produce an open short. `status=filled` with qty 0 cannot either.

## 3. Candidate picker
- Files: `filltrue/picker.py`, `filltrue/occ.py`, `tests/test_picker.py`
- Built: IWM (or injected chain) 16–20Δ put nearest 45 DTE, limit@bid. Skip no-bid / out-of-band.
- Done-when: fixture chain returns the 18Δ/45 DTE put; 15Δ and 21Δ skipped.

## 4. Agent surface
- Files: `filltrue/agent.py`, `filltrue/broker.py`, `filltrue/cli.py`, `prompts/SYSTEM.md`
- Built: paper-only loop. MCP is the hands (`place_option_order` + `get_order_by_id`). FillTrue is the brain. `client_order_id` prefix `filltrue-`.
- Done-when: FakeBroker fill → OPEN; FakeBroker expire → flat; market order while closed → refuse; live keys refused unless `ALPACA_PAPER_TRADE=true`.

## 5. Demo URL
- Files: `index.html`, `events.json`, `demo/app.py`
- Built: judges click a URL, watch Naive vs FillTrue on the same unfilled DAY limit. Streamlit optional local.
- Done-when: GitHub Pages 200, no API keys required.

## 6. Public GitHub + BIP
- Public `gbrussich52/filltrue`, MIT, CI, no secrets. X draft in `docs/bip-draft.txt`.

— Grok Build (grok-4.6, effort: high) · 2026-08-25
