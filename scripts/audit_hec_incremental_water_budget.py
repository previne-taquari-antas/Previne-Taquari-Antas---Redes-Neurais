#!/usr/bin/env python3
"""Read native DSS components; check nonnegativity, sums and recharge scale.

This is not a catchment groundwater-storage validation. Initial groundwater
storage is not observed in the available project.
"""
import argparse,csv,json,subprocess
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
import numpy as np
import run_hec_hms_g040_e1_hindcast as hms

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'assets/data/hec_hms_g040_full_basin'
CAL=BASE/'mucum_estrela_event_calibration_20261024'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('hec');args=ap.parse_args()
    selected=json.loads((CAL/'selected_models.json').read_text())['selected'];results=[]
    rain=hms.rain_components(json.loads((BASE/'historical_calibration_forcing/E24_NOV2023/rain.json').read_text()))
    area={hms.hec_subbasin_name(cid):x['area_km2'] for cid,x in rain.items()}
    for row in selected:
        rp=ROOT/row['result_file'];d=json.loads(rp.read_text());proj=rp.parent/'project';out=rp.parent/'water_budget_native.csv'
        script=rp.parent/'water_budget.script'
        script.write_text('''from hms.model.JythonHms import *
from hec.heclib.dss import HecDss
import csv
dss=HecDss.open(%r)
fo=open(%r,"wb");w=csv.writer(fo);w.writerow(["element","variable","time_value","value","units"])
for path in dss.getCatalogedPathnames():
    p=path.split("/")
    if not p[2].startswith("SB_") or p[3] not in ["FLOW","FLOW-BASE","FLOW-DIRECT","PRECIP-LOSS-CUM"]:continue
    s=dss.get(path)
    for i in range(s.numberValues):
        v=float(s.values[i])
        if v>-1e20:w.writerow([p[2],p[3],int(s.times[i]),v,s.units])
fo.close();dss.close();Exit(0)
'''%(str(proj/'output.dss'),str(out)))
        p=subprocess.run([str(Path(args.hec).resolve()),'-s',str(script)],capture_output=True,text=True,cwd=Path(args.hec).resolve().parent,timeout=180)
        if p.returncode or not out.exists():raise RuntimeError(p.stderr[-1000:]+p.stdout[-1000:])
        by=defaultdict(dict);start=hms.utc(d['window']['start_utc']);end=hms.utc(d['window']['end_utc'])
        with out.open() as fh:
            for r in csv.DictReader(fh):
                t=hms.dss_time_to_utc(r['time_value'])
                if start<=t<=end:by[(r['element'],r['variable'])][t]=float(r['value'])
        rows=[]
        for element in sorted({e for e,v in by}):
            flow=by[element,'FLOW'];base=by[element,'FLOW-BASE'];direct=by[element,'FLOW-DIRECT'];loss=by[element,'PRECIP-LOSS-CUM']
            times=sorted(set(flow)&set(base)&set(direct))
            if len(times)<2:raise RuntimeError('missing native component series')
            if any((b-a).total_seconds()!=180 for a,b in zip(times,times[1:])):raise RuntimeError('native component time gap')
            base_depth=float(np.trapezoid([base[t] for t in times],dx=180)/(area[element]*1000))
            loss_depth=max(loss.values())
            residual=max(abs(flow[t]-base[t]-direct[t]) for t in times)
            min_flow=min([*flow.values(),*base.values(),*direct.values()])
            if min_flow < -1e-6 or residual>1e-5:raise RuntimeError('native flow-component conservation/nonnegativity failure')
            rows.append(dict(element=element,area_km2=area[element],baseflow_depth_mm=base_depth,
               cumulative_infiltration_loss_mm=loss_depth,baseflow_within_event_loss=base_depth<=loss_depth,
               max_abs_total_minus_direct_minus_base_m3s=residual,valid_3min_values=len(times)))
        results.append(dict(city=row['target_name'],run_id=row['run_id'],incremental_subbasins=rows,
          all_baseflow_volumes_below_event_losses=all(r['baseflow_within_event_loss'] for r in rows),
          initial_groundwater_storage_observed=False,
          interpretation='Necessary numerical and scale checks only; not validation of aquifer physics or initial storage'))
    (CAL/'native_water_budget_audit.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(results,ensure_ascii=False))

if __name__=='__main__':main()
