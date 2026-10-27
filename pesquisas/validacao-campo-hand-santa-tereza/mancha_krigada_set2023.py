#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mancha de set/2023 do HAND krigado (INUND_HAND_2165) e distância dos limites H à borda.

INUND_HAND_2165 = LiDAR 1 m − (cota do rio krigada + 21,65 m) (ver metadados_hand_krigado.json).
Para o pico de set/2023 (régua 23,65 m):

  z0 = 1,60 m → limiar HAND 22,05 m → inundado onde INUND_HAND_2165 < 0,40 m
  z0 = 2,00 m → limiar HAND 21,65 m → inundado onde INUND_HAND_2165 < 0

Só entram as células ligadas (8-vizinhos) ao rio principal (arcos de
STREAM_TAQUARI_ANTAS rasterizados), numa janela 2 km maior que a do mapa, e o
resultado é recortado na área do mapa da fig_v7_1_mapa (envelope dos pontos RTK
válidos e da estação 86472600, com folga de 0,0032°, como em figuras_manuscrito.py).

Para cada limite H com RTK válido calcula a distância à borda de cada mancha
(polígono em 1 m, sem simplificar), com sinal: + fora da mancha (a mancha não
chega ao limite observado), − dentro (a mancha passa do limite). Compara |d| com
erro_h_rtk_m do erros_campo_santa_tereza.csv (métricas só com os limites de set/2023).

Saídas (sem coordenadas de pontos de campo):
  mancha_krigada_set2023_z160.geojson, mancha_krigada_set2023_z200.geojson
      (polígonos de área inundável em EPSG:4326, simplificados a 0,5 m; atributos só de z0/área)
  distancias_borda_krigada.csv, distancias_borda_krigada_resumo.json

Uso:
  python pesquisas/validacao-campo-hand-santa-tereza/mancha_krigada_set2023.py \
      caminho/sumario_erros_hand.xlsx [--fapergs-dir "D:\\PREVINE\\FAPERGS"]
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import rasterio
import shapefile  # pyshp
from pyproj import Transformer
from rasterio.features import rasterize, shapes
from rasterio.windows import Window, from_bounds
from scipy import ndimage
from shapely.geometry import LineString, Point, box, mapping, shape
from shapely.ops import transform as shp_transform, unary_union

HERE = Path(__file__).resolve().parent
PICO_SET23 = 23.65
OFFSET_KRIG = 21.65
Z0 = {"z160": 1.60, "z200": 2.00}
PAD_GRAUS = 0.0032
GAUGE_LONLAT = (-51.7322, -29.1781)
FOLGA_M = 2000.0
SIMPLIFICA_M = 0.5


