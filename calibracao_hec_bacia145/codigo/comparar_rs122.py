"""Compara pares e convergência RS122, sem métricas contra observado ou seleção."""
import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from contrato_extracao import conferir_csv
from contrato_rs122 import conferir_metadata
from congelar_fontes_rs122 import fingerprint

RECORTES = {"S2023_07": ("E4", "2023-07-12T07:00", "2023-07-17T18:00"),
            "S2023_11": ("E12", "2023-11-13T00:00", "2023-11-25T11:00")}
RUN = "38284983152"
COMMIT = "84401448f203ae6f29ff6e3f66a9c0120e4c742d"
PILOTO_RUN = "38147587943"
PILOTO_COMMIT = "2e7e31875b824b5f55da5b8e0212afa31d9ced92"
PILOTO_HASHES = {"S2023_07": "95879f2745b1634357a58f5e64bbbe0bb45489e9e1653055cab8697962ef49f7",
                 "S2023_11": "a4a9330d8470c2c862bf7062c8b2128f0dcebe9a5dcaa95cb4cc825b7777ad2d"}
# Contrato externo à auto-declaração do artefato; datas do catálogo congelado.
JANELAS = {"S2023_07": ("2023-07-04T18:00", "2023-07-20T18:00"),
           "S2023_11": ("2023-11-10T00:00", "2023-11-28T11:00")}
CONTROLES = {"J_106", "J_211", "J_236", "J_213", "J_208", "J_201", "J_258", "J_189", "J_254", "J_220"}
NOS = {"A": CONTROLES | {"SB_211", "R_211"},
       "B0": CONTROLES | {"R_211_UP", "R_211_DOWN", "J_RS122", "SB_211"},
       "B1": CONTROLES | {"R_211_UP", "R_211_DOWN", "J_RS122", "SB_211_UP", "SB_211_DOWN"}}
NOS_PILOTO = NOS["A"] | {"J_072", "J_078", "J_089", "J_217", "J_218", "J_222", "J_224", "J_226", "R_218", "R_224", "SB_218", "SB_224"}


def dentro(value, limit):
    # Somente arredondamento de ponto flutuante, não tolerância hidrológica extra.
    return value is not None and (abs(value) <= limit or math.isclose(abs(value), limit, rel_tol=1e-12, abs_tol=1e-12))


def percentual(ref, other):
    return 100 * (other - ref) / ref if ref else (0.0 if other == 0 else None)


def stamp(iso):
    return int((datetime.fromisoformat(iso) - datetime(1899, 12, 31)).total_seconds() / 60)


def ler(path):
    out = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            n, t, q = r["node"], int(r["time_value"]), float(r["flow"])
            if not math.isfinite(q) or q < 0:
                raise ValueError("Vazão inválida")
            if t in out.setdefault(n, {}):
                raise ValueError("Duplicata de série")
            out[n][t] = q
    return out


def validar_serie(path, nodes, dt, bounds, declared):
    actual = conferir_csv(path, sorted(nodes), dt, *bounds)
    if actual != {k: declared[k] for k in actual}:
        raise ValueError("Extração declarada difere do contrato/contagem real")
    data = ler(path)
    if set(data) != set(nodes):
        raise ValueError("Conjunto de nós difere do contrato externo")
    conferir_metadata(path.parent / "series_metadata.json", sorted(nodes), dt, actual["n_por_no"])
    return data


def recortar(series, bounds):
    if bounds is None:
        return series
    if bounds[0] not in series or bounds[1] not in series:
        raise ValueError("Recorte truncado")
    return {t: q for t, q in series.items() if bounds[0] <= t <= bounds[1]}


def medidas(series):
    times = sorted(series)
    if len(times) < 2:
        raise ValueError("Série insuficiente")
    maximum = max(series.values())
    peaks = [t for t in times if series[t] == maximum]
    groups = []
    for index, t in enumerate(times):
        if series[t] == maximum:
            if index and series[times[index - 1]] == maximum:
                groups[-1].append(t)
            else:
                groups.append([t])
    volume = sum((series[a] + series[b]) * .5 * (b - a) * 60 for a, b in zip(times, times[1:]))
    return {"pico_m3s": maximum, "pico_inicio_hec_min": peaks[0], "pico_fim_hec_min": peaks[-1],
            "picos_hec_min": peaks, "grupos_maximos_hec_min": groups,
            "pico_empatado": len(peaks) > 1, "pico_na_borda": times[0] in peaks or times[-1] in peaks,
            "volume_m3": volume, "n": len(times)}


