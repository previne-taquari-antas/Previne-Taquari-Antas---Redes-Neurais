#!/usr/bin/env python3
"""Event/city-specific native HMS calibration with full-telemetry diagnostics.

The full-Q fit is explicitly conditional on the archived telemetry rating.
Muçum Q <=15 m is retained as a separate strict-domain diagnostic. No event
transfer is required for inclusion in the event library.
"""
import argparse,concurrent.futures as cf,copy,hashlib,json,subprocess,sys,fcntl
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from scipy.stats import qmc
import run_hec_hms_g040_e1_hindcast as hms
import calibrate_mucum_estrela_event_library as v1
import refine_mucum_estrela_stage_consistency as review

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'assets/data/hec_hms_g040_full_basin'
OUT=BASE/'event_members_v2_20261024';EVENT='E24_NOV2023'
def load(p):return json.loads(Path(p).read_text())
def save(p,d):
    p.parent.mkdir(parents=True,exist_ok=True)
    pending=p.with_name(p.name+'.pending')
    pending.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');pending.replace(p)

def prepare():
    conf=load(v1.CONFIG);raw=load(BASE/'historical_calibration_forcing'/EVENT/'hydro.json')
    strict=v1.prepare_scoring(raw,conf);full=copy.deepcopy(raw)
    for c in full['controls']:
        if str(c['code'])!='86510000':continue
        for r in c['recent_rows']:
            t=hms.utc(r['time_utc']);r['time_utc']=v1.iso(t+__import__('datetime').timedelta(minutes=-105))
    save(OUT/'full_Q_clock_corrected.json',full);save(OUT/'strict_Q_domain.json',strict)
    crests={c:v1.peak_stage(raw,c,conf) for c in ['86510000','86879300']}
    return raw,full,strict,crests,review.stage_bound(raw,'86879300')

def execute(hec,p,raw,full,strict,crests,bound):
    sha=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()[:12];rid=EVENT+'_'+sha;dest=OUT/'runs'/rid;rp=dest/'result.json'
    def valid_cache():
        try:
            d=load(rp)
            return d.get('compute_ok') and all((d.get('scores',{}).get(c,{}).get('pairs',0)>=4) for c in ['86510000','86879300'])
        except (OSError,ValueError):return False
    lock_path=OUT/'locks'/f'{rid}.lock';lock_path.parent.mkdir(parents=True,exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if not valid_cache():
            forcing=BASE/'historical_calibration_forcing'/EVENT
            cmd=[sys.executable,'-B',str(ROOT/'scripts/run_hec_hms_g040_e1_hindcast.py'),hec,'--candidate-id',rid,'--event-id',EVENT,
                '--output-root',str(OUT/'runs'),'--rain-file',str(forcing/'rain.json'),'--hydro-file',str(forcing/'hydro.json'),
                '--scenario-file',str(forcing/'scenario.json'),'--score-hydro-file',str(OUT/'full_Q_clock_corrected.json')]
            for k,v in p.items():cmd+=['--'+k.replace('_','-'),str(v)]
            cp=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=300)
            if not valid_cache():raise RuntimeError(cp.stderr[-1000:]+cp.stdout[-500:])
    d=load(rp)
    if not d['compute_ok']:raise RuntimeError('native HEC failed '+rid)
    by=hms.read_output_csv(dest/'project/hec_output_values.csv');times=hms.hourly_axis(hms.utc(d['window']['start_utc']),hms.utc(d['window']['end_utc']))
    strict_scores=hms.score_outputs(by,strict,times,'86472000')
    row=dict(run_id=rid,parameters=p,result_file=str(rp.relative_to(ROOT)),scores=d['scores'],strict_scores=strict_scores,metrics={})
    for code in ['86510000','86879300']:
        m=d['scores'][code];q={t:v for t,v in by['J_'+code]};obs=hms.target_hourly(full,code,times);crest=hms.utc(crests[code]['time_utc'])
        rise=[(obs[t],q[t]) for t in times if t in obs and t in q and 0<=(crest-t).total_seconds()<=24*3600]
        rise_nmae=sum(abs(o-s) for o,s in rise)/sum(o for o,s in rise)
        stage_timing=(hms.utc(m['full_simulated_peak_time_utc'])-crest).total_seconds()/3600
        peak_full=100*(m['full_simulated_peak_m3s']/m['observed_peak_m3s']-1)
        z=dict(full_Q_nse=m['nse'],full_Q_kge=m['kge'],paired_bias_pct=m['pbias_pct'],full_peak_error_vs_recorded_telemetry_pct=peak_full,
            stage_crest_timing_h=stage_timing,rising_limb_nmae=rise_nmae,strict_domain_nse=strict_scores[code].get('nse'),
            paired_Q_nmae=m['mae_m3s']/m['mean_observed_m3s'])
        z['loss']=(.6*(1-m['nse'])+.15*(1-m['kge'])+1.0*abs(m['pbias_pct'])/100+2*abs(peak_full)/100
            +.045*abs(stage_timing)+.5*rise_nmae+.4*z['paired_Q_nmae'])
        row['metrics'][code]=z
    row['low_stage_constraint']=review.violations(row,bound)
    return row

