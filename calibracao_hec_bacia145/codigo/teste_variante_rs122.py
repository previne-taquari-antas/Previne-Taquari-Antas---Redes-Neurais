import unittest
from variante_rs122 import adaptar, chuva_transferida, blocos, campo, jusante, conferir_transferencia, discretizar


GEO = dict(area_local_antes_posto_km2=4.8168, area_local_depois_posto_km2=408.951,
           comprimento_antes_m=374.5584412271571, comprimento_depois_m=42109.52811191491)


def fixture():
    sub = "Subbasin: SB_211\n     Area: 413.768\n     Downstream: R_211\n     Time of Concentration: 2.40397\n     Storage Coefficient: 29.37242\n     Baseflow: Linear Reservoir\nEnd:\n"
    reach = "Reach: R_211\n     Downstream: J_211\n     Route: Muskingum Cunge\n     Channel: Trapezoid\n     Length: 38621.9\n     Energy Slope: 0.002064\nEnd:\n"
    rest = "".join(f"Subbasin: S{i}\n     Area: 1\n     Downstream: J_211\nEnd:\n" for i in range(144))
    rest += "".join(f"Reach: R{i}\n     Downstream: J_211\nEnd:\n" for i in range(104))
    rest += "Junction: J_222\n     Downstream: R_211\nEnd:\nJunction: J_089\n     Downstream: R_211\nEnd:\nSink: J_211\nEnd:\n"
    return sub + reach + rest


class VarianteTest(unittest.TestCase):
    def test_only_registered_terminal(self):
        self.assertIsNone(jusante("Junction", "J_157", "Computation Point: Yes"))
        with self.assertRaises(ValueError):
            jusante("Junction", "J_999", "Computation Point: Yes")

    def test_a_unchanged(self):
        self.assertEqual(adaptar(fixture(), "A", GEO)[0], fixture())

    def test_b0(self):
        text, meta = adaptar(fixture(), "B0", GEO)
        b = blocos(text)
        self.assertIn("SB_211", b)
        self.assertEqual(campo(b["SB_211"][1], "Downstream"), "R_211_UP")
        self.assertEqual(meta["length_modelo_up_m"] + meta["length_modelo_down_m"], 38621.9)

    def test_b1_preserves_response_area_and_topology(self):
        text, meta = adaptar(fixture(), "B1", GEO)
        b = blocos(text)
        self.assertNotIn("SB_211", b)
        areas = []
        for side in ("UP", "DOWN"):
            block = b["SB_211_" + side][1]
            areas.append(float(campo(block, "Area")))
            self.assertEqual(campo(block, "Time of Concentration"), "2.40397")
            self.assertEqual(campo(block, "Storage Coefficient"), "29.37242")
            self.assertEqual(campo(block, "Downstream"), "R_211_" + side)
        self.assertAlmostEqual(sum(areas), 413.768)
        self.assertAlmostEqual(meta["residuo_area_atribuido_down_km2"], .0002)

    def test_contract_rejects(self):
        for text in (fixture().replace("Muskingum Cunge", "Muskingum"), fixture().replace("413.768", "414.0"), fixture().replace("Sink: J_211\nEnd:", "Junction: J_211\n     Downstream: R_211\nEnd:")):
            with self.subTest(text=text[:20]), self.assertRaises(ValueError):
                adaptar(text, "B1", GEO)

    def test_rain_units_and_no_alias(self):
        f = {"chuva_por_subbacia": {f"S{i}": [1., 2.] for i in range(144)}, "horas": ["a", "b"]}
        f["chuva_por_subbacia"]["SB_211"] = [0., 10.]
        new = chuva_transferida(f, "B1")
        self.assertEqual(len(new["chuva_por_subbacia"]), 146)
        self.assertNotIn("SB_211", new["chuva_por_subbacia"])
        self.assertEqual(new["chuva_por_subbacia"]["SB_211_DOWN"], [0., 10.])
        new["chuva_por_subbacia"]["SB_211_UP"][0] = 1
        self.assertEqual(f["chuva_por_subbacia"]["SB_211"], [0., 10.])
        self.assertEqual(new["chuva_por_subbacia"]["SB_211_DOWN"], [0., 10.])

    def test_transfer_contract(self):
        f = {"chuva_por_subbacia": {f"S{i}": [0., 12.] for i in range(144)}, "horas": ["a", "b"]}
        f["chuva_por_subbacia"]["SB_211"] = [0., 17.31]
        rain = chuva_transferida(f, "B1")
        text, _ = adaptar(fixture(), "B1", GEO)
        self.assertLess(conferir_transferencia(fixture(), text, f, rain, "B1")["erro_max_volume_horario_mm_km2"], 1e-7)
        rain["chuva_por_subbacia"]["S1"][0] = 9
        with self.assertRaises(ValueError):
            conferir_transferencia(fixture(), text, f, rain, "B1")

    def test_dt_explicit_and_K_frozen(self):
        text = "Reach: R\n     Route: Muskingum\n     Muskingum K: 0.2\n     Muskingum x: 0.2\n     Muskingum Steps: 1\nEnd:\n"
        calls = []
        def calc(k, x, dt_h):
            calls.append((k, x, dt_h))
            return 2
        out, _ = discretizar(text, 5, calc)
        self.assertEqual(calls, [(.2, .2, 5/60)])
        self.assertIn("Muskingum K: 0.2", out)
        self.assertIn("Muskingum Steps: 2", out)
        self.assertEqual(discretizar(text, 10, calc)[0], text)


if __name__ == "__main__":
    unittest.main()
