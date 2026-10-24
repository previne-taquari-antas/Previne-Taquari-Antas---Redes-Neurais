#!/usr/bin/env python3
"""Compare native May profiles on unchanged hourly observations and windows."""
from datetime import datetime,timezone
import json
import calibrate_mucum_may2024 as m

def main():
 ctx=m.prepare();window=dict(start_utc=ctx[0][0].isoformat(),end_utc=ctx[0][-1].isoformat());a=datetime(2024,5,4,tzinfo=timezone.utc);b=datetime(2024,5,7,tzinfo=timezone.utc);rows=[]
 for name,file in [('before','before_revision2_selection.json'),('full_event','selection.json'),('second_crest','secondary_crest_native.json')]:
  d=m.load(m.OUT/file);sim=m.ind.model(m.ROOT/d['project']/'hec_output_values.csv','86510000');pairs=m.ind.independent_pairs(sim,ctx[2],'86510000',window);stats=m.ind.metrics(pairs)
  for k in ['nse','kge','pbias_pct','rmse_m3s']:
   if abs(stats[k]-d['metrics']['86510000'][k])>1e-8:raise RuntimeError('Independent profile metric mismatch')
  p=[(t,o,q) for t,o,q in pairs if a<=t<b];obs=max(p,key=lambda r:r[1]);tp,qp=max(((t,q) for t,q in sim if a<=t<b),key=lambda r:r[1]);second=dict(pairs=len(p),NMAE=sum(abs(o-q) for t,o,q in p)/sum(o for t,o,q in p),peak_error_pct=100*(qp/obs[1]-1),peak_time_h=(tp-obs[0]).total_seconds()/3600,native_peak_m3s=qp,native_peak_time_utc=tp.isoformat(),observed_hourly_peak_m3s=obs[1],observed_hourly_peak_utc=obs[0].isoformat());rows.append(dict(profile=name,project=d['project'],parameters=d['parameters'],native_full_event=d['metrics']['86510000'],JJ_partial=d['metrics']['86472000'],second_wave=second,input_sha256=d['input_sha256']))
 old,new,alt=rows
 if len({r['input_sha256'] for r in rows})!=1:raise RuntimeError('Changed forcing')
 for r in [new,alt]:
  if not (r['native_full_event']['nse']>old['native_full_event']['nse'] and r['native_full_event']['recession_NMAE']<old['native_full_event']['recession_NMAE'] and r['second_wave']['NMAE']<old['second_wave']['NMAE'] and abs(r['second_wave']['peak_error_pct'])<abs(old['second_wave']['peak_error_pct']) and abs(r['second_wave']['peak_time_h'])<abs(old['second_wave']['peak_time_h'])):raise RuntimeError('Profile failed improvement on event and secondary wave')
 out=dict(event='E27_MAY2024',role='event_calibration_not_independent_validation',secondary_window_utc=[a.isoformat(),b.isoformat()],profiles=rows,selected='full_event',selection_reason='Lower full-event RMSE/NSE error, lower recession NMAE and lower second-wave NMAE than alternative; the alternative reduces second-crest magnitude and timing errors further.',rainfall_unchanged=True,observations_unchanged=True,clock_shift_minutes=0,JJ_note='JJ is an auxiliary calibration control on 77 real hours. Its partial NSE fell slightly relative to the previous model; Muçum is the selection target.')
 m.save(m.OUT/'revision2_comparison.json',out);print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
