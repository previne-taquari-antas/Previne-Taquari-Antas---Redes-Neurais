#!/usr/bin/env python3
"""Execute reproducible native-HMS historical target/event calibration.

No target observation enters boundary forcing. Observations used to choose
parameters are explicitly calibration data. Future observed upstream flow and
rainfall make these historical hindcasts, not real-time forecasts.
"""
from __future__ import annotations
import argparse, concurrent.futures as cf, copy, csv, hashlib, json, math, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from scipy.stats import qmc

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'assets/data/hec_hms_g040_full_basin'
OUT=BASE/'mucum_estrela_event_calibration_20261024'
CONFIG=ROOT/'config/hec_mucum_estrela_event_calibration_20261024.json'
KEYS=['cn','lag_min','k_g1','k_g2','k_g3','x','baseflow_specific','baseflow_recession','baseflow_threshold_ratio']
BOUNDS=[(24,48),(35,330),(1.8,6.0),(.6,3.2),(1.2,5.5),(.08,.24),(.025,.19),(.80,.985),(.06,.30)]
P0=dict(cn=34.11993525,lag_min=71.18895694218449,k_g1=5.,k_g2=1.9285714285714284,k_g3=3.9545454545454546,k_g4=4.038461538461538,x=.14705882352941177)
P1=dict(cn=39.7339445,lag_min=150.88032734900438,k_g1=2.46,k_g2=.9957142857142856,k_g3=1.8263636363636364,k_g4=1.8607692307692305,x=.12352941176470589)