def design(old):
    seeds={r['target_code']:r['parameters'] for r in old['selected']};jobs=[]
    for c,p in seeds.items():jobs.append((c,p,'V1_SCS_reference'))
    for c,count in [('86510000',34),('86879300',24)]:
        seed=seeds[c]
        # Evenly compare legacy loss/UH plus storage with native I+C/Clark.
        samples=qmc.LatinHypercube(13,seed=20261025+(0 if c=='86510000' else 1)).random(count)
        for i,u in enumerate(samples):
            p=dict(seed);ic=(i>=count//3 or c=='86879300')
            p.update(k_g1=1.6+u[0]*2.4,k_g2=.7+u[1]*1.0,k_g3=1.2+u[2]*2.0,baseflow_specific=.09+u[3]*.10,
                     baseflow_recession=.88+u[4]*.11,baseflow_threshold_ratio=.08+u[5]*.2)
            if ic:
                p.update(initial_loss_mm=10+u[6]*60,constant_loss_mm_h=7+u[7]*9,
                    clark_tc_h=(4+u[8]*14 if c=='86510000' else 8+u[8]*20),clark_storage_h=2+u[9]*12)
            else:p.update(cn=20.5+u[6]*14,lag_min=100+u[8]*250)
            if c=='86510000':
                p.update(overbank_threshold_m3s=4500+u[10]*4000,overbank_fraction=.25+u[11]*.60,overbank_release_tau_h=6+u[12]*24)
            jobs.append((c,p,'IC_Clark' if ic else 'SCS_storage'))
    return jobs

def choose(results,code):
    rr=[r for r in results if r['target_code']==code]
    def key(r):
        valid=(code!='86879300' or r['low_stage_constraint']['pass_with_10pct_model_tolerance'])
        return (0 if valid else 1,r['metrics'][code]['loss']+(2*r['low_stage_constraint']['mean_positive_relative_exceedance'] if code=='86879300' else 0))
    return min(rr,key=key)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('hec');ap.add_argument('--phase',choices=['initial','local','all'],default='all');args=ap.parse_args()
    raw,full,strict,crests,bound=prepare();old=load(BASE/'mucum_estrela_event_calibration_20261024/selected_models.json')
    path=OUT/'evaluations.json';results=load(path) if path.exists() else []
    def batch(jobs):
        seen={(r['target_code'],json.dumps(r['parameters'],sort_keys=True)) for r in results}
        jobs=[(c,p,fam) for c,p,fam in jobs if (c,json.dumps(p,sort_keys=True)) not in seen]
        with cf.ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(execute,args.hec,p,raw,full,strict,crests,bound):(c,fam) for c,p,fam in jobs}
            for f in cf.as_completed(futures):
                c,family=futures[f]
                try:
                    r=f.result();r.update(target_code=c,family=family,event_id=EVENT);results.append(r);save(path,results)
                    print(json.dumps(dict(n=len(results),target=c,metrics=r['metrics'][c])),flush=True)
                except Exception as e:
                    with (OUT/'failures.txt').open('a') as fh:fh.write(str(e)+'\n')
                    print('FAILED '+str(e),flush=True)
    if args.phase in ['initial','all']:batch(design(old))
    if args.phase in ['local','all']:
        for it in range(2):
            jobs=[]
            for c in ['86510000','86879300']:
                p=choose(results,c)['parameters']
                steps={'k_g1':(.35,1.3,6),'baseflow_specific':(.02,.04,.25),'baseflow_recession':(.025,.75,.995)}
                if c=='86510000':steps.update(overbank_fraction=(.08,.05,.95),overbank_release_tau_h=(4,2,40),overbank_threshold_m3s=(750,3000,10000))
                else:steps.update(k_g2=(.25,.5,3),k_g3=(.3,1.2,5))
                if 'initial_loss_mm' in p:steps.update(constant_loss_mm_h=(1.5,3,20),clark_tc_h=(3,2,36),clark_storage_h=(2,.5,24))
                for k,(step,lo,hi) in steps.items():
                    if k not in p:continue
                    for sign in [-1,1]:
                        q=dict(p);q[k]=max(lo,min(hi,p[k]+sign*step/(it+1)))
                        if q!=p:jobs.append((c,q,'local_'+str(it)))
            batch(jobs)
    selected=[choose(results,c) for c in ['86510000','86879300']]
    save(OUT/'selected.json',dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),event_id=EVENT,selection_unit='city x event; no requirement to transfer to other events',
         target_evaluations=len(results),unique_native_runs=len({r['run_id'] for r in results}),selected=selected,
         original_level_crests=crests,low_stage_bound=bound,
         caveats=['full Q comparison is conditional on the archived telemetry rating; extreme discharge is not independent field validation',
          'Muçum clock correction -105 min follows the supplied station QA note; Q <=15 m retained as separate diagnostic',
          'Original upstream observed Q and rainfall remain untouched; overbank is a mass-conserving conceptual model hypothesis, not measured floodplain geometry',
          'November rain support median only 3 gauges/hour; parameter compensation is possible']))
    print(json.dumps(dict(done=True,selected=[dict(city=r['target_code'],family=r['family'],metrics=r['metrics'][r['target_code']]) for r in selected])),flush=True)

if __name__=='__main__':main()
