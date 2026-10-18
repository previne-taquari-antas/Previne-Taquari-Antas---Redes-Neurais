#!/usr/bin/env python3
"""Isolated floodplain-storage hypothesis experiment for G040/Muçum.

This is a *conceptual* off-channel storage sensitivity for the reach downstream
of observed 86472000. The HEC-HMS core still routes each candidate downstream.
No observed discharge is overwritten on disk, and calibration years only.

A successful numerical run is NOT validation of reservoir geometry, flooding
volumes, or a production-ready forecast.
"""
from __future__ import annotations
import csv, json, math, sys
from datetime import datetime,timezone
from pathlib import Path
try:
    from scripts import calibrate_hec_hms_g040_e1_multievent as cal
except ImportError:
    import calibrate_hec_hms_g040_e1_multievent as cal

OUT=cal.BASE/"g040_mucum_overbank_sensitivity_latest.json"
OUTCSV=cal.BASE/"g040_mucum_overbank_sensitivity_candidates.csv"
KEYS=("nse","kge","pbias_pct","volume_error_pct","peak_error_pct",
      "peak_timing_error_h","pairs","observed_missing_hours","full_simulated_peak_m3s",
      "full_peak_observation_status","full_simulated_peak_time_utc")

def vals(run,code="86510000"):
    m=(run.get("scores") or {}).get(code) or {}
    return {k:m.get(k) for k in KEYS}

def design(frozen):
    reference=dict(frozen,candidate_id="OVERBANK_REFERENCE")
    rows=[reference]
    n=0
    for bankfull in (5000,7000):
        for fraction in (0.35,0.65):
            for tau in (6,12):
                n+=1
                rows.append(dict(frozen,
                    candidate_id=f"OVERBANK_{n:02d}",
                    overbank_threshold_m3s=bankfull,
                    overbank_fraction=fraction,
                    overbank_release_tau_h=tau,
                ))
    return rows

def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: run_g040_overbank_sensitivity.py /path/to/hec-hms.sh")
    j=json.loads(cal.OUT.read_text(encoding="utf-8"))
    anchor=j.get("best_calibration_candidate") or {}
    params=anchor.get("parameters")
    if not params:
        raise RuntimeError("No frozen candidate parameters")
    rows=design(params)
    results=[]
    for i,row in enumerate(rows,1):
        print(f"[{i}/{len(rows)}] overbank candidate {row['candidate_id']}",flush=True)
        events=[]
        for eid in cal.CAL_EVENTS:
            try:
                e=cal.run_event(sys.argv[1],row,eid)
            except Exception as ex:
                e={"event_id":eid,"compute_ok":False,"error":str(ex)}
            events.append({
                "event_id":eid,"compute_ok":bool(e.get("compute_ok")),
                "mucum":vals(e),
                "all_checkpoint_scores":e.get("scores"),
                "storage":e.get("upstream_boundary_overbank_storage_experiment"),
                "error":e.get("error"),
            })
        results.append({
            "candidate_id":row["candidate_id"],
            "parameters":{k:row.get(k) for k in
                ("cn","lag_min","k_g1","k_g2","k_g3","k_g4","x",
                 "overbank_threshold_m3s","overbank_fraction","overbank_release_tau_h")},
            "both_computed":all(x["compute_ok"] for x in events),
            "events":events,
        })
    baseline=results[0]
    b=next((x["mucum"] for x in baseline["events"] if x["event_id"]=="E24_NOV2023"),{})
    out=[]
    for row in results:
        events={x["event_id"]:x for x in row["events"]}
        v=(events.get("E24_NOV2023") or {}).get("mucum") or {}
        sept=(events.get("E22_SEP2023") or {}).get("mucum") or {}
        baseline_nse=b.get("nse"); baseline_peak=b.get("peak_error_pct")
        if v.get("nse") is not None and baseline_nse is not None and v.get("peak_error_pct") is not None and baseline_peak is not None:
            nse_delta=v["nse"]-baseline_nse
            peak_err_improvement=abs(baseline_peak)-abs(v["peak_error_pct"])
            # Report numerical improvement only if calibration-fit shape and
            # peak accuracy both improve in E24 and volume/timing stay reasonable.
            better=bool(nse_delta>=-0.02 and peak_err_improvement>=4
                and abs(v.get("peak_timing_error_h") or 0)<=3
                and abs(v.get("pbias_pct") or 0)<=20)
        else:
            nse_delta=None; peak_err_improvement=None; better=False
        row["comparison_to_reference"]={
            "november_nse_delta":nse_delta,
            "november_absolute_peak_error_reduction_percentage_points":peak_err_improvement,
            "meets_provisional_E24_numerical_improvement_rule":better,
            "E22_full_peak_m3s":sept.get("full_simulated_peak_m3s"),
            "E22_full_peak_observation_status":sept.get("full_peak_observation_status"),
        }
        out.append(row)
    payload={
        "schema_version":"g040_mucum_overbank_sensitivity_v1",
        "generated_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "status":"RESEARCH_DIAGNOSTIC_NO_PROMOTION",
        "research_only":True,
        "physical_hypothesis":"temporary off-channel floodplain storage downstream of 86472000; exact causal mass-conserving hourly linear reservoir; HEC-HMS downstream routing unchanged",
        "not_a_measured_storage_curve":True,
        "candidate_count":len(out),
        "calibration_events":list(cal.CAL_EVENTS),
        "independent_validation_events_not_used":list(cal.VALIDATION_EVENTS),
        "reference":baseline,
        "provisional_E24_improvements":[r["candidate_id"] for r in out if r["comparison_to_reference"]["meets_provisional_E24_numerical_improvement_rule"]],
        "candidates":out,
        "limitations":[
            "No direct stage-area-volume relation or LiDAR floodplain storage geometry is used",
            "Do not interpret a higher NSE on E22 paired hours as correction of its 90h missing discharge crest",
            "Must validate on E27 and E28 before any production change",
            "Event windows start before overtopping; initial off-channel storage is assumed zero",
            "Boundary Q is routed through a conceptual storage module before entering HEC-HMS and is not physically observed after this transformation",
        ],
        "promotion_allowed":False,
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with OUTCSV.open("w",encoding="utf-8",newline="") as fh:
        w=csv.writer(fh);w.writerow(["candidate","threshold_m3s","divert_fraction","tau_h","nov_nse","nov_peak_error_pct","nov_lag_h","nov_pbias_pct","nov_storage_max_m3","sept_full_peak_m3s","sept_full_peak_observed","numerical_improvement_E24"])
        for r in out:
            events={x["event_id"]:x for x in r["events"]}
            sep=events.get("E22_SEP2023") or {}
            nov=events.get("E24_NOV2023") or {}
            a=sep.get("mucum") or {};b=nov.get("mucum") or {}
            w.writerow([r["candidate_id"],r["parameters"]["overbank_threshold_m3s"],r["parameters"]["overbank_fraction"],r["parameters"]["overbank_release_tau_h"],b.get("nse"),b.get("peak_error_pct"),b.get("peak_timing_error_h"),b.get("pbias_pct"),(nov.get("storage") or {}).get("maximum_storage_m3"),a.get("full_simulated_peak_m3s"),a.get("full_peak_observation_status"),r["comparison_to_reference"]["meets_provisional_E24_numerical_improvement_rule"]])
    print(json.dumps({"computed":sum(r["both_computed"] for r in out),"total":len(out),
          "provisional_improvements":payload["provisional_E24_improvements"]},ensure_ascii=False),flush=True)
    return 0 if all(r["both_computed"] for r in out) else 2

if __name__=="__main__":
    raise SystemExit(main())
