"""Extensão 2→1 previamente registrada; conserva o diagnóstico original 5→1."""
import argparse
import hashlib
import json
from pathlib import Path

from comparar_rs122 import (NOS, JANELAS, RECORTES, stamp, validar_serie, conferir_snapshot,
                            recortar, contraste, triagem, verificar_soma, auditar_log, resolucao_efeito)
from contrato_rs122 import conferir_extensao
from congelar_fontes_rs122 import fingerprint


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artefatos-2min", type=Path, required=True)
    ap.add_argument("--artefatos-1min", type=Path, required=True)
    ap.add_argument("--run-novo", required=True)
    ap.add_argument("--commit-novo", required=True)
    ap.add_argument("--saida", type=Path, required=True)
    a = ap.parse_args()
    if a.saida.exists():
        raise ValueError("Saída já existe")
    root = Path(__file__).resolve().parents[1]
    cfg = json.loads((root / "experimentos/rs122/contrato.json").read_text(encoding="utf-8"))
    ext = conferir_extensao(root, cfg, 2)
    ext_hash = fingerprint(root / "experimentos/rs122/extensao_2min.json")["sha256"]
    sources, data, logs = {}, {}, []
    for sim in JANELAS:
        for dt, folder, run, commit in ((2, a.artefatos_2min, a.run_novo, a.commit_novo),
                                      (1, a.artefatos_1min, ext["referencia"]["run_id"], ext["referencia"]["codigo_commit"])):
            where = folder / f"rs122-{sim}-{dt}min"
            ex = json.loads((where / "execucao.json").read_text(encoding="utf-8"))
            if (ex["status"] != "executado_nao_calibrado" or ex["janela"] != sim or ex["passo_min"] != dt or
                ex["run_id"] != run or ex["codigo_commit"] != commit or set(ex["bracos"]) != set(NOS)):
                raise ValueError("Identidade ou execução completa incompatível")
            if dt == 2 and (ex.get("extensao") != ext or ex.get("extensao_sha256") != ext_hash or ex["min_tc_escrito_min"] <= 2):
                raise ValueError("Extensão não corresponde ao registro")
            sources[sim + "/" + str(dt)] = ex
            for arm in NOS:
                p = where / arm / "projeto/vazao.csv"
                meta = ex["bracos"][arm]
                expected = meta["vazao_sha256"] if dt == 2 else ext["referencia"]["vazao_sha256"][sim][arm]
                if meta["vazao_sha256"] != expected or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
                    raise ValueError("Hash vazão não corresponde ao lote fixado")
                data[sim, dt, arm] = validar_serie(p, NOS[arm], dt, tuple(map(stamp, JANELAS[sim])), meta["extracao"])
                log = auditar_log(p.parent / "Rodada.log")
                if log["tc_elevado_ao_passo"]:
                    raise ValueError("HEC alterou Tc nesta comparação")
                logs.append({"janela": sim, "passo_min": dt, "arm": arm, **log})
        ex2, ex1 = sources[sim + "/2"], sources[sim + "/1"]
        for key in ("config", "parametros", "contrato_sha256", "snapshot_fontes_sha256", "pedido_sha256",
                    "chuva_fonte_sha256", "observados_fontes", "inicializacao_congelada"):
            if ex2[key] != ex1[key]:
                raise ValueError("Pareamento 2→1 mudou " + key)
        for arm in NOS:
            if ex2["bracos"][arm]["chuva_sha256"] != ex1["bracos"][arm]["chuva_sha256"]:
                raise ValueError("Chuva não idêntica entre passos")
    conferir_snapshot(sources, root)
    convergence, sums, pairs, resolution = [], [], [], []
    for sim, (event, start, end) in RECORTES.items():
        for scope, bounds in (("janela_completa", None), (event, (stamp(start), stamp(end)))):
            def cut(s):
                return recortar(s, bounds)
            for dt in (2, 1):
                A, B0, B1 = [data[sim, dt, arm] for arm in NOS]
                sums.append({"janela": sim, "recorte": scope, "passo_min": dt,
                             **verificar_soma(cut(A["SB_211"]), cut(B1["SB_211_UP"]), cut(B1["SB_211_DOWN"]))})
                for name, left, right in (("B0-A", A, B0), ("B1-B0", B0, B1)):
                    for n in sorted(set(left) & set(right)):
                        pairs.append({"janela": sim, "recorte": scope, "passo_min": dt,
                                      "comparacao": name, "node": n, **contraste(cut(left[n]), cut(right[n]))})
            for arm in NOS:
                for node in sorted(NOS[arm]):
                    c = contraste(cut(data[sim, 2, arm][node]), cut(data[sim, 1, arm][node]))
                    convergence.append({"janela": sim, "recorte": scope, "arm": arm, "node": node,
                                        "passos": [2, 1], **triagem(c), **c})
            for node in sorted(NOS["B0"] & NOS["B1"]):
                resolution.append({"janela": sim, "recorte": scope, "node": node,
                                   **resolucao_efeito(*(cut(data[sim, dt, arm][node]) for dt, arm in ((2,"B0"),(2,"B1"),(1,"B0"),(1,"B1"))), passo_grosso=2)})
    gates = {"soma_filhos_passou": all(r["passou_ponto_a_ponto"] and r["passou_volume"] for r in sums),
             "triagem2_1_passou": all(r["triagem_passou"] is True for r in convergence)}
    out = {"status": "extensao_numerica_nao_calibracao" if all(gates.values()) else "extensao_inconclusiva_gate_falhou",
           "contrato_extensao": ext, "gates": gates, "soma_filhos": sums, "convergencia": convergence,
           "pares": pairs, "resolucao_efeito_B1_B0": resolution, "logs_calculo": logs, "fontes_execucoes": sources,
           "limites": ext["limites"] + ["Variação 2→1 não certifica a forma completa ou erro numérico total", "Primeiro máximo global não é tempo de viagem de uma onda"]}
    a.saida.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"gates": gates, "falhas": sum(r["triagem_passou"] is False for r in convergence),
                      "indeterminadas": sum(r["triagem_passou"] is None for r in convergence)}))


if __name__ == "__main__":
    main()
