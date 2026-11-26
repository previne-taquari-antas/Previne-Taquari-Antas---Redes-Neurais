#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"scripts/run_hec_hms_g040_e1_hindcast.py"
spec=importlib.util.spec_from_file_location("g040e1",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestNumerics(unittest.TestCase):
    def test_overbank_storage_conserves_mass_and_is_causal(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location(
            "overbank",ROOT/"scripts/g040_overbank_storage.py")
        ob=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ob)
        q=[700.0]*8+[8000.0]*8+[700.0]*30
        args=dict(threshold_m3s=5000,diverted_fraction=0.65,
                  release_tau_h=12.0)
        out,audit=ob.route_overbank(q,**args)
        self.assertEqual(len(out),len(q))
        self.assertGreater(max(q),max(out))
        self.assertAlmostEqual(sum(q)*3600,sum(out)*3600+
                               audit["remaining_storage_m3"],delta=0.5)
        self.assertLess(audit["maximum_storage_m3"],4e8)
        qfuture=q[:20]+[9999.0]*26
        changed,_=ob.route_overbank(qfuture,**args)
        self.assertEqual(out[:20],changed[:20])
        self.assertTrue(all(v>=0 for v in out))
        self.assertEqual(out[:8],q[:8])

    def test_overbank_zero_fraction_keeps_original_observed_flow(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location(
            "overbank_zero",ROOT/"scripts/g040_overbank_storage.py")
        ob=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ob)
        q=[120.0,8000.0,1200.0]
        out,audit=ob.route_overbank(q,threshold_m3s=1000,
                                     diverted_fraction=0,
                                     release_tau_h=6)
        self.assertEqual(out,q)
        self.assertAlmostEqual(audit["remaining_storage_m3"],0)

    def test_interval_is_three_minutes(self):
        self.assertEqual(m.COMPUTE_INTERVAL_MIN,3)
        from datetime import datetime, timezone
        s=m.build_control(datetime(2023,9,1,tzinfo=timezone.utc),datetime(2023,9,2,tzinfo=timezone.utc))
        self.assertIn("Time Interval: 3",s)

    def test_scs_interval_gate_for_min_search_lag(self):
        self.assertLessEqual(m.COMPUTE_INTERVAL_MIN,0.29*15.847934)

    def test_muskingum_steps_make_coefficients_nonnegative(self):
        dt=m.COMPUTE_INTERVAL_MIN/60.0
        for k in (0.05,0.14,0.20,0.5,1.5,3.0,6.0,12.0):
            for x in (0.10,0.20,0.30):
                try:
                    n=m.muskingum_steps(k,x)
                except RuntimeError:
                    # Some broad search-edge combinations are intentionally
                    # rejected when no stable representation exists within
                    # the HEC-HMS accepted subreach range.
                    continue
                self.assertLessEqual(n,m.MAX_MUSKINGUM_SUBREACHES)
                ks=k/n
                self.assertLessEqual(2*ks*x-1e-12,dt)
                self.assertLessEqual(dt,2*ks*(1-x)+1e-12)

    def test_anchor_long_reach_is_stable_within_hec_limit(self):
        n=m.muskingum_steps(6.0,0.2)
        self.assertLessEqual(n,100)
        dt=m.COMPUTE_INTERVAL_MIN/60.0
        ks=6.0/n
        self.assertLessEqual(2*ks*0.2-1e-12,dt)
        self.assertLessEqual(dt,2*ks*(1-0.2)+1e-12)

    def test_all_anchor_reaches_are_stable_at_three_minutes(self):
        class A:
            k_g1=3.5; k_g2=1.5; k_g3=5.0; k_g4=6.0; x=0.2
        dt=m.COMPUTE_INTERVAL_MIN/60.0
        for name,_up,_down,length,group in m.REACHES:
            k=m.route_k(length,group,A)
            n=m.muskingum_steps(k,A.x)
            ks=k/n
            self.assertLessEqual(n,m.MAX_MUSKINGUM_SUBREACHES,name)
            self.assertLessEqual(2*ks*A.x-1e-12,dt,name)
            self.assertLessEqual(dt,2*ks*(1-A.x)+1e-12,name)

    def test_hourly_forcing_is_not_falsely_resampled_to_three_minutes(self):
        src=Path(m.__file__).read_text(encoding="utf-8")
        self.assertIn('c.interval=60',src)
        self.assertIn('t.add(60)',src)
        self.assertIn('Time Interval: {COMPUTE_INTERVAL_MIN}',src)


    def test_observed_interpolation_never_bridges_an_outage(self):
        from datetime import datetime, timedelta, timezone
        a=datetime(2023,9,1,0,0,tzinfo=timezone.utc)
        rows=[(a,100.0),(a+timedelta(minutes=30),130.0),
              (a+timedelta(hours=4),400.0)]
        self.assertAlmostEqual(m.interp(rows,a+timedelta(minutes=15)),115.0)
        self.assertIsNone(m.interp(rows,a+timedelta(hours=1)))
        self.assertIsNone(m.interp(rows,a+timedelta(hours=2)))
        self.assertEqual(m.interp(rows,a+timedelta(hours=4)),400.0)

    def test_e22_scoring_uses_only_recorded_mucum_discharge(self):
        # Replays must not count 90 missing historical hours as observations.
        from datetime import timedelta, timezone
        from unittest.mock import patch
        data=ROOT/"assets/data/hec_hms_g040_full_basin/historical_calibration_forcing/E22_SEP2023/hydro.json"
        self.assertTrue(data.is_file(),"Historical hydro package should be committed")
        import json
        hydro=json.loads(data.read_text(encoding="utf-8"))
        _,series=m.series_control(hydro,"86510000")
        start=series[0][0]; end=series[-1][0]
        axis=m.hourly_axis(start,end)
        observed=m.target_hourly(hydro,"86510000",axis)
        self.assertEqual(len(axis),288)
        self.assertEqual(len(observed),198)
        # Simulated discharge covers the whole HEC window, not the observed gaps.
        predicted={"J_86510000":[(t,1000.0) for t in axis]}
        with patch.object(m,"MAIN_CHECKPOINTS",["86510000"]):
            scores=m.score_outputs(predicted,hydro,axis)
        mu=scores["86510000"]
        self.assertEqual(mu["pairs"],198)
        self.assertEqual(mu["observed_missing_hours"],90)
        self.assertEqual(mu["observed_gap_count"],1)
        self.assertEqual(mu["max_observed_gap_hours"],90.0)
        self.assertEqual(mu["valid_hourly_slope_pairs"],196)
        self.assertEqual(mu["volume_error_scope"],"paired_hours_only")

    def test_full_hydrograph_peak_is_not_hidden_by_missing_observations(self):
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch
        start=datetime(2023,9,4,0,0,tzinfo=timezone.utc)
        axis=[start+timedelta(hours=i) for i in range(7)]
        # Synthetic observation has a three-hour outage around the flood crest.
        observed=[100.0,120.0,None,None,None,140.0,110.0]
        hydropkg={"controls":[{"code":"86510000","recent_rows":[
            {"time_utc":t.isoformat(),"flow_m3s":q}
            for t,q in zip(axis,observed) if q is not None
        ]}]}
        simulated=[100.0,125.0,180.0,700.0,340.0,142.0,115.0]
        out_by={"J_86510000":list(zip(axis,simulated))}
        with patch.object(m,"MAIN_CHECKPOINTS",["86510000"]):
            score=m.score_outputs(out_by,hydropkg,axis)["86510000"]
        self.assertEqual(score["pairs"],4)
        self.assertEqual(score["full_simulated_peak_m3s"],700.0)
        self.assertEqual(score["full_peak_observation_status"],
                         "FULL_SIMULATED_PEAK_HAS_NO_NEARBY_OBSERVATION")
        self.assertEqual(score["max_observed_gap_hours"],3.0)
        self.assertLess(score["simulated_peak_m3s"],200.0)

    def test_dss_time_conversion_preserves_project_timezone(self):
        from datetime import datetime, timezone
        # 2023-09-01 00:00 local BRT must become 03:00 UTC.
        local=datetime(2023,9,1,0,0)
        minutes=int((local-m.DSS_EPOCH).total_seconds()/60)
        self.assertEqual(
            m.dss_time_to_utc(minutes),
            datetime(2023,9,1,3,0,tzinfo=timezone.utc),
        )

if __name__=="__main__":
    unittest.main()
