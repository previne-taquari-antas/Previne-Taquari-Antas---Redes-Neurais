#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figuras da v7 do manuscrito (SBSR 2027): as da v6, refeitas após os pareceres da v5, com os ajustes da segunda rodada (afluente destacado e eixo renomeado no diagnóstico; rótulo H001 no mapa).

  fig_v7_1_mapa.png         mapa em uma coluna, com a legenda embaixo
  fig_v7_2_vertical.png     (a) profundidade observada × estimada, V (n = 13), faixa de ±0,5 m;
                            (b) erro de cada marca V com RTK: e_d (terreno do celular) → e_s (terreno RTK)
  fig_v7_3_diagnostico.png  cota observada da cheia de set/2023 × cota do trecho de drenagem de referência,
                            V e H com RTK (n = 15), com a premissa do HAND, o plano horizontal e o ajuste

Mesmo estilo em todas: fonte serifada do corpo do texto e as cores de evento do mapa.

Uso:
  python pesquisas/validacao-campo-hand-santa-tereza/figuras_v7.py \
      caminho/sumario_erros_hand.xlsx caminho/brazil-states.geojson
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
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MultipleLocator

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from figuras_manuscrito import CM, COR_EVENTO, FIG_DIR, ROT_EVENTO, _desenha_mapa  # noqa: E402

COL = 7.0 * CM          # largura impressa na coluna do SBSR (fontes em tamanho final)
DUAS = 15.5 * CM        # largura impressa nas duas colunas
LARANJA, CINZA = "#d9531e", "#555555"
MK = {"marca": "^", "limite": "o"}
AFLUENTE = ("H003", "H004", "H007")  # limites no vale do afluente, fora da mancha


def virgula(ax, eixos="xy"):
    f = FuncFormatter(lambda v, _p: f"{v:g}".replace(".", ",").replace("-", "−"))
    if "x" in eixos:
        ax.xaxis.set_major_formatter(f)
    if "y" in eixos:
        ax.yaxis.set_major_formatter(f)


def limpa(ax):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.tick_params(labelsize=7)


