#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figuras da v14 do manuscrito (SBSR 2027): o HAND avaliado é o krigado (INUND_HAND_2165), lido nas posições RTK.

  fig_v14_1_mapa.png        mapa em uma coluna com a mancha krigada de set/2023 (z0 = 1,60 m)
  fig_v14_2_profundidade.png profundidade observada × estimada nas 13 marcas (posição do celular)
  fig_v14_3_erros.png       erro em cada marca com RTK: profundidade na posição do celular e na posição RTK,
                            e cota da água (terreno RTK)
  fig_v14_4_borda.png       distância dos oito limites de set/2023 à borda da mancha krigada, com sinal
  fig_v14_5_diagnostico.png cota observada da cheia de set/2023 × cota do rio krigada na posição RTK (n = 15)

Lê revisao_v14.json (rodar revisao_v14.py antes). O mapa precisa da planilha de campo (coordenadas RTK, não
versionadas), do contorno dos estados e de mancha_krigada_set2023_z160.geojson; só é gerado se as entradas existirem.
A borda usa as distâncias da planilha, que a mancha krigada reproduz (distancias_borda_krigada.csv).

Uso:
  python pesquisas/validacao-campo-hand-santa-tereza/figuras_v14.py [sumario_erros_hand.xlsx brazil-states.geojson]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from figuras_manuscrito import CM, COR_EVENTO, FIG_DIR, ROT_EVENTO, _desenha_mapa  # noqa: E402
from figuras_v7 import AFLUENTE, CINZA, LARANJA, MK, limpa, virgula  # noqa: E402

GEOJSON = AQUI / "mancha_krigada_set2023_z160.geojson"


