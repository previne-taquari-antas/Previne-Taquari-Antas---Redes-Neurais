#!/usr/bin/env python3
"""Histórico sombra do AI Lab: a mesma hora recalculada sem mudança não regrava o arquivo."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
_spec = importlib.util.spec_from_file_location("ai_lab_shadow_live_infer", RAIZ / "scripts/ai_lab_shadow_live_infer.py")
INFER = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(INFER)


def registro(hora, previsto, gerado):
    return {"id": f"STZ|AI_LAB_SHADOW|2h|{hora}", "hora_modelo": hora, "hora_alvo": hora.replace("T10", "T12"),
            "temporal_previsto_cm": previsto, "static_previsto_cm": previsto, "modelo_operacional_previsto_cm": previsto,
            "observado_cm": None, "generated_at_utc": gerado}


class ShadowHistoryTests(unittest.TestCase):
    def test_same_hour_same_result_keeps_file(self):
        with tempfile.TemporaryDirectory() as d, patch.object(INFER, "HISTORY", Path(d) / "h.json"):
            INFER.update_history(registro("2026-10-21T10:00:00", 300.0, "g1"), {})
            antes = INFER.HISTORY.read_bytes()
            pacote = INFER.update_history(registro("2026-10-21T10:00:00", 300.0, "g2"), {})
            self.assertEqual(INFER.HISTORY.read_bytes(), antes)
            self.assertEqual(pacote["registros"][0]["generated_at_utc"], "g1")
            self.assertEqual(pacote["updated_at_utc"], json.loads(antes)["updated_at_utc"])
            # resultado diferente na mesma hora regrava, com o carimbo novo
            INFER.update_history(registro("2026-10-21T10:00:00", 301.0, "g3"), {})
            salvo = json.loads(INFER.HISTORY.read_text(encoding="utf-8"))["registros"]
            self.assertEqual((salvo[0]["temporal_previsto_cm"], salvo[0]["generated_at_utc"]), (301.0, "g3"))
            # hora nova acrescenta
            INFER.update_history(registro("2026-10-21T11:00:00", 302.0, "g4"), {})
            self.assertEqual(len(json.loads(INFER.HISTORY.read_text(encoding="utf-8"))["registros"]), 2)


if __name__ == "__main__":
    unittest.main()
