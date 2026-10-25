#!/usr/bin/env python3
"""Screen SCS/Clark event wetting with separate Prata response; verify natively."""
import json
import numpy as np
from scipy.optimize import least_squares
import calibrate_mucum_may2024 as m
from search_mucum_may2024 import engine

KEYS=['cn_up','tc_up','r_up','cn_down','tc_down','r_down','baseflow_specific','recession','routing_k','cn_prata','tc_prata','r_prata']
BOUNDS=([20.1,1,1,20.1,.5,.5,.002,.85,.75,20.1,1,1],[95,40,65,95,30,45,.15,.999,10,95,40,65])

def main():
    ctx=m.prepare();axis,simulate=engine(ctx);lookup={t:i for i,t in enumerate(axis)};obs={}
    for code in ['86510000','86472000']:
        c=next(c for c in ctx[2]['controls'] if c['code']==code);rr=[r for r in c['recent_rows'] if r.get('flow_m3s') is not None and m.hms.utc(r['time_utc']) in lookup]
        obs[code]=(np.array([lookup[m.hms.utc(r['time_utc'])] for r in rr]),np.array([r['flow_m3s'] for r in rr]))
    ii,o=obs['86510000'];ji,jo=obs['86472000'];crest=axis[ii[int(np.argmax(o))]];rise=np.array([j for j,i in enumerate(ii) if 0<=(crest-axis[i]).total_seconds()<=24*3600]);fall=np.array([j for j,i in enumerate(ii) if axis[i]>crest])
    def parameters(x):
        p=dict(m.SEED);p.update(dict(zip(KEYS,map(float,x))));p['loss_method']='SCS';return p
    def metrics(jj,q):
        err=q[ii]-o;je=jj[ji]-jo;peak=int(ii[0]+np.argmax(q[ii[0]:ii[-1]+1]));return dict(NSE=float(1-(err@err)/np.sum((o-o.mean())**2)),peak_error_pct=float(100*(q[peak]/max(o)-1)),peak_time_h=(axis[peak]-crest).total_seconds()/3600,
            bias_pct=float(100*err.sum()/o.sum()),rise_NMAE=float(np.abs(err[rise]).sum()/o[rise].sum()),recession_NMAE=float(np.abs(err[fall]).sum()/o[fall].sum()),JJ_partial_NSE=float(1-(je@je)/np.sum((jo-jo.mean())**2)))
    rows=[]
    # Multiple physical starts distinguish fast Prata from the larger Antas trunk.
    for n,start in enumerate([[45,8,25,60,3,10,.025,.97,3,55,5,12],[35,14,35,70,6,15,.015,.95,5,65,4,8],[60,10,25,50,4,15,.01,.98,4,35,10,30]]):
        def residual(x):
            jj,q=simulate(parameters(x));err=(q[ii]-o)/max(np.std(o),1);je=(jj[ji]-jo)/max(np.std(jo),1)
            # Moderate relative weighting protects the low-flow/recession shape
            # while retaining the upstream observations as an auxiliary check.
            weights=np.sqrt(1+2000/np.maximum(o,500))
            return np.r_[err*weights,je*.35,(q[ii[np.argmax(o)]]/max(o)-1)*10]
        result=least_squares(residual,start,bounds=BOUNDS,max_nfev=110,xtol=1e-7,ftol=1e-7,diff_step=.002)
        p=parameters(result.x);jj,q=simulate(p);stats=metrics(jj,q);loss=3*(1-stats['NSE'])+stats['rise_NMAE']+.7*stats['recession_NMAE']+.8*abs(stats['peak_error_pct'])/100+.025*abs(stats['peak_time_h'])
        row=dict(parameters=p,proxy_metrics=stats,objective=loss,proxy_only=True,evaluations=result.nfev,start_index=n)
        rows.append(row);m.save(m.OUT/'scs_screening.json',dict(candidates=rows,selected=min(rows,key=lambda r:r['objective'])));m.save(m.OUT/'scs_selected_parameters.json',min(rows,key=lambda r:r['objective'])['parameters']);print(json.dumps(row),flush=True)

if __name__=='__main__':main()
