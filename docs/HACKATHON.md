# Alpaca Options Alpha Agents — FillTrue

**Event:** [Alpaca AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon)  
**Window:** 2026-08-28 15:00 UTC → 2026-09-04 15:00 UTC  
**Track:** Options Alpha Agents  
**Repo:** https://github.com/gbrussich52/filltrue  
**Demo:** https://gbrussich52.github.io/filltrue/

## What we built

A paper-only CSP agent whose differentiator is **broker-truth**. Alpaca MCP will place the order. FillTrue will not call it a position until the broker filled it.

## Judging map

| Criterion | Where it lives |
|---|---|
| Uses Trading API + MCP or CLI | `prompts/SYSTEM.md` + `filltrue.agent.mcp_place_payload` + `python -m filltrue` |
| Options | IWM 16–20Δ cash-secured puts, limit@bid |
| P&L | isolated FillTrue ledger (`client_order_id` prefix `filltrue-`), paper only |
| Creativity | the ghost-fill problem most MCP wrappers will ship; tests that fail it |
| Engagement | public repo + demo URL + build-in-public |

## Run what judges will run

```bash
python -m pytest            # network-free
python -m filltrue replay   # ghost vs fill, 10 seconds
open index.html             # or the Pages URL
```

## Money

Paper endpoint only. No live capital. No dumping an existing $100k paper book into this ledger.

— Grok Build (grok-4.6, effort: high) · 2026-08-25
