#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gráficos do manuscrito separados, um por arquivo, para escolher quais ficam.

Cada gráfico tem largura de uma coluna do SBSR (8,6 cm) e o mesmo estilo da Figura 2
da versão no Google Docs (cores por evento, linha 1:1 tracejada), com a mesma fonte serifada (Liberation Serif,
métrica igual à Times New Roman) das figuras do mapa e do diagnóstico.

  fig_sep_2_profundidade_v.png      profundidade observada × estimada, V (n = 13)
  fig_sep_3_cota_agua_v_rtk.png     cota da água observada (RTK) × reconstruída, V com RTK (n = 10)
  fig_sep_4_borda_h.png             distância dos limites H à borda, celular × RTK (n = 9)
  fig_sep_5_colunas_originais.png   colunas de erro vertical absoluto da TABELA_ARTIGOS, celular × RTK
                                    (a coluna RTK é, em 16 dos 20 pares, Δz = LiDAR − RTK do terreno, não erro da
                                    estimativa; V001a, V005, V009 e V011 não batem com nenhuma grandeza calculada)
  fig_sep_6_erro_celular_rtk_v.png  |e_d| (terreno na posição do celular) × |e_s| (terreno RTK), V com RTK (n = 10)

O mapa (fig_manuscrito_1_mapa.png) e o diagnóstico (fig_manuscrito_2_diagnostico_v.png) já são
figuras separadas.

Uso:
  python pesquisas/validacao-campo-hand-santa-tereza/figuras_separadas.py caminho/sumario_erros_hand.xlsx
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import openpyxl
import pandas as pd
from matplotlib.lines import Line2D

AQUI = Path(__file__).resolve().parent
FIG = AQUI / "figuras"
CM = 1 / 2.54
LARG = 8.6 * CM

AZUL, VERMELHAO, VERDE, CINZA = "#0072B2", "#D55E00", "#009E73", "#444444"
EVENTOS = {
    "2023-09": dict(rot="set/2023", cor=AZUL, mk="o"),
    "2023-11": dict(rot="nov/2023", cor=VERMELHAO, mk="s"),
    "2024-05": dict(rot="mai/2024", cor=VERDE, mk="^"),
}
plt.rcParams.update({
    "font.family": "Liberation Serif", "font.size": 8, "axes.labelsize": 8.5, "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5, "legend.fontsize": 7.5, "legend.frameon": False, "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#e6e6e6",
    "grid.linewidth": 0.6, "axes.axisbelow": True, "savefig.dpi": 400, "savefig.bbox": "tight",
    "savefig.pad_inches": 0.03, "axes.formatter.use_locale": False, "mathtext.fontset": "stix",
})


def virgula(ax, eixos="xy", casas=None):
    """Separador decimal com vírgula nos rótulos dos eixos."""
    def fmt(v, _pos):
        txt = f"{v:.{casas}f}" if casas is not None else f"{v:g}"
        return txt.replace(".", ",").replace("-", "−")
    from matplotlib.ticker import FuncFormatter
    if "x" in eixos:
        ax.xaxis.set_major_formatter(FuncFormatter(fmt))
    if "y" in eixos:
        ax.yaxis.set_major_formatter(FuncFormatter(fmt))


def ponto(ax, x, y, ev, **kw):
    e = EVENTOS[ev]
    ax.scatter(x, y, s=kw.pop("s", 26), marker=e["mk"], color=e["cor"], edgecolor="white", linewidth=0.5,
               zorder=3, label=e["rot"], **kw)


def legenda_eventos(ax, eventos, **kw):
    hs = [Line2D([], [], ls="none", marker=EVENTOS[ev]["mk"], ms=5, mfc=EVENTOS[ev]["cor"], mec="white",
                 mew=0.5, label=EVENTOS[ev]["rot"]) for ev in eventos]
    hs.append(Line2D([], [], color=CINZA, ls="--", lw=1, label="1:1"))
    ax.legend(handles=hs, **kw)


def salvar(fig, nome):
    out = FIG / nome
    fig.savefig(out)
    plt.close(fig)
    return out


