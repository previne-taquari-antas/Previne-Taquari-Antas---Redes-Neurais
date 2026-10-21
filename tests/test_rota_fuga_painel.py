#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes do painel casa a casa: cheias registradas, capacidade e abrigos.

Sem shapely/rasterio: lê o template do código-fonte e os dados embutidos nos
painéis publicados. Cobrem a revisão de out/2026:
  - painel publicado igual ao template atual (Muçum tinha ficado para trás);
  - cheias de referência batendo com os picos das séries das réguas;
  - subida padrão de 90 cm/h (40 cm/h dava margem 2 a 5 vezes maior);
  - capacidade planejada de Muçum vinda do Plano de Contingência;
  - pontos de Muçum em abrigos.geojson (sem eles o gerador abortava).
"""
import json
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
GERADOR = RAIZ / "codigo_python" / "09_rota_fuga" / "gerar_painel.py"
PAINEIS = {"santa_tereza": RAIZ / "santa_tereza_painel_casas.html",
           "mucum": RAIZ / "mucum_painel_casas.html"}
SERIES = {"santa_tereza": RAIZ / "assets" / "data" / "eventos_analise.json",
          "mucum": RAIZ / "assets" / "data" / "mucum_eventos_analise.json"}
PLANO_MUCUM = RAIZ / "assets" / "data" / "mucum_contingencia_202607.json"
ABRIGOS = RAIZ / "assets" / "data" / "servicos" / "abrigos.geojson"


def ler(p):
    return json.loads(p.read_text(encoding="utf-8"))


def payload_bruto(html):
    i = html.index("const D=") + len("const D=")
    return html[i:html.index(", M=D.meta", i)]


TEMPLATE = re.search(r'_TEMPLATE = r"""(.*?)"""', GERADOR.read_text(encoding="utf-8"), re.S).group(1)
HTML = {c: p.read_text(encoding="utf-8") for c, p in PAINEIS.items()}
DADOS = {c: json.loads(payload_bruto(h)) for c, h in HTML.items()}


class PainelPublicadoTest(unittest.TestCase):
    def test_painel_e_o_template_atual(self):
        for c, html in HTML.items():
            with self.subTest(cidade=c):
                self.assertEqual(TEMPLATE.replace("__DADOS__", payload_bruto(html)), html)

    def test_subida_padrao_90(self):
        for c, d in DADOS.items():
            with self.subTest(cidade=c):
                self.assertEqual(d["meta"]["taxa_cm_h"], 90.0)

    def test_cheias_batem_com_a_serie_da_regua(self):
        for c, d in DADOS.items():
            picos = {e["pico_data"]: e["pico_cm"] / 100 for e in ler(SERIES[c])["eventos"]}
            cheias = d["meta"]["cheias_ref"]
            self.assertEqual(sum(1 for x in cheias if x.get("tipo") == "cota_oficial"), 1)
            for x in cheias:
                data = x.get("data") or ""
                if len(data) == 10:
                    with self.subTest(cidade=c, cheia=x["rotulo"]):
                        self.assertAlmostEqual(x["regua_m"], picos[data], places=2)

    def test_cheia_mais_alta_alaga_o_ginasio(self):
        d = DADOS["santa_tereza"]
        zr, pior = d["meta"]["bankfull_m"], max(x["regua_m"] for x in d["meta"]["cheias_ref"])
        gin = d["abrigos"][0]
        self.assertLessEqual(gin["cota_alaga_m"], pior - zr)

    def test_capacidade_de_muçum_do_plano(self):
        plano = ler(PLANO_MUCUM)
        por_id = {a["id"]: a for a in plano["abrigos"] + plano["pontos_encontro"]}
        for a in DADOS["mucum"]["abrigos"]:
            cap, ref = a["capacidade_plano"], por_id[a["id"]]
            vals = [v for v in (ref.get("capacidade_planejada"), ref.get("capacidade_quadro_13"),
                                ref.get("capacidade_ficha_tecnica")) if v is not None]
            with self.subTest(abrigo=a["id"]):
                self.assertEqual((cap["min"], cap["max"]), (min(vals), max(vals)))
        self.assertTrue(all(a["capacidade_plano"] is None for a in DADOS["santa_tereza"]["abrigos"]))


class AbrigosGeojsonTest(unittest.TestCase):
    def setUp(self):
        self.feats = ler(ABRIGOS)["features"]

    def test_ginasio_continua_primeiro(self):
        # scripts/test_response_exercise.py lê features[0]
        self.assertEqual(self.feats[0]["properties"]["id"], "santa_tereza_ginasio_esportes")

    def test_mucum_igual_ao_painel(self):
        geo = {f["properties"]["id"]: f["geometry"]["coordinates"] for f in self.feats
               if f["properties"]["municipio"] == "Muçum"}
        painel = {a["id"]: [a["lon"], a["lat"]] for a in DADOS["mucum"]["abrigos"]}
        self.assertEqual(set(geo), set(painel))
        for k, (lon, lat) in painel.items():
            with self.subTest(abrigo=k):
                self.assertAlmostEqual(geo[k][0], lon, places=5)
                self.assertAlmostEqual(geo[k][1], lat, places=5)

    def test_sem_campo_de_capacidade(self):
        # scripts/validate_santa_tereza_piloto.py barra "capacidade" no cadastro de abrigos
        self.assertFalse(any("capacidade" in f["properties"] for f in self.feats))


if __name__ == "__main__":
    unittest.main()
