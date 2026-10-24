#!/usr/bin/env python3
"""Refine soil-storage candidate while guarding the observed main crest."""
import json
import numpy as np
from scipy.optimize import least_squares
import calibrate_mucum_may2024 as m
from refine_mucum_may_spatial import KEYS as BKEYS,LO as BLO,HI as BHI
from refine_mucum_may_wetness import setup

def main():
 ctx,axis,simulate,obs=setup();ii,o=obs['86510000'];ji,jo=obs['86472000'];oi=int(np.argmax(o));crest=axis[ii[oi]];ri=np.array([j for j,i in enumerate(ii) if 0<=(crest-axis[i]).total_seconds()<=86400]);fi=np.array([j for j,i in enumerate(ii) if axis[i]>crest]);second=np.array([j for j,i in enumerate(ii) if axis[i].month==5 and axis[i].day in (4,5,6)]);candidates=m.load(m.OUT/'soil_storage_screening.json')['candidates'];rows=[]
 keys=BKEYS+['gw_k','gw_fraction','gw_k_up','gw_fraction_up','gw_k_carreiro','gw_fraction_carreiro'];lo=BLO+[1,0,1,0,1,0];hi=BHI+[200,1,200,1,200,1]
 for n,(index,weight,fallweight) in enumerate([(2,40,1.2),(2,70,1.5),(4,50,1.8)]):
  seed=candidates[index]['parameters']
  def params(x):p=dict(seed);p.update(zip(keys,map(float,x)));return p
  def residual(x):
   jj,q=simulate(params(x));err=(q[ii]-o)/np.std(o);weights=np.sqrt(1+700/np.maximum(o,500));weights[fi]*=fallweight
   return np.r_[err*weights,(jj[ji]-jo)/np.std(jo)*.15,(q[ii[oi]]/max(o)-1)*weight,(q[ii[oi]+4]-q[ii[oi]-4])/max(o)*25]
  r=least_squares(residual,[seed[k] for k in keys],bounds=(lo,hi),max_nfev=200,diff_step=.001,ftol=1e-9,xtol=1e-9)
  p=params(r.x);jj,q=simulate(p);err=q[ii]-o;je=jj[ji]-jo;peak=int(ii[0]+np.argmax(q[ii[0]:ii[-1]+1]));stats=dict(NSE=float(1-(err@err)/np.sum((o-o.mean())**2)),peak_error_pct=float(100*(q[peak]/max(o)-1)),peak_time_h=(axis[peak]-crest).total_seconds()/3600,bias_pct=float(100*err.sum()/o.sum()),rise_NMAE=float(np.abs(err[ri]).sum()/o[ri].sum()),recession_NMAE=float(np.abs(err[fi]).sum()/o[fi].sum()),second_NMAE=float(np.abs(err[second]).sum()/o[second].sum()),JJ_partial_NSE=float(1-(je@je)/np.sum((jo-jo.mean())**2)))
  objective=5*(1-stats['NSE'])+stats['rise_NMAE']+2*stats['recession_NMAE']+abs(stats['peak_error_pct'])/100+.05*abs(stats['peak_time_h']);row=dict(parameters=p,proxy_metrics=stats,objective=objective,proxy_only=True,evaluations=r.nfev,start_index=n);rows.append(row);m.save(m.OUT/'soil_peak_screening.json',dict(candidates=rows,selected=min(rows,key=lambda r:r['objective'])));m.save(m.OUT/'soil_peak_selected_parameters.json',min(rows,key=lambda r:r['objective'])['parameters']);print(json.dumps(row),flush=True)
if __name__=='__main__':main()
