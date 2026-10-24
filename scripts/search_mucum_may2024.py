#!/usr/bin/env python3
"""Screen May rainfall-runoff parameters; only native runs are deliverable fits.

Clark time-area and reservoir equations follow USACE technical documentation.
Native baseline comparison measures the approximation before optimization.
"""
import argparse,json
from pathlib import Path
from datetime import timedelta
import numpy as np
from scipy.signal import lfilter,fftconvolve
from scipy.optimize import differential_evolution
import calibrate_mucum_may2024 as model

def linear(q,k,dt):
    a=dt/(2*k+dt);b=(2*k-dt)/(2*k+dt)
    return lfilter([a,a],[1,-b],q,zi=[q[0]*(1-a)])[0]

def clark(excess,area,tc,r,dt):
    edge=np.minimum(np.arange(int(np.ceil(tc/dt))+1)*dt/tc,1.)
    cumulative=np.where(edge<=.5,1.414*edge**1.5,1-1.414*(1-edge)**1.5);cumulative[0]=0;cumulative[-1]=1
    ta=np.diff(cumulative);tail=np.pad(ta,(0,int(10*r/dt)+2));a=dt/(2*r+dt);b=(2*r-dt)/(2*r+dt)
    kernel=lfilter([a,a],[1,-b],tail);end=int(np.searchsorted(np.cumsum(kernel),.995))+1;kernel=kernel[:end];kernel/=kernel.sum()
    return fftconvolve(excess,kernel)[:len(excess)]*area/(3.6*dt)

