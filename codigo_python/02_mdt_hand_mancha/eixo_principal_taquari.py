#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extrai apenas o eixo dominante Taquari-Antas, sem tratar afluentes como referência.

O limiar FLOWACC sozinho inclui rios tributários (p.ex. Marrecão). Este
algoritmo parte da célula de maior área contribuinte na grade e sobe,
escolhendo SOMENTE o contribuinte imediato de maior FLOWACC em cada
confluência. O percurso usa o grafo D8 receptor previamente auditado.

A validação da estação é uma trava de geometria, NÃO calibra a superfície
livre, o datum vertical, a cota de remanso ou a hidrodinâmica da confluência.
"""
from __future__ import annotations

import numpy as np


def extrair_eixo_dominante(
    flowacc: np.ndarray,
    receiver: np.ndarray,
    candidato: np.ndarray,
    estacao_rc: tuple[int, int],
    resolucao_m: float,
    *,
    tolerancia_estacao_m: float = 350.0,
    comprimento_min_m: float = 1000.0,
) -> tuple[np.ndarray, dict]:
    """Retorna máscara 1-pixel de canal principal e diagnóstico fail-closed.

    receiver é índice plano do vizinho a jusante na grade ~5 m.
    candidato define um limiar mínimo de área drenada: candidatos de todos
    os tributários podem entrar, mas não são automaticamente eixo principal.
    """
    a = np.asarray(flowacc)
    rec = np.asarray(receiver)
    elig = np.asarray(candidato, dtype=bool)
    if a.ndim != 2 or rec.shape != a.shape or elig.shape != a.shape:
        raise ValueError("FLOWACC, receiver e candidato exigem mesma grade 2D")
    if not np.isfinite(resolucao_m) or resolucao_m <= 0:
        raise ValueError("resolução espacial inválida")
    if not elig.any():
        raise ValueError("nenhum canal candidato encontrado")
    rows, cols = a.shape
    sr, sc = (int(v) for v in estacao_rc)
    if sr < 0 or sc < 0 or sr >= rows or sc >= cols:
        raise ValueError("estação de referência fora do mosaico")

    score = np.where(elig & np.isfinite(a), a, -np.inf)
    outlet = int(np.argmax(score.ravel()))
    if not np.isfinite(score.ravel()[outlet]):
        raise ValueError("acumulação inválida no canal")

    eixo = np.zeros(a.size, dtype=bool)
    visitados = set()
    atual = outlet
    passos = 0
    while passos < a.size:
        if atual in visitados:
            raise ValueError("ciclo no eixo do Taquari")
        visitados.add(atual)
        eixo[atual] = True
        passos += 1
        rr, cc = divmod(atual, cols)
        possibilidades = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = rr + dr, cc + dc
                if not (0 <= nr < rows and 0 <= nc < cols):
                    continue
                idx = nr * cols + nc
                if (elig[nr, nc] and int(rec[nr, nc]) == atual
                        and idx not in visitados
                        and np.isfinite(a[nr, nc])
                        and a[nr, nc] <= a[rr, cc]):
                    possibilidades.append((float(a[nr, nc]), -idx, idx))
        if not possibilidades:
            break
        atual = max(possibilidades)[2]

    geom = eixo.reshape(a.shape)
    rr, cc = np.nonzero(geom)
    distancia_estacao = float(np.min(np.hypot((rr - sr) * resolucao_m, (cc - sc) * resolucao_m)))
    comprimento = float(max(0, passos - 1) * resolucao_m)
    if distancia_estacao > tolerancia_estacao_m:
        raise ValueError(
            f"eixo Taquari a {distancia_estacao:.1f} m da estação; "
            "verifique rio, datum e FLOWDIR antes de publicar"
        )
    if comprimento < comprimento_min_m:
        raise ValueError(
            f"eixo dominante com apenas {comprimento:.1f} m; "
            "não publicar: verificar fonte FLOWACC/FLOWDIR"
        )
    return geom, {
        "method": "dominant_D8_mainstem_not_FLOWACC_threshold_network",
        "outlet_index_row_col": list(divmod(outlet, cols)),
        "axis_cells": int(passos),
        "axis_length_m_approx": round(comprimento, 1),
        "station_distance_to_axis_m": round(distancia_estacao, 1),
        "station_tolerance_m": float(tolerancia_estacao_m),
        "min_axis_length_m": float(comprimento_min_m),
        "excluded_candidate_tributary_cells": int(np.count_nonzero(elig & ~geom)),
        "warning": "Excluir afluentes como REFERÊNCIA não equivale a remanso hidrodinâmico calibrado.",
    }
