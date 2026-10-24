#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes do painel casa a casa: cheias registradas, capacidade e abrigos.

Sem shapely/rasterio: lê o template do código-fonte e os dados embutidos nos
painéis publicados. Cobrem a revisão de out/2026:
  - painel publicado igual ao template atual (Muçum tinha ficado para trás);
  - cheias de referência batendo com os picos das séries das réguas;
  - subida padrão de 90 cm/h (40 cm/h dava margem 2 a 5 vezes maior);
  - capacidade planejada de Muçum vinda do Plano de Contingência;
  - pontos de Muçum em abrigos.geojson (sem eles o gerador abortava);
  - locais altos de Santa Tereza (out/2026): fora da água de set/2023, a maior
    cheia registrada, com 2 m de folga no HAND e na altitude do LiDAR; o painel
    publicado é o recálculo de locais_altos.py.
"""
import json
import re
import sys
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
sys.path.insert(0, str(RAIZ / "codigo_python" / "09_rota_fuga"))
import locais_altos  # noqa: E402


def ler(p):
    return json.loads(p.read_text(encoding="utf-8"))


def payload_bruto(html):
    i = html.index("const D=") + len("const D=")
    return html[i:json.JSONDecoder().raw_decode(html, i)[1]]


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


class LocaisAltosTest(unittest.TestCase):
    """Santa Tereza: locais altos sugeridos e cheias de referência."""

    @classmethod
    def setUpClass(cls):
        cls.d = DADOS["santa_tereza"]
        cls.alt = cls.d["altos"]
        cls.crit = cls.alt["meta"]["criterios"]
        cls.A = {k: i for i, k in enumerate(cls.alt["meta"]["casas_campos"])}

    def test_publicado_e_o_recalculo(self):
        novo = locais_altos.calcula(json.loads(payload_bruto(HTML["santa_tereza"])), "santa_tereza")
        for k, v in novo.items():
            with self.subTest(campo=k):
                self.assertEqual(json.loads(json.dumps(v)), self.alt[k])

    def test_criterios_da_validacao_de_campo(self):
        ch = self.alt["meta"]["cheia"]
        self.assertAlmostEqual(ch["regua_m"] - ch["zero_regua_m"], ch["hand_m"], places=2)
        self.assertAlmostEqual(self.crit["hand_min_m"], ch["hand_m"] + 2.0, places=2)
        self.assertAlmostEqual(self.crit["altitude_min_m"], ch["agua_max_rtk_m"] + 2.0, places=2)
        # a folga cobre o maior erro do HAND no sentido perigoso medido com RTK
        self.assertGreater(self.alt["meta"]["folga_hand_m"], ch["erro_max_perigoso_m"])

    def test_locais_ficam_fora_da_agua_de_2023_com_folga(self):
        self.assertTrue(2 <= len(self.alt["locais"]) <= locais_altos.LOCAIS_MAX)
        cota = self.d["cota_no"]
        for loc in self.alt["locais"]:
            with self.subTest(local=loc["id"]):
                c = cota[loc["no"]]
                self.assertTrue(c is None or c >= self.crit["hand_min_m"])
                self.assertGreaterEqual(loc["altitude_m"], self.crit["altitude_min_local_m"])
                self.assertEqual(self.alt["no_alto"][loc["no"]], 1)
                self.assertGreater(loc["n_casas"], 0)

    def test_rotas_pela_rede_e_corte_coerente(self):
        A, cota = self.A, self.d["cota_no"]
        aresta = {}
        for a, b, _ag, _pe, cz in self.d["edges"]:
            for k in ((a, b), (b, a)):
                aresta[k] = max(aresta.get(k, -1), 1e9 if cz is None else cz)
        n_rota = 0
        for ci, c in enumerate(self.alt["casas"]):
            if self.alt["meta"]["estados"][c[A["estado"]]] != "rota":
                continue
            n_rota += 1
            r = c[A["rota"]]
            with self.subTest(casa=ci):
                F = {k: i for i, k in enumerate(self.d["meta"]["casas_campos"])}
                self.assertEqual(r[0], self.d["casas"][ci][F["no"]])
                self.assertEqual(r[-1], self.alt["locais"][c[A["local"]]]["no"])
                self.assertTrue(all((u, v) in aresta for u, v in zip(r, r[1:])))
                cortes = [aresta[(u, v)] for u, v in zip(r, r[1:])] + [1e9 if cota[k] is None else cota[k] for k in r]
                esperado = min(cortes)
                self.assertEqual(c[A["corte_m"]], None if esperado >= 1e9 else round(esperado, 1))
        self.assertGreater(n_rota, 100)

    def test_set2023_e_a_maior_cheia(self):
        cheias = {c["rotulo"]: c for c in self.d["meta"]["cheias_ref"]}
        self.assertNotIn("ref. mai/2024", cheias)
        self.assertEqual(cheias["mai/2024"]["regua_m"], 22.42)  # SGB; telemetria parou em 22,32 m
        hist = [c for c in cheias.values() if c.get("tipo") != "cota_oficial"]
        self.assertEqual(max(hist, key=lambda c: c["regua_m"])["rotulo"], "set/2023")
        self.assertEqual(self.alt["meta"]["cheia"]["regua_m"], cheias["set/2023"]["regua_m"])

    def test_ginasio_fica_dentro_da_agua_de_2023(self):
        gin = self.d["abrigos"][0]
        self.assertLessEqual(gin["cota_alaga_m"], self.alt["meta"]["cheia"]["hand_m"])

    def test_candidatos_antigos_saem_e_mancha_de_2023(self):
        self.assertEqual(self.d["candidatos"], [])
        self.assertIsNone(self.d["rota_cand"])
        m = self.alt["mancha_cheia"]
        self.assertAlmostEqual(m["nivel_hand_m"], 22.1, places=6)
        self.assertTrue(m["poligonos"])
        self.assertEqual(len(self.alt["cel_alta"]), len(self.d["cells"]))
        self.assertTrue(all(not c["casas"] for c, f in zip(self.d["cells"], self.alt["cel_alta"]) if f))
        self.assertNotIn("altos", DADOS["mucum"])


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
