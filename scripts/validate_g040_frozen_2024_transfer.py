#!/usr/bin/env python3
"""Frozen E27/E28 HEC-HMS event-transfer validation, without parameter tuning.

These are *retrospective, observed-rainfall-forced hindcasts* (not forecasts).
The upstream 86472000 flow in E27 is too sparse and absent in E28; use the
already-frozen Prata+Antas upper rainfall/runoff model instead.  The original
observed discharge is retained for scoring and never used for forcing.  The
two experimental overbank variants are conceptual, not validated storage curves.
"""
from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import build_g040_causal_upper_antas as upper
    from scripts import calibrate_hec_hms_g040_e1_multievent as cal
except ImportError:
    import build_g040_causal_upper_antas as upper
    import calibrate_hec_hms_g040_e1_multievent as cal

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"assets/data/hec_hms_g040_full_basin"
CONF=ROOT/"config/g040_frozen_2024_transfer_validation_v1.json"
OUT=BASE/"g040_frozen_2024_transfer_validation_latest.json"
OUTCSV=BASE/"g040_frozen_2024_transfer_validation_scores.csv"
PREP=BASE/"g040_frozen_2024_validation_inputs"
METRICS=("pairs","nse","kge","pbias_pct","peak_error_pct","peak_timing_error_h",
         "observed_coverage_ratio","observed_missing_hours","max_observed_gap_hours",
         "full_simulated_peak_m3s","full_peak_observation_status","volume_error_scope")

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def save(p,j):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def source_coverage(eid):
    raw=load(BASE/"historical_hydro_events"/f"{eid}.json")
    st=next((s for s in raw.get("stations") or [] if str(s.get("code"))=="86472000"),{})
    start,end=upper.local_to_utc(raw["window_local"]["start"]),upper.local_to_utc(raw["window_local"]["end"])
    hours=int((end-start).total_seconds()/3600)+1
    # Coverage means *unique valid hourly instants inside this event window*;
    # duplicate rows, out-of-window data and malformed/negative Q cannot count.
    valid_hours=set()
    raw_flow_records=0
    for row in st.get("series") or []:
        if row.get("flow_m3s") is None or not row.get("time_utc"):
            continue
        raw_flow_records+=1
        try:
            t=datetime.fromisoformat(str(row["time_utc"]).replace("Z","+00:00"))
            q=float(row["flow_m3s"])
        except (ValueError,TypeError,OverflowError):
            continue
        if t.tzinfo is None or not math.isfinite(q) or q<0:
            continue
        t=t.astimezone(timezone.utc)
        if start<=t<=end and t.minute==0 and t.second==0 and t.microsecond==0:
            valid_hours.add(t)
    n=len(valid_hours)
    return {"station":"86472000","actual_flow_observations":n,
            "raw_flow_records":raw_flow_records,
            "discarded_duplicate_invalid_or_out_of_window_records":raw_flow_records-n,
            "event_window_hours":hours,"observed_coverage_ratio":n/max(hours,1),
            "direct_observed_boundary_eligible":n>=0.95*hours}

