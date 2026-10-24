#!/usr/bin/env python3
"""Muçum May-2024 rainfall-runoff model, independent of November parameters.

Five audited nested rainfall zones generate the complete event. Interrupted JJ
observations are diagnostics, never fabricated inflow or persisted boundary.
The raw Muçum observations are used for calibration and as an observed gage.
"""
import argparse,copy,csv,hashlib,json,math,subprocess,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np
from scipy.signal import lfilter,fftconvolve
from scipy.optimize import differential_evolution
import run_hec_hms_g040_e1_hindcast as hms
import export_mucum_estrela_event_calibration as ind

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'assets/data/hec_hms_g040_full_basin'
FORCING=BASE/'historical_calibration_forcing/E27_MAY2024'
OUT=ROOT/'assets/data/g040_hydro_stack/mucum_may2024_20261024'
ZONES=['SB_PRATA_7868','SB_ANTAS_RESIDUAL','SB_CARREIRO_7866','SB_STZ_RESIDUAL','SB_INC_MUCUM']
AREAS=[3775.99,9142.666,2564.19,292.34,190.021]
PARAMS=['loss_up','tc_up','r_up','loss_down','tc_down','r_down','baseflow_specific','recession','routing_k']
SEED=dict(zip(PARAMS,[2.,10.,45.,2.,6.,25.,.04,.95,3.]))

def load(p):return json.loads(Path(p).read_text())
def save(p,d):
    p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+'.pending');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');t.replace(p)

def prepare():
    rain=load(FORCING/'rain.json');hydro=load(FORCING/'hydro.json');nested=rain['upper_antas_nested_forcing'];zones={z['subbasin_id']:z for z in nested['zones']}
    maps={sid:{datetime.fromisoformat(r['time_local']).replace(tzinfo=hms.BRT).astimezone(timezone.utc):r['mm'] for r in zones[sid]['series']} for sid in ZONES}
    start=datetime.fromisoformat(nested['start_local']).replace(tzinfo=hms.BRT).astimezone(timezone.utc);end=datetime.fromisoformat(nested['end_local']).replace(tzinfo=hms.BRT).astimezone(timezone.utc)
    times=hms.hourly_axis(start,end);values={sid:[maps[sid].get(t) for t in times] for sid in ZONES}
    for sid,rr in values.items():
        if any(q is None or not np.isfinite(q) or q<0 for q in rr):raise RuntimeError('Missing/invalid observed rainfall '+sid)
    digest=hashlib.sha256((FORCING/'rain.json').read_bytes()+(FORCING/'hydro.json').read_bytes()).hexdigest()
    save(OUT/'input_audit.json',dict(event='E27_MAY2024',city='Muçum',model_role='event_specific_calibration_not_holdout',input_sha256=digest,
        simulation_start_utc=start.isoformat(),simulation_end_utc=end.isoformat(),warmup_days=7,rain_hours=len(times),
        station_event_support=rain['network']['station_event_support'] if 'station_event_support' in rain['network'] else rain['network'],
        rain_diagnostics=rain['rain_diagnostics'],nested_diagnostics=nested['diagnostics'],subbasin_areas_km2=dict(zip(ZONES,AREAS)),
        total_area_km2=sum(AREAS),source_boundary_policy='No observed-flow Source element. All five zones are rainfall-runoff. JJ is an auxiliary calibration control on 77 real observed hours, not an independent validation.',
        observation_clock_shift_minutes=0,missing_rain_zero_filled=False))
    return times,values,hydro,digest

def local_params(p,i):
    up=i<2;tc=p['tc_up' if up else 'tc_down'];r=p['r_up' if up else 'r_down'];loss=p['loss_up' if up else 'loss_down']
    if i==0:
        tc=p.get('tc_prata',tc);r=p.get('r_prata',r);loss=p.get('loss_prata',loss)
    initial=p.get('initial_up' if up else 'initial_down',5.)
    if i==0:initial=p.get('initial_prata',initial)
    # Spatial parameters remain constant throughout the event. Carreiro and
    # the small lower residuals need not share an effective soil/response.
    zone=['prata','antas','carreiro','stz','mucum'][i]
    initial=p.get('initial_'+zone,initial);loss=p.get('loss_'+zone,loss)
    tc=p.get('tc_'+zone,tc);r=p.get('r_'+zone,r)
    return initial,loss,tc,r

