#!/usr/bin/env python3
"""Research-only Muskingum attenuation sensitivity near Muçum.

Change only the physically interpretable reach routing K for g1 and the
Muskingum X weighting, retaining rainfall, CN, source hydrographs, event
windows, and all other routing parameters. Tests whether additional
channel storage can attenuate the peak without degrading timing or
other stations. This is NOT a calibration promotion.

No timestamp shifts, synthetic discharge or rainfall scaling.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import calibrate_hec_hms_g040_e1_multievent as cal
except ImportError:
    import calibrate_hec_hms_g040_e1_multievent as cal

BASE=cal.BASE
OUT=BASE/"g040_e1_mucum_routing_sensitivity_latest.json"
OUTCSV=BASE/"g040_e1_mucum_routing_sensitivity_candidates.csv"

def finite(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):
        return None

def simple_metric(result,code="86510000"):
    m=(result.get("scores") or {}).get(code) or {}
    return {k:m.get(k) for k in (
        "pairs","observed_coverage_ratio","max_observed_gap_hours",
        "nse","kge","pbias_pct","peak_error_pct","peak_timing_error_h",
        "full_simulated_peak_m3s","full_simulated_peak_time_utc",
        "full_peak_observation_status","full_peak_relative_to_recorded_observed_peak_pct",
    )}

def design(base):
    # Constant CN + SCS lag, variable only channel travel/storage.
    # K is hours across the g1 group, roughly 44km between 86472000 and Muçum.
    # 5 to 12 hours spans ~2.4 to 1.0 m/s average wave celerity.
    rows=[{**base,"candidate_id":"ROUTING_FROZEN_REFERENCE"}]
    n=0
    for k in (7.5,10.0,12.0):
        for x in (0.05,0.10,0.20):
            n+=1
            rows.append({**base,"candidate_id":f"ROUTING_G1_{n:02d}",
                         "k_g1":k,"x":x})
    return rows

def primary_score(events):
    """Conservative score: E24 physically checkable; E22 gap is diagnostic.

    Do not treat unobserved E22 peak as correctly reproduced simply because
    a parameter set has a strong NSE on the recorded portion.
    """
    by={e["event_id"]:e for e in events}
    if not all(by.get(c,{}).get("compute_ok") for c in cal.CAL_EVENTS):
        return None
    e24=simple_metric(by["E24_NOV2023"])
    if not e24.get("pairs") or e24["pairs"]<200:
        return None
    if e24.get("nse") is None:
        return None
    terms=[
        max(0.0,1-e24["nse"]),
        abs(finite(e24.get("pbias_pct")) or 0)/100,
        abs(finite(e24.get("peak_error_pct")) or 0)/100,
        abs(finite(e24.get("peak_timing_error_h")) or 0)/12,
    ]
    # Rank ONLY with complete enough E24 observations; never assert that a
    # good score constitutes independent validation.
    return sum(terms)/len(terms)

def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: run_g040_reach_attenuation_sensitivity.py HEC_HMS_SH")
    benchmark=json.loads(cal.OUT.read_text(encoding="utf-8"))
    best=benchmark.get("best_calibration_candidate")
    if not best:
        raise RuntimeError("multi-event frozen candidate unavailable")
    base=deepcopy(best["parameters"])
    rows=design(base)
    runs=[]
    for idx,row in enumerate(rows,1):
        print(f"[{idx}/{len(rows)}] {row['candidate_id']}",flush=True)
        events=[]
        for event_id in cal.CAL_EVENTS:
            try:
                j=cal.run_event(sys.argv[1],row,event_id)
            except Exception as exc:
                j={"event_id":event_id,"compute_ok":False,"error":str(exc)}
            events.append(j)
        runs.append({
            "candidate_id":row["candidate_id"],
            "parameters":{k:row[k] for k in
                ("cn","lag_min","k_g1","k_g2","k_g3","k_g4","x")},
            "compute_ok":all(e.get("compute_ok") for e in events),
            "research_penalty_e24_only":primary_score(events),
            "events":[{
                "event_id":e.get("event_id"),
                "compute_ok":e.get("compute_ok"),
                "mucum":simple_metric(e),
                "all_checkpoint_scores":e.get("scores"),
                "error":e.get("error"),
            } for e in events]
        })
    ranked=sorted(runs,key=lambda r:(
        r["research_penalty_e24_only"] is None,
        float("inf") if r["research_penalty_e24_only"] is None
            else r["research_penalty_e24_only"],
    ))
    ref=next((r for r in runs if r["candidate_id"]=="ROUTING_FROZEN_REFERENCE"),None)
    leader=ranked[0] if ranked else None
    payload={
        "schema_version":"g040_mucum_routing_sensitivity_v1",
        "generated_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "status":"RESEARCH_DIAGNOSTIC_NO_PROMOTION",
        "hypothesis":"Increase physically bounded g1 Muskingum travel/storage while holding rainfall-runoff constant",
        "reach_group":"g1; approximately 44 km through Muçum",
        "fixed_calibration_events":list(cal.CAL_EVENTS),
        "E22_caveat":"90 hours without observed Muçum discharge, including the uncertain flood crest",
        "E24_caveat":"Sparse spatial rainfall observational support",
        "design":"frozen reference plus 3 g1 K * 3 X, no event-specific parameter changes",
        "frozen_reference":ref,
        "best_diagnostic_candidate":leader,
        "candidates":ranked,
        "promotion_allowed":False,
        "independent_validation_performed":False,
        "decision_rule":"Do not promote without independently validating E27/E28 and reconciling E22 gauge/rating/timing",
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with OUTCSV.open("w",encoding="utf-8",newline="") as fh:
        w=csv.writer(fh)
        w.writerow(["candidate","g1_k_h","x","E24_penalty","E22_nse","E22_full_peak_m3s",
                    "E22_peak_obs_status","E24_nse","E24_peak_error_pct","E24_lag_h","E24_pbias_pct"])
        for r in ranked:
            by={e["event_id"]:e.get("mucum") or {} for e in r["events"]}
            a=by.get("E22_SEP2023",{}); b=by.get("E24_NOV2023",{})
            w.writerow([r["candidate_id"],r["parameters"]["k_g1"],r["parameters"]["x"],
                r["research_penalty_e24_only"],a.get("nse"),a.get("full_simulated_peak_m3s"),
                a.get("full_peak_observation_status"),b.get("nse"),b.get("peak_error_pct"),
                b.get("peak_timing_error_h"),b.get("pbias_pct")])
    print(json.dumps({"candidates":len(ranked),"best":None if leader is None else leader["candidate_id"],
                      "reference":None if ref is None else ref["research_penalty_e24_only"],
                      "leader_penalty":None if leader is None else leader["research_penalty_e24_only"]},ensure_ascii=False))
    return 0 if any(r["compute_ok"] for r in runs) else 2

if __name__=="__main__":
    raise SystemExit(main())
