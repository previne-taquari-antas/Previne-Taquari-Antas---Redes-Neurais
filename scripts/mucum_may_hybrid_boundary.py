#!/usr/bin/env python3
"""Use real JJ Q where available; explicitly model, never relabel, missing Q.

The rainfall model supplies gaps. At each observation its flow-state error is
updated; this correction decays for 12 h into missing periods. No Muçum Q is
used by the reconstruction. Parameters are event-calibrated, not a forecast test.
"""
import json
import numpy as np
from scipy.optimize import least_squares
import calibrate_mucum_may2024 as m
from search_mucum_may2024 import engine,linear
from refine_mucum_may_initial_state import KEYS,BASEBOUNDS

def reconstruct(times,generated,hydro):
    c=next(c for c in hydro['controls'] if c['code']=='86472000');observed={m.hms.utc(r['time_utc']):r['flow_m3s'] for r in c['recent_rows'] if r.get('flow_m3s') is not None}
    values=[];provenance=[];error=0.;last=None
    for t,q in zip(times,generated):
        if t in observed:
            value=float(observed[t]);error=value-q;last=t;kind='observed_JJ'
        else:
            correction=error*np.exp(-(t-last).total_seconds()/43200) if last is not None else 0.
            value=max(0.,q+correction);kind='rainfall_model_plus_decaying_state' if last is not None else 'rainfall_model'
        values.append(value);provenance.append(kind)
    return np.array(values),provenance

def main():
    ctx=m.prepare();times,rain,hydro,digest=ctx;axis,simulate=engine(ctx);lookup={t:i for i,t in enumerate(axis)};c=next(c for c in hydro['controls'] if c['code']=='86510000');rr=[r for r in c['recent_rows'] if r.get('flow_m3s') is not None];ii=np.array([lookup[m.hms.utc(r['time_utc'])] for r in rr]);o=np.array([r['flow_m3s'] for r in rr]);oi=int(np.argmax(o));crest=axis[ii[oi]];ri=np.array([j for j,i in enumerate(ii) if 0<=(crest-axis[i]).total_seconds()<=86400]);fi=np.array([j for j,i in enumerate(ii) if axis[i]>crest]);step=4
    bounds=(BASEBOUNDS[0]+[0,0,0],BASEBOUNDS[1]+[180,180,180]);old=m.load(m.OUT/'initial_state_screening.json')['candidates'];results=[]
    def run(p):
        jj,q=simulate(p);source,_=reconstruct(times,jj[::step],hydro);src=np.interp(np.arange(len(axis))*.25,np.arange(len(times)),source)
        def route(x):
            for length in [2.557,18.315,23.652]:x=linear(x,p['routing_k']*length/44.524,.25)
            return x
        return jj,q-route(jj)+route(src)
    for n,which in enumerate([1,0]):
        start=[old[which]['parameters'][k] for k in KEYS]
        def params(x):return dict(zip(KEYS,map(float,x)))
        def residual(x):
            jj,q=run(params(x));e=(q[ii]-o)/np.std(o);weights=np.sqrt(1+1000/np.maximum(o,500))
            return np.r_[e*weights,(q[ii[oi]]/max(o)-1)*12,(q[ii[oi]+4]-q[ii[oi]-4])/max(o)*8]
        opt=least_squares(residual,start,bounds=bounds,max_nfev=140,diff_step=.002,ftol=1e-7,xtol=1e-7);p=params(opt.x);jj,q=run(p);e=q[ii]-o;peak=int(ii[0]+np.argmax(q[ii[0]:ii[-1]+1]));stats=dict(NSE=float(1-(e@e)/np.sum((o-o.mean())**2)),peak_error_pct=float(100*(q[peak]/max(o)-1)),peak_time_h=(axis[peak]-crest).total_seconds()/3600,bias_pct=float(100*e.sum()/o.sum()),rise_NMAE=float(np.abs(e[ri]).sum()/o[ri].sum()),recession_NMAE=float(np.abs(e[fi]).sum()/o[fi].sum()))
        score=5*(1-stats['NSE'])+stats['rise_NMAE']+stats['recession_NMAE']+abs(stats['peak_error_pct'])/100+.05*abs(stats['peak_time_h']);row=dict(parameters=p,proxy_metrics=stats,objective=score,proxy_only=True,source_reconstruction_tau_hours=12.,source_provenance_explicit=True,modelled_values_not_claimed_as_observed=True)
        results.append(row);m.save(m.OUT/'hybrid_screening.json',dict(candidates=results,selected=min(results,key=lambda r:r['objective'])));m.save(m.OUT/'hybrid_selected_parameters.json',min(results,key=lambda r:r['objective'])['parameters']);print(json.dumps(row),flush=True)

if __name__=='__main__':main()
