# FillTrue

**An options agent that only believes fills.**

Paper-only cash-secured puts on [Alpaca](https://alpaca.markets). Hands = [Alpaca MCP](https://github.com/alpacahq/alpaca-mcp-server). Brain = this repo.

> Most MCP trading bots will wrap “LLM says sell a put” around `place_option_order` and log **OPEN** when the call returns an id. Alpaca will happily hand you `status=new` and `filled_qty=0`. A DAY limit that expires unfilled then sits on the ledger as a short that never existed.

FillTrue will not do that. **OPEN requires a true fill:** `filled_qty >= qty` and a positive `filled_avg_price`. Status words are rumors.

**Demo (no keys):** https://gbrussich52.github.io/filltrue/  
**Hackathon:** Alpaca Options Alpha Agents (2026-08-28 → 2026-09-04)

[![test](https://github.com/gbrussich52/filltrue/actions/workflows/ci.yml/badge.svg)](https://github.com/gbrussich52/filltrue/actions/workflows/ci.yml)

## 10-second proof

```bash
pip install pytest
python -m pytest          # network-free
python -m filltrue replay
```

You should see:

```
Naive ledger OPEN count : 1
FillTrue OPEN count     : 0
```

That is the product.

## Contest vs lab (read this)

The 90-day dual-momentum / 16–20Δ CSP lab is a **different paper account** and a different game. Official Alpaca rules: dedicated $100k competition paper account, options must be in the strategy, judged on **P&L + creativity**.

| | Lab book | This repo (contest) |
|---|---|---|
| Account | existing ~$104k paper, do **not** reset | **new** paper account, $100k |
| Horizon | 90-day gate | ~5 RTH sessions |
| Tenor / delta | 45 DTE / 16–20Δ | **14 DTE / 30Δ** |
| Take profit | forbidden | **required** (bank 50% credit) |
| Structure | naked CSP | defined-risk default |

Signals we keep: SPY 200d crash brake, dual-momentum regime, IVP, fill-sync.

```bash
python -m filltrue contest-plan --spy-above-200 --ivp 70
python -m filltrue contest-plan --no-spy-above-200 --ivp 70   # cash
```

How to open the account (do not touch the lab): Alpaca dashboard → paper account number (upper left) → **Open New Paper Account** → $100,000 → new API keys into `.env`.

Full write-up: [`docs/CONTEST-RULES.md`](docs/CONTEST-RULES.md) · required one-pager: [`docs/ONE-PAGER.md`](docs/ONE-PAGER.md)

## What it trades

- Underlying: IWM
- Structure: naked cash-secured put
- Band: |delta| 0.16–0.20, DTE 30–60 (target 45 / 18Δ)
- Entry: limit at bid, TIF DAY, `position_intent=sell_to_open`
- Exits (no take-profit cap):
  - stop when mark ≥ 1.5× credit
  - trail giveback (arm 30%, giveback 15 points of credit)
  - 21 DTE gamma stop
- Close: `buy_to_close` only — never `buy_to_open` (that leftover long put is a real bug)

New entries and market exits only while the session is open. Parking a DAY limit overnight is how ghosts are born.

## Why this, not another LLM picker

Judges will see ~2,400 registrants. A lot of those agents will pick a ticker with a prompt. Alpaca’s MCP already does the plumbing. The thing MCP cannot do for you is **policy + broker-truth**.

FillTrue’s ledger is isolated with `client_order_id` prefix `filltrue-`. It does not ingest some other strategy’s book.

## MCP (the hands)

Use official `alpacahq/alpaca-mcp-server`. Then paste [`prompts/SYSTEM.md`](prompts/SYSTEM.md) as the system prompt.

```json
{
  "mcpServers": {
    "alpaca": {
      "command": "uvx",
      "args": ["alpaca-mcp-server"],
      "env": {
        "ALPACA_API_KEY": "paper_key",
        "ALPACA_SECRET_KEY": "paper_secret",
        "ALPACA_PAPER_TRADE": "true",
        "ALPACA_TOOLSETS": "account,trading,assets,options-data"
      }
    }
  }
}
```

FillTrue will refuse to run if `ALPACA_PAPER_TRADE` is false.

After every `place_option_order`:

1. Treat the result as **WORKING**
2. Poll `get_order_by_id`
3. OPEN only on a true fill
4. `expired` / `canceled` / `rejected` with qty 0 → **UNFILLED**, not a short
5. Reconcile vs `get_all_positions` — local OPEN missing at the broker is a ghost, clear it

`python -m filltrue payload` prints the exact MCP JSON for the demo contract.

## Layout

```
filltrue/          policy, ledger, picker, gate, agent (stdlib only)
tests/             ghost case, leftover-long, take-profit refusal, session
prompts/SYSTEM.md  MCP agent prompt
index.html         public demo
demo/app.py        Streamlit (optional extra)
```

The kernel has **no third-party dependencies**. Tests do not talk to the network.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```

Streamlit local demo:

```bash
pip install -e ".[demo]"
python -m filltrue demo
```

## Paper money

This uses Alpaca’s **paper** API. It is not an offer to buy or sell securities. Options can lose more than the credit received. Read the [OCC options disclosure](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document). Past paper P&L is not future results.

Do not paste live keys here. Do not point this agent at a live account.

## License

MIT. Built in public for the Alpaca × lablab.ai hackathon.
