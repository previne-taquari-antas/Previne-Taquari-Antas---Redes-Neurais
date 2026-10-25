#!/usr/bin/env python3
"""Bounded timing refinement after antecedent-state calibration."""
import json
import numpy as np
import calibrate_mucum_may2024 as m
from search_mucum_may2024 import engine

def main():
    ctx=m.prepare();axis,simulate=engine(ctx);lookup={t:i for i,t in enumerate(axis)};c=next(c for c in ctx[2]['controls'] if c['code']=='86510000');rows=[r for r in c['recent_rows'] if r.get('flow_m3s') is not None and m.hms.utc(r['time_utc']) in lookup]
    ii=np.array([lookup[m.hms.utc(r['time_utc'])] for r in rows]);o=np.array([r['flow_m3s'] for r in rows]);crest=axis[ii[int(np.argmax(o))]];ri=np.array([j for j,i in enumerate(ii) if 0<=(crest-axis[i]).total_seconds()<=86400]);fi=np.array([j for j,i in enumerate(ii) if axis[i]>crest]);tests=[]
    starts=m.load(m.OUT/'initial_state_screening.json')['candidates'][:2]
    for start in starts:
        seed=start['parameters']
        for dk in np.arange(-2.,.251,.25):
            for dtc in [-.5,0.,.5]:
                for rr in [.97,1.,1.03]:
                    for loss in [.98,1.,1.02]:
                        p=dict(seed,routing_k=max(.75,seed['routing_k']+float(dk)),tc_up=max(.5,seed['tc_up']+dtc),r_up=seed['r_up']*rr,loss_up=seed['loss_up']*loss)
                        jj,q=simulate(p);e=q[ii]-o;peak=int(ii[0]+np.argmax(q[ii[0]:ii[-1]+1]));metrics=dict(NSE=float(1-(e@e)/np.sum((o-o.mean())**2)),peak_error_pct=float(100*(q[peak]/max(o)-1)),peak_time_h=(axis[peak]-crest).total_seconds()/3600,bias_pct=float(100*e.sum()/o.sum()),rise_NMAE=float(np.abs(e[ri]).sum()/o[ri].sum()),recession_NMAE=float(np.abs(e[fi]).sum()/o[fi].sum()))
                        if abs(metrics['peak_time_h'])>.5 or abs(metrics['peak_error_pct'])>3 or metrics['NSE']<.969 or abs(metrics['bias_pct'])>3:continue
                        score=5*(1-metrics['NSE'])+metrics['rise_NMAE']+metrics['recession_NMAE']+abs(metrics['peak_error_pct'])/100+.05*abs(metrics['peak_time_h'])
                        tests.append(dict(parameters=p,proxy_metrics=metrics,objective=score,proxy_only=True))
    tests.sort(key=lambda r:r['objective'])
    if not tests:
        m.save(m.OUT/'phase_screening.json',dict(successful_candidates=0,selected=None,constraint='NSE >=0.969, abs peak error <=3%, abs timing <=0.5h, abs bias <=3%',interpretation='No timing-only alternative superseded the retained complete-event calibration.'));return
    m.save(m.OUT/'phase_screening.json',dict(successful_candidates=len(tests),top_candidates=tests[:10],selected=tests[0],constraint='NSE >=0.969, abs peak error <=3%, abs timing <=0.5h, abs bias <=3%'))
    m.save(m.OUT/'phase_selected_parameters.json',tests[0]['parameters']);print(json.dumps(tests[0]),flush=True)

if __name__=='__main__':main()
