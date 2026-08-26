# FillTrue — grand plan (Alpaca Options Alpha Agents hackathon)

**Window:** 2026-08-28 15:00 UTC → 2026-09-04 15:00 UTC  
**Track:** Options Alpha Agents  
**Money:** paper only. No live capital.  
**Done-when:** judges can clone the public repo, run tests with no network, open a demo URL, and see an agent that (1) talks to Alpaca MCP/API, (2) sells a labeled CSP on a limit, (3) **does not record OPEN unless the broker filled**, (4) exits when the reason to hold is gone (stop / trail / thesis-dead-while-green / time — contest also harvests into the deadline).

## Hunt
- Topic: Alpaca MCP options trading agents for this hackathon
- Queries: `gh search alpaca mcp trading agent`; official `alpacahq/alpaca-mcp-server` (925★, MIT, pushed 2026-08-24); lablab rules + Alpaca HQ 2026-08-25
- Fresh signal: ~2,400 registrants; several empty `alpaca-options-agent` repos already. Official ask = Trading API + MCP **or** CLI. Judged on P&L + creativity/engagement. lablab also wants public GitHub + demo URL + video.
- Best hits:
  - `alpacahq/alpaca-mcp-server` — **adopt** as the tool surface judges expect
  - our `automated-trading` sleeve — **adapt** exit spine + session gates; **do not** dump the $100k book or ghost state
- Decision: **adapt** lab rules + **build** fill-sync (the lab’s real bug) as the public agent
- What we take: `decide_exit` (harvest when the reason to hold is gone), limit-only off-hours, labeled OPEN. What we fix: record OPEN on submit (expired DAY limits became “open shorts”).

## Why this wins
Everyone else will prompt an LLM to pick a ticker. We ship the thing Alpaca MCP cannot do for you: **policy + broker-truth**. We already paid tuition on ghost CSPs (three “open” shorts, fill qty 0). The hackathon product *is* that lesson.

## Constraints
- Paper endpoint only (`ALPACA_PAPER_TRADE=true`)
- No secrets in git
- No mixing E1 dual-momentum book into hackathon P&L
- Build in public (repo + X), no account numbers / no personal $100k curve

## Chunks
1. Policy kernel (entry + spine exits) + adversarial tests
2. Fill-sync + ledger (OPEN only on fill; reconcile vs broker)
3. Candidate picker (IWM 16–20Δ ~45 DTE, limit@bid)
4. Agent surface (README prompts + optional CLI wrapping Alpaca MCP)
5. Streamlit demo + sample events (judges’ URL)
6. Public GitHub + build-in-public draft

## Q / adversarial bar
A: submit → fill → ledger OPEN; mark hits 1.5× credit → CLOSE stop.  
B: DAY limit expires unfilled → ledger stays flat (the ghost case). Market order when closed → refuse. Take-profit-only close → refused.

— Grok Build (grok-4.6, effort: high) · 2026-08-25
