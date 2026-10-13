import unittest
import json
import tempfile
from pathlib import Path
from comparar_rs122 import (medidas, contraste, verificar_soma, dentro, recortar,
                            resolucao_efeito, validar_serie, conferir_pareamento, triagem, auditar_log)


class ComparacaoTest(unittest.TestCase):
    def test_volume_tie(self):
        m = medidas({0: 1, 10: 2, 20: 2})
        self.assertEqual(m["volume_m3"], 2100)
        self.assertEqual(m["pico_inicio_hec_min"], 10)
        self.assertEqual(m["pico_fim_hec_min"], 20)

    def test_children(self):
        self.assertTrue(verificar_soma({0: 3, 1: 6}, {0: 1, 1: 2}, {0: 2, 1: 4})["passou_volume"])
        self.assertFalse(verificar_soma({0: 3, 1: 6}, {0: 1, 1: 2}, {0: 3, 1: 4})["passou_ponto_a_ponto"])
        with self.assertRaises(ValueError):
            verificar_soma({0: 3, 1: 6}, {0: 1}, {0: 2, 1: 4})

    def test_percent_and_native_grids(self):
        c = contraste({0: 1, 10: 2}, {0: 2, 5: 3, 10: 4})
        self.assertEqual(c["delta_pico_pct"], 100)
        self.assertEqual(c["delta_volume_pct"], 100)

    def test_zero_and_boundary(self):
        z = {0: 0, 1: 0}
        self.assertTrue(verificar_soma(z, z, z)["passou_volume"])
        self.assertIsNone(contraste(z, {0: 1, 1: 1})["delta_volume_pct"])
        self.assertTrue(dentro(1.0000000000000009, 1))
        self.assertFalse(dentro(1.000001, 1))

    def test_tie_groups_and_censored(self):
        m = medidas({0: 1, 1: 2, 2: 2, 3: 1, 4: 2, 5: 1})
        self.assertEqual(m["grupos_maximos_hec_min"], [[1, 2], [4]])
        self.assertFalse(m["pico_na_borda"])
        self.assertTrue(m["pico_empatado"])
        self.assertTrue(medidas({0: 2, 1: 1})["pico_na_borda"])

    def test_cut_must_have_both_edges(self):
        with self.assertRaises(ValueError):
            recortar({1: 1, 2: 2}, (0, 2))
        self.assertEqual(recortar({0: 0, 1: 1, 2: 2}, (1, 2)), {1: 1, 2: 2})

    def test_effect_resolution(self):
        s = lambda q: {0: 0, 5: q, 10: 0}
        self.assertTrue(resolucao_efeito(s(10), s(20), s(10.1), s(20.1))["pico_m3s"]["efeito_supera_variacao_numerica"])
        self.assertFalse(resolucao_efeito(s(10), s(10.1), s(11), s(11.1))["pico_m3s"]["efeito_supera_variacao_numerica"])

    def test_contract_not_self_declared(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "vazao.csv"
            p.write_text("node,time_value,flow\nJ,0,1\nJ,10,2\n", encoding="utf-8")
            (p.parent / "series_metadata.json").write_text(json.dumps([{"node": "J", "pathname": "//J/FLOW/x/", "units": "CMS", "type": "INST-VAL", "interval": 10, "count": 2}]), encoding="utf-8")
            meta = {"nos": ["J"], "n_por_no": 2, "inicio_hec_min": 0, "fim_hec_min": 10, "passo_min": 10}
            self.assertEqual(set(validar_serie(p, {"J"}, 10, (0, 10), meta)), {"J"})
            for nodes, bounds, declared in (({"J", "K"}, (0, 10), meta), ({"J"}, (0, 20), meta), ({"J"}, (0, 10), dict(meta, n_por_no=3))):
                with self.assertRaises(ValueError):
                    validar_serie(p, nodes, 10, bounds, declared)

    def test_incomplete_matrix_rejected(self):
        with self.assertRaises(ValueError):
            conferir_pareamento({})

    def test_triagem_ambiguous_not_false_or_true(self):
        for s in ({0: 0, 5: 0, 10: 0}, {0: 2, 5: 1, 10: 0}, {0: 0, 5: 2, 10: 2, 15: 0}):
            result = triagem(contraste(s, s))
            self.assertTrue(result["triagem_pico_volume_passou"])
            self.assertIsNone(result["triagem_temporal_passou"])
            self.assertIsNone(result["triagem_passou"])
        s = {0: 0, 5: 2, 10: 0}
        self.assertTrue(triagem(contraste(s, s))["triagem_passou"])
        self.assertFalse(triagem(contraste(s, {0: 0, 5: 3, 10: 0}))["triagem_passou"])

    def test_calculation_log(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Rodada.log"
            completed = 'NOTE 15302:  Finished computing simulation run "Rodada"\n'
            p.write_text(completed + 'WARNING 42403:  Time of concentration increased at subbasin "SB_1".\n', encoding="utf-8")
            self.assertEqual(auditar_log(p)["tc_elevado_ao_passo"], ["SB_1"])
            for value in ("", completed + "ERROR 1: Failed"):
                p.write_text(value, encoding="utf-8")
                with self.assertRaises(ValueError):
                    auditar_log(p)


if __name__ == "__main__":
    unittest.main()