def build_event_inputs(eid,cfg):
    rain_file=cal.FORCING/eid/"rain.json"
    orig_hydro=cal.FORCING/eid/"hydro.json"
    scenario=cal.FORCING/eid/"scenario.json"
    if not all(p.exists() for p in (rain_file,orig_hydro,scenario)):
        raise RuntimeError("E27/E28 forcing package not generated")
    frozen=load(ROOT/cfg["upstream_frozen_model"])
    if frozen.get("calibration_events")!=cfg["calibration_events"] or not frozen.get("no_validation_leakage"):
        raise RuntimeError("upper Antas donor not frozen exclusively on 2023")
    if (cfg["allowed_future_observed_discharge_as_forcing"] is not False
        or cfg["weather_mode"]!="retrospective_observed_rain_not_operational_forecast"):
        raise RuntimeError("2024 observed Q leakage / weather provenance contract failed")
    axis,prata,antas=upper.calibration_rain(eid)
    pred=upper.simulate_upper(
        prata,antas,upper.params_from_dict(frozen["parameters"]),upper.areas())
    if len(pred)!=len(axis) or any(not math.isfinite(x) or x<0 for x in pred):
        raise RuntimeError("upstream rainfall-runoff boundary invalid")
    package=deepcopy(load(orig_hydro))
    controls=[x for x in package.get("controls") or [] if str(x.get("code"))!="86472000"]
    controls.append({
        "code":"86472000","label":"2023-frozen simulated Prata+Antas boundary",
        "role":"primary_upstream_modelled_reconstruction",
        "fetch_ok":False,
        "modelled_not_observed":True,
        "recent_rows":[
            {"time_utc":upper.iso(t),"flow_m3s":round(float(q),6),
             "source":"2023_frozen_upper_antas_rainfall_runoff"}
            for t,q in zip(axis,pred)
        ],
    })
    package["controls"]=controls
    package["source"]="frozen_2023_upper_antas_modelled_boundary"
    package["research_only"]=True
    package["primary_future_observed_Q_used"]=False
    package["weather_inputs_use_full_historical_event"]=True
    package["forecast_skill_demonstrated"]=False
    dest=PREP/eid/"hydro_modelled_upstream.json"
    save(dest,package)
    rain=load(rain_file)
    med=(rain.get("rain_diagnostics") or {}).get("median_valid_station_count")
    return {
        "rain_file":rain_file,"hydro_file":dest,"score_hydro_file":orig_hydro,
        "scenario_file":scenario,
        "input_provenance":{
            "upstream":"frozen_2023_calibrated_rainfall_runoff",
            "upstream_model_sha_not_reestimated":True,
            "observed_Q_used_in_forcing":False,
            "weather":"observed_rainfall_across_entire_validation_event",
            "weather_is_future_known_for_realtime_forecast":False,
            "upper_rain_covered_hours":len(axis),
            "upper_model_full_peak_m3s":max(pred),
            "upstream_archived_observation_coverage":source_coverage(eid),
            "median_spatial_reporting_rain_gauges":med,
            "rain_quality_warning":"fewer_than_4_gauges" if med is None or med<4 else None,
        },
    }

