#!/usr/bin/env python3
"""Regression safeguards for frozen 2023 models tested on 2024 flood events."""
import json
import py_compile
import unittest
from pathlib import Path
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
