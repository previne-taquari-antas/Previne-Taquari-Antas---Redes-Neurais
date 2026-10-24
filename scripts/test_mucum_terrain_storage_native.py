#!/usr/bin/env python3
"""Native HMS diagnostic of terrain-derived local storage, without Q editing.

Uses a Modified Puls reservoir immediately upstream of the Muçum output node.
The terrain controls storage; the archived dated ANA rating supplies discharge.
This lumped level-pool diagnostic is not a calibrated 1D/2D hydraulic solution.
"""
import argparse,copy,csv,json,re,shutil,subprocess,sys
from pathlib import Path
import numpy as np
import calibrate_event_members_v2 as v
import build_mucum_floodplain_storage as geo

def rating(stage):
    # Coefficients as returned by the dated ANA archive, equation in metres.
    # Do not use the incorrectly named derived h0_cm/h0_m columns in that CSV.
    return (134.9935*(stage-.83)**1.461 if stage<=5.99 else 31.3809*(stage+2.05)**1.85)

def prepare_curve(width=100):
    rows=list(csv.DictReader((geo.OUT/'curva_cota_area_volume.csv').open()))
    rows=[r for r in rows if float(r['channel_half_width_m'])==width and r['domain']=='upstream_of_gauge']
    curve=[(0.,0.,0.)]
    for r in rows:
        h=float(r['gauge_stage_m']);s=float(r['connected_floodplain_total_volume_m3']);q=rating(h)
        if s>curve[-1][0]+1e-5 and q>curve[-1][1]:curve.append((s,q,h))
    if len(curve)<5:raise RuntimeError('Not enough increasing storage-flow pairs')
    with (geo.OUT/'curva_armazenamento_descarga_HMS.csv').open('w',newline='') as fh:
        w=csv.writer(fh);w.writerow(['storage_m3','discharge_m3s','gauge_stage_m']);w.writerows(curve)
    return curve