def run_member(hec,eid,member,p,cfg):
    mid=member["id"]
    command=[sys.executable,"-B",str(cal.RUNNER),hec,
        "--candidate-id",f"FROZEN_2024_{mid}__{eid}",
        "--event-id",eid,
        "--rain-file",str(p["rain_file"]),
        "--hydro-file",str(p["hydro_file"]),
        "--score-hydro-file",str(p["score_hydro_file"]),
        "--scenario-file",str(p["scenario_file"]),
        "--output-root",str(PREP/"hec_runs"),
    ]
    for key,flag in (("cn","--cn"),("lag_min","--lag-min"),
                     ("k_g1","--k-g1"),("k_g2","--k-g2"),("k_g3","--k-g3"),
                     ("k_g4","--k-g4"),("x","--x")):
        command.extend([flag,str(cfg["parameters"][key])])
    st=member.get("storage")
    if st:
        command.extend([
            "--overbank-threshold-m3s",str(st["threshold_m3s"]),
            "--overbank-fraction",str(st["diverted_fraction"]),
            "--overbank-release-tau-h",str(st["release_tau_h"]),
        ])
    run_id=f"FROZEN_2024_{mid}__{eid}"
    log=PREP/f"{run_id}.log"
    try:
        p0=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=600,check=False)
        log.write_text(p0.stdout[-20000:]+"\nSTDERR:\n"+p0.stderr[-8000:],encoding="utf-8")
        result_path=PREP/"hec_runs"/run_id/"result.json"
        if not result_path.exists():
            raise RuntimeError(f"runner return={p0.returncode}; result missing; stderr={p0.stderr[-1200:]}")
        j=load(result_path)
        if p0.returncode!=0 or not j.get("compute_ok"):
            raise RuntimeError(f"HEC unsuccessful return={p0.returncode}: {j.get('error')}")
        metrics=(j.get("scores") or {}).get("86510000") or {}
        if int(metrics.get("pairs") or 0)<4:
            raise RuntimeError("too few Muçum observations to score")
        s=(j.get("upstream_boundary_overbank_storage_experiment") or {})
        window=j.get("window") or {}
        expected=int((load(p["rain_file"]).get("window") or {}).get("hours") or 0)
        window_hours=int(window.get("hours") or 0)
        complete_fraction=window_hours/expected if expected else 0.0
        observed_target=next((c for c in load(p["score_hydro_file"]).get("controls") or []
                              if str(c.get("code"))=="86510000"),{})
        observed_records=[
            x for x in observed_target.get("recent_rows") or []
            if x.get("flow_m3s") is not None and x.get("time_utc")
        ]
        valid_obs=[
            (float(x["flow_m3s"]),datetime.fromisoformat(
             str(x["time_utc"]).replace("Z","+00:00")))
            for x in observed_records if math.isfinite(float(x["flow_m3s"]))
        ]
        max_obs_time=max(valid_obs,key=lambda x:x[0])[1] if valid_obs else None
        begin=datetime.fromisoformat(str(window["start_utc"]).replace("Z","+00:00"))
        end=datetime.fromisoformat(str(window["end_utc"]).replace("Z","+00:00"))
        recorded_crest_in_simulation=bool(
            max_obs_time and begin<=max_obs_time<=end
        )
        return {
            "model_id":mid,"event_id":eid,"compute_ok":True,
            "mucum":{k:metrics.get(k) for k in METRICS},
            "stations":{code:{k:m.get(k) for k in METRICS}
                for code,m in (j.get("scores") or {}).items()},
            "storage_max_m3":s.get("maximum_storage_m3"),
            "mass_balance_error_m3":s.get("mass_balance_error_m3"),
            "simulation_times_utc":window,
            "fraction_full_event_simulated":complete_fraction,
            "recorded_event_crest_inside_simulated_window":recorded_crest_in_simulation,
            "rain_observed_full_event_not_forecast":True,
            "evaluation_uses_2024_Q_only_for_scoring":True,
            "log":str(log.relative_to(ROOT)),
        }
    except Exception as exc:
        return {"model_id":mid,"event_id":eid,"compute_ok":False,
                "error":str(exc),"log":str(log.relative_to(ROOT))}

def score_quality(row,inputs,config):
    q=config["verification_quality"]
    m=row.get("mucum") or {}
    checks={
        "HEC_computed":bool(row.get("compute_ok")),
        "has_enough_observed_pairs":int(m.get("pairs") or 0)>=q["min_score_pairs"],
        "observed_Q_coverage":(m.get("observed_coverage_ratio") or 0)>=q["min_target_observed_coverage"],
        "no_long_observation_gap":(
            m.get("max_observed_gap_hours") is not None
            and m["max_observed_gap_hours"]<=q["max_internal_missing_observed_hours"]
        ),
        "rain_gauge_spatial_proxy":(
            inputs["input_provenance"].get("median_spatial_reporting_rain_gauges") or 0
        )>=q["min_median_rain_gauges_per_hour"],
        "simulated_at_least_70pct_of_full_event":(
            row.get("fraction_full_event_simulated") or 0
        )>=q["min_target_observed_coverage"],
        "simulated_minimum_absolute_hours":(
            (row.get("simulation_times_utc") or {}).get("hours") or 0
        )>=q["min_simulated_window_hours"],
        "recorded_crest_inside_simulation":bool(
            row.get("recorded_event_crest_inside_simulated_window")
        ),
    }
    # Observed Q and meteorological quality cannot be rescued by good NSE.
    return {"gates":checks,"research_evidence_quality_adequate":all(checks.values()),
            "independent_operational_forecast_validated":False}

