import unittest
from compact_monitor import level_candidate, prepare
from export_monitor import build

class CompactMonitor(unittest.TestCase):
    def row(self,ticker='TEST',side='Support'):
        return {'Ticker':ticker,'Price':100,'price_status':'OK','Price Date':'2026-10-05',
                'Drawdown From High %':-20,'Technical Bottom Score':50,
                'Short '+side:99 if side=='Support' else 101,'Distance to '+side+' %':1,
                'Short '+side+' Tests':2,'Short '+side+' Source':'21-session swing '+('low' if side=='Support' else 'high'),
                'Short '+side+' Date':'2026-09-25','Breakdown Status':'None','Breakout Status':'None'}
    def test_screen_rejects_weak_dynamic_and_wrong_side_levels(self):
        base=self.row()
        self.assertTrue(level_candidate(base,'Support'))
        for change in [{'Short Support Tests':1},{'Short Support Source':'20-session MA'},
                       {'Short Support Source':'21-session swing high'},
                       {'Distance to Support %':5},{'Short Support':101},
                       {'Short Support Date':'2026-10-05'},{'price_status':'STALE_PRICE'}]:
            self.assertFalse(level_candidate({**base,**change},'Support'))
        self.assertTrue(level_candidate(self.row(side='Resistance'),'Resistance'))
    def test_lists_are_short_and_calculations_remain_complete(self):
        rows=[self.row(str(i)) for i in range(25)]
        report={'views':{'Master':rows,'Scanner':rows,'Top Opportunities':rows},'calculations':rows,'positions':[],
                'counts':{},'source_sha256':{},'code_sha256':{}}
        views={name:(rs,hs) for name,rs,hs in prepare(report)}
        self.assertEqual(len(views['At-Approach Support'][0]),10)
        self.assertEqual(len(views['Top Opportunities'][0]),10)
        self.assertEqual(len(views['Scanner'][0]),15)
        w=build(report,compact=True)
        self.assertEqual(len(w.sheetnames),12)
        self.assertEqual(w['Master'].max_row,26)
        self.assertEqual(w['Calculations'].max_row,26)
        self.assertIn('Technical Bottom Score',[c.value for c in w['Master'][1]])
        self.assertIn('Bottom Status',[c.value for c in w['Master'][1]])
        self.assertIn('Short Support Tests',[c.value for c in w['Calculations'][1]])
    def test_no_filler_when_no_candidate_qualifies(self):
        r={**self.row(),'Short Support Tests':1}
        v={n:rs for n,rs,_ in prepare({'calculations':[r],'views':{}})}
        self.assertEqual(v['At-Approach Support'],[])

if __name__=='__main__':unittest.main()
