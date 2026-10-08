import unittest
from compact_monitor import level_candidate, prepare, BASE
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
    def test_support_resistance_are_complete_and_summary_lists_stay_short(self):
        rows=[self.row(str(i)) for i in range(25)]
        for row in rows:
            row.update({key:value for key,value in self.row(row['Ticker'],'Resistance').items()
                        if 'Resistance' in key})
            row.update({'S1 Min':99,'S1 Max':99,'R1 Min':101,'R1 Max':101})
        report={'views':{'Master':rows,'Scanner':rows,'Top Opportunities':rows},'calculations':rows,'positions':[],
                'counts':{},'source_sha256':{},'code_sha256':{}}
        views={name:(rs,hs) for name,rs,hs in prepare(report)}
        self.assertEqual(len(views['At-Approach Support'][0]),25)
        self.assertEqual(len(views['At-Approach Resistance'][0]),25)
        self.assertEqual(len(views['Top Opportunities'][0]),10)
        self.assertEqual(len(views['Scanner'][0]),15)
        for _,headers in views.values():self.assertEqual(headers[:len(BASE)],BASE)
        self.assertIn('S1 Status',views['At-Approach Support'][1])
        self.assertIn('R1 Status',views['At-Approach Resistance'][1])
        self.assertIn('Breakout Level',views['Breakouts'][1])
        self.assertIn('Breakdown Level',views['Breakdowns'][1])
        self.assertIn('Current Value',views['Owned Positions'][1])
        for field in ['Qty','Cost Basis','3M %','6M %','YTD %','S1 Min','S1 Max','S2 Min','S2 Max','R1 Min','R1 Max','R2 Min','R2 Max',
                      'Bottom Min','Bottom Max','Win6mo%','price_suggest_80']:
            self.assertIn(field,BASE)
        w=build(report,compact=True)
        self.assertEqual(len(w.sheetnames),13)
        self.assertEqual(w['Master'].max_row,26)
        self.assertEqual(w['Calculations'].max_row,26)
        self.assertEqual(w['At-Approach Support'].max_row,26)
        self.assertEqual(w['At-Approach Resistance'].max_row,26)
        self.assertIn('Bottom Min',[c.value for c in w['Master'][1]])
        self.assertIn('Bottom Status',[c.value for c in w['Master'][1]])
        self.assertIn('Short Support Tests',[c.value for c in w['Calculations'][1]])
    def test_no_filler_when_no_candidate_qualifies(self):
        r={**self.row(),'Short Support Tests':1}
        v={n:rs for n,rs,_ in prepare({'calculations':[r],'views':{}})}
        self.assertEqual(v['At-Approach Support'],[])

if __name__=='__main__':unittest.main()
