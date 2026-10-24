#!/usr/bin/env python3
"""Separate Carreiro and lower-residual responses; constant event parameters.
Observed rain, flow, timestamps and catchment areas are never optimized.
"""
import json
import numpy as np
from scipy.optimize import least_squares
import calibrate_mucum_may2024 as m
from search_mucum_may2024 import engine
from refine_mucum_may_initial_state import KEYS as OLDKEYS

KEYS=OLDKEYS+['loss_carreiro','tc_carreiro','r_carreiro','initial_carreiro']
LO=[.02,.5,.3,.02,.5,.3,.001,.85,.6,.02,.5,.3,0,0,0,.02,.5,.3,0]
HI=[12,50,100,12,36,70,.15,.9999,12,12,70,150,180,180,180,12,50,100,180]

def main():
 ctx=m.prepare();axis,simulate=engine(ctx);lookup={t:i for i,t in enumerate(axis)};obs={}
 for code in ['86510000','86472000']:
  c=next(c for c in ctx[2]['controls'] if c['code']==code);rr=[r for r in c['recent_rows'] if r.get('flow_m3s') is not None and m.hms.utc(r['time_utc']) in lookup]
  obs[code]=(np.array([lookup[m.hms.utc(r['time_utc'])] for r in rr]),np.array([r['flow_m3s'] for r in rr]))
 ii,o=obs['86510000'];ji,jo=obs['86472000'];oi=int(np.argmax(o));crest=axis[ii[oi]];ri=np.array([j for j,i in enumerate(ii) if 0<=(crest-axis[i]).total_seconds()<=24*3600]);fi=np.array([j for j,i in enumerate(ii) if axis[i]>crest]);second=np.array([j for j,i in enumerate(ii) if axis[i].day in (4,5,6) and axis[i].month==5]);rows=[]
 previous=m.load(m.OUT/'previous_accepted_selection.json')['parameters']
 starts=[(previous,1.,.15,1.),(previous,2.,.15,1.),(previous,3.,.1,1.),(previous,2.,.3,2.)]
 for n,(seed,fallweight,jweight,secondweight) in enumerate(starts):
  p=dict(seed);p.update(loss_carreiro=seed['loss_down'],tc_carreiro=seed['tc_down'],r_carreiro=seed['r_down'],initial_carreiro=seed['initial_down'])
  if n and rows:p=rows[-1]['parameters']
  def residual(x):
   jj,q=simulate(dict(zip(KEYS,x)));err=(q[ii]-o)/np.std(o);je=(jj[ji]-jo)/np.std(jo);weights=np.sqrt(1+1000/np.maximum(o,500));weights[fi]*=fallweight;weights[second]*=secondweight
   return np.r_[err*weights,je*jweight,(q[ii[oi]]/max(o)-1)*14,(q[ii[oi]+4]-q[ii[oi]-4])/max(o)*12]
  result=least_squares(residual,[p[k] for k in KEYS],bounds=(LO,HI),max_nfev=350,diff_step=.001,ftol=1e-8,xtol=1e-8)
  p=dict(zip(KEYS,map(float,result.x)));jj,q=simulate(p);err=q[ii]-o;je=jj[ji]-jo;peak=int(ii[0]+np.argmax(q[ii[0]:ii[-1]+1]));stats=dict(NSE=float(1-(err@err)/np.sum((o-o.mean())**2)),peak_error_pct=float(100*(q[peak]/max(o)-1)),peak_time_h=(axis[peak]-crest).total_seconds()/3600,bias_pct=float(100*err.sum()/o.sum()),rise_NMAE=float(np.abs(err[ri]).sum()/o[ri].sum()),recession_NMAE=float(np.abs(err[fi]).sum()/o[fi].sum()),second_NMAE=float(np.abs(err[second]).sum()/o[second].sum()),JJ_partial_NSE=float(1-(je@je)/np.sum((jo-jo.mean())**2)))
  objective=5*(1-stats['NSE'])+stats['rise_NMAE']+2*stats['recession_NMAE']+abs(stats['peak_error_pct'])/100+.05*abs(stats['peak_time_h'])
  row=dict(parameters=p,proxy_metrics=stats,objective=objective,proxy_only=True,evaluations=result.nfev,start_index=n);rows.append(row)
  m.save(m.OUT/'spatial_screening.json',dict(candidates=rows,selected=min(rows,key=lambda r:r['objective'])));m.save(m.OUT/'spatial_selected_parameters.json',min(rows,key=lambda r:r['objective'])['parameters']);print(json.dumps(row),flush=True)
if __name__=='__main__':main()
