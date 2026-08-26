# 90-second judge video

1. **0:00–0:12** Title card: “FillTrue — an options agent that only believes fills.” Paper only. Alpaca MCP.
2. **0:12–0:35** Terminal: `python -m pytest` (green) then `python -m filltrue replay`. Point at `Naive OPEN count : 1` vs `FillTrue OPEN count : 0`.
3. **0:35–0:70** Demo URL: run the day. Naive card stamps OPEN on submit, then VOID. FillTrue stays WORKING, then UNFILLED. Second beat: a real fill stamps FILL, stop uses `buy_to_close`.
4. **0:70–0:90** One line: “MCP is the hands. FillTrue is the brain that will not lie about a fill.” Repo URL + demo URL.

Do not show account numbers, buying power of other sleeves, or live keys.
