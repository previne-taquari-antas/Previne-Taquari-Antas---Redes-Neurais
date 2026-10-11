#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Análises pedidas pelos dois pareceres da v5 (SBSR 2027), para a versão v6.

Lê só arquivos sem coordenadas (erros_campo_santa_tereza.csv, analises_adicionais.json e o
diagnóstico do gerador do HAND) e grava revisao_v6.json:

- e_s (terreno RTK) como métrica principal das marcas V com RTK; e_d como secundária;
- fração de erros em ±0,5 m com IC de Wilson e RMSE, no lugar de kappa, NSE e KGE;
- erros individuais dos outros eventos (n = 4), sem IC t;
- sensibilidade do viés dos outros eventos a z0 calibrado com V, com H, com V+H e com e_s;
- diagnóstico da premissa do HAND com V+H (n = 15), só V (n = 7) e sem V010;
- distância dos limites H à borda com sinal (sinal de e_s: dentro/fora da mancha modelada);
- decomposição de Δz em posição do celular e terreno, com o LiDAR de 10 m nas posições RTK;
- tamanho da barreira hidráulica no HAND (diagnóstico do gerador).

Uso:
  python pesquisas/validacao-campo-hand-santa-tereza/revisao_v6.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from analise_erros_campo import DATA, LIMIAR_HAND, ZERO_REGUA_M  # noqa: E402
from analises_adicionais import classe, loo  # noqa: E402


def r3(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 3)


def resumo(e):
    e = np.asarray(e, float)
    return {"n": int(e.size), "vies_m": r3(e.mean()), "mae_m": r3(np.abs(e).mean()),
            "rmse_m": r3(np.sqrt(np.mean(e ** 2))), "mediana_abs_m": r3(np.median(np.abs(e)))}


def wilson(k, n, z=1.96):
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [r3(c - h), r3(c + h)]


def dentro_05(e):
    e = np.abs(np.asarray(e, float))
    k = int((e <= 0.5).sum())
    return {"k": k, "n": int(e.size), "fracao": r3(k / e.size), "ic95_wilson": wilson(k, e.size)}


def regressao(z_dren, wse_obs):
    n = len(z_dren)
    lr = stats.linregress(z_dren, wse_obs)
    t = stats.t.ppf(0.975, n - 2)
    return {"n": n, "inclinacao": r3(lr.slope),
            "ic95": [r3(lr.slope - t * lr.stderr), r3(lr.slope + t * lr.stderr)],
            "p_inclinacao_1": r3(2 * stats.t.sf(abs((lr.slope - 1) / lr.stderr), n - 2)),
            "p_inclinacao_0": r3(lr.pvalue)}