def retrospective_skill(row):
    """Fixed descriptive 2023-calibration thresholds, NOT forecast validation.

    Data availability passes are independent of hydrograph accuracy. These
    limits are declared for transparent comparison, never model selection or
    retuning against the independent 2024 validation events.
    """
    m = row.get("mucum") or {}
    limits = {
        "nse_min": 0.50,
        "absolute_pbias_pct_max": 20.0,
        "absolute_peak_error_pct_max": 20.0,
        "absolute_peak_timing_error_h_max": 3.0,
    }
    def good(key):
        try:
            value = float(m.get(key))
            return value if math.isfinite(value) else None
        except (TypeError, ValueError):
            return None
    nse, pbias, peak, lag = (
        good("nse"), good("pbias_pct"), good("peak_error_pct"),
        good("peak_timing_error_h")
    )
    checks = {
        "nse_at_least_0_50": nse is not None and nse >= limits["nse_min"],
        "absolute_PBIAS_at_most_20_pct": (
            pbias is not None and abs(pbias) <= limits["absolute_pbias_pct_max"]
        ),
        "absolute_peak_error_at_most_20_pct": (
            peak is not None and abs(peak) <= limits["absolute_peak_error_pct_max"]
        ),
        "absolute_peak_timing_at_most_3h": (
            lag is not None and abs(lag) <= limits["absolute_peak_timing_error_h_max"]
        ),
    }
    return {
        "diagnostic_thresholds": limits,
        "criteria_source": "2023 calibration checkpoint_gate; retrospective description only",
        "checks": checks,
        "meets_all_descriptive_skill_criteria": bool(row.get("compute_ok")) and all(checks.values()),
        "retrospective_hindcast_not_forecast": True,
        "selection_or_retuning_using_2024": False,
        "operational_forecast_validated": False,
    }

