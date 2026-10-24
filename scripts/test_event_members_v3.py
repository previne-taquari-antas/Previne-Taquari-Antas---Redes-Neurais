"""Regression cases from the native refinement and publication gate."""
import copy,json,unittest
from pathlib import Path
import improve_event_members_v3 as s
from finalize_event_members_v3 import acceptable

class NativeRefinementTests(unittest.TestCase):
    def setUp(self):
        self.seeds=json.loads((s.V2/'selection_manifest.json').read_text())['selected']

    def test_short_muskingum_reach_rejects_infeasible_low_travel_time(self):
        p=dict(next(r for r in self.seeds if r['target_code']=='86879300')['parameters'])
        self.assertTrue(s.numerically_feasible(p))
        # This corner of the broad search range cannot supply positive stable
        # coefficients on every short reach at the fixed 3min compute interval.
        p.update(k_g1=.8,k_g2=.4,k_g3=.5,k_g4=.8)
        self.assertFalse(s.numerically_feasible(p))

    def test_full_nse_cannot_hide_worse_recession_or_rise(self):
        c='86510000';b=copy.deepcopy(self.seeds[0]);b['refinement_metrics']={'full_nmae':.04,'strict_nmae':.06,'rise_nmae':.03,'recession_nmae':.04}
        r=copy.deepcopy(b);r['metrics'][c]['full_Q_nse']+=.0001
        r['refinement_metrics']['recession_nmae']=.08
        self.assertFalse(acceptable(r,b))
        r['refinement_metrics']['recession_nmae']=.03;r['metrics'][c]['rising_limb_nmae']*=1.2
        self.assertFalse(acceptable(r,b))

    def test_low_stage_contradiction_blocks_estrela_member(self):
        c='86879300';b=copy.deepcopy(self.seeds[1]);b['refinement_metrics']={'full_nmae':.06,'strict_nmae':.06,'rise_nmae':.05,'recession_nmae':.08}
        r=copy.deepcopy(b);r['low_stage_constraint']={'pass_with_10pct_model_tolerance':False}
        self.assertFalse(acceptable(r,b))

if __name__=='__main__':unittest.main()