def main():
    d = pd.read_csv(AQUI / "erros_campo_santa_tereza.csv")
    aa = json.loads((AQUI / "analises_adicionais.json").read_text())
    v = d[d.tipo == "marca"]
    h = d[d.tipo == "limite"]
    vr = v[v.rtk_valido == True]  # noqa: E712
    out = {"fonte": ["erros_campo_santa_tereza.csv", "analises_adicionais.json",
                     "assets/data/santa_tereza_inundacao/hand_lidar_5m_diagnostic.json"]}

    # 1. Métricas verticais
    out["V_ed"] = {**resumo(v.erro_lamina_m), "dentro_05m": dentro_05(v.erro_lamina_m)}
    out["V_ed_sem_V010"] = resumo(v[v.id != "V010"].erro_lamina_m)
    out["V_rtk_es"] = {**resumo(vr.erro_cota_rtk_m), "dentro_05m": dentro_05(vr.erro_cota_rtk_m)}
    out["V_rtk_es_sem_V011"] = resumo(vr[vr.id != "V011"].erro_cota_rtk_m)
    out["V_rtk_ed"] = {**resumo(vr.erro_lamina_m), "dentro_05m": dentro_05(vr.erro_lamina_m)}
    a, b = classe(v.lamina_obs_m), classe(v.lamina_hand_m)
    out["classes_V"] = {"acertos": int((a == b).sum()), "n": int(a.size),
                        "acertos_classe_maior_2m": int(((a == b) & (a == 3)).sum()),
                        "discordancias": v.id[a != b].tolist()}

    # 2. Outros eventos: erros individuais
    o = v[v.evento != "2023-09"]
    out["outros_eventos_V_ed"] = {"erros_m": {r.id: r3(r.erro_lamina_m) for r in o.itertuples()},
                                  "vies_m": r3(o.erro_lamina_m.mean()),
                                  "vies_sem_V011_m": r3(o[o.id != "V011"].erro_lamina_m.mean()),
                                  "locais_novos": int(o[o.id != "V001b"].shape[0])}

    # 3. Sensibilidade de z0 (o viés de set/2023 é linear em z0: deslocar z0 em δ soma −δ a d_H)
    cal = d[d.calibracao == True]  # noqa: E712
    cal_v, cal_h = cal[cal.tipo == "marca"], cal[cal.tipo == "limite"]
    s_es = d[(d.evento == "2023-09") & (d.rtk_valido == True)]  # noqa: E712
    cen = {
        "V_e_H_ed_17": ZERO_REGUA_M + cal.erro_lamina_m.mean(),
        "so_V_ed_9": ZERO_REGUA_M + cal_v.erro_lamina_m.mean(),
        "so_H_ed_8": ZERO_REGUA_M + cal_h.erro_lamina_m.mean(),
        "V_e_H_es_15": ZERO_REGUA_M + s_es.erro_cota_rtk_m.mean(),
    }
    out["sensibilidade_z0"] = {}
    for nome, z0 in cen.items():
        e = o.erro_lamina_m - (z0 - ZERO_REGUA_M)
        out["sensibilidade_z0"][nome] = {"z0_m": r3(z0), "outros_eventos_vies_m": r3(e.mean()),
                                         "outros_eventos_mae_m": r3(np.abs(e).mean()),
                                         "outros_eventos_mediana_abs_m": r3(np.median(np.abs(e)))}
    out["set2023_vies_es"] = {"V": r3(s_es[s_es.tipo == "marca"].erro_cota_rtk_m.mean()),
                              "H": r3(s_es[s_es.tipo == "limite"].erro_cota_rtk_m.mean())}

    # 4. Diagnóstico da premissa do HAND: cota observada × cota do trecho de drenagem de referência
    def pontos(sub):
        wo = (sub.z_rtk_m + sub.lamina_obs_m).to_numpy()
        wm = (sub.z_lidar_m + sub.lamina_hand_m).to_numpy()
        return wm - LIMIAR_HAND["2023-09"], wo, wm
    diag = {}
    for nome, sub in {"V_e_H_15": s_es, "so_V_7": s_es[s_es.tipo == "marca"],
                      "V_e_H_sem_V010_14": s_es[s_es.id != "V010"],
                      "so_V_sem_V010_6": s_es[(s_es.tipo == "marca") & (s_es.id != "V010")]}.items():
        zd, wo, wm = pontos(sub)
        diag[nome] = regressao(zd, wo)
    zd, wo, wm = pontos(s_es)
    sup = zd > 53.2
    um = np.ones(len(wo))[:, None]
    res_plano, res_hand = loo(wo, um), loo(wo - wm, um)
    diag["grupos"] = {"cota_drenagem_mediana_m": [r3(np.median(zd[~sup])), r3(np.median(zd[sup]))],
                      "diferenca_drenagem_m": r3(np.median(zd[sup]) - np.median(zd[~sup])),
                      "cota_obs_media_m": [r3(wo[~sup].mean()), r3(wo[sup].mean())],
                      "diferenca_obs_m": r3(wo[sup].mean() - wo[~sup].mean()),
                      "n": [int((~sup).sum()), int(sup.sum())]}
    diag["loo_V_e_H_15"] = {"mae_plano_m": r3(np.abs(res_plano).mean()), "mae_hand_m": r3(np.abs(res_hand).mean()),
                            "plano_melhor_em": int((np.abs(res_plano) < np.abs(res_hand)).sum()),
                            "p_wilcoxon": r3(stats.wilcoxon(np.abs(res_plano), np.abs(res_hand)).pvalue)}
    diag["pontos"] = [{"id": r.id, "tipo": r.tipo, "cota_drenagem_m": r3(z), "cota_obs_m": r3(w), "cota_hand_m": r3(m)}
                      for r, z, w, m in zip(s_es.itertuples(), zd, wo, wm)]
    out["diagnostico"] = diag

    # 5. Limites H: distância à borda com sinal (e_s > 0: o modelo inunda o ponto, limite dentro da mancha)
    decl = {p["id"]: p["declividade_pct"] for p in aa["erro_horizontal_limites"]["por_ponto"]}
    hh = h.assign(dentro=h.erro_cota_rtk_m > 0, decl=h.id.map(decl))
    hh["dist_assinada_rtk_m"] = np.where(hh.dentro, 1, -1) * hh.erro_h_rtk_m
    hh["dist_implicita_m"] = hh.erro_cota_rtk_m.abs() / (hh.decl / 100)
    out["limites_H"] = {
        "dentro": int(hh.dentro.sum()), "fora": int((~hh.dentro).sum()),
        "na_borda_es_menor_0_07m": int((hh.erro_cota_rtk_m.abs() < 0.07).sum()),
        "dist_rtk_m": {"media": r3(hh.erro_h_rtk_m.mean()), "mediana": r3(hh.erro_h_rtk_m.median()),
                       "min": r3(hh.erro_h_rtk_m.min()), "max": r3(hh.erro_h_rtk_m.max())},
        "dist_cel_m": {"media": r3(hh.erro_h_cel_m.mean()), "mediana": r3(hh.erro_h_cel_m.median())},
        "menores_que_meia_celula_2_5m": int((hh.erro_h_rtk_m < 2.5).sum()),
        "spearman_dist_rtk_vs_abs_es": r3(stats.spearmanr(hh.erro_h_rtk_m, hh.erro_cota_rtk_m.abs()).statistic),
        "spearman_dist_cel_vs_abs_ed": r3(stats.spearmanr(hh.erro_h_cel_m, hh.erro_lamina_m.abs()).statistic),
        "limite_inferior_separacao_cel_rtk_m": {
            "min": r3((hh.erro_h_rtk_m - hh.erro_h_cel_m).abs().min()),
            "mediana": r3((hh.erro_h_rtk_m - hh.erro_h_cel_m).abs().median()),
            "max": r3((hh.erro_h_rtk_m - hh.erro_h_cel_m).abs().max())},
        "d_H_nos_limites": resumo(hh.erro_lamina_m),
        "por_ponto": [{"id": r.id, "e_s_m": r3(r.erro_cota_rtk_m), "dist_assinada_rtk_m": r3(r.dist_assinada_rtk_m),
                       "dist_cel_m": r3(r.erro_h_cel_m), "declividade_pct": r3(r.decl),
                       "dist_implicita_m": r3(r.dist_implicita_m)} for r in hh.itertuples()],
    }

    # 6. Δz = [z_L(celular) − z_L(RTK)] + [z_L(RTK) − z_RTK], com o LiDAR de 10 m na posição RTK
    dz = vr.assign(pos=vr.z_lidar_m - vr.z_lidar10_no_rtk_m, terr=vr.z_lidar10_no_rtk_m - vr.z_rtk_m)
    out["delta_z_V"] = {
        "positivos": int((vr.dz_lidar_rtk_m > 0).sum()), "n": int(len(vr)),
        "mediana_m": r3(vr.dz_lidar_rtk_m.median()),
        "nmad_m": r3(1.4826 * np.median(np.abs(vr.dz_lidar_rtk_m - vr.dz_lidar_rtk_m.median()))),
        "decomposicao_lidar10": {r.id: {"posicao_m": r3(r.pos), "terreno_m": r3(r.terr)}
                                 for r in dz[dz.id.isin(["V010", "V011"])].itertuples()},
    }
    out["hand_web_5m_nas_posicoes_rtk_V"] = {
        **resumo(vr.erro_lamina_hand_web_rtk_m.dropna()),
        "max_abs": {r.id: r3(r.erro_lamina_hand_web_rtk_m) for r in
                    vr.loc[[vr.erro_lamina_hand_web_rtk_m.abs().idxmax()]].itertuples()}}

    # 7. Barreira hidráulica do HAND (diagnóstico do gerador)
    g = json.loads((DATA / "santa_tereza_inundacao" / "hand_lidar_5m_diagnostic.json").read_text())
    out["barreira_hidraulica"] = {
        "celulas_barreira_maior_0_10m": g["hydraulic_barrier_cells_gt_0_10m"],
        "celulas_validas": g["valid_terrain_cells"],
        "fracao": r3(g["hydraulic_barrier_cells_gt_0_10m"] / g["valid_terrain_cells"]),
        "p95_acrescimo_m": r3(g["hydraulic_barrier_added_p95_m"]),
        "resolucao_fonte_m": g["resolucao_fonte_m"], "fator_agregacao": g["fator_payload"],
        "metodo_agregacao": g["flowdir_coarse_method"]}
    out["mdt_nos_vertices_rtk"] = aa["mdt_nos_vertices_rtk"]

    dest = AQUI / "revisao_v6.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return dest


if __name__ == "__main__":
    print(main())
