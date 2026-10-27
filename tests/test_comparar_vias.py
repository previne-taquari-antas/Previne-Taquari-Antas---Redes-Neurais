# -*- coding: utf-8 -*-
"""Comparação da base viária da SEMA (BCRS25) com a rede do OSM dos painéis
(codigo_python/09_rota_fuga/comparar_vias.py).

  python tests/test_comparar_vias.py -v
"""
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "codigo_python" / "09_rota_fuga"))
try:
    from shapely.geometry import LineString
    import comparar_vias as cv
    import pontos_encontro as pe
except ImportError:  # CI sem shapely
    cv = None


def perto(a, b, caminho=()):
    """Mesmo conteúdo, com folga nos números: o GEOS muda os últimos dígitos dos buffers entre versões."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= max(0.2, 0.005 * abs(b)) or caminho
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return caminho
        return next((r for k in a if (r := perto(a[k], b[k], caminho + (k,))) is not True), True)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return caminho
        return next((r for i, (x, y) in enumerate(zip(a, b)) if (r := perto(x, y, caminho + (i,))) is not True), True)
    return a == b or caminho


@unittest.skipIf(cv is None, "sem shapely")
class CompararViasTest(unittest.TestCase):
    def test_trecho_deslocado_alem_da_tolerancia_entra_com_a_distancia(self):
        plano = pe.Plano([(-29.17, -51.73)])
        b = LineString([(0, 0), (500, 0)])
        longe = cv.faltando(LineString([(0, 30), (500, 30)]), b, plano)
        self.assertEqual(len(longe), 1)
        self.assertEqual((longe[0][0], longe[0][3]), (500, 30))
        self.assertEqual(cv.faltando(LineString([(0, 10), (500, 10)]), b, plano), [])   # dentro dos 20 m
        self.assertEqual(cv.faltando(LineString([(0, 30), (40, 30)]), b, plano), [])    # menos de 50 m

    def test_publicado_bate_com_a_conta(self):
        pub = Path(cv.SAIDA)
        if not pub.exists():
            self.skipTest("sem comparacao_vias_sema_osm.json")
        d = json.loads(pub.read_text(encoding="utf-8"))
        self.assertEqual((d["tolerancia_m"], d["trecho_min_m"], d["deslocado_m"]), (cv.TOLERANCIA_M, cv.TRECHO_MIN_M, cv.DESLOCADO_M))
        for cidade, r in d["cidades"].items():
            self.assertTrue(Path(cv.vias_sema(cidade)).exists(), cidade)
            self.assertIs(perto(json.loads(json.dumps(cv.compara(cidade))), r), True, cidade)

    def test_sema_nao_tem_as_ruas_da_cidade(self):
        """O achado do README: a SEMA não tem as ruas urbanas, então cobre bem menos casas que o OSM."""
        pub = Path(cv.SAIDA)
        if not pub.exists():
            self.skipTest("sem comparacao_vias_sema_osm.json")
        for cidade, r in json.loads(pub.read_text(encoding="utf-8"))["cidades"].items():
            self.assertLess(r["casas_com_via_sema"], 0.6 * r["casas_com_via_osm"], cidade)
            self.assertGreater(r["sema_com_osm_pct"], 90, cidade)


if __name__ == "__main__":
    unittest.main()
