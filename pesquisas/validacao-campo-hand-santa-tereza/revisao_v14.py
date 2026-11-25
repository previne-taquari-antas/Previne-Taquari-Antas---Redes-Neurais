#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Análises da v14 do manuscrito: o HAND avaliado lido nas posições RTK.

O T_H da planilha de campo vem do HAND krigado (INUND_HAND_2165 + 21,65 m; ver metadados_hand_krigado.json),
e não do HAND hidráulico de 5 m do site. Com o raster lido nas posições RTK (rasters_1m_nas_posicoes.csv):

  e_d (celular) = d_H(celular) − d_obs                         profundidade, como na planilha
  e_d (RTK)     = (H_r − z0 − T_H(RTK)) − d_obs                profundidade com o HAND e o LiDAR 1 m no ponto certo
  e_s           = (z_rio(RTK) + H_r − z0) − (z_RTK + d_obs)    cota da água; e_s = e_d(RTK) + δ
  δ             = z_LiDAR1m(RTK) − z_RTK                        terreno LiDAR menos terreno RTK no mesmo ponto

Também refaz o diagnóstico da premissa (cota observada × cota do rio krigada) e resume a borda nos oito
limites de set/2023 (H005 é de mai/2024 e não tem mancha própria). Lê só os CSV, sem coordenadas.

Uso:
  python pesquisas/validacao-campo-hand-santa-tereza/revisao_v14.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

AQUI = Path(__file__).resolve().parent
PICO = {"2023-09": 23.65, "2023-11": 21.61, "2024-05": 22.33}
Z0 = 1.60
AFLUENTE = ("H003", "H004", "H007")


def r(x, n=3):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def metricas(x):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    k = int((np.abs(x) <= 0.5).sum())
    n = len(x)
    z = 1.96
    centro = (k + z * z / 2) / (n + z * z)
    meia = z * np.sqrt(k * (n - k) / n + z * z / 4) / (n + z * z)
    return {"n": n, "vies_m": r(x.mean()), "mae_m": r(np.abs(x).mean()), "rmse_m": r(np.sqrt((x ** 2).mean())),
            "mediana_abs_m": r(np.median(np.abs(x))), "em_05m": k, "ic95_wilson_em_05m": [r(centro - meia), r(centro + meia)]}


def regressao(sub):
    x, y = sub.z_rio_krig_rtk.to_numpy(), sub.cota_obs.to_numpy()
    n = len(x)
    res = stats.linregress(x, y)
    t = stats.t.ppf(0.975, n - 2)
    p1 = 2 * stats.t.sf(abs((res.slope - 1) / res.stderr), n - 2)
    return {"n": n, "inclinacao": r(res.slope), "ic95": [r(res.slope - t * res.stderr), r(res.slope + t * res.stderr)],
            "p_inclinacao_1": r(p1, 4), "p_inclinacao_0": r(res.pvalue, 4)}


