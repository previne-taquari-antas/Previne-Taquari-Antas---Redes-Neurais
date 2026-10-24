#!/usr/bin/env python3
"""Read-only diagnostic of frozen 2024 transfer results; no calibration or promotion."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "assets/data/hec_hms_g040_full_basin"
SOURCE = BASE / "g040_frozen_2024_transfer_validation_latest.json"
OUTPUT = BASE / "g040_frozen_2024_timing_quality_diagnostic.csv"

def diagnose(payload):
    assert payload["no_2024_parameter_retuning"] is True
    assert payload["promotion_allowed"] is False
    assert payload["independent_forecast_validation_passed"] is False
    rows = []
    for event in payload["validation_events"]:
        provenance = event.get("input_provenance") or {}
        candidates = event.get("candidate_results") or []
        baseline = next((r for r in candidates if r.get("model_id") == "QMC_04"), None)
        bm = (baseline or {}).get("mucum") or {}
        for member in candidates:
            metrics = member.get("mucum") or {}
            quality = member.get("verification_quality") or {}
            gates = quality.get("gates") or {}
            lag = metrics.get("peak_timing_error_h")
            peak = metrics.get("peak_error_pct")
            baseline_peak = bm.get("peak_error_pct")
            rows.append({
                "event": event["event_id"],
                "model": member.get("model_id"),
                "computed": member.get("compute_ok"),
                "NSE": metrics.get("nse"),
                "KGE": metrics.get("kge"),
                "PBIAS_pct": metrics.get("pbias_pct"),
                "peak_error_pct": peak,
                "peak_timing_error_h": lag,
                "peak_early": lag is not None and lag < 0,
                "peak_error_reduction_vs_QMC_pp": (
                    round(abs(baseline_peak) - abs(peak), 4)
                    if baseline_peak is not None and peak is not None else None),
                "observed_pairs": metrics.get("pairs"),
                "observed_coverage": metrics.get("observed_coverage_ratio"),
                "largest_observed_gap_h": metrics.get("max_observed_gap_hours"),
                "full_event_simulated_fraction": member.get("fraction_full_event_simulated"),
                "recorded_crest_inside_window": member.get("recorded_event_crest_inside_simulated_window"),
                "median_rain_gauges": provenance.get("median_spatial_reporting_rain_gauges"),
                "rain_spatial_gate": gates.get("rain_gauge_spatial_proxy"),
                "all_quality_gates": quality.get("research_evidence_quality_adequate"),
                "failed_gates": ";".join(k for k, ok in gates.items() if not ok),
                "storage_max_m3": member.get("storage_max_m3"),
                "research_only": True,
                "forecast_skill_validated": False,
            })
    return rows

def main():
    if not SOURCE.exists():
        raise SystemExit(f"Missing results: {SOURCE}; run frozen hindcast first")
    rows = diagnose(json.loads(SOURCE.read_text(encoding="utf-8")))
    if not rows:
        raise SystemExit("No candidate results to diagnose")
    with OUTPUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"output": str(OUTPUT), "rows": len(rows),
                      "timing_issues": [r for r in rows if r["peak_early"]],
                      "failed_quality_gates": [r for r in rows if not r["all_quality_gates"]]},
                     ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
