# FillTrue contest rules — read this, not the 90-day lab

**Confidence:** official Alpaca submission rules = **Certain** (Alpaca HQ thread, 2026-08-25). Trading-day count = **Certain**. “How to win P&L in 5 sessions” = **Likely** (our judgment, not a posted formula).

## What the organizers actually required

Source: [@AlpacaHQ](https://x.com/AlpacaHQ/status/2092250645458047162) 2026-08-25.

**Submission**

1. **Dedicated competition paper account (one per email)** — not the lab book.
2. **Starting balance $100,000.**
3. **One-page write-up:** AI logic, risk gates, Alpaca infrastructure.
4. **All strategies must include options trading.**

**Also required (lablab + Alpaca):** public GitHub, demo URL, Trading API + MCP or CLI, paper only. Track name: **Options Alpha Agents**.

**Judged on:** P&L **and** creativity / engagement. Plus 2 social-engagement awards.

**Window:** Fri 2026-08-28 15:00 UTC → Fri 2026-09-04 15:00 UTC.

Kickoff 15:00 UTC = 11:00 ET. Last day submissions close 11:00 ET. Cash RTH sessions:

| Day | Notes |
|---|---|
| Fri Aug 28 | ~5 hours after kickoff |
| Mon Aug 31 | full |
| Tue Sep 1 | full |
| Wed Sep 2 | full |
| Thu Sep 3 | full |
| Fri Sep 4 | morning only if you submit at 11:00 ET |

That is **~4.5–5 trading sessions**, not a 90-day gate. Labor Day 2026 is Sep 7 — after the contest.

Prize copy disagrees slightly: Alpaca tweet $2.5k / $1.5k / $1k + 2 social; lablab header currently says $6,000 pool. Play as if **P&L + story + social** all score.

## New paper account — do this, do not touch the lab

Alpaca lets you run **multiple paper accounts**. Dashboard: click the paper account number (upper left) → **Open New Paper Account** → start at **$100,000** → generate **new API keys**.

- **Do not reset** the existing lab paper account. That would wipe the 90-day E1/E2 gate.
- **Do not** point FillTrue at the lab keys (the ~$104k book with SPY/VEA + leftover options).
- Name the new account something like `FillTrue-hackathon`.
- Put the new keys only in `filltrue/.env` (gitignored). `ALPACA_PAPER_TRADE=true`.

If the broker shows stock positions in `SPY` / `VEA` / `BND` / `BIL`, FillTrue refuses to trade (`lab_contamination`).

## Why the lab sleeve would lose this race

A 45 DTE 16–20Δ IWM CSP on $100k is a scientific instrument. Over 5 sessions:

- Theta is a rounding error vs $100k.
- One contract of premium (~$100) cannot win a P&L ranking.
- “No take-profit” is correct for a 90-day gate and **wrong** for a snapshot contest. Sitting on a winner through Friday is how you donate mark-to-market.

## Signals we keep (E1 / E2 brain)

| Signal | Contest use |
|---|---|
| SPY vs 200d SMA (crash brake) | **Hard.** Below 200d → no new short premium. Cash or a small put debit. |
| Dual-momentum risk-on/off | Side of the structure (bull vs sit). |
| IVP | High (≥50) → **sell** defined-risk premium. Low (<30) → **buy** premium. Mid → half-size credit. |
| Fill-sync | Unchanged. OPEN only on a true fill. Creativity score lives here. |

## What gets more aggressive (controlled)

| Dial | Lab | Contest |
|---|---|---|
| DTE | 30–60 (target 45) | **7–21 (target 14)** — no 0DTE |
| Delta | 16–20 | **25–35** |
| Structure | naked CSP | **defined-risk spreads default** (bull put / call debit) |
| Take profit | forbidden | **required** — bank 50% of credit, ~80% on debit |
| Flatten | 21 DTE | **contest end / DTE≤3** |
| Size | 1 lot | **2% of equity at risk per ticket**, max 4 tickets, 8% gross, 20 contracts cap |
| Underlying | IWM | IWM (liquid). SPY/QQQ only if IWM chain is empty |

0DTE, earnings lotteries, and “max leverage until it prints” are out. That is not controlled, and a blow-up on a $100k paper account is a visible P&L **loss**, not a clever story.

## Default playbook (risk-on week)

1. Confirm crash brake is **off** (SPY > 200d).
2. If IVP high: IWM bull put credit, ~14 DTE, ~30Δ short / $2–5 wide long, size to 2% max loss.
3. Limit at the credit. Poll fill. Never OPEN on submit.
4. Bank 50% of credit. Stop at 1.5× credit. Flatten Thursday close / Friday morning.
5. Repeat up to 4 concurrent tickets. Stop new risk if gross at-risk ≥ 8%.

If the brake is **on**: cash, or a small put debit if IV is cheap. Do not sell premium into a crash.

— Grok Build (grok-4.6, effort: high) · 2026-08-25
