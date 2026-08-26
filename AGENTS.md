# FillTrue — agent notes

Paper only. No live capital. No secrets in git.

- Policy: `filltrue/policy.py` (lab spine, no take-profit) vs `filltrue/contest.py` (5-day P&L overlay, take-profit required)
- Ledger: `filltrue/ledger.py` (OPEN only on true fill)
- Contest account: new $100k paper. Never the lab keys. `FILLTRUE_CONTEST=true`
- MCP hands: `prompts/SYSTEM.md`
- Tests must stay network-free
- Do not import the private `automated-trading` lab into this repo