def load(p):return json.loads(Path(p).read_text())
def save(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def utc(s):return datetime.fromisoformat(s.replace('Z','+00:00'))
def iso(t):return t.isoformat().replace('+00:00','Z')

def prepare_scoring(raw,conf):
    """Apply the user's dated station QA only to a separate score package."""
    d=copy.deepcopy(raw)
    for c in d['controls']:
        qa=conf['observation_quality'].get(str(c['code']))
        if not qa:continue
        for r in c['recent_rows']:
            t=utc(r['time_utc'])
            if utc(qa['clock_offset_start_utc'])<=t<utc(qa['clock_offset_end_utc']):
                r['time_utc']=iso(t+timedelta(minutes=qa['clock_offset_minutes']))
            level=r.get('level_source_unit')
            if level is None or level>qa['max_discharge_stage_source_unit']:
                r['flow_m3s']=None
    d['score_only_quality_control']=conf['observation_quality']
    return d

def peak_stage(raw,code,conf):
    c=next(c for c in raw['controls'] if str(c['code'])==code)
    rows=[r for r in c['recent_rows'] if r.get('level_source_unit') is not None]
    r=max(rows,key=lambda r:r['level_source_unit']);t=utc(r['time_utc'])
    qa=conf['observation_quality'].get(code,{})
    if qa and utc(qa['clock_offset_start_utc'])<=t<utc(qa['clock_offset_end_utc']):
        t+=timedelta(minutes=qa['clock_offset_minutes'])
    return dict(time_utc=iso(t),level_source_unit=r['level_source_unit'])

def objective(m,code,crest):
    if not m or m.get('nse') is None:return 1e6
    timing=(utc(m['full_simulated_peak_time_utc'])-utc(crest['time_utc'])).total_seconds()/3600
    # For Muçum, the extreme discharge amplitude is outside the user-supplied
    # rating-curve domain. Its recorded surrogate peak must not drive fitting.
    peak=abs(m.get('peak_error_pct',0))/100 if code=='86879300' else 0
    loss=(1-m['nse'])+.4*(1-m['kge'])+1.4*abs(m['pbias_pct'])/100+1.5*peak+.025*abs(timing)
    return float(loss)

def candidates(code):
    rows=[]
    for p in [P0,P1]:
        rows.append(dict(p))
        for bf in [.08,.14]:
            rows.append(dict(p,baseflow_specific=bf,baseflow_recession=.95,baseflow_threshold_ratio=.15))
    if code=='86510000':
        rows.extend([dict(P0,overbank_threshold_m3s=t,overbank_fraction=.35,overbank_release_tau_h=12)
                     for t in [5000,7000]])
    sample=qmc.LatinHypercube(d=len(KEYS),seed=20261024+(0 if code=='86510000' else 1)).random(24-len(rows))
    for v in qmc.scale(sample,[a for a,b in BOUNDS],[b for a,b in BOUNDS]):
        p=dict(P0 if code=='86510000' else P1);p.update(dict(zip(KEYS,map(float,v))));rows.append(p)
    return rows

def execute(hec,p,eid,score_path):
    digest=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()[:12]
    rid=f'{eid}_{digest}'
    out=OUT/'runs'/rid
    rp=out/'result.json'
    if not rp.exists():
        forcing=BASE/'historical_calibration_forcing'/eid
        cmd=[sys.executable,'-B',str(ROOT/'scripts/run_hec_hms_g040_e1_hindcast.py'),hec,
             '--candidate-id',rid,'--event-id',eid,'--output-root',str(OUT/'runs'),
             '--rain-file',str(forcing/'rain.json'),'--hydro-file',str(forcing/'hydro.json'),
             '--scenario-file',str(forcing/'scenario.json'),'--score-hydro-file',str(score_path)]
        for k,v in p.items():cmd.extend(['--'+k.replace('_','-'),str(v)])
        proc=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=300)
        if not rp.exists():raise RuntimeError(proc.stderr[-1000:] or proc.stdout[-1000:])
    d=load(rp)
    if not d['compute_ok']:raise RuntimeError(f'HEC failed: {out}')
    return dict(run_id=rid,parameters=p,result_file=str(rp.relative_to(ROOT)),scores=d['scores'])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('hec');ap.add_argument('--workers',type=int,default=3);ap.add_argument('--phase',choices=['initial','local','all'],default='all');args=ap.parse_args()
    cfg=load(CONFIG);eid=cfg['event_id'];raw=load(BASE/'historical_calibration_forcing'/eid/'hydro.json')
    score_path=OUT/'score_hydro_quality_controlled.json';save(score_path,prepare_scoring(raw,cfg))
    evidence=[CONFIG,score_path,ROOT/'scripts/run_hec_hms_g040_e1_hindcast.py',
              *[(BASE/'historical_calibration_forcing'/eid/f) for f in ['rain.json','hydro.json','scenario.json']]]
    fingerprints={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence}
    provenance_path=OUT/'input_fingerprints.json'
    if provenance_path.exists() and load(provenance_path)!=fingerprints:
        raise RuntimeError('Calibration inputs/configuration changed: use a fresh output directory; never reuse stale cached scores')
    save(provenance_path,fingerprints)
    crests={c:peak_stage(raw,c,cfg) for c in cfg['targets']}
    results_path=OUT/'search_results.json';results=load(results_path) if results_path.exists() else []
    def batch(jobs):
        existing={(r['target_code'],json.dumps(r['parameters'],sort_keys=True)) for r in results}
        jobs=[(c,p) for c,p in jobs if (c,json.dumps(p,sort_keys=True)) not in existing]
        with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
            fs={pool.submit(execute,args.hec,p,eid,score_path):(c,p) for c,p in jobs}
            for f in cf.as_completed(fs):
                c,p=fs[f]
                try:
                    row=f.result();m=row['scores'][c];row.update(target_code=c,objective=objective(m,c,crests[c]),observed_stage_crest=crests[c])
                    results.append(row);save(results_path,results)
                    print(json.dumps(dict(completed=len(results),target=c,objective=round(row['objective'],5),nse=round(m['nse'],5),bias=round(m['pbias_pct'],2),run_id=row['run_id'])),flush=True)
                except Exception as ex:
                    with (OUT/'failures.jsonl').open('a') as fh:fh.write(json.dumps(dict(target=c,parameters=p,error=str(ex)))+'\n')
                    print('FAILED '+str(ex),flush=True)
    stages_path=OUT/'search_stages_completed.json'
    stages=load(stages_path) if stages_path.exists() else {}
    if args.phase in ['initial','all'] and not stages.get('initial'):
        batch([(c,p) for c in cfg['targets'] for p in candidates(c)])
        stages['initial']=True;save(stages_path,stages)
    if args.phase in ['local','all']:
        for iteration in range(2):
            if stages.get(f'local_{iteration}'):continue
            jobs=[]
            for c in cfg['targets']:
                best=min([r for r in results if r['target_code']==c],key=lambda r:r['objective'])
                p=best['parameters']
                steps={'cn':3.,'lag_min':35.,'k_g1':.65,'k_g2':.35,'k_g3':.6,'baseflow_specific':.025,'baseflow_recession':.035,'baseflow_threshold_ratio':.05}
                for k,step in steps.items():
                    if k not in p:continue
                    i=KEYS.index(k);lo,hi=BOUNDS[i]
                    for sign in [-1,1]:
                        v=min(hi,max(lo,p[k]+sign*step/(iteration+1)));q=dict(p,**{k:v})
                        if q!=p:jobs.append((c,q))
            batch(jobs)
            stages[f'local_{iteration}']=True;save(stages_path,stages)
    selected=[]
    for c,name in cfg['targets'].items():
        rr=sorted([r for r in results if r['target_code']==c],key=lambda r:r['objective'])
        best=copy.deepcopy(rr[0]);m=best['scores'][c]
        best.update(target_name=name,calibration_event=eid,fit_only=True,operationally_validated=False,
          timing_error_against_observed_stage_crest_h=(utc(m['full_simulated_peak_time_utc'])-utc(crests[c]['time_utc'])).total_seconds()/3600,
          parameter_selection_uses_complete_calibration_event=True)
        selected.append(best)
    summary=dict(generated_at_utc=iso(datetime.now(timezone.utc)),configuration=cfg,total_completed_runs=len(results),selected=selected,
       evidence_limits=['November median rain support is only 3 gauges/hour; parameter compensation is possible',
        'Estrela Q observations cover only part of this event; missing observations are never interpolated across outages',
        'Observed upstream Q and rain across full event are historical hindcast inputs, unavailable in advance in a real forecast',
        'Muçum discharge calibration above 15 m is excluded; no extreme-flow amplitude accuracy is claimed',
        'Added recession is a native HEC model hypothesis; not identified groundwater physics or recovered original parameters'])
    save(OUT/'selected_models.json',summary)
    print(json.dumps(dict(done=True,total=len(results),selected=[dict(target=r['target_name'],run_id=r['run_id'],nse=r['scores'][r['target_code']]['nse'],objective=r['objective']) for r in selected])),flush=True)

if __name__=='__main__':main()
