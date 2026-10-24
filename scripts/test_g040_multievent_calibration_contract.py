#!/usr/bin/env python3
import json
import unittest
from datetime import datetime, timedelta
from importlib.util import spec_from_file_location, module_from_spec
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

    def test_station_audit_counts_only_unique_event_hours(self):
        script = ROOT / "scripts/build_g040_historical_calibration_forcing.py"
        spec = spec_from_file_location("historical_rain_station_audit", script)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        t0 = datetime(2024, 6, 15)
        hours = [t0 + timedelta(hours=i) for i in range(3)]
        warmup = t0 - timedelta(days=1)
        candidates = {
            "A": {"code": "A", "name": "Station A", "network": "ANA"},
            "B": {"code": "B", "name": "Station B", "network": "CEMADEN"},
            "C": {"code": "C", "name": "Station C", "network": "INMET"},
        }
        stations = [
            {**candidates["A"], "archive_contributed": True},
            {**candidates["B"], "archive_contributed": True},
        ]
        series = {"A": {warmup: 9.0, hours[0]: 0.0, hours[2]: 4.0},
                  "B": {warmup: 3.0}}
        audit = mod.summarize_event_station_support(candidates, stations, series, hours)
        self.assertEqual(audit["candidate_station_count"], 3)
        self.assertEqual(audit["stations_reporting_at_least_one_event_hour"], 1)
        self.assertEqual(audit["reporting_stations_by_network"], {"ANA": 1})
        self.assertEqual(audit["station_hourly_support"][0]["hours_in_event"], 2)
        self.assertEqual(audit["candidate_codes_without_any_event_hour"], ["B", "C"])
        self.assertEqual(audit["stations_reporting_at_least_75pct_event_hours"], 0)

    def test_entirely_missing_rain_hours_count_as_spatially_sparse(self):
        script = ROOT / "scripts/build_g040_historical_calibration_forcing.py"
        spec = spec_from_file_location("historical_rain_missing_hours", script)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        t0 = datetime(2024, 6, 15)
        hours = [t0 + timedelta(hours=i) for i in range(3)]
        from unittest.mock import patch
        support = [{"component_id": "G040_TEST", "local_area_km2": 1.0}]
        with patch.object(mod, "read_support", return_value=support):
            components, diag = mod.component_forcing([], {}, hours, [])
        self.assertEqual(diag["hours_with_fewer_than_4_stations"], 3)
        self.assertEqual(diag["hours_without_any_station"], 3)
        self.assertEqual(diag["hours_with_any_station"], 0)
        self.assertEqual(components[0]["available_hours"], 0)

    def test_ana_cache_isolated_by_historical_event_window(self):
        # 2023/09 and 2023/11 must trigger distinct ANA requests for one
        # station in the SAME process; a second call for the same window
        # should reuse its cached response.
        from unittest.mock import patch
        source = ROOT / "scripts/build_mucum_observed_multistation.py"
        spec = spec_from_file_location("mucum_rain_cache_isolation", source)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        sep_start = datetime(2023, 9, 1)
        sep_end = datetime(2023, 9, 12, 23)
        nov_start = datetime(2023, 11, 15)
        nov_end = datetime(2023, 11, 25, 23)
        def rows_for_window(_raw, start, end):
            return [{"time_local": start, "rain_mm": 1.0,
                     "flow_m3s": None, "level": None}]
        with (patch.object(mod, "ANA_CACHE", {}),
              patch.object(mod, "request_bytes", return_value=b"<response/>") as request,
              patch.object(mod, "parse_ana_xml", side_effect=rows_for_window)):
            sep = mod.fetch_ana("86472600", sep_start, sep_end)
            nov = mod.fetch_ana("86472600", nov_start, nov_end)
            sep_repeated = mod.fetch_ana("86472600", sep_start, sep_end)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(sep["rows"][0]["time_local"], sep_start)
            self.assertEqual(nov["rows"][0]["time_local"], nov_start)
            self.assertEqual(sep_repeated, sep)
            urls = [call.args[0] for call in request.call_args_list]
            self.assertIn("2023", urls[0])
            self.assertNotEqual(urls[0], urls[1])

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

    def test_long_observation_outage_cannot_pass_calibration_gate(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location(
            "g040_quality_gate",ROOT/"scripts/calibrate_hec_hms_g040_e1_multievent.py"
        )
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        strong={
            "pairs":198, "nse":0.95,"pbias_pct":0,
            "peak_error_pct":1, "peak_timing_error_h":0,
            "rise_fall_sign_skill":0.99,
            "observed_coverage_ratio":198/288,
            "max_observed_gap_hours":90.0,
        }
        self.assertFalse(mod.checkpoint_gate(strong))
        strong["observed_coverage_ratio"]=1.0
        strong["max_observed_gap_hours"]=0.0
        self.assertTrue(mod.checkpoint_gate(strong))

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