def main() -> None:
    e = pd.read_csv(AQUI / "erros_campo_santa_tereza.csv")
    rr = pd.read_csv(AQUI / "rasters_1m_nas_posicoes.csv")
    d = e.merge(rr[["id", "z_lidar1m_rtk_m", "dz_lidar1m_rtk_m", "hand_krig_rtk", "z_dren_krig_rtk", "hand_conv_rtk_m",
                    "z_dren_rtk_m"]], on="id", how="left")
    d = d.rename(columns={"z_dren_krig_rtk": "z_rio_krig_rtk", "dz_lidar1m_rtk_m": "delta_m"})
    d["Hr"] = d.evento.map(PICO)
    d["ed_cel"] = d.erro_lamina_m
    d["ed_rtk"] = (d.Hr - Z0 - d.hand_krig_rtk) - d.lamina_obs_m
    d["es"] = (d.z_rio_krig_rtk + d.Hr - Z0) - (d.z_rtk_m + d.lamina_obs_m)
    d["cota_obs"] = d.z_rtk_m + d.lamina_obs_m
    rtk = d[d.rtk_valido == True]  # noqa: E712
    v = rtk[rtk.tipo == "marca"]
    out = {"fonte": "erros_campo_santa_tereza.csv + rasters_1m_nas_posicoes.csv (HAND krigado INUND_HAND_2165)", "z0_m": Z0}

    out["V_rtk"] = {nome: metricas(v[c]) for nome, c in
                    (("ed_celular", "ed_cel"), ("ed_rtk", "ed_rtk"), ("es", "es"), ("delta", "delta_m"))}
    sem11 = v[v.id != "V011"]
    out["V_rtk_sem_V011"] = {nome: metricas(sem11[c]) for nome, c in (("ed_rtk", "ed_rtk"), ("es", "es"))}
    out["V_rtk_por_ponto"] = [{"id": x.id, "evento": x.evento, "ed_celular_m": r(x.ed_cel), "ed_rtk_m": r(x.ed_rtk),
                              "es_m": r(x.es), "delta_m": r(x.delta_m)} for x in v.itertuples()]
    out["posicao_reduz_erro_em"] = int((v.ed_rtk.abs() < v.ed_cel.abs()).sum())

    dl = rtk.delta_m
    out["delta_19_vertices"] = {"n": int(dl.notna().sum()), "mediana_m": r(dl.median()),
                                "nmad_m": r(1.4826 * np.median(np.abs(dl - dl.median()))),
                                "acima_1m": {x.id: r(x.delta_m) for x in rtk.itertuples() if abs(x.delta_m) > 1}}

    # ajuste de z0 nas posições RTK (viés nulo de e_d RTK nos registros de set/2023 com RTK)
    s = rtk[rtk.evento == "2023-09"]
    out["z0_rtk"] = {"V_e_H": r(Z0 + s.ed_rtk.mean()), "so_V": r(Z0 + s[s.tipo == "marca"].ed_rtk.mean()),
                     "so_H": r(Z0 + s[s.tipo == "limite"].ed_rtk.mean()),
                     "vies_ed_rtk_V_m": r(s[s.tipo == "marca"].ed_rtk.mean()),
                     "vies_ed_rtk_H_m": r(s[s.tipo == "limite"].ed_rtk.mean()),
                     "vies_ed_rtk_H_sem_afluente_m": r(s[(s.tipo == "limite") & ~s.id.isin(AFLUENTE)].ed_rtk.mean()),
                     "vies_es_V_m": r(s[s.tipo == "marca"].es.mean()), "vies_es_H_m": r(s[s.tipo == "limite"].es.mean())}

    out["diagnostico"] = {"V_e_H": regressao(s), "V_e_H_sem_V010": regressao(s[s.id != "V010"]),
                          "sem_afluente": regressao(s[~s.id.isin(AFLUENTE)]), "so_V": regressao(s[s.tipo == "marca"]),
                          "so_V_sem_V010": regressao(s[(s.tipo == "marca") & (s.id != "V010")])}
    baixo, alto = s[s.z_rio_krig_rtk < 53.3], s[s.z_rio_krig_rtk >= 53.3]
    out["diagnostico"]["grupos"] = {
        "n": [len(baixo), len(alto)],
        "diferenca_rio_m": r(alto.z_rio_krig_rtk.mean() - baixo.z_rio_krig_rtk.mean()),
        "diferenca_obs_m": r(alto.cota_obs.mean() - baixo.cota_obs.mean()),
        "p_welch_contra_premissa": r(stats.ttest_ind(baixo.cota_obs - baixo.z_rio_krig_rtk,
                                                     alto.cota_obs - alto.z_rio_krig_rtk, equal_var=False).pvalue, 4),
        "dp_obs_m": r(s.cota_obs.std()), "faixa_rio_m": [r(s.z_rio_krig_rtk.min()), r(s.z_rio_krig_rtk.max())]}

    # HAND operacional do site (5 m, trajetória D8) nas mesmas posições RTK, só como sensibilidade
    d["ed_op"] = (d.Hr - Z0 - d.hand_conv_rtk_m) - d.lamina_obs_m
    rtk = d[d.rtk_valido == True]  # noqa: E712
    s = rtk[rtk.evento == "2023-09"]
    z0_op, z0_kr = Z0 + s.ed_op.mean(), Z0 + s.ed_rtk.mean()
    vv = rtk[rtk.tipo == "marca"]
    dif_rio = (rtk.z_dren_rtk_m - rtk.z_rio_krig_rtk).abs()
    out["hand_operacional_5m_rtk"] = {
        "V_z0_160": metricas(vv.ed_op), "z0_ajustado_set2023_rtk": r(z0_op),
        "V_z0_ajustado": metricas(vv.ed_op - (z0_op - Z0)),
        "krigado_z0_ajustado_set2023_rtk": r(z0_kr), "krigado_V_z0_ajustado": metricas(vv.ed_rtk - (z0_kr - Z0)),
        "posicoes_rtk": int(len(dif_rio)), "posicoes_rio_difere_1m": int((dif_rio >= 0.95).sum()),
        "dif_rio_max_m": r(dif_rio.max())}

    h = s[s.tipo == "limite"]
    out["limites_set2023"] = {
        "n": len(h), "dist_rtk_m": {"min": r(h.erro_h_rtk_m.min(), 2), "max": r(h.erro_h_rtk_m.max(), 2),
                                    "media": r(h.erro_h_rtk_m.mean(), 2), "mediana": r(h.erro_h_rtk_m.median(), 2)},
        "dist_cel_m": {"media": r(h.erro_h_cel_m.mean(), 2), "mediana": r(h.erro_h_cel_m.median(), 2)},
        "spearman_dist_rtk_abs_es": r(stats.spearmanr(h.erro_h_rtk_m, h.es.abs()).correlation, 2),
        "spearman_dist_rtk_abs_ed_rtk": r(stats.spearmanr(h.erro_h_rtk_m, h.ed_rtk.abs()).correlation, 2),
        "dentro_da_mancha_rtk": sorted(h[h.ed_rtk > 0].id), "fora_da_mancha_rtk": sorted(h[h.ed_rtk <= 0].id),
        "dentro_da_mancha_cel": sorted(h[h.ed_cel > 0].id),
        "declividade_pct_mediana_lidar10": r(np.median([x["declividade_pct"] for x in json.loads(
            (AQUI / "analises_adicionais.json").read_text())["erro_horizontal_limites"]["por_ponto"]
            if x["id"] in set(h.id)]), 1),
        "spearman_dist_cel_abs_ed_cel": r(stats.spearmanr(h.erro_h_cel_m, h.ed_cel.abs()).correlation, 2),
        "vies_es_m": r(h.es.mean()), "vies_ed_rtk_m": r(h.ed_rtk.mean()), "vies_ed_cel_m": r(h.ed_cel.mean()),
        "por_ponto": [{"id": x.id, "dist_rtk_m": r(x.erro_h_rtk_m, 2), "dist_cel_m": r(x.erro_h_cel_m, 2),
                       "es_m": r(x.es), "ed_rtk_m": r(x.ed_rtk), "ed_cel_m": r(x.ed_cel)} for x in h.itertuples()]}
    borda = AQUI / "distancias_borda_krigada.csv"
    if borda.exists():
        b = pd.read_csv(borda)
        out["limites_set2023"]["mancha_krigada_z160"] = b.to_dict(orient="records")

    (AQUI / "revisao_v14.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("V_rtk", "V_rtk_sem_V011", "delta_19_vertices", "z0_rtk", "posicao_reduz_erro_em")},
                     ensure_ascii=False, indent=1))
    print(json.dumps(out["diagnostico"], ensure_ascii=False))
    print(json.dumps(out["hand_operacional_5m_rtk"], ensure_ascii=False))
    print(json.dumps({k: v for k, v in out["limites_set2023"].items() if k != "por_ponto"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
