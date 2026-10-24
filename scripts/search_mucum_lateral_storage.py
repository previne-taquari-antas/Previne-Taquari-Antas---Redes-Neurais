#!/usr/bin/env python3
"""Screen causal parallel-storage hypotheses, then require native verification.

The source boundary is unchanged. A branch diverts above-threshold flow into
a linear reservoir and returns its outflow before channel routing. Storage is
a calibrated whole-reach hypothesis, NOT the measured local drone capacity.
This Python screen is not an HEC-HMS result.
"""
import json,sys
from pathlib import Path
import numpy as np
from scipy.signal import lfilter
from scipy.optimize import differential_evolution
import run_hec_hms_g040_e1_hindcast as hms
import build_mucum_floodplain_storage as geo

OUT=geo.OUT/'lateral_reach_hypothesis'

def route(q,k):
    dt=.05;c0=dt/(2*k+dt);c2=(2*k-dt)/(2*k+dt)
    return lfilter([c0,c0],[1,-c2],q,zi=[q[0]*(1-c0)])[0]

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    bounded='--capacity' in sys.argv
    old=geo.OUT/'verified_isolated_native_diagnostic_rawclock/project/hec_output_values.csv'
    by=hms.read_output_csv(old);times=[t for t,q in by['SRC_86472000']];qsrc=np.array([q for t,q in by['SRC_86472000']]);n=len(times)
    b=np.array([q for t,q in by['SB_B_86500000']]);c=np.array([q for t,q in by['SB_C_86472000_86510000']])
    raw=json.loads((hms.BASE/'historical_calibration_forcing/E24_NOV2023/hydro.json').read_text());axis=hms.hourly_axis(times[0],times[-1]);obs=hms.target_hourly(raw,'86510000',axis)
    index={t:i for i,t in enumerate(times)};ii=np.array([index[t] for t in obs]);o=np.array(list(obs.values()));peak_obs=max(o)
    hc=next(x for x in raw['controls'] if str(x['code'])=='86510000');low={hms.utc(r['time_utc']) for r in hc['recent_rows'] if r.get('level_source_unit') is not None and r['level_source_unit']<=1500}
    li=np.array([j for j,t in enumerate(obs) if t in low]);crest=hms.utc('2023-11-19T02:45:00Z');days=np.arange(n)*.05/24
    rise=np.array([j for j,t in enumerate(obs) if 0<=(crest-t).total_seconds()<=24*3600]);fall=np.array([j for j,t in enumerate(obs) if t>crest])
    denom=np.sum((o-o.mean())**2);ldenom=np.sum((o[li]-o[li].mean())**2)
    capacity=None
    if bounded:
        capacity=json.loads((OUT/'regional_hourly_capacity.json').read_text());ct=np.array([hms.utc(r['time_utc']).timestamp() for r in capacity['hourly']]);cv=np.array([r['connected_land_volume_m3'] for r in capacity['hourly']])
    def budget(p):
        if capacity is None:return float('inf')
        onset=max(0,int(np.flatnonzero(qsrc>p[1])[0])-1)
        reference=float(np.interp(times[onset].timestamp(),ct,cv))
        return .98*(max(cv)-reference)
    def simulate(p):
        k,threshold,fraction,tau,bf,rec=p
        diversion=fraction*np.maximum(qsrc-threshold,0);release=route(diversion,tau)
        effective=qsrc-diversion+release
        scale=bf/.14795432458733807*(rec/.9410459041489682)**days
        routed=route(route(effective,k*2.557/43.975)+b*scale,k*41.418/43.975)+c*scale
        storage=release*tau*3600
        return routed,storage,diversion,release
    def metrics(q,s):
        paired=q[ii];err=paired-o;peak=int(np.argmax(q));dt=(times[peak]-crest).total_seconds()/3600
        return dict(NSE=float(1-np.sum(err**2)/denom),strict_NSE=float(1-np.sum(err[li]**2)/ldenom),bias_pct=float(100*err.sum()/o.sum()),
            peak_error_pct=float(100*(max(q)/peak_obs-1)),peak_time_minus_SGB_h=dt,
            rise_NMAE=float(np.abs(err[rise]).sum()/o[rise].sum()),recession_NMAE=float(np.abs(err[fall]).sum()/o[fall].sum()),
            storage_max_m3=float(max(s)),storage_end_m3=float(s[-1]))
    baseline=simulate([5,10000,0,10,.14795432458733807,.9410459041489682])[0]
    reference=np.array([q for t,q in by['J_MUCUM_INFLOW']]);baseline_error=float(max(abs(baseline-reference)))
    if baseline_error>1:raise RuntimeError('Proxy disagrees with native baseline '+str(baseline_error))
    def objective(p):
        q,s,_,_=simulate(p);m=metrics(q,s)
        # Global curve and both limbs, with explicit peak/timing/bias penalties.
        return 8*(1-m['NSE'])+2*m['rise_NMAE']+m['recession_NMAE']+.7*abs(m['peak_error_pct'])/100+.04*abs(m['peak_time_minus_SGB_h'])+.5*abs(m['bias_pct'])/100+max(0,.97-m['strict_NSE'])+100*max(0,m['storage_max_m3']/budget(p)-1)
    bounds=[(.5,7),(3500,11500),(.02,.98),(2,120),(.06,.25),(.82,.998)]
    candidates=[]
    for seed in [20261024,20261025,20261026]:
        result=differential_evolution(objective,bounds,seed=seed,popsize=12,maxiter=280 if bounded else 220,tol=1e-7,polish=True)
        q,s,div,rel=simulate(result.x);m=metrics(q,s)
        row=dict(parameters=dict(zip(['k_g1','threshold_m3s','fraction','tau_h','baseflow_specific','baseflow_recession'],map(float,result.x))),metrics=m,objective=float(result.fun),evaluations=result.nfev,
            source_input_unchanged=True,proxy_only=True,local_terrain_curve_unchanged=True,whole_reach_storage_measured=False,regional_capacity_constraint=bounded,
            incremental_storage_budget_m3=budget(result.x) if bounded else None)
        candidates.append(row);geo.save(OUT/'screening.json',dict(native_baseline_proxy_max_error_m3s=baseline_error,candidates=candidates,selected=min(candidates,key=lambda r:r['objective'])))
        print(json.dumps(row),flush=True)

if __name__=='__main__':main()
