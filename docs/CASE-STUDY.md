# The bug, caught in the wild

FillTrue is built on one claim: **an order id is not a position, and a status
word is not a fill.** Every agent in this contest will be tempted to log `OPEN`
when `place_option_order` returns. Alpaca will hand you `status=new` and
`filled_qty=0` all day long.

That claim is easy to assert and hard to prove. On **2026-09-03**, four sessions
into this contest, it got proven — not by a unit test, but by a real system
running the naive pattern for 49 days.

## The natural experiment

The author runs a second, older options lab in a **separate Alpaca paper
account** (the one disclosed in the README's contest-vs-lab table). Same broker,
same API, same option types. One difference that matters:

> The lab records a position immediately after `submit_order()` returns.
> FillTrue records a position only when the broker confirms a fill.

Nobody designed this as an experiment. It became one because the two codebases
made opposite choices about the same line of code.

## What the ledger said vs. what the broker said

A full reconciliation of 49 days of the lab's cash-secured-put sleeve against
the broker's own order history:

| | Local ledger | Broker |
|---|---|---|
| Sell-to-open orders submitted | 11 | 11 |
| **Actually filled** | **11** | **5** |
| Expired unfilled (DAY limit, never filled) | 0 | **6** |
| Completed round-trip cycles | 8 | **4** |

**Six shorts that never existed** sat on the books as open positions for weeks.
They accrued unrealized P&L. They appeared in the weekly scorecard. Two of them
were reported as *open and profitable* the day before the audit.

## Why it compounds instead of staying still

A phantom position is not a static accounting error. It is an input to
everything downstream:

**1. The exit logic acts on it.** The sleeve's close path submitted a market
**buy** to "close" shorts that were never opened. With no short to offset, each
buy opened a *long* put outright. Four of them, **$895** of premium spent
acquiring positions nobody intended to own. The largest was a single put bought
for **$830**.

**2. The research record inherits it.** That $830 purchase was written up in a
weekly report as a **stop-loss on a real position, −$416**. It was not a stop
loss. It was the bug buying an option. A human read that number, believed it,
and carried it into a hypothesis scorecard.

**3. The statistics are computed from it.** The sleeve's headline record was
built on 8 cycles. Four were fiction. One hypothesis showed a mixed 4L/2W record
that, rebuilt from the broker's ledger, is **0W/3L** — a different conclusion
about whether the strategy works, from the same 49 days of trading.

A second variant of the same root cause appeared in a sibling script: a position
was flagged `closed = True` at the moment the *closing* order was submitted. That
close order expired unfilled too. The position stayed open, its stop rule was
never applied again, and it drifted unmanaged for **14 days**.

## The root cause is one line, in three places

Three different scripts, written weeks apart, each independently made the same
choice: **treat the return of `submit_order()` as the event, instead of polling
the broker for a terminal order state.** It was patched twice, per-script. The
class survived both times because the fix was local and the mistake was
architectural.

## What FillTrue does instead

```python
# OPEN requires a true fill. Status words are rumors.
filled_qty >= qty and filled_avg_price > 0
```

- **Submit → `WORKING`, never `OPEN`.** An id buys you nothing.
- **Poll to a terminal state.** `expired` DAY limit → `UNFILLED`, dropped.
- **Reconcile drops local `OPEN`s the broker cannot confirm.**
- **Close intent is explicit** (`buy_to_close` / `sell_to_close`), so a stop can
  never open a fresh long on top of a short that isn't there — the exact
  mechanism that spent $895 above.
- **`ops/flatten.py` polls every deadline ticket** and reports unfilled as
  unfilled, exiting non-zero rather than recording a close that didn't happen.

Run it yourself, no keys and no network:

```bash
python -m filltrue replay
```

```
Naive ledger OPEN count : 1
FillTrue OPEN count     : 0
```

That replay is the same failure the table above describes, reduced to one order.

## The honest caveats

- **This is paper money.** Both accounts, no live capital, by design and by rule.
- **n = 1 system, 49 days.** One lab, one sleeve. Not a survey.
- FillTrue's fill gate was written at the start of this contest (2026-08-28) on
  the strength of the *hypothesis*. The 09-03 audit is independent confirmation
  at scale, not the reason the gate exists — but it is the reason we can now put
  a number on what the gate is worth.
- The lab's phantom positions have been reconciled and a read-only sensor now
  runs against its broker ledger daily. Its findings are public in that repo's
  learning log, including the ones that make its own past reports wrong.

## Why this is the interesting problem

Roughly 2,400 agents registered for this contest. Most will wrap an LLM around
`place_option_order`. The model will pick good tickers some days and bad ones
others, and the P&L will be mostly noise over five sessions.

The part that isn't noise is whether your agent knows what it owns.

An agent that believes it holds a position it does not hold will size the next
trade against a false denominator, apply a stop to nothing, report a return it
never earned, and — as the $830 put shows — *spend real money* acting on the
belief. None of that requires a bad model. It requires one optimistic line of
plumbing, and it degrades silently for as long as you let it.

FillTrue is small on purpose. It only believes fills.
