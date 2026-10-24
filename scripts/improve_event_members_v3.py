#!/usr/bin/env python3
"""Native HMS trust-region refinement, independently for each city/event.

No output correction or observed target is used as an input boundary.
The residual gives separate weight to low-stage Q, rise and recession.
"""
import argparse,concurrent.futures as cf,copy,json,sys,time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import calibrate_event_members_v2 as v

V2=v.BASE/'event_members_v2_20261024'
OUT=v.BASE/'event_members_v3_20261024'
CITIES={'86510000':'Muçum','86879300':'Estrela'}

def setup():
    v.OUT=OUT
    return v.prepare()

def numerically_feasible(p):
    args=SimpleNamespace(**p)
    try:
        for name,up,down,length,group in v.hms.active_reaches('86472000'):
            v.hms.muskingum_steps(v.hms.route_k(length,group,args),p['x'])
    except (RuntimeError,ValueError):return False
    return True

def evaluate(hec,c,p,ctx):
    r=v.execute(hec,p,*ctx);r.update(target_code=c,target_name=CITIES[c],event_id=v.EVENT,family='V3_native_refinement')
    native=v.load(v.ROOT/r['result_file']);by=v.hms.read_output_csv((v.ROOT/r['result_file']).parent/'project/hec_output_values.csv')
    axis=v.hms.hourly_axis(v.hms.utc(native['window']['start_utc']),v.hms.utc(native['window']['end_utc']))
    full=v.hms.target_hourly(ctx[1],c,axis);strict=v.hms.target_hourly(ctx[2],c,axis);sim=dict(by['J_'+c]);crest=v.hms.utc(ctx[3][c]['time_utc'])
    pairs=[(t,full[t],sim[t]) for t in axis if t in full and t in sim]
    groups=[pairs,[(t,o,q) for t,o,q in pairs if t in strict],[(t,o,q) for t,o,q in pairs if 0<=(crest-t).total_seconds()/3600<=24],[(t,o,q) for t,o,q in pairs if t>crest]]
    weights=[.20,.40,.20,.20] if c=='86510000' else [.35,.05,.30,.30]
    residual=[];extra={}
    for group,w,label in zip(groups,weights,['full','strict','rise','recession']):
        o=np.array([o for t,o,q in group]);q=np.array([q for t,o,q in group]);scale=max(float(o.mean()),500.)
        residual.extend(np.sqrt(w/len(o))*(q-o)/scale)
        extra[label+'_nmae']=float(np.abs(q-o).sum()/o.sum())
    m=r['metrics'][c];residual += [2*m['full_peak_error_vs_recorded_telemetry_pct']/100,.7*m['paired_bias_pct']/100]
    # Smooth upper-bound residuals constrain the 32 missing-Q low-stage hours.
    bound=ctx[4];tt=[v.hms.utc(t) for t in bound['times_utc']];qq=np.array([sim[t] for t in tt]);excess=np.maximum(0,qq/bound['Q_upper_bound_m3s']-1)
    if c=='86879300':residual.extend(np.sqrt(2/len(excess))*excess)
    z=np.array(residual);r['refinement_metrics']=extra;r['refinement_objective']=float(z@z)
    return r,z

