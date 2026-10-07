import unittest

import pandas as pd

from historical_zones import atr_series, candidates, evaluate, zones_for


class HistoricalZones(unittest.TestCase):
    def frame(self, n=80):
        return pd.DataFrame({
            'Date': pd.bdate_range('2024-01-02', periods=n),
            'Open': 110.0,
            'High': 112.0,
            'Low': 108.0,
            'Close': 110.0,
            'Volume': 1000.0,
        })

    def set_bar(self, g, i, close, low, high):
        g.loc[i, ['Open', 'High', 'Low', 'Close']] = [close, high, low, close]

    def event_frame(self):
        g = self.frame(40)
        # Two defenses after ATR warmup, a break, a reclaim, then a retest.
        self.set_bar(g, 15, 101.0, 99.0, 102.0)
        self.set_bar(g, 16, 105.0, 103.0, 107.0)
        self.set_bar(g, 20, 101.0, 99.0, 102.0)
        self.set_bar(g, 21, 105.0, 103.0, 107.0)
        self.set_bar(g, 25, 98.0, 96.0, 99.0)
        self.set_bar(g, 26, 98.0, 96.0, 99.0)
        self.set_bar(g, 27, 102.0, 101.0, 104.0)
        self.set_bar(g, 31, 101.0, 99.0, 102.0)
        self.set_bar(g, 32, 105.0, 103.0, 107.0)
        member = {'i': 5, 'date': g.Date.iloc[5], 'price': 100.0, 'scale': 2}
        return g, member

    def test_short_history_does_not_produce_selected_zones(self):
        g = self.frame(29)
        selected, _, _, _, tolerance = zones_for(g)
        self.assertTrue(all(value is None for value in selected.values()))
        self.assertIsNotNone(tolerance)

    def test_pivot_is_one_event_with_two_bar_confirmation(self):
        g = self.frame(40)
        g.loc[20, 'Low'] = 100.0

        support = [x for x in candidates(g)['Support'] if x['i'] == 20]

        self.assertEqual(len(support), 1)
        self.assertEqual(support[0]['price'], 100.0)
        self.assertEqual(support[0]['confirmed'], g.Date.iloc[22])
        self.assertLessEqual(support[0]['confirmed'], g.Date.iloc[-1])

    def test_break_reclaim_and_retest_are_distinct_chronological_events(self):
        g, member = self.event_frame()
        result = evaluate(g, 'Support', [member], atr_series(g), 7)

        types = [event['type'] for event in result['events']]
        self.assertEqual(types.count('Defended test'), 2)
        self.assertEqual(types.count('Break'), 1)
        self.assertEqual(types.count('Reclaim'), 1)
        self.assertEqual(types.count('Defended retest'), 1)
        self.assertEqual(result['tests'], 3)
        self.assertEqual(result['tests_since_break'], 1)
        dates = [event['date'] for event in result['events'] if 'date' in event]
        self.assertEqual(dates, sorted(dates))

    def test_event_classification_scales_with_price_and_atr(self):
        g, member = self.event_frame()
        original = evaluate(g, 'Support', [member], atr_series(g), 7)

        scaled = g.copy()
        scaled[['Open', 'High', 'Low', 'Close']] *= 10
        scaled_member = {**member, 'price': member['price'] * 10}
        result = evaluate(scaled, 'Support', [scaled_member], atr_series(scaled), 7)

        self.assertEqual([e['type'] for e in result['events']],
                         [e['type'] for e in original['events']])
        self.assertEqual(result['tests_since_break'], original['tests_since_break'])
        self.assertAlmostEqual(
            result['events'][0]['reaction_pct'],
            original['events'][0]['reaction_pct'],
        )
        self.assertAlmostEqual(atr_series(scaled)[-1], atr_series(g)[-1] * 10)

    def test_pending_touch_uses_supplied_history_cutoff(self):
        g = self.frame(40)
        self.set_bar(g, len(g) - 1, 101.0, 99.0, 102.0)
        member = {'i': 5, 'date': g.Date.iloc[5], 'price': 100.0, 'scale': 2}

        result = evaluate(g, 'Support', [member], atr_series(g), 7)
        pending = [event for event in result['events'] if event['type'] == 'Pending touch']

        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['resolved'], g.Date.iloc[-1])
        self.assertLessEqual(pending[0]['resolved'], g.Date.iloc[-1])
        self.assertLessEqual(result['band_known_date'], g.Date.iloc[-1])


if __name__ == '__main__':
    unittest.main()