def fig_profundidade_v(d):
    v = d[d.tipo == "marca"]
    fig, ax = plt.subplots(figsize=(LARG, LARG * 0.9))
    ax.plot([0, 5], [0, 5], ls="--", color=CINZA, lw=1, zorder=2)
    for ev in EVENTOS:
        s = v[v.evento == ev]
        ponto(ax, s.lamina_obs_m, s.lamina_hand_m, ev)
    for _, r in v[v.id.isin(["V010", "V011"])].iterrows():
        ax.annotate(r.id, (r.lamina_obs_m, r.lamina_hand_m), xytext=(5, -2), textcoords="offset points", fontsize=7)
    ax.set(xlim=(0, 5), ylim=(0, 5), aspect="equal", xlabel="Profundidade observada (m)",
           ylabel="Profundidade estimada (m)")
    legenda_eventos(ax, EVENTOS, loc="upper left", handletextpad=0.3, labelspacing=0.35)
    return salvar(fig, "fig_sep_2_profundidade_v.png")


def fig_cota_agua_v_rtk(d):
    v = d[(d.tipo == "marca") & (d.rtk_valido == True)].copy()  # noqa: E712
    v["obs"] = v.z_rtk_m + v.lamina_obs_m
    v["rec"] = v.z_lidar_m + v.lamina_hand_m
    lo = np.floor(min(v.obs.min(), v.rec.min())) - 0.5
    hi = np.ceil(max(v.obs.max(), v.rec.max())) + 0.5
    fig, ax = plt.subplots(figsize=(LARG, LARG * 0.9))
    ax.plot([lo, hi], [lo, hi], ls="--", color=CINZA, lw=1, zorder=2)
    for ev in EVENTOS:
        s = v[v.evento == ev]
        ponto(ax, s.obs, s.rec, ev)
    for _, r in v[v.id.isin(["V010", "V011"])].iterrows():
        ax.annotate(r.id, (r.obs, r.rec), xytext=(5, -2), textcoords="offset points", fontsize=7)
    ax.set(xlim=(lo, hi), ylim=(lo, hi), aspect="equal", xlabel="Cota da água observada, RTK (m)",
           ylabel="Cota da água reconstruída (m)")
    from matplotlib.ticker import MultipleLocator
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.yaxis.set_major_locator(MultipleLocator(2))
    virgula(ax)
    legenda_eventos(ax, EVENTOS, loc="upper left", handletextpad=0.3, labelspacing=0.35)
    return salvar(fig, "fig_sep_3_cota_agua_v_rtk.png")


def fig_borda_h(d):
    h = d[d.tipo == "limite"].sort_values("id")
    y = np.arange(len(h))[::-1]
    fig, ax = plt.subplots(figsize=(LARG, LARG * 0.72))
    fora = (h.erro_cota_rtk_m < 0).to_numpy()  # pelo sinal de e_s: abaixo da superfície d'água do HAND
    for yi, (_, r) in zip(y, h.iterrows()):
        ax.plot([r.erro_h_cel_m, r.erro_h_rtk_m], [yi, yi], color="#a6a6a6", lw=1, zorder=1)
    ax.axvline(2.5, color=CINZA, ls=":", lw=0.9, zorder=0)
    ax.text(2.6, len(h) - 0.75, "meia célula", fontsize=6.5, color=CINZA, style="italic", va="bottom")
    ax.scatter(h.erro_h_cel_m, y, s=30, color=AZUL, edgecolor="white", linewidth=0.5, zorder=3, label="Celular")
    ax.scatter(h.erro_h_rtk_m[~fora], y[~fora], s=26, marker="s", facecolor="white", edgecolor=VERMELHAO,
               linewidth=1.1, zorder=3, label="RTK, dentro da mancha")
    ax.scatter(h.erro_h_rtk_m[fora], y[fora], s=26, marker="s", color=VERMELHAO, edgecolor=VERMELHAO,
               linewidth=1.1, zorder=3, label="RTK, fora da mancha")
    ax.set_yticks(y, h.id)
    ax.set(xlim=(0, 10), ylim=(-0.6, len(h) + 0.1), xlabel="Distância à borda da mancha (m)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", handletextpad=0.2, labelspacing=0.3)
    return salvar(fig, "fig_sep_4_borda_h.png")


