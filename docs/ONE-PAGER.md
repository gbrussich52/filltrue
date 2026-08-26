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
- 2% of equity at risk per ticket, 4 tickets, 8% gross cap.
- Contest take-profit (50% of credit / ~80% debit). Stop 1.5× credit. Flatten into the deadline.
- Closes are `buy_to_close`, never `buy_to_open`.

## Alpaca infrastructure

- Trading API via official `alpacahq/alpaca-mcp-server` (MCP) and/or this CLI.
- Paper endpoint only (`ALPACA_PAPER_TRADE=true`).
- `client_order_id` prefix `filltrue-` for an isolated ledger.
- Public repo + demo: https://github.com/gbrussich52/filltrue · https://gbrussich52.github.io/filltrue/

Not investment advice. Paper trading. Options can lose more than the credit.
