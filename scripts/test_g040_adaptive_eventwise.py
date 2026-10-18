#!/usr/bin/env python3
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"assets/data/hec_hms_g040_full_basin"

class TestAdaptiveEventwise(unittest.TestCase):
    def test_contract_forbids_single_parameter_collapse(self):
        j=json.loads((ROOT/"config/g040_adaptive_eventwise_selection_v1.json").read_text(encoding="utf-8"))
        self.assertIn("Do not replace",j["no_single_parameter_rule"])
        self.assertFalse(j["selector"]["hard_pick"])
        self.assertEqual(j["selector"]["top_k"],3)

    def test_builder_generates_target_event_rows(self):
        subprocess.run([sys.executable,"-B",str(ROOT/"scripts/build_g040_target_event_parameter_library.py")],check=True,cwd=ROOT)
        j=json.loads((BASE/"g040_target_event_parameter_library_latest.json").read_text(encoding="utf-8"))
        rows=j["hec_target_event_candidates"]
        self.assertTrue(all(x.get("forecast_selection_eligible") is False for x in rows))
        self.assertTrue(all(x.get("independent_transfer_validation_passed") is False for x in rows))
        self.assertTrue(any(x["target_code"]=="86510000" and x["event_id"]=="E22_SEP2023" for x in rows))
        self.assertTrue(any(x["target_code"]=="86720000" and x["event_id"]=="E24_NOV2023" for x in rows))
        self.assertGreaterEqual(len(j["existing_mucum_eventwise_library"]),9)
        if (BASE/"g040_target_event_refinement_latest.json").exists():
            self.assertGreater(j["coverage"]["refined_target_event_rows_used"],0)
            self.assertTrue(any(x.get("selection_source")=="target_event_refinement" for x in rows))

    def test_real_observation_gaps_restrict_historical_eventwise_claims(self):
        from importlib.util import spec_from_file_location,module_from_spec
        spec=spec_from_file_location("model_bank",
            ROOT/"scripts/build_g040_target_event_parameter_library.py")
        mod=module_from_spec(spec)
        spec.loader.exec_module(mod)
        sep=mod.observed_evidence("E22_SEP2023","86510000")
        nov=mod.observed_evidence("E24_NOV2023","86510000")
        self.assertEqual(sep["observed_Q_hours"],198)
        self.assertEqual(sep["event_window_hours"],288)
        self.assertEqual(sep["maximum_internal_Q_gap_hours"],90)
        self.assertIn("observed_Q_gap_over_6h",sep["blockers"])
        self.assertEqual(nov["observed_Q_hours"],238)
        self.assertEqual(nov["rain_median_valid_gauges_per_hour"],3)
        self.assertIn("sparse_rain_gauges_for_spatial_calibration",nov["blockers"])

    def test_selector_keeps_fallback_and_never_hard_picks(self):
        subprocess.run([sys.executable,"-B",str(ROOT/"scripts/select_g040_adaptive_scenario.py")],check=True,cwd=ROOT)
        j=json.loads((BASE/"g040_adaptive_scenario_latest.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(j["targets"]),8)
        for t in j["targets"]:
            self.assertFalse(t["hard_parameter_pick"])
            self.assertIn("fallback",t)
            self.assertIn("confidence_before_data_quality_cap",t)
            self.assertFalse(t["operational_selection_approved"])
            self.assertEqual(t["roster_status"],"suggested_candidates_not_executed")
            self.assertNotEqual(t["confidence"],"high")
            self.assertLessEqual(len(t["research_comparison_roster"]),4)
            for candidate in t["top_analogs"]:
                self.assertEqual(candidate["weight_interpretation"],
                                 "relative_scenario_similarity_not_forecast_probability")
                self.assertFalse(candidate["independent_transfer_validation_passed"])
            if t["top_analogs"]:
                self.assertGreaterEqual(len(t["research_comparison_roster"]),1)
        rain=j["live_fingerprint"]["rain"]
        self.assertIn("freshness",rain)
        self.assertIn("forcing_age_hours",rain["freshness"])
        self.assertIn("latest_observed_rain_utc",rain["freshness"])
        self.assertTrue(
            rain["forecast_24h_basin_mm"] is None or rain["forecast_24h_basin_mm"] >= 0
        )
        self.assertTrue(j["governance"]["pseudo_operational_validation_required"])

if __name__=="__main__":
    unittest.main()
