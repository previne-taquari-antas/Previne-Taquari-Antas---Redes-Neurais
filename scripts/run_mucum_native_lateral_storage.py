#!/usr/bin/env python3
"""Native, mass-conserving diversion/return branch with unchanged source DSS.

Reach storage is a calibrated hypothesis. It is separate from the fixed local
drone storage and must not be described as surveyed floodplain capacity.
"""
import ast,copy,csv,json,re,shutil,subprocess,sys
from pathlib import Path
import numpy as np
import build_mucum_floodplain_storage as geo
import run_hec_hms_g040_e1_hindcast as hms
import export_mucum_estrela_event_calibration as ind
from search_mucum_lateral_storage import OUT

def main():
    hec=Path(sys.argv[1]).resolve();selection=json.loads((OUT/'screening.json').read_text())['selected'];p=selection['parameters']
    base=geo.OUT/'native_lateral_base/terrain_local_modified_puls';dest=OUT/'native';proj=dest/'project'
    if proj.exists():shutil.rmtree(proj)
    shutil.copytree(base/'project',proj);d=json.loads((base/'result.json').read_text())
    basin=(proj/'e1.basin').read_text()
    source_pattern=r'(Source: SRC_86472000\n.*?Downstream: )R_86472000_JOIN_86500000'
    if len(re.findall(source_pattern,basin,re.S))!=1:raise RuntimeError('Expected primary source connection missing')
    basin=re.sub(source_pattern,r'\1DIV_REACH_FP',basin,count=1,flags=re.S)
    basin+='''
Diversion: DIV_REACH_FP
     Description: Calibrated reach-scale side storage hypothesis; not local surveyed capacity
     Downstream: J_REACH_RETURN
     Divert To: FP_REACH
     Diverter: Inflow-Diversion Table
     Inflow Diversion Table Name: Reach Side Diversion
     End Diverter:
End:

Reservoir: FP_REACH
     Description: Conceptual reach-wide lateral storage, linear return
     Downstream: J_REACH_RETURN
     Route: Modified Puls
     Routing Curve: Storage-Outflow
     Initial Storage: 0
     Storage-Outflow Table: Reach Side Storage Flow
End:

Junction: J_REACH_RETURN
     Downstream: R_86472000_JOIN_86500000
End:
'''
    (proj/'e1.basin').write_text(basin)
    tables=[('Reach Side Diversion','Inflow-Diversion','M3/S','M3/S','/MUCUM/REACH-SIDE/INFLOW-DIVERSION///TABLE/'),
        ('Reach Side Storage Flow','Storage-Outflow','THOU M3','M3/S','/MUCUM/REACH-SIDE/STORAGE-FLOW///TABLE/')]
    with (proj/'g040_e1_hindcast.pdata').open('a') as f:
        for name,typ,xunit,yunit,path in tables:
            f.write(f'\nTable: {name}\n     Table Type: {typ}\n     X-Units: {xunit}\n     Y-Units: {yunit}\n     Use External DSS File: YES\n     DSS File: terrain_geometry.dss\n     Pathname: {path}\n     Interpolation: Linear Interpolation\nEnd:\n')
    inflow=[0.,p['threshold_m3s'],15000.,30000.,60000.];divert=[p['fraction']*max(0,x-p['threshold_m3s']) for x in inflow]
    release=[0.,100.,500.,1000.,2000.,5000.,10000.];storage=[q*p['tau_h']*3600/1000 for q in release]
    capacity=None
    if selection.get('regional_capacity_constraint'):
        capacity=selection['incremental_storage_budget_m3']/.98
        pairs=[(s,q) for s,q in zip(storage,release) if s*1000<.99*capacity]
        # Below 99% capacity: calibrated linear return. Above it: emergency
        # return to the same river, encoding the regional scenario's limit.
        pairs += [(.99*capacity/1000,.99*capacity/(p['tau_h']*3600)),(capacity/1000,60000.),(1.001*capacity/1000,1000000.)]
        storage=[s for s,q in pairs];release=[q for s,q in pairs]
    insert=''
    for table,x,y in [(tables[0],inflow,divert),(tables[1],storage,release)]:
        name,typ,xunit,yunit,path=table
        insert+=f'''\npd=PairedDataContainer()
pd.fullName={path!r}
pd.numberCurves=1
pd.numberOrdinates={len(x)}
pd.xOrdinates={x!r}
pd.yOrdinates=[{y!r}]
pd.xunits={xunit!r}
pd.yunits={yunit!r}
pd.xtype=""
pd.ytype=""
pd.labelsUsed=False
gdss=HecDss.open(project_dir+"/terrain_geometry.dss")
gdss.put(pd)
gdss.close()
'''
    script=(base/'project/run.script').read_text().replace(str(base/'project'),str(proj))
    script=script.replace('OpenProject("g040_e1_hindcast",project_dir)',insert+'\nOpenProject("g040_e1_hindcast",project_dir)')
    export='''
dss=HecDss.open(project_dir+"/output.dss")
fo=open(project_dir+"/lateral_native_values.csv","wb");w=csv.writer(fo)
w.writerow(["element","variable","time_value","value","units"])
for path in dss.getCatalogedPathnames():
    parts=path.split("/")
    if parts[2] not in ["DIV_REACH_FP","FP_REACH","FP_MUCUM"]:continue
    series=dss.get(path)
    print("LATERAL_NATIVE_PATH",path,series.units,series.numberValues)
    for i in range(series.numberValues):
        val=float(series.values[i])
        if val>-1e20:w.writerow([parts[2],parts[3],int(series.times[i]),val,series.units])
fo.close();dss.close()
'''
    script=script.replace('Exit(0)',export+'\nExit(0)');(proj/'run.script').write_text(script)
    (proj/'output.dss').unlink(missing_ok=True);(proj/'hec_output_values.csv').unlink(missing_ok=True)
    cp=subprocess.run([str(hec),'-s',str(proj/'run.script')],cwd=hec.parent,capture_output=True,text=True,timeout=240)
    (dest/'compute.log').write_text(cp.stdout+'\n'+cp.stderr)
    if 'G040_E1_HINDCAST_COMPUTE_OK' not in cp.stdout:raise RuntimeError(cp.stdout[-3500:]+cp.stderr[-1500:])
    by=hms.read_output_csv(proj/'hec_output_values.csv');start=hms.utc(d['window']['start_utc']);end=hms.utc(d['window']['end_utc']);count=int((end-start).total_seconds()/180)+1
    for name in ['SRC_86472000','DIV_REACH_FP','FP_REACH','FP_MUCUM']+['J_'+c for c in hms.MAIN_CHECKPOINTS]:
        rr=by.get(name,[])
        if len(rr)!=count or rr[0][0]!=start or rr[-1][0]!=end or any(not np.isfinite(q) or q<0 for t,q in rr):raise RuntimeError('Incomplete native series '+name+' count '+str(len(rr)))
    raw=json.loads((hms.BASE/'historical_calibration_forcing/E24_NOV2023/hydro.json').read_text());strict=copy.deepcopy(raw)
    for c in strict['controls']:
        if str(c['code'])=='86510000':
            for r in c['recent_rows']:
                if r.get('level_source_unit') is None or r['level_source_unit']>1500:r['flow_m3s']=None
    axis=hms.hourly_axis(start,end);scores=hms.score_outputs(by,raw,axis,'86472000');sscores=hms.score_outputs(by,strict,axis,'86472000')
    sim=ind.model(proj/'hec_output_values.csv','86510000');pairs=ind.independent_pairs(sim,raw,'86510000',d['window']);m=ind.metrics(pairs)
    for k in ['nse','kge','pbias_pct','rmse_m3s']:
        if abs(m[k]-scores['86510000'][k])>1e-8:raise RuntimeError('Independent metric mismatch '+k)
    original=hms.source_hourly(raw,'86472000',axis);source=ast.literal_eval(next(l for l in script.splitlines() if l.startswith('source_values=')).split('=',1)[1])['86472000']
    source_delta=max(abs(a-b) for a,b in zip(original,source))
    if len(original)!=len(source) or source_delta>1e-10:raise RuntimeError('Source input was changed')
    peak_t,peak_q=max(sim,key=lambda z:z[1]);crest=hms.utc('2023-11-19T02:45:00Z');timing=(peak_t-crest).total_seconds()/3600
    rise=[(o,q) for t,o,q in pairs if 0<=(crest-t).total_seconds()<=24*3600];fall=[(o,q) for t,o,q in pairs if t>crest]
    m.update(strict_NSE=sscores['86510000']['nse'],peak_error_pct=100*(peak_q/max(o for t,o,q in pairs)-1),peak_time_minus_SGB_h=timing,
        rise_NMAE=sum(abs(o-q) for o,q in rise)/sum(o for o,q in rise),recession_NMAE=sum(abs(o-q) for o,q in fall)/sum(o for o,q in fall))
    rows=list(csv.DictReader((proj/'lateral_native_values.csv').open()));variables=sorted({r['variable'] for r in rows if r['element']=='DIV_REACH_FP'})
    audit=dict(native_values_per_series=count,unmodified_source_max_difference_m3s=source_delta,diversion_native_variables=variables,
        whole_reach_storage_measured=False,local_drone_storage_curve_changed=False,geometry_is_a_lumped_hypothesis=True,clock_shift_minutes=0)
    for element,inflow_key in [('FP_REACH',None),('FP_MUCUM','J_MUCUM_INFLOW')]:
        rr=sorted([r for r in rows if r['element']==element and r['variable']=='STORAGE'],key=lambda r:int(r['time_value']));unit=rr[0]['units'];factor=1000 if unit.upper().replace(' ','') in ['1000M3','THOUM3'] else 1
        if len(rr)!=count:raise RuntimeError('Storage count mismatch '+element)
        sv=np.array([float(r['value'])*factor for r in rr]);out=np.array([q for t,q in by[element]])
        if element=='FP_REACH':inp=p['fraction']*np.maximum(np.array([q for t,q in by['SRC_86472000']])-p['threshold_m3s'],0)
        else:inp=np.array([q for t,q in by[inflow_key]])
        residual=float(np.trapezoid(inp-out,dx=180)-(sv[-1]-sv[0]))
        if abs(residual)>max(100.,np.trapezoid(inp,dx=180)*1e-7):raise RuntimeError('Storage balance failed '+element+' '+str(residual))
        audit[element]=dict(storage_units=unit,storage_max_m3=float(sv.max()),storage_end_m3=float(sv[-1]),balance_residual_m3=residual)
    d.update(scores=scores,strict_scores=sscores,parameters_lateral=p,lateral_audit=audit,independent_metrics=m,upstream_boundary_overbank_storage_experiment=None,
        native_reach_capacity_m3=capacity,capacity_above_99pct_uses_emergency_return_to_river=capacity is not None)
    geo.save(dest/'result.json',d);geo.save(OUT/'native_verification.json',dict(metrics=m,audit=audit))
    print(json.dumps(dict(metrics=m,audit=audit),ensure_ascii=False))

if __name__=='__main__':main()
