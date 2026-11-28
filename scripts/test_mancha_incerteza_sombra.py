"""Testes do robô sombra da mancha com incerteza de Muçum."""
import json, os, shutil, sys, tempfile, unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(RAIZ, "codigo_python", "01_previsao_ao_vivo"))
import gerar_mancha_incerteza_mucum_sombra as R  # noqa: E402

PASTA = os.path.join(RAIZ, R.PASTA)


def tabelas():
    with open(os.path.join(PASTA, "tabela_incerteza.json"), encoding="utf-8") as f:
        tab = json.load(f)
    with open(os.path.join(PASTA, "expostos_por_hand.json"), encoding="utf-8") as f:
        exp = json.load(f)
    return tab, exp


class TestTabelas(unittest.TestCase):
    def test_quantis_ordenados_e_grupo_geral(self):
        tab, _ = tabelas()
        for H in ("4", "8", "12"):
            self.assertIn("todos|todos", tab["horizontes"][H])
            for k, g in tab["horizontes"][H].items():
                self.assertEqual(len(g["q"]), 99, k)
                self.assertEqual(g["q"], sorted(g["q"]), k)
                self.assertGreaterEqual(g["eventos"], tab["min_eventos_grupo"], k)

    def test_expostos_acumulados(self):
        _, exp = tabelas()
        for k, v in exp["series"].items():
            self.assertEqual(len(v), 250, k)
            self.assertTrue(all(b >= a for a, b in zip(v, v[1:])), k)


class TestCalculo(unittest.TestCase):
    def setUp(self):
        self.tab, exp = tabelas()
        self.series = exp["series"]

    def prev(self, atual, previsto, H=4):
        return {"horizonte_h": H, "disponivel": True, "nivel_modelo_cm": atual, "nivel_previsto_cm": previsto,
                "hora_modelo": "2026-09-21T20:00:00", "hora_alvo": "2026-09-22T00:00:00", "modelo_papel": "principal"}

    def test_cheia_grande_contornos_em_ordem(self):
        obs = {"2026-09-21T20:00": 1526.0, "2026-09-21T19:00": 1490.0}
        r = R.calcula("8h", self.prev(1526, 1901, 8), self.tab, self.series, obs)
        h = r["hand_m"]
        self.assertTrue(h["90"] <= h["50"] <= h["10"])
        f = r["faixa_nivel_cm"]
        self.assertTrue(f["p10"] <= f["p50"] <= f["p90"])
        e = r["expostos"]
        self.assertTrue(e["90"]["pessoas"] <= e["50"]["pessoas"] <= e["10"]["pessoas"])
        self.assertEqual(r["situacao"], "subindo forte")
        # mesma ordem de grandeza da Fase 3 (E75, 8 h: HAND 11,5 / 14,0 / 16,7 m)
        self.assertAlmostEqual(h["50"], 14.0, delta=0.3)

    def test_rio_na_calha_sem_expostos(self):
        r = R.calcula("4h", self.prev(210, 200), self.tab, self.series, {})
        self.assertIsNone(r["hand_m"]["50"])
        self.assertEqual(r["expostos"]["50"]["pessoas"], 0)
        self.assertEqual(r["situacao"], "todos")  # sem série observada: grupo geral

    def test_2h_usa_tabela_de_4h(self):
        r = R.calcula("2h", self.prev(900, 950, 2), self.tab, self.series, {})
        self.assertTrue(r["proxy_horizonte"])
        self.assertEqual(r["tabela_residuos_h"], 4)

    def test_indisponivel(self):
        d = self.prev(500, None, 8)
        d["disponivel"] = False
        r = R.calcula("8h", d, self.tab, self.series, {})
        self.assertFalse(r["disponivel"])


class TestPagina(unittest.TestCase):
    def test_exemplo_e_pagina(self):
        with open(os.path.join(PASTA, "exemplo_cheia_set2026.json"), encoding="utf-8") as f:
            ex = json.load(f)
        self.assertEqual(ex["modo"], "exemplo")
        for k in ("4h", "8h", "12h"):
            r = ex["horizontes"][k]
            h = r["hand_m"]
            self.assertTrue(h["90"] <= h["50"] <= h["10"], k)
            self.assertIn("pessoas", r["observado"]["expostos"])
        with open(os.path.join(RAIZ, "mucum_mancha_incerteza_sombra.html"), encoding="utf-8") as f:
            html = f.read()
        for trecho in ("sombra_atual.json", "exemplo_cheia_set2026.json", "contornos_extravasamento.json",
                       "não é alerta oficial", 'name="robots" content="noindex"'):
            self.assertIn(trecho, html)


class TestRoboponta(unittest.TestCase):
    def test_roda_e_confere(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, R.PASTA))
            for f in ("tabela_incerteza.json", "expostos_por_hand.json"):
                shutil.copy(os.path.join(PASTA, f), os.path.join(tmp, R.PASTA, f))
            prev = {"gerado_em": "2026-09-21T20:00:00", "horizontes": {"4h": {
                "horizonte_h": 4, "disponivel": True, "nivel_modelo_cm": 1526, "nivel_previsto_cm": 1750,
                "hora_modelo": "2026-09-21T20:00:00", "hora_alvo": "2026-09-22T00:00:00", "modelo_papel": "principal"}}}
            with open(os.path.join(tmp, R.PREV), "w", encoding="utf-8") as f:
                json.dump(prev, f)
            os.makedirs(os.path.dirname(os.path.join(tmp, R.CACHE)), exist_ok=True)
            cache = {"estacoes": {R.ESTACAO: [["2026-09-21T19:00:00", 1490.0], ["2026-09-21T20:00:00", 1526.0],
                                              ["2026-09-22T00:00:00", 1759.0]]}}
            with open(os.path.join(tmp, R.CACHE), "w", encoding="utf-8") as f:
                json.dump(cache, f)
            sys.argv = ["x", "--raiz", tmp]
            R.main()
            with open(os.path.join(tmp, R.PASTA, "sombra_atual.json"), encoding="utf-8") as f:
                s = json.load(f)
            self.assertEqual(s["modo"], "sombra")
            self.assertEqual(s["verificacao"]["4h"]["n"], 1)
            R.main()  # segunda rodada não duplica o histórico
            with open(os.path.join(tmp, R.PASTA, "historico_sombra.jsonl"), encoding="utf-8") as f:
                self.assertEqual(len([l for l in f if l.strip()]), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
