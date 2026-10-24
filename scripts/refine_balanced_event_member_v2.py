#!/usr/bin/env python3
"""Refine Muçum peak while retaining the separately checked low-stage fit."""
import concurrent.futures as cf,json,sys
import calibrate_event_members_v2 as v
import calibrate_mucum_estrela_event_library as old
import refine_mucum_estrela_stage_consistency as review

def main():
    cfg=v.load(old.CONFIG);raw=v.load(v.BASE/'historical_calibration_forcing'/v.EVENT/'hydro.json')
    full=v.load(v.OUT/'full_Q_clock_corrected.json');strict=v.load(v.OUT/'strict_Q_domain.json')
    crests={c:old.peak_stage(raw,c,cfg) for c in ['86510000','86879300']};bound=review.stage_bound(raw,'86879300')
    p=dict(cn=24.,lag_min=263.3293016944609,k_g1=2.111432470091512,k_g2=.9626194665274246,k_g3=4.686360215918556,k_g4=4.038461538461538,
        x=.21694512692521034,baseflow_specific=.12,baseflow_recession=.98,baseflow_threshold_ratio=.2207436003961918,
        overbank_threshold_m3s=6000.,overbank_fraction=.3,overbank_release_tau_h=96.)
    jobs=[dict(p)]
    for k,step in dict(k_g1=.3,baseflow_specific=.02,cn=2.,overbank_release_tau_h=24.,overbank_fraction=.05,overbank_threshold_m3s=500.).items():
        for sign in [-1,1]:q=dict(p);q[k]+=sign*step;jobs.append(q)
    for dk,db in [(-.3,.02),(-.3,.04),(-.15,.02),(.15,.02)]:jobs.append(dict(p,k_g1=p['k_g1']+dk,baseflow_specific=p['baseflow_specific']+db))
    # Activate the lateral-storage hypothesis only at larger upstream flows,
    # keeping the separately checked low-stage rising limb less affected.
    for k in [1.8,2.1]:
        for bf in [.14,.16]:
            jobs.append(dict(p,k_g1=k,baseflow_specific=bf,overbank_threshold_m3s=8500.,overbank_fraction=.5))
        jobs.append(dict(p,k_g1=k,baseflow_specific=.14,overbank_threshold_m3s=8000.,overbank_fraction=.45))
        jobs.append(dict(p,k_g1=k,baseflow_specific=.14,overbank_threshold_m3s=9000.,overbank_fraction=.6))
    path=v.OUT/'balanced_refinement.json';rs=v.load(path) if path.exists() else []
    seen={json.dumps(r['parameters'],sort_keys=True) for r in rs};jobs=[p for p in jobs if json.dumps(p,sort_keys=True) not in seen]
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        fs=[pool.submit(v.execute,sys.argv[1],p,raw,full,strict,crests,bound) for p in jobs]
        for f in cf.as_completed(fs):
            try:
                r=f.result();r.update(target_code='86510000',family='balanced_peak_lowflow_refinement',event_id=v.EVENT);rs.append(r);v.save(path,rs)
                print(json.dumps(r['metrics']['86510000']),flush=True)
            except Exception as e:print('FAILED '+str(e),flush=True)

if __name__=='__main__':main()
