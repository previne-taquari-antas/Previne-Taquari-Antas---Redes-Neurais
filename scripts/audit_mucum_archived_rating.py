#!/usr/bin/env python3
"""Compare archived hourly ANA Q/H pairs with the dated archived rating.

This audit does not replace observations, infer an official replacement curve,
or treat a fit to Q/H as independent hydraulic calibration.
"""
import csv,json,hashlib
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
import build_mucum_floodplain_storage as geo
from test_mucum_terrain_storage_native import rating

def main():
    hydro=geo.ROOT/'assets/data/hec_hms_g040_full_basin/historical_calibration_forcing/E24_NOV2023/hydro.json'
    data=json.loads(hydro.read_text());control=next(c for c in data['controls'] if str(c['code'])=='86510000')
    pairs=[]
    for r in control['recent_rows']:
        h=r.get('level_source_unit');q=r.get('flow_m3s')
        if h is None or q is None or h<700 or q<=0:continue
        h=h/100.;pred=rating(h)
        pairs.append(dict(time_utc=r['time_utc'],archived_hourly_stage_m=h,archived_hourly_flow_m3s=q,
            dated_rating_at_hourly_mean_stage_m3s=pred,relative_difference_pct=100*(pred/q-1)))
    h=np.array([r['archived_hourly_stage_m'] for r in pairs]);q=np.array([r['archived_hourly_flow_m3s'] for r in pairs])
    fit=least_squares(lambda p:np.log(p[0]*(h-p[1])**p[2])-np.log(q),[150.,.5,1.4],bounds=([1,-10,.5],[1000,6,3]))
    a,h0,n=map(float,fit.x);pred=a*(h-h0)**n;peak=max(pairs,key=lambda r:r['archived_hourly_stage_m'])
    report=dict(event='E24_NOV2023',station='86510000',source_file=str(hydro.relative_to(geo.ROOT)),source_sha256=hashlib.sha256(hydro.read_bytes()).hexdigest(),
        source_provenance='ANA/SGB DadosHidrometeorologicos, separate Vazao and Nivel XML fields, hourly arithmetic mean. See build_g040_historical_hydro_events.py parse_xml/hourly. No rating is applied by that importer.',
        compared_pairs=len(pairs),minimum_stage_m=7.,peak_hourly_pair=peak,
        diagnostic_fit_only=dict(equation='A*(h-h0)^n, h in metres',A=a,h0_m=h0,n=n,relative_RMSE=float(np.sqrt(np.mean((pred/q-1)**2))),official_curve=False),
        dated_rating_relative_RMSE=float(np.sqrt(np.mean([(r['relative_difference_pct']/100)**2 for r in pairs]))),
        input_or_target_values_changed=False,
        limitations=['Hourly mean of a nonlinear rating differs from rating of hourly mean stage. Raw subhourly pairs were not retained in this archive, preventing exact aggregation-error attribution.',
            'The low residual empirical fit is a diagnostic, not an official replacement rating or an independent discharge measurement.',
            'Archived telemetry discharge and the separately archived dated ANA curve are not mutually consistent at the crest. Revision history and exact source curve require confirmation.',
            'Do not relabel dated-rating discharge as observed discharge or silently change the calibration target. Extreme-stage fit remains conditional on discharge provenance.'])
    geo.save(geo.OUT/'archived_rating_consistency_audit.json',report)
    with (geo.OUT/'archived_rating_comparison.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(pairs[0]));w.writeheader();w.writerows(pairs)
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
