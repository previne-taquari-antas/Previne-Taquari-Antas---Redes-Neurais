#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestG040MultieventCalibrationContract(unittest.TestCase):
    def test_fixed_split_is_frozen(self):
        cfg = json.loads(
            (ROOT / "config/g040_stage2_execution_v1.json").read_text(encoding="utf-8")
        )
        split = cfg["fixed_benchmark_split"]
        self.assertEqual(split["calibration"], ["E22_SEP2023", "E24_NOV2023"])
        self.assertEqual(
            split["independent_validation"], ["E27_MAY2024", "E28_JUN2024"]
        )
        self.assertEqual(split["pseudo_operational_holdout"], ["E2026_JUL"])
        self.assertIn("Do not move validation/holdout", cfg["no_leakage_rule"])

    def test_historical_forcing_never_zero_fills(self):
        src = (
            ROOT / "scripts/build_g040_historical_calibration_forcing.py"
        ).read_text(encoding="utf-8")
        self.assertIn("missing remains missing; never zero-filled", src)
        self.assertIn("E22_SEP2023", src)
        self.assertIn("E24_NOV2023", src)

    def test_calibrator_uses_only_calibration_events_for_selection(self):
        src = (
            ROOT / "scripts/calibrate_hec_hms_g040_e1_multievent.py"
        ).read_text(encoding="utf-8")
        self.assertIn('CAL_EVENTS = ("E22_SEP2023", "E24_NOV2023")', src)
        self.assertIn('VALIDATION_EVENTS = ("E27_MAY2024", "E28_JUN2024")', src)
        self.assertIn("no_leakage", src)
        self.assertIn("parameter_freeze_rule", src)

    def test_rank_favors_two_events_over_single_event_overfit(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "g040_calibration", ROOT / "scripts/calibrate_hec_hms_g040_e1_multievent.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        concentrated = {
            "eligible_for_calibration_ranking": True,
            "calibration_events_with_gate": 1,
            "checkpoint_gate_pass_count": 4,
            "worst_event_penalty": 0.2,
            "mean_multi_metric_penalty": 0.2,
        }
        balanced = {
            "eligible_for_calibration_ranking": True,
            "calibration_events_with_gate": 2,
            "checkpoint_gate_pass_count": 2,
            "worst_event_penalty": 0.3,
            "mean_multi_metric_penalty": 0.3,
        }
        self.assertLess(mod.rank_key(balanced), mod.rank_key(concentrated))

    def test_penalty_accounts_for_hydrograph_slope(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "g040_calibration_penalty", ROOT / "scripts/calibrate_hec_hms_g040_e1_multievent.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        base = {
            "pairs": 48,
            "nse": 0.8,
            "kge": 0.8,
            "normalized_rmse": 0.3,
            "pbias_pct": 8,
            "peak_error_pct": 6,
            "peak_timing_error_h": 1,
            "rise_fall_sign_skill": 0.7,
            "mean_observed_m3s": 1000,
        }
        good = mod.metric_penalty({**base, "derivative_rmse_m3s_h": 50})
        poor = mod.metric_penalty({**base, "derivative_rmse_m3s_h": 500})
        self.assertLess(good, poor)

    def test_runner_accepts_event_specific_inputs(self):
        src = (
            ROOT / "scripts/run_hec_hms_g040_e1_hindcast.py"
        ).read_text(encoding="utf-8")
        for token in (
            "--event-id",
            "--rain-file",
            "--hydro-file",
            "--scenario-file",
            "--output-root",
        ):
            self.assertIn(token, src)


if __name__ == "__main__":
    unittest.main()
