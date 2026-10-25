"""Refine spatial soil response and native Muskingum routing, fixed event inputs."""
import json
from datetime import timedelta
import numpy as np
from scipy.signal import lfilter
from scipy.optimize import least_squares
import calibrate_estrela_may2024 as m
from search_mucum_may2024 import clark,linear

def engine(ctx,dt=.05):
 times=ctx[0];steps=round(1/dt);axis=[times[0]+timedelta(hours=i*dt) for i in range((len(times)-1)*steps+1)];n=len(axis);days=np.arange(n)*dt/24;source=np.interp(np.arange(n)*dt,np.arange(len(times)),ctx[1]);fine={z:np.r_[0,np.repeat(np.array(ctx[2][z][1:])/steps,steps)] for z in m.ZONES}
 def route(q,k,x):
  count=m.hms.muskingum_steps(k,x,3,1);kk=k/count;den=2*kk*(1-x)+dt;a=(dt-2*kk*x)/den;b=(dt+2*kk*x)/den;c=(2*kk*(1-x)-dt)/den
  for _ in range(count):q=lfilter([a,b],[1,-c],q,zi=[q[0]*(1-a)])[0]
  return q
 def sim(p):
  out=[]
  for z,group in zip(m.ZONES,m.GROUPS):
   g=p.get('zone_groups',{}).get(z,group);available=np.maximum(np.cumsum(fine[z])-p['initial_'+g],0);post=np.diff(np.r_[0,available]);perc=np.minimum(post,p['loss_'+g]*dt);q=clark(post-perc,ctx[3][z],p['tc_'+g],p['r_'+g],dt)+p['baseflow_specific']*ctx[3][z]*p['recession']**days;gw=perc*ctx[3][z]/(3.6*dt)*p['fraction_'+g]
   for _ in range(p.get('gw_steps_'+g,p['gw_steps'])):gw=linear(gw,p['gw_k_'+g],dt)
   out.append(q+gw)
  x=p.get('routing_x',0);q=route(source,p['k_up']*5.108/m.hms.GROUP_LENGTH['g2'],x)+out[0];q=route(q,p['k_up']*12.666/m.hms.GROUP_LENGTH['g2'],x)+out[1];q=route(q,p['k_down']*35.113/m.hms.GROUP_LENGTH['g3'],x)+out[2];q=route(q,p['k_down']*5.139/m.hms.GROUP_LENGTH['g3'],x)+out[3];q=route(q,p['k_down']*10.85/m.hms.GROUP_LENGTH['g3'],x)+out[4];return route(q,p['k_down']*1.472/m.hms.GROUP_LENGTH['g3'],x)+out[5]
 return axis,sim

def main():
 ctx=m.prepare();axis,sim=engine(ctx);lookup={t:i for i,t in enumerate(axis)};rr=next(c for c in ctx[4]['controls'] if c['code']=='86879300')['recent_rows'];rr=[r for r in rr if r['flow_m3s'] is not None];ii=np.array([lookup[m.hms.utc(r['time_utc'])] for r in rr]);o=np.array([r['flow_m3s'] for r in rr]);bi=np.array([lookup[m.hms.utc(t)] for t in ctx[6]['low_stage_constraint']['times_utc']]);bound=ctx[6]['low_stage_constraint']['Q_upper_bound_m3s'];oi=np.argmax(o);early=np.array([j for j,i in enumerate(ii) if axis[i]<m.hms.utc('2024-05-01T00:00Z')]);tail=np.array([j for j,i in enumerate(ii) if axis[i]>=m.hms.utc('2024-05-07T00:00Z')]);fall=np.array([j for j,i in enumerate(ii) if i>ii[oi]]);consecutive=np.array([j for j in range(len(ii)-1) if ii[j+1]-ii[j]==20]);rows=[];seed=m.load(m.OUT/'previous_selection.json')['parameters']
 keys=m.KEYS+[v+'_lower' for v in ['initial','loss','tc','r','gw_k','fraction']];lo=m.LOW+[0,.02,.3,.3,.3,0];hi=m.HIGH+[180,15,60,100,100,1]
 for n in [0,1,2,3,4,5]:
  x=0
  p=dict(seed);p.update(routing_x=x,zone_groups={z:'lower' for z in m.ZONES[2:] if z!='BRANCH_86746000'})
  for v in ['initial','loss','tc','r','gw_k','fraction']:p[v+'_lower']=p[v+'_residual']
  if n%2==1 and rows:p.update(rows[-1]['parameters']);p['routing_x']=0
  elif n==0:p.update(m.load(m.OUT/'refinement_screening.json')[0]['parameters'])
  p['recession']=.7
  if n in [0,2,4]:
   p.update(tc_guapore=[8,8,24,24,40,40][n],r_guapore=12,tc_forqueta=[24,24,12,12,6,6][n],r_forqueta=20,k_down=6,gw_steps=4)
  for g in ['guapore','forqueta','residual','lower']:p['gw_k_'+g]=6
  lo[-1-6]=.3
  bounds_hi=list(hi);bounds_hi[m.KEYS.index('k_down')]=12 if x==.3 else 18
  def params(a):r=dict(p);r.update(zip(keys,map(float,a)));return r
  def residual(a):
   q=sim(params(a));e=(q[ii]-o)/np.std(o);weights=3*np.std(o)/o;weights[early]*=1.4;weights[tail]*=1.4
   de=(q[ii[consecutive+1]]-q[ii[consecutive]]-(o[consecutive+1]-o[consecutive]))/np.std(np.diff(o))
   return np.r_[e*weights,np.maximum(0,q[bi]/bound-1.005)*8,(q[ii[oi]]/max(o)-1)*35,(q[ii[oi]+10]-q[ii[oi]-10])/max(o)*100,np.mean(e)*10,de*.2]
  fit=least_squares(residual,[p[k] for k in keys],bounds=(lo,bounds_hi),max_nfev=160,diff_step=.001,ftol=1e-8,xtol=1e-8);p=params(fit.x);q=sim(p);e=q[ii]-o;pk=int(np.argmax(q));stats=dict(NSE=float(1-e@e/np.sum((o-o.mean())**2)),peak_error_pct=float(100*(q[pk]/max(o)-1)),peak_time_h=(axis[pk]-axis[ii[oi]]).total_seconds()/3600,bias_pct=float(100*e.sum()/o.sum()),early_NMAE=float(abs(e[early]).sum()/o[early].sum()),tail_NMAE=float(abs(e[tail]).sum()/o[tail].sum()),fall_NMAE=float(abs(e[fall]).sum()/o[fall].sum()),maximum_relative_error_pct=float(max(abs(e)/o)*100),stage_bound_exceedance=float(max(np.maximum(0,q[bi]/bound-1))));row=dict(parameters=p,proxy_metrics=stats,cost=float(sum(residual(fit.x)**2)),proxy_only=True,dt_minutes=3,evaluations=fit.nfev);rows.append(row);m.save(m.OUT/'restart_screening.json',rows);m.save(m.OUT/'restart_parameters.json',min(rows,key=lambda r:r['cost'])['parameters']);print(json.dumps(row),flush=True)
if __name__=='__main__':main()
