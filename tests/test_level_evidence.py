import unittest
import numpy as np
import pandas as pd
from buy_sell_monitor import calculate, levels, defended_tests

class LevelEvidence(unittest.TestCase):
    def frame(self,n=300):
        return pd.DataFrame({'Date':pd.bdate_range(end='2026-10-05',periods=n),
             'Open':110.,'Close':110.,'High':112.,'Low':108.,'Volume':1000.})
    def test_overlapping_horizons_do_not_inflate_strength(self):
        g=self.frame();g.loc[[250,270,290],'Low']=[100.,100.3,100.2]
        support,_=levels(g,110,True)
        self.assertEqual(support['tests'],2)
        self.assertEqual(support['strength'],40)
        self.assertIn('63-session',support['source'])
        self.assertIn('252-session',support['source'])
    def test_formation_is_not_a_retest(self):
        g=self.frame();g.loc[250,'Low']=100
        self.assertEqual(levels(g,110,True),(None,None))
        g.loc[270,'Low']=100.3
        self.assertIsNone(levels(g,110,True)[0])
    def test_break_resets_previous_defenses(self):
        g=self.frame();g.loc[[250,270,290],'Low']=[100.,100.3,100.2]
        g.loc[295,['Open','Close','Low','High']]=[98,98,97,99]
        self.assertIsNone(levels(g,110,True)[0])
    def test_current_range_edge_and_ma_are_not_confirmed_levels(self):
        g=self.frame();g.Close=np.arange(300.)+100;g.Open=g.Close;g.High=g.Close+1;g.Low=g.Close-1
        self.assertEqual(levels(g,g.Close.iloc[-1]),(None,None))
    def test_partial_bottom_inputs_are_kept_without_full_score(self):
        g=self.frame();g.loc[[250,270,290],'Low']=[100.,100.3,100.2]
        out=calculate(g,110,'2026-10-05')
        self.assertTrue(np.isnan(out['Bottom Confidence']))
        self.assertEqual(out['Bottom Confidence Coverage %'],57.1)
        evidence=[out['Bottom '+k+' Evidence'] for k in ['Higher-Low','Volatility','Flow','Momentum']]
        self.assertEqual(out['Technical Bottom Score'],round(sum(evidence)/4,1))
        self.assertTrue(np.isnan(out['Bottom Fundamental Evidence']))
        self.assertIn('Higher Low Observed',out)

    def test_cluster_price_and_date_use_same_earliest_pivot(self):
        g=self.frame();g.loc[[250,270,290],'Low']=[100.4,100.,100.2]
        support,_=levels(g,110,True)
        self.assertEqual(support['date'],str(g.Date.iloc[250].date()))
        self.assertEqual(support['value'],100.4)
        self.assertEqual(len(support['test_dates']),2)

    def test_noisy_touch_boundary_does_not_create_two_tests(self):
        g=self.frame(5);g.Low=[100,101.01,100,101.01,100];g.Close=[101,101.02,101,101.02,101]
        self.assertEqual(len(defended_tests(g,100,True)),1)

    def test_departure_bar_is_not_simultaneously_new_test(self):
        g=self.frame(4);g.Low=[100,101.5,100,100];g.Close=[101,101.5,103,101]
        dates=defended_tests(g,100,True)
        self.assertEqual(dates,[str(g.Date.iloc[0].date()),str(g.Date.iloc[3].date())])

    def test_missing_bottom_input_does_not_become_risk_evidence(self):
        g=self.frame();g.High=200;g.Volume=np.nan
        context={'Revenue Growth':.1,'EPS Growth':.1,'Operating Margin':.2,'Market Cap':1e9,
                 'Free Cash Flow':1e8,'Net Debt / EBITDA':1,'EPS Revision 90D':.1,
                 'Forward PE':20,'Peer Forward PE':20}
        out=calculate(g,110,'2026-10-05',context=context)
        self.assertGreaterEqual(out['Research Coverage %'],50)
        self.assertTrue(np.isnan(out['Bottom Confidence']))
        self.assertEqual(out['Research Bottom Status'],'Insufficient evidence')
        self.assertNotIn(out['Overall Signal/Action'],['Strong Buy Zone','Buy/Accumulate'])

    def test_short_history_is_unavailable_not_negative_bottom_evidence(self):
        g=self.frame(5);out=calculate(g,110,'2026-10-05')
        self.assertTrue(np.isnan(out['Bottom Higher-Low Evidence']))
        self.assertTrue(np.isnan(out['Bottom Volatility Evidence']))
        self.assertTrue(np.isnan(out['Bottom Momentum Evidence']))
        self.assertTrue(np.isnan(out['Technical Bottom Score']))
        self.assertLess(out['Technical Bottom Input Coverage %'],100)

if __name__=='__main__':unittest.main()
