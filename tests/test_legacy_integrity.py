import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'scripts'))
import stock_analysis_runtime_patch as runtime
from rankings_watchlist import generate_rankings_watchlists


class LegacyIntegrity(unittest.TestCase):
    def test_no_stale_fallback_into_ranked_views(self):
        data=pd.DataFrame({'Symbol':['TEST'],'price_status':['STALE_PRICE'],'Marketcap':[3e9],
                           'last_close':[100.],'RSI':[40.],'win%':[.9],'win%_covid':[.8]})
        views=runtime.scanner.make_ranked_views(data)
        for name,view in views.items():
            if name=='Full Master':self.assertEqual(len(view),1)
            else:self.assertEqual(len(view),0,name)

    def test_successful_download_of_old_prices_still_stale(self):
        data=pd.DataFrame({'Symbol':['TEST'],'price_status':['OK'],'Date':['2026-10-01'],
                           'min':[50.],'max':[150.],'minCovid_filled':[50.],'last_close':[100.]})
        with patch('buy_sell_monitor.latest_session',return_value='2026-10-02'):
            self.assertEqual(runtime.add_core_value_calculations(data).price_status.iloc[0],'STALE_PRICE')

    def test_prior_snapshot_excludes_latest_history_future(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            pd.DataFrame({'Symbol':['OLD'],'candidate':['Y'],'rank':[1]}).to_csv(path/'rankings_cap2b_2026-10-01.csv',index=False)
            for suffix in ['latest','history','2026-10-06']:
                pd.DataFrame({'Symbol':['WRONG'],'candidate':['Y'],'rank':[1]}).to_csv(path/f'rankings_cap2b_{suffix}.csv',index=False)
            current=pd.DataFrame({'Symbol':['NEW'],'composite_score':[90],'Marketcap':[3e9]})
            result=generate_rankings_watchlists(current,output_dir=path,run_date='2026-10-02')
            demotions=pd.read_csv(result['paths']['demotions_today'])
            self.assertEqual(demotions.Symbol.tolist(),['OLD'])


if __name__=='__main__':unittest.main()
