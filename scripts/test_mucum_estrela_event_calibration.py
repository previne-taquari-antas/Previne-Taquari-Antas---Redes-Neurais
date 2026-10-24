#!/usr/bin/env python3
"""Consequential station-QA and native-model invariants for event calibration."""
import copy, json, unittest
from pathlib import Path
import calibrate_mucum_estrela_event_library as cal
import run_hec_hms_g040_e1_hindcast as hms
import refine_mucum_estrela_stage_consistency as review

class CalibrationTests(unittest.TestCase):
    def setUp(self):self.cfg=cal.load(cal.CONFIG)

    def test_station_qa_never_overwrites_forcing(self):
        raw={'controls':[{'code':'86510000','recent_rows':[
          {'time_utc':'2023-11-18T03:00:00Z','flow_m3s':100,'level_source_unit':1000},
          {'time_utc':'2023-11-18T04:00:00Z','flow_m3s':200,'level_source_unit':1600}]}]}
        original=copy.deepcopy(raw);q=cal.prepare_scoring(raw,self.cfg)
        self.assertEqual(raw,original)
        rows=q['controls'][0]['recent_rows']
        self.assertEqual(rows[0]['time_utc'],'2023-11-18T01:15:00Z')
        self.assertEqual(rows[0]['flow_m3s'],100)
        self.assertIsNone(rows[1]['flow_m3s'])

    def test_dated_clock_correction_does_not_shift_other_events(self):
        raw={'controls':[{'code':'86510000','recent_rows':[
          {'time_utc':'2023-09-04T03:00:00Z','flow_m3s':100,'level_source_unit':1000}]}]}
        self.assertEqual(cal.prepare_scoring(raw,self.cfg)['controls'][0]['recent_rows'][0]['time_utc'],'2023-09-04T03:00:00Z')

    def test_native_baseflow_explicit_and_scales_with_incremental_area(self):
        legacy=hms.subbasin_block('TEST',10,'J',34,71)
        self.assertIn('Baseflow: None',legacy)
        new=hms.subbasin_block('TEST',10,'J',34,71,(.14,.95,.15))
        self.assertIn('Baseflow: Recession',new)
        self.assertIn('Initial Flow/Area Ratio: 0.140000000',new)
        self.assertNotIn('Baseflow: None',new)

    def test_extreme_mucum_discharge_cannot_drive_parameter_selection(self):
        m=dict(nse=.9,kge=.9,pbias_pct=2,peak_error_pct=10,full_simulated_peak_time_utc='2023-11-19T00:15:00Z')
        crest={'time_utc':'2023-11-19T00:15:00Z'}
        a=cal.objective(m,'86510000',crest)
        b=cal.objective(dict(m,peak_error_pct=999),'86510000',crest)
        self.assertEqual(a,b)

    def test_historical_score_domain_and_reserved_events(self):
        self.assertEqual(self.cfg['event_id'],'E24_NOV2023')
        self.assertNotIn(self.cfg['event_id'],self.cfg['split']['reserved_event_transfer'])
        self.assertTrue(self.cfg['split']['do_not_retune_on_reserved_events'])

    def test_missing_Q_is_only_bounded_not_fabricated(self):
        raw={'controls':[{'code':'86879300','recent_rows':[
          {'time_utc':'2023-11-18T03:00:00Z','flow_m3s':2200,'level_source_unit':1400},
          {'time_utc':'2023-11-18T04:00:00Z','flow_m3s':3000,'level_source_unit':1500},
          {'time_utc':'2023-11-18T05:00:00Z','flow_m3s':None,'level_source_unit':1300},
          {'time_utc':'2023-11-18T06:00:00Z','flow_m3s':None,'level_source_unit':1600}]}]}
        original=copy.deepcopy(raw);bound=review.stage_bound(raw,'86879300')
        self.assertEqual(raw,original)
        self.assertEqual(bound['Q_upper_bound_m3s'],2200)
        self.assertEqual(bound['times_utc'],['2023-11-18T05:00:00Z'])

if __name__=='__main__':unittest.main()
