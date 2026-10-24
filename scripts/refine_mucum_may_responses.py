#!/usr/bin/env python3
"""Event-specific Prata/Antas response separation, keeping observed rain fixed."""
import json
import numpy as np
from scipy.optimize import least_squares
import calibrate_mucum_may2024 as m
from search_mucum_may2024 import engine

KEYS=m.PARAMS+['loss_prata','tc_prata','r_prata']
BOUNDS=([.05,.5,.5,.05,.5,.5,.002,.85,.75,.05,.5,.5],[12,40,70,12,30,50,.15,.999,12,12,40,70])

def main():
    ctx=m.prepare();axis,simulate=engine(ctx);lookup={t:i for i,t in enumerate(axis)};obs={}
    for code in ['86510000','86472000']:
        c=next(c for c in ctx[2]['controls'] if c['code']==code);rr=[r for r in c['recent_rows'] if r.get('flow_m3s') is not None and m.hms.utc(r['time_utc']) in lookup]
        obs[code]=(np.array([lookup[m.hms.utc(r['time_utc'])] for r in rr]),np.array([r['flow_m3s'] for r in rr]))
    ii,o=obs['86510000'];ji,jo=obs['86472000'];oi=int(np.argmax(o));crest=axis[ii[oi]];ri=np.array([j for j,i in enumerate(ii) if 0<=(crest-axis[i]).total_seconds()<=24*3600]);fi=np.array([j for j,i in enumerate(ii) if axis[i]>crest]);seed=m.load(m.OUT/'selected_parameters.json');rows=[]
    for n,(pcl,ptc,pr,jw) in enumerate([(1.,5.,12.,.2),(3.,20.,50.,.1),(.5,15.,25.,.35),(1.,4.,5.,.0)]):
        start=[seed[k] for k in m.PARAMS]+[pcl,ptc,pr]
        def params(x):return dict(zip(KEYS,map(float,x)))
        def residual(x):
            jj,q=simulate(params(x));err=(q[ii]-o)/np.std(o);je=(jj[ji]-jo)/np.std(jo);weights=np.sqrt(1+1000/np.maximum(o,500))
            return np.r_[err*weights,je*jw,(q[ii[oi]]/max(o)-1)*12,(q[ii[oi]+4]-q[ii[oi]-4])/max(o)*5]
        result=least_squares(residual,start,bounds=BOUNDS,max_nfev=100,diff_step=.002,ftol=1e-7,xtol=1e-7)
        p=params(result.x);jj,q=simulate(p);err=q[ii]-o;je=jj[ji]-jo;peak=int(ii[0]+np.argmax(q[ii[0]:ii[-1]+1]));stats=dict(NSE=float(1-(err@err)/np.sum((o-o.mean())**2)),peak_error_pct=float(100*(q[peak]/max(o)-1)),peak_time_h=(axis[peak]-crest).total_seconds()/3600,
            bias_pct=float(100*err.sum()/o.sum()),rise_NMAE=float(np.abs(err[ri]).sum()/o[ri].sum()),recession_NMAE=float(np.abs(err[fi]).sum()/o[fi].sum()),JJ_partial_NSE=float(1-(je@je)/np.sum((jo-jo.mean())**2)))
        objective=5*(1-stats['NSE'])+stats['rise_NMAE']+stats['recession_NMAE']+.8*abs(stats['peak_error_pct'])/100+.04*abs(stats['peak_time_h'])
        row=dict(parameters=p,proxy_metrics=stats,objective=objective,upstream_weight=jw,proxy_only=True,evaluations=result.nfev);rows.append(row)
        m.save(m.OUT/'response_screening.json',dict(candidates=rows,selected=min(rows,key=lambda r:r['objective'])));m.save(m.OUT/'response_selected_parameters.json',min(rows,key=lambda r:r['objective'])['parameters']);print(json.dumps(row),flush=True)

if __name__=='__main__':main()
