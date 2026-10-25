#!/usr/bin/env python3
"""Deficit soil state and delayed percolation: saturation/interflow hypothesis."""
import json
import numpy as np
from scipy.optimize import least_squares
import calibrate_mucum_may2024 as m
from refine_mucum_may_spatial import KEYS as BASEKEYS,LO as BASELO,HI as BASEHI
from refine_mucum_may_wetness import setup

def main():
 ctx,axis,simulate,obs=setup();ii,o=obs['86510000'];ji,jo=obs['86472000'];oi=int(np.argmax(o));crest=axis[ii[oi]];ri=np.array([j for j,i in enumerate(ii) if 0<=(crest-axis[i]).total_seconds()<=86400]);fi=np.array([j for j,i in enumerate(ii) if axis[i]>crest]);second=np.array([j for j,i in enumerate(ii) if axis[i].month==5 and axis[i].day in (4,5,6)]);seed=m.load(m.OUT/'spatial_screening.json')['candidates'][0]['parameters'];rows=[]
 keys=BASEKEYS+['gw_k','gw_fraction','gw_k_up','gw_fraction_up','gw_k_carreiro','gw_fraction_carreiro'];lo=BASELO+[1,.0,1,.0,1,.0];hi=BASEHI+[200,1.,200,1.,200,1.]
 for n,(gwk,gfrac,fallweight,steps) in enumerate([(18,.5,1.,2),(36,.8,1.5,2),(12,.5,1.,3),(24,.4,1.,1),(48,.8,2.,3)]):
  p=dict(seed);p.update(gw_k=gwk,gw_fraction=gfrac,gw_k_up=gwk,gw_fraction_up=gfrac,gw_k_carreiro=gwk,gw_fraction_carreiro=gfrac)
  if n and rows:p.update(min(rows,key=lambda r:r['objective'])['parameters'])
  def params(x):
   p=dict(seed);p.update(zip(keys,map(float,x)));p['loss_method']='DeficitConstantLinear';p['gw_steps']=steps;return p
  def residual(x):
   jj,q=simulate(params(x));err=(q[ii]-o)/np.std(o);weights=np.sqrt(1+700/np.maximum(o,500));weights[fi]*=fallweight
   return np.r_[err*weights,(jj[ji]-jo)/np.std(jo)*.15,(q[ii[oi]]/max(o)-1)*14,(q[ii[oi]+4]-q[ii[oi]-4])/max(o)*12]
  r=least_squares(residual,[p[k] for k in keys],bounds=(lo,hi),max_nfev=250,diff_step=.002,ftol=1e-8,xtol=1e-8)
  p=params(r.x);jj,q=simulate(p);err=q[ii]-o;je=jj[ji]-jo;peak=int(ii[0]+np.argmax(q[ii[0]:ii[-1]+1]));stats=dict(NSE=float(1-(err@err)/np.sum((o-o.mean())**2)),peak_error_pct=float(100*(q[peak]/max(o)-1)),peak_time_h=(axis[peak]-crest).total_seconds()/3600,bias_pct=float(100*err.sum()/o.sum()),rise_NMAE=float(np.abs(err[ri]).sum()/o[ri].sum()),recession_NMAE=float(np.abs(err[fi]).sum()/o[fi].sum()),second_NMAE=float(np.abs(err[second]).sum()/o[second].sum()),JJ_partial_NSE=float(1-(je@je)/np.sum((jo-jo.mean())**2)))
  objective=5*(1-stats['NSE'])+stats['rise_NMAE']+2*stats['recession_NMAE']+abs(stats['peak_error_pct'])/100+.05*abs(stats['peak_time_h']);row=dict(parameters=p,proxy_metrics=stats,objective=objective,proxy_only=True,evaluations=r.nfev,start_index=n);rows.append(row);m.save(m.OUT/'soil_storage_screening.json',dict(candidates=rows,selected=min(rows,key=lambda r:r['objective'])));m.save(m.OUT/'soil_storage_selected_parameters.json',min(rows,key=lambda r:r['objective'])['parameters']);print(json.dumps(row),flush=True)
if __name__=='__main__':main()