def contraste(ref, other):
    a, b = medidas(ref), medidas(other)
    return {"referencia": a, "comparada": b, "delta_pico_m3s": b["pico_m3s"] - a["pico_m3s"],
            "delta_pico_pct": percentual(a["pico_m3s"], b["pico_m3s"]),
            "delta_volume_m3": b["volume_m3"] - a["volume_m3"],
            "delta_volume_pct": percentual(a["volume_m3"], b["volume_m3"]),
            "instante_identificavel": not any(m[k] for m in (a, b) for k in ("pico_empatado", "pico_na_borda")),
            "delta_instante_min": b["pico_inicio_hec_min"] - a["pico_inicio_hec_min"]}


def triagem(c):
    magnitude = dentro(c["delta_pico_pct"], 1) and dentro(c["delta_volume_pct"], 1)
    temporal = dentro(c["delta_instante_min"], 10) if c["instante_identificavel"] else None
    result = False if magnitude is False or temporal is False else (None if temporal is None else True)
    return {"triagem_pico_volume_passou": magnitude, "triagem_temporal_passou": temporal,
            "criterio_primeiro_maximo_passou": magnitude and dentro(c["delta_instante_min"], 10),
            "triagem_passou": result,
            "motivo_temporal_indeterminado": None if temporal is not None else "maximo_empatado_ou_na_borda"}


def auditar_log(path):
    text = path.read_text(encoding="utf-8", errors="strict")
    if 'NOTE 15302:  Finished computing simulation run "Rodada"' not in text or re.search(r"(?mi)^\s*(?:ERROR|FATAL)\b", text):
        raise ValueError("Log de cálculo sem conclusão limpa")
    warnings = [line for line in text.splitlines() if line.startswith("WARNING ")]
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "avisos_por_codigo": dict(Counter(re.search(r"WARNING (\d+):", x)[1] for x in warnings)),
            "tc_elevado_ao_passo": re.findall(r'WARNING 42403:.*subbasin "([^"]+)"', text),
            "avisos": warnings,
            "routing_R211": [line for line in text.splitlines() if "R_211" in line]}


def verificar_soma(parent, upper, lower):
    if set(parent) != set(upper) or set(parent) != set(lower):
        raise ValueError("Grades dos filhos diferentes")
    summed = {t: upper[t] + lower[t] for t in parent}
    differences = {t: abs(summed[t] - q) for t, q in parent.items()}
    pass_point = all(differences[t] <= .001 + .0001 * abs(q) for t, q in parent.items())
    compare = contraste(parent, summed)
    pass_vol = dentro(compare["delta_volume_pct"], .01)
    return {"max_abs_m3s": max(differences.values()), "passou_ponto_a_ponto": pass_point,
            "passou_volume": pass_vol, "contraste": compare}


def conferir_pareamento(exec_by_key):
    if set(exec_by_key) != {sim + "/" + str(dt) for sim in JANELAS for dt in (10, 5, 1)}:
        raise ValueError("Matriz de execuções incompleta")
    ref = next(iter(exec_by_key.values()))
    keys = ("contrato_sha256", "snapshot_fontes_sha256", "parametros", "codigo_commit", "config")
    if not ref.get("codigo_commit"):
        raise ValueError("Commit cloud não identificado")
    for ex in exec_by_key.values():
        if ex.get("run_id") != RUN or ex.get("codigo_commit") != COMMIT:
            raise ValueError("Run/commit não correspondem ao lote fixado")
        if any(ex[k] != ref[k] for k in keys):
            raise ValueError("Mistura de código/contrato/fontes/parâmetros")
        base = exec_by_key[ex["janela"] + "/10"]
        if any(ex[k] != base[k] for k in ("chuva_fonte_sha256", "observados_fontes", "inicializacao_congelada", "pedido_sha256")):
            raise ValueError("Janela com fontes/estados diferentes entre passos")
        for arm in ("A", "B0", "B1"):
            a, b = ex["bracos"][arm], base["bracos"][arm]
            if a["chuva_sha256"] != b["chuva_sha256"]:
                raise ValueError("Chuva mudou entre passos")
            for k in ("inicio_hec_min", "fim_hec_min", "nos"):
                if a["extracao"][k] != b["extracao"][k]:
                    raise ValueError("Cobertura/nós mudaram entre passos")


