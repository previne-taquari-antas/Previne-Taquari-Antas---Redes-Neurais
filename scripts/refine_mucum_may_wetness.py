#!/usr/bin/env python3
"""Test progressive wetting with native-compatible Green-Ampt infiltration.
A=wetting-front suction * initial volumetric deficit: only the product is
identifiable from rainfall-runoff data. No soil measurements are asserted.
"""
import json
import numpy as np
from numba import njit
from scipy.optimize import least_squares
import calibrate_mucum_may2024 as m

@njit(cache=True)
def green_ampt(rain,ks,a,dt):
 out=np.zeros(len(rain));f=0.
 for j in range(len(rain)):
  amount=rain[j]
  if amount<=0:continue
  rate=amount/dt
  if rate<=ks:
   f+=amount;continue
  fp=ks*a/(rate-ks)
  if f+amount<=fp:
   f+=amount;continue
  start=max(fp,f);pond_time=max(0.,(fp-f)/rate);duration=dt-pond_time
  lo=start;hi=f+amount
  for k in range(35):
   mid=.5*(lo+hi);elapsed=(mid-start-a*np.log((mid+a)/(start+a)))/ks
   if elapsed>duration:hi=mid
   else:lo=mid
  fn=.5*(lo+hi);out[j]=max(0.,amount-(fn-f));f=fn
 return out

def setup():
 from search_mucum_may2024 import engine
 ctx=m.prepare();axis,simulate=engine(ctx);lookup={t:i for i,t in enumerate(axis)};obs={}
 for code in ['86510000','86472000']:
  c=next(c for c in ctx[2]['controls'] if c['code']==code);rr=[r for r in c['recent_rows'] if r.get('flow_m3s') is not None and m.hms.utc(r['time_utc']) in lookup];obs[code]=(np.array([lookup[m.hms.utc(r['time_utc'])] for r in rr]),np.array([r['flow_m3s'] for r in rr]))
 return ctx,axis,simulate,obs

def main():
 from refine_mucum_may_spatial import KEYS as ALLKEYS,LO,HI
 ctx,axis,simulate,obs=setup();ii,o=obs['86510000'];ji,jo=obs['86472000'];oi=int(np.argmax(o));crest=axis[ii[oi]];ri=np.array([j for j,i in enumerate(ii) if 0<=(crest-axis[i]).total_seconds()<=86400]);fi=np.array([j for j,i in enumerate(ii) if axis[i]>crest]);second=np.array([j for j,i in enumerate(ii) if axis[i].month==5 and axis[i].day in (4,5,6)])
 seed=m.load(m.OUT/'spatial_screening.json')['candidates'][0]['parameters'];rows=[]
 # Change infiltration only in lower zones first; then test all zones.
 for case,groups,fallweight in [('lower',['carreiro','down'],1.),('all',['prata','up','carreiro','down'],1.),('all_tail',['prata','up','carreiro','down'],1.7),('antas_lower',['up','carreiro','down'],1.)]:
  drop={'prata':['loss_prata','initial_prata'],'up':['loss_up','initial_up'],'carreiro':['loss_carreiro','initial_carreiro'],'down':['loss_down','initial_down']}
  excluded=sum([drop[g] for g in groups],[]);keys=[k for k in ALLKEYS if k not in excluded];lo=[LO[ALLKEYS.index(k)] for k in keys];hi=[HI[ALLKEYS.index(k)] for k in keys];p=dict(seed)
  for g in groups:
   keys+=['ks_'+g,'suction_deficit_'+g];lo+=[.005,.01];hi+=[10,500];p.update({'ks_'+g:.2 if g in ['up','prata'] else .8,'suction_deficit_'+g:100})
  if case=='all_tail' and rows:p.update(rows[-1]['parameters'])
  def params(x):
   r=dict(seed);r.update(zip(keys,map(float,x)));r['green_ampt_groups']=groups;return r
  def residual(x):
   jj,q=simulate(params(x));err=(q[ii]-o)/np.std(o);weights=np.sqrt(1+700/np.maximum(o,500));weights[fi]*=fallweight
   return np.r_[err*weights,(jj[ji]-jo)/np.std(jo)*.15,(q[ii[oi]]/max(o)-1)*14,(q[ii[oi]+4]-q[ii[oi]-4])/max(o)*12]
  r=least_squares(residual,[p[k] for k in keys],bounds=(lo,hi),max_nfev=230,diff_step=.002,ftol=1e-8,xtol=1e-8)
  p=params(r.x);jj,q=simulate(p);err=q[ii]-o;je=jj[ji]-jo;peak=int(ii[0]+np.argmax(q[ii[0]:ii[-1]+1]));stats=dict(NSE=float(1-(err@err)/np.sum((o-o.mean())**2)),peak_error_pct=float(100*(q[peak]/max(o)-1)),peak_time_h=(axis[peak]-crest).total_seconds()/3600,bias_pct=float(100*err.sum()/o.sum()),rise_NMAE=float(np.abs(err[ri]).sum()/o[ri].sum()),recession_NMAE=float(np.abs(err[fi]).sum()/o[fi].sum()),second_NMAE=float(np.abs(err[second]).sum()/o[second].sum()),JJ_partial_NSE=float(1-(je@je)/np.sum((jo-jo.mean())**2)))
  objective=5*(1-stats['NSE'])+stats['rise_NMAE']+2*stats['recession_NMAE']+abs(stats['peak_error_pct'])/100+.05*abs(stats['peak_time_h']);row=dict(case=case,parameters=p,proxy_metrics=stats,objective=objective,proxy_only=True,evaluations=r.nfev);rows.append(row);m.save(m.OUT/'wetness_screening.json',dict(candidates=rows,selected=min(rows,key=lambda r:r['objective'])));m.save(m.OUT/'wetness_selected_parameters.json',min(rows,key=lambda r:r['objective'])['parameters']);print(json.dumps(row),flush=True)
if __name__=='__main__':main()
