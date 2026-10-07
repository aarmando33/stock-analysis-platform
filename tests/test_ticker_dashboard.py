import json,tempfile,unittest
from pathlib import Path
from ticker_dashboard import build_dashboard
from compact_monitor import level_candidate
from zone_monitor import report_details
import pandas as pd

class TickerDashboard(unittest.TestCase):
    def test_failed_quote_is_not_presented_as_current_in_zone_details(self):
        report={'session':'2026-10-06','calculations':[{'Ticker':'TEST','Price':100,'price_status':'STALE_PRICE'}]}
        history=pd.DataFrame(columns=['Date','Symbol','Open','High','Low','Close','Volume'])
        report_details(report,history,{},'2026-10-07T01:00:00Z')
        self.assertEqual(len(report['zone_details']),4)
        self.assertTrue(all(x['Current Price'] is None for x in report['zone_details']))
        self.assertIsNone(report['ticker_dashboard_data']['tickers'][0]['price'])

    def test_snapshot_escapes_text_and_preserves_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'report.html'
            build_dashboard({'cutoff':'2026-10-06','tickers':[{'ticker':'TEST','name':'</script><script>bad()</script>',
                'price':100,'market_cap':None,'win':80,'win52':70,'win6':60,'price80':90,
                'history':[{'date':'2026-10-06','open':99,'high':101,'low':98,'close':100},
                           {'date':'2026-10-07','open':110,'high':112,'low':108,'close':111}],
                'indicators':{'20D MA':99,'200D MA':None}}]},target)
            text=target.read_text(encoding='utf8')
            self.assertNotIn('</script><script>bad()',text)
            raw=text.split('<script id="dashboard-data" type="application/json">')[1].split('</script>')[0]
            data=json.loads(raw)
            self.assertEqual(len(data['tickers'][0]['history']),1)
            self.assertIsNone(data['tickers'][0]['market_cap'])
            for label in ['Win%','Win52%','Win6mo%','price_suggest_80','Moving-average references']:self.assertIn(label,text)

    def test_zone_screen_accepts_unconfirmed_structure_but_not_bad_data(self):
        row={'Price':100,'price_status':'OK','S1 Min':96,'S1 Max':98,'Short Support Tests':0}
        self.assertTrue(level_candidate(row,'Support'))
        self.assertFalse(level_candidate({**row,'price_status':'STALE_PRICE'},'Support'))
        self.assertFalse(level_candidate({**row,'S1 Min':None},'Support'))
        self.assertFalse(level_candidate({**row,'S1 Min':80,'S1 Max':90},'Support'))

if __name__=='__main__':unittest.main()
