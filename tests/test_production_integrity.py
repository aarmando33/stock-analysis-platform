import io
import json
from pathlib import Path
import tempfile
import os
import unittest
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
from zipfile import ZipFile
from openpyxl import Workbook
from production_integrity import (SUMMER_CRON,WINTER_CRON,scheduled_window,ready_matches,
                                  prior_ready,validate_output,digest)
from production_integrity import main,window_plan,wait_for_close,verify_generation

class ProductionIntegrity(unittest.TestCase):
    def record(self,run=7,session='2026-10-12'):
        return {'schema_version':1,'ready':True,'session':session,'head_sha':'head','run_id':str(run),
                'tickers':['TEST'],'verified_hashes':14,'counts':{'Expected':1,'Usable':1},
                'deliverable_sha256':{'report.xlsx':'a'*64,'dashboard.html':'b'*64}}

    def test_dst_windows_and_manual_recovery(self):
        summer=datetime(2026,10,12,20,17,tzinfo=timezone.utc)
        winter=datetime(2026,12,1,21,17,tzinfo=timezone.utc)
        self.assertTrue(scheduled_window('schedule',SUMMER_CRON,summer))
        self.assertTrue(scheduled_window('schedule',WINTER_CRON,summer))
        self.assertTrue(scheduled_window('schedule',WINTER_CRON,winter))
        self.assertTrue(scheduled_window('schedule',SUMMER_CRON,winter))
        self.assertTrue(scheduled_window('workflow_dispatch','',summer))
        self.assertFalse(scheduled_window('schedule',SUMMER_CRON,summer.replace(hour=16)))
        self.assertTrue(scheduled_window('schedule',SUMMER_CRON,summer.replace(hour=20,minute=4)))
        self.assertFalse(scheduled_window('schedule',WINTER_CRON,winter.replace(hour=17)))
        self.assertFalse(scheduled_window('schedule',SUMMER_CRON,summer.replace(day=10)))
        # A delayed scheduled attempt remains valid, even after the delivery hour.
        self.assertTrue(scheduled_window('schedule',SUMMER_CRON,summer.replace(hour=23)))

    def test_early_runner_waits_for_close_instead_of_discarding_wakeup(self):
        now=datetime(2026,10,16,18,33,tzinfo=timezone.utc)
        plan=window_plan('schedule',now)
        self.assertTrue(plan['run']);self.assertEqual(plan['session'],'2026-10-16')
        self.assertEqual(plan['wait_seconds'],97*60)
        current=[now];sleeps=[]
        def sleep(seconds):
            sleeps.append(seconds);current[0]+=timedelta(seconds=seconds)
        wait_for_close(plan,sleep=sleep,clock=lambda:current[0])
        self.assertEqual(current[0],datetime(2026,10,16,20,10,tzinfo=timezone.utc))
        self.assertLessEqual(max(sleeps),60)

    def test_exchange_holiday_early_close_dst_and_late_recovery(self):
        self.assertFalse(window_plan('schedule',datetime(2026,12,25,21,tzinfo=timezone.utc))['run'])
        # Thanksgiving Friday closes at noon Chicago; no normal-close wait.
        early=window_plan('schedule',datetime(2026,11,27,19,7,tzinfo=timezone.utc))
        self.assertTrue(early['run']);self.assertEqual(early['wait_seconds'],0)
        winter=window_plan('schedule',datetime(2026,12,1,19,7,tzinfo=timezone.utc))
        self.assertEqual(winter['wait_seconds'],123*60)
        # Friday's last retry is already Saturday in UTC.
        late=window_plan('schedule',datetime(2026,10,17,2,47,tzinfo=timezone.utc))
        self.assertEqual(late['session'],'2026-10-16');self.assertTrue(late['run'])
        with self.assertRaisesRegex(ValueError,'Timezone-aware'):
            window_plan('schedule',datetime(2026,10,16,20))

    def test_postclose_noop_is_not_reported_as_healthy_without_a_report(self):
        class API:
            def get(self,path,binary=False):return {'artifacts':[]} if '/artifacts?' in path else {'workflow_runs':[]}
        plan={'run':True,'wait_seconds':0,'reason':'Completed exchange session'}
        with self.assertRaisesRegex(ValueError,'no report'):
            verify_generation(API(),9,'head','2026-10-16',['TEST'],plan)
        pre={**plan,'run':False,'reason':'XNYS holiday'}
        self.assertEqual(verify_generation(API(),9,'head','2026-10-16',['TEST'],pre)['state'],'NOT_DUE')

    def test_another_good_run_cannot_hide_a_broken_producing_run(self):
        owner=self
        class API:
            def get(self,path,binary=False):
                if '/artifacts?' in path:return {'artifacts':[
                    {'id':1,'name':'stock-price-feed','expired':False,'size_in_bytes':100},
                    {'id':2,'name':'stock-monitor-ready','expired':False}]}
                return owner.zip(owner.record(run=7))
        plan={'run':True,'wait_seconds':0,'reason':'Completed exchange session'}
        with self.assertRaisesRegex(ValueError,'This producing run'):
            verify_generation(API(),9,'head','2026-10-12',['TEST'],plan)
        self.assertEqual(verify_generation(API(),7,'head','2026-10-12',['TEST'],plan)['state'],'READY')

    def test_stale_wrong_release_duplicate_and_empty_records_do_not_skip_refresh(self):
        record=self.record()
        self.assertTrue(ready_matches(record,'2026-10-12','head',7,['TEST']))
        changes=[{'session':'2026-10-09'},{'head_sha':'other'},{'run_id':'6'},
                 {'tickers':['TEST','TEST']},{'ready':False},{'counts':{'Expected':1,'Usable':0}},
                 {'counts':{'Expected':2,'Usable':1}},{'verified_hashes':0},
                 {'deliverable_sha256':{'report.xlsx':'not-a-hash','dashboard.html':'b'*64}}]
        for change in changes:
            with self.subTest(change=change):self.assertFalse(ready_matches({**record,**change},'2026-10-12','head',7,['TEST']))
        partial={**record,'retry_needed':True}
        self.assertFalse(ready_matches(partial,'2026-10-12','head',7,['TEST']))
        self.assertTrue(ready_matches(partial,'2026-10-12','head',7,['TEST'],allow_partial=True))

    def zip(self,record):
        payload=io.BytesIO()
        with ZipFile(payload,'w') as archive:archive.writestr('ready.json',json.dumps(record))
        return payload.getvalue()

    def test_noop_runs_are_skipped_and_latest_stale_marker_does_not_hide_fresh_marker(self):
        owner=self
        class API:
            def get(self,path,binary=False):
                if '/runs?' in path:return {'workflow_runs':[
                    {'id':9,'head_sha':'head','head_branch':'main','conclusion':'success'},
                    {'id':7,'head_sha':'head','head_branch':'main','conclusion':'success'}]}
                if 'runs/9/' in path:return {'artifacts':[]}
                if 'runs/7/' in path:return {'artifacts':[
                    {'id':1,'name':'stock-price-feed','expired':False,'size_in_bytes':100},
                    {'id':2,'name':'stock-monitor-ready','expired':False},
                    {'id':3,'name':'stock-monitor-ready','expired':False}]}
                return owner.zip(owner.record(session='2026-10-09') if '/3/' in path else owner.record())
        self.assertEqual(prior_ready(API(),'2026-10-12','head',['TEST'])['run_id'],'7')

    def fixture(self,root,folder):
        (root/'tickers.csv').write_text('Symbol\nTEST\n')
        audit={'expected_market_date':'2026-10-12','latest_market_date':'2026-10-12','expected_tickers':1}
        (folder/'price_audit.json').write_text(json.dumps(audit))
        for name in ['prices_latest.csv','price_history.csv.gz','profiles.json','symbol_aliases.csv']:
            (folder/name).write_bytes(b'input')
        code=['buy_sell_monitor.py','export_monitor.py','historical_zones.py','zone_monitor.py',
              'compact_monitor.py','ticker_dashboard.py','profile_feed.py','profile_enrichment.py']
        for name in code:(root/name).write_bytes(b'code')
        report={'session':'2026-10-12','historical':False,'counts':{'Expected':1,'Usable':1},
                'calculations':[{'Ticker':'TEST','Price':100,'Price Date':'2026-10-12','price_status':'OK'}],
                'source_sha256':{n:digest(folder/n) for n in ['price_audit.json','prices_latest.csv','price_history.csv.gz']},
                'input_sha256':{'universe':digest(root/'tickers.csv'),**{n:digest(folder/n) for n in ['profiles.json','symbol_aliases.csv']}},
                'code_sha256':{n:digest(root/n) for n in code}}
        (folder/'monitor_results.json').write_text(json.dumps(report))
        w=Workbook();w.remove(w.active)
        for name in ['Master','Zone Details']:
            s=w.create_sheet(name);s.append(['Ticker','Price']);s.append(['TEST',100])
        w.save(folder/'Stock_Buy_Sell_Monitor.xlsx')
        data={'cutoff':'2026-10-12','tickers':[{'ticker':'TEST','price':100,'history':[]}]}
        (folder/'Stock_Buy_Sell_Ticker_Dashboard.html').write_text('<script id="dashboard-data" type="application/json">'+json.dumps(data)+'</script>')
        for stem,ext in [('Stock_Buy_Sell_Monitor','xlsx'),('Stock_Buy_Sell_Ticker_Dashboard','html')]:
            (folder/f'{stem}_2026-10-12.{ext}').write_bytes((folder/f'{stem}.{ext}').read_bytes())

    def test_ready_requires_fresh_dates_exact_inputs_and_both_deliverables(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'source';folder=Path(directory)/'outputs';root.mkdir();folder.mkdir()
            self.fixture(root,folder)
            record=validate_output(folder,root,'2026-10-12',['TEST'])
            self.assertTrue(record['ready']);self.assertEqual(record['verified_hashes'],14)
            with self.assertRaisesRegex(ValueError,'dates'):
                validate_output(folder,root,'2026-10-13',['TEST'])
            (folder/'price_history.csv.gz').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'Integrity mismatch'):
                validate_output(folder,root,'2026-10-12',['TEST'])
            self.fixture(root,folder)
            (folder/'Stock_Buy_Sell_Monitor_2026-10-12.xlsx').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'deliverable'):
                validate_output(folder,root,'2026-10-12',['TEST'])

    def test_readiness_lookup_error_falls_back_to_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'github-output'
            env={'GITHUB_OUTPUT':str(target),'GITHUB_EVENT_NAME':'schedule',
                 'GITHUB_REPOSITORY':'owner/repo','GITHUB_SHA':'head','GH_TOKEN':'test-placeholder'}
            with patch.dict(os.environ,env),patch('sys.argv',['production_integrity.py','probe']),\
                 patch('buy_sell_monitor.latest_session',return_value='2026-10-12'),\
                 patch('production_integrity.expected_symbols',return_value=['TEST']),\
                 patch('production_integrity.prior_ready',side_effect=OSError('Lookup failed')):
                main()
            self.assertIn('refresh=true',target.read_text())

    def test_future_chart_and_wrong_current_price_cannot_be_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'source';folder=Path(directory)/'outputs';root.mkdir();folder.mkdir()
            self.fixture(root,folder)
            r=json.loads((folder/'monitor_results.json').read_text());r['calculations'][0]['Price Date']='2026-10-09'
            (folder/'monitor_results.json').write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'current valid price'):
                validate_output(folder,root,'2026-10-12',['TEST'])
            self.fixture(root,folder)
            data={'cutoff':'2026-10-12','tickers':[{'ticker':'TEST','price':100,'history':[['2026-10-13',100]]}]}
            text='<script id="dashboard-data" type="application/json">'+json.dumps(data)+'</script>'
            for name in ['Stock_Buy_Sell_Ticker_Dashboard.html','Stock_Buy_Sell_Ticker_Dashboard_2026-10-12.html']:
                (folder/name).write_text(text)
            with self.assertRaisesRegex(ValueError,'Future dashboard'):
                validate_output(folder,root,'2026-10-12',['TEST'])

if __name__=='__main__':unittest.main()

