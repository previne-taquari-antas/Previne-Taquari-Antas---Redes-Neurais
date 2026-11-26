#!/usr/bin/env python3
"""Regression safeguards for frozen 2023 models tested on 2024 flood events."""
import json
import py_compile
import unittest
from pathlib import Path
from unittest.mock import patch
from importlib.util import spec_from_file_location, module_from_spec
ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"config/g040_frozen_2024_transfer_validation_v1.json"
SCRIPT=ROOT/"scripts/validate_g040_frozen_2024_transfer.py"

class TestFrozenTransfer(unittest.TestCase):
    def test_python_valid(self):
        py_compile.compile(str(SCRIPT),doraise=True)

    def test_frozen_split_and_three_distinct_members(self):
        j=json.loads(CFG.read_text(encoding="utf-8"))
        self.assertEqual(j["calibration_events"],["E22_SEP2023","E24_NOV2023"])
        self.assertEqual(j["validation_events"],["E27_MAY2024","E28_JUN2024"])
        self.assertEqual([m["id"] for m in j["candidate_members"]],
                         ["QMC_04","OVERBANK_02","OVERBANK_06"])
        self.assertFalse(j["allowed_future_observed_discharge_as_forcing"])
        self.assertTrue(j["frozen_before_validation"])
        self.assertFalse(j["promotion_allowed"])
        self.assertEqual(j["parameters"]["cn"],34.11993525)
        self.assertEqual(j["candidate_members"][1]["storage"]["threshold_m3s"],5000)
        self.assertEqual(j["candidate_members"][2]["storage"]["threshold_m3s"],7000)

    def test_validation_has_sufficient_source_observation_problem(self):
        spec=spec_from_file_location("frozen_transfer",SCRIPT)
        mod=module_from_spec(spec)
        spec.loader.exec_module(mod)
        may=mod.source_coverage("E27_MAY2024")
        june=mod.source_coverage("E28_JUN2024")
        self.assertEqual(may["actual_flow_observations"],77)
        self.assertEqual(june["actual_flow_observations"],0)
        self.assertFalse(may["direct_observed_boundary_eligible"])
        self.assertFalse(june["direct_observed_boundary_eligible"])


    def test_coverage_does_not_count_duplicate_invalid_or_outside_hours(self):
        spec=spec_from_file_location("frozen_transfer_coverage",SCRIPT)
        mod=module_from_spec(spec)
        spec.loader.exec_module(mod)
        raw={
            "window_local":{"start":"2024-05-01T00:00","end":"2024-05-01T02:59"},
            "stations":[{"code":"86472000","series":[
                {"time_utc":"2024-05-01T03:00:00Z","flow_m3s":100},
                {"time_utc":"2024-05-01T03:00:00Z","flow_m3s":110},
                {"time_utc":"2024-05-01T04:00:00Z","flow_m3s":120},
                {"time_utc":"2024-05-01T06:00:00Z","flow_m3s":130},
                {"time_utc":"2024-05-01T05:00:00Z","flow_m3s":-9},
                {"time_utc":"invalid","flow_m3s":140}
            ]}]
        }
        with patch.object(mod,"load",return_value=raw):
            result=mod.source_coverage("E27_MAY2024")
        self.assertEqual(result["actual_flow_observations"],2)
        self.assertEqual(result["raw_flow_records"],6)
        self.assertEqual(result["event_window_hours"],3)
        self.assertEqual(result["discarded_duplicate_invalid_or_out_of_window_records"],4)
        self.assertFalse(result["direct_observed_boundary_eligible"])

    def test_simulation_minimum_duration_is_a_separate_quality_gate(self):
        spec=spec_from_file_location("frozen_transfer_duration",SCRIPT)
        mod=module_from_spec(spec)
        spec.loader.exec_module(mod)
        cfg=json.loads(CFG.read_text(encoding="utf-8"))
        row={
            "compute_ok":True,
            "mucum":{"pairs":24,"observed_coverage_ratio":1.0,
                     "max_observed_gap_hours":0},
            "fraction_full_event_simulated":1.0,
            "recorded_event_crest_inside_simulated_window":True,
            "simulation_times_utc":{"hours":36},
        }
        inputs={"input_provenance":{"median_spatial_reporting_rain_gauges":5}}
        report=mod.score_quality(row,inputs,cfg)
        self.assertTrue(report["gates"]["simulated_at_least_70pct_of_full_event"])
        self.assertFalse(report["gates"]["simulated_minimum_absolute_hours"])
        self.assertFalse(report["research_evidence_quality_adequate"])
        row["simulation_times_utc"]["hours"]=72
        self.assertTrue(mod.score_quality(row,inputs,cfg)["research_evidence_quality_adequate"])

    def test_data_quality_and_hydrological_skill_are_separate(self):
        spec=spec_from_file_location("frozen_transfer_skill",SCRIPT)
        mod=module_from_spec(spec)
        spec.loader.exec_module(mod)
        cfg=json.loads(CFG.read_text(encoding="utf-8"))
        row={
            "compute_ok":True,
            "mucum":{"pairs":312,"nse":0.82,"kge":0.82,
                     "pbias_pct":-0.4,"peak_error_pct":23.8,
                     "peak_timing_error_h":-3.0,
                     "observed_coverage_ratio":1.0,
                     "max_observed_gap_hours":0},
            "fraction_full_event_simulated":1.0,
            "recorded_event_crest_inside_simulated_window":True,
            "simulation_times_utc":{"hours":312},
        }
        inputs={"input_provenance":{"median_spatial_reporting_rain_gauges":43}}
        evidence=mod.score_quality(row,inputs,cfg)
        skill=mod.retrospective_skill(row)
        self.assertTrue(evidence["research_evidence_quality_adequate"])
        self.assertFalse(skill["meets_all_descriptive_skill_criteria"])
        self.assertFalse(skill["checks"]["absolute_peak_error_at_most_20_pct"])
        self.assertFalse(skill["operational_forecast_validated"])
        self.assertFalse(skill["selection_or_retuning_using_2024"])
        row["mucum"]["peak_error_pct"]=5.0
        row["mucum"]["pbias_pct"]=-24.66
        self.assertFalse(mod.retrospective_skill(row)["meets_all_descriptive_skill_criteria"])
        row["mucum"]["pbias_pct"]=-5.0
        self.assertTrue(mod.retrospective_skill(row)["meets_all_descriptive_skill_criteria"])
        row["mucum"]["peak_timing_error_h"]=None
        self.assertFalse(mod.retrospective_skill(row)["meets_all_descriptive_skill_criteria"])

    def test_deployment_forbidden_and_weather_not_forecast(self):
        text=SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"--score-hydro-file"',text)
        self.assertIn('score_hydro_file',text)
        self.assertIn('observed_rainfall_across_entire_validation_event',text)
        self.assertIn('forecast_skill_demonstrated',text)
        self.assertIn('"promotion_allowed":False',text)
        self.assertIn('"no_2024_parameter_retuning":True',text)

if __name__=="__main__":
    unittest.main()
