#!/usr/bin/env python3
"""Testes do robô em sombra de Muçum (RNAs v2): contrato de chuva, QC ao vivo e hierarquia."""
from __future__ import annotations

import datetime as dt
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "codigo_python" / "01_previsao_ao_vivo" / "gerar_previsao_sombra_mucum.py"
SPEC = importlib.util.spec_from_file_location("sombra_mucum", SCRIPT)
S = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(S)

T0 = dt.datetime(2026, 9, 22, 10, 0)


def horas(n, inicio=T0):
    return [inicio - dt.timedelta(hours=i) for i in range(n)]


class SombraMucumTests(unittest.TestCase):
    def test_rain_hour_label_is_past_only(self) -> None:
        xml = b"""<?xml version="1.0"?><root>
        <r><DataHora>2026-09-22 09:15:00</DataHora><Nivel>500</Nivel><Chuva>1</Chuva></r>
        <r><DataHora>2026-09-22 10:00:00</DataHora><Nivel>510</Nivel><Chuva>2</Chuva></r>
        <r><DataHora>2026-09-22 10:15:00</DataHora><Nivel>515</Nivel><Chuva>4</Chuva></r>
        <r><DataHora>2026-09-22 10:30:00</DataHora><Nivel>520</Nivel><Chuva>-1</Chuva></r>
        </root>"""
        niveis, chuva = S.series_da_resposta(xml)
        self.assertEqual(niveis, {T0: 510.0})                  # só hora cheia exata
        self.assertEqual(chuva[T0], 3.0)                      # (09:00, 10:00] = 09:15 + 10:00
        self.assertEqual(chuva[T0 + dt.timedelta(hours=1)], 4.0)  # 10:15 vai para 11:00; negativo ignorado

    def test_mean_of_station_accumulations(self) -> None:
        chuva = {"A": {h: 1.0 for h in horas(6)}, "B": {h: 2.0 for h in horas(5)}, "C": {}}
        inp = {"tipo": "chuva_acum", "janela_h": 6, "estacoes": ["A", "B", "C"], "nome": "c"}
        x, faltam = S.montar_entradas([inp], {}, chuva, T0)
        self.assertEqual(x, [6.0])          # B incompleto e C vazio ficam fora (COUNT/AVERAGE)
        x, faltam = S.montar_entradas([dict(inp, estacoes=["C"])], {}, chuva, T0)
        self.assertEqual(faltam, ["c"])     # nenhum posto com valor -> ausente, nunca zero

    def test_rain_difference_is_mean_of_station_differences(self) -> None:
        chuva = {"A": {h: (2.0 if i < 24 else 1.0) for i, h in enumerate(horas(48))}}
        inp = {"tipo": "chuva_diferenca", "janela_h": 24, "janela_anterior_h": 24, "estacoes": ["A"], "nome": "d"}
        x, _ = S.montar_entradas([inp], {}, chuva, T0)
        self.assertEqual(x, [24.0])

    def test_level_formulas_match_training(self) -> None:
        n = {"X": {h: float(100 + 10 * (20 - i) + (i % 3)) for i, h in enumerate(horas(21))}}
        inputs = [{"tipo": "nivel", "estacao": "X", "defasagem_h": 0, "nome": "n"},
                  {"tipo": "vel_nivel", "estacao": "X", "defasagem_h": 4, "nome": "d4"},
                  {"tipo": "acel_nivel", "estacao": "X", "defasagem_h": 12, "nome": "a12"}]
        x, faltam = S.montar_entradas(inputs, n, {}, T0)
        N = lambda k: n["X"][T0 - dt.timedelta(hours=k)]
        self.assertEqual(faltam, [])
        self.assertEqual(x, [N(0), N(0) - N(4), (N(0) - N(1)) - (N(12) - N(13))])

    def test_exp_idw_rain_filter(self) -> None:
        # 2 postos, 1 sub-bacia; B sem dado em uma hora -> só A entra (IDW renormaliza)
        hs = sorted(horas(60))
        chuva = {"A": {h: 0.0 for h in hs}, "B": {h: 0.0 for h in hs}}
        chuva["A"][T0 - dt.timedelta(hours=1)] = 4.0
        chuva["B"][T0 - dt.timedelta(hours=1)] = 2.0
        chuva["B"].pop(T0)
        chuva["A"][T0] = 3.0
        inp = {"tipo": "chuva_exp_idw", "tau_h": 12, "postos": ["A", "B"], "pesos_idw_sub_x_posto": [[1.0, 1.0]],
               "areas_km2": [10.0], "nome": "c"}
        x, faltam = S.montar_entradas([inp], {}, chuva, T0)
        a = 2.718281828459045 ** (-1 / 12)
        self.assertEqual(faltam, [])
        self.assertAlmostEqual(x[0], a * 3.0 + 3.0, places=9)
        # janela curta (sem aquecimento) -> ausente
        curto = {"A": {h: 1.0 for h in horas(10)}}
        x, faltam = S.montar_entradas([dict(inp, postos=["A"], pesos_idw_sub_x_posto=[[1.0]])], {}, curto, T0)
        self.assertEqual(faltam, ["c"])

    def test_mm3_level_is_mean_of_last_three_hourly_changes(self) -> None:
        n = {"X": {T0: 130.0, T0 - dt.timedelta(hours=1): 120.0, T0 - dt.timedelta(hours=2): 100.0, T0 - dt.timedelta(hours=3): 100.0}}
        inp = {"tipo": "mm3_nivel", "estacao": "X", "nome": "m"}
        x, _ = S.montar_entradas([inp], n, {}, T0)
        self.assertAlmostEqual(x[0], (10 + 20 + 0) / 3)
        n["X"].pop(T0 - dt.timedelta(hours=3))                    # 2 variações bastam (min_periods=2 do treino)
        self.assertAlmostEqual(S.montar_entradas([inp], n, {}, T0)[0][0], 15.0)
        n["X"].pop(T0 - dt.timedelta(hours=1))                    # só 0 variação completa -> ausente
        self.assertEqual(S.montar_entradas([inp], n, {}, T0)[1], ["m"])

    def test_area_rain_idw_windows(self) -> None:
        S.POSTOS_IDW[:] = ["A", "B"]
        S.REGIOES_CHUVA.clear()
        S.REGIOES_CHUVA["R"] = {"areas_km2": [1.0, 3.0], "pesos_idw_sub_x_posto": [[1.0, 0.0001], [0.0001, 1.0]]}
        S._CACHE_AREA.clear()
        hs = horas(60)
        chuva = {"A": {h: 1.0 for h in hs}, "B": {h: 2.0 for h in hs}}
        chuva["B"].pop(T0)                                        # só A na hora T0 -> as duas sub-bacias recebem A
        base = lambda k: {"tipo": "chuva_area", "regiao": "R", "nome": f"c{k}"}
        x, faltam = S.montar_entradas([base(1) | {"op": "acum", "janela_h": 2}, base(2) | {"op": "dif", "janela_h": 24}], {}, chuva, T0)
        p = (1.0 * (1 + 0.0001 * 2) / 1.0001 + 3.0 * (0.0001 * 1 + 2) / 1.0001) / 4   # média por área numa hora com A e B
        self.assertEqual(faltam, [])
        self.assertAlmostEqual(x[0], 1.0 + p, places=9)
        self.assertAlmostEqual(x[1], (1.0 + 23 * p) - 24 * p, places=9)
        vazio = {"A": {}, "B": {}}
        self.assertEqual(S.montar_entradas([base(3) | {"op": "acum", "janela_h": 2}], {}, vazio, T0)[1], ["c3"])   # nunca zero
        S._CACHE_AREA.clear()

    def test_mixture_uses_first_complete_ridge_and_trees(self) -> None:
        import json, tempfile
        from unittest import mock
        arv = {"colunas": ["a"], "modelos": [{"base_score": 10.0, "arvores": [[[0, 5.0, 1, 2, 2, 0.0], [-1, 0, -1, -1, -1, 1.0], [-1, 0, -1, -1, -1, -1.0]]]}]}
        self.assertEqual(S.avaliar_xgb(arv, [3.0]), 11.0)
        self.assertEqual(S.avaliar_xgb(arv, [None]), 9.0)          # faltante -> ramo padrão
        niveis = {S.ALVO: {h: 500.0 for h in horas(3)}}
        nivel = lambda est: {"tipo": "nivel", "estacao": est, "defasagem_h": 0, "nome": f"n{est}"}
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "x.json"
            arq.write_text(json.dumps(arv), encoding="utf-8")
            m = {"modelo_id": "mix", "tipo_modelo": "mistura", "nivel_hierarquia": 1, "peso_xgb": 0.5,
                 "xgb": {"arquivo": str(arq), "inputs": [nivel("86472000")]},
                 "lineares": [{"nome": "CTRL", "intercepto": 0.0, "coeficientes": [1.0], "inputs": [nivel("86472000")]},
                              {"nome": "MU9", "intercepto": 20.0, "coeficientes": [0.0], "inputs": [nivel(S.ALVO)]}]}
            with mock.patch.object(S.R, "antecedencia_efetiva", return_value=(3.5, True)):
                escolhido, _ = S.prever_horizonte({"horizonte_h": 4, "modelos": [m]}, niveis, {}, sorted(niveis[S.ALVO]), T0)
        self.assertEqual(escolhido["linear_usado"], "MU9")          # sem LJJ -> cai para o ridge só de Muçum
        self.assertEqual(escolhido["nivel_previsto_cm"], 500.0 + 0.5 * 9.0 + 0.5 * 20.0)

    def test_daily_rain_qc_drops_excess_day(self) -> None:
        d = dt.datetime(2026, 9, 21, 1, 0)
        hs = [d + dt.timedelta(hours=i) for i in range(23)]
        postos = ["A", "B", "C", "D", "E"]
        chuva = {p: {h: 1.0 for h in hs} for p in postos}
        chuva["C"] = {h: 10.0 for h in hs}          # 230 mm no dia contra 23 mm dos vizinhos
        chuva["A"][T0] = 150.0                        # hora > 100 mm
        limpa = S.qc_chuva_postos(chuva, postos)
        self.assertEqual(limpa["C"], {})
        self.assertNotIn(T0, limpa["A"])
        self.assertEqual(len(limpa["B"]), 23)

    def test_live_qc_drops_zero_bitflip_and_stuck_sensor(self) -> None:
        alvo = {h: 500.0 + 10 * i for i, h in enumerate(horas(10))}   # Muçum variando 90 cm
        serie = {h: 42500.0 for h in horas(8)}                         # barragem travada 8 h
        serie[T0 - dt.timedelta(hours=9)] = 0.0
        limpa = S.qc_niveis("86489000", serie, {"86489000": {"min": 40000, "max": 50000}}, alvo)
        self.assertEqual(limpa, {})
        regua = {T0: 16438.0, T0 - dt.timedelta(hours=1): 120.0}
        self.assertEqual(S.qc_niveis("86099000", regua, {}, alvo), {T0 - dt.timedelta(hours=1): 120.0})

    def test_live_qc_drops_impossible_jump_until_level_returns(self) -> None:
        # 86298000 em 06/10/2026: 171 -> 1475 -> 1892 cm em 2 h sem cheia; volta a 180
        t0 = dt.datetime(2026, 10, 6, 6, 0)
        valores = [172, 171, 254, 1475, 1870, 1802, 1860, 1892, 180]
        serie = {t0 + dt.timedelta(hours=i): float(v) for i, v in enumerate(valores)}
        limpa = S.qc_niveis(S.ALVO, serie, {S.ALVO: {"min": 1, "max": 3260, "salto_max_1h": 696}})
        self.assertEqual(sorted(limpa.values()), [171.0, 172.0, 180.0, 254.0])
        # interrupção real (> 3 h sem leitura) refaz a âncora
        serie2 = {t0: 200.0, t0 + dt.timedelta(hours=5): 1200.0, t0 + dt.timedelta(hours=6): 1210.0}
        self.assertEqual(len(S.qc_niveis(S.ALVO, serie2, {S.ALVO: {"salto_max_1h": 696}})), 3)

    def test_shadow_contracts_are_consistent(self) -> None:
        import json
        for nome in ("mucum_modelos_sombra.json", "santa_tereza_modelos_sombra.json"):
            caminho = ROOT / "assets" / "data" / nome
            if not caminho.exists():
                continue
            contrato = json.loads(caminho.read_text(encoding="utf-8"))
            self.assertIn(contrato["alvo"], contrato["limites_estacao_cm"])
            for chave, hz in contrato["horizontes"].items():
                niveis = [m["nivel_hierarquia"] for m in hz["modelos"] if m["nivel_hierarquia"] >= 1]   # nível 0 = só registro
                self.assertEqual(len(niveis), len(set(niveis)), f"{nome} {chave}: nível repetido")
                for m in hz["modelos"]:
                    if m.get("tipo_modelo") == "mistura":
                        arq = ROOT / m["xgb"]["arquivo"]
                        self.assertTrue(arq.exists(), m["xgb"]["arquivo"])
                        self.assertEqual(S._sha256(str(arq)), m["xgb"]["sha256"].upper())
                        mod = json.loads(arq.read_text(encoding="utf-8"))
                        self.assertEqual(mod["colunas"], [i["nome"] for i in m["xgb"]["inputs"]])
                        for v in mod["verificacao"]:                 # árvores em Python puro = xgboost no treino
                            self.assertAlmostEqual(S.avaliar_xgb(mod, v["x"]), v["y"], places=6)
                        for lin in m["lineares"]:
                            self.assertEqual(len(lin["coeficientes"]), len(lin["inputs"]))
                            self.assertEqual(lin["inputs"][0]["estacao"], contrato["alvo"])
                        for i in m["xgb"]["inputs"] + [j for lin in m["lineares"] for j in lin["inputs"]]:
                            if i["tipo"] == "chuva_area":
                                rg = contrato["regioes_chuva"][i["regiao"]]
                                self.assertEqual(len(rg["pesos_idw_sub_x_posto"]), len(rg["areas_km2"]))
                                self.assertTrue(all(len(w) == len(contrato["postos_chuva_idw"]) for w in rg["pesos_idw_sub_x_posto"]))
                        self.assertTrue(set(contrato["postos_chuva_idw"]) <= set(contrato["qc_chuva_postos"]))
                        for est in m["estacoes_nivel"]:
                            self.assertIn(est, contrato["limites_estacao_cm"])
                        continue
                    if m.get("tipo_modelo") == "linear":
                        self.assertEqual(len(m["coeficientes"]), m["n_inputs"])
                        for i in m["inputs"]:
                            if i["tipo"] == "chuva_exp_idw":
                                self.assertEqual(len(i["pesos_idw_sub_x_posto"]), len(i["areas_km2"]))
                                self.assertTrue(all(len(w) == len(i["postos"]) for w in i["pesos_idw_sub_x_posto"]))
                                self.assertTrue(set(i["postos"]) <= set(contrato.get("qc_chuva_postos", [])))
                    else:
                        mat = ROOT / m["mat"]
                        self.assertTrue(mat.exists(), m["mat"])
                        self.assertEqual(S._sha256(str(mat)), m["modelo_sha256"].upper(), m["mat"])
                    self.assertEqual(len(m["inputs"]), m["n_inputs"])
                    self.assertEqual(m["inputs"][0]["tipo"], "nivel")
                    self.assertEqual(m["inputs"][0]["estacao"], contrato["alvo"])   # âncora ALT
                    for est in m["estacoes_nivel"]:
                        self.assertIn(est, contrato["limites_estacao_cm"])

    def test_hierarchy_skips_control_and_falls_back_when_inputs_missing(self) -> None:
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            mat = str(Path(d) / "m.mat")
            Path(mat).write_bytes(b"x")
            niveis = {S.ALVO: {h: 500.0 for h in horas(3)}}
            nivel = lambda est: [{"tipo": "nivel", "estacao": est, "defasagem_h": 0, "nome": f"n{est}"}]
            cfg = {"horizonte_h": 4, "modelos": [
                {"modelo_id": "ctrl", "nivel_hierarquia": 0, "mat": mat, "inputs": nivel(S.ALVO)},
                {"modelo_id": "n1", "nivel_hierarquia": 1, "mat": mat, "inputs": nivel("86472000")},
                {"modelo_id": "n2", "nivel_hierarquia": 2, "mat": mat, "inputs": nivel(S.ALVO),
                 "faixa_e95_cm": {"geral": 40.0}},
            ]}
            with mock.patch.object(S.R, "prever", return_value=12.0), \
                 mock.patch.object(S.R, "antecedencia_efetiva", return_value=(3.5, True)):
                escolhido, todos = S.prever_horizonte(cfg, niveis, {}, sorted(niveis[S.ALVO]), T0)
        self.assertEqual(escolhido["modelo"], "n2")              # n1 sem LJJ; controle nunca é escolhido
        self.assertEqual([t["status"] for t in todos], ["ok", "entradas incompletas (1)", "ok"])
        self.assertEqual(escolhido["nivel_previsto_cm"], 512.0)
        self.assertEqual(escolhido["faixa_incerteza"]["min_cm"], 472)


if __name__ == "__main__":
    unittest.main()
