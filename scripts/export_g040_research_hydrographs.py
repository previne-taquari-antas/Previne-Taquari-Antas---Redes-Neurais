#!/usr/bin/env python3
"""Export time-aligned observed vs complete simulated hydrographs from research HEC runs.

Includes missing observations as empty cells rather than interpolating them.
Saved only as isolated GitHub Actions artifacts, never to the public forecast.
"""
from __future__ import annotations
import csv, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import calibrate_hec_hms_g040_e1_multievent as cal
from scripts import run_hec_hms_g040_e1_hindcast as runner

OUT=cal.BASE/"g040_research_hydrograph_exports"

def export(candidate_id:str,event_id:str):
    candidate_dir=cal.RUNROOT/f"{candidate_id}__{event_id}"
    sim_file=candidate_dir/"project"/"hec_output_values.csv"
    if not sim_file.exists():
        return {"candidate_id":candidate_id,"event_id":event_id,
                "status":"MISSING_HMS_OUTPUT","path":str(sim_file)}
    sim=runner.read_output_csv(sim_file)
    hydro_file=cal.FORCING/event_id/"hydro.json"
    forcing=cal.FORCING/event_id/"rain.json"
    hydro=json.loads(hydro_file.read_text(encoding="utf-8"))
    rain=json.loads(forcing.read_text(encoding="utf-8"))
    window=rain["window"]
    from datetime import datetime, timezone
    a=datetime.fromisoformat(window["start_local"]).replace(tzinfo=runner.BRT).astimezone(timezone.utc)
    b=datetime.fromisoformat(window["end_local"]).replace(tzinfo=runner.BRT).astimezone(timezone.utc)
    times=runner.hourly_axis(a,b)
    out=OUT/f"{candidate_id}__{event_id}.csv"
    exported=0
    with out.open("w",encoding="utf-8",newline="") as fh:
        w=csv.writer(fh)
        w.writerow(["candidate_id","event_id","station_code","time_utc",
                    "observed_m3s","simulated_m3s","observation_present"])
        for code in runner.MAIN_CHECKPOINTS:
            sim_hourly=dict(sim.get("J_"+code) or [])
            try:
                obs=runner.target_hourly(hydro,code,times)
            except Exception:
                obs={}
            for t in times:
                qs=sim_hourly.get(t)
                if qs is None:
                    continue
                qo=obs.get(t)
                w.writerow([candidate_id,event_id,code,
                    t.isoformat().replace("+00:00","Z"),
                    "" if qo is None else round(qo,3),round(float(qs),3),
                    0 if qo is None else 1])
                exported+=1
    return {"candidate_id":candidate_id,"event_id":event_id,
            "status":"EXPORTED","rows":exported,"path":str(out)}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    j=json.loads(cal.OUT.read_text(encoding="utf-8"))
    best=j.get("best_calibration_candidate") or {}
    ids=[best.get("candidate_id")]
    sens=cal.BASE/"g040_e1_mucum_routing_sensitivity_latest.json"
    if sens.exists():
        d=json.loads(sens.read_text(encoding="utf-8"))
        row=d.get("best_diagnostic_candidate") or {}
        ids.append(row.get("candidate_id"))
    ids=[x for x in dict.fromkeys(ids) if x]
    rows=[]
    for cand in ids:
        for event in cal.CAL_EVENTS:
            rows.append(export(cand,event))
    (OUT/"manifest.json").write_text(json.dumps({
        "research_only":True,
        "status":"RESEARCH_HYDROGRAPH_EXPORT",
        "observation_handling":"Do not interpolate through measured discharge gaps",
        "records":rows
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"exports":rows},ensure_ascii=False))
    return 0 if any(x["status"]=="EXPORTED" for x in rows) else 2

if __name__=="__main__":
    raise SystemExit(main())