def main():
    ap=argparse.ArgumentParser();ap.add_argument('hec');ap.add_argument('--city',choices=list(CITIES));args=ap.parse_args()
    hec=args.hec;ctx=setup();seed=v.load(V2/'selection_manifest.json');out=v.OUT/'refinement_evaluations.json'
    history=v.load(out) if out.exists() else [];best_rows=[]
    specs={
      '86510000':dict(cn=(1.,20.01,45),lag_min=(20.,50,450),k_g1=(.10,.8,4),baseflow_specific=(.012,.03,.25),baseflow_recession=(.012,.8,.998),baseflow_threshold_ratio=(.025,.04,.45),overbank_fraction=(.04,.1,.9),overbank_threshold_m3s=(400.,4500,11000),overbank_release_tau_h=(12.,12,180)),
      '86879300':dict(k_g1=(.10,.8,4),k_g2=(.10,.4,2.5),k_g3=(.10,.5,3),k_g4=(.10,.8,3.5),baseflow_specific=(.012,.03,.25),baseflow_recession=(.012,.8,.998),baseflow_threshold_ratio=(.025,.04,.45),initial_loss_mm=(4.,5,100),constant_loss_mm_h=(.6,4,25),clark_tc_h=(.8,2,30),clark_storage_h=(.4,.3,18))}
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
      for seed_row in seed['selected']:
        c=seed_row['target_code'];p=dict(seed_row['parameters']);sp=specs[c];keys=list(sp);sc=np.array([sp[k][0] for k in keys]);lo=np.array([sp[k][1] for k in keys]);hi=np.array([sp[k][2] for k in keys])
        if args.city and args.city!=c:continue
        checkpoint=v.OUT/(c+'_best.json')
        completed=v.load(checkpoint)['iteration']+1 if checkpoint.exists() else 0
        if completed>=5:continue
        def run(params):return evaluate(hec,c,params,ctx)
        def record(res):
            r,z=res;history.append(r);v.save(out,history)
            print(json.dumps(dict(n=len(history),city=c,objective=r['refinement_objective'],metrics=r['metrics'][c],segments=r['refinement_metrics'])),flush=True)
            return res
        current,z=record(run(p));initial=current
        # Resume from the best prior actual native evaluation of this city.
        prior=[r for r in history if r['target_code']==c]
        prior=min(prior,key=lambda r:r['refinement_objective'])
        if prior['refinement_objective']<current['refinement_objective']:p=prior['parameters'];current,z=run(p)
        trust=1.5
        for iteration in range(completed,5):
            x=np.array([p[k] for k in keys]);jobs=[];deltas=[]
            for j,k in enumerate(keys):
                dx=sc[j]*(.7 if iteration>=3 else 1.)
                if x[j]+dx>hi[j]:dx=-dx
                pp=dict(p);pp[k]=float(x[j]+dx)
                for attempt in range(24):
                    if numerically_feasible(pp):break
                    dx*=-.5;pp[k]=float(x[j]+dx)
                else:raise RuntimeError('No stable finite difference for '+k)
                jobs.append(pp);deltas.append(dx/sc[j])
            vals=[record(r) for r in pool.map(run,jobs)]
            jac=np.column_stack([(zz-z)/delta for (rr,zz),delta in zip(vals,deltas)])
            step=np.linalg.solve(jac.T@jac+np.eye(len(keys))*max(1e-7,float(np.trace(jac.T@jac)/len(keys))*.03),-jac.T@z)
            step=np.clip(step,-trust,trust);candidates=[]
            for alpha in [1.,.5]:
                for attempt in range(24):
                    xx=np.clip(x+alpha*step*sc,lo,hi);pp=dict(p);pp.update({k:float(val) for k,val in zip(keys,xx)})
                    if numerically_feasible(pp):break
                    alpha*=.5
                else:raise RuntimeError('No stable native trust-region step')
                candidates.append(pp)
            vals += [record(r) for r in pool.map(run,candidates)]
            candidate,zz=min(vals+[(current,z)],key=lambda r:r[0]['refinement_objective'])
            improved=candidate['refinement_objective']<current['refinement_objective']-1e-7
            current,z=candidate,zz;p=current['parameters'];trust=min(2.5,trust*1.2) if improved else trust*.5
            v.save(v.OUT/(c+'_best.json'),dict(baseline=initial,selected=current,iteration=iteration))
        best_rows.append(current)
    best_rows=[v.load(v.OUT/(c+'_best.json'))['selected'] for c in CITIES if (v.OUT/(c+'_best.json')).exists()]
    v.save(v.OUT/'search_selected.json',dict(selected=best_rows))

if __name__=='__main__':main()
