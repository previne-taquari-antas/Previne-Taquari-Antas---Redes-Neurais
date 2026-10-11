"""Contrato de extração diagnóstica; não altera hidrologia nem escolhe parâmetros."""
import csv
import json
import math
import re
from pathlib import Path


def validar_nos(nos, texto_bacia):
    if not isinstance(nos, list) or any(not isinstance(n, str) for n in nos):
        raise ValueError("nos_extra deve ser uma lista de nomes de elementos")
    existentes = set(re.findall(r"^(?:Junction|Reach|Subbasin|Source|Sink|Reservoir|Diversion):\s*(\S+)\s*$", texto_bacia, re.M))
    invalidos = set(nos) - existentes
    if invalidos:
        raise ValueError(f"Elementos ausentes na bacia: {sorted(invalidos)}")
    return sorted(set(nos))


def conferir_csv(path, requeridos, passo_min=10, inicio_esperado=None, fim_esperado=None):
    """Recusa cache incompleto, lacunas, duplicatas e sentinelas DSS; nunca preenche."""
    series = {n: {} for n in requeridos}
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ["node", "time_value", "flow"]:
            raise ValueError("Cabeçalho de vazao.csv incompatível")
        for row in reader:
            node = row["node"]
            if node not in series:
                continue
            t, q = int(row["time_value"]), float(row["flow"])
            if not math.isfinite(q) or q < 0:
                raise ValueError(f"Vazão ausente/inválida: {node}/{t}")
            if t in series[node]:
                raise ValueError(f"Carimbo duplicado: {node}/{t}")
            series[node][t] = q
    reference = None
    for node, values in series.items():
        times = sorted(values)
        if len(times) < 2:
            raise ValueError(f"Nó sem série completa: {node}")
        if any(b - a != passo_min for a, b in zip(times, times[1:])):
            raise ValueError(f"Lacuna/passo irregular: {node}")
        if reference is not None and times != reference:
            raise ValueError(f"Nós com coberturas temporais diferentes: {node}")
        if inicio_esperado is not None and times[0] != inicio_esperado:
            raise ValueError(f"Início truncado/inesperado: {node}")
        if fim_esperado is not None and times[-1] != fim_esperado:
            raise ValueError(f"Fim truncado/inesperado: {node}")
        reference = times
    return {"nos": sorted(series), "n_por_no": len(reference or []),
            "inicio_hec_min": reference[0] if reference else None,
            "fim_hec_min": reference[-1] if reference else None, "passo_min": passo_min}


def ler_nos(path, texto_bacia):
    return validar_nos(json.loads(Path(path).read_text(encoding="utf-8")), texto_bacia) if path else []


def exigir_destinos_novos(paths):
    existentes = [str(p) for p in paths if Path(p).exists()]
    if existentes:
        raise ValueError("Diagnóstico exige pastas novas; nada foi removido: " + ", ".join(existentes))
