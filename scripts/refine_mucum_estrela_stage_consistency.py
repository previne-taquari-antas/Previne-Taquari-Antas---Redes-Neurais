#!/usr/bin/env python3
"""Reject unobserved Q pulses contradicted by observed low stage.

This does not manufacture a missing Q observation. If stage is below the
lowest observed stage/Q pair, monotonicity of the same rating relation gives
only an upper Q bound. The constraint supplements, never replaces, Q scores.
"""
import argparse,concurrent.futures as cf,csv,copy,json
from datetime import datetime,timezone
from pathlib import Path
import calibrate_mucum_estrela_event_library as cal
import run_hec_hms_g040_e1_hindcast as hms

def stage_bound(raw,code):
    c=next(c for c in raw['controls'] if str(c['code'])==code)
    paired=[(r['level_source_unit'],r['flow_m3s']) for r in c['recent_rows'] if r.get('flow_m3s') is not None and r.get('level_source_unit') is not None]
    low_h,low_q=min(paired)
    missing=[hms.utc(r['time_utc']) for r in c['recent_rows'] if r.get('flow_m3s') is None and r.get('level_source_unit') is not None and r['level_source_unit']<low_h]
    return dict(stage_ceiling_source_unit=low_h,Q_upper_bound_m3s=low_q,times_utc=[cal.iso(t) for t in missing],
      assumption='Monotonicity within the same observed stage/discharge relation; no missing Q is assigned')

def violations(row,bound):
    target='J_86879300';times=set(bound['times_utc']);vals=[]
    p=cal.ROOT/row['result_file']
    with (p.parent/'project/hec_output_values.csv').open() as fh:
        for r in csv.DictReader(fh):
            if r['element']!=target:continue
            t=hms.dss_time_to_utc(r['time_value'])
            if cal.iso(t) in times:vals.append(float(r['q_m3s']))
    q=bound['Q_upper_bound_m3s']
    if len(vals)!=len(times):raise RuntimeError('stage-constraint simulation pairs missing')
    excess=[max(0,v/q-1) for v in vals]
    return dict(pairs=len(vals),mean_positive_relative_exceedance=sum(excess)/len(excess),
       maximum_simulated_Q_at_low_observed_stage_m3s=max(vals),
       maximum_relative_exceedance=max(excess),pass_with_10pct_model_tolerance=max(excess)<=.10)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('hec');args=ap.parse_args()
    cfg=cal.load(cal.CONFIG);eid=cfg['event_id'];raw=cal.load(cal.BASE/'historical_calibration_forcing'/eid/'hydro.json')
    results=cal.load(cal.OUT/'search_results.json');old_summary=cal.load(cal.OUT/'selected_models.json')
    bound=stage_bound(raw,'86879300')
    bests={r['target_code']:r for r in old_summary['selected']}
    jobs=[]
    p=bests['86879300']['parameters']
    for cn in [20.5,21.5,24.,28.,32.]:
        for bf in [.14,.17]:
            for rec in [.95,.98]:jobs.append(('86879300',dict(p,cn=cn,baseflow_specific=bf,baseflow_recession=rec)))
    pm=bests['86510000']['parameters']
    for cn in [24.,28.,32.]:
        for rec in [.95,.98]:jobs.append(('86510000',dict(pm,cn=cn,baseflow_recession=rec)))
    existing={(r['target_code'],json.dumps(r['parameters'],sort_keys=True)) for r in results}
    jobs=[(c,p) for c,p in jobs if (c,json.dumps(p,sort_keys=True)) not in existing]
    score=cal.OUT/'score_hydro_quality_controlled.json'
    with cf.ThreadPoolExecutor(max_workers=3) as pool:
        fs={pool.submit(cal.execute,args.hec,p,eid,score):(c,p) for c,p in jobs}
        for f in cf.as_completed(fs):
            c,p=fs[f];r=f.result();r.update(target_code=c,observed_stage_crest=cal.peak_stage(raw,c,cfg));r['objective']=cal.objective(r['scores'][c],c,r['observed_stage_crest']);results.append(r)
            cal.save(cal.OUT/'search_results.json',results)
            print(json.dumps(dict(completed=len(results),target=c,nse=r['scores'][c]['nse'])),flush=True)
    for r in results:
        c=r['target_code'];m=r['scores'][c]
        # Add relative MAE so a low-flow recession error cannot disappear
        # merely because the main flood wave dominates NSE variance.
        r['review_objective']=r['objective']+.5*m['mae_m3s']/m['mean_observed_m3s']
        if c=='86879300':
            v=violations(r,bound);r['low_stage_constraint']=v
            r['review_objective']+=2*v['mean_positive_relative_exceedance']
    selected=[]
    for c,name in cfg['targets'].items():
        rr=[r for r in results if r['target_code']==c]
        if c=='86879300' and not any(r['low_stage_constraint']['pass_with_10pct_model_tolerance'] for r in rr):
            raise RuntimeError('No stage-consistent Estrela model: extend the native search before exporting')
        rr.sort(key=lambda r:(0 if c!='86879300' or r['low_stage_constraint']['pass_with_10pct_model_tolerance'] else 1,r['review_objective']))
        best=copy.deepcopy(rr[0]);m=best['scores'][c]
        best.update(target_name=name,calibration_event=eid,fit_only=True,operationally_validated=False,
           timing_error_against_observed_stage_crest_h=(cal.utc(m['full_simulated_peak_time_utc'])-cal.utc(best['observed_stage_crest']['time_utc'])).total_seconds()/3600,
           parameter_selection_uses_complete_calibration_event=True)
        selected.append(best)
    old_summary.update(generated_at_utc=cal.iso(datetime.now(timezone.utc)),total_completed_runs=len(results),selected=selected,
       observed_low_stage_constraint=bound,
       review_rationale='Initial high NSE concealed a second Estrela pulse during missing Q. Observed low stage supplies an upper bound, not a fabricated Q value. Select candidates satisfying that constraint first, then composite loss including relative MAE.')
    cal.save(cal.OUT/'selected_models.json',old_summary);cal.save(cal.OUT/'search_results.json',results)
    print(json.dumps(dict(done=True,selected=[dict(city=r['target_name'],run_id=r['run_id'],nse=r['scores'][r['target_code']]['nse'],constraint=r.get('low_stage_constraint')) for r in selected])),flush=True)

if __name__=='__main__':main()
