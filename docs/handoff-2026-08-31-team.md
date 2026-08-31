# FillTrue team brief — 2026-08-31 08:50 ET

## FROM: Grok Build
## TO: Opus (teammate) → then Fable (finalize)
## STATUS: In Progress

Giani: we are one team. Goal is to **win** the Alpaca Options Alpha Agents hackathon (ends 2026-09-04 15:00 UTC). Usage is almost gone on Claude (week 92%, Fable 73%). Be brutal and short. No new features. No trades from this pass.

## Live facts (verified this morning, not transcript)

- Market: **closed**. Next open 09:30 ET. Clock ~08:47 ET when pulled.
- Contest paper (created 2026-08-28): equity **$99,065** vs $100k start (−0.93%). Cash ~$59.1k. No SPY/VEA/BND/BIL stock. Options level 3. Paper.
- Positions (both `buy_to_open` **limit**, **true fills** — qty + avg price):
  1. `IWM260918C00300000` 81 long @ 2.58, mark 2.44, uPL **−$1,134**. Expiry Sep 18 → ~18 DTE. Matches `plan()` call_debit (risk-on + IVP<30).
  2. `IWM261120P00285000` 34 long @ 5.87, mark 5.93, uPL **+$204**. Expiry Nov 20 → **~81 DTE**. `contest.DTE_MAX=21`. Kernel would refuse this.
- `client_order_id` on both = raw UUIDs, **not** `filltrue-`. `source=access_key`. `alpaca.py` docstring: those two orders went out through ad-hoc REST and **bypassed `gate_order()`**.
- Monitor: launchd `com.giani.filltrue-monitor` loaded, last exit 0, 37 runs, last jsonl **Fri 15:45 ET**. Weekend silent is expected. Next fire ~09:00 ET.
- Tests: `filltrue/.venv/bin/python -m pytest` green (111 dots). Demo URL 200, last-modified Sat 08-29.
- Git: `main` clean, latest `e335c0e` (monitor must not strip a spread naked).

## Grok's opening bid (adversarial)

Kill or keep each. Add only if it can lose the contest.

1. **P0 docs lie.** README “What it trades” is still lab CSP 45 DTE / 16–20Δ. `prompts/SYSTEM.md` contest-mode says call debit 14 DTE, then non-negotiable #5 and Entry still say sell puts 45 DTE. `docs/RUNBOOK.md` still says there is no Alpaca client and no cron. `filltrue/alpaca.py` + launchd exist. Judges clone this.
2. **P0 book vs kernel.** Friday `plan()` = IWM call debit ~14 DTE. Sep 18 300c is in-band. Nov 20 285p is not. Either a documented cheap-vega exception or a position the product would refuse.
3. **P1 story split.** Demo/creativity = ghost-fill (keep — this is how we win engagement). Live P&L = long cheap IV. One-pager still reads like a CSP sleeve. Align copy; do not rebuild the demo.
4. **P1 isolation claim.** Public docs promise `filltrue-` prefix. Live orders don’t have it. `AlpacaBroker` still does not *require* the prefix.
5. **P2 picker defaults.** `picker.py` imports lab `DELTA_LO`/`DTE_MIN` from `policy.py`. Contest bands live in `contest.py`. Easy to pick the wrong band.
6. **Do not trade from this review.** Flattening the Nov put, adding risk, or placing anything is Giani’s call.

## Task for Opus

You are **Opus**, Grok Build’s teammate on FillTrue. Giani said we are a team: bounce, adversarial-check, then Fable finalizes. Do **not** re-derive the live account. Do **not** explore the rest of the portfolio. Do **not** edit yet.

Return only:

```
KEEP: <Grok items you agree are real, with file:line>
KILL: <Grok items that are wrong, one sentence why>
ADD: <new P0/P1 only, file:line, why it loses the contest>
TWEAK NOW: <max 5 file-level edits, ranked, that we can ship without Giani>
GIANI: <0–2 decisions that need him, default recommendation>
```

Read at most: `README.md`, `prompts/SYSTEM.md`, `docs/RUNBOOK.md`, `docs/ONE-PAGER.md`, `docs/CONTEST-RULES.md`, `index.html` (first 120 lines), `filltrue/contest.py`, `filltrue/gate.py`, `filltrue/alpaca.py`, `filltrue/picker.py`, `filltrue/agent.py`, `ops/monitor.py` (thesis triggers). Stop.

## Fable (after Opus)

One finalize pass on this file + Opus reply. Approve/kill tweaks. Then Grok implements.

## OUTPUTS

- **Opus:** could not launch. `claude -p` in this environment: `Not logged in · Please run /login`. Did not burn the 92% Claude week trying to force it.
- **Fable (advisor, 2026-08-31):** KEEP Grok 1,2,4,5,6. KILL “one-pager is still CSP-flavored” (L9–13 already contest). ADD: clone-run still only `sell_to_open` CSPs (`gate.py` L139–149, `agent.manage()` hardcodes credit) — do **not** wire debit execution this morning. TWEAK NOW 1–5 shipped below. GIANI: HOLD the Nov 20 put; no new tickets until Monday regime.

Shipped this morning (Grok, Fable-approved):

- `README.md` — contest agent, IV-follows-structure, live sleeve named
- `prompts/SYSTEM.md` — not a CSP-only agent; credit *and* debit payloads
- `docs/RUNBOOK.md` — AlpacaBroker + launchd monitor exist
- `docs/ONE-PAGER.md` — survival-cap sizing; cheap-IV live sleeve; 81-DTE hold called out
- `index.html` meta only
- `filltrue/cli.py` `propose`/`payload` use contest bands
- `filltrue/picker.py` — **lab `gate_entry` no longer overrides contest kwargs** (this was why propose returned nothing)
- tests: contest pick, cheap-IV `call_debit` CLI, 81 DTE refuse

Not shipped (Fable): debit execution path, prefix enforcement in `AlpacaBroker`, flattening the Nov put, new tickets.

## NEXT HANDOFF

Opus: if you open a session, you are on this team with Grok. Read this file. Do not re-derive the live account. Adversarial-check the picker fix and the docs. Do not trade.

— Grok Build (grok-4.6, effort: medium) · 2026-08-31 09:05 ET