def conferir_snapshot(sources, root):
    cfg_path = root / "experimentos/rs122/contrato.json"
    snap_path = root / "experimentos/rs122/fontes.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    snap = json.loads(snap_path.read_text(encoding="utf-8"))["entradas"]
    pedido = json.loads((root / cfg["parametros_origem"]).read_text(encoding="utf-8"))
    for ex in sources.values():
        sim = ex["janela"]
        obs = {Path(n).name: v["sha256"] for n, v in snap.items() if n.startswith("dados/observados/") and sim in n}
        if (ex["config"] != cfg or ex["parametros"] != pedido["candidatos"][0] or
            ex["contrato_sha256"] != fingerprint(cfg_path)["sha256"] or
            ex["snapshot_fontes_sha256"] != fingerprint(snap_path)["sha256"] or
            ex["pedido_sha256"] != cfg["pedido_sha256_lf"] or ex["observados_fontes"] != obs or
            ex["chuva_fonte_sha256"] != snap["dados/" + cfg["forcamento"] + "/" + sim + ".json.gz"]["sha256"]):
            raise ValueError("Execução não corresponde ao contrato/fontes congelados locais")


def resolucao_efeito(b05, b15, b01, b11, passo_grosso=5):
    """Diagnóstico conservador, não novo gate de aceitação nem ajuste de parâmetros."""
    out = {}
    ms = [medidas(s) for s in (b05, b15, b01, b11)]
    for key in ("pico_m3s", "volume_m3", "pico_inicio_hec_min"):
        a, b, c, d = [m[key] for m in ms]
        e5, e1 = b - a, d - c
        numerical = abs(c - a) + abs(d - b)
        identifiable = key != "pico_inicio_hec_min" or not any(m[k] for m in ms for k in ("pico_empatado", "pico_na_borda"))
        out[key] = {f"efeito_{passo_grosso}min": e5, "efeito_1min": e1, "mudanca_efeito": e1 - e5,
                    "soma_variacao_numerica_bracos": numerical,
                    "efeito_supera_variacao_numerica": bool(identifiable and e5 * e1 > 0 and min(abs(e5), abs(e1)) > numerical),
                    "instante_identificavel": identifiable}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artefatos", type=Path, required=True)
    ap.add_argument("--piloto-anterior", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    a = ap.parse_args()
    if a.saida.exists():
        raise ValueError("Saída já existe")
    data, sources, control, logs = {}, {}, [], []
    for sim in RECORTES:
        for dt in (10, 5, 1):
            root = a.artefatos / f"rs122-{sim}-{dt}min"
            ex = json.loads((root / "execucao.json").read_text(encoding="utf-8"))
            if ex["status"] != "executado_nao_calibrado" or ex["janela"] != sim or ex["passo_min"] != dt:
                raise ValueError("Execução não completa/coerente")
            sources[f"{sim}/{dt}"] = ex
            for arm in ("A", "B0", "B1"):
                p = root / arm / "projeto/vazao.csv"
                meta = ex["bracos"][arm]
                if hashlib.sha256(p.read_bytes()).hexdigest() != meta["vazao_sha256"]:
                    raise ValueError("Hash da vazão mudou")
                data[sim, dt, arm] = validar_serie(p, NOS[arm], dt, tuple(map(stamp, JANELAS[sim])), meta["extracao"])
                logs.append({"janela": sim, "passo_min": dt, "arm": arm, **auditar_log(p.parent / "Rodada.log")})
        prior = list(a.piloto_anterior.rglob(sim + "/vazao.csv"))
        if len(prior) != 1:
            raise ValueError("Piloto anterior ambíguo/ausente")
        prior_meta = json.loads((prior[0].parent / "extracao.json").read_text(encoding="utf-8"))
        if (prior_meta["run_id"] != PILOTO_RUN or prior_meta["codigo_commit"] != PILOTO_COMMIT or
            prior_meta["janela"] != sim or prior_meta["candidato"] != "dl-piloto-c000" or
            prior_meta["vazao_sha256"] != PILOTO_HASHES[sim] or
            hashlib.sha256(prior[0].read_bytes()).hexdigest() != PILOTO_HASHES[sim]):
            raise ValueError("Referência piloto não corresponde à identidade/hash congelados")
        old = validar_serie(prior[0], NOS_PILOTO, 10, tuple(map(stamp, JANELAS[sim])), prior_meta)
        current = data[sim, 10, "A"]
        for n in current:
            if n not in old or set(old[n]) != set(current[n]):
                raise ValueError("Referência A difere na cobertura")
            control.append({"janela": sim, "node": n, "max_abs_m3s": max(abs(q - old[n][t]) for t, q in current[n].items())})
    conferir_pareamento(sources)
    conferir_snapshot(sources, Path(__file__).resolve().parents[1])
    pairs, sums, convergence, resolution = [], [], [], []
    for sim in RECORTES:
        event, start, end = RECORTES[sim]
        scopes = {"janela_completa": None, event: (stamp(start), stamp(end))}
        for scope, bounds in scopes.items():
            def cut(series):
                return recortar(series, bounds)
            for dt in (10, 5, 1):
                A, B0, B1 = [data[sim, dt, arm] for arm in ("A", "B0", "B1")]
                sums.append({"janela": sim, "recorte": scope, "passo_min": dt,
                             **verificar_soma(cut(A["SB_211"]), cut(B1["SB_211_UP"]), cut(B1["SB_211_DOWN"]))})
                for name, left, right in (("B0-A", A, B0), ("B1-B0", B0, B1)):
                    for n in sorted(set(left) & set(right)):
                        pairs.append({"janela": sim, "recorte": scope, "passo_min": dt,
                                      "comparacao": name, "node": n, **contraste(cut(left[n]), cut(right[n]))})
            for arm in ("A", "B0", "B1"):
                for coarse in (10, 5):
                    fine = 5 if coarse == 10 else 1
                    for n in data[sim, coarse, arm]:
                        c = contraste(cut(data[sim, coarse, arm][n]), cut(data[sim, fine, arm][n]))
                        convergence.append({"janela": sim, "recorte": scope, "arm": arm, "node": n,
                                            "passos": [coarse, fine], **triagem(c), **c})
            for n in sorted(NOS["B0"] & NOS["B1"]):
                resolution.append({"janela": sim, "recorte": scope, "node": n,
                                   **resolucao_efeito(*(cut(data[sim, dt, arm][n]) for dt, arm in ((5, "B0"), (5, "B1"), (1, "B0"), (1, "B1"))))})
    gates = {"A_reproduz_exatamente": all(r["max_abs_m3s"] == 0 for r in control),
             "soma_filhos_passou": all(r["passou_ponto_a_ponto"] and r["passou_volume"] for r in sums),
             "triagem5_1_passou": all(r["triagem_passou"] is True for r in convergence if r["passos"] == [5, 1])}
    out = {"status": "comparacao_numerica_nao_calibracao" if all(gates.values()) else "diagnostico_inconclusivo_gate_falhou",
           "gates": gates, "referencia_A": control, "soma_filhos": sums,
           "pares": pairs, "convergencia": convergence, "fontes_execucoes": sources,
           "resolucao_efeito_B1_B0": resolution,
           "logs_calculo": logs,
           "piloto_referencia": {"run_id": PILOTO_RUN, "commit": PILOTO_COMMIT, "hashes": PILOTO_HASHES},
           "limites": ["Sem pontuação contra observado", "B0 não representa o posto", "B1 usa resposta e chuva herdadas",
                       "Instante compara primeiros máximos globais, não tempo de viagem da mesma onda",
                       "Empates e máximos na borda não identificam um instante de pico; triagem numérica não resolve essa ambiguidade",
                       "HEC pode elevar Tc ao passo de cálculo; comparação entre passos inclui esse piso interno, mesmo com parâmetros escritos congelados",
                       "Triagem de convergência não certifica toda a forma do hidrograma"]}
    a.saida.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"A_max_abs": max(r["max_abs_m3s"] for r in control),
                      "soma_passou": all(r["passou_ponto_a_ponto"] and r["passou_volume"] for r in sums),
                      "convergencia5_1_falhas": sum(r["triagem_passou"] is False for r in convergence if r["passos"] == [5, 1]),
                      "convergencia5_1_indeterminadas": sum(r["triagem_passou"] is None for r in convergence if r["passos"] == [5, 1])}))


if __name__ == "__main__":
    main()
