#!/usr/bin/env python3
"""Recompute a copied project, verify full series and native storage balance."""
import ast,csv,json,shutil,subprocess,sys
from pathlib import Path
import numpy as np
import build_mucum_floodplain_storage as geo
import run_hec_hms_g040_e1_hindcast as hms
import export_mucum_estrela_event_calibration as independent

def main():
    hec=Path(sys.argv[1]).resolve();s=json.loads((geo.OUT/'native_diagnostic_summary.json').read_text())
    case=next(r for r in s['models'] if r['name']=='local_terrain_Modified_Puls');rp=geo.ROOT/case['result_file'];dest=geo.OUT/('verified_isolated_'+rp.parent.parent.name);proj=dest/'project'
    if proj.exists():shutil.rmtree(proj)
    shutil.copytree(rp.parent/'project',proj);dest.mkdir(parents=True,exist_ok=True)
    (proj/'output.dss').unlink(missing_ok=True);(proj/'hec_output_values.csv').unlink(missing_ok=True)
    script=(rp.parent/'project/run.script').read_text().replace(str(rp.parent/'project'),str(proj))
    script=script.replace('Exit(0)','''
dss=HecDss.open(project_dir+"/output.dss")
fo=open(project_dir+"/reservoir_native_values.csv","wb");w=csv.writer(fo)
w.writerow(["variable","time_value","value","units"])
for path in dss.getCatalogedPathnames():
    parts=path.split("/")
    if parts[2]!="FP_MUCUM":continue
    series=dss.get(path)
    print("FP_NATIVE_PATH",path,series.units,series.numberValues)
    for i in range(series.numberValues):
        val=float(series.values[i])
        if val>-1e20:w.writerow([parts[3],int(series.times[i]),val,series.units])
fo.close();dss.close()
Exit(0)
''')
    (proj/'run.script').write_text(script)
    cp=subprocess.run([str(hec),'-s',str(proj/'run.script')],cwd=hec.parent,capture_output=True,text=True,timeout=240)
    (dest/'isolated_compute.log').write_text(cp.stdout+'\n'+cp.stderr)
    if 'G040_E1_HINDCAST_COMPUTE_OK' not in cp.stdout:raise RuntimeError(cp.stdout[-1500:]+cp.stderr[-500:])
    by=hms.read_output_csv(proj/'hec_output_values.csv');d=json.loads(rp.read_text());start=hms.utc(d['window']['start_utc']);end=hms.utc(d['window']['end_utc'])
    count=int((end-start).total_seconds()/180)+1
    for code in hms.MAIN_CHECKPOINTS+['MUCUM_INFLOW']:
        values=by['J_'+code]
        if len(values)!=count or values[0][0]!=start or values[-1][0]!=end or any(not np.isfinite(q) or q<0 for t,q in values):raise RuntimeError('Missing/invalid isolated series '+code)
    fp=by['FP_MUCUM']
    rows=list(csv.DictReader((proj/'reservoir_native_values.csv').open()));storage={hms.dss_time_to_utc(r['time_value']):(float(r['value']),r['units']) for r in rows if r['variable']=='STORAGE'}
    if len(storage)!=count:raise RuntimeError('Incomplete native storage series')
    units=next(iter(storage.values()))[1];key=units.upper().replace(' ','')
    if key in ['1000M3','THOUM3','1000M^3']:factor=1000.
    elif key in ['M3','M^3']:factor=1.
    else:raise RuntimeError('Unrecognized native storage units '+units)
    times=[t for t,q in fp];sv=np.array([storage[t][0]*factor for t in times]);inflow=np.array([q for t,q in by['J_MUCUM_INFLOW']]);outflow=np.array([q for t,q in fp])
    balance=float(np.trapezoid(inflow-outflow,dx=180)-(sv[-1]-sv[0]))
    if not np.isfinite(sv).all() or min(sv)<-1e-6 or abs(balance)>max(100.,np.trapezoid(inflow,dx=180)*1e-7):raise RuntimeError('Native reservoir water balance failed '+str(balance))
    curve=list(csv.DictReader((geo.OUT/'curva_armazenamento_descarga_HMS.csv').open()));ss=np.array([float(r['storage_m3']) for r in curve]);qq=np.array([float(r['discharge_m3s']) for r in curve])
    if max(outflow)>max(qq)+1:raise RuntimeError('Native discharge left the published curve domain')
    curve_error=float(np.max(np.abs(sv-np.interp(outflow,qq,ss))))
    if curve_error>max(10.,max(ss)*1e-4):raise RuntimeError('Native storage units or curve interpretation mismatch '+str(curve_error))
    score_path=Path(d['input_artifacts']['score_hydro_file']);full=json.loads(score_path.read_text());strict=json.loads((score_path.parent/'strict_Q_domain.json').read_text())
    pairs=independent.independent_pairs(independent.model(proj/'hec_output_values.csv','86510000'),full,'86510000',d['window']);m=independent.metrics(pairs)
    for k in ['nse','kge','pbias_pct','rmse_m3s']:
        if abs(m[k]-d['scores']['86510000'][k])>1e-8:raise RuntimeError('Independent metric mismatch '+k)
    constraints=None
    if 'native_peak_refined' in str(rp):
        sm=independent.metrics(independent.independent_pairs(independent.model(proj/'hec_output_values.csv','86510000'),strict,'86510000',d['window']))
        peak_t,peak_q=max(by['J_86510000'],key=lambda z:z[1]);timing=(peak_t-hms.utc('2023-11-19T02:45:00Z')).total_seconds()/3600
        constraints=dict(NSE=m['nse'],strict_NSE=sm['nse'],bias_pct=m['pbias_pct'],peak_time_minus_SGB_h=timing)
        if m['nse']<.98 or sm['nse']<.95 or abs(m['pbias_pct'])>3 or abs(timing)>1.000001:
            raise RuntimeError('Final geometry case violated selection guardrails '+str(constraints))
    # Independently compare every source value written into the geometry project
    # to the original archived upstream observation, before any reservoir.
    line=next(x for x in script.splitlines() if x.startswith('source_values='));source_values=ast.literal_eval(line.split('=',1)[1])['86472000']
    raw=json.loads((hms.BASE/'historical_calibration_forcing/E24_NOV2023/hydro.json').read_text());axis=hms.hourly_axis(start,end);original=hms.source_hourly(raw,'86472000',axis)
    difference=max(abs(a-b) for a,b in zip(original,source_values))
    if len(source_values)!=len(original) or difference>1e-10:raise RuntimeError('Geometry project changed observed upstream Q')
    reference=s['models'][0];rd=json.loads((geo.ROOT/reference['result_file']).read_text());old_storage=rd['upstream_boundary_overbank_storage_experiment']
    audit=dict(isolated_compute_verified=True,native_values_per_control=count,native_storage_values=count,
        native_storage_units=units,native_storage_max_m3=float(max(sv)),native_storage_initial_m3=float(sv[0]),native_storage_final_m3=float(sv[-1]),
        native_integrated_inflow_minus_outflow_m3=float(np.trapezoid(inflow-outflow,dx=180)),native_storage_balance_residual_m3=balance,
        storage_curve_unit_check_max_error_m3=curve_error,unmodified_upstream_max_abs_difference_m3s=difference,
        independent_Q_metrics=m,final_selection_constraints=constraints,V3_conceptual_max_storage_m3=old_storage['maximum_storage_m3'],V3_conceptual_remaining_storage_m3=old_storage['remaining_storage_m3'],
        interpretation='Local terrain-derived level-pool sensitivity only; no newly measured bathymetry, bank lines, or backwater solution.',
        original_research_result=case['result_file'])
    geo.save(geo.OUT/'native_geometry_verification.json',audit)
    d['native_geometry_verification']=audit;geo.save(dest/'result.json',d)
    case['result_file']=str((dest/'result.json').relative_to(geo.ROOT));case['isolated_compute_verified']=True
    geo.save(geo.OUT/'native_diagnostic_summary.json',s)
    print(json.dumps(audit,ensure_ascii=False))

if __name__=='__main__':main()
