#!/usr/bin/env python3
"""Spatial transit-time dispersion and explicit second-crest calibration.
Constant event parameters; no rainfall, observation or clock adjustment.
"""
import json
from datetime import datetime,timezone
import numpy as np
from scipy.optimize import least_squares
import calibrate_mucum_may2024 as m
from search_mucum_may2024 import engine
from refine_mucum_may_spatial import KEYS as BKEYS,LO as BLO,HI as BHI

def main():
 ctx=m.prepare();axis,simulate=engine(ctx,dt=.1);lookup={t:i for i,t in enumerate(axis)};obs={}
 for code in ['86510000','86472000']:
  c=next(c for c in ctx[2]['controls'] if c['code']==code);rr=[r for r in c['recent_rows'] if r.get('flow_m3s') is not None and m.hms.utc(r['time_utc']) in lookup];obs[code]=(np.array([lookup[m.hms.utc(r['time_utc'])] for r in rr]),np.array([r['flow_m3s'] for r in rr]))
 ii,o=obs['86510000'];ji,jo=obs['86472000'];oi=int(np.argmax(o));crest=axis[ii[oi]];ri=np.array([j for j,i in enumerate(ii) if 0<=(crest-axis[i]).total_seconds()<=86400]);fi=np.array([j for j,i in enumerate(ii) if axis[i]>crest]);second=np.array([j for j,i in enumerate(ii) if datetime(2024,5,4,tzinfo=timezone.utc)<=axis[i]<datetime(2024,5,7,tzinfo=timezone.utc)]);s2=int(second[np.argmax(o[second])]);rows=[]
 seed=m.load(m.OUT/'second_wave_screening.json')['candidates'][1]['parameters'];keys=BKEYS+['gw_k','gw_fraction','gw_k_up','gw_fraction_up','gw_k_carreiro','gw_fraction_carreiro'];lo=BLO+[1,0,1,0,1,0];hi=BHI+[200,1,200,1,200,1]
 configurations=[(6,8,8,30.),(6,8,6,60.),(6,8,4,100.),(6,10,6,60.)]
 for n,(nu,nc,npra,fallweight) in enumerate(configurations):
  p=dict(seed);p.update(gw_steps_up=nu,gw_steps_carreiro=nc,gw_steps_prata=npra);p['gw_k_up']*=6/nu;p['gw_k_carreiro']*=8/nc
  # Prata and lower residuals originally share gw_k; separate Prata's mean lag
  # when its cascade order changes, without altering the rainfall support.
  p['gw_k_prata']=seed['gw_k_prata']*8/npra
  localkeys=keys+['gw_k_prata'];locallo=lo+[1];localhi=hi+[200]
  def params(x):r=dict(p);r.update(zip(localkeys,map(float,x)));return r
  def residual(x):
   jj,q=simulate(params(x));err=(q[ii]-o)/np.std(o);weights=np.sqrt(1+700/np.maximum(o,500));weights[fi]*=1.25;weights[second]*=1.15
   return np.r_[err*weights,(jj[ji]-jo)/np.std(jo)*.15,(q[ii[oi]]/max(o)-1)*45,(q[ii[oi]+5]-q[ii[oi]-5])/max(o)*30,(q[ii[s2]]/o[s2]-1)*12,(q[ii[s2]+5]-q[ii[s2]-5])/o[s2]*fallweight,err.sum()/len(o)*25]
  fit=least_squares(residual,[p[k] for k in localkeys],bounds=(locallo,localhi),max_nfev=130,diff_step=.001,ftol=1e-8,xtol=1e-8)
  p=params(fit.x);jj,q=simulate(p);err=q[ii]-o;je=jj[ji]-jo;peak=ii[0]+np.argmax(q[ii[0]:ii[-1]+1]);b2=ii[second[0]]+np.argmax(q[ii[second[0]]:ii[second[-1]]+1]);stats=dict(NSE=float(1-(err@err)/np.sum((o-o.mean())**2)),KGE=float(1-np.linalg.norm([np.corrcoef(q[ii],o)[0,1]-1,np.std(q[ii])/np.std(o)-1,np.mean(q[ii])/np.mean(o)-1])),peak_error_pct=float(100*(q[peak]/max(o)-1)),peak_time_h=(axis[peak]-crest).total_seconds()/3600,bias_pct=float(100*err.sum()/o.sum()),rise_NMAE=float(np.abs(err[ri]).sum()/o[ri].sum()),recession_NMAE=float(np.abs(err[fi]).sum()/o[fi].sum()),second_NMAE=float(np.abs(err[second]).sum()/o[second].sum()),second_peak_error_pct=float(100*(q[b2]/o[s2]-1)),second_peak_time_h=(axis[b2]-axis[ii[s2]]).total_seconds()/3600,JJ_partial_NSE=float(1-(je@je)/np.sum((jo-jo.mean())**2)))
  objective=15*(1-stats['NSE'])+stats['rise_NMAE']+2*stats['recession_NMAE']+stats['second_NMAE']+abs(stats['peak_error_pct'])/100+abs(stats['second_peak_error_pct'])/100+.02*abs(stats['peak_time_h'])+.02*abs(stats['second_peak_time_h']);row=dict(parameters=p,proxy_metrics=stats,objective=objective,proxy_only=True,proxy_dt_minutes=6,evaluations=fit.nfev,start_index=n);rows.append(row);m.save(m.OUT/'second_wave_balance_screening.json',dict(candidates=rows,selected=min(rows,key=lambda r:r['objective'])));m.save(m.OUT/'second_wave_balance_selected_parameters.json',min(rows,key=lambda r:r['objective'])['parameters']);print(json.dumps(row),flush=True)
if __name__=='__main__':main()
