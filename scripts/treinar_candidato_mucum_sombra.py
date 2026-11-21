#!/usr/bin/env python3
"""Congela o candidato linear de Muçum (4h e 8h) para a operação em sombra.

Treina Ridge (padronização + RidgeCV) sobre a variação do nível com as
variáveis de ``mucum_candidato_features`` (Muçum + Linha José Júlio + chuva
média da bacia), usando as cheias históricas do G040 e a série contínua de
2026 disponível até agora. Grava ``config/mucum_candidato_ridge_v1.json``.

Antes de congelar, repete a validação em blocos de 7 dias (purga 48 h + h)
com as MESMAS funções de variáveis da sombra e publica o resultado no JSON,
para conferir que bate com ``experimento_mucum_candidato_regimes.py``.

A avaliação prospectiva honesta usa só horas depois de ``congelado_ate``.
Pesquisa; não é alerta oficial. Requer pandas e scikit-learn (só aqui; a
sombra usa biblioteca padrão).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import experimento_mucum_candidato_regimes as EXP  # noqa: E402
import mucum_candidato_features as F  # noqa: E402

OUT = ROOT / "config/mucum_candidato_ridge_v1.json"
HORIZONTES = (4, 8)
ALPHAS = np.logspace(-2, 3, 12)


def series_de(df, col):
    return {t.to_pydatetime(): float(v) for t, v in df[col].items() if v == v}


def linhas(df, h):
    """(tempo, x, alvo) para cada hora do bloco com variáveis e alvo."""
    m_raw = series_de(df, EXP.M)
    m, j = F.interpolar(m_raw), F.interpolar(series_de(df, EXP.J))
    chuva = series_de(df, "rain") if "rain" in df else {}
    out = []
    for u in sorted(m_raw):
        alvo = m_raw.get(u + h * F.H)
        if alvo is None:
            continue
        x = F.vetor(m, j, chuva, u)
        if x is not None:
            out.append((u, x, alvo - m[u]))
    return out


def ajustar(X, y):
    modelo = make_pipeline(StandardScaler(), RidgeCV(alphas=ALPHAS))
    modelo.fit(np.asarray(X), np.asarray(y))
    return modelo


def validar_blocos(hist, cont, h):
    """MAE (cm) em blocos de 7 dias de 2026, com purga."""
    if not cont:
        return None
    t0 = min(t for t, _, _ in cont).replace(hour=0)
    t1 = max(t for t, _, _ in cont)
    margem = timedelta(hours=EXP.PURGE_H + h)
    erros, pers = [], []
    a = t0
    while a <= t1:
        b = a + timedelta(days=EXP.BLOCK_DAYS)
        teste = [r for r in cont if a <= r[0] < b]
        treino = hist + [r for r in cont if r[0] < a - margem or r[0] >= b + margem]
        if teste and len(treino) >= 200:
            mod = ajustar([r[1] for r in treino], [r[2] for r in treino])
            p = mod.predict(np.asarray([r[1] for r in teste]))
            erros += [abs(pi - r[2]) for pi, r in zip(p, teste)]
            pers += [abs(r[2]) for r in teste]
        a = b
    return {"n": len(erros), "mae_cm": round(float(np.mean(erros)), 1),
            "mae_persistencia_cm": round(float(np.mean(pers)), 1)}


def main() -> int:
    eventos = EXP.historical_events()
    cont_df = EXP.continuous_2026()
    modelos = {}
    for h in HORIZONTES:
        hist = [r for df in eventos.values() if "rain" in df for r in linhas(df, h)]
        cont = linhas(cont_df, h)
        todos = hist + cont
        mod = ajustar([r[1] for r in todos], [r[2] for r in todos])
        esc, ridge = mod.named_steps["standardscaler"], mod.named_steps["ridgecv"]
        modelos[f"{h}h"] = {
            "horizonte_h": h,
            "variaveis": F.NOMES,
            "media": [round(float(v), 8) for v in esc.mean_],
            "escala": [round(float(v), 8) for v in esc.scale_],
            "coeficientes": [round(float(v), 8) for v in ridge.coef_],
            "intercepto": round(float(ridge.intercept_), 8),
            "alpha": float(ridge.alpha_),
            "n_treino": len(todos),
            "n_treino_cheias_historicas": len(hist),
            "validacao_blocos_2026": validar_blocos(hist, cont, h),
        }
        print(h, "h", modelos[f"{h}h"]["validacao_blocos_2026"], "alpha", ridge.alpha_)
    congelado = max(cont_df.dropna(subset=[EXP.M]).index).to_pydatetime()
    corpo = {
        "schema_version": "mucum_candidato_ridge_v1",
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "congelado_ate": congelado.isoformat(timespec="minutes"),
        "aviso": "Pesquisa em sombra. Não é alerta oficial nem substitui a RNA publicada.",
        "rotulo_tempo": "rótulo horário do CSV de pesquisa (início da hora de média)",
        "estacoes": {"M": EXP.M, "J": EXP.J},
        "chuva": "basin_mean_mm de mucum_observed_multistation_rain_hourly.csv (IDW²), atrasada 1 h; cheias históricas: média ponderada das zonas do G040",
        "origem": "docs/mucum_candidato_regimes_20261119.md",
        "modelos": modelos,
    }
    corpo["sha256_modelos"] = hashlib.sha256(json.dumps(modelos, sort_keys=True).encode()).hexdigest()
    OUT.write_text(json.dumps(corpo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("gravado", OUT.relative_to(ROOT), "congelado_ate", corpo["congelado_ate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