def fig_erro_celular_rtk_v(d):
    """Erro absoluto com o terreno na posição do celular (|e_d|) e com o terreno RTK (|e_s|), V com RTK."""
    v = d[(d.tipo == "marca") & (d.rtk_valido == True)].copy()  # noqa: E712
    v["ed"] = v.erro_lamina_m.abs()
    v["es"] = v.erro_cota_rtk_m.abs()
    lim = 3.5
    fig, ax = plt.subplots(figsize=(LARG, LARG * 0.9))
    ax.plot([0, lim], [0, lim], ls="--", color=CINZA, lw=1, zorder=2)
    for ev in EVENTOS:
        s = v[v.evento == ev]
        ponto(ax, s.ed, s.es, ev)
    for _, r in v[v.id.isin(["V010", "V011"])].iterrows():
        ax.annotate(r.id, (r.ed, r.es), xytext=(5, -2), textcoords="offset points", fontsize=7)
    ax.text(0.15, 1.95, "o terreno RTK aumenta |e|", fontsize=7, color=CINZA, style="italic")
    ax.text(1.55, 0.95, "o terreno RTK reduz |e|", fontsize=7, color=CINZA, style="italic")
    ax.set(xlim=(-0.1, lim), ylim=(-0.1, lim), aspect="equal", xlabel="|$e_d$|, terreno na posição do celular (m)",
           ylabel="|$e_s$|, terreno RTK (m)")
    virgula(ax)
    legenda_eventos(ax, EVENTOS, loc="upper left", handletextpad=0.3, labelspacing=0.35)
    print(f"V com RTK: {len(v)}; RTK aumenta o erro em {(v.es > v.ed).sum()}, reduz em {(v.es < v.ed).sum()}")
    return salvar(fig, "fig_sep_6_erro_celular_rtk_v.png")


def colunas_originais(xlsx):
    """Erro vertical absoluto das colunas celular e RTK da aba TABELA_ARTIGOS (pares completos)."""
    ws = openpyxl.load_workbook(xlsx, data_only=True, read_only=True)["TABELA_ARTIGOS"]
    linhas = list(ws.iter_rows(values_only=True))
    cab = [str(c).strip() if c is not None else "" for c in linhas[0]]
    i_id = cab.index("ID")
    i_cel = cab.index("ERRO ABSOLUTO VERTICAL (m) CELULAR")
    i_rtk = cab.index("ERRO ABSOLUTO VERTICAL (m) RTK")
    reg = []
    for ln in linhas[1:]:
        pid = ln[i_id]
        if not isinstance(pid, str) or pid[:1] not in "VH":
            continue
        reg.append({"id": pid, "cel": ln[i_cel], "rtk": ln[i_rtk]})
    t = pd.DataFrame(reg)
    return t, t.dropna(subset=["cel", "rtk"])


def fig_colunas_originais(xlsx):
    todos, t = colunas_originais(xlsx)
    fig, ax = plt.subplots(figsize=(LARG, LARG * 0.9))
    ax.plot([0, 5], [0, 5], ls="--", color=CINZA, lw=1, zorder=2)
    v, h = t[t.id.str.startswith("V")], t[t.id.str.startswith("H")]
    ax.scatter(v.cel, v.rtk, s=28, color=AZUL, edgecolor="white", linewidth=0.5, zorder=3,
               label=f"V ({len(v)} pares)")
    ax.scatter(h.cel, h.rtk, s=26, marker="s", color=VERMELHAO, edgecolor="white", linewidth=0.5, zorder=3,
               label=f"H ({len(h)} pares)")
    for _, r in t[t.id.isin(["V005", "V009", "V010", "V011"])].iterrows():
        ax.annotate(r.id, (r.cel, r.rtk), xytext=(5, -2), textcoords="offset points", fontsize=7)
    ax.set(xlim=(0, 5), ylim=(0, 5), aspect="equal", xlabel="Coluna celular, erro absoluto (m)",
           ylabel="Coluna RTK, erro absoluto (m)")
    hs, _ = ax.get_legend_handles_labels()
    hs.append(Line2D([], [], color=CINZA, ls="--", lw=1, label="1:1"))
    ax.legend(handles=hs, loc="lower right", handletextpad=0.3, labelspacing=0.35)
    print(f"TABELA_ARTIGOS: {len(todos)} registros, {len(t)} pares completos ({len(v)} V, {len(h)} H)")
    return salvar(fig, "fig_sep_5_colunas_originais.png")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    dados = pd.read_csv(AQUI / "erros_campo_santa_tereza.csv")
    for f in (fig_profundidade_v(dados), fig_cota_agua_v_rtk(dados), fig_borda_h(dados),
              fig_colunas_originais(Path(sys.argv[1])), fig_erro_celular_rtk_v(dados)):
        print(f)
