# -*- coding: utf-8 -*-
"""Pontos de encontro, primeira versão (codigo_python/09_rota_fuga/pontos_encontro.py e
pontos_encontro.html): trecho de via fora da mancha do mapa único com 100 m de afastamento.

Sem o arquivo do MUP RS no checkout, a conta roda numa mancha de teste (a cheia de set/2023 do
painel de Santa Tereza): o que se testa é o critério, não o resultado publicado.

  python tests/test_pontos_encontro.py -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "codigo_python" / "09_rota_fuga"))
try:
    from shapely.geometry import Point, Polygon, mapping, shape
    from shapely.ops import unary_union
    import pontos_encontro as pe
except ImportError:  # CI sem shapely
    pe = None
import locais_altos  # noqa: E402

PAGINA = (RAIZ / "pontos_encontro.html").read_text(encoding="utf-8")


def mancha_de_teste(destino):
    """A mancha HAND de set/2023 do painel de Santa Tereza, só para exercitar o critério."""
    d = locais_altos.payload(RAIZ / "santa_tereza_painel_casas.html")
    pol = [Polygon([(lo, la) for la, lo in p[0]], [[(lo, la) for la, lo in h] for h in p[1:]]).buffer(0)
           for p in d["altos"]["mancha_cheia"]["poligonos"]]
    with open(destino, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry": mapping(unary_union(pol))}]}, f)


@unittest.skipIf(pe is None, "sem shapely")
class CriterioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.arq = os.path.join(cls.tmp.name, "mancha.geojson")
        mancha_de_teste(cls.arq)
        cls.d = pe.documento("santa_tereza", cls.arq)
        cls.doc = locais_altos.payload(pe.CIDADES["santa_tereza"]["painel"])
        cls.plano = pe.Plano(cls.doc["nos"])
        cls.mancha = pe.le_mancha(cls.arq, cls.plano)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_pontos_ficam_fora_da_faixa_e_numa_via_fora_dela(self):
        self.assertTrue(self.d["pontos"])
        seguras = {k for a, b, ok in self.d["arestas"] if ok for k in (a, b)}
        for p in self.d["pontos"]:
            dist = self.mancha.distance(Point(self.plano.xy(p["lat"], p["lon"])))
            self.assertGreater(dist, pe.OFFSET_M, p)           # a mais de 100 m da mancha
            self.assertIn(p["no"], seguras, p)                  # ponta de um trecho de via inteiro fora da faixa
            self.assertAlmostEqual(dist, p["dist_mancha_m"], delta=0.1)

    def test_trecho_seguro_nao_toca_a_faixa(self):
        from shapely.geometry import LineString
        zona = self.mancha.buffer(pe.OFFSET_M)
        nos = self.d["nos"]
        for a, b, ok in self.d["arestas"]:
            if ok:
                self.assertFalse(zona.intersects(LineString([self.plano.xy(*nos[a]), self.plano.xy(*nos[b])])))

    def test_casa_na_mancha_ou_na_faixa_tem_caminho_ate_o_ponto(self):
        F = {k: i for i, k in enumerate(self.d["casas_campos"])}
        com_rota = 0
        for c in self.d["casas"]:
            est = self.d["estados"][c[F["estado"]]]
            if est == "fora":
                self.assertEqual(c[F["ponto"]], -1)
                self.assertFalse(self.mancha.buffer(pe.OFFSET_M).contains(Point(self.plano.xy(c[F["lat"]], c[F["lon"]]))))
            elif c[F["ponto"]] >= 0:
                com_rota += 1
                self.assertLessEqual(c[F["tempo_s"]], pe.TEMPO_TETO_S)
        self.assertGreater(com_rota, 0)
        # todo nó com ponto segue o "prox" até o próprio ponto
        alvo = {p["no"]: i for i, p in enumerate(self.d["pontos"])}
        for n, k in enumerate(self.d["ponto_no"]):
            if k < 0:
                continue
            j, g = n, 0
            while self.d["prox"][j] >= 0 and g < 6000:
                j, g = self.d["prox"][j], g + 1
            self.assertEqual(alvo.get(j), k)

    def test_afastamento_maior_afasta_os_pontos(self):
        d2 = pe.documento("santa_tereza", self.arq, offset_m=200.0)
        self.assertEqual(d2["offset_m"], 200.0)
        for p in d2["pontos"]:
            self.assertGreater(self.mancha.distance(Point(self.plano.xy(p["lat"], p["lon"]))), 200.0)

    def test_deterministico(self):
        self.assertEqual(json.dumps(self.d, sort_keys=True), json.dumps(pe.documento("santa_tereza", self.arq), sort_keys=True))

    def test_publicado_bate_com_a_conta(self):
        for cidade in pe.CIDADES:
            pub, mancha = Path(pe.saida_padrao(cidade)), Path(pe.mancha_padrao(cidade))
            if not pub.exists():
                continue
            self.assertTrue(mancha.exists(), f"{pub.name} sem a mancha de origem")
            d = json.loads(pub.read_text(encoding="utf-8"))
            self.assertEqual(d["mancha_sha256"], pe._sha256(mancha))
            novo = pe.documento(cidade, str(mancha), d["offset_m"], d["fonte_mancha"])
            # a conta (pontos, casas, ruas) bate exatamente; o contorno desenhado da faixa varia nos últimos
            # dígitos entre versões do GEOS (vértices dos arcos do buffer)
            for k in d:
                if k in ("mancha", "faixa"):
                    a, b = shape(d[k]), shape(novo[k])
                    self.assertLess(a.symmetric_difference(b).area, 1e-3 * b.area, (cidade, k))
                else:
                    self.assertEqual(json.dumps(d[k], sort_keys=True), json.dumps(novo[k], sort_keys=True), (cidade, k))


class PaginaTest(unittest.TestCase):
    def test_le_o_json_da_cidade_e_avisa(self):
        self.assertIn("'assets/data/rota_fuga/'+CID+'_pontos_encontro_mup.json'", PAGINA)
        self.assertIn("CIDADES[pedido]?pedido:'santa_tereza'", PAGINA)  # cidade fora da lista não monta caminho
        self.assertIn('<a href="tel:199">199</a>', PAGINA)
        self.assertIn("não é abrigo oficial", PAGINA)
        self.assertIn("Mapa Único do Plano Rio Grande", PAGINA)
        self.assertIn("if(!casa&&bd>LONGE_DA_RUA_M)", PAGINA)  # toque longe da rua não vira rota
        self.assertNotIn("você já está fora da área atingida", PAGINA)
        self.assertIn("map.getPane('agua').style.pointerEvents='none'", PAGINA)  # a mancha não captura o toque


if __name__ == "__main__":
    unittest.main()