def basin(p):
    text='''Basin: G040 E1 Hindcast
     Description: Muçum May2024 five-zone observed-rain calibration, no observed-flow source
     Version: 4.13
     Filepath Separator: \\
     Unit System: Metric
     Missing Flow To Zero: No
     Enable Flow Ratio: No
     Compute Local Flow At Junctions: No
     Unregulated Output Required: No
     Enable Sediment Routing: No
End:
'''
    downs=['J_86472000','J_86472000','J_CARREIRO','J_86472600','J_86510000']
    for i,sid in enumerate(ZONES):
        block=hms.subbasin_block(hms.hec_subbasin_name(sid),AREAS[i],downs[i],50,120,
            (p['baseflow_specific'],p['recession'],.01),local_params(p,i))
        group=['prata','up','carreiro','down','down'][i]
        if p.get('loss_method')=='DeficitConstantLinear':
            import re
            initial,loss,tc,storage=local_params(p,i)
            block=re.sub(r'     LossRate: Initial\+Constant\n     Percent Impervious Area: 0.0\n     Initial Loss: [^\n]+\n     Constant Loss Rate: [^\n]+',
                f'     LossRate: Deficit Constant\n     Percent Impervious Area: 0.0\n     Initial Deficit: {initial:.9f}\n     Maximum Deficit: {max(200.,initial):.9f}\n     Percolation Rate: {loss:.9f}\n     Recovery Factor: 1.0',block)
            k=p.get('gw_k_'+group,p['gw_k']);fraction=p.get('gw_fraction_'+group,p['gw_fraction'])
            block=re.sub(r'     Baseflow: Recession\n.*?     Threshold Flow to Peak Ratio: [^\n]+',
                f'     Baseflow: Linear Reservoir\n     Groundwater Layer: 1\n     GW-1 Baseflow Fraction: {fraction:.9f}\n     GW-1 Number Reservoirs: {int(p.get("gw_steps_"+group,p.get("gw_steps",2)))}\n     GW-1 Routing Coefficient: {k:.9f}\n     GW-1 Initial Flow/Area Ratio: 0\n'
                f'     Groundwater Layer: 2\n     GW-2 Baseflow Fraction: 0\n     GW-2 Number Reservoirs: 1\n     GW-2 Routing Coefficient: {-24/math.log(p["recession"]):.9f}\n     GW-2 Initial Flow/Area Ratio: {p["baseflow_specific"]:.9f}',block,flags=re.S)
        if p.get('loss_method')=='GreenAmpt' or group in p.get('green_ampt_groups',[]):
            import re
            block=re.sub(r'     LossRate: Initial\+Constant\n     Percent Impervious Area: 0.0\n     Initial Loss: [^\n]+\n     Constant Loss Rate: [^\n]+',
                '     LossRate: Green and Ampt\n     Percent Impervious Area: 0.0\n'
                '     Initial Variable: Initial Content\n     Initial Content: 0.15\n     Saturated Content: 0.45\n'
                f'     Capillarity Method: SUCTION\n     Wetting Front Suction: {p["suction_deficit_"+group]/.3:.9f}\n     Hydraulic Conductivity: {p["ks_"+group]:.9f}',block)
        if p.get('loss_method')=='SCS':
            cn=p['cn_up' if i<2 else 'cn_down']
            if i==0:cn=p.get('cn_prata',cn)
            import re
            block=re.sub(r'     LossRate: Initial\+Constant\n     Percent Impervious Area: 0.0\n     Initial Loss: [^\n]+\n     Constant Loss Rate: [^\n]+',
                f'     LossRate: SCS\n     Percent Impervious Area: 0.0\n     Curve Number: {cn:.9f}',block)
        text+=block
    for name,down in [('J_86472000','R_JJ_CARREIRO'),('J_CARREIRO','R_CARREIRO_STZ'),('J_86472600','R_STZ_MUCUM')]:text+=hms.junction_block(name,down,True)
    text+='''Junction: J_86510000
     Computation Point: Yes
     Observed Hydrograph Gage: Q_OBS_MU
End:
'''
    for name,down,length in [('R_JJ_CARREIRO','J_CARREIRO',2.557),('R_CARREIRO_STZ','J_86472600',18.315),('R_STZ_MUCUM','J_86510000',23.652)]:
        text+=hms.reach_block(name,down,p['routing_k']*length/44.524,0.,1)
    if 'Source:' in text:raise RuntimeError('Observed discharge must not be an inflow')
    return text

def evaluate(project,hydro,times):
    by=hms.read_output_csv(project/'hec_output_values.csv');expected=int((times[-1]-times[0]).total_seconds()/180)+1
    for name in ['J_86472000','J_86472600','J_86510000']+[hms.hec_subbasin_name(s) for s in ZONES]:
        rr=by.get(name,[])
        if len(rr)!=expected or rr[0][0]!=times[0] or rr[-1][0]!=times[-1] or any(not np.isfinite(q) or q<0 for t,q in rr):raise RuntimeError('Incomplete native output '+name)
    scores={};window=dict(start_utc=times[0].isoformat(),end_utc=times[-1].isoformat())
    for code in ['86510000','86472000']:
        sim=ind.model(project/'hec_output_values.csv',code);pairs=ind.independent_pairs(sim,hydro,code,window);m=ind.metrics(pairs)
        scored_sim=[(t,q) for t,q in sim if pairs[0][0]<=t<=pairs[-1][0]]
        peak_t,peak_q=max(scored_sim,key=lambda z:z[1]);observed_peak_t=max(pairs,key=lambda z:z[1])[0];observed_peak=max(o for t,o,q in pairs)
        rise=[(o,q) for t,o,q in pairs if 0<=(observed_peak_t-t).total_seconds()<=24*3600];fall=[(o,q) for t,o,q in pairs if t>observed_peak_t]
        m.update(full_simulated_peak_m3s=peak_q,full_simulated_peak_time_utc=peak_t.isoformat(),observed_peak_m3s=observed_peak,
            peak_error_pct=100*(peak_q/observed_peak-1),peak_time_minus_telemetry_h=(peak_t-observed_peak_t).total_seconds()/3600,
            rising_NMAE=sum(abs(o-q) for o,q in rise)/sum(o for o,q in rise),recession_NMAE=sum(abs(o-q) for o,q in fall)/sum(o for o,q in fall) if fall else None)
        scores[code]=m
    # JJ full-event simulated peak is not compared with a truncated observed crest.
    scores['86472000']['full_peak_error_not_valid_after_observation_loss']=True
    return scores,expected

