"""Flatten planner: pure, network-free, one case per way the last morning bites."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ops.flatten import plan, bump_price


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


class BumpPrice(unittest.TestCase):
    """The re-price ladder. A limit left at a stale quote is the whole reason
    this project exists, so the crossing has to actually cross."""

    def test_sell_crosses_down_further_each_round(self):
        # Under $3 the tick is a penny.
        self.assertEqual(bump_price(1.79, True, 1), 1.78)
        self.assertEqual(bump_price(1.79, True, 2), 1.77)
        self.assertEqual(bump_price(1.79, True, 3), 1.76)

    def test_buy_crosses_up(self):
        self.assertEqual(bump_price(1.79, False, 2), 1.81)

    def test_nickel_tick_at_and_above_three_dollars(self):
        self.assertEqual(bump_price(5.62, True, 1), 5.57)
        self.assertEqual(bump_price(3.00, True, 1), 2.95)
        self.assertEqual(bump_price(2.99, True, 1), 2.98)

    def test_never_goes_below_the_minimum_tradable_price(self):
        # A near-worthless long must not be priced at or below zero.
        self.assertEqual(bump_price(0.02, True, 5), 0.01)
        self.assertGreater(bump_price(0.01, True, 9), 0)

    def test_round_zero_is_the_untouched_marketable_price(self):
        self.assertEqual(bump_price(1.79, True, 0), 1.79)