def raw_clock_context(ctx):
    raw=ctx[0];full=copy.deepcopy(raw);strict=copy.deepcopy(raw)
    for c in strict['controls']:
        if str(c['code'])=='86510000':
            for row in c['recent_rows']:
                if row.get('level_source_unit') is None or row['level_source_unit']>1500:row['flow_m3s']=None
    crests={}
    for c in raw['controls']:
        code=str(c['code'])
        if code in ['86510000','86879300']:
            rr=[r for r in c['recent_rows'] if r.get('level_source_unit') is not None]
            peak=max(rr,key=lambda r:r['level_source_unit']);crests[code]=dict(time_utc=peak['time_utc'],level_source_unit=peak['level_source_unit'])
    # execute()'s legacy filename is kept for compatibility; its raw-clock
    # contents and the explicit provenance below prevent a hidden clock shift.
    v.save(v.OUT/'full_Q_clock_corrected.json',full);v.save(v.OUT/'strict_Q_domain.json',strict)
    v.save(v.OUT/'scoring_clock_manifest.json',dict(offset_minutes=0,archived_timestamps_unchanged=True,
        source_peak_BRT='2023-11-18T23:45:00-03:00',source_peak_UTC='2023-11-19T02:45:00Z',
        source_telemetry_peak_m=23.02,source_manual_gauge_peak_m=23.20,
        source='https://rigeo.sgb.gov.br/bitstreams/98db393c-19a5-4a87-9d29-46b3a2985e74/download',
        evidence='Published peak lies between the raw archive maxima at 02:00 and 03:00 UTC. The prior -105min QA assumption is not corroborated for this event.',
        note='Peak agreement supports the raw clock for November 2023; it is not proof of all hourly timestamps. Original series and prior QA105 outputs are preserved.'))
    return raw,full,strict,crests,ctx[4]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('hec');ap.add_argument('--rating-archive',type=Path,required=True)
    ap.add_argument('--raw-clock',action='store_true');ap.add_argument('--geometry-parameters',type=Path)
    ap.add_argument('--output-tag',default=None,help='Separate experiment folder; preserves previous native projects')
    args=ap.parse_args()
    if args.output_tag and (Path(args.output_tag).name!=args.output_tag or args.output_tag in ['.','..']):raise ValueError('Output tag must be a single folder name')
    v.OUT=geo.OUT/(args.output_tag or ('native_diagnostic_rawclock' if args.raw_clock else 'native_diagnostic'));ctx=v.prepare()
    if args.raw_clock:ctx=raw_clock_context(ctx)
    old=v.load(v.BASE/'event_members_v3_20261024/selection_manifest.json')
    p=dict(next(r for r in old['selected'] if r['target_code']=='86510000')['parameters'])
    # Confirm the two original curve segments and period before using them.
    rated=[r for r in csv.DictReader(args.rating_archive.open()) if r['valid_from']=='2023-09-06' and r['valid_to']=='2023-12-31']
    if len(rated)!=2:raise RuntimeError('Missing November 2023 dated official rating')
    expected=[(134.9935,.83,1.461),(31.3809,-2.05,1.85)]
    for row,values in zip(sorted(rated,key=lambda r:int(r['segment_number'])),expected):
        if any(abs(float(row[k])-a)>1e-8 for k,a in zip(['coefficient_a','coefficient_h0','coefficient_n'],values)):raise RuntimeError('Official rating coefficients changed')
    summary=dict(event_id=v.EVENT,geometry='local upstream drone footprint only',rating_archive_rows=rated,
        geometry_model_upstream_observations_unchanged=True,comparison_contains_modified_V3_reference=True,level_pool_is_a_diagnostic_hypothesis=True,
        storage_not_calibrated_to_target_hydrograph=True,models=[])
    geometry_parameters=v.load(args.geometry_parameters) if args.geometry_parameters else {k:val for k,val in p.items() if not k.startswith('overbank_')}
    summary['scoring_clock_offset_minutes']=0 if args.raw_clock else -105
    for name,params in [('V3_conceptual_reference',p),('unmodified_upstream_no_extra_storage',geometry_parameters)]:
        r=v.execute(args.hec,params,*ctx);r.update(name=name,target_code='86510000',target_name='Muçum');summary['models'].append(r)
        print(name,r['metrics']['86510000'],flush=True)
    base=summary['models'][1];bp=v.ROOT/base['result_file'];source=bp.parent/'project'
    curve=prepare_curve();store=[x[0] for x in curve];q=[x[1] for x in curve]
    native=v.OUT/'terrain_local_modified_puls';proj=native/'project'
    if proj.exists():shutil.rmtree(proj)
    shutil.copytree(source,proj);by=v.hms.read_output_csv(source/'hec_output_values.csv')
    initial_q=by['J_86510000'][0][1];initial_s=float(np.interp(initial_q,q,store))
    basin=(proj/'e1.basin').read_text().replace('J_86510000','J_MUCUM_INFLOW')
    junction_pattern=r'Junction: J_MUCUM_INFLOW\n.*?\nEnd:\n'
    if not re.search(junction_pattern,basin,re.S):raise RuntimeError('Expected Muçum junction not found')
    reservoir=f'''Junction: J_MUCUM_INFLOW
     Downstream: FP_MUCUM
End:

Reservoir: FP_MUCUM
     Description: Research local terrain-derived side-storage diagnostic; not a real dam
     Downstream: J_86510000
     Route: Modified Puls
     Routing Curve: Storage-Outflow
     Initial Storage: {initial_s/1000:.9f}
     Storage-Outflow Table: Mucum Terrain Storage Flow
End:

'''+v.hms.junction_block('J_86510000','R_86510000_JOIN_86595000',True)
    (proj/'e1.basin').write_text(re.sub(junction_pattern,lambda m:reservoir,basin,count=1,flags=re.S))
    pdata='''Paired Data Manager: g040_e1_hindcast
     Version: 4.13
     Filepath Separator: \\
End:

Table: Mucum Terrain Storage Flow
     Table Type: Storage-Outflow
     X-Units: THOU M3
     Y-Units: M3/S
     Use External DSS File: YES
     DSS File: terrain_geometry.dss
     Pathname: /MUCUM/FLOODPLAIN/STORAGE-FLOW///TABLE/
     Interpolation: Linear Interpolation
End:
'''
    (proj/'g040_e1_hindcast.pdata').write_text(pdata)
    # Build the paired data inside the same native Java/DSS runtime used by HMS.
    insert='''from hec.io import PairedDataContainer
pd=PairedDataContainer()
pd.fullName="/MUCUM/FLOODPLAIN/STORAGE-FLOW///TABLE/"
pd.numberCurves=1
pd.numberOrdinates=%d
pd.xOrdinates=%r
pd.yOrdinates=[%r]
pd.xunits="THOU M3"
pd.yunits="M3/S"
pd.xtype=""
pd.ytype=""
pd.labelsUsed=False
gdss=HecDss.open(project_dir+"/terrain_geometry.dss")
gdss.put(pd)
gdss.close()
'''%(len(curve),[s/1000 for s in store],q)
    script=(source/'run.script').read_text().replace(str(source),str(proj))
    script=script.replace('OpenProject("g040_e1_hindcast",project_dir)',insert+'\nOpenProject("g040_e1_hindcast",project_dir)')
    script=script.replace('Exit(1)','Exit(0)');(proj/'run.script').write_text(script)
    cp=subprocess.run([str(Path(args.hec).resolve()),'-s',str((proj/'run.script').resolve())],cwd=Path(args.hec).resolve().parent,capture_output=True,text=True,timeout=240)
    (native/'native_compute.log').write_text(cp.stdout+'\n'+cp.stderr)
    if 'G040_E1_HINDCAST_COMPUTE_OK' not in cp.stdout:raise RuntimeError(cp.stdout[-2500:]+cp.stderr[-1200:])
    by=v.hms.read_output_csv(proj/'hec_output_values.csv');d=v.load(bp);start=v.hms.utc(d['window']['start_utc']);end=v.hms.utc(d['window']['end_utc'])
    expected_count=int((end-start).total_seconds()/180)+1
    for c in v.hms.MAIN_CHECKPOINTS:
        values=by['J_'+c]
        if len(values)!=expected_count or values[0][0]!=start or values[-1][0]!=end or any(not np.isfinite(z) or z<0 for t,z in values):raise RuntimeError('Incomplete native output '+c)
    scores=v.hms.score_outputs(by,ctx[1],v.hms.hourly_axis(start,end),'86472000')
    strict=v.hms.score_outputs(by,ctx[2],v.hms.hourly_axis(start,end),'86472000')
    d.update(scores=scores,strict_scores=strict,compute_ok=True,upstream_boundary_overbank_storage_experiment=None,
        geometric_reservoir=dict(geometry_source='curva_cota_area_volume.csv',storage_units_in_HMS='THOU M3',storage_curve_volume_max_m3=max(store),
          input_source_Q_unchanged=True,channel_exclusion_half_width_m=100,initial_storage_m3=initial_s,initial_flow_m3s=initial_q,
          bed_and_bank_surveys_audited=False,level_pool_backwater_not_solved=True),native_output_contract=dict(complete=True,expected_values_per_checkpoint=expected_count))
    geo.save(native/'result.json',d)
    summary['models'].append(dict(name='local_terrain_Modified_Puls',result_file=str((native/'result.json').relative_to(v.ROOT)),scores=scores,strict_scores=strict,
        target_code='86510000',target_name='Muçum',parameters=base['parameters'],geometric_reservoir=d['geometric_reservoir']))
    geo.save(geo.OUT/'native_diagnostic_summary.json',summary)
    print('GEOMETRY_NATIVE_COMPUTE_OK',json.dumps(scores['86510000']),flush=True)

if __name__=='__main__':main()
