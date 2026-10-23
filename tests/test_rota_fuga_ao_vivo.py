#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes das rotas de fuga ao vivo: hora, nível do rio e o que a página mostra.

Sem LiDAR nem OSM. Cobrem os erros achados na revisão de out/2026:
  - hora sem fuso lida como hora do runner (UTC): idade do dado +180 min;
  - nível atual ausente virando 0 m (rio "seco" que sobe até a previsão);
  - Muçum grava [hora, modelo, agora, previsto] e o índice 2 é o nível de agora;
  - leitura rejeitada caindo para o nível de base do modelo, sem hora;
  - previsto contado da hora da leitura e não da hora do modelo (margem a mais);
  - ponto seguro placeholder a ~670 m do Ginásio de Esportes;
  - rota desenhada toda em verde mesmo atravessando água;
  - frases de comando ("SAIR AGORA", "Ninguém precisa sair agora") na fila.
"""
import datetime as dt
import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PASTA = RAIZ / "codigo_python" / "09_rota_fuga"


def carrega(nome):
    spec = importlib.util.spec_from_file_location(nome, PASTA / f"{nome}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nv = carrega("nivel_ao_vivo")

try:
    import numpy  # noqa: F401
    import PIL  # noqa: F401
    TEM_NUMPY_PIL = True
except ImportError:
    TEM_NUMPY_PIL = False


class NivelAoVivoTest(unittest.TestCase):
    def setUp(self):
        # o runner do GitHub roda em UTC; a hora da previsão é de Brasília
        self.tz_antigo = os.environ.get("TZ")
        os.environ["TZ"] = "UTC"
        time.tzset()
        self.ref = dt.datetime(2026, 10, 20, 20, 45, tzinfo=nv.FUSO)

    def tearDown(self):
        if self.tz_antigo is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self.tz_antigo
        time.tzset()

    def test_hora_sem_fuso_e_brasilia(self):
        self.assertEqual(nv.idade_min("2026-10-20T19:45:00", self.ref), 60)

    def test_hora_com_fuso(self):
        self.assertEqual(nv.idade_min("2026-10-20T22:45:00Z", self.ref), 60)
        self.assertEqual(nv.idade_min("2026-10-20T19:45:00-03:00", self.ref), 60)

    def test_hora_invalida_ou_ausente(self):
        self.assertIsNone(nv.idade_min(None, self.ref))
        self.assertIsNone(nv.idade_min("ontem", self.ref))

    def test_nivel_ausente_nao_vira_zero(self):
        em = "2026-10-20T19:45:00"
        self.assertIsNone(nv.nivel_atual_cm({}))
        self.assertIsNone(nv.nivel_atual_cm({"telemetria_ultima_nivel_cm": None, "telemetria_ultima_em": em}))
        self.assertEqual(nv.nivel_atual_cm({"telemetria_ultima_nivel_cm": 0, "telemetria_ultima_em": em}), 0.0)

    def test_leitura_rejeitada_nao_usa_nivel_do_modelo(self):
        # o robô de previsão zera a leitura e a hora, mas preenche nivel_atual_cm com o modelo
        self.assertIsNone(nv.nivel_atual_cm({"telemetria_ultima_nivel_cm": None,
                                             "telemetria_ultima_em": None, "nivel_atual_cm": 186}))
        self.assertIsNone(nv.nivel_atual_cm({"telemetria_ultima_nivel_cm": 202, "telemetria_ultima_em": None}))

    def test_previsto_santa_tereza(self):
        # leitura 19:45, modelo das 19:00: 2h vale para 21:00 (75 min), 4h para 23:00 (195 min)
        d = {"telemetria_ultima_em": "2026-10-20T19:45:00",
             "horizontes": {"2h": {"disponivel": True, "nivel_previsto_cm": 313, "hora_modelo": "2026-10-20T19:00:00",
                                   "passos": [["2026-10-20T19:00:00", 202, 313]]},
                            "4h": {"disponivel": True, "passos": [["2026-10-20T19:00:00", 202, 433]]}}}
        self.assertEqual(nv.previstos_cm(d), [("2h", 75, 313.0), ("4h", 195, 433.0)])

    def test_previsto_mucum_nao_le_o_nivel_de_agora(self):
        # formato de Muçum: [hora, modelo, nível agora, previsto]; leitura 20:15, 4h vale para 00:00
        d = {"telemetria_ultima_em": "2026-10-20T20:15:00",
             "horizontes": {"4h": {"disponivel": True, "nivel_previsto_cm": 344, "hora_modelo": "2026-10-20T20:00:00",
                                   "passos": [["2026-10-20T20:00:00", 173, 171, 344]]}}}
        self.assertEqual(nv.previstos_cm(d), [("4h", 225, 344.0)])
        d["horizontes"]["4h"].pop("nivel_previsto_cm")
        self.assertEqual(nv.previstos_cm(d), [("4h", 225, 344.0)])

    def test_previsto_ja_vencido_fica_de_fora(self):
        # modelo das 17:00, leitura 19:45: o 2h (19:00) já passou; o 4h (21:00) fica
        d = {"telemetria_ultima_em": "2026-10-20T19:45:00",
             "horizontes": {"2h": {"disponivel": True, "passos": [["2026-10-20T17:00:00", 150, 260]]},
                            "4h": {"disponivel": True, "passos": [["2026-10-20T17:00:00", 150, 300]]}}}
        self.assertEqual(nv.previstos_cm(d), [("4h", 75, 300.0)])

    def test_sem_hora_usa_o_horizonte(self):
        d = {"horizontes": {"2h": {"disponivel": True, "passos": [["x", 202, 313]]}}}
        self.assertEqual(nv.previstos_cm(d), [("2h", 120, 313.0)])

    def test_horizonte_indisponivel_fica_fora(self):
        d = {"horizontes": {"2h": {"disponivel": False, "nivel_previsto_cm": 900},
                            "4h": {"disponivel": True, "passos": []}}}
        self.assertEqual(nv.previstos_cm(d), [])


@unittest.skipUnless(TEM_NUMPY_PIL, "precisa de numpy e pillow")
class Etapa1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = carrega("gerar_rota_fuga_santa_tereza")

    def trajetoria(self, previsao):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(previsao, f)
        antigo = self.mod.FORECAST
        try:
            self.mod.FORECAST = f.name
            return self.mod.trajetoria_nivel("ao_vivo")
        finally:
            self.mod.FORECAST = antigo
            os.unlink(f.name)

    def test_sem_nivel_atual_nao_publica(self):
        for prev in ({"telemetria_ultima_nivel_cm": None, "telemetria_ultima_em": "2026-10-20T19:45:00"},
                     {"telemetria_ultima_nivel_cm": None, "telemetria_ultima_em": None, "nivel_atual_cm": 186}):
            prev["horizontes"] = {"2h": {"disponivel": True, "passos": [["x", 202, 265]]}}
            pts, _rot, nivel, _em = self.trajetoria(prev)
            with self.subTest(previsao=prev):
                self.assertIsNone(pts)
                self.assertIsNone(nivel)

    def test_trajetoria_parte_do_nivel_atual(self):
        pts, _rot, nivel, em = self.trajetoria({
            "telemetria_ultima_nivel_cm": 202, "telemetria_ultima_em": "2026-10-20T19:45:00",
            "horizontes": {"2h": {"disponivel": True, "passos": [["2026-10-20T19:00:00", 202, 313]]},
                           "4h": {"disponivel": True, "passos": [["2026-10-20T19:00:00", 202, 433]]}}})
        self.assertEqual(pts[:3], [(0, 2.02), (75, 3.13), (195, 4.33)])
        self.assertEqual(nivel, 202.0)
        self.assertEqual(em, "2026-10-20T19:45:00")

    def test_mudar_o_template_republica(self):
        meta = {"gerado_em": "2026-10-21 10:00", "template": self.mod.hashlib.sha1(
            self.mod._TEMPLATE.encode("utf-8")).hexdigest()[:12], "nivel_txt": "2,02 m"}
        quadras = [{"lat": -29.17, "lon": -51.73, "classe": "alagada"}]
        with tempfile.TemporaryDirectory() as tmp:
            j = os.path.join(tmp, "rota.json")
            self.mod.escreve_json(quadras, meta, j)
            self.assertTrue(self.mod.mesmo_conteudo(j, quadras, dict(meta, gerado_em="2026-10-21 10:05")))
            self.assertFalse(self.mod.mesmo_conteudo(j, quadras, dict(meta, template="outro")))
            self.assertFalse(self.mod.mesmo_conteudo(j, quadras, dict(meta, nivel_txt="2,10 m")))

    def test_ponto_seguro_e_o_do_geojson(self):
        abrigos = json.load(open(RAIZ / "assets/data/servicos/abrigos.geojson", encoding="utf-8"))
        gin = next(f for f in abrigos["features"] if f["properties"]["municipio"] == "Santa Tereza")
        lon, lat = gin["geometry"]["coordinates"][:2]
        self.assertEqual((self.mod.PONTO_SEGURO["lat"], self.mod.PONTO_SEGURO["lon"]), (lat, lon))
        self.assertNotIn("PLACEHOLDER", self.mod.PONTO_SEGURO["nome"])


class PaginasTest(unittest.TestCase):
    PAINEIS = [PASTA / "gerar_painel.py", RAIZ / "santa_tereza_painel_casas.html", RAIZ / "mucum_painel_casas.html"]
    # As páginas _usuario usam o mesmo assets/previsao_fila.js (a cópia _usuario foi removida).
    FILAS = [RAIZ / "assets" / "previsao_fila.js"]

    def test_rota_molhada_nao_sai_verde(self):
        for p in self.PAINEIS:
            s = p.read_text(encoding="utf-8")
            with self.subTest(arquivo=p.name):
                self.assertIn("cam=rotaPorTrecho(casa,", s)
                self.assertNotIn("cam=L.polyline(cadeia(casa[CF.no],D.prox,base()),{color:'#0f8b46'", s)
                self.assertNotIn("abrigar-se no local", s)
                # rotas por nível têm passo de 1 m: o corte fica ENTRE dois níveis
                self.assertIn("A água corta a rota entre ${txtNivel(hs[k-1])} e ${txtNivel(hs[k])}", s)
                self.assertIn("40199", s)

    def test_canais_oficiais_nas_paginas_de_rota(self):
        paginas = self.PAINEIS + [PASTA / "gerar_rota_fuga_santa_tereza.py"] + [RAIZ / p for p in (
            "santa_tereza_painel_evacuacao.html", "mucum_painel_evacuacao.html",
            "pesquisas/santa-tereza-painel-evacuacao.html", "pesquisas/mucum-painel-evacuacao.html",
            "santa_tereza_rota_fuga_ruas_cenario.html", "mucum_rota_fuga_ruas_cenario.html",
            "pesquisas/santa-tereza-rota-fuga-ruas-cenario.html", "pesquisas/mucum-rota-fuga-ruas-cenario.html")]
        antigas = [RAIZ / p for p in (
            "santa_tereza_rota_fuga_cenario.html", "pesquisas/santa-tereza-rota-fuga.html",
            "pesquisas/santa-tereza-rota-fuga-ruas.html", "pesquisas/mucum-rota-fuga-ruas.html",
            "pesquisas/mucum-rota-fuga-ruas-fixo.html")]
        paginas += antigas
        for p in paginas:
            s = p.read_text(encoding="utf-8")
            with self.subTest(arquivo=str(p.relative_to(RAIZ))):
                self.assertIn("<b>193</b>", s)
                self.assertIn("<b>199</b>", s)
                self.assertIn("<b>40199</b>", s)
                if "rota_fuga_ruas_cenario" in p.name or "rota-fuga-ruas-cenario" in p.name or p in antigas:
                    self.assertIn("painel_casas.html#rotas", s)

    def test_paineis_por_grade_sobem_90(self):
        # 40 cm/h dava margem 2 a 5 vezes maior que a subida observada
        for p in ("santa_tereza_painel_evacuacao.html", "mucum_painel_evacuacao.html",
                  "pesquisas/santa-tereza-painel-evacuacao.html", "pesquisas/mucum-painel-evacuacao.html"):
            s = (RAIZ / p).read_text(encoding="utf-8")
            with self.subTest(arquivo=p):
                self.assertIn('"taxa_cm_h":90.0', s)
                self.assertIn('id="sldTaxa" min="10" max="200" value="90"', s)
                self.assertNotIn("ritmo de recorde", s)

    def test_fila_sem_frases_de_comando(self):
        for p in self.FILAS:
            s = p.read_text(encoding="utf-8")
            for frase in ("SAIR AGORA", "Ninguém precisa sair", "ainda seguro", "só pela água", "último corredor"):
                with self.subTest(arquivo=p.name, frase=frase):
                    self.assertNotIn(frase, s)


if __name__ == "__main__":
    unittest.main()
