"""Streamlit demo. Fixture replay — no keys required."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from filltrue.replay import print_report, run_fill_then_stop, run_ghost

ROOT = Path(__file__).resolve().parent.parent
EVENTS = json.loads((ROOT / "events.json").read_text())

st.set_page_config(page_title="FillTrue", page_icon="▣", layout="wide")
st.title("FillTrue")
st.caption("An options agent that only believes fills. Paper only.")

st.markdown(
    "Naive MCP wrappers record **OPEN** the moment `submit_order` returns. "
    "FillTrue waits for `filled_qty` and a real average price."
)

col1, col2 = st.columns(2)
ghost = run_ghost()
filled = run_fill_then_stop()
with col1:
    st.subheader("Act I — ghost DAY limit")
    st.metric("Naive OPEN count", ghost["naive_open"])
    st.metric("FillTrue OPEN count", ghost["filltrue_open"])
    st.json(ghost["filltrue_sync"][-1])
with col2:
    st.subheader("Act II — fill then 1.5× stop")
    st.metric("Remaining OPEN", filled["open"])
    st.write("Close intent")
    st.json(filled["close_intent"])

st.subheader("Replay (same as `python -m filltrue replay`)")
st.code(print_report(text=False))

st.markdown(
    "[Public demo](https://gbrussich52.github.io/filltrue/) · "
    "[GitHub](https://github.com/gbrussich52/filltrue)"
)
st.caption("Not investment advice. Paper trading only. No account numbers in this demo.")
