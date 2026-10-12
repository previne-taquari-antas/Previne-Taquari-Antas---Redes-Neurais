import unittest
import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import LineString, box
from perfil_rs122 import estatistica_perfil, amostrar_perfil, relevo


class PerfilTest(unittest.TestCase):
    def test_endpoint_and_ascent(self):
        p = estatistica_perfil([(0, 0), (3, 4), (6, 8)], [10, 12, 4])
        self.assertEqual(p["length_m"], 10)
        self.assertEqual(p["queda_m"], 6)
        self.assertEqual(p["segmentos_ascendentes"], 1)
        self.assertEqual(p["maior_subida_m"], 2)

    def test_negative_slope_not_clamped(self):
        self.assertEqual(estatistica_perfil([(0, 0), (10, 0)], [1, 2])["declividade_superficie_extremos_m_m"], -.1)

    def test_invalid(self):
        for xy, z in (([(0, 0)], [1]), ([(0, 0), (0, 0)], [1, 2]), ([(0, 0), (1, 0)], [1, np.nan])):
            with self.subTest(xy=xy), self.assertRaises(ValueError):
                estatistica_perfil(xy, z)

    def test_raster_and_missing(self):
        with MemoryFile() as mem:
            with mem.open(driver="GTiff", height=2, width=2, count=1, dtype="float32",
                          crs="EPSG:31982", transform=from_origin(0, 60, 30, 30), nodata=-9999) as src:
                src.write(np.array([[4, 3], [2, 1]], dtype="float32"), 1)
                self.assertEqual(amostrar_perfil(src, LineString([(15, 45), (45, 15)]))["queda_m"], 3)
                self.assertEqual(relevo(src, box(0, 0, 60, 60))["n_pixels_centros_no_poligono"], 4)
                with self.assertRaisesRegex(ValueError, "Cobertura espacial"):
                    relevo(src, box(-5, -5, 55, 55))
                src.write(np.array([[4, 3], [2, -9999]], dtype="float32"), 1)
                with self.assertRaises(ValueError):
                    amostrar_perfil(src, LineString([(15, 45), (45, 15)]))
                with self.assertRaisesRegex(ValueError, "Cobertura"):
                    relevo(src, box(0, 0, 60, 60))


if __name__ == "__main__":
    unittest.main()