def compute(hec,p,context):
    times,rain,hydro,digest=context;key=hashlib.sha256(json.dumps(dict(parameters=p,input=digest,model='may_rain_v1'),sort_keys=True).encode()).hexdigest()[:12]
    dest=OUT/'runs'/key;proj=dest/'project';result=dest/'result.json'
    if result.exists():
        d=load(result)
        if d.get('native_compute_verified'):return d
    proj.mkdir(parents=True,exist_ok=True)
    for name,text in [('g040_e1_hindcast.hms',hms.build_project()),('g040_e1_hindcast.run',hms.build_run()),('e1.control',hms.build_control(times[0],times[-1])),('e1.met',hms.build_met(ZONES)),('e1.basin',basin(p))]:(proj/name).write_text(text)
    c=next(c for c in hydro['controls'] if str(c['code'])=='86510000');rows=[r for r in c['recent_rows'] if r.get('flow_m3s') is not None];a=hms.utc(rows[0]['time_utc']);b=hms.utc(rows[-1]['time_utc'])
    obsaxis=hms.hourly_axis(a,b);obsmap={hms.utc(r['time_utc']):r['flow_m3s'] for r in rows}
    if any(t not in obsmap for t in obsaxis):raise RuntimeError('Mu observed-gage construction requires an explicitly contiguous series')
    dp=hms.dpart(hms.local_naive(a));obs_path=f'/G040/OBS_MU/FLOW/{dp}/1Hour/OBSERVED/'
    gages=hms.build_gage(times[0],times[-1],[],ZONES)
    # Drop the unused default source-flow gage; all flow input is generated by rain.
    import re
    gages=re.sub(r'Gage: Q_86472000\n.*?\nEnd:\n','',gages,flags=re.S)
    gages+=hms.gage_block('Q_OBS_MU','Flow',obs_path,a,b);(proj/'g040_e1_hindcast.gage').write_text(gages)
    script=hms.write_jython(proj,times,{},rain);text=script.read_text();la=hms.local_naive(a)
    insert=f'''\n# Observation-only gage; no Source element consumes this series.
dss=HecDss.open(project_dir+"/input.dss")
ot=HecTime({hms.fmt_date(la)!r},{hms.fmt_time(la)!r})
ovals={[obsmap[t] for t in obsaxis]!r}
ots=[]
for val in ovals:
    ots.append(ot.value());ot.add(60)
og=TimeSeriesContainer();og.fullName={obs_path!r};og.interval=60
og.times=ots;og.values=ovals;og.numberValues=len(ovals);og.units="M3/S";og.type="INST-VAL"
dss.put(og);dss.close()
'''
    text=text.replace('OpenProject("g040_e1_hindcast",project_dir)',insert+'\nOpenProject("g040_e1_hindcast",project_dir)').replace('Exit(1)','Exit(0)');script.write_text(text)
    cp=subprocess.run([str(Path(hec).resolve()),'-s',str(script.resolve())],cwd=Path(hec).resolve().parent,capture_output=True,text=True,timeout=300)
    (dest/'compute.log').write_text(cp.stdout+'\n'+cp.stderr)
    if 'G040_E1_HINDCAST_COMPUTE_OK' not in cp.stdout:raise RuntimeError(cp.stdout[-2500:]+cp.stderr[-1500:])
    metrics,count=evaluate(proj,hydro,times)
    d=dict(event_id='E27_MAY2024',target='86510000',parameters=p,input_sha256=digest,metrics=metrics,native_compute_verified=True,native_values_per_element=count,
        project=str(proj.relative_to(ROOT)),source_Q_used_as_inflow=False,observation_clock_shift_minutes=0,calibration_event_not_independent_validation=True)
    save(result,d);print(json.dumps(dict(native=key,parameters=p,metrics=metrics['86510000'])),flush=True);return d

def main():
    ap=argparse.ArgumentParser();ap.add_argument('hec');ap.add_argument('--parameters',type=Path);args=ap.parse_args();ctx=prepare();p=load(args.parameters) if args.parameters else SEED
    d=compute(args.hec,p,ctx);save(OUT/'baseline.json' if not args.parameters else OUT/'latest_native.json',d)

if __name__=='__main__':main()
