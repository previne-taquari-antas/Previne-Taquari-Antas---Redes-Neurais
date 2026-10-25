#!/usr/bin/env python3
"""Test native channel propagation with unmodified source and raw target clock.

Local floodplain geometry is frozen and added to the final chosen native case.
No event-observed target is inserted as a hydraulic/hydrological inflow.
"""
import concurrent.futures as cf,copy,json,sys
from pathlib import Path
import calibrate_event_members_v2 as v
import build_mucum_floodplain_storage as geo
from test_mucum_terrain_storage_native import raw_clock_context

def main():
    hec=sys.argv[1];v.OUT=geo.OUT/'rawclock_channel_search';ctx=raw_clock_context(v.prepare())
    s=v.load(v.BASE/'event_members_v3_20261024/selection_manifest.json');seed=dict(s['selected'][0]['parameters']);seed={k:x for k,x in seed.items() if not k.startswith('overbank_')}
    path=v.OUT/'evaluations.json';rows=v.load(path) if path.exists() else []
    def rank(r):
        m=r['metrics']['86510000'];peak_t=v.hms.utc(r['scores']['86510000']['full_simulated_peak_time_utc']);timing=(peak_t-v.hms.utc('2023-11-19T02:45:00Z')).total_seconds()/3600
        return .7*(1-m['full_Q_nse'])+.6*m['paired_Q_nmae']+.4*m['rising_limb_nmae']+1.5*abs(m['full_peak_error_vs_recorded_telemetry_pct'])/100+.025*abs(timing)+.5*abs(m['paired_bias_pct'])/100
    def run(p):
        r=v.execute(hec,p,*ctx);r['rawclock_objective']=rank(r);return r
    def batch(jobs):
        seen={json.dumps(r['parameters'],sort_keys=True) for r in rows};jobs=[p for p in jobs if json.dumps(p,sort_keys=True) not in seen]
        with cf.ThreadPoolExecutor(max_workers=2) as pool:
            for r in pool.map(run,jobs):
                rows.append(r);v.save(path,rows);print(json.dumps(dict(n=len(rows),objective=r['rawclock_objective'],metrics=r['metrics']['86510000'])),flush=True)
    jobs=[seed]
    for k in [2.,3.,4.,5.,6.,7.]:
        for n in [1,2]:jobs.append(dict(seed,k_g1=k,x=0.,routing_subreach_target=n))
    batch(jobs)
    best=min(rows,key=rank);p=best['parameters'];jobs=[]
    for k,step,lo,hi in [('k_g1',.5,1,8),('cn',2,20.01,45),('lag_min',60,30,550),('baseflow_specific',.03,.03,.3),('baseflow_recession',.03,.8,.998)]:
        for sign in [-1,1]:
            q=dict(p);q[k]=max(lo,min(hi,p[k]+step*sign));jobs.append(q)
    batch(jobs);best=min(rows,key=rank)
    v.save(geo.OUT/'rawclock_selected_channel_parameters.json',best['parameters'])
    v.save(geo.OUT/'rawclock_channel_selection.json',dict(selected=best,target_code='86510000',event=v.EVENT,clock_offset_minutes=0,
        original_Q_source_unchanged=True,peak_reference_UTC='2023-11-19T02:45:00Z',
        selection='Event-only native Muskingum/recession/loss calibration. Geometry is frozen and will be routed in the final case. No 95.6 Mm3 source-retention device.',
        number_successful_evaluations=len(rows)))
    print('RAW_CLOCK_CHANNEL_SELECTED',json.dumps(best['metrics']['86510000']),flush=True)

if __name__=='__main__':main()
