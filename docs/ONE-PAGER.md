# FillTrue — one-page write-up

Required by Alpaca: *AI logic, risk gates, and Alpaca infrastructure.*

## AI logic

FillTrue is a paper-only options agent. Alpaca MCP is the hands (`place_option_order`, `get_order_by_id`, `get_clock`, option chain/snapshot). FillTrue is the brain.

**Signals (from a live dual-momentum / CSP research lab, not dumped into this account):**

- Risk-on/off: SPY vs 200-day SMA crash brake + dual-momentum regime.
- IVP: sell defined-risk premium when IV is rich; buy premium when IV is cheap.
- Horizon: 7–21 DTE, ~30Δ, because the contest is ~5 cash sessions, not 90 days.

**Broker-truth:** an order id is not a position. OPEN requires `filled_qty ≥ qty` and a positive `filled_avg_price`. Expired DAY limits stay UNFILLED. That is the differentiator vs wrapping “LLM says buy” around MCP.

## Risk gates

- Paper only. Live keys refused.
- Dedicated $100k contest paper account. Lab ETFs (SPY/VEA/BND/BIL stock) abort the agent.
- No 0DTE. No 45 DTE lab tenor on this account.
- Defined-risk default (spreads). Crash brake on → no new short premium.
- Size is `survival_cap(sessions_left) × conviction × tournament_tilt`, not a fixed 2%/8%. Max 4 tickets.
- Contest take-profit (50% of credit / ~80% debit). Stop 1.5× credit. Flatten into the deadline.
- Close a short with `buy_to_close`. Close a long with `sell_to_close`. Never flatten a short with `buy_to_open`.
- Live sleeve this week: cheap-IV long IWM premium (call debit from `plan()`). OPEN still only on a true fill. One 81-DTE long put sits outside the 7–21 band as a cheap-vega hold, not a new-entry template.

## Alpaca infrastructure

- Trading API via official `alpacahq/alpaca-mcp-server` (MCP) and/or this CLI.
- Paper endpoint only (`ALPACA_PAPER_TRADE=true`).
- Agent-generated `client_order_id` prefix `filltrue-`. Ledger still OPEN-on-fill if an ad-hoc id omitted it.
- Public repo + demo: https://github.com/gbrussich52/filltrue · https://gbrussich52.github.io/filltrue/

Not investment advice. Paper trading. Options can lose more than the credit.
