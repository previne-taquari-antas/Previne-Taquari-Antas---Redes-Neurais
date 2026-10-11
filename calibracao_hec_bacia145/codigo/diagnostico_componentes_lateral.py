"""Decomposição descritiva do piloto; não ajusta parâmetros nem pontua postos interiores.

Entradas simultâneas são somadas antes da propagação. A participação da SB é na
ENTRADA, não uma atribuição da vazão na saída. Máximos de uma janela com várias
ondas não medem tempo de viagem. Nenhuma observação é lida neste diagnóstico.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta
from pathlib import Path


TRECHOS = {
    "224": ["J_217", "J_072", "SB_224"],
    "218": ["J_226", "J_078", "SB_218"],
    "211": ["J_222", "J_089", "SB_211"],
}
ORIGEM = datetime(1899, 12, 31)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def iso(t):
    return (ORIGEM + timedelta(minutes=t)).isoformat(sep=" ")


def maximo(t, q):
    if not t or len(t) != len(q) or any(not math.isfinite(v) or v < 0 for v in q):
        raise ValueError("Série inválida")
    peak = max(q)
    ix = [i for i, v in enumerate(q) if v == peak]
    return {"q_m3s": peak, "primeiro": iso(t[ix[0]]), "ultimo": iso(t[ix[-1]]),
            "n_maximos": len(ix), "maximos_desconectados": any(b != a + 1 for a, b in zip(ix, ix[1:])),
            "maximo_na_borda": 0 in ix or len(t) - 1 in ix}


def topologia(texto):
    out = {}
    for m in re.finditer(r"(?ms)^(?:Subbasin|Reach|Junction): ([^\r\n]+)\r?\n(.*?)(?=^End:)", texto):
        d = re.search(r"(?m)^\s*Downstream: ([^\r\n]+)", m[2])
        if d:
            out[m[1].strip()] = d[1].strip()
    return out


def ler_series(path):
    out = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            node, t, q = r["node"], int(r["time_value"]), float(r["flow"])
            if not math.isfinite(q) or q < 0 or t in out.setdefault(node, {}):
                raise ValueError("Valor inválido ou duplicata")
            out[node][t] = q
    return out


def componentes(series, rid, inicio, fim):
    entradas = TRECHOS[rid]
    reach, junction = "R_" + rid, "J_" + rid
    nodes = entradas + [reach, junction]
    t = sorted(k for k in series[reach] if inicio <= ORIGEM + timedelta(minutes=k) <= fim)
    if not t or any(b - a != 10 for a, b in zip(t, t[1:])):
        raise ValueError("Grade ausente ou descontínua")
    if iso(t[0]) != str(inicio) or iso(t[-1]) != str(fim):
        raise ValueError("Janela truncada")
    q = {n: [series[n][k] for k in t] for n in nodes}
    combined = [sum(v) for v in zip(*(q[n] for n in entradas))]
    delta = max(abs(a - b) for a, b in zip(q[reach], q[junction]))
    if delta > 1e-6:
        raise ValueError("Saída do reach difere da junção sem outra entrada")
    peak = max(combined)
    ix = [i for i, v in enumerate(combined) if v == peak]
    frac = [100 * q[entradas[-1]][i] / peak for i in ix] if peak > 0 else []
    return {"trecho": reach, "n": len(t), "entrada": entradas,
            "maximos": {n: maximo(t, v) for n, v in q.items()},
            "maximo_entrada_combinada": maximo(t, combined),
            "fracao_SB_no_maximo_entrada_pct": [min(frac), max(frac)] if frac else None,
            "delta_saida_juncao_m3s": delta,
            "lag_observado": None, "motivo_sem_lag": "posto interior; ondas não pareadas"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--verificacao", type=Path, required=True)
    ap.add_argument("--resultados", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    a = ap.parse_args()
    root = a.root.resolve()
    pedido = json.loads((root / "rodadas/PEDIDO.json").read_text(encoding="utf-8-sig"))
    check = json.loads(a.verificacao.read_text(encoding="utf-8"))
    assert check["status"] == "reproducao_controles_confirmada"
    assert check["pedido_sha256"] == sha(root / "rodadas/PEDIDO.json")
    os.environ["HEC_CATALOGO"] = str(root / "dados/catalogo_ampliado.json")
    # Aplicar papéis explicitamente abaixo; ignorar um override externo acidental.
    os.environ.pop("HEC_PAPEIS", None)
    from comum import EVENTOS
    for eid, papel in pedido["papeis"].items():
        assert EVENTOS[eid]["papel"] != "teste" and papel != "teste"
        EVENTOS[eid]["papel"] = papel
    basin = root / "dados/basin/a00_E27.basin"
    down = topologia(basin.read_text(encoding="utf-8"))
    for rid, entradas in TRECHOS.items():
        assert {n for n, d in down.items() if d == "R_" + rid} == set(entradas)
        assert {n for n, d in down.items() if d == "J_" + rid} == {"R_" + rid}
    rows, sources = [], []
    for c in check["comparacoes"]:
        files = list(a.resultados.rglob(f"{pedido['candidatos'][0]['id']}/{c['sim']}/vazao.csv"))
        assert len(files) == 1 and sha(files[0]) == c["manifesto"]["vazao_sha256"]
        s = ler_series(files[0])
        sources.append({"arquivo": str(files[0].resolve()), "sha256": sha(files[0])})
        for eid, ev in EVENTOS.items():
            if ev["sim"] != c["sim"] or ev["papel"] != "calibracao":
                continue
            for rid in TRECHOS:
                rows.append({"evento": eid, "sim": c["sim"], "papel": ev["papel"],
                             **componentes(s, rid, ev["ini"], ev["fim"])})
    assert {r["evento"] for r in rows} == {"E4", "E12"}, "Escopo do piloto mudou"
    out = {"status": "diagnostico_descritivo_sem_recalibracao", "dados": rows,
           "fontes": sources, "verificacao_sha256": sha(a.verificacao),
           "bacia_topologia_sha256": sha(basin), "codigo_sha256": sha(__file__),
           "limites": ["Sem métricas observado-simulado nos postos interiores",
                       "Máximos da janela não demonstram a mesma onda nem tempo de viagem",
                       "Fração lateral é anterior à propagação, não fração no pico da saída"]}
    a.saida.parent.mkdir(parents=True, exist_ok=True)
    a.saida.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    for r in rows:
        print(json.dumps({"evento": r["evento"], "trecho": r["trecho"],
                          "entrada": r["maximo_entrada_combinada"],
                          "saida": r["maximos"][r["trecho"]],
                          "SB_pct_entrada": r["fracao_SB_no_maximo_entrada_pct"]}))


if __name__ == "__main__":
    main()
