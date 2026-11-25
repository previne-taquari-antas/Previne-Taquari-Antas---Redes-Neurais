#!/usr/bin/env python3
"""Deterministic contract tests for the Santa Tereza live feed.

These tests read the current feed and MAT hash. The one network-path regression
test uses a mocked ANA response, never reaches the network, and never writes
dynamic JSON, so the suite is safe to run in CI or locally.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from .validar_previsao_ao_vivo import B_MAT, validate_data
except ImportError:  # execução direta: python scripts/test_...py
    from validar_previsao_ao_vivo import B_MAT, validate_data


ROOT = Path(__file__).resolve().parents[1]


class LiveFeedContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = json.loads((ROOT / "previsao_ao_vivo.json").read_text(encoding="utf-8"))

    def test_current_feed_schema_and_forward_metadata(self) -> None:
        validate_data(self.data, b_mat=B_MAT)

    def make_total_outage_feed(self):
        from previne.robo import gerar_previsao_ao_vivo as robo
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "outage.json"
            with patch.object(robo, "SAIDA", str(output)), \
                 patch.object(robo, "carregar_historico", return_value=[]), \
                 patch.dict(robo.ULTIMA_RAW, {}, clear=True):
                robo.escrever_pacote_indisponivel("sem dado recente em Santa Tereza", "consulta indisponivel")
            return json.loads(output.read_text(encoding="utf-8"))

    def test_total_ana_outage_publishes_explicit_unavailability(self):
        data = self.make_total_outage_feed()
        self.assertEqual(data["serie_observada_ana"], [])
        self.assertEqual(data["serie_observada_ana_n"], 0)
        self.assertEqual(data["serie_observada_ana_status"], "INDISPONIVEL")
        validate_data(data, b_mat=B_MAT)

    def test_empty_observations_never_authorize_a_forecast(self):
        data = self.make_total_outage_feed()
        data["horizontes"]["4h"]["nivel_previsto_cm"] = 500
        with self.assertRaises(SystemExit):
            validate_data(data, b_mat=B_MAT)

    def test_empty_observations_do_not_skip_model_hash_checks(self):
        data = self.make_total_outage_feed()
        data["horizontes"]["2h"]["modelo_sha256"] = "INVALIDO"
        with self.assertRaisesRegex(SystemExit, "hash"):
            validate_data(data, b_mat=B_MAT)

    def test_empty_observations_cannot_claim_current_telemetry(self):
        data = self.make_total_outage_feed()
        data["telemetria_ultima_nivel_cm"] = 200
        with self.assertRaises(SystemExit):
            validate_data(data, b_mat=B_MAT)

    def test_hand_zero_is_separate_from_official_flood_level(self) -> None:
        self.assertEqual(self.data["bankfull_cm"], 1500)
        self.assertEqual(self.data["hand_zero_cm"], 160)
        for horizon in ("2h", "4h", "8h"):
            self.assertEqual(self.data["horizontes"][horizon]["hand_zero_cm"], 160)

    def test_page_uses_field_zero_for_spatialization(self) -> None:
        page = (ROOT / "santa_tereza_previsao_inundacao.html").read_text(encoding="utf-8")
        self.assertIn("HAND_ZERO_DEFAULT_CM=160", page)
        self.assertIn("const COTA_INUND=1500", page)
        self.assertIn("function stageToSpatialHand(cm,zeroCm=HAND_ZERO_DEFAULT_CM)", page)
        self.assertIn("(Number(cm)-Number(zeroCm))/100", page)
        self.assertIn("contornos_mancha.json", page)
        self.assertNotIn("Number(cm)-COTA_INUND", page)

    def test_generated_hand_diagnostic_is_main_river_only(self) -> None:
        diagnostic = json.loads(
            (ROOT / "assets" / "data" / "santa_tereza_inundacao" / "hand_lidar_5m_diagnostic.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(diagnostic["hand_zero_cm"], 160)
        self.assertEqual(diagnostic["flowacc_threshold_fine_cells"], 50_000_000)
        self.assertEqual(diagnostic["componentes_mantidos"], 1)
        self.assertGreater(diagnostic["celulas_rio_principal"], 0)
        self.assertGreaterEqual(diagnostic["contornos_features"], 151)
        if "contour_max_m" in diagnostic:
            self.assertEqual(diagnostic["contour_max_m"], 25.0)

    def test_explicit_4h_without_prediction_is_valid(self) -> None:
        data = copy.deepcopy(self.data)
        four = data["horizontes"]["4h"]
        four["nivel_previsto_cm"] = None
        four["disponivel"] = False
        four["status"] = "inputs incompletos — sem previsão nesta hora"
        four["auditoria_inputs"] = {"status": "ATENCAO"}
        validate_data(data, b_mat=B_MAT)

    def test_legacy_cascata_is_rejected_from_public_feed(self) -> None:
        data = copy.deepcopy(self.data)
        data["horizontes"]["4h"]["modelo"] = "4h_cascata_legado"
        with self.assertRaises(SystemExit):
            validate_data(data, b_mat=B_MAT)

    def test_unexpected_horizon_is_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["horizontes"]["4h_cascata"] = copy.deepcopy(data["horizontes"]["4h"])
        with self.assertRaises(SystemExit):
            validate_data(data, b_mat=B_MAT)

    def test_non_exact_4h_timestamp_is_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["horizontes"]["4h"]["hora_modelo"] = "2026-08-16T08:30:00"
        with self.assertRaises(SystemExit):
            validate_data(data, b_mat=B_MAT)

    def test_missing_prediction_cannot_be_marked_available(self) -> None:
        data = copy.deepcopy(self.data)
        two = data["horizontes"]["2h"]
        two["nivel_previsto_cm"] = None
        two["disponivel"] = True
        two["auditoria_inputs"] = {"status": "ATENCAO"}
        with self.assertRaises(SystemExit):
            validate_data(data, b_mat=B_MAT)

    def test_implausible_prediction_is_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["horizontes"]["2h"]["nivel_previsto_cm"] = 99999
        with self.assertRaises(SystemExit):
            validate_data(data, b_mat=B_MAT)

    def test_robot_failure_does_not_fake_a_fresh_success_timestamp(self) -> None:
        source = (ROOT / "previne" / "robo" / "gerar_previsao_ao_vivo.py").read_text(encoding="utf-8")
        start = source.index("def preservar_saida_valida_em_falha")
        end = source.index("def algum_horizonte_com_previsao", start)
        block = source[start:end]
        self.assertNotIn('atual["consultado_em"] = agora', block)
        self.assertIn('atual["ultima_tentativa_em"] = agora', block)
        self.assertIn('audit = auditoria_inputs_8h(cfg, cand, x)', source)

    def test_ana_failure_does_not_publish_expired_forecast(self) -> None:
        from previne.robo import gerar_previsao_ao_vivo as live

        now = live.dt.datetime(2026, 11, 8, 12, 0)
        expired = {
            "hora_alvo": "2026-11-08T11:00:00",
            "nivel_previsto_cm": 397,
            "disponivel": True,
            "passos": [["2026-11-08T09:00:00", 447, 429, 397]],
            "auditoria_inputs": {"status": "NORMAL"},
            "qualidade_ao_vivo": {"status": "NORMAL"},
        }
        valid = {
            **expired,
            "hora_alvo": "2026-11-08T13:00:00",
            "nivel_previsto_cm": 333,
            "passos": [["2026-11-08T09:00:00", 447, 429, 333]],
        }
        data = {
            **expired,
            "horizontes": {"2h": copy.deepcopy(expired), "4h": copy.deepcopy(valid)},
        }
        with tempfile.TemporaryDirectory() as tmp:
            saida = Path(tmp) / "previsao.json"
            with (
                patch.object(live, "carregar_saida_atual", return_value=data),
                patch.object(live, "saida_respeita_contrato_horario_atual", return_value=True),
                patch.object(live, "agora_brt", return_value=now),
                patch.object(live, "SAIDA", saida),
                patch.object(live, "MODELOS", []),
            ):
                live.preservar_saida_valida_em_falha("sem dado recente", "experimental")
            output = json.loads(saida.read_text(encoding="utf-8"))

        self.assertIsNone(output["horizontes"]["2h"]["nivel_previsto_cm"])
        self.assertFalse(output["horizontes"]["2h"]["disponivel"])
        self.assertEqual(output["horizontes"]["2h"]["previsao_stale_candidata_cm"], 397)
        self.assertEqual(output["horizontes"]["2h"]["qualidade_ao_vivo"]["status"], "BASE_DESATUALIZADA")
        self.assertEqual(output["horizontes"]["4h"]["nivel_previsto_cm"], 333)
        self.assertIsNone(output["nivel_previsto_cm"])
        self.assertFalse(output["disponivel"])
        self.assertEqual(output["ultima_tentativa_status"], "falha")

    def test_history_is_not_rewritten_when_only_stamps_change(self) -> None:
        import tempfile
        from previne.robo import gerar_previsao_ao_vivo as live
        reg = {"id": "a", "hora_alvo": "2026-10-21T10:00:00-03:00", "nivel_previsto_cm": 300,
               "status_auditoria": "sem_dado_ana", "criado_em": "2026-10-21T08:05:00-03:00",
               "auditado_em": "2026-10-21T10:30:00-03:00"}
        with tempfile.TemporaryDirectory() as d, patch.object(live, "HISTORICO_SAIDA", str(Path(d) / "h.json")):
            self.assertTrue(live.salvar_historico([dict(reg)]))
            antes = Path(live.HISTORICO_SAIDA).read_bytes()
            # novo ciclo: mesmo conteúdo, carimbos novos -> arquivo intacto
            self.assertFalse(live.salvar_historico([dict(reg, criado_em="x", auditado_em="y")]))
            self.assertEqual(Path(live.HISTORICO_SAIDA).read_bytes(), antes)
            # conferência real: grava, com o novo carimbo
            conferido = dict(reg, status_auditoria="conferido", observado_cm=310, auditado_em="z")
            self.assertTrue(live.salvar_historico([conferido]))
            salvo = json.loads(Path(live.HISTORICO_SAIDA).read_text(encoding="utf-8"))["registros"]
            self.assertEqual(salvo, [dict(conferido, criado_em=reg["criado_em"])])
            # registro novo também grava
            self.assertTrue(live.salvar_historico([conferido, dict(reg, id="b")]))

    def test_8h_is_hard_suspended_without_model_or_fallback_publication(self) -> None:
        from previne.robo import gerar_previsao_ao_vivo as live

        self.assertTrue(live.SUSPENSAO_STZ_8H_ATIVA)
        configs = {cfg["horizonte"]: cfg for cfg in live.MODELOS}
        for key in ("8h", "8h_v002"):
            self.assertFalse(configs[key]["ativo_ao_vivo"])
            self.assertFalse(live.FALLBACKS_HORIZONTE[key]["ativo_ao_vivo"])
            out = live.saida_suspensa_stz_8h(configs[key], "teste", [])
            self.assertIsNone(out["nivel_previsto_cm"])
            self.assertFalse(out["disponivel"])
            self.assertFalse(out["ativo_ao_vivo"])
            self.assertEqual(
                out["qualidade_ao_vivo"]["status"],
                "SUSPENSO_TELEMETRIA_INVALIDA",
            )
            self.assertTrue(out["suspensao_operacional"]["ativa"])
            self.assertEqual(out["auditoria_inputs"]["status"], "INVALIDO")

    def test_operational_fallbacks_are_explicit_and_drop_86298000_dependency(self) -> None:
        from previne.robo import gerar_previsao_ao_vivo as live

        self.assertNotIn("4h", live.FALLBACKS_HORIZONTE)
        eight = live.FALLBACKS_HORIZONTE["8h"]
        eight_v2 = live.FALLBACKS_HORIZONTE["8h_v002"]
        self.assertEqual(eight["inputs_total"], 10)
        self.assertEqual(eight_v2["inputs_total"], 10)
        self.assertEqual(eight["input_grade"], "hourly_exact")
        self.assertEqual(eight_v2["input_grade"], "hourly_exact")
        self.assertNotIn("86298000", " ".join(eight.get("input_labels") or []))
        self.assertNotIn("86298000", " ".join(eight_v2.get("input_labels") or []))
        self.assertTrue(eight_v2["shadow_only"])
        self.assertNotEqual(eight["modelo"], eight_v2["modelo"])

    def test_expired_primary_requests_fallback(self) -> None:
        from previne.robo import gerar_previsao_ao_vivo as live

        expired = {
            "nivel_previsto_cm": 500,
            "hora_modelo": "2026-09-21T19:00:00",
            "hora_alvo": "2026-09-21T23:00:00",
        }
        self.assertTrue(live._precisa_fallback(expired))

    def test_4h_is_v11_cascade_matching_contract_without_fallback(self) -> None:
        from previne.robo import gerar_previsao_ao_vivo as live

        cfg = next(c for c in live.MODELOS if c["horizonte"] == "4h")
        self.assertEqual(cfg["modelo"], "STZ_4H_V11_CASCATA")
        self.assertEqual(cfg["inputs_total"], 18)
        self.assertEqual(len(cfg["input_labels"]), 18)
        self.assertTrue(cfg["principal"])
        self.assertFalse(cfg.get("shadow_only", False))
        self.assertFalse(hasattr(live, "SUSPENSAO_STZ_4H_PRO_ATIVA"))
        self.assertEqual(live.sha256_arquivo(ROOT / cfg["mat"]), cfg["modelo_sha256"])

        contract = json.loads((ROOT / live.MODELO_4H_V11_CONTRATO).read_text(encoding="utf-8"))
        tipos = {"nivel": "nivel", "vel_nivel": "dif", "acel_nivel": "acel"}
        as_specs = lambda items: tuple(
            (tipos[i["tipo"]], i["estacao"], int(i["defasagem_h"])) for i in items
        )
        self.assertEqual(contract["mat"], cfg["mat"])
        self.assertEqual(contract["modelo_sha256"], cfg["modelo_sha256"])
        self.assertEqual(as_specs(contract["inputs_nivel"]), live.SPECS_NIVEL_4H_V11)
        self.assertEqual(as_specs(contract["cascata_2h"]["inputs"]), live.SPECS_NIVEL_CASCATA_2H)
        self.assertEqual(contract["cascata_2h"]["mat"], live.MODELO_MAT)
        self.assertEqual(
            [(c["nome"], c["janela_h"], tuple(c["estacoes"])) for c in contract["chuvas"]],
            list(live.CHUVAS_4H_V11),
        )

        expired = {
            "modelo": cfg["modelo"], "nivel_previsto_cm": 500,
            "hora_modelo": "2026-09-21T19:00:00", "hora_alvo": "2026-09-21T23:00:00",
        }
        self.assertIs(live.aplicar_fallback_operacional(cfg, expired, {}, [], "", []), expired)

    def test_v11_rain_hour_closes_interval_and_requires_all_quarters(self) -> None:
        from previne.robo import gerar_previsao_ao_vivo as live

        rows = [("08:15", "1"), ("08:30", "2"), ("08:45", "3"), ("09:00", "4"),
                ("09:15", "5"), ("09:30", "6")]
        xml = "<root>" + "".join(
            f"<row><DataHora>2026-10-08 {h}:00</DataHora><Chuva>{v}</Chuva></row>" for h, v in rows
        ) + "</root>"
        rain = live._chuva_horaria_fim_intervalo(xml)
        self.assertEqual(rain, {live.dt.datetime(2026, 10, 8, 9): 10.0})

    def test_v11_inputs_use_2h_forecast_at_same_base(self) -> None:
        from previne.robo import gerar_previsao_ao_vivo as live

        t = live.dt.datetime(2026, 10, 8, 22)
        hours = [t - live.dt.timedelta(hours=h) for h in range(30)]
        series = {
            "86472600": {h: 450.0 + 0.3 * i * i for i, h in enumerate(reversed(hours))},
            "86472000": {h: 300.0 + 1.5 * i for i, h in enumerate(reversed(hours))},
            "__chuva4h_v11_postos__": {
                "86472600": {h: 0.2 for h in hours},
                "86472000": {h: 0.4 for h in hours[:6]},
                "2851044": {h: 1.0 for h in hours},
            },
        }
        x, st0 = live.montar_inputs_4h_v11_cascata(series, t)
        x2 = [live._valor_nivel_exato(series, spec, t) for spec in live.SPECS_NIVEL_CASCATA_2H]
        self.assertEqual(len(x), 18)
        self.assertEqual(st0, series["86472600"][t])
        self.assertAlmostEqual(x[14], 6 * 0.3 + 6 * 0.2)
        self.assertAlmostEqual(x[15], 15.0)
        self.assertAlmostEqual(x[16], live.prever(live.MODELO_MAT, x2))
        self.assertAlmostEqual(x[17], x[0] + x[16])
        audit = live.auditoria_inputs_4h_v11_cascata(series, t, valores=x)
        self.assertEqual(audit["status"], "NORMAL")
        self.assertTrue(audit["formula_conferida_com_montador"])
        self.assertEqual(audit["n_inputs"], 18)
        self.assertEqual(audit["n_inputs_nao_exatos"], 0)
        self.assertTrue(audit["chuva_parcial"])

        del series["__chuva4h_v11_postos__"]["2851044"][t - live.dt.timedelta(hours=14)]
        x, _ = live.montar_inputs_4h_v11_cascata(series, t)
        self.assertIsNone(x[15])
        audit = live.auditoria_inputs_4h_v11_cascata(series, t, valores=x)
        self.assertEqual(audit["status"], "INVALIDO")

    def test_ana_reuses_one_xml_for_level_and_rain(self) -> None:
        from previne.robo import gerar_previsao_ao_vivo as live

        xml = b"""
        <root><row>
          <DataHora>2026-09-21T07:00:00</DataHora>
          <Nivel>350</Nivel>
          <Chuva>1.2</Chuva>
        </row></root>
        """
        calls = []

        class Response:
            def read(self):
                return xml

        def fake_urlopen(request, timeout):
            calls.append((request.full_url, timeout))
            return Response()

        live.ANA_XML_CACHE.clear()
        live.CHUVA_ANA_CACHE.clear()
        live.ULTIMA_RAW.clear()
        try:
            with patch.object(live.urllib.request, "urlopen", side_effect=fake_urlopen):
                level = live.buscar_ana("86472000", dias=5, tentativas_rede=1)
                rain = live.buscar_ana_chuva("86472000", dias=5, tentativas_rede=1)
        finally:
            live.ANA_XML_CACHE.clear()
            live.CHUVA_ANA_CACHE.clear()
            live.ULTIMA_RAW.clear()

        self.assertEqual(len(calls), 1)
        self.assertEqual(list(level.values()), [350.0])
        self.assertEqual(list(rain.values()), [1.2])


    def test_ana_gap_recovery_only_adds_official_exact_measurements(self) -> None:
        from previne.robo import gerar_previsao_ao_vivo as live

        t = live.dt.datetime
        observed = {
            t(2026, 11, 4, 12): 272.0,
            t(2026, 11, 4, 10): 319.0,
            t(2026, 11, 4, 8): 335.0,
        }
        payload = b"""<root>
        <row><DataHora>2026-11-04T11:00:00</DataHora><Nivel>295</Nivel></row>
        <row><DataHora>2026-11-04T09:30:00</DataHora><Nivel>324</Nivel></row>
        <row><DataHora>2026-11-04T12:00:00</DataHora><Nivel>999</Nivel></row>
        </root>"""
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return payload

        urls = []
        def fake_urlopen(request, timeout):
            urls.append(request.full_url)
            return Response()

        with patch.object(live, "agora_brt", return_value=t(2026, 11, 4, 12, 45)):
            with patch.object(live.urllib.request, "urlopen", side_effect=fake_urlopen):
                recovered = live._recuperar_horas_ana("86472600", dict(observed))
        self.assertEqual(recovered[t(2026, 11, 4, 11)], 295.0)
        self.assertEqual(recovered[t(2026, 11, 4, 12)], 272.0)
        self.assertNotIn(t(2026, 11, 4, 9), recovered)
        self.assertNotIn(t(2026, 11, 4, 9, 30), recovered)
        self.assertGreaterEqual(len(urls), 1)
        self.assertTrue(all("ana.gov.br" in url for url in urls))

    def test_suspended_8h_does_not_trigger_8h_ana_or_rain_downloads(self) -> None:
        from previne.robo import gerar_previsao_ao_vivo as live

        t = live.dt.datetime(2026, 11, 4, 12)
        stations = []
        def fake_fetch(codes, func, max_workers=1):
            stations.append(list(codes))
            return {
                code: {t: 272.0 if code == "86472600" else 379.0}
                for code in codes
            }

        with patch.object(live, "buscar_series_paralelo", side_effect=fake_fetch), \
             patch.object(live, "buscar_chuvas_8h", side_effect=AssertionError("8h")) as rain8, \
             patch.object(live, "buscar_chuvas_4h_v11", return_value={}), \
             patch.object(live, "carregar_historico", return_value=[]), \
             patch.object(live, "salvar_historico"), \
             patch.object(live, "conferir_historico", return_value=[]), \
             patch.object(live, "resumo_auditoria", return_value={}), \
             patch.object(live, "escrever_pacote") as published, \
             patch.object(live, "escrever_janela_inputs_ai_lab"), \
             patch.object(live, "preservar_saida_valida_em_falha") as preserve:
            live.main()
        self.assertEqual(stations, [["86472600", "86472000"]])
        rain8.assert_not_called()
        preserve.assert_not_called()
        published.assert_called_once()
        horizons = published.call_args.args[0]
        self.assertIsNone(horizons["2h"]["nivel_previsto_cm"])
        self.assertFalse(horizons["8h"]["disponivel"])


    def test_ana_observed_cache_recovers_only_existing_exact_hours(self) -> None:
        from previne.robo import gerar_previsao_ao_vivo as live

        t = live.dt.datetime(2026, 11, 4, 14)
        full = {t - live.dt.timedelta(hours=h): 350.0 + h for h in range(12)}
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "exact_levels.json")
            with patch.object(live, "agora_brt", return_value=t):
                series = {"86472600": dict(full), "86472000": {}}
                saved = live.complementar_niveis_cache_observado(series, caminho=path)
                self.assertTrue(saved["cache_escrito"])
                hole = t - live.dt.timedelta(hours=4)
                second = dict(full)
                del second[hole]
                # O cache soma apenas medições anteriormente recebidas: não
                # há interpolação nem alteração do valor observado deste ciclo.
                current = {"86472600": second, "86472000": {}}
                recovered = live.complementar_niveis_cache_observado(current, caminho=path)
                self.assertEqual(recovered["horas_resgatadas"]["86472600"], 1)
                self.assertEqual(current["86472600"][hole], full[hole])
                self.assertNotIn(t - live.dt.timedelta(hours=13), current["86472600"])
                self.assertEqual(current["86472600"][t], 350.0)

                # Sem dados reais atuais, não mascarar a perda de telemetria
                # usando o último ciclo como se fosse a leitura corrente.
                unavailable = {"86472600": {}, "86472000": {}}
                result = live.complementar_niveis_cache_observado(
                    unavailable, caminho=path
                )
                self.assertFalse(result["cache_escrito"])
                self.assertEqual(unavailable["86472600"], {})


    def test_4h_rain_response_recovers_real_station_levels(self) -> None:
        from previne.robo import gerar_previsao_ao_vivo as live

        xml = b"""<root>
        <row><DataHora>2026-11-04T14:00:00</DataHora><Nivel>272</Nivel><Chuva>0.0</Chuva></row>
        <row><DataHora>2026-11-04T15:00:00</DataHora><Nivel>270</Nivel><Chuva>0.0</Chuva></row>
        </root>"""
        original_raw = dict(live.ULTIMA_RAW)
        try:
            live.ULTIMA_RAW.clear()
            series = {"86472600": {}, "86472000": {}}
            def fake_xml(cod, *args, **kwargs):
                return xml if cod == "86472600" else None

            with patch.object(live, "_obter_xml_ana", side_effect=fake_xml):
                live.buscar_chuvas_4h_v11(series)
            ts = live.dt.datetime(2026, 11, 4, 15)
            self.assertEqual(series["86472600"][ts], 270.0)
            self.assertEqual(live.ULTIMA_RAW["86472600"], (ts, 270.0))
            self.assertEqual(series["86472000"], {})
        finally:
            live.ULTIMA_RAW.clear()
            live.ULTIMA_RAW.update(original_raw)


if __name__ == "__main__":
    unittest.main()
