import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import price_feed


class YahooRetry(unittest.TestCase):
    def batch(self, missing=False):
        fields = ['Open', 'High', 'Low', 'Close', 'Volume']
        columns = pd.MultiIndex.from_product([fields, ['GOOD', 'NEW']], names=['Price', 'Ticker'])
        data = pd.DataFrame(10.0, index=pd.date_range('2026-10-05', periods=2, name='Date'), columns=columns)
        if missing:
            data.loc[:, pd.IndexSlice[:, 'NEW']] = np.nan
        return data

    def run_feed(self, responses):
        with patch('price_feed.provider_symbols', return_value={'GOOD': 'GOOD', 'OLD': 'NEW'}), patch('price_feed.time.sleep'), patch('price_feed.yf.download', side_effect=responses) as download:
            result = price_feed.yahoo(['GOOD', 'OLD'], '2026-01-01', pd.Timestamp('2026-10-07'))
        return result, download.call_args_list

    def test_partial_batch_recovers_only_missing_alias_without_threads(self):
        recovered = self.batch().loc[:, pd.IndexSlice[:, ['NEW']]]
        result, calls = self.run_feed([self.batch(True), recovered])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].args[0], ['NEW'])
        self.assertFalse(calls[1].kwargs['threads'])
        self.assertTrue(calls[1].kwargs['auto_adjust'])
        self.assertTrue(calls[1].kwargs['repair'])
        self.assertEqual(set(result.Symbol), {'GOOD', 'OLD'})
        self.assertEqual(len(result), 4)
        self.assertEqual(set(result.loc[result.Symbol.eq('OLD'), 'Provider Symbol']), {'NEW'})
        self.assertTrue(result.Close.notna().all())

    def test_persistent_failure_is_bounded_and_remains_missing(self):
        result, calls = self.run_feed([self.batch(True), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()])
        self.assertEqual(len(calls), 4)
        audit = price_feed.audit_history(result, ['GOOD', 'OLD'], '2026-10-06', now='2026-10-07T04:00:00Z')
        self.assertEqual(audit.set_index('Symbol').loc['OLD', 'price_status'], 'MISSING_PRICE')

    def test_complete_batch_does_not_repeat_download(self):
        result, calls = self.run_feed([self.batch()])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(result), 4)

