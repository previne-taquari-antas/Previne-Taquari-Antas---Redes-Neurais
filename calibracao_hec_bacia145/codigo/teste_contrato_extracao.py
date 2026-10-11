"""Testes do contrato sem executar HEC-HMS nem ler observações."""
import tempfile
import unittest
from pathlib import Path

from contrato_extracao import conferir_csv, validar_nos, exigir_destinos_novos


class ContratoTest(unittest.TestCase):
    def csv(self, rows):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = Path(self.tmp.name) / "vazao.csv"
        p.write_text("node,time_value,flow\n" + rows, encoding="utf-8")
        return p

    def test_valid_complete(self):
        p = self.csv("J_1,0,0\nJ_1,10,4\nR_2,0,1\nR_2,10,3\n")
        self.assertEqual(conferir_csv(p, ["J_1", "R_2"])["n_por_no"], 2)

    def test_missing_node_cached(self):
        with self.assertRaisesRegex(ValueError, "sem série"):
            conferir_csv(self.csv("J_1,0,1\nJ_1,10,2\n"), ["J_1", "R_2"])

    def test_duplicates_even_identical(self):
        with self.assertRaisesRegex(ValueError, "duplicado"):
            conferir_csv(self.csv("J_1,0,1\nJ_1,0,1\n"), ["J_1"])

    def test_gap(self):
        with self.assertRaisesRegex(ValueError, "Lacuna"):
            conferir_csv(self.csv("J_1,0,1\nJ_1,20,1\n"), ["J_1"])

    def test_different_grids(self):
        with self.assertRaisesRegex(ValueError, "coberturas"):
            conferir_csv(self.csv("J_1,0,1\nJ_1,10,1\nR_2,10,1\nR_2,20,1\n"), ["J_1", "R_2"])

    def test_invalid_flow(self):
        for value in ["nan", "inf", "-901", "-1"]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "inválida"):
                conferir_csv(self.csv(f"J_1,0,{value}\nJ_1,10,1\n"), ["J_1"])

    def test_known_nodes(self):
        self.assertEqual(validar_nos(["R_2", "J_1", "J_1"], "Junction: J_1\nReach: R_2\n"), ["J_1", "R_2"])

    def test_unknown_node(self):
        with self.assertRaisesRegex(ValueError, "ausentes"):
            validar_nos(["R_404"], "Junction: J_1\n")

    def test_bad_type(self):
        for value in ["J_1", None, [4]]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "lista"):
                validar_nos(value, "Junction: J_1\n")

    def test_header(self):
        p = self.csv("J_1,0,1\nJ_1,10,2\n")
        p.write_text("node,time,flow\nJ_1,0,1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Cabeçalho"):
            conferir_csv(p, ["J_1"])

    def test_truncated_start(self):
        with self.assertRaisesRegex(ValueError, "Início"):
            conferir_csv(self.csv("J_1,10,1\nJ_1,20,2\n"), ["J_1"], inicio_esperado=0)

    def test_initial_sample_included(self):
        r = conferir_csv(self.csv("J_1,0,1\nJ_1,10,2\nJ_1,20,3\n"), ["J_1"],
                         inicio_esperado=0, fim_esperado=20)
        self.assertEqual(r["n_por_no"], 3)

    def test_truncated_end(self):
        with self.assertRaisesRegex(ValueError, "Fim"):
            conferir_csv(self.csv("J_1,0,1\nJ_1,10,2\n"), ["J_1"], fim_esperado=20)

    def test_preserve_existing_with_or_without_ok(self):
        for completed in [False, True]:
            with self.subTest(completed=completed), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp) / "job"
                d.mkdir()
                (d / "output.dss").write_bytes(b"preserve")
                if completed:
                    (d / "ok.txt").write_text("OK")
                with self.assertRaisesRegex(ValueError, "pastas novas"):
                    exigir_destinos_novos([d])
                self.assertEqual((d / "output.dss").read_bytes(), b"preserve")

    def test_new_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            exigir_destinos_novos([Path(tmp) / "new"])


if __name__ == "__main__":
    unittest.main()
