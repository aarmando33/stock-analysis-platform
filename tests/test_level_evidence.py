import unittest
import numpy as np
import pandas as pd
from buy_sell_monitor import calculate, levels

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

if __name__=='__main__':unittest.main()
