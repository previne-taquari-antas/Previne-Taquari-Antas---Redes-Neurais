#!/usr/bin/env python3
"""Sombra do candidato de Muçum: emite uma vez por hora, confere depois, nunca reescreve."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
import candidato_mucum_sombra as S  # noqa: E402
import mucum_candidato_features as F  # noqa: E402

T0 = datetime(2026, 11, 20, 0, 0)


def escrever_csvs(pasta: Path, horas: int, m=200.0, j=300.0, chuva=0.0, sem_chuva_em=None):
    flow, rain = pasta / "flow.csv", pasta / "rain.csv"
    with open(flow, "w", encoding="utf-8") as f:
        f.write("code,name,upg,time_local,flow_m3s,level\n")
        for i in range(horas):
            t = (T0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M")
            f.write(f"86510000,MUCUM,x,{t},1,{m + i}\n86472000,LJJ,x,{t},1,{j}\n")
    with open(rain, "w", encoding="utf-8") as f:
        f.write("time_local,basin_mean_mm\n")
        for i in range(horas):
            t = T0 + timedelta(hours=i)
            v = "" if sem_chuva_em is not None and t == sem_chuva_em else chuva
            f.write(f"{t.strftime('%Y-%m-%dT%H:%M')},{v}\n")
    return flow, rain


def utc_de_local(t_local: datetime) -> datetime:
    return (t_local + timedelta(hours=3)).replace(tzinfo=timezone.utc)


class SombraTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.dest = self.dir / "saida"

    def tearDown(self):
        self._tmp.cleanup()

    def rodar(self, horas_csv, agora_local, **kw):
        flow, rain = escrever_csvs(self.dir, horas_csv, **kw)
        return S.executar(utc_de_local(agora_local), self.dest, flow, rain)

    def regs(self):
        return S.carregar_registros(self.dest)

    def test_emite_uma_vez_e_confere_depois(self):
        r = self.rodar(60, T0 + timedelta(hours=60, minutes=10))
        self.assertEqual(r["hora_csv"], (T0 + timedelta(hours=59)).isoformat())
        self.assertEqual(len(r["emitidos"]), 2)
        antes = {k: v["nivel_previsto_cm"] for k, v in self.regs().items()}
        # mesma hora de novo: nada novo
        self.assertEqual(self.rodar(60, T0 + timedelta(hours=60, minutes=40))["emitidos"], [])
        # 9 h depois: alvo de 4h e 8h existem no CSV; previsões novas para a hora nova
        r = self.rodar(69, T0 + timedelta(hours=69, minutes=10))
        self.assertGreaterEqual(r["conferidos"], 2)
        regs = self.regs()
        for k, v in antes.items():
            self.assertEqual(regs[k]["nivel_previsto_cm"], v)  # nunca reescrita
            self.assertEqual(regs[k]["status_auditoria"], "conferido")
            h = regs[k]["horizonte_h"]
            self.assertEqual(regs[k]["observado_cm"], 200.0 + 59 + h)

    def test_hora_incompleta_nao_e_usada(self):
        r = self.rodar(61, T0 + timedelta(hours=60, minutes=10))  # CSV já tem a hora 60 parcial
        self.assertEqual(r["hora_csv"], (T0 + timedelta(hours=59)).isoformat())

    def test_falta_chuva_recente_nao_emite_hora_antiga_demais(self):
        falta = T0 + timedelta(hours=55)
        r = self.rodar(60, T0 + timedelta(hours=60, minutes=10), sem_chuva_em=falta)
        # a hora 55 entra na janela de 48 h (u-1 ... u-48) de todas as horas 56..59
        # (as únicas dentro de MAX_ATRASO_H); a sombra não volta mais atrás
        self.assertEqual(r["emitidos"], [])
        self.assertIsNotNone(r["motivo"])

    def test_sem_dado_quando_alvo_nunca_chega(self):
        self.rodar(60, T0 + timedelta(hours=60, minutes=10))
        self.rodar(60, T0 + timedelta(hours=60 + 8 + S.SEM_DADO_APOS_H + 2))
        self.assertTrue(all(v["status_auditoria"] == "sem_dado" for v in self.regs().values()))

    def test_contrato_de_variaveis(self):
        cfg = json.loads(S.MODELO.read_text("utf-8"))
        for mod in cfg["modelos"].values():
            self.assertEqual(mod["variaveis"], F.NOMES)
            self.assertEqual(len(mod["coeficientes"]), len(F.NOMES))
        ruim = dict(next(iter(cfg["modelos"].values())), variaveis=["x"])
        with self.assertRaises(ValueError):
            F.prever(ruim, [0.0] * len(F.NOMES))

    def test_interpolacao_so_lacunas_curtas(self):
        s = {T0: 0.0, T0 + timedelta(hours=3): 3.0, T0 + timedelta(hours=7): 7.0}
        out = F.interpolar(s)
        self.assertAlmostEqual(out[T0 + timedelta(hours=1)], 1.0)
        self.assertNotIn(T0 + timedelta(hours=5), out)

    def test_paridade_com_scikit_learn(self):
        try:
            import numpy as np
            from sklearn.linear_model import Ridge
            from sklearn.pipeline import make_pipeline
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            self.skipTest("scikit-learn ausente (a sombra não precisa dele)")
        rng = np.random.default_rng(0)
        X = rng.normal(size=(200, len(F.NOMES))) * 10
        y = X @ rng.normal(size=len(F.NOMES)) + 3
        p = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(X, y)
        esc, rid = p.named_steps["standardscaler"], p.named_steps["ridge"]
        mod = {"variaveis": F.NOMES, "media": list(esc.mean_), "escala": list(esc.scale_),
               "coeficientes": list(rid.coef_), "intercepto": float(rid.intercept_)}
        for x in X[:5]:
            self.assertAlmostEqual(F.prever(mod, list(x)), float(p.predict(x[None])[0]), places=6)


if __name__ == "__main__":
    unittest.main()
