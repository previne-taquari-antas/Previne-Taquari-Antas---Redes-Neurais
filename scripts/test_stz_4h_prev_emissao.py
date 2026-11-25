#!/usr/bin/env python3
"""A ultima previsao 4h so pode ser reaproveitada se realmente foi emitida antes."""
import datetime as dt
import unittest
from unittest.mock import patch
from previne.robo import gerar_previsao_ao_vivo as R


class EmissaoAnterior4hTest(unittest.TestCase):
    def setUp(self):
        self.cfg = next(x for x in R.MODELOS if x["horizonte"] == "4h")
        self.t0 = dt.datetime(2026, 11, 16, 20)
        self.emitida = self.t0 + dt.timedelta(hours=1)
        self.now = self.t0 + dt.timedelta(hours=2, minutes=5)
        self.previa = {
            "horizonte": "4h", "modelo": self.cfg["modelo"],
            "modelo_sha256": self.cfg["modelo_sha256"],
            "formula_contract_version": self.cfg["formula_contract_version"],
            "input_contract_version": "hourly_exact_v1",
            "input_grade": "hourly_exact",
            "hora_modelo": self.t0.isoformat(),
            "hora_alvo": (self.t0 + dt.timedelta(hours=4)).isoformat(),
            "consultado_em": self.emitida.isoformat(),
            "nivel_previsto_cm": 261,
            "disponivel": True,
            "input_values_cm": list(range(18)),
            "auditoria_inputs": {"status": "NORMAL"},
            "qualidade_ao_vivo": {"status": "NORMAL"},
        }
        self.sem_base = {"nivel_previsto_cm": None, "status": "sem hora valida",
                         "proxima_base_diagnostico": {"pronta": False}}

    def run_recovery(self, previa=None, now=None):
        feed = {"horizontes": {"4h": previa if previa is not None else self.previa}}
        with patch.object(R, "carregar_saida_atual", return_value=feed), \
             patch.object(R, "agora_brt", return_value=now or self.now):
            return R.recuperar_ultima_4h_emitida(self.cfg, self.sem_base)

    def test_reusa_apenas_emissao_original_ainda_futura(self):
        out = self.run_recovery()
        self.assertTrue(out["ultima_previsao_reaproveitada"])
        self.assertEqual(out["nivel_previsto_cm"], 261)
        self.assertEqual(out["emissao_original_em"], self.emitida.isoformat())
        self.assertEqual(out["base_nova_status"], "sem hora valida")
        self.assertNotIn("ultima_previsao_reaproveitada", self.previa)

    def test_rejeita_entrada_nao_auditada(self):
        p = dict(self.previa, auditoria_inputs={"status": "INVALIDO"})
        self.assertIs(self.run_recovery(p), self.sem_base)

    def test_rejeita_previsao_ja_vencida(self):
        self.assertIs(self.run_recovery(now=self.t0 + dt.timedelta(hours=4, minutes=1)),
                      self.sem_base)

    def test_rejeita_emissao_retroativa(self):
        p = dict(self.previa, consultado_em=(self.t0 + dt.timedelta(hours=2, minutes=10)).isoformat())
        self.assertIs(self.run_recovery(p), self.sem_base)


class AlvoFuturoObrigatorioTest(unittest.TestCase):
    def test_previsao_2h_vencida_e_retirada(self):
        out = {
            "hora_alvo": "2026-11-16T22:00:00",
            "nivel_previsto_cm": 198,
            "disponivel": True,
            "passos": [["2026-11-16T20:00:00", 161, 198]],
            "auditoria_inputs": {"status": "NORMAL"},
        }
        R.bloquear_previsao_com_alvo_vencido(
            out, dt.datetime(2026, 11, 16, 22, 15))
        self.assertIsNone(out["nivel_previsto_cm"])
        self.assertFalse(out["disponivel"])
        self.assertEqual(out["bloqueio_publicacao"], "hora_alvo_vencida")
        self.assertEqual(out["auditoria_inputs"]["status"], "ATENCAO")

    def test_previsao_4h_com_alvo_futuro_permanece(self):
        out = {
            "hora_alvo": "2026-11-17T00:00:00",
            "nivel_previsto_cm": 261,
            "disponivel": True,
            "passos": [["2026-11-16T20:00:00", 161, 261]],
        }
        R.bloquear_previsao_com_alvo_vencido(
            out, dt.datetime(2026, 11, 16, 22, 15))
        self.assertEqual(out["nivel_previsto_cm"], 261)
        self.assertTrue(out["disponivel"])


if __name__ == "__main__":
    unittest.main()
