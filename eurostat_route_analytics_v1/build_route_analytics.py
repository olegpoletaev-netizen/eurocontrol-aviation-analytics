"""Build Eurostat Route Analytics v1 from local exported Colab ZIP. No network, no DB writes."""
import argparse
import json
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd

REQ = ['eurostat_paexcc_panel.csv','eurostat_paexcc_requests.csv','eurostat_paexcc_report.json']


def build(src: Path, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        if any(s not in z.namelist() for s in REQ):
            raise ValueError('Input ZIP lacks required source files')
        panel = pd.read_csv(z.open(REQ[0]), dtype={'geo':str,'partner':str,'time':str,'cell_state':str})
        requests = pd.read_csv(z.open(REQ[1]))
        source_report = json.load(z.open(REQ[2]))
    assert (panel[['dataset','unit','tra_meas','schedule','freq']].nunique() == 1).all(), 'Mixed dimensions'
    assert panel.iloc[0]['dataset']=='avia_paexcc' and panel.iloc[0]['unit']=='FLIGHT' and panel.iloc[0]['tra_meas']=='CAF_PAS' and panel.iloc[0]['schedule']=='TOTAL' and panel.iloc[0]['freq']=='M'
    key = ['geo','partner','time']
    assert not panel.duplicated(key).any(), 'Duplicate pair/month keys'
    assert panel['cell_state'].isin(['REPORTED_VALUE','REPORTED_ZERO','NOT_RETURNED']).all()
    bad_value = panel.cell_state.eq('NOT_RETURNED') & panel.value.notna()
    bad_missing = panel.cell_state.ne('NOT_RETURNED') & panel.value.isna()
    assert not bad_value.any() and not bad_missing.any(), 'Cell-state/value mismatch'
    assert (panel.loc[panel.cell_state.eq('REPORTED_ZERO'),'value']==0).all()
    assert (panel.loc[panel.cell_state.eq('REPORTED_VALUE'),'value']>0).all()
    assert len(requests)==len(panel[['geo','partner']].drop_duplicates())
    assert requests.http.eq(200).all(), 'HTTP errors in input audit'
    assert not ((panel.value.dropna()%1)!=0).any(), 'Noninteger flight count'
    panel['year'] = panel.time.str[:4].astype(int)
    panel['month_num'] = panel.time.str[5:7].astype(int)
    panel['observed'] = panel.value.notna()
    panel['is_zero'] = panel.cell_state.eq('REPORTED_ZERO')
    panel.to_csv(dest/'route_monthly_panel.csv',index=False)

    # Pair-level year-over-year comparisons with explicit denominator states
    left = panel.loc[panel.year.eq(2026),['geo','partner','time','month_num','value','cell_state']].rename(columns={'time':'month_2026','value':'flights_2026','cell_state':'state_2026'})
    right = panel.loc[panel.year.eq(2025),['geo','partner','month_num','value','cell_state']].rename(columns={'value':'flights_2025','cell_state':'state_2025'})
    yoy=left.merge(right,on=['geo','partner','month_num'],how='left',validate='one_to_one')
    yoy['month_2025']='2025-'+yoy.month_num.astype(str).str.zfill(2)
    yoy['comparable']=yoy.flights_2026.notna() & yoy.flights_2025.notna()
    yoy['difference']=np.where(yoy.comparable,yoy.flights_2026-yoy.flights_2025,np.nan)
    yoy['yoy_pct']=np.where(yoy.comparable & yoy.flights_2025.gt(0),100*yoy.difference/yoy.flights_2025.replace(0,np.nan),np.nan)
    yoy['pct_state']=np.select([~yoy.comparable,yoy.flights_2025.eq(0)],['MISSING','BASE_ZERO'],default='VALID')
    yoy.to_csv(dest/'route_pair_yoy.csv',index=False)

    # Coverage over complete 496 pair grid for each month.
    coverage=panel.groupby('time',sort=True).agg(pairs_total=('observed','size'),pairs_reported=('observed','sum'),reported_zeros=('is_zero','sum'),observed_sum_selected_pairs=('value','sum')).reset_index()
    coverage['pairs_not_returned']=coverage.pairs_total-coverage.pairs_reported
    coverage['coverage_pct']=100*coverage.pairs_reported/coverage.pairs_total
    coverage.to_csv(dest/'route_coverage_monthly.csv',index=False)

    # Matched-pair aggregates recomputed per month & partner: NEVER compare unmatched aggregate totals.
    matched=yoy[yoy.comparable].copy()
    def aggregate(bycols):
        g=matched.groupby(bycols,dropna=False).agg(matched_pairs=('geo','size'),flights_2025=('flights_2025','sum'),flights_2026=('flights_2026','sum')).reset_index()
        g['difference']=g.flights_2026-g.flights_2025
        g['yoy_pct']=np.where(g.flights_2025.gt(0),100*g.difference/g.flights_2025,np.nan)
        g['pct_state']=np.where(g.flights_2025.gt(0),'VALID','BASE_ZERO')
        return g
    partner=aggregate(['month_2026','partner'])
    country=aggregate(['month_2026','geo'])
    partner.to_csv(dest/'route_partner_yoy.csv',index=False)
    country.to_csv(dest/'route_reporting_country_yoy.csv',index=False)
    
    # Pair exposure: selected partners / selected partners, not share of all airline routes.
    # Use pre-event calendar 2025; only reported months are aggregated, include completeness.
    pre=panel[panel.year.eq(2025)].groupby(['geo','partner']).agg(months_reported=('observed','sum'),flights_2025_reported=('value','sum')).reset_index()
    pre['months_expected']=12
    pre['coverage_complete']=pre.months_reported.eq(12)
    pre['note']='Selected 16 destinations only; NOT a share of all airport or country departures'
    pre.to_csv(dest/'route_baseline_2025.csv',index=False)

    missing = int(panel.value.isna().sum())
    report={
      'status':'OK_VALIDATED', 'source_dataset':'avia_paexcc','period':source_report['period'],
      'indicator':{'freq':'M','schedule':'TOTAL','unit':'FLIGHT','tra_meas':'CAF_PAS'},
      'pair_count':int(panel[['geo','partner']].drop_duplicates().shape[0]),
      'grid_cells':len(panel),'numeric_cells':int(panel.value.notna().sum()),
      'reported_zeros':int(panel.cell_state.eq('REPORTED_ZERO').sum()),
      'not_returned_cells':missing,'http_200_requests':int(requests.http.eq(200).sum()),
      'matched_pair_months':int(yoy.comparable.sum()),
      '2026_monthly_coverage':coverage.loc[coverage.time.str.startswith('2026'),['time','coverage_pct']].to_dict('records'),
      'constraints':['Country-to-partner monthly commercial passenger flights, not airport routes',
                     'Do not conflate 2026 missing publication with zeros',
                     'Every YoY aggregate uses same matched pairs in both years',
                     'The 2025 baseline sums 16 selected partners only, not all routes',
                     'March 2026 differs from the event study daily 28-day window',
                     'Flight counts alone do not establish rerouting or causal effects'],
      'database_modified':False,'external_http_requests':0,
      'outputs':['route_monthly_panel.csv','route_pair_yoy.csv','route_coverage_monthly.csv','route_partner_yoy.csv','route_reporting_country_yoy.csv','route_baseline_2025.csv']
    }
    (dest/'route_analytics_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['status','pair_count','numeric_cells','reported_zeros','not_returned_cells','matched_pair_months']},indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',type=Path,default=Path('eurostat_paexcc_bulk_results.zip'))
    ap.add_argument('--output',type=Path,default=Path('data'))
    args=ap.parse_args();build(args.input,args.output)
