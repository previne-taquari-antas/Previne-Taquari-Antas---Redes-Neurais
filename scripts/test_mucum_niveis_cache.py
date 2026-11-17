#!/usr/bin/env python3
"""Regressoes do cache de observacoes ANA: somente leituras reais e horas exatas."""
from __future__ import annotations
import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "codigo_python/01_previsao_ao_vivo/gerar_previsao_ao_vivo_mucum.py"
SPEC = importlib.util.spec_from_file_location("mucum_live_cache_test", PATH)
LIVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LIVE)


class MucumCacheObservadoTest(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 16, 22)
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "cache.json"
        self.path.write_text(json.dumps({"schema_version":1,"estacoes":{}}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def rodar(self, series):
        with patch.object(LIVE, "agora_brt", return_value=self.now), patch.dict(LIVE.ULTIMA_RAW, {}, clear=True):
            diag = LIVE.complementar_niveis_cache_observado(series, str(self.path))
        return diag

    def test_mantem_timestamps_exatos_sem_criar_horas_faltantes(self):
        antiga = self.now - dt.timedelta(hours=2)
        atual = self.now - dt.timedelta(minutes=15)
        inicial = {"schema_version":1,"estacoes":{
            "86510000": [[antiga.isoformat(), 180.0]],
        }}
        self.path.write_text(json.dumps(inicial), encoding="utf-8")
        series = {"86510000": {atual: 190.0}}
        diag = self.rodar(series)
        self.assertEqual(series["86510000"], {antiga:180.0, atual:190.0})
        self.assertNotIn(self.now - dt.timedelta(hours=1), series["86510000"])
        self.assertEqual(diag["86510000"]["recuperadas_do_cache"], 1)
        self.assertEqual(json.loads(self.path.read_text())["schema_version"], 1)

    def test_descarta_leitura_futura_invalida_sem_fabricar_zero(self):
        antiga = self.now - dt.timedelta(hours=3)
        futuro = self.now + dt.timedelta(hours=1)
        self.path.write_text(json.dumps({"schema_version":1,"estacoes":{
            "86510000": [[antiga.isoformat(), 200.0], [futuro.isoformat(), 205.0]]
        }}), encoding="utf-8")
        series = {"86510000": {self.now: 9000.0}}
        self.rodar(series)
        self.assertEqual(series["86510000"], {antiga:200.0})
        self.assertNotIn(futuro, series["86510000"])
        self.assertNotIn(self.now, series["86510000"])


if __name__ == "__main__":
    unittest.main()
