#!/usr/bin/env python3
"""Arquivo permanente do historico ao vivo: nunca apaga, atualiza conferencias e e idempotente."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
import arquivar_historico_ao_vivo as A  # noqa: E402


def reg(hora, status="aguardando", obs=None, modelo="M1"):
    return {"id": f"Muçum|2h|{modelo}|{hora}", "horizonte": "2h", "modelo": modelo,
            "hora_modelo": hora, "nivel_previsto_cm": 300, "status_auditoria": status,
            "observado_cm": obs}


class ArquivoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def ler(self, mes):
        return {r["id"]: r for r in json.loads((self.dest / "mucum" / f"{mes}.json").read_text("utf-8"))["registros"]}

    def test_registro_que_sai_do_rolante_permanece(self):
        A.arquivar("mucum", [reg("2026-10-31T23:00:00"), reg("2026-11-01T00:00:00")], self.dest)
        A.arquivar("mucum", [reg("2026-11-01T01:00:00")], self.dest)
        self.assertEqual(len(self.ler("2026-10")), 1)
        self.assertEqual(len(self.ler("2026-11")), 2)

    def test_conferencia_mais_nova_substitui(self):
        A.arquivar("mucum", [reg("2026-11-01T00:00:00")], self.dest)
        A.arquivar("mucum", [reg("2026-11-01T00:00:00", "conferido", 310)], self.dest)
        r = self.ler("2026-11")["Muçum|2h|M1|2026-11-01T00:00:00"]
        self.assertEqual((r["status_auditoria"], r["observado_cm"]), ("conferido", 310))

    def test_so_acrescentar_nao_sobrescreve(self):
        A.arquivar("mucum", [reg("2026-11-01T00:00:00", "conferido", 310)], self.dest)
        A.arquivar("mucum", [reg("2026-11-01T00:00:00")], self.dest, substituir=False)
        self.assertEqual(self.ler("2026-11")["Muçum|2h|M1|2026-11-01T00:00:00"]["observado_cm"], 310)

    def test_idempotente_e_indice(self):
        regs = [reg("2026-11-01T00:00:00", "conferido", 1), reg("2026-11-01T01:00:00")]
        A.arquivar("mucum", regs, self.dest)
        antes = (self.dest / "mucum" / "2026-11.json").read_bytes()
        resumo = A.arquivar("mucum", regs, self.dest)
        self.assertEqual(resumo["meses_alterados"], [])
        self.assertEqual((self.dest / "mucum" / "2026-11.json").read_bytes(), antes)
        indice = json.loads((self.dest / "mucum" / "indice.json").read_text("utf-8"))
        self.assertEqual(indice["meses"]["2026-11"]["total"], 2)
        self.assertEqual(indice["meses"]["2026-11"]["conferidos"], 1)

    def test_historico_invalido_preserva_arquivo(self):
        A.arquivar("mucum", [reg("2026-11-01T00:00:00")], self.dest)
        ruim = self.dest / "ruim.json"
        ruim.write_text("{", encoding="utf-8")
        codigo = A.main(["--local", "mucum", "--entrada", str(ruim), "--destino", str(self.dest)])
        self.assertEqual(codigo, 1)
        self.assertEqual(len(self.ler("2026-11")), 1)

    def test_arquivo_publicado_e_json_valido(self):
        pasta = RAIZ / "assets" / "data" / "historico_ao_vivo_arquivo"
        for arq in pasta.glob("*/????-??.json"):
            dados = json.loads(arq.read_text("utf-8"))
            self.assertEqual(dados["total"], len(dados["registros"]), arq)
            self.assertEqual(len({r["id"] for r in dados["registros"]}), dados["total"], arq)


if __name__ == "__main__":
    unittest.main()