def carregar(nome, caminho):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def r3(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("planilha", type=Path)
    ap.add_argument("--fapergs-dir", type=Path, default=Path(r"D:\PREVINE\FAPERGS"))
    args = ap.parse_args()

    analise = carregar("analise_erros_campo", HERE / "analise_erros_campo.py")
    rtk, _ = analise.ler_planilha(args.planilha)
    d = list(csv.DictReader((HERE / "erros_campo_santa_tereza.csv").open(encoding="utf-8")))
    validos = [r for r in d if r["rtk_valido"] == "True"]
    ids = sorted({r["id"] for r in validos})
    pos = {i: (rtk[analise.RTK_ALIAS.get(i, i)]["E"], rtk[analise.RTK_ALIAS.get(i, i)]["N"]) for i in ids}

    # área do mapa (mesma regra de figuras_manuscrito._desenha_mapa), em EPSG:4674 → UTM
    to_geo = Transformer.from_crs("EPSG:31982", "EPSG:4674", always_xy=True)
    to_utm = Transformer.from_crs("EPSG:4674", "EPSG:31982", always_xy=True)
    lons = [to_geo.transform(*pos[i])[0] for i in ids] + [GAUGE_LONLAT[0]]
    lats = [to_geo.transform(*pos[i])[1] for i in ids] + [GAUGE_LONLAT[1]]
    W, E, S, N = min(lons) - PAD_GRAUS, max(lons) + PAD_GRAUS, min(lats) - PAD_GRAUS, max(lats) + PAD_GRAUS
    mapa_geo = box(W, S, E, N)
    mapa_utm = shp_transform(lambda x, y, z=None: to_utm.transform(x, y), mapa_geo.segmentize(0.0005))

    inund_path = args.fapergs_dir / "INUND_HAND_2165.tif"
    with rasterio.open(inund_path) as ds:
        x0, y0, x1, y1 = mapa_utm.bounds
        win = from_bounds(x0 - FOLGA_M, y0 - FOLGA_M, x1 + FOLGA_M, y1 + FOLGA_M, ds.transform)
        win = win.round_offsets().round_lengths().intersection(Window(0, 0, ds.width, ds.height))
        inund = ds.read(1, window=win, masked=True).filled(np.nan).astype("float32")
        T = ds.window_transform(win)
        crs = ds.crs

    sf = shapefile.Reader(str(args.fapergs_dir / "STREAM_TAQUARI_ANTAS.shp"))
    rio_geoms = [LineString(s.points) for s in sf.shapes() if len(s.points) > 1]
    rio = rasterize(((g, 1) for g in rio_geoms), out_shape=inund.shape, transform=T,
                    all_touched=True, dtype="uint8").astype(bool)

    conn8 = np.ones((3, 3), dtype=bool)
    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    manchas, resumo = {}, {"area_mapa_graus": [round(v, 6) for v in (W, S, E, N)],
                           "celulas_rio_na_janela": int(rio.sum())}
    for tag, z0 in Z0.items():
        lim_inund = (PICO_SET23 - z0) - OFFSET_KRIG  # 0,40 ou 0,00
        cand = np.isfinite(inund) & (inund < lim_inund)
        lab, _ = ndimage.label(cand, structure=conn8)
        toca = np.unique(lab[rio & cand])
        mask = np.isin(lab, toca[toca != 0])
        polys = [shape(g) for g, v in shapes(mask.astype("uint8"), mask=mask, transform=T, connectivity=8) if v]
        geom = unary_union(polys).intersection(mapa_utm)
        manchas[tag] = geom
        geo_out = shp_transform(lambda x, y, z=None: to_wgs.transform(x, y),
                                geom.simplify(SIMPLIFICA_M, preserve_topology=True))
        fc = {"type": "FeatureCollection",
              "features": [{"type": "Feature",
                            "properties": {"evento": "2023-09", "pico_regua_m": PICO_SET23, "z0_m": z0,
                                           "limiar_hand_m": round(PICO_SET23 - z0, 2),
                                           "regra": f"INUND_HAND_2165 < {lim_inund:.2f} m, ligado ao rio principal",
                                           "area_ha": round(geom.area / 1e4, 2)},
                            "geometry": mapping(geo_out)}],
              "metadata": {"fonte": "INUND_HAND_2165.tif (HAND krigado, LiDAR RS 1 m)",
                           "rio_principal": "STREAM_TAQUARI_ANTAS (20 arcos), conectividade 8-vizinhos",
                           "recorte": "área do mapa fig_v7_1_mapa", "crs": "EPSG:4326",
                           "simplificacao_m": SIMPLIFICA_M}}
        out = HERE / f"mancha_krigada_set2023_{tag}.geojson"
        out.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        resumo[tag] = {"limiar_inund_m": lim_inund, "area_ha": round(geom.area / 1e4, 2)}

    linhas = []
    for r in validos:
        if r["tipo"] != "limite":
            continue
        p = Point(pos[r["id"]])
        lin = {"id": r["id"], "evento": r["evento"],
               "nota": "" if r["evento"] == "2023-09" else "limite de outro evento; mancha de set/2023 não se aplica", "erro_h_rtk_m": r3(float(r["erro_h_rtk_m"])),
               "erro_h_cel_m": r3(float(r["erro_h_cel_m"])), "e_s_m": r3(float(r["erro_cota_rtk_m"]))}
        for tag, g in manchas.items():
            dist = g.boundary.distance(p)
            sinal = -1.0 if g.contains(p) else 1.0
            lin[f"dist_borda_{tag}_m"] = r3(sinal * dist)
            lin[f"dif_abs_{tag}_m"] = r3(abs(dist) - float(r["erro_h_rtk_m"]))
        linhas.append(lin)
    with (HERE / "distancias_borda_krigada.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)

    # as manchas são de set/2023: as métricas usam só os limites desse evento
    set23 = [l for l in linhas if l["evento"] == "2023-09"]
    resumo["fora_das_metricas"] = [l["id"] + " (" + l["evento"] + ")" for l in linhas if l["evento"] != "2023-09"]
    plan = np.array([l["erro_h_rtk_m"] for l in set23])
    for tag in Z0:
        dd = np.array([l[f"dist_borda_{tag}_m"] for l in set23])
        a = np.abs(dd)
        resumo[tag].update({
            "n": len(set23),
            "max_abs_d_menos_planilha_m": r3(np.max(np.abs(a - plan))),
            "mae_abs_d_menos_planilha_m": r3(np.mean(np.abs(a - plan))),
            "mediana_abs_d_menos_planilha_m": r3(np.median(np.abs(a - plan))),
            "n_dif_le_0_5m": int(np.sum(np.abs(a - plan) <= 0.5)),
            "spearman_abs_d_vs_planilha": r3(_spearman(a, plan)),
            "n_dentro": int(np.sum(dd < 0)), "n_fora": int(np.sum(dd > 0)),
        })
    (HERE / "distancias_borda_krigada_resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


def _spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


if __name__ == "__main__":
    main()
