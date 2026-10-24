#!/usr/bin/env python3
"""Seek a crest reduction while retaining the previous global/low-stage fit."""
import concurrent.futures as cf,json,sys
import calibrate_event_members_v2 as v
import build_mucum_floodplain_storage as geo
from test_mucum_terrain_storage_native import raw_clock_context

def main():
    v.OUT=geo.OUT/'peak_timing_search';ctx=raw_clock_context(v.prepare());hec=sys.argv[1]
    seed=v.load(geo.OUT/'rawclock_selected_channel_parameters.json');path=v.OUT/'evaluations.json';rows=v.load(path)
    seen={json.dumps(r['parameters'],sort_keys=True) for r in rows}
    jobs=[dict(seed,k_g1=k,baseflow_specific=b,baseflow_recession=rec) for k in [5.,5.125] for b in [.17,.19] for rec in [.85,.9]]
    def run(p):
        r=v.execute(hec,p,*ctx);r['peak_time_minus_SGB_h']=(v.hms.utc(r['scores']['86510000']['full_simulated_peak_time_utc'])-v.hms.utc('2023-11-19T02:45:00Z')).total_seconds()/3600;return r
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        for r in pool.map(run,[p for p in jobs if json.dumps(p,sort_keys=True) not in seen]):rows.append(r);v.save(path,rows)
    def eligible(r):
        m=r['metrics']['86510000'];return m['full_Q_nse']>=.986 and m['strict_domain_nse']>=.9675 and abs(r['peak_time_minus_SGB_h'])<=.25 and abs(m['full_peak_error_vs_recorded_telemetry_pct'])<10.029
    good=list(filter(eligible,rows));best=min(good,key=lambda r:abs(r['metrics']['86510000']['full_peak_error_vs_recorded_telemetry_pct'])) if good else None
    v.save(geo.OUT/'balanced_selection.json',dict(evaluations_total=len(rows),additional_cases=len(jobs),selected=best,
        constraints=dict(min_channel_NSE=.986,min_channel_strict_NSE=.9675,max_abs_peak_time_h=.25,max_abs_peak_error_pct=10.029),
        event=v.EVENT,target='86510000',clock_shift_minutes=0,upstream_Q_unchanged=True,geometry_fixed=True,
        interpretation='Candidate must still pass native geometry recompute; selection is event-specific calibration, not independent validation.'))
    if best:v.save(geo.OUT/'balanced_selected_parameters.json',best['parameters'])
    print(json.dumps(dict(evaluations=len(rows),selected=best),ensure_ascii=False))

if __name__=='__main__':main()
