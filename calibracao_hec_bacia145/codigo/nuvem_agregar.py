"""Junta os vazao.csv de uma rodada (um ou vários shards) e calcula as métricas e o J de cada candidato.

Mesma conta de buscar_v3.avaliar (bi.avaliar_sim + bi.J_evento). Eventos de TESTE só entram com --teste.
J_t = J_pico + penalidade de atraso e recessão nas cheias médias e grandes (tempo.py); "tempo" guarda as medidas.
Uso:
  python nuvem_agregar.py --candidatos cands.json --dir pasta_com_os_shards --saida resultado.json [--janelas cal] [--teste]
Procura recursivamente <dir>/**/<id>/<janela>/vazao.csv.
"""
import argparse
import csv
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import bacia_inteira as bi
import buscar_v3 as bs
import metricas
import tempo
from comum import EVENTOS, SIMULACOES

CAMPOS = ("evento", "papel", "controle", "nse", "vol", "erro_pico", "lag_h", "pen", "passa", "pico_obs")


def ler(p):
    out = {}
    for r in csv.DictReader(open(p, encoding="utf-8")):
        t = datetime(1899, 12, 31) + timedelta(minutes=int(r["time_value"]))
        out.setdefault(r["node"], {})[t] = float(r["flow"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidatos", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--saida", required=True)
    ap.add_argument("--janelas", default="cal")
    ap.add_argument("--teste", action="store_true")
    a = ap.parse_args()
    cands = json.loads(Path(a.candidatos).read_text(encoding="utf-8"))
    sims = bs.SIMS_CAL if a.janelas == "cal" else (list(SIMULACOES) if a.janelas == "todas" else a.janelas.split(","))
    achados = {}
    for f in Path(a.dir).rglob("vazao.csv"):
        achados[(f.parent.parent.name, f.parent.name)] = f
    cal = sorted(e for e, v in EVENTOS.items() if v["papel"] == "calibracao")
    out = []
    pesos = None
    for c in cands:
        mets, tmp, faltam = [], [], []
        for s in sims:
            f = achados.get((c["id"], s))
            if f is None:
                faltam.append(s)
                continue
            serie = ler(f)
            mets += bi.avaliar_sim(s, serie)
            tmp += tempo.medir_sim(s, serie)
        if not a.teste:
            mets = [m for m in mets if m["papel"] != "teste"]
            tmp = [m for m in tmp if m["papel"] != "teste"]
        J_ev = {e: bi.J_evento(mets, e) for e in cal}
        fin = [v for v in J_ev.values() if math.isfinite(v)]
        J = sum(fin) / len(fin) if fin and not faltam else float("inf")
        if pesos is None and not faltam:
            pesos = metricas.pesos_por_pico(mets, set(cal))
        J_pico = metricas.J_ponderado(J_ev, pesos) if pesos and not faltam else float("inf")
        J_t, T = tempo.J_t(J_pico, tmp, mets) if not faltam else (float("inf"), None)
        out.append({"id": c["id"], "rota": c.get("rota", "mc"), "p": c["p"], "J": J, "J_pico": J_pico, "J_t": J_t, "T": T,
                    "faltam": faltam,
                    "J_ev": {k: (v if math.isfinite(v) else None) for k, v in J_ev.items()},
                    "metricas": [{k: m[k] for k in CAMPOS} for m in mets],
                    "tempo": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()} for m in tmp]})
    Path(a.saida).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    ok = [r for r in out if math.isfinite(r["J"])]
    print(f"{len(out)} candidatos; {len(ok)} completos; melhor J = {min((r['J'] for r in ok), default=float('nan')):.3f}")
    incompletos = [r["id"] for r in out if r["faltam"]]
    if incompletos:
        print("INCOMPLETOS (faltam janelas):", incompletos[:10])


if __name__ == "__main__":
    main()
