#!/usr/bin/env python3
"""Verify copied native May project, original rain and observation-only gage."""
import json,re,shutil,subprocess,sys
from pathlib import Path
import numpy as np
import calibrate_mucum_may2024 as m

def export_script(proj,include_rain=True):
    return '''from hms.model.JythonHms import *
from hec.heclib.dss import HecDss
import csv
project_dir=%r
OpenProject("g040_e1_hindcast",project_dir)
Compute("Hindcast")
dss=HecDss.open(project_dir+"/output.dss")
fo=open(project_dir+"/hec_output_values.csv","wb");w=csv.writer(fo)
w.writerow(["element","time_value","q_m3s","pathname"])
for path in dss.getCatalogedPathnames():
    parts=path.split("/")
    if parts[3]!="FLOW" or "/RUN:Hindcast/" not in path:continue
    s=dss.get(path)
    if s.units!="M3/S":raise RuntimeError("Unexpected flow units: "+str(s.units))
    for i in range(s.numberValues):
        value=float(s.values[i])
        if value>-1e20:w.writerow([parts[2],int(s.times[i]),value,path])
fo.close()
fo=open(project_dir+"/native_soil_process_3min.csv","wb");w=csv.writer(fo)
w.writerow(["element","variable","time_value","value","units","type"])
selected_variables=["MOISTURE DEFICIT","SATURATION FRACTION","PERC-SOIL","INFILTRATION","PRECIP-EXCESS","PRECIP-LOSS","FLOW-BASE","FLOW-BASE-1","FLOW-BASE-2","FLOW-DIRECT","AQUIFER RECHARGE"]
for path in dss.getCatalogedPathnames():
    parts=path.split("/")
    if parts[3] not in selected_variables or "/RUN:Hindcast/" not in path:continue
    s=dss.get(path)
    for i in range(s.numberValues):
        value=float(s.values[i]);time=int(s.times[i])
        if value>-1e20:w.writerow([parts[2],parts[3],time,value,s.units,s.type])
fo.close();dss.close()
dss=HecDss.open(project_dir+"/input.dss")
fo=open(project_dir+"/native_rain_values.csv","wb");w=csv.writer(fo)
w.writerow(["zone","time_value","mm","units"])
for path in dss.getCatalogedPathnames():
    parts=path.split("/")
    if parts[3]!="PRECIP-INC":continue
    s=dss.get(path)
    for i in range(s.numberValues):
        value=float(s.values[i])
        if value>-1e20:w.writerow([parts[2],int(s.times[i]),value,s.units])
fo.close();dss.close()
print("MAY_EXISTING_DSS_COMPUTE_OK")
Exit(0)
'''%str(proj)