def figura_mapa(xlsx: Path, estados: Path):
    fig = plt.figure(figsize=(8.4 * CM, 13.2 * CM))
    ax = fig.add_axes([0.15, 0.20, 0.84, 0.79])
    ax.set_anchor("S")
    rot = {"V010": (4, 3), "V011": (-27, -3), "V005": (5, -7), "V009": (-27, 4), "H003": (4, 3), "H004": (4, 3),
           "H007": (3, -9), "H001": (-9, 6)}
    leg = _desenha_mapa(ax, xlsx, estados, rotulos=rot)
    leg[2].set_label("Evento set/2023 (calibração)")
    fig.canvas.draw()
    pos = ax.get_position()
    fig.legend(handles=leg, loc="upper center", bbox_to_anchor=((pos.x0 + pos.x1) / 2 - 0.04, pos.y0 - 0.05), ncol=2,
               fontsize=6, handlelength=1.1, labelspacing=0.3, columnspacing=0.6, handletextpad=0.35)
    out = FIG_DIR / "fig_v7_1_mapa.png"
    fig.savefig(out, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    return out


def figura_vertical(d: pd.DataFrame):
    fig, (a, b) = plt.subplots(1, 2, figsize=(DUAS, 5.7 * CM), gridspec_kw={"width_ratios": [1, 1.25]})

    # (a) profundidade observada × estimada nas 13 observações V
    v = d[d.tipo == "marca"]
    lim = 5.0
    a.fill_between([0, lim], [-0.5, lim - 0.5], [0.5, lim + 0.5], color="#e6e6e6", lw=0)
    a.plot([0, lim], [0, lim], color="black", lw=0.7)
    for ev, cor in COR_EVENTO.items():
        s = v[v.evento == ev]
        a.plot(s.lamina_obs_m, s.lamina_hand_m, ls="none", marker="^", ms=5, mfc=cor, mec="white", mew=0.4)
    desloc = {"V010": (-25, -3), "V011": (-25, -3), "V001": (-17, 5), "V001b": (-12, 6)}
    for r in v[v.id.isin(desloc)].itertuples():
        a.annotate(r.id, (r.lamina_obs_m, r.lamina_hand_m), textcoords="offset points", xytext=desloc[r.id],
                   fontsize=6.5)
    a.set(xlim=(0, lim), ylim=(0, lim), aspect="equal", xlabel="Profundidade observada (m)",
          ylabel="Profundidade estimada, $d_H$ (m)")
    leg = [Line2D([], [], ls="none", marker="^", ms=5, mfc=c, mec="white", label=ROT_EVENTO[e])
           for e, c in COR_EVENTO.items()]
    leg.append(Patch(fc="#e6e6e6", label="±0,5 m"))
    a.legend(handles=leg, loc="upper left", fontsize=6.5, handletextpad=0.3, labelspacing=0.3, frameon=False)
    a.text(-0.21, 1.02, "(a)", transform=a.transAxes, fontsize=9, fontweight="bold")
    limpa(a)

    # (b) e_d → e_s em cada marca V com RTK
    vr = d[(d.tipo == "marca") & (d.rtk_valido == True)].sort_values("id")  # noqa: E712
    y = np.arange(len(vr))[::-1]
    b.axvspan(-0.5, 0.5, color="#e6e6e6", lw=0, zorder=0)
    b.axvline(0, color="black", lw=0.6, zorder=1)
    for yi, r in zip(y, vr.itertuples()):
        cor = COR_EVENTO[r.evento]
        b.annotate("", xy=(r.erro_cota_rtk_m, yi), xytext=(r.erro_lamina_m, yi), zorder=2,
                   arrowprops=dict(arrowstyle="-|>", color="#9a9a9a", lw=0.8, mutation_scale=7,
                                   shrinkA=3, shrinkB=3))
        b.plot(r.erro_lamina_m, yi, marker="^", ms=5, mfc="white", mec=cor, mew=0.9, ls="none", zorder=3)
        b.plot(r.erro_cota_rtk_m, yi, marker="^", ms=5, mfc=cor, mec="white", mew=0.4, ls="none", zorder=4)
    b.set_yticks(y, vr.id, fontsize=6.8)
    b.set_xlim(-3.6, 3.3)
    b.set_ylim(-0.7, len(vr) - 0.3)
    b.set_xlabel("Erro (m); positivo = superestimativa")
    b.legend(handles=[Line2D([], [], ls="none", marker="^", ms=5, mfc="white", mec="black", mew=0.9,
                             label="$e_d$: terreno na posição do celular"),
                      Line2D([], [], ls="none", marker="^", ms=5, mfc="black", mec="white",
                             label="$e_s$: terreno RTK")],
             loc="upper left", fontsize=6.5, handletextpad=0.3, labelspacing=0.3, frameon=True,
             framealpha=0.95, edgecolor="none", borderpad=0.3)
    b.text(-0.12, 1.02, "(b)", transform=b.transAxes, fontsize=9, fontweight="bold")
    virgula(b, "x")
    limpa(b)
    fig.subplots_adjust(left=0.07, right=0.99, bottom=0.17, top=0.93, wspace=0.28)
    out = FIG_DIR / "fig_v7_2_vertical.png"
    fig.savefig(out, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    return out


def figura_diagnostico(rev: dict):
    p = pd.DataFrame(rev["diagnostico"]["pontos"])
    lim = 22.05
    fig, ax = plt.subplots(figsize=(8.2 * CM, 6.8 * CM))
    xx = np.array([p.cota_drenagem_m.min() - 0.15, p.cota_drenagem_m.max() + 0.15])
    ax.plot(xx, xx + lim, color=LARANJA, ls="--", lw=1.2, zorder=2)
    ax.axhline(p.cota_obs_m.mean(), color="#9a9a9a", ls=":", lw=1.2, zorder=1)
    lr = np.polyfit(p.cota_drenagem_m, p.cota_obs_m, 1)
    ax.plot(xx, np.polyval(lr, xx), color=CINZA, lw=1.0, zorder=2)
    afl = p.id.isin(AFLUENTE)
    for tipo, mk in MK.items():
        s = p[(p.tipo == tipo) & ~afl]
        ax.plot(s.cota_drenagem_m, s.cota_obs_m, ls="none", marker=mk, ms=5.2 if tipo == "marca" else 4.6,
                mfc="#1a1a1a" if tipo == "marca" else "white", mec="#1a1a1a", mew=0.6 if tipo == "marca" else 1.0,
                zorder=4)
    s = p[afl]
    ax.plot(s.cota_drenagem_m, s.cota_obs_m, ls="none", marker="o", ms=4.6, mfc="#bdbdbd", mec="#6b6b6b", mew=1.0,
            zorder=4)
    r = p[p.id == "V010"].iloc[0]
    ax.annotate("V010", (r.cota_drenagem_m, r.cota_obs_m), textcoords="offset points", xytext=(5, -3), fontsize=6.5)
    ax.set_xlabel("Cota de drenagem reconstruída (m)")
    ax.set_ylabel("Cota da cheia observada, RTK (m)")
    ax.xaxis.set_major_locator(MultipleLocator(0.5))
    ax.yaxis.set_major_locator(MultipleLocator(0.5))
    virgula(ax)
    limpa(ax)
    reg = rev["diagnostico"]["V_e_H_15"]
    leg = [Line2D([], [], ls="none", marker="^", ms=5, mfc="#1a1a1a", mec="#1a1a1a", label="Marca (V)"),
           Line2D([], [], ls="none", marker="o", ms=4.6, mfc="white", mec="#1a1a1a", mew=1.0, label="Limite (H)"),
           Line2D([], [], ls="none", marker="o", ms=4.6, mfc="#bdbdbd", mec="#6b6b6b", mew=1.0,
                  label="Limite no vale do afluente"),
           Line2D([], [], color=LARANJA, ls="--", lw=1.2, label="Premissa do HAND (inclinação 1)"),
           Line2D([], [], color="#9a9a9a", ls=":", lw=1.2, label="Plano horizontal (média)"),
           Line2D([], [], color=CINZA, lw=1.0,
                  label=f"Ajuste (inclinação {reg['inclinacao']:.2f})".replace(".", ",").replace("-", "−"))]
    ax.legend(handles=leg, loc="upper center", bbox_to_anchor=(0.42, -0.22), ncol=2, fontsize=6,
              handlelength=1.6, columnspacing=0.7, labelspacing=0.25, frameon=False)
    fig.subplots_adjust(left=0.15, right=0.98, top=0.97, bottom=0.36)
    out = FIG_DIR / "fig_v7_3_diagnostico.png"
    fig.savefig(out, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    dados = pd.read_csv(AQUI / "erros_campo_santa_tereza.csv")
    rev = json.loads((AQUI / "revisao_v6.json").read_text())
    print(figura_mapa(Path(sys.argv[1]), Path(sys.argv[2])))
    print(figura_vertical(dados))
    print(figura_diagnostico(rev))