def engine(context,dt=.25):
    times,rain,hydro,digest=context;steps=round(1/dt);axis=[times[0]+timedelta(hours=i*dt) for i in range((len(times)-1)*steps+1)]
    # PER-CUM ordinate at each original hour is interval-ending rainfall.
    fine={sid:np.r_[0,np.repeat(np.array(rain[sid][1:])/steps,steps)] for sid in model.ZONES}
    n=len(axis);days=np.arange(n)*dt/24
    def simulate(p):
        out=[]
        for i,sid in enumerate(model.ZONES):
            initial,loss,tc,r=model.local_params(p,i)
            group=['prata','up','carreiro','down','down'][i]
            if p.get('loss_method')=='GreenAmpt' or group in p.get('green_ampt_groups',[]):
                from refine_mucum_may_wetness import green_ampt
                excess=green_ampt(fine[sid],p['ks_'+group],p['suction_deficit_'+group],dt)
            elif p.get('loss_method')=='SCS':
                cn=p['cn_up' if i<2 else 'cn_down']
                if i==0:cn=p.get('cn_prata',cn)
                retention=25400/cn-254;rain_sum=np.cumsum(fine[sid]);effective=np.maximum(rain_sum-.2*retention,0);runoff=effective**2/(effective+retention);excess=np.diff(np.r_[0,runoff])
            else:
                available=np.maximum(np.cumsum(fine[sid])-initial,0);post=np.diff(np.r_[0,available]);excess=np.maximum(post-loss*dt,0)
            q=clark(excess,model.AREAS[i],tc,r,dt)+p['baseflow_specific']*model.AREAS[i]*p['recession']**days
            if p.get('loss_method')=='DeficitConstantLinear':
                percolation=np.minimum(post,loss*dt)*model.AREAS[i]/(3.6*dt)
                gw=percolation*p.get('gw_fraction_'+group,p['gw_fraction'])
                for layer in range(int(p.get('gw_steps_'+group,p.get('gw_steps',2)))):gw=linear(gw,p.get('gw_k_'+group,p['gw_k']),dt)
                q+=gw
            out.append(q)
        jj=out[0]+out[1];car=linear(jj,p['routing_k']*2.557/44.524,dt)+out[2];stz=linear(car,p['routing_k']*18.315/44.524,dt)+out[3];mu=linear(stz,p['routing_k']*23.652/44.524,dt)+out[4]
        return jj,mu
    return axis,simulate

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check-only',action='store_true');args=ap.parse_args();ctx=model.prepare();times,rain,hydro,digest=ctx
    axis,simulate=engine(ctx);lookup={t:i for i,t in enumerate(axis)};obs={}
    for code in ['86510000','86472000']:
        c=next(c for c in hydro['controls'] if str(c['code'])==code);rr=[r for r in c['recent_rows'] if r.get('flow_m3s') is not None and model.hms.utc(r['time_utc']) in lookup]
        ii=np.array([lookup[model.hms.utc(r['time_utc'])] for r in rr]);qq=np.array([r['flow_m3s'] for r in rr]);obs[code]=(ii,qq)
    ii,o=obs['86510000'];ji,jo=obs['86472000'];crest=axis[ii[int(np.argmax(o))]]
    rise=np.array([j for j,i in enumerate(ii) if 0<=(crest-axis[i]).total_seconds()<=24*3600]);fall=np.array([j for j,i in enumerate(ii) if axis[i]>crest])
    def metrics(jj,mu):
        q=mu[ii];err=q-o;peak=int(ii[0]+np.argmax(mu[ii[0]:ii[-1]+1]));jerr=jj[ji]-jo
        return dict(NSE=float(1-(err@err)/np.sum((o-o.mean())**2)),KGE=float(1-np.linalg.norm([np.corrcoef(q,o)[0,1]-1,np.std(q)/np.std(o)-1,np.mean(q)/np.mean(o)-1])),
            peak_error_pct=float(100*(mu[peak]/max(o)-1)),peak_time_h=(axis[peak]-crest).total_seconds()/3600,bias_pct=float(100*err.sum()/o.sum()),
            rise_NMAE=float(np.abs(err[rise]).sum()/o[rise].sum()),recession_NMAE=float(np.abs(err[fall]).sum()/o[fall].sum()),
            JJ_partial_NSE=float(1-(jerr@jerr)/np.sum((jo-jo.mean())**2)),JJ_partial_NMAE=float(np.abs(jerr).sum()/jo.sum()))
    native=model.load(model.OUT/'baseline.json');by=model.hms.read_output_csv(model.ROOT/native['project']/'hec_output_values.csv');ref={t:q for t,q in by['J_86510000']};jj,mu=simulate(model.SEED)
    error=np.array([mu[i]-ref[t] for i,t in enumerate(axis)]);audit=dict(proxy_dt_minutes=15,max_difference_vs_native_baseline_m3s=float(max(abs(error))),RMSE_vs_native_baseline_m3s=float(np.sqrt(np.mean(error**2))),proxy_baseline_metrics=metrics(jj,mu),native_baseline_metrics=native['metrics']['86510000'])
    model.save(model.OUT/'proxy_comparison.json',audit);print(json.dumps(audit),flush=True)
    if args.check_only:return
    def objective(x):
        p=dict(zip(model.PARAMS,x));jj,mu=simulate(p);m=metrics(jj,mu)
        return 6*(1-m['NSE'])+.9*(1-m['KGE'])+.9*abs(m['peak_error_pct'])/100+.025*abs(m['peak_time_h'])+.7*abs(m['bias_pct'])/100+m['rise_NMAE']+.5*m['recession_NMAE']+.3*m['JJ_partial_NMAE']
    bounds=[(.1,6),(1,36),(1,60),(.1,8),(.5,24),(.5,40),(.002,.12),(.85,.999),(.75,8)]
    rows=[]
    for seed in [20240502,20240503]:
        r=differential_evolution(objective,bounds,seed=seed,popsize=10,maxiter=180,tol=1e-6,polish=False)
        p=dict(zip(model.PARAMS,map(float,r.x)));jj,mu=simulate(p);row=dict(parameters=p,proxy_metrics=metrics(jj,mu),objective=float(r.fun),evaluations=r.nfev,proxy_only=True,input_sha256=digest)
        rows.append(row);model.save(model.OUT/'screening.json',dict(candidates=rows,selected=min(rows,key=lambda r:r['objective'])))
        model.save(model.OUT/'selected_parameters.json',min(rows,key=lambda r:r['objective'])['parameters']);print(json.dumps(row),flush=True)

if __name__=='__main__':main()