def main():
    hec=Path(sys.argv[1]).resolve();ctx=m.prepare();times,rain,hydro,digest=ctx;selected=m.load(m.OUT/'latest_native.json');src=m.ROOT/selected['project'];dest=m.OUT/'verified_isolated';proj=dest/'project'
    if proj.exists():shutil.rmtree(proj)
    shutil.copytree(src,proj);(proj/'output.dss').unlink(missing_ok=True);(proj/'hec_output_values.csv').unlink(missing_ok=True)
    original_input=(proj/'input.dss').read_bytes();(proj/'run.script').write_text(export_script(proj))
    def run(folder,label):
        cp=subprocess.run([str(hec),'-s',str(folder/'run.script')],cwd=hec.parent,capture_output=True,text=True,timeout=300)
        (dest/(label+'.log')).write_text(cp.stdout+'\n'+cp.stderr)
        if 'MAY_EXISTING_DSS_COMPUTE_OK' not in cp.stdout:raise RuntimeError(cp.stdout[-2000:]+cp.stderr[-1000:])
    run(proj,'isolated_compute');metrics,count=m.evaluate(proj,hydro,times);by=m.hms.read_output_csv(proj/'hec_output_values.csv');before=m.hms.read_output_csv(src/'hec_output_values.csv')
    for name,rows in by.items():
        if name not in before:continue
        if len(rows)!=len(before[name]) or any(t!=u or abs(q-v)>1e-8 for (t,q),(u,v) in zip(rows,before[name])):raise RuntimeError('Copied project changed results '+name)
        if len(set(t for t,q in rows))!=len(rows):raise RuntimeError('Duplicate native times '+name)
    independent=m.hms.score_outputs(by,hydro,times)['86510000']
    for name in ['nse','kge','pbias_pct','rmse_m3s']:
        if abs(independent[name]-metrics['86510000'][name])>1e-8:raise RuntimeError('Independent metric mismatch '+name)
    import csv
    rows=list(csv.DictReader((proj/'native_rain_values.csv').open()));rain_audit={}
    for sid in m.ZONES:
        rr=[r for r in rows if r['zone']==sid];mapping={m.hms.dss_time_to_utc(r['time_value']):float(r['mm']) for r in rr}
        if not all(t in mapping for t in times):raise RuntimeError('Native rain missing original hour '+sid)
        error=max(abs(mapping[t]-x) for t,x in zip(times,rain[sid]))
        if error>1e-4 or {r['units'] for r in rr}!={'MM'}:raise RuntimeError('Native rainfall values/units/clock changed '+sid)
        rain_audit[sid]=dict(original_hours=len(times),native_max_precision_difference_mm=error)
    basin=(proj/'e1.basin').read_text()
    if re.search(r'^Source:',basin,re.M):raise RuntimeError('Unexpected observed-Q source in rainfall model')
    area=sum(float(s) for s in re.findall(r'^\s+Area: ([\d.]+)',basin,re.M))
    if abs(area-sum(m.AREAS))>1e-3:raise RuntimeError('Basin areas changed or overlap was added')
    # A second copied compute removes the target-observation connection. Model
    # flow must remain identical; target Q cannot act as forcing or assimilation.
    leak=dest/'observation_disconnected';
    if leak.exists():shutil.rmtree(leak)
    shutil.copytree(proj,leak);(leak/'output.dss').unlink(missing_ok=True);(leak/'hec_output_values.csv').unlink(missing_ok=True)
    (leak/'e1.basin').write_text(re.sub(r'^\s+Observed Hydrograph Gage:.*\n','',basin,flags=re.M));(leak/'run.script').write_text(export_script(leak));run(leak,'observation_disconnect_test')
    other=m.hms.read_output_csv(leak/'hec_output_values.csv');effect=max(abs(q-v) for (t,q),(u,v) in zip(by['J_86510000'],other['J_86510000']))
    if effect>1e-10:raise RuntimeError('Target observation affects the simulated outflow')
    old=m.load(m.OUT/'baseline.json')['metrics']['86510000'];new=metrics['86510000']
    improved=(new['nse']>old['nse'] and new['kge']>old['kge'] and abs(new['peak_error_pct'])<abs(old['peak_error_pct']) and abs(new['peak_time_minus_telemetry_h'])<abs(old['peak_time_minus_telemetry_h']) and new['rising_NMAE']<old['rising_NMAE'] and new['recession_NMAE']<old['recession_NMAE'])
    if not improved:raise RuntimeError('Final selection did not jointly improve the baseline')
    previous=m.load(m.OUT/'previous_accepted_selection.json')['metrics']['86510000']
    improved_previous=(new['nse']>previous['nse'] and new['kge']>previous['kge'] and abs(new['pbias_pct'])<abs(previous['pbias_pct']) and abs(new['peak_error_pct'])<abs(previous['peak_error_pct']) and abs(new['peak_time_minus_telemetry_h'])<abs(previous['peak_time_minus_telemetry_h']) and new['rising_NMAE']<previous['rising_NMAE'] and new['recession_NMAE']<previous['recession_NMAE'])
    if not improved_previous:raise RuntimeError('Soil revision failed to improve the previous accepted May model')
    prior=m.load(m.OUT/'before_revision2_selection.json')['metrics']['86510000']
    improved_revision2=(new['nse']>prior['nse'] and new['kge']>prior['kge'] and abs(new['pbias_pct'])<abs(prior['pbias_pct']) and abs(new['peak_error_pct'])<abs(prior['peak_error_pct']) and abs(new['peak_time_minus_telemetry_h'])<abs(prior['peak_time_minus_telemetry_h']) and new['rising_NMAE']<prior['rising_NMAE'] and new['recession_NMAE']<prior['recession_NMAE'])
    if not improved_revision2:raise RuntimeError('Second-wave revision did not improve the accepted NSE 0.9981 model')
    audit=dict(native_recomputed_from_existing_DSS=True,values_per_element=count,area_km2=area,source_elements_present=False,observation_only_gage_has_zero_flow_effect_m3s=effect,
        original_rain=rain_audit,clock_shift_minutes=0,paired_Mu_hours=new['pairs'],paired_JJ_hours=metrics['86472000']['pairs'],joint_improvement_against_same_rainfall_baseline=improved,
        joint_improvement_against_previous_May_model=improved_previous,previous_May_metrics=previous,
        joint_improvement_against_NSE_09981_revision=improved_revision2,previous_revision_metrics=prior,
        event_role='May 2024 event-specific calibration, not independent event validation',field_peak_reference_m=26.0,field_peak_reference_not_substituted_for_telemetry=True)
    selected.update(project=str(proj.relative_to(m.ROOT)),metrics=metrics,verification=audit);m.save(dest/'result.json',selected);m.save(m.OUT/'selection.json',selected)
    print(json.dumps(dict(metrics=new,audit=audit),ensure_ascii=False))

if __name__=='__main__':main()
