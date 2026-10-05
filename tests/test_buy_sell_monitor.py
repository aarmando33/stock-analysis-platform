import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from buy_sell_monitor import *


def history(n=300, descending=False):
    dates=pd.bdate_range(end='2026-10-02',periods=n)
    c=100+np.arange(n)*.08+np.sin(np.arange(n)/4)*2
    if descending:c=c[::-1]
    return pd.DataFrame({'Date':dates,'Symbol':'TEST','Open':c-.1,'High':c+1,'Low':c-1,'Close':c,'Volume':1000.})


class Calculations(unittest.TestCase):
    def test_range_position(self):
        self.assertEqual(range_position(pd.Series([10.,30.]),14.),(80.,14.))
        self.assertTrue(np.isnan(range_position(pd.Series([10.,10.]),10.)[0]))

    def test_fundamental_normalization_and_coverage(self):
        x=fundamental_evidence({'Revenue Growth':.2,'EPS Growth':.2,'Operating Margin':.3,
                                'Market Cap':100,'Free Cash Flow':8,'Net Debt / EBITDA':0,
                                'EPS Revision 90D':.1,'Forward PE':10,'Peer Forward PE':20})
        self.assertEqual(x['Fundamentals Score'],100)
        self.assertEqual(x['Fundamental Input Coverage %'],100)
        self.assertEqual(x['Revisions Score'],100)
        missing=fundamental_evidence({})
        self.assertTrue(np.isnan(missing['Fundamentals Score']))
        self.assertEqual(missing['Fundamental Input Coverage %'],0)

    def test_volume_baseline_excludes_today(self):
        g=history();g.loc[g.index[-1],'Volume']=2000
        o=calculate(g,g.Close.iloc[-1],'2026-10-02')
        self.assertEqual(o['Relative Volume'],2)
        self.assertEqual(o['Average Volume 20D'],1000)

    def test_rsi_edges(self):
        self.assertEqual(rsi(pd.Series(np.arange(30.))).iloc[-1],100)
        self.assertEqual(rsi(pd.Series(np.arange(30.)[::-1])).iloc[-1],0)
        self.assertEqual(rsi(pd.Series([10.]*30)).iloc[-1],50)

    def test_macd_against_recurrence(self):
        s=pd.Series(np.arange(50.));a=b=0.;sig=0.
        for x in s:
            a+=(x-a)*2/13;b+=(x-b)*2/27;sig+=((a-b)-sig)*.2
        line,signal,h=macd(s)
        self.assertAlmostEqual(line.iloc[-1],a-b)
        self.assertAlmostEqual(signal.iloc[-1],sig)
        self.assertAlmostEqual(h.iloc[-1],a-b-sig)

    def test_atr_gap(self):
        g=history();g['Close']=10.;g['High']=11.;g['Low']=9.
        self.assertAlmostEqual(atr(g).iloc[-1],2)
        g.loc[g.index[-1],['High','Low','Close']]=[21.,19.,20.]
        self.assertAlmostEqual(atr(g).iloc[-1],2+9/14)

    def test_proximity_boundaries(self):
        self.assertEqual([proximity(x) for x in [2,2.01,3,3.01,5,5.01]],
                         ['Strong Proximity','Near','Near','Approaching','Approaching','Not Near'])

    def test_major_sources_and_sides(self):
        g=history();p=g.Close.iloc[-1]
        sup,res=levels(g,p,True)
        self.assertLess(sup['value'],p)
        if res:self.assertGreater(res['value'],p)
        self.assertNotIn('5-session',sup['source'])
        self.assertNotIn('21-session',sup['source'])

    def test_relative_strength_alignment(self):
        s=pd.Series([100,110,121],index=pd.date_range('2026-01-01',periods=3))
        b=pd.Series([100,100,110],index=s.index)
        self.assertAlmostEqual(relative_strength(s,b,2),10.)

    def test_price_volume_used_without_obv_origin(self):
        g=history(descending=True);g['Close']=np.arange(300,0,-1.)
        o=calculate(g,g.Close.iloc[-1],'2026-10-02')
        self.assertEqual(o['OBV20 %'],-100)
        self.assertEqual(o['Money Flow'],'Leaving')

    def test_missing_volume_is_unavailable(self):
        g=history();g['Volume']=np.nan
        o=calculate(g,g.Close.iloc[-1],'2026-10-02')
        self.assertEqual(o['Money Flow'],'Unavailable')
        self.assertTrue(np.isnan(o['OBV']))

    def test_missing_evidence_cannot_grant_buy(self):
        g=history();o=calculate(g,g.Close.iloc[-1],'2026-10-02')
        self.assertEqual(o['Fundamentals Points'],0)
        self.assertEqual(o['Environment Points'],0)
        self.assertLess(o['Evidence Coverage %'],75)
        self.assertNotIn(o['Overall Signal/Action'],['Buy/Accumulate','Strong Buy Zone'])
        self.assertEqual(o['Owned/Watch'],'Ownership/Cost Basis Unavailable')
        self.assertTrue(np.isnan(o['Cost Basis']))

    def test_existing_metrics_and_bounds(self):
        g=history();o=calculate(g,g.Close.iloc[-1],'2026-10-02')
        self.assertAlmostEqual(o['50D MA'],g.Close.iloc[-50:].mean())
        self.assertAlmostEqual(o['2W %'],100*(g.Close.iloc[-1]/g.Close.iloc[-11]-1))
        for name in ['Opportunity Score','Setup Confidence','Bottom Confidence']:
            self.assertGreaterEqual(o[name],0);self.assertLessEqual(o[name],100)

    def test_ipo_and_history_cutoff(self):
        g=history(40);o=calculate(g,g.Close.iloc[-1],'2026-10-02')
        expected=range_position(g.Close,g.Close.iloc[-1])[0]
        self.assertAlmostEqual(o['Primary Win%'],expected)
        extra=g.copy();extra.Date+=pd.Timedelta(days=365);extra.Close=10000
        both=pd.concat([g,extra])
        self.assertEqual(calculate(both,g.Close.iloc[-1],'2026-10-02')['Primary Win%'],expected)

    def test_calendar_weekend_holiday_and_preclose(self):
        self.assertEqual(latest_session('2026-10-04T18:00:00Z'),'2026-10-02')
        self.assertEqual(latest_session('2026-07-03T21:00:00Z'),'2026-07-02')
        self.assertEqual(latest_session('2026-10-02T19:00:00Z'),'2026-10-01')


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)
        g=history();g.to_csv(self.p/'price_history.csv.gz',index=False,compression='gzip')
        pd.DataFrame([{'Symbol':'TEST','Current Price':g.Close.iloc[-1],'Price Date':'2026-10-02',
                       'Provider':'fixture','Price Basis':'adjusted daily OHLC','price_status':'OK'}]).to_csv(self.p/'prices_latest.csv',index=False)
        (self.p/'price_audit.json').write_text(json.dumps({'latest_market_date':'2026-10-02','expected_tickers':1}))
        pd.DataFrame({'Symbol':['TEST']}).to_csv(self.p/'tickers.csv',index=False)

    def tearDown(self):self.tmp.cleanup()

    def go(self,**kw):return run(self.p,self.p/'tickers.csv','2026-10-02',historical=True,**kw)

    def test_views_and_dynamic_counts(self):
        x=self.go();self.assertEqual(x['counts']['Usable'],1)
        self.assertEqual(len(x['views']['Master']),1)
        for r in x['views']['At-Approach Support']:
            self.assertEqual(r['Breakdown Status'],'None')
        self.assertEqual(len(x['views']['Owned Positions']),0)

    def test_duplicate_universe(self):
        pd.DataFrame({'Symbol':['TEST','TEST']}).to_csv(self.p/'tickers.csv',index=False)
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.go()

    def test_stale_gate(self):
        (self.p/'price_audit.json').write_text(json.dumps({'latest_market_date':'2026-10-01','expected_tickers':1}))
        with self.assertRaisesRegex(ValueError,'INCOMPLETE'):self.go()

    def test_split_or_price_basis_mismatch(self):
        f=pd.read_csv(self.p/'prices_latest.csv');f['Current Price']/=2;f.to_csv(self.p/'prices_latest.csv',index=False)
        self.assertEqual(self.go()['counts']['Usable'],0)
        self.assertEqual(self.go()['views']['Master'][0]['price_status'],'PRICE_HISTORY_MISMATCH')

    def test_future_context(self):
        f=self.p/'context.csv';pd.DataFrame([{'Ticker':'TEST','Source':'test','As Of':'2026-10-03','Raw Evidence':'test'}]).to_csv(f,index=False)
        with self.assertRaisesRegex(ValueError,'Future'):self.go(context_path=f)


if __name__=='__main__':unittest.main()
