import unittest
import pandas as pd
from zone_monitor import reference_extremes,wide_zone_fields,report_details
from export_monitor import build
from compact_monitor import BASE,VOLUME_FIELDS

class ZoneColumns(unittest.TestCase):
    def history(self):
        dates=pd.bdate_range('2020-02-19','2020-05-05')
        return pd.DataFrame({'Date':dates,'Low':range(10,10+len(dates)),
                             'High':range(20,20+len(dates))})

    def test_reference_extremes_use_adjusted_low_high_and_cutoff(self):
        g=self.history();g.loc[len(g)-1,'High']=9999
        out=reference_extremes(g,'2020-04-30')
        self.assertEqual(out['Min COVID'],10)
        self.assertEqual(out['Min COVID Date'],'2020-02-19')
        self.assertLess(out['Max Since COVID'],9999)
        self.assertEqual(out['COVID Coverage'],'Full window')
        self.assertEqual(out['Min Since COVID Date'],'2020-03-02')

    def test_late_history_does_not_invent_covid_price(self):
        out=reference_extremes(self.history().iloc[20:],'2020-04-30')
        self.assertIsNone(out['Min COVID'])
        self.assertIsNone(out['Max COVID'])
        self.assertIsNotNone(out['Min Since COVID'])
        self.assertTrue(out['Since COVID Coverage'].startswith('Available history'))

    def test_three_zones_preserve_tied_boundary_dates(self):
        zone={'low':10,'high':11,'state':'Historical; no recent defense','window':252,
              'band_known_date':'2026-01-10','tests_since_break':2,
              'members':[{'price':10,'date':'2026-01-01'},{'price':10,'date':'2026-01-02'},
                         {'price':11,'date':'2026-01-08'}],'events':[]}
        fields=wide_zone_fields({'Support Major':zone})
        self.assertEqual(fields['S3 Min'],10)
        self.assertEqual(fields['S3 Min Date'],'2026-01-01; 2026-01-02')
        self.assertEqual(fields['S3 Max Date'],'2026-01-08')
        self.assertIsNone(fields['R3 Min'])

    def test_wide_details_has_one_row_per_ticker_and_frozen_price(self):
        r={'session':'2026-10-08','calculations':[{'Ticker':'IPO','Price':20,'price_status':'OK'}],
           'views':{},'positions':[],'counts':{}}
        history=pd.DataFrame(columns=['Date','Symbol','Open','High','Low','Close','Volume'])
        report_details(r,history,{},'now')
        self.assertEqual(len(r['zone_summary']),1)
        self.assertEqual(len(r['zone_details']),4) # Full JSON evidence retained.
        wb=build(r,compact=True);sh=wb['Zone Details']
        self.assertEqual(sh.max_row,2)
        self.assertEqual([c.value for c in sh[1]][:2],['Ticker','Current Price'])
        self.assertEqual(sh.freeze_panes,'C2')
        self.assertIn('S3 Min',[c.value for c in sh[1]])
        self.assertTrue(all(k in BASE for k in ['S3 Min','R3 Max','Min COVID','Max Since COVID']+VOLUME_FIELDS))

if __name__=='__main__':unittest.main()
