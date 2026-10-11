import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from diagnostico_componentes_lateral import componentes, maximo, topologia, ORIGEM
from verificar_diagnostico_lateral import sha, sha_lf


class DiagnosticoTest(unittest.TestCase):
    def test_hash_apenas_crlf(self):
        with tempfile.TemporaryDirectory() as d:
            p, q = Path(d) / "crlf", Path(d) / "lf"
            p.write_bytes(b'{\r\n"a": 1\r\n}')
            q.write_bytes(b'{\n"a": 1\n}')
            self.assertNotEqual(sha(p), sha(q))
            self.assertEqual(sha_lf(p), sha(q))
            p.write_bytes(b'{\r\n"a": 2\r\n}')
            self.assertNotEqual(sha_lf(p), sha(q))

    def test_plateau_desconectado(self):
        self.assertTrue(maximo([0, 10, 20, 30, 40], [0, 3, 1, 3, 0])["maximos_desconectados"])
        self.assertFalse(maximo([0, 10, 20, 30], [0, 3, 3, 0])["maximos_desconectados"])

    def test_maximo_borda(self):
        self.assertTrue(maximo([0, 10], [3, 1])["maximo_na_borda"])

    def test_topologia(self):
        self.assertEqual(topologia("Subbasin: SB_1\n Downstream: R_1\nEnd:\nReach: R_1\n Downstream: J_1\nEnd:\n"),
                         {"SB_1": "R_1", "R_1": "J_1"})

    def test_soma_antes_routing(self):
        s = {n: {0: v, 10: v} for n, v in [("J_217", 3), ("J_072", 5), ("SB_224", 2), ("R_224", 9), ("J_224", 9)]}
        r = componentes(s, "224", ORIGEM, ORIGEM + timedelta(minutes=10))
        self.assertEqual(r["maximo_entrada_combinada"]["q_m3s"], 10)
        self.assertEqual(r["fracao_SB_no_maximo_entrada_pct"], [20, 20])
        self.assertIsNone(r["lag_observado"])
        s["J_224"][0] = 10
        with self.assertRaisesRegex(ValueError, "difere"):
            componentes(s, "224", ORIGEM, ORIGEM + timedelta(minutes=10))

    def test_truncada(self):
        s = {n: {0: 1, 10: 1} for n in ["J_217", "J_072", "SB_224", "R_224", "J_224"]}
        with self.assertRaisesRegex(ValueError, "truncada"):
            componentes(s, "224", ORIGEM, ORIGEM + timedelta(minutes=20))


if __name__ == "__main__":
    unittest.main()
