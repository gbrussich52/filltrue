from __future__ import annotations

from filltrue.cli import main
from filltrue.replay import print_report


def test_replay_cli(capsys):
    assert main(["replay"]) == 0
    out = capsys.readouterr().out
    assert "Naive ledger OPEN count : 1" in out
    assert "FillTrue OPEN count     : 0" in out
    assert "buy_to_close" in out


def test_propose_cli(capsys):
    assert main(["propose"]) == 0
    out = capsys.readouterr().out
    assert "IWM261016P00220000" in out


def test_payload_cli(capsys):
    assert main(["payload"]) == 0
    out = capsys.readouterr().out
    assert "sell_to_open" in out
    assert "limit" in out


def test_contest_plan_cli(capsys):
    assert main(["contest-plan", "--spy-above-200", "--ivp", "70"]) == 0
    out = capsys.readouterr().out
    assert "bull_put_credit" in out
    assert main(["contest-plan", "--no-spy-above-200", "--ivp", "70"]) == 0
    out = capsys.readouterr().out
    assert "cash" in out


def test_print_report_matches_cli():
    report = print_report(text=False)
    assert "OPEN is a fill" in report
    assert "Ghost DAY limit" in report
