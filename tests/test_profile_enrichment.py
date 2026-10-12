import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from compact_monitor import VOLUME_FIELDS, prepare
from export_monitor import build
from profile_enrichment import enrich
from profile_feed import bounded_profile, collect, sha, write_enriched
from ticker_dashboard import _prepare


class ProfileEnrichment(unittest.TestCase):
    def report(self):
        rows=[{'Ticker':ticker,'Price':100,'Overall Signal/Action':'Hold/Wait',
               'Action Reason':'Missing research','Evidence Coverage %':42,'Opportunity Score':51,
               **dict(zip(VOLUME_FIELDS,[1200,1000,1.2,15,'Normal',8500]))}
              for ticker in ['A','B']]
        return {'session':'2026-10-07','calculations':rows,'views':{'Master':copy.deepcopy(rows)},
                'zone_details':[{'Ticker':r['Ticker'],'Min':95} for r in rows],
                'ticker_dashboard_data':{'cutoff':'2026-10-07','tickers':[{'ticker':r['Ticker']} for r in rows]},
                'code_sha256':{'buy_sell_monitor.py':'original-calculator-hash'},
                'input_sha256':{'universe':'original-universe-hash'},'counts':{},'source_sha256':{}}

    def test_failure_preserves_universe_actions_and_calculations(self):
        report=self.report();original=copy.deepcopy(report)
        profiles={'A':{'Stock Name':'Company A','Market Cap':2e9,'Currency':'USD',
                       'Sector':'Technology','Subsector':'Software','Profile Retrieved UTC':'2026-10-08T01:00:00Z'},
                  'B':{'Profile Error':'Timeout'}}
        result=enrich(report,profiles)
        self.assertEqual(report,original)
        self.assertEqual(len(result['calculations']),2)
        for before,after in zip(report['calculations'],result['calculations']):
            for key,value in before.items():self.assertEqual(after[key],value)
        for rows in [result['calculations'],result['zone_details'],result['views']['Master']]:
            self.assertEqual(rows[0]['capMil'],2000)
            self.assertEqual(rows[1]['Sector'],'Unavailable')
            self.assertEqual(rows[1]['capMil'],'Unavailable')
        dashboard=_prepare(result['ticker_dashboard_data'])['tickers']
        self.assertEqual(dashboard[1]['action'],'Hold/Wait')
        self.assertEqual(dashboard[0]['volume']['OBV'],8500)
        self.assertEqual(dashboard[1]['sector'],'Unavailable')

    def test_currency_guard_and_non_equity_sector(self):
        result=enrich(self.report(),{'A':{'Market Cap':1e9,'Currency':'EUR'},'B':{'Quote Type':'ETF'}})
        self.assertEqual(result['calculations'][0]['capMil'],'Unavailable')
        self.assertEqual(result['calculations'][1]['Sector'],'Not applicable')

    def test_timeout_is_bounded_and_missing_metadata_does_not_remove_ticker(self):
        with patch('profile_feed.subprocess.run',side_effect=subprocess.TimeoutExpired('provider',20)) as run:
            profiles=collect(['A','B'],{'A':'ALIAS'})
        self.assertEqual(set(profiles),{'A','B'})
        self.assertIn('20 seconds',profiles['A']['Profile Error'])
        self.assertEqual(profiles['A']['Provider Symbol'],'ALIAS')
        self.assertTrue(profiles['B']['Profile Source'].startswith('https://finance.yahoo.com/'))
        self.assertTrue(profiles['B']['Profile Retrieved UTC'])
        self.assertEqual(run.call_args.kwargs['timeout'],20)

    def test_provenance_appends_without_replacing_calculator_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);aliases=root/'symbol_aliases.csv'
            aliases.write_text('Monitor Symbol,Provider Symbol\nA,A\n')
            profiles=root/'profiles.json';output=root/'monitor_results.json'
            result=write_enriched(self.report(),{},profiles,output,aliases)
            self.assertEqual(result['code_sha256']['buy_sell_monitor.py'],'original-calculator-hash')
            self.assertEqual(result['input_sha256']['universe'],'original-universe-hash')
            self.assertEqual(result['input_sha256']['profiles.json'],sha(profiles))
            self.assertIn('profile_enrichment.py',result['code_sha256'])
            self.assertEqual(json.loads(output.read_text()),result)

    def test_all_six_calculated_volume_fields_reach_reader_exports(self):
        report=enrich(self.report(),{})
        for _,_,headers in prepare(report):
            for key in VOLUME_FIELDS:self.assertIn(key,headers)
        workbook=build(report,compact=True)
        headers=[c.value for c in workbook['Master'][1]]
        for key,value in zip(VOLUME_FIELDS,[1200,1000,1.2,15,'Normal',8500]):
            self.assertEqual(workbook['Master'].cell(2,headers.index(key)+1).value,value)


if __name__=='__main__':unittest.main()