def figura_mapa(xlsx: Path, estados: Path):
    mancha = json.loads(GEOJSON.read_text())["features"][0]["geometry"]
    fig = plt.figure(figsize=(8.4 * CM, 13.2 * CM))
    ax = fig.add_axes([0.15, 0.20, 0.84, 0.79])
    ax.set_anchor("S")
    rot = {"V010": (4, 3), "V011": (-27, -3), "V005": (5, -7), "V009": (-27, 4), "H003": (4, 3), "H004": (4, 3),
           "H007": (3, -9), "H001": (-9, 6)}
    leg = _desenha_mapa(ax, xlsx, estados, rotulos=rot, mancha=mancha, rotulo_mancha="Mancha do HAND krigado, set/2023")
    leg[2].set_label("Evento set/2023 (calibração)")
    fig.canvas.draw()
    pos = ax.get_position()
    fig.legend(handles=leg, loc="upper center", bbox_to_anchor=((pos.x0 + pos.x1) / 2 - 0.04, pos.y0 - 0.05), ncol=2,
               fontsize=6, handlelength=1.1, labelspacing=0.3, columnspacing=0.6, handletextpad=0.35)
    out = FIG_DIR / "fig_v14_1_mapa.png"
    fig.savefig(out, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    return out


def figura_profundidade():
    """Profundidade observada × estimada nas 13 marcas, com T_H na posição do celular (planilha), z0 = 1,60 m.

    Círculo vazio = posição do celular, como na Figura 3; cores dos eventos iguais às do mapa.
    """
    v = pd.read_csv(AQUI / "erros_campo_santa_tereza.csv")
    v = v[v.tipo == "marca"]
    fig, ax = plt.subplots(figsize=(7.0 * CM, 6.6 * CM))
    ax.plot([0, 5], [0, 5], ls="--", color="#9a9a9a", lw=0.9, zorder=1)
    for ev, c in COR_EVENTO.items():
        s = v[v.evento == ev]
        ax.plot(s.lamina_obs_m, s.lamina_hand_m, "o", ms=4.6, mfc="white", mec=c, mew=1.1, zorder=3)
    for r in v[v.id.isin(["V010", "V011"])].itertuples():
        ax.annotate(r.id, (r.lamina_obs_m, r.lamina_hand_m), textcoords="offset points", xytext=(5, -3), fontsize=6.5)
    ax.set(xlim=(0, 5), ylim=(0, 5), aspect="equal")
    ax.set_xlabel("Profundidade observada (m)")
    ax.set_ylabel("Profundidade estimada (m)")
    ax.xaxis.set_major_locator(MultipleLocator(1))
    ax.yaxis.set_major_locator(MultipleLocator(1))
    virgula(ax)
    limpa(ax)
    leg = [Line2D([], [], ls="none", marker="o", ms=4.6, mfc="white", mec=c, mew=1.1, label=ROT_EVENTO[e])
           for e, c in COR_EVENTO.items()]
    leg.append(Line2D([], [], color="#9a9a9a", ls="--", lw=0.9, label="1:1"))
    ax.legend(handles=leg, loc="upper left", fontsize=6, frameon=False, handletextpad=0.3, labelspacing=0.3)
    out = FIG_DIR / "fig_v14_2_profundidade.png"
    fig.savefig(out, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    return out


def figura_erros(rev: dict):
    p = pd.DataFrame(rev["V_rtk_por_ponto"])
    ordem = {"2023-09": 0, "2023-11": 1, "2024-05": 2}
    p = p.assign(o=p.evento.map(ordem)).sort_values(["o", "id"]).reset_index(drop=True)
    y = np.arange(len(p))[::-1]
    fig, ax = plt.subplots(figsize=(7.0 * CM, 6.6 * CM))
    ax.axvspan(-0.5, 0.5, color="#ececec", zorder=0)
    ax.axvline(0, color="#9a9a9a", lw=0.6, zorder=1)
    for yi, r in zip(y, p.itertuples()):
        c = COR_EVENTO[r.evento]
        ax.annotate("", xy=(r.ed_rtk_m, yi), xytext=(r.ed_celular_m, yi),
                    arrowprops=dict(arrowstyle="-|>", color="#8c8c8c", lw=0.8, shrinkA=3, shrinkB=3), zorder=2)
        ax.plot(r.ed_celular_m, yi, "o", ms=4.6, mfc="white", mec=c, mew=1.0, zorder=3)
        ax.plot(r.ed_rtk_m, yi, "o", ms=4.6, mfc=c, mec=c, zorder=4)
        ax.plot(r.es_m, yi, "D", ms=3.6, mfc="none", mec="#1a1a1a", mew=0.8, zorder=5)
    ax.set_yticks(y, p.id)
    ax.tick_params(axis="y", labelsize=6.8, length=0)
    ax.set_xlim(-3.6, 3.3)
    ax.set_ylim(-0.7, len(p) - 0.3)
    ax.xaxis.set_major_locator(MultipleLocator(1))
    ax.set_xlabel("Erro (m); positivo = superestimativa")
    virgula(ax, "x")
    limpa(ax)
    ax.spines["left"].set_visible(False)
    leg = [Line2D([], [], ls="none", marker="o", ms=4.6, mfc="white", mec="#555555", mew=1.0,
                  label="Profundidade, posição do celular"),
           Line2D([], [], ls="none", marker="o", ms=4.6, mfc="#555555", mec="#555555", label="Profundidade, posição RTK"),
           Line2D([], [], ls="none", marker="D", ms=3.6, mfc="none", mec="#1a1a1a", mew=0.8, label="Cota da água")]
    leg += [Line2D([], [], ls="none", marker="s", ms=4.2, mfc=c, mec=c, label=ROT_EVENTO[e]) for e, c in COR_EVENTO.items()]
    ax.legend(handles=leg, loc="upper center", bbox_to_anchor=(0.45, -0.2), ncol=2, fontsize=6, frameon=False,
              handletextpad=0.3, columnspacing=0.8, labelspacing=0.25)
    out = FIG_DIR / "fig_v14_3_erros.png"
    fig.savefig(out, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    return out


def figura_borda(rev: dict):
    """Distância à borda com sinal: positivo = limite dentro da mancha (a mancha passa do limite observado).

    Distâncias da planilha (erro_h_rtk_m, erro_h_cel_m), medidas até a mancha krigada de set/2023 com z0 = 1,60 m
    (a sessão local as reproduziu com diferença média de 0,25 m; ver distancias_borda_krigada.csv). O sinal vem de
    e_d no mesmo ponto: e_d > 0 é profundidade estimada positiva, isto é, ponto dentro da mancha.
    """
    h = pd.DataFrame(rev["limites_set2023"]["por_ponto"]).sort_values("id").reset_index(drop=True)
    h["s_rtk"] = np.where(h.ed_rtk_m > 0, 1, -1) * h.dist_rtk_m
    h["s_cel"] = np.where(h.ed_cel_m > 0, 1, -1) * h.dist_cel_m
    y = np.arange(len(h))[::-1]
    fig, ax = plt.subplots(figsize=(7.0 * CM, 5.6 * CM))
    ax.axvline(0, color="#9a9a9a", lw=0.6, zorder=1)
    for yi, r in zip(y, h.itertuples()):
        c = "#8c8c8c" if r.id in AFLUENTE else "#1a1a1a"
        ax.plot([r.s_cel, r.s_rtk], [yi, yi], color="#c4c4c4", lw=1.0, zorder=2)
        ax.plot(r.s_cel, yi, "o", ms=4.6, mfc="white", mec=c, mew=1.0, zorder=3)
        ax.plot(r.s_rtk, yi, "s", ms=4.4, mfc=c, mec=c, zorder=4)
    ax.set_yticks(y, h.id)
    ax.tick_params(axis="y", labelsize=6.8, length=0)
    for lab in ax.get_yticklabels():
        if lab.get_text() in AFLUENTE:
            lab.set_color("#8c8c8c")
    ax.set_xlim(-10.5, 7.5)
    ax.set_ylim(-0.7, len(h) + 0.4)
    ax.text(-0.4, len(h) - 0.15, "fora da mancha", ha="right", fontsize=6.5, style="italic", color=CINZA)
    ax.text(0.4, len(h) - 0.15, "dentro", ha="left", fontsize=6.5, style="italic", color=CINZA)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.set_xlabel("Distância à borda (m); positivo = dentro da mancha")
    virgula(ax, "x")
    limpa(ax)
    ax.spines["left"].set_visible(False)
    leg = [Line2D([], [], ls="none", marker="o", ms=4.6, mfc="white", mec="#555555", mew=1.0, label="Posição do celular"),
           Line2D([], [], ls="none", marker="s", ms=4.4, mfc="#555555", mec="#555555", label="Posição RTK"),
           Line2D([], [], ls="none", marker="s", ms=4.4, mfc="#8c8c8c", mec="#8c8c8c", label="Vale do afluente")]
    ax.legend(handles=leg, loc="upper center", bbox_to_anchor=(0.45, -0.24), ncol=3, fontsize=6, frameon=False,
              handletextpad=0.3, columnspacing=0.8)
    out = FIG_DIR / "fig_v14_4_borda.png"
    fig.savefig(out, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    return out


def figura_diagnostico(rev: dict):
    e = pd.read_csv(AQUI / "erros_campo_santa_tereza.csv")
    rr = pd.read_csv(AQUI / "rasters_1m_nas_posicoes.csv")[["id", "z_dren_krig_rtk"]]
    p = e.merge(rr, on="id")
    p = p[(p.evento == "2023-09") & (p.rtk_valido == True)].copy()  # noqa: E712
    p["obs"] = p.z_rtk_m + p.lamina_obs_m
    lim = 23.65 - 1.60
    fig, ax = plt.subplots(figsize=(8.2 * CM, 6.8 * CM))
    xx = np.array([p.z_dren_krig_rtk.min() - 0.15, p.z_dren_krig_rtk.max() + 0.15])
    ax.plot(xx, xx + lim, color=LARANJA, ls="--", lw=1.2, zorder=2)
    ax.axhline(p.obs.mean(), color="#9a9a9a", ls=":", lw=1.2, zorder=1)
    ax.plot(xx, np.polyval(np.polyfit(p.z_dren_krig_rtk, p.obs, 1), xx), color=CINZA, lw=1.0, zorder=2)
    afl = p.id.isin(AFLUENTE)
    for tipo, mk in MK.items():
        s = p[(p.tipo == tipo) & ~afl]
        ax.plot(s.z_dren_krig_rtk, s.obs, ls="none", marker=mk, ms=5.2 if tipo == "marca" else 4.6,
                mfc="#1a1a1a" if tipo == "marca" else "white", mec="#1a1a1a", mew=0.6 if tipo == "marca" else 1.0,
                zorder=4)
    s = p[afl]
    ax.plot(s.z_dren_krig_rtk, s.obs, ls="none", marker="o", ms=4.6, mfc="#bdbdbd", mec="#6b6b6b", mew=1.0, zorder=4)
    r = p[p.id == "V010"].iloc[0]
    ax.annotate("V010", (r.z_dren_krig_rtk, r.obs), textcoords="offset points", xytext=(5, -3), fontsize=6.5)
    ax.set_xlabel("Cota do rio krigada na posição RTK (m)")
    ax.set_ylabel("Cota da cheia observada, RTK (m)")
    ax.xaxis.set_major_locator(MultipleLocator(0.5))
    ax.yaxis.set_major_locator(MultipleLocator(0.5))
    virgula(ax)
    limpa(ax)
    inc = rev["diagnostico"]["V_e_H"]["inclinacao"]
    leg = [Line2D([], [], ls="none", marker="^", ms=5, mfc="#1a1a1a", mec="#1a1a1a", label="Marca (V)"),
           Line2D([], [], ls="none", marker="o", ms=4.6, mfc="white", mec="#1a1a1a", mew=1.0, label="Limite (H)"),
           Line2D([], [], ls="none", marker="o", ms=4.6, mfc="#bdbdbd", mec="#6b6b6b", mew=1.0,
                  label="Limite no vale do afluente"),
           Line2D([], [], color=LARANJA, ls="--", lw=1.2, label="Premissa do HAND (inclinação 1)"),
           Line2D([], [], color="#9a9a9a", ls=":", lw=1.2, label="Plano horizontal (média)"),
           Line2D([], [], color=CINZA, lw=1.0, label=f"Ajuste (inclinação {inc:.2f})".replace(".", ",").replace("-", "−"))]
    ax.legend(handles=leg, loc="upper center", bbox_to_anchor=(0.42, -0.22), ncol=2, fontsize=6,
              handlelength=1.6, columnspacing=0.7, labelspacing=0.25, frameon=False)
    fig.subplots_adjust(left=0.15, right=0.98, top=0.97, bottom=0.36)
    out = FIG_DIR / "fig_v14_5_diagnostico.png"
    fig.savefig(out, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    return out


if __name__ == "__main__":
    rev = json.loads((AQUI / "revisao_v14.json").read_text())
    print(figura_profundidade())
    print(figura_erros(rev))
    print(figura_diagnostico(rev))
    print(figura_borda(rev))
    if len(sys.argv) >= 3 and GEOJSON.exists():
        print(figura_mapa(Path(sys.argv[1]), Path(sys.argv[2])))
