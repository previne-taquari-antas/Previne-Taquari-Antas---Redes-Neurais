#!/usr/bin/env python3
"""Event-only native search: unchanged JJ, raw clock, bounded timing tradeoff.

Search never scales source discharge or the terrain-derived storage curve.
The additional geometry is routed and independently checked after selection.
"""
import concurrent.futures as cf
import json,sys
import calibrate_event_members_v2 as v
import build_mucum_floodplain_storage as geo
from test_mucum_terrain_storage_native import raw_clock_context

def main():
    hec=sys.argv[1];v.OUT=geo.OUT/'peak_timing_search';ctx=raw_clock_context(v.prepare())
    seed=v.load(geo.OUT/'rawclock_selected_channel_parameters.json')
    path=v.OUT/'evaluations.json';rows=v.load(path) if path.exists() else []
    def timing(r):
        return (v.hms.utc(r['scores']['86510000']['full_simulated_peak_time_utc'])-v.hms.utc('2023-11-19T02:45:00Z')).total_seconds()/3600
    def eligible(r):
        m=r['metrics']['86510000']
        return abs(timing(r))<=1 and m['full_Q_nse']>=.98 and m['strict_domain_nse']>=.95 and abs(m['paired_bias_pct'])<=3
    def objective(r):
        m=r['metrics']['86510000']
        return abs(m['full_peak_error_vs_recorded_telemetry_pct'])+.5*abs(timing(r))
    def batch(jobs):
        seen={json.dumps(r['parameters'],sort_keys=True) for r in rows}
        jobs=[p for p in jobs if json.dumps(p,sort_keys=True) not in seen]
        def run(p):
            r=v.execute(hec,p,*ctx);r['peak_time_minus_SGB_h']=timing(r);return r
        with cf.ThreadPoolExecutor(max_workers=2) as pool:
            for r in pool.map(run,jobs):
                rows.append(r);v.save(path,rows)
    if "--final-grid-only" not in sys.argv:
        batch([seed]+[dict(seed,k_g1=k,baseflow_specific=b) for k in [5.5,6.,6.5,7.] for b in [.07,.11,.15,.19]])
        best=min(filter(eligible,rows),key=objective);p=best['parameters']
        batch([dict(p,k_g1=k,baseflow_specific=b) for k in [p['k_g1']-.25,p['k_g1'],p['k_g1']+.25] for b in [p['baseflow_specific']-.02,p['baseflow_specific']+.02]])
        best=min(filter(eligible,rows),key=objective);p=best['parameters']
        batch([dict(p,**{key:value}) for key,values in {
            'cn':[20.01,25.,30.], 'lag_min':[120.,420.,550.],
            'baseflow_recession':[.85,.99], 'baseflow_threshold_ratio':[.1,.4]}.items() for value in values])
        # Recession and initial specific baseflow must also be tested jointly:
        # their effects on the early hydrograph and crest oppose one another.
        batch([dict(seed,k_g1=k,baseflow_specific=b,baseflow_recession=rec)
            for k in [5.75,6.] for b in [.15,.17,.19] for rec in [.85,.9]])
    # Fine native grid near the active strict-domain and timing constraints.
    batch([dict(seed,k_g1=k,cn=cn,baseflow_specific=bf,baseflow_recession=rec)
        for k in [6.,6.125] for cn in [21.462933265466535,25.]
        for bf,rec in [(.155,.9410459041489682),(.18,.9),(.19,.9)]])
    best=min(filter(eligible,rows),key=objective)
    v.save(geo.OUT/'peak_timing_selected_parameters.json',best['parameters'])
    v.save(geo.OUT/'peak_timing_selection.json',dict(selected=best,evaluations=len(rows),
        constraints=dict(max_abs_peak_time_h=1,min_NSE=.98,min_strict_NSE=.95,max_abs_bias_pct=3),
        objective='Absolute peak error in percent + 0.5 times absolute hours from SGB published crest; select on same raw-clock observations.',
        event=v.EVENT,target='86510000',clock_shift_minutes=0,upstream_Q_unchanged=True,
        geometry_fixed=True,independent_event_validation=False))
    print(json.dumps(dict(evaluations=len(rows),parameters=best['parameters'],metrics=best['metrics']['86510000'],timing_h=timing(best))))

if __name__=='__main__':main()
