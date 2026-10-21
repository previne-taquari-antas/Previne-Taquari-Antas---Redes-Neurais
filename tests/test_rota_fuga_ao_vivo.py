#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes das rotas de fuga ao vivo: hora, nível do rio e o que a página mostra.

Sem LiDAR nem OSM. Cobrem os erros achados na revisão de out/2026:
  - hora sem fuso lida como hora do runner (UTC): idade do dado +180 min;
  - nível atual ausente virando 0 m (rio "seco" que sobe até a previsão);
  - Muçum grava [hora, modelo, agora, previsto] e o índice 2 é o nível de agora;
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
        self.assertIsNone(nv.nivel_atual_cm({}))
        self.assertIsNone(nv.nivel_atual_cm({"telemetria_ultima_nivel_cm": None}))
        self.assertEqual(nv.nivel_atual_cm({"telemetria_ultima_nivel_cm": 0}), 0.0)
        self.assertEqual(nv.nivel_atual_cm({"nivel_atual_cm": 186}), 186.0)

    def test_previsto_santa_tereza(self):
        d = {"horizontes": {"2h": {"disponivel": True, "nivel_previsto_cm": 313,
                                   "passos": [["2026-10-20T19:00:00", 202, 313]]},
                            "4h": {"disponivel": True, "passos": [["2026-10-20T19:00:00", 202, 433]]}}}
        self.assertEqual(nv.previstos_cm(d), [("2h", 120, 313.0), ("4h", 240, 433.0)])

    def test_previsto_mucum_nao_le_o_nivel_de_agora(self):
        # formato de Muçum: [hora, modelo, nível agora, previsto]
        d = {"horizontes": {"4h": {"disponivel": True, "nivel_previsto_cm": 344,
                                   "passos": [["2026-10-20T20:00:00", 173, 171, 344]]}}}
        self.assertEqual(nv.previstos_cm(d), [("4h", 240, 344.0)])
        d["horizontes"]["4h"].pop("nivel_previsto_cm")
        self.assertEqual(nv.previstos_cm(d), [("4h", 240, 344.0)])

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
        pts, _rot, nivel, _em = self.trajetoria({
            "telemetria_ultima_nivel_cm": None, "telemetria_ultima_em": "2026-10-20T19:45:00",
            "horizontes": {"2h": {"disponivel": True, "passos": [["x", 202, 265]]}}})
        self.assertIsNone(pts)
        self.assertIsNone(nivel)

    def test_trajetoria_parte_do_nivel_atual(self):
        pts, _rot, nivel, em = self.trajetoria({
            "telemetria_ultima_nivel_cm": 202, "telemetria_ultima_em": "2026-10-20T19:45:00",
            "horizontes": {"2h": {"disponivel": True, "passos": [["x", 202, 313]]},
                           "4h": {"disponivel": True, "passos": [["x", 202, 433]]}}})
        self.assertEqual(pts[:3], [(0, 2.02), (120, 3.13), (240, 4.33)])
        self.assertEqual(nivel, 202.0)
        self.assertEqual(em, "2026-10-20T19:45:00")

    def test_ponto_seguro_e_o_do_geojson(self):
        abrigos = json.load(open(RAIZ / "assets/data/servicos/abrigos.geojson", encoding="utf-8"))
        gin = next(f for f in abrigos["features"] if f["properties"]["municipio"] == "Santa Tereza")
        lon, lat = gin["geometry"]["coordinates"][:2]
        self.assertEqual((self.mod.PONTO_SEGURO["lat"], self.mod.PONTO_SEGURO["lon"]), (lat, lon))
        self.assertNotIn("PLACEHOLDER", self.mod.PONTO_SEGURO["nome"])


class PaginasTest(unittest.TestCase):
    PAINEIS = [PASTA / "gerar_painel.py", RAIZ / "santa_tereza_painel_casas.html", RAIZ / "mucum_painel_casas.html"]
    FILAS = [RAIZ / "assets" / "previsao_fila.js", RAIZ / "assets" / "previsao_fila_usuario.js"]

    def test_rota_molhada_nao_sai_verde(self):
        for p in self.PAINEIS:
            s = p.read_text(encoding="utf-8")
            with self.subTest(arquivo=p.name):
                self.assertIn("cam=rotaPorTrecho(casa,", s)
                self.assertNotIn("cam=L.polyline(cadeia(casa[CF.no],D.prox,base()),{color:'#0f8b46'", s)
                self.assertNotIn("abrigar-se no local", s)
                self.assertIn("40199", s)

    def test_fila_sem_frases_de_comando(self):
        for p in self.FILAS:
            s = p.read_text(encoding="utf-8")
            for frase in ("SAIR AGORA", "Ninguém precisa sair", "ainda seguro", "só pela água", "último corredor"):
                with self.subTest(arquivo=p.name, frase=frase):
                    self.assertNotIn(frase, s)


if __name__ == "__main__":
    unittest.main()
