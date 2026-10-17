"""Real contour-writer regression on a 10x10 synthetic grid, never field rasters.

The canonical scope/datum is checked by the unchanged field validator.
STZ_WRITER_TEST_REF optionally loads historical source read-only for a
counter-test; it does not check out files, write Git, or execute main().
"""
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import shape
from shapely.ops import transform as transform_geometry

ROOT = Path(__file__).resolve().parents[1]
PRODUCER = ROOT / "codigo_python/02_mdt_hand_mancha/gerar_hand_lidar_santa_tereza.py"
sys.path.insert(0, str(PRODUCER.parent))
sys.path.insert(0, str(ROOT / "scripts"))
from santa_tereza_hand_field_contract import FIELD_SCOPE, validate_field_contours

spec = importlib.util.spec_from_file_location("stz_real_contour_writer_under_test", PRODUCER)
writer = importlib.util.module_from_spec(spec)
if os.environ.get("STZ_WRITER_TEST_REF"):
    result = subprocess.run(["git", "show", os.environ["STZ_WRITER_TEST_REF"] + ":" + PRODUCER.relative_to(ROOT).as_posix()],
                            cwd=ROOT, capture_output=True, check=True, timeout=30)
    exec(compile(result.stdout.decode("utf-8"), str(PRODUCER), "exec"), writer.__dict__)
else:
    spec.loader.exec_module(writer)


class FieldWriterTests(unittest.TestCase):
    def fixture(self):
        hand = np.zeros((10, 10), dtype="float32")
        hand[:, 4:] = 0.4
        axis = np.zeros_like(hand, dtype=bool)
        axis[:, 0] = True
        return hand, axis, from_origin(405000, 6780000, 5, 5), "EPSG:31982"

    def test_real_writer_emits_all_levels_canonical_scope_and_backwater_limits(self):
        with tempfile.TemporaryDirectory(prefix="stz-writer-contract-") as folder:
            output = Path(folder) / "contours.json"
            with redirect_stdout(io.StringIO()):
                report = writer.write_contours(*self.fixture(), output)
            document = json.loads(output.read_text(encoding="utf-8"))
            levels, geometries, provenance = validate_field_contours(document)
            self.assertEqual(levels, [round(index / 10, 1) for index in range(251)])
            self.assertEqual(report["contornos_features"], 251)
            self.assertEqual(document["metadata"]["rio"], FIELD_SCOPE)
            self.assertEqual(document["metadata"]["hand_zero_cm"], 160)
            self.assertEqual(document["metadata"]["river_reference_method"], "eixo_dominante_taquari_D8")
            self.assertEqual(document["metadata"]["backwater_hydrodynamic_calibration"], "not_validated")
            self.assertIn("sem_rio_local_25m", document["metadata"]["marrecao_regime"])
            self.assertEqual(provenance["scope"], FIELD_SCOPE)
            to_native = Transformer.from_crs("EPSG:4326", "EPSG:31982", always_xy=True).transform
            for feature in document["features"]:
                area = transform_geometry(to_native, shape(feature["geometry"])).area
                self.assertEqual(feature["properties"]["area_ha"], round(area / 10000, 1))
            for earlier, later in zip(geometries, geometries[1:]):
                self.assertLessEqual(earlier.difference(later).area, 1e-16)

    def test_incompatible_scope_is_rejected_before_contour_file_is_written(self):
        with tempfile.TemporaryDirectory(prefix="stz-writer-reject-") as folder:
            output = Path(folder) / "must-not-exist.json"
            with (mock.patch.object(writer, "FIELD_SCOPE", "eixo dominante Taquari; Marrecão tributário sujeito a remanso"),
                  redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "somente rio principal")):
                writer.write_contours(*self.fixture(), output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
