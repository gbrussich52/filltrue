"""Flatten planner: pure, network-free, one case per way the last morning bites."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ops.flatten import plan


def q(bid, ask): return {"latestQuote": {"bp": bid, "ap": ask}}


class TestPlan(unittest.TestCase):
    def test_long_is_sold_at_the_bid(self):
        t = plan([{"symbol": "IWM260910C00296000", "qty": "180"}],
                 {"IWM260910C00296000": q(1.64, 1.68)})[0]
        self.assertEqual((t["side"], t["position_intent"], t["limit"], t["qty"]),
                         ("sell", "sell_to_close", 1.64, 180))

    def test_short_is_bought_at_the_ask(self):
        t = plan([{"symbol": "IWM261120P00285000", "qty": "-34"}],
                 {"IWM261120P00285000": q(5.70, 5.80)})[0]
        self.assertEqual((t["side"], t["position_intent"], t["limit"], t["qty"]),
                         ("buy", "buy_to_close", 5.80, 34))

    def test_no_quote_is_blocked_not_priced_at_zero(self):
        # A zero limit would be sent as a real order and sit unfilled through
        # the snapshot. Refusing is the only honest move.
        t = plan([{"symbol": "IWM260918C00300000", "qty": "81"}],
                 {"IWM260918C00300000": q(0, 0)})[0]
        self.assertIsNone(t["limit"])
        self.assertEqual(t["blocked"], "no quote on the close side")

    def test_missing_snapshot_entirely_is_blocked(self):
        t = plan([{"symbol": "IWM260918C00300000", "qty": "81"}], {})[0]
        self.assertEqual(t["blocked"], "no quote on the close side")

    def test_zero_qty_position_is_skipped(self):
        self.assertEqual(plan([{"symbol": "X", "qty": "0"}], {}), [])

    def test_every_open_leg_gets_a_ticket(self):
        pos = [{"symbol": "A", "qty": "180"}, {"symbol": "B", "qty": "81"},
               {"symbol": "C", "qty": "-34"}]
        got = plan(pos, {"A": q(1, 2), "B": q(3, 4), "C": q(5, 6)})
        self.assertEqual([t["symbol"] for t in got], ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()