def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: validate_g040_frozen_2024_transfer.py PATH_TO_HEC_HMS_SH")
    config=load(CONF)
    assert config["frozen_before_validation"] and config["promotion_allowed"] is False
    assert config["validation_events"]==["E27_MAY2024","E28_JUN2024"]
    PREP.mkdir(parents=True,exist_ok=True)
    candidates=config["candidate_members"]
    out=[]
    for eid in config["validation_events"]:
        try:
            inputs=build_event_inputs(eid,config)
        except Exception as exc:
            out.append({"event_id":eid,"status":"UNTESTABLE_MISSING_OR_INVALID_FORCING",
                        "error":str(exc),"source_observation_coverage":source_coverage(eid),
                        "candidate_results":[]})
            print(f"{eid} blocked: {exc}",flush=True)
            continue
        rr=[]
        for member in candidates:
            print(f"2024 transfer {eid}: {member['id']}",flush=True)
            row=run_member(sys.argv[1],eid,member,inputs,config)
            row["verification_quality"]=score_quality(row,inputs,config)
            row["retrospective_skill"]=retrospective_skill(row)
            rr.append(row)
        out.append({"event_id":eid,"status":"COMPUTED" if all(r["compute_ok"] for r in rr)
                    else "PARTIALLY_COMPUTED", "input_provenance":inputs["input_provenance"],
                    "candidate_results":rr})
    evaluated=[r for event in out for r in event.get("candidate_results") or []]
    any_computed=any(r.get("compute_ok") for r in evaluated)
    all_adequate=(
        len(out)==len(config["validation_events"])
        and all(
            event.get("status")=="COMPUTED"
            and len(event.get("candidate_results") or [])==len(candidates)
            and all(
                (r.get("verification_quality") or {}).get("research_evidence_quality_adequate")
                for r in event["candidate_results"]
            )
            for event in out
        )
    )
    failed_gates=sorted({
        gate
        for r in evaluated
        for gate,passed in ((r.get("verification_quality") or {}).get("gates") or {}).items()
        if not passed
    })
    skill_passing=[
        r for r in evaluated
        if (r.get("retrospective_skill") or {}).get("meets_all_descriptive_skill_criteria")
    ]
    skill_failures=sorted({
        key
        for r in evaluated
        for key,passed in ((r.get("retrospective_skill") or {}).get("checks") or {}).items()
        if not passed
    })
    payload={
        "schema_version":"g040_frozen_2024_transfer_validation_v1",
        "generated_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "status":(
            "RESEARCH_HISTORICAL_EVENT_TRANSFER_QUALITY_GATES_PASSED"
            if all_adequate else
            "RESEARCH_HISTORICAL_EVENT_TRANSFER_COMPUTED_QUALITY_BLOCKED"
            if any_computed else "RESEARCH_HISTORICAL_EVENT_TRANSFER_UNTESTABLE"
        ),
        "research_evidence_quality_adequate":all_adequate,
        "evaluated_candidate_event_runs":len(evaluated),
        "quality_adequate_candidate_event_runs":sum(
            bool((r.get("verification_quality") or {}).get("research_evidence_quality_adequate"))
            for r in evaluated
        ),
        "failed_quality_gates":failed_gates,
        "evidence_gate_scope":"observation coverage, rainfall station count and simulated window, NOT hydrological skill",
        "retrospective_hydrological_skill_status":(
            "ALL_MEMBERS_MEET_DESCRIPTIVE_SKILL_GATES"
            if len(skill_passing)==len(evaluated) and bool(evaluated)
            else "SOME_MEMBERS_FAIL_DESCRIPTIVE_SKILL_GATES"
        ),
        "retrospective_skill_passing_candidate_event_runs":len(skill_passing),
        "retrospective_skill_failed_gates":skill_failures,
        "skill_gate_scope":"NSE/PBIAS/crest magnitude and timing; 2023 calibration-style thresholds, descriptive only",
        "research_only":True,
        "frozen_parameters_provenance":config["source_artifact"],
        "frozen_member_parameters":config["candidate_members"],
        "frozen_common_parameters":config["parameters"],
        "weather_mode":"RETROSPECTIVE_OBSERVED_RAIN_HINDCAST_NOT_PSEUDO_OPERATIONAL_FORECAST",
        "no_validation_event_Q_used_for_model_selection_or_forcing":True,
        "no_2024_parameter_retuning":True,
        "validation_events":out,
        "comparison_policy":"Report each member independently; never select a winner or retune using E27/E28",
        "independent_forecast_validation_passed":False,
        "promotion_allowed":False,
        "next_step":"Evaluate fixed models with exact archived ECMWF issued at t0; verify physically plausible temporary storage using LiDAR and valley geometry",
    }
    save(OUT,payload)
    with OUTCSV.open("w",encoding="utf-8",newline="") as fh:
        w=csv.writer(fh)
        w.writerow(["event","candidate","computed","NSE","KGE","PBIAS_pct","peak_error_pct",
                    "peak_timing_error_h","pairs","Q_coverage","max_Q_gap_h",
                    "max_storage_m3","enough_evidence","retrospective_skill_all_gates","retrospective_skill_failed_gates","error"])
        for e in out:
            for r in e.get("candidate_results") or []:
                m=r.get("mucum") or {}
                w.writerow([e["event_id"],r["model_id"],r["compute_ok"],
                    *[m.get(k) for k in ("nse","kge","pbias_pct","peak_error_pct",
                      "peak_timing_error_h","pairs","observed_coverage_ratio",
                      "max_observed_gap_hours")],r.get("storage_max_m3"),
                      r["verification_quality"]["research_evidence_quality_adequate"],
                      r["retrospective_skill"]["meets_all_descriptive_skill_criteria"],
                      ";".join(k for k,ok in r["retrospective_skill"]["checks"].items() if not ok),
                      r.get("error")])
    print(json.dumps({"status":payload["status"],"events":[{
        "event":x["event_id"],"status":x["status"],"computed":sum(y["compute_ok"] for y in x.get("candidate_results",[])),
        "errors":[y.get("error") for y in x.get("candidate_results",[]) if not y["compute_ok"]]
    } for x in out]},ensure_ascii=False),flush=True)
    return 0 if any_computed else 2

if __name__=="__main__":
    raise SystemExit(main())
