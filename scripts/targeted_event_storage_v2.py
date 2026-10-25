#!/usr/bin/env python3
"""Independent city/event candidate supplement; never overwrites active search."""
import concurrent.futures as cf,copy,json
import calibrate_event_members_v2 as v
import calibrate_mucum_estrela_event_library as old
import refine_mucum_estrela_stage_consistency as review

def main():
    import sys
    hec=sys.argv[1];cfg=v.load(old.CONFIG);eid=v.EVENT
    raw=v.load(v.BASE/'historical_calibration_forcing'/eid/'hydro.json')
    full=v.load(v.OUT/'full_Q_clock_corrected.json');strict=v.load(v.OUT/'strict_Q_domain.json')
    crests={c:old.peak_stage(raw,c,cfg) for c in ['86510000','86879300']};bound=review.stage_bound(raw,'86879300')
    seeds={r['target_code']:r['parameters'] for r in v.load(v.BASE/'mucum_estrela_event_calibration_20261024/selected_models.json')['selected']}
    jobs=[]
    # Native channel storage: USACE permits calibration of Muskingum subreaches.
    for k in [2.5,3.5,4.5,5.5]:
        for bf in [.12,.18]:
            jobs.append(('86510000',dict(seeds['86510000'],k_g1=k,x=0.,routing_subreach_target=1,baseflow_specific=bf),'native_channel_storage'))
    # Slow off-channel hypothesis preserves the event water balance explicitly.
    for tau in [48.,96.,168.]:
        for frac in [.3,.5]:
            for bf in [.12,.16]:jobs.append(('86510000',dict(seeds['86510000'],overbank_threshold_m3s=6000.,overbank_fraction=frac,overbank_release_tau_h=tau,baseflow_specific=bf),'slow_floodplain_storage'))
    for scale in [.6,.7,.8,.9]:
        p=dict(seeds['86879300']);p.update(k_g1=max(1.3,p['k_g1']*scale),k_g2=max(.5,p['k_g2']*scale),k_g3=max(1.2,p['k_g3']*scale))
        jobs.append(('86879300',p,'legacy_event_route_refinement'))
        for bf in [.14,.18]:jobs.append(('86879300',dict(p,x=0.,routing_subreach_target=1,baseflow_specific=bf),'native_channel_storage'))
    for constant in [10.,12.,14.]:
        for tc in [12.,18.,24.]:
            p=dict(seeds['86879300'],k_g1=2.2,k_g2=.9,k_g3=1.4,initial_loss_mm=25.,constant_loss_mm_h=constant,
                   clark_tc_h=tc,clark_storage_h=8.,baseflow_specific=.14)
            jobs.append(('86879300',p,'targeted_IC_Clark'))
    path=v.OUT/'supplement_evaluations.json';results=v.load(path) if path.exists() else []
    seen={(r['target_code'],json.dumps(r['parameters'],sort_keys=True)) for r in results}
    jobs=[(c,p,f) for c,p,f in jobs if (c,json.dumps(p,sort_keys=True)) not in seen]
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        fs={pool.submit(v.execute,hec,p,raw,full,strict,crests,bound):(c,fam) for c,p,fam in jobs}
        for f in cf.as_completed(fs):
            c,fam=fs[f]
            try:
                r=f.result();r.update(target_code=c,family=fam,event_id=eid);results.append(r);v.save(path,results)
                print(json.dumps(dict(n=len(results),target=c,family=fam,metrics=r['metrics'][c])),flush=True)
            except Exception as e:print('FAILED '+str(e),flush=True)

if __name__=='__main__':main()
