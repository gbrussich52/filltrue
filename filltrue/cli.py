"""CLI: replay, propose, demo. Default does no live trading."""

from __future__ import annotations

import argparse
import json
import sys

from filltrue import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="filltrue",
        description="An options agent that only believes fills. Paper only.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("replay", help="run the ghost + fill fixtures (no network)")
    sub.add_parser("propose", help="pick a CSP from the demo chain")
    sub.add_parser("payload", help="print MCP place_option_order JSON for the demo CSP")
    p_plan = sub.add_parser("contest-plan", help="map lab signals → 5-day contest structure")
    p_plan.add_argument("--equity", type=float, default=100_000.0)
    p_plan.add_argument("--start-equity", type=float, default=100_000.0)
    p_plan.add_argument("--sessions-left", type=int, default=5)
    p_plan.add_argument("--spy-above-200", action=argparse.BooleanOptionalAction, default=True)
    p_plan.add_argument("--risk-on", action=argparse.BooleanOptionalAction, default=True)
    p_plan.add_argument("--ivp", type=float, default=55.0)
    p_demo = sub.add_parser("demo", help="launch Streamlit (requires streamlit extra)")
    p_demo.add_argument("--port", type=int, default=8501)

    args = parser.parse_args(argv)

    if args.cmd == "replay":
        from filltrue.replay import print_report

        print_report()
        return 0

    if args.cmd == "propose":
        from filltrue.picker import pick_csp
        from filltrue.replay import AS_OF, demo_chain

        cand = pick_csp(demo_chain(), as_of=AS_OF, underlying="IWM")
        if cand is None:
            print("no candidate", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "symbol": cand.symbol,
                    "delta": cand.delta,
                    "dte": cand.dte,
                    "limit": cand.limit_price,
                    "strike": cand.strike,
                },
                indent=2,
            )
        )
        return 0

    if args.cmd == "contest-plan":
        from filltrue.contest import Regime, sized_plan

        out = sized_plan(
            Regime(
                spy_above_200=args.spy_above_200,
                risk_on=args.risk_on,
                ivp=args.ivp,
            ),
            equity=args.equity,
            start_equity=args.start_equity,
            sessions_remaining=args.sessions_left,
        )
        print(json.dumps(out, indent=2))
        return 0


    if args.cmd == "payload":
        from filltrue.agent import client_order_id, mcp_place_payload
        from filltrue.gate import open_intent
        from filltrue.picker import pick_csp
        from filltrue.replay import AS_OF, demo_chain

        cand = pick_csp(demo_chain(), as_of=AS_OF, underlying="IWM")
        assert cand is not None
        intent = open_intent(
            cand.symbol,
            cand.limit_price,
            client_order_id=client_order_id(cand.symbol),
        )
        print(json.dumps(mcp_place_payload(intent), indent=2))
        return 0

    if args.cmd == "demo":
        try:
            from streamlit.web.cli import main as st_main
        except ImportError:
            print("pip install 'filltrue[demo]'  # streamlit extra", file=sys.stderr)
            return 1
        from pathlib import Path

        app = Path(__file__).resolve().parent.parent / "demo" / "app.py"
        sys.argv = ["streamlit", "run", str(app), "--server.port", str(args.port)]
        st_main()
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
