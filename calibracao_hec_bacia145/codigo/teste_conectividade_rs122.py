import unittest
import numpy as np
from affine import Affine
from rasterio.crs import CRS
from types import SimpleNamespace

from auditar_conectividade_rs122 import RasterPath, drena_grafo, grafo_basin, area_pixel_km2


class FakeRaster:
    nodata = -9999

    def __init__(self, values):
        self.values = np.array(values)
        self.height, self.width = self.values.shape

    def read(self, band, window):
        r, c = int(window.row_off), int(window.col_off)
        return self.values[r:r + int(window.height), c:c + int(window.width)]


class ConectividadeTest(unittest.TestCase):
    def test_pixel_area_and_crs(self):
        src = SimpleNamespace(crs=CRS.from_epsg(31982), transform=Affine(30, 0, 400000, 0, -30, 6800000))
        self.assertAlmostEqual(area_pixel_km2(src), 0.0009)
        for crs in (None, CRS.from_epsg(4326), CRS.from_epsg(31983)):
            with self.subTest(crs=crs), self.assertRaisesRegex(ValueError, "CRS"):
                area_pixel_km2(SimpleNamespace(crs=crs, transform=src.transform))

    def test_pixel_resolution_rotation(self):
        for t in (Affine.scale(90, -90), Affine.scale(30, 30), Affine(30, 1, 0, 0, -30, 0)):
            with self.subTest(transform=t), self.assertRaisesRegex(ValueError, "Grade"):
                area_pixel_km2(SimpleNamespace(crs=CRS.from_epsg(31982), transform=t))

    def test_target_and_cache(self):
        t = RasterPath(FakeRaster([[2, 2, 2, 0]]), (0, 2))
        self.assertTrue(t.drena((0, 0)))
        self.assertTrue(t.drena((0, 1)))
        self.assertFalse(t.drena((0, 3)))

    def test_edge(self):
        self.assertFalse(RasterPath(FakeRaster([[128, 0]]), (0, 1)).drena((0, 0)))

    def test_cycle(self):
        with self.assertRaisesRegex(ValueError, "Ciclo"):
            RasterPath(FakeRaster([[2, 32, 0]]), (0, 2)).drena((0, 0))

    def test_nodata(self):
        self.assertFalse(RasterPath(FakeRaster([[-9999, 0]]), (0, 1)).drena((0, 0)))

    def test_invalid_code(self):
        with self.assertRaisesRegex(ValueError, "desconhecido"):
            RasterPath(FakeRaster([[3, 0]]), (0, 1)).drena((0, 0))

    def test_graph(self):
        d, a = grafo_basin("Subbasin: SB_1\n Area: 4.5\n Downstream: R_1\nEnd:\nReach: R_1\n Downstream: J_1\nEnd:\nSink: J_1\nEnd:\n")
        self.assertEqual(a, {"SB_1": 4.5})
        self.assertTrue(drena_grafo("SB_1", d, {"J_1"}))
        self.assertFalse(drena_grafo("SB_1", d, {"J_2"}))
        with self.assertRaisesRegex(ValueError, "Ciclo"):
            drena_grafo("x", {"x": "y", "y": "x"}, {"z"})


if __name__ == "__main__":
    unittest.main()
