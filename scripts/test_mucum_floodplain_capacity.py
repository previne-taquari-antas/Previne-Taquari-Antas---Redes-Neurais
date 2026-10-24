"""Physical bookkeeping tests: connectivity, NoData and upstream attribution."""
import unittest
import numpy as np
from build_mucum_floodplain_storage import connected_capacity,GAUGE_ZERO,geoid_interpolator,OUT,GAUGE_LAT,GAUGE_LON

class CapacityTests(unittest.TestCase):
    def test_packaged_mapgeo_grid_reproduces_SGB_local_undulation(self):
        f=geoid_interpolator(OUT/'mapgeo2015_local_grid.json')
        self.assertAlmostEqual(float(f([[GAUGE_LAT,GAUGE_LON]])[0]),6.47,delta=.01)

    def fixture(self):
        z=np.array([[34.,34.,40.,34.]])
        valid=np.ones(z.shape,bool);channel=np.array([[True,False,False,False]])
        return z,valid,channel,np.ones(z.shape,bool)

    def test_isolated_low_basin_is_not_flooded_through_high_barrier(self):
        z,v,c,u=self.fixture();area,volume,mask=connected_capacity(z,v,c,u,2,100)
        self.assertEqual(area,4.)
        self.assertAlmostEqual(volume,(GAUGE_ZERO+2-34)*4)
        self.assertFalse(mask[0,3])

    def test_nodata_is_not_added_as_storage_or_opened_as_land_connection(self):
        z,v,c,u=self.fixture();z[0,1]=np.nan;v[0,1]=False
        area,volume,_=connected_capacity(z,v,c,u,10,100)
        self.assertEqual(area,0.);self.assertEqual(volume,0.)

    def test_downstream_land_cannot_be_used_as_upstream_storage(self):
        z,v,c,u=self.fixture();u[0,2:]=False
        area,volume,mask=connected_capacity(z,v,c,u,10,100)
        self.assertEqual(area,4.);self.assertFalse(mask[0,3])

    def test_increasing_level_never_decreases_capacity(self):
        z,v,c,u=self.fixture();volumes=[connected_capacity(z,v,c,u,h,100)[1] for h in [0,2,4,6,8,10]]
        self.assertTrue(all(b>=a for a,b in zip(volumes,volumes[1:])))

if __name__=='__main__':unittest.main()
