import numpy as np,json
from datetime import timedelta
from scipy.optimize import least_squares
import calibrate_estrela_may2024 as m
from search_mucum_may2024 import clark,linear
ctx=m.prepare();dt=.1;times=ctx[0];axis=[times[0]+timedelta(hours=i*dt) for i in range((len(times)-1)*10+1)];lookup={t:i for i,t in enumerate(axis)};n=len(axis);days=np.arange(n)*dt/24;source=np.interp(np.arange(n)*dt,np.arange(len(times)),ctx[1]);fine={z:np.r_[0,np.repeat(np.array(ctx[2][z][1:])/10,10)] for z in m.ZONES}
r=next(c for c in ctx[4]['controls'] if c['code']=='86879300')['recent_rows'];rr=[r for r in r if r['flow_m3s'] is not None];ii=np.array([lookup[m.hms.utc(r['time_utc'])] for r in rr]);o=np.array([r['flow_m3s'] for r in rr]);bi=np.array([lookup[m.hms.utc(t)] for t in ctx[6]['low_stage_constraint']['times_utc']]);bound=ctx[6]['low_stage_constraint']['Q_upper_bound_m3s'];oi=np.argmax(o)
def sim(p):
 out=[]
 for z,g in zip(m.ZONES,m.GROUPS):
  available=np.maximum(np.cumsum(fine[z])-p['initial_'+g],0);post=np.diff(np.r_[0,available]);perc=np.minimum(post,p['loss_'+g]*dt);q=clark(post-perc,ctx[3][z],p['tc_'+g],p['r_'+g],dt)+p['baseflow_specific']*ctx[3][z]*p['recession']**days;gw=perc*ctx[3][z]/(3.6*dt)*p['fraction_'+g]
  for _ in range(p['gw_steps']):gw=linear(gw,p['gw_k_'+g],dt)
  out.append(q+gw)
 q=linear(source,p['k_up']*5.108/m.hms.GROUP_LENGTH['g2'],dt)+out[0];q=linear(q,p['k_up']*12.666/m.hms.GROUP_LENGTH['g2'],dt)+out[1];q=linear(q,p['k_down']*35.113/m.hms.GROUP_LENGTH['g3'],dt)+out[2];q=linear(q,p['k_down']*5.139/m.hms.GROUP_LENGTH['g3'],dt)+out[3];q=linear(q,p['k_down']*10.85/m.hms.GROUP_LENGTH['g3'],dt)+out[4];return linear(q,p['k_down']*1.472/m.hms.GROUP_LENGTH['g3'],dt)+out[5]
rows=[]
for steps in [2,4,6,8]:
 seed=dict(m.SEED if not rows else min(rows,key=lambda r:r['cost'])['parameters']);old=seed['gw_steps'];seed['gw_steps']=steps
 for g in ['guapore','forqueta','residual']:seed['gw_k_'+g]*=old/steps
 def params(x):p=dict(seed);p.update(zip(m.KEYS,map(float,x)));return p
 def residual(x):
  q=sim(params(x));e=(q[ii]-o)/np.std(o);return np.r_[e*np.sqrt(1+1000/np.maximum(o,1000)),np.maximum(0,q[bi]/bound-1)*3,(q[ii[oi]]/max(o)-1)*12,(q[ii[oi]+5]-q[ii[oi]-5])/max(o)*12,np.mean(e)*5]
 fit=least_squares(residual,[seed[k] for k in m.KEYS],bounds=(m.LOW,m.HIGH),max_nfev=200,diff_step=.002);p=params(fit.x);q=sim(p);e=q[ii]-o;peak=np.argmax(q);stats=dict(NSE=float(1-e@e/np.sum((o-o.mean())**2)),peak_error_pct=float(100*(q[peak]/max(o)-1)),peak_time_h=(axis[peak]-axis[ii[oi]]).total_seconds()/3600,bias_pct=float(100*sum(e)/sum(o)),stage_bound_exceedance=float(max(np.maximum(0,q[bi]/bound-1))));row=dict(parameters=p,proxy_metrics=stats,cost=float(sum(residual(fit.x)**2)),proxy_only=True);rows.append(row);m.save(m.OUT/'screening.json',rows);m.save(m.OUT/'selected_parameters.json',min(rows,key=lambda r:r['cost'])['parameters']);print(json.dumps(row),flush=True)
