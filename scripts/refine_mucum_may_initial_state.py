#!/usr/bin/env python3
"""Calibrate antecedent initial loss, keeping seven-day observed rain unchanged."""
import json
import numpy as np
from scipy.optimize import least_squares
import calibrate_mucum_may2024 as m
from search_mucum_may2024 import engine
from refine_mucum_may_responses import KEYS as BASEKEYS,BOUNDS as BASEBOUNDS

KEYS=BASEKEYS+['initial_up','initial_down','initial_prata']

def main():
    ctx=m.prepare();axis,simulate=engine(ctx);lookup={t:i for i,t in enumerate(axis)};obs={}
    for code in ['86510000','86472000']:
        c=next(c for c in ctx[2]['controls'] if c['code']==code);rr=[r for r in c['recent_rows'] if r.get('flow_m3s') is not None and m.hms.utc(r['time_utc']) in lookup]
        obs[code]=(np.array([lookup[m.hms.utc(r['time_utc'])] for r in rr]),np.array([r['flow_m3s'] for r in rr]))
    ii,o=obs['86510000'];ji,jo=obs['86472000'];oi=int(np.argmax(o));crest=axis[ii[oi]];ri=np.array([j for j,i in enumerate(ii) if 0<=(crest-axis[i]).total_seconds()<=24*3600]);fi=np.array([j for j,i in enumerate(ii) if axis[i]>crest]);old=m.load(m.OUT/'response_screening.json')['candidates'];rows=[]
    bounds=(BASEBOUNDS[0]+[0,0,0],BASEBOUNDS[1]+[180,180,180])
    for n,(which,initials,jweight) in enumerate([(0,[40,60,40],.2),(1,[60,40,60],.2),(0,[20,25,20],.35)]):
        start=[old[which]['parameters'][k] for k in BASEKEYS]+initials
        def parameters(x):return dict(zip(KEYS,map(float,x)))
        def residual(x):
            jj,q=simulate(parameters(x));err=(q[ii]-o)/np.std(o);je=(jj[ji]-jo)/np.std(jo);weights=np.sqrt(1+700/np.maximum(o,500))
            return np.r_[err*weights,je*jweight,(q[ii[oi]]/max(o)-1)*10,(q[ii[oi]+4]-q[ii[oi]-4])/max(o)*6]
        result=least_squares(residual,start,bounds=bounds,max_nfev=150,diff_step=.002,ftol=1e-8,xtol=1e-8)
        p=parameters(result.x);jj,q=simulate(p);err=q[ii]-o;je=jj[ji]-jo;peak=int(ii[0]+np.argmax(q[ii[0]:ii[-1]+1]));stats=dict(NSE=float(1-(err@err)/np.sum((o-o.mean())**2)),peak_error_pct=float(100*(q[peak]/max(o)-1)),peak_time_h=(axis[peak]-crest).total_seconds()/3600,
            bias_pct=float(100*err.sum()/o.sum()),rise_NMAE=float(np.abs(err[ri]).sum()/o[ri].sum()),recession_NMAE=float(np.abs(err[fi]).sum()/o[fi].sum()),JJ_partial_NSE=float(1-(je@je)/np.sum((jo-jo.mean())**2)))
        objective=5*(1-stats['NSE'])+stats['rise_NMAE']+stats['recession_NMAE']+abs(stats['peak_error_pct'])/100+.04*abs(stats['peak_time_h'])
        row=dict(parameters=p,proxy_metrics=stats,objective=objective,proxy_only=True,evaluations=result.nfev,start_index=n);rows.append(row)
        m.save(m.OUT/'initial_state_screening.json',dict(candidates=rows,selected=min(rows,key=lambda r:r['objective'])));m.save(m.OUT/'initial_state_selected_parameters.json',min(rows,key=lambda r:r['objective'])['parameters']);print(json.dumps(row),flush=True)

if __name__=='__main__':main()
