#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes sintéticos: afluente Marrecão não pode virar o Taquari.

Sem LiDAR de produção. Estes testes validam SOMENTE a lógica da máscara.
"""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

MODULE = Path(__file__).resolve().parents[1] / "codigo_python/02_mdt_hand_mancha/eixo_principal_taquari.py"
spec = importlib.util.spec_from_file_location("eixo_principal_taquari", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class EixoTaquariTest(unittest.TestCase):
    def setUp(self):
        # Taquari de oeste para leste, linha 5; tributário chega pelo norte.
        self.a = np.zeros((11, 17), dtype="float32")
        self.rec = np.arange(self.a.size, dtype="int32").reshape(self.a.shape)
        for col in range(1, 16):
            self.a[5, col] = col * 100.0
            if col < 15:
                self.rec[5, col] = 5 * 17 + col + 1
        for row in range(0, 5):
            self.a[row, 8] = 110.0 + row * 100.0
            if row < 4:
                self.rec[row, 8] = (row + 1) * 17 + 8
            else:
                self.rec[row, 8] = 5 * 17 + 8
        self.candidatos = self.a >= 100.0

    def test_exclui_tributario_e_mantem_taquari(self):
        main, diag = mod.extrair_eixo_dominante(
            self.a, self.rec, self.candidatos, (5, 7), 10.0,
            tolerancia_estacao_m=20.0, comprimento_min_m=100.0,
        )
        self.assertEqual(int(main.sum()), 15)
        self.assertTrue(np.all(main[5, 1:16]))
        self.assertFalse(np.any(main[0:5, 8]))
        self.assertGreater(diag["excluded_candidate_tributary_cells"], 0)
        self.assertEqual(diag["station_distance_to_axis_m"], 0.0)

    def test_estacao_fora_eixo_interrompe_publicacao(self):
        with self.assertRaisesRegex(ValueError, "eixo Taquari"):
            mod.extrair_eixo_dominante(
                self.a, self.rec, self.candidatos, (0, 8), 10.0,
                tolerancia_estacao_m=10.0, comprimento_min_m=100.0,
            )

    def test_limite_curto_interrompe_publicacao(self):
        with self.assertRaisesRegex(ValueError, "eixo dominante"):
            mod.extrair_eixo_dominante(
                self.a, self.rec, self.candidatos, (5, 7), 10.0,
                comprimento_min_m=1000.0,
            )

    def test_sem_candidatos_rejeita(self):
        with self.assertRaisesRegex(ValueError, "nenhum canal"):
            mod.extrair_eixo_dominante(
                self.a, self.rec, np.zeros_like(self.candidatos),
                (5, 7), 10.0,
            )


if __name__ == "__main__":
    unittest.main()
