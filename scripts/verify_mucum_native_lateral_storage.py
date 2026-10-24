#!/usr/bin/env python3
"""Recompute existing portable DSS project; audit every branch and storage."""
import copy,csv,json,shutil,subprocess,sys
from pathlib import Path
import numpy as np
import build_mucum_floodplain_storage as geo
import run_hec_hms_g040_e1_hindcast as hms
import export_mucum_estrela_event_calibration as ind
from search_mucum_lateral_storage import OUT

def main():
    hec=Path(sys.argv[1]).resolve();src=OUT/'native';dest=OUT/'verified_isolated';proj=dest/'project'
    if proj.exists():shutil.rmtree(proj)
    shutil.copytree(src/'project',proj)
    for name in ['output.dss','hec_output_values.csv','lateral_native_values.csv']:(proj/name).unlink(missing_ok=True)
    # Existing input.dss and terrain_geometry.dss are consumed without rewriting
    # either file, as when a user opens the delivered project and presses Compute.
    script='''from hms.model.JythonHms import *
from hec.heclib.dss import HecDss
import csv
project_dir=%r
OpenProject("g040_e1_hindcast",project_dir)
Compute("Hindcast")
dss=HecDss.open(project_dir+"/output.dss")
fo=open(project_dir+"/hec_output_values.csv","wb");fw=csv.writer(fo)
fw.writerow(["element","time_value","q_m3s","pathname"])
fa=open(project_dir+"/lateral_native_values.csv","wb");aw=csv.writer(fa)
aw.writerow(["element","variable","time_value","value","units"])
for path in dss.getCatalogedPathnames():
    parts=path.split("/")
    if "/RUN:Hindcast/" not in path:continue
    series=dss.get(path)
    for i in range(series.numberValues):
        value=float(series.values[i])
        if value<=-1e20:continue
        if parts[3]=="FLOW":fw.writerow([parts[2],int(series.times[i]),value,path])
        if parts[2] in ["DIV_REACH_FP","FP_REACH","FP_MUCUM"]:aw.writerow([parts[2],parts[3],int(series.times[i]),value,series.units])
fo.close();fa.close();dss.close()
print("LATERAL_EXISTING_DSS_COMPUTE_OK")
Exit(0)
'''%str(proj)
    (proj/'run.script').write_text(script)
    cp=subprocess.run([str(hec),'-s',str(proj/'run.script')],cwd=hec.parent,capture_output=True,text=True,timeout=240)
    (dest/'compute.log').write_text(cp.stdout+'\n'+cp.stderr)
    if 'LATERAL_EXISTING_DSS_COMPUTE_OK' not in cp.stdout:raise RuntimeError(cp.stdout[-2500:]+cp.stderr[-1500:])
    d=json.loads((src/'result.json').read_text());by=hms.read_output_csv(proj/'hec_output_values.csv');original=hms.read_output_csv(src/'project/hec_output_values.csv')
    base=hms.read_output_csv(geo.OUT/'verified_isolated_native_diagnostic_rawclock/project/hec_output_values.csv')
    start=hms.utc(d['window']['start_utc']);end=hms.utc(d['window']['end_utc']);count=int((end-start).total_seconds()/180)+1
    names=['SRC_86472000','DIV_REACH_FP','FP_REACH','FP_MUCUM','J_REACH_RETURN']+['J_'+c for c in hms.MAIN_CHECKPOINTS]
    for name in names:
        rr=by[name]
        if len(rr)!=count or rr[0][0]!=start or rr[-1][0]!=end or any(not np.isfinite(q) or q<0 for t,q in rr):raise RuntimeError('Incomplete isolated series '+name)
        if max(abs(q-b) for (t,q),(u,b) in zip(rr,original[name]))>1e-8:raise RuntimeError('Copied project changed output '+name)
    source_delta=max(abs(q-b) for (t,q),(u,b) in zip(by['SRC_86472000'],base['SRC_86472000']))
    if source_delta>1e-10:raise RuntimeError('Original source boundary changed')
    axis=[t for t,q in by['SRC_86472000']];rr=list(csv.DictReader((proj/'lateral_native_values.csv').open()))
    def native(element,var):
        rows=[r for r in rr if r['element']==element and r['variable']==var]
        mapping={hms.dss_time_to_utc(r['time_value']):float(r['value']) for r in rows}
        if len(rows)!=count or len(mapping)!=count:raise RuntimeError('Incomplete native branch '+element+' '+var)
        if not all(t in mapping for t in axis):raise RuntimeError('Native timestamps mismatch')
        return np.array([mapping[t] for t in axis]),{r['units'] for r in rows}
    audit=dict(existing_input_DSS_recomputed_without_rewriting=True,complete_values_per_series=count,source_max_difference_m3s=source_delta,clock_shift_minutes=0,whole_reach_capacity_field_measured=False)
    combined,_=native('DIV_REACH_FP','FLOW-COMBINE');main,_=native('DIV_REACH_FP','FLOW');div,_=native('DIV_REACH_FP','FLOW-DIVERSION')
    residual=float(max(abs(combined-main-div)));audit['diversion_split_max_residual_m3s']=residual
    if residual>1e-8:raise RuntimeError('Diversion branch balance failed')
    p=d['parameters_lateral'];theory=p['fraction']*np.maximum(combined-p['threshold_m3s'],0);audit['diversion_curve_max_difference_m3s']=float(max(abs(theory-div)))
    for element in ['FP_REACH','FP_MUCUM']:
        s,units=native(element,'STORAGE');infl,_=native(element,'FLOW-COMBINE');out,_=native(element,'FLOW')
        if units!={'1000 M3'}:raise RuntimeError('Unrecognized storage units '+str(units))
        s=s*1000;balance=float(np.trapezoid(infl-out,dx=180)-(s[-1]-s[0]))
        if abs(balance)>1:raise RuntimeError('Storage balance failed '+element+' '+str(balance))
        audit[element]=dict(max_storage_m3=float(max(s)),end_storage_m3=float(s[-1]),balance_residual_m3=balance)
        if element=='FP_REACH' and max(abs(div-infl))>1e-8:raise RuntimeError('Diverted flow did not enter lateral storage')
        if element=='FP_MUCUM':
            curve=list(csv.DictReader((geo.OUT/'curva_armazenamento_descarga_HMS.csv').open()))
            cs=np.array([float(r['storage_m3']) for r in curve]);cq=np.array([float(r['discharge_m3s']) for r in curve]);difference=float(max(abs(s-np.interp(out,cq,cs))))
            if difference>10:raise RuntimeError('Local terrain storage curve was altered or misread')
            audit['local_terrain_curve_max_interpretation_error_m3']=difference
    side,_=native('FP_REACH','FLOW');rejoin=np.array([q for t,q in by['J_REACH_RETURN']]);audit['return_junction_max_residual_m3s']=float(max(abs(main+side-rejoin)))
    if audit['return_junction_max_residual_m3s']>1e-8:raise RuntimeError('Return junction balance failed')
    selection=json.loads((OUT/'screening.json').read_text())['selected']
    if selection.get('regional_capacity_constraint'):
        capacity=json.loads((OUT/'regional_hourly_capacity.json').read_text());ct=np.array([hms.utc(r['time_utc']).timestamp() for r in capacity['hourly']]);cv=np.array([r['connected_land_volume_m3'] for r in capacity['hourly']])
        onset=max(0,int(np.flatnonzero(combined>p['threshold_m3s'])[0])-1);reference=float(np.interp(axis[onset].timestamp(),ct,cv));available=float(max(cv)-reference);budget=.98*available
        required=audit['FP_REACH']['max_storage_m3']
        if required>budget+100:raise RuntimeError('Regional incremental storage budget exceeded '+str((required,budget)))
        audit['regional_incremental_capacity']=dict(max_event_land_volume_m3=float(max(cv)),reference_at_first_diversion_m3=reference,
            additional_capacity_m3=available,budget_with_two_percent_margin_m3=budget,required_native_max_storage_m3=required,
            passed=True,reference_time_utc=axis[onset].isoformat(),
            interpretation='Central regional terrain scenario, using maximum event capacity; not a dynamic hydraulic water-surface validation or a measured channel-bank threshold.')
    raw=json.loads((hms.BASE/'historical_calibration_forcing/E24_NOV2023/hydro.json').read_text());strict=copy.deepcopy(raw)
    for c in strict['controls']:
        if str(c['code'])=='86510000':
            for r in c['recent_rows']:
                if r.get('level_source_unit') is None or r['level_source_unit']>1500:r['flow_m3s']=None
    sim=ind.model(proj/'hec_output_values.csv','86510000');pairs=ind.independent_pairs(sim,raw,'86510000',d['window']);m=ind.metrics(pairs)
    low=ind.metrics(ind.independent_pairs(sim,strict,'86510000',d['window']));peak_t,peak_q=max(sim,key=lambda z:z[1]);crest=hms.utc('2023-11-19T02:45:00Z')
    rise=[(o,q) for t,o,q in pairs if 0<=(crest-t).total_seconds()<=24*3600];fall=[(o,q) for t,o,q in pairs if t>crest]
    m.update(strict_NSE=low['nse'],peak_error_pct=100*(peak_q/max(o for t,o,q in pairs)-1),peak_time_minus_SGB_h=(peak_t-crest).total_seconds()/3600,
        rise_NMAE=sum(abs(o-q) for o,q in rise)/sum(o for o,q in rise),recession_NMAE=sum(abs(o-q) for o,q in fall)/sum(o for o,q in fall))
    for key in ['nse','kge','pbias_pct','rmse_m3s']:
        if abs(m[key]-d['independent_metrics'][key])>1e-8:raise RuntimeError('Independent copied-project metric mismatch '+key)
    passed=(m['nse']>=.99 and m['kge']>=.95 and m['strict_NSE']>=.97 and abs(m['peak_error_pct'])<=5 and abs(m['peak_time_minus_SGB_h'])<=1 and abs(m['pbias_pct'])<=3 and m['rise_NMAE']<=.05 and m['recession_NMAE']<=.05)
    if not passed:raise RuntimeError('Calibration quality gate failed '+str(m))
    d.update(independent_metrics=m,isolated_lateral_audit=audit,quality_gate_passed=True)
    geo.save(dest/'result.json',d);geo.save(OUT/'isolated_verification.json',dict(metrics=m,audit=audit,quality_gate_passed=True,independent_event_validation=False,interpretation='Good fit in this calibration event; whole-reach side storage remains an unmeasured physical hypothesis.'))
    print(json.dumps(dict(metrics=m,audit=audit,quality_gate_passed=True),ensure_ascii=False))

if __name__=='__main__':main()
