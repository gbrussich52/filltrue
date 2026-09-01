# FillTrue contest runbook

**Window:** Fri 2026-08-28 15:00 UTC → Fri 2026-09-04 15:00 UTC (5 cash sessions).
**Account:** a dedicated $100,000 paper account. Not the research account.

## How the loop actually runs

FillTrue is the brain: it decides, and it will not call anything OPEN until
the broker filled. Hands:

1. **Alpaca MCP** (`place_option_order` + `get_order_by_id`) in a session.
2. **`filltrue/alpaca.py` (`AlpacaBroker`)** — the gated path. Route new tickets
   through the agent so `gate_order()` actually sees them. The two 2026-08-28
   live fills went out through ad-hoc REST and bypassed the gate; do not
   repeat that.

A launchd job `com.giani.filltrue-monitor` (`ops/com.giani.filltrue-monitor.plist`)
re-evaluates every 15 minutes **weekdays 09:30–15:45 ET only** through
2026-09-04. No weekend wakes, no overnight. After that date the runner
`launchctl bootout`s itself. It names HOLD / TRIM / ADD / EXIT. The only
order it may submit is the Giani-authorized Thursday 1pm time-stop on the
Sep 10 296c.

```
FillTrue     the brain — decides, OPEN only on a true fill
AlpacaBroker / MCP  the hands — place the order
monitor      the eyes — a verdict every 15 min, human still clicks
```

## One-time setup

1. **New paper account.** Alpaca dashboard → click the **account number in the
   upper left** (not Settings — this is where people get stuck) → *Open New
   Paper Account* → start at **$100,000** → generate **new API keys**.

2. **Point the MCP at it.** `~/.claude.json` → `mcpServers.alpaca.env`:
   `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, and `ALPACA_PAPER_TRADE=true`.
   Restart the session — MCP env is read at connect time.

3. **Arm the contamination guard.** Fingerprint every account that must never
   be traded here, and list them:

   ```bash
   .venv/bin/python -c "from filltrue.gate import key_fingerprint; print(key_fingerprint('<research-account-key>'))"
   export FILLTRUE_FORBIDDEN_KEY_FINGERPRINTS=<fp1>,<fp2>
   ```

   Fingerprints only — never keys. This repo is public and carries no account
   identity of its own.

4. **Verify before the first order:**

   ```bash
   .venv/bin/python -m pytest -q          # network-free. If this is red, do not trade.
   ```

## Each session

**Pre-open — read the regime, don't guess it.**

```bash
# SPY vs 200d (risk-on/off) and realized-vol percentile (the IVP input)
../automated-trading/.venv/bin/python -c "
import yfinance as yf, numpy as np
for t in ('SPY','IWM'):
    h=yf.Ticker(t).history(period='3y')['Close'].astype(float)
    s,m=float(h.iloc[-1]),float(h.rolling(200).mean().iloc[-1])
    r=np.log(h).diff(); hv=(r.rolling(20).std()*np.sqrt(252)).dropna(); c=hv.iloc[-1]
    print(f'{t} {s:.2f} 200d {m:.2f} above={s>m} HV20 {c*100:.1f}% 1y-pct {100*(hv.tail(252)<c).mean():.0f}')"
```

Feed the IWM 1-year percentile in as `--ivp`. Do not invent it — the plan
inverts across that number, and a placeholder produces the opposite trade.

```bash
.venv/bin/python -m filltrue contest-plan --spy-above-200 --risk-on --ivp <pct>
```

**Open the ticket.** Take the plan's structure and underlying, then via Alpaca
MCP: pull the chain, pick ~30Δ at 7–21 DTE, submit a **limit** order.

**Then the rule the whole project exists for:** poll `get_order_by_id`.
An order id is not a position. Log `OPEN` only when `filled_qty >= qty` and
`filled_avg_price > 0`. A DAY limit that expires unfilled is **UNFILLED**, not
a short you now own.

**Manage.** Contest overlay differs from the lab on purpose: bank 50% of credit
(~80% on a debit), stop at 1.5× credit, and flatten into the deadline. The lab
holds for the right exit; the contest is scored on a snapshot, so sitting on a
winner through Friday donates mark-to-market.

**IVP pulse:** every 15 min the monitor reads RVX IVP. Low IVP + long
expiry (DTE > 21) is a hold — cheap vol plays out on the long-dated contract,
not on a 50% gamma stop. The Nov 20 285p is that ticket. Short calls still
use the 50% stop + Thursday 1pm clock. Harvest the long-vol hold at IVP ≥ 90,
not because a 5-day mark looks tired.

**Thursday 1pm ET time-stop (Giani 2026-09-01):** the Sep 10 296c
(`IWM260910C00296000`, entry $1.19) is a gamma ticket. If it is not up vs
entry at 2026-09-03 13:00 ET, the monitor EXITs it and submits
`sell_to_close` (market, RTH only, idempotent `client_order_id`). A print of
even a cent keeps it. The Sep 18 300c and the Nov put are **not** on this
clock.

## Friday 2026-09-04

Score is a snapshot at 15:00 UTC. Flatten everything in the morning session.
Submitting at 11:00 ET means the Friday morning session is your last.

## Refusals you should expect to see

| Message | Meaning |
|---|---|
| `live_refused` | `ALPACA_PAPER_TRADE` is falsey. FillTrue never trades live capital. |
| `forbidden_account` | The key fingerprints to a listed account. Wrong account — stop. |
| `lab_account` | The account holds research ETF **stock** (SPY/VEA/BND/BIL/VTI/AGG). Wrong account. |
| `session_closed` | A new DAY limit outside the session would ghost. Refused on purpose. |

None of these are bugs. Each is a trade that should not happen.
