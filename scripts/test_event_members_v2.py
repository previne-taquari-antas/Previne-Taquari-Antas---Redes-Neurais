import unittest
import run_hec_hms_g040_e1_hindcast as h

class EventMembersTests(unittest.TestCase):
    def test_legacy_response_preserved(self):
        s=h.subbasin_block('A',10,'J',34,71)
        self.assertIn('LossRate: SCS',s);self.assertIn('Transform: SCS',s)
        self.assertNotIn('Initial Loss:',s)

    def test_native_initial_constant_clark_declares_hours(self):
        s=h.subbasin_block('A',10,'J',34,71,(.12,.98,.15),(25,12,18,8))
        self.assertIn('LossRate: Initial+Constant',s)
        self.assertIn('Initial Loss: 25.000000000',s)
        self.assertIn('Constant Loss Rate: 12.000000000',s)
        self.assertIn('Transform: Clark',s)
        self.assertIn('Time of Concentration: 18.000000000',s)
        self.assertIn('Storage Coefficient: 8.000000000',s)
        self.assertNotIn('Curve Number:',s)

    def test_calibrated_subreach_count_never_breaks_positive_coefficients(self):
        dt=h.COMPUTE_INTERVAL_MIN/60
        for k in [.03,.1,.5,2,5]:
            for x in [0,.05,.15,.3]:
                for preferred in [1,2,4,10]:
                    try:n=h.muskingum_steps(k,x,preferred=preferred)
                    except RuntimeError:continue
                    self.assertLessEqual(2*k*x/n,dt+1e-12)
                    self.assertGreaterEqual(2*k*(1-x)/n,dt-1e-12)

    def test_channel_storage_and_legacy_translation_are_distinct_models(self):
        self.assertEqual(h.muskingum_steps(4,0,preferred=1),1)
        self.assertEqual(h.muskingum_steps(4,0),80)

if __name__=='__main__':unittest.main()
