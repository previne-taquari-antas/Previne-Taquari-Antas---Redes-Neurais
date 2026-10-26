#!/usr/bin/env python3
"""O divisor de contornos por nível preserva cada feição e o índice descreve todos os níveis."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "dividir_contornos_por_nivel", RAIZ / "codigo_python/02_mdt_hand_mancha/dividir_contornos_por_nivel.py")
divisor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(divisor)


def feicao(nivel, area):
    return {"type": "Feature", "properties": {"nivel_m": nivel, "area_ha": area},
            "geometry": {"type": "MultiPolygon", "coordinates": [[[[-51.8, -29.1], [-51.7, -29.1], [-51.7, -29.2], [-51.8, -29.1]]]]}}


class DividirContornosTests(unittest.TestCase):
    def test_indice_e_niveis_reproduzem_a_fonte(self):
        fc = {"type": "FeatureCollection", "metadata": {"cidade": "teste"},
              "features": [feicao(0.1, 3.4), feicao(0.2, 5.0), feicao(25.0, 900.1)]}
        with tempfile.TemporaryDirectory() as tmp:
            fonte = Path(tmp) / "contornos_extravasamento.json"
            fonte.write_text(json.dumps(fc), encoding="utf-8")
            resumo = divisor.dividir(fonte)
            pasta = Path(tmp) / "contornos_extravasamento_niveis"
            indice = json.loads((pasta / "indice.json").read_text(encoding="utf-8"))
            self.assertEqual(resumo["niveis"], 3)
            self.assertEqual(indice["metadata"], fc["metadata"])
            self.assertEqual([n["arquivo"] for n in indice["niveis"]], ["n0010.json", "n0020.json", "n2500.json"])
            for n, original in zip(indice["niveis"], fc["features"]):
                self.assertEqual(n["properties"], original["properties"])
                self.assertEqual(json.loads((pasta / n["arquivo"]).read_text(encoding="utf-8")), original)
            # rodar de novo substitui a pasta sem deixar níveis antigos
            fc["features"] = fc["features"][:1]
            fonte.write_text(json.dumps(fc), encoding="utf-8")
            divisor.dividir(fonte)
            self.assertEqual(sorted(p.name for p in pasta.iterdir()), ["indice.json", "n0010.json"])

    def test_destino_separado_da_fonte(self):
        # publish-pages.yml: a fonte fica no checkout e os níveis vão para o _site
        fc = {"type": "FeatureCollection", "features": [feicao(0.1, 3.4)]}
        with tempfile.TemporaryDirectory() as tmp:
            fonte = Path(tmp) / "checkout" / "contornos_extravasamento.json"
            fonte.parent.mkdir()
            fonte.write_text(json.dumps(fc), encoding="utf-8")
            destino = Path(tmp) / "_site" / "contornos_extravasamento_niveis"
            divisor.dividir(fonte, destino)
            self.assertTrue((destino / "indice.json").exists())
            self.assertFalse((fonte.parent / "contornos_extravasamento_niveis").exists())

    def test_nivel_repetido_falha(self):
        fc = {"type": "FeatureCollection", "features": [feicao(1.0, 1), feicao(1.0, 2)]}
        with tempfile.TemporaryDirectory() as tmp:
            fonte = Path(tmp) / "c.json"
            fonte.write_text(json.dumps(fc), encoding="utf-8")
            with self.assertRaises(ValueError):
                divisor.dividir(fonte)


if __name__ == "__main__":
    unittest.main()
