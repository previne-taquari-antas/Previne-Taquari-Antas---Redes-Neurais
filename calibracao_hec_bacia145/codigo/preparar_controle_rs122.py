"""Partição geográfica candidata de SB_211/R_211 no posto RS-122.

Não altera a bacia HEC, chuva, parâmetros ou observações. Usa os rasters D8
originais Whitebox (não ESRI), sem fração de comprimento como fração de área.
Saída diagnóstica exige revisão antes da integração no modelo.
"""
import argparse
import hashlib
import json
import math
import importlib.metadata
from collections import deque
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.windows import Window, from_bounds
from pyproj import Transformer
from shapely.geometry import shape, mapping, LineString
from shapely.ops import transform, unary_union

OFFSETS = {1: (-1, 1), 2: (0, 1), 4: (1, 1), 8: (1, 0),
           16: (1, -1), 32: (0, -1), 64: (-1, -1), 128: (-1, 0)}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def montante_restrita(pointer, allowed, seed):
    if not allowed[seed]:
        raise ValueError("Ponto fora da sub-bacia original")
    seen = np.zeros(allowed.shape, dtype=bool)
    seen[seed] = True
    todo = deque([seed])
    h, w = allowed.shape
    while todo:
        r, c = todo.popleft()
        for code, (dr, dc) in OFFSETS.items():
            nr, nc = r - dr, c - dc
            if 0 <= nr < h and 0 <= nc < w and allowed[nr, nc] and not seen[nr, nc] and pointer[nr, nc] == code:
                seen[nr, nc] = True
                todo.append((nr, nc))
    return seen


def caminho(pointer, links, accum, rid):
    cells = np.argwhere(links == rid)
    if not len(cells):
        raise ValueError("Trecho ausente")
    start = tuple(cells[np.argmin(accum[links == rid])])
    path, seen = [], set()
    r, c = start
    while 0 <= r < links.shape[0] and 0 <= c < links.shape[1] and links[r, c] == rid:
        if (r, c) in seen:
            raise ValueError("Ciclo D8")
        seen.add((r, c))
        path.append((r, c))
        code = int(pointer[r, c])
        if code not in OFFSETS:
            raise ValueError("Ponteiro D8 inválido no trecho")
        dr, dc = OFFSETS[code]
        r, c = r + dr, c + dc
    if len(path) != len(cells):
        raise ValueError("Trecho descontínuo ou ramificado")
    return path


def poligono(mask, affine):
    geoms = [shape(g) for g, value in shapes(mask.astype("uint8"), mask=mask, transform=affine) if value == 1]
    return unary_union(geoms)


def incluir_conexao_final(path, pointer, links, downstream):
    """R original termina no centro da primeira célula do link seguinte."""
    r, c = path[-1]
    dr, dc = OFFSETS[int(pointer[r, c])]
    target = (r + dr, c + dc)
    if not (0 <= target[0] < links.shape[0] and 0 <= target[1] < links.shape[1]):
        raise ValueError("Conexão final fora do recorte")
    if links[target] != downstream:
        raise ValueError("Link de jusante diferente da topologia esperada")
    return path + [target]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace-original", type=Path, required=True)
    ap.add_argument("--inventario", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    a = ap.parse_args()
    if a.saida.exists():
        raise ValueError("Saída deve ser nova; preservar tentativas anteriores")
    topo = a.workspace_original / "topologia_bacia_taquari_antas_contexto_corrigido_20260920"
    modelo = a.workspace_original / "modelo_bacia_taquari_antas_reconstruido_20260920"
    subfile = modelo / "subbacias_taquari_antas_145.geojson"
    reachfile = modelo / "trechos_taquari_antas_105.geojson"
    reach_original = next(f for f in json.loads(reachfile.read_text(encoding="utf-8"))["features"]
                          if f["properties"]["reach_id"] == "R_211")
    subs = json.loads(subfile.read_text(encoding="utf-8"))["features"]
    parent = next(f for f in subs if f["properties"]["sub_id"] == "SB_211")
    label = parent["properties"]["raster_label"]
    station = next(s for s in json.loads(a.inventario.read_text(encoding="utf-8")) if s["cod"] == "86298000")
    to_utm = Transformer.from_crs(4326, 31982, always_xy=True).transform
    to_ll = Transformer.from_crs(31982, 4326, always_xy=True).transform
    parent_geo = transform(to_utm, shape(parent["geometry"]))
    x, y = to_utm(float(station["lon"]), float(station["lat"]))
    inputs = {"sub": topo / "subbasins_t150000.tif", "link": topo / "links_t150000.tif",
              "d8": topo / "d8_pointer.tif", "acc": topo / "d8_accumulation_cells.tif",
              "dem": topo / "dem_contexto_utm22s_30m.tif"}
    arrays, grid = {}, None
    for key, path in inputs.items():
        with rasterio.open(path) as src:
            signature = (src.crs, src.transform, src.width, src.height)
            if grid is None:
                grid = signature
                if src.crs.to_epsg() != 31982 or src.res != (30, 30):
                    raise ValueError("CRS/resolução inesperados")
                b = parent_geo.buffer(90).bounds
                raw = from_bounds(*b, src.transform)
                r0, c0 = math.floor(raw.row_off), math.floor(raw.col_off)
                window = Window(c0, r0, math.ceil(raw.col_off + raw.width) - c0, math.ceil(raw.row_off + raw.height) - r0)
                affine = src.window_transform(window)
            elif grid != signature:
                raise ValueError("Rasters com grades diferentes")
            arrays[key] = src.read(1, window=window)
    mask = arrays["sub"] == label
    parent_raster = poligono(mask, affine)
    # Sem recorte ou tolerância percentual arbitrária: limite absoluto de um pixel.
    symmetric_area = parent_raster.symmetric_difference(parent_geo).area
    if symmetric_area > 900:
        raise ValueError(f"Raster e polígono da sub-bacia diferem: {symmetric_area} m²")
    path = caminho(arrays["d8"], arrays["link"], arrays["acc"], 211)
    xy = [rasterio.transform.xy(affine, r, c) for r, c in path]
    distances = [math.hypot(px - x, py - y) for px, py in xy]
    i = int(np.argmin(distances))
    if distances[i] > 150 or i == 0 or i == len(path) - 1:
        raise ValueError("Snap distante ou no extremo: revisar georreferenciamento")
    seed = path[i]
    upper = montante_restrita(arrays["d8"], mask, seed)
    lower = mask & ~upper
    whole = montante_restrita(arrays["d8"], mask, path[-1])
    if not np.array_equal(whole, mask):
        raise ValueError("Há células da sub-bacia que não drenam ao fim do trecho")
    if not upper.any() or not lower.any() or np.any(upper & lower) or not np.array_equal(upper | lower, mask):
        raise ValueError("Partição inválida")
    cellarea = abs(affine.a * affine.e - affine.b * affine.d)
    snap_sensitivity = []
    for j in range(max(0, i - 2), min(len(path), i + 3)):
        local = montante_restrita(arrays["d8"], mask, path[j])
        snap_sensitivity.append({"offset_cells": j - i, "distance_station_m": distances[j],
                                 "area_local_km2": int(local.sum()) * cellarea / 1e6})
    polys = [poligono(m, affine) for m in (upper, lower)]
    complete = incluir_conexao_final(path, arrays["d8"], arrays["link"], 205)
    complete_xy = [rasterio.transform.xy(affine, r, c) for r, c in complete]
    reaches = [LineString(complete_xy[:i + 1]), LineString(complete_xy[i:])]
    original_line = transform(to_utm, shape(reach_original["geometry"]))
    combined_line = LineString(complete_xy)
    length_error = abs(sum(r.length for r in reaches) - original_line.length)
    hausdorff = combined_line.hausdorff_distance(original_line)
    if length_error > 0.01 or hausdorff > 0.01:
        raise ValueError(f"Partição não recompõe R original: comprimento={length_error}, Hausdorff={hausdorff}")
    features = []
    for name, poly, m in zip(("SB_211_UP", "SB_211_DOWN"), polys, (upper, lower)):
        z = arrays["dem"][m]
        if not np.all(np.isfinite(z) & (z > -30000)):
            raise ValueError("MDT incompleto na partição")
        features.append({"type": "Feature", "properties": {"id": name, "area_km2": int(m.sum()) * cellarea / 1e6,
                         "centroid_lonlat": list(to_ll(poly.centroid.x, poly.centroid.y)),
                         "elev_p10_m": float(np.percentile(z, 10)), "elev_p90_m": float(np.percentile(z, 90))},
                         "geometry": mapping(transform(to_ll, poly))})
    for name, line in zip(("R_211_UP", "R_211_DOWN"), reaches):
        features.append({"type": "Feature", "properties": {"id": name, "length_m": line.length},
                         "geometry": mapping(transform(to_ll, line))})
    out = {"status": "particao_geografica_candidata_nao_integrada", "posto": station,
           "crs_analise": "EPSG:31982", "resolucao_m": 30, "d8": "Whitebox não ESRI",
           "crs_coordenada_posto": "EPSG:4326 assumido; datum não declarado no inventário local",
           "snap_m": distances[i], "snap_lonlat": list(to_ll(*xy[i])),
           "row_col_global": [int(seed[0] + window.row_off), int(seed[1] + window.col_off)],
           "area_raster_parent_km2": int(mask.sum()) * cellarea / 1e6,
           "area_geo_parent_km2": parent_geo.area / 1e6,
           "diferenca_simetrica_parent_m2": symmetric_area,
           "area_local_antes_posto_km2": int(upper.sum()) * cellarea / 1e6,
           "area_local_depois_posto_km2": int(lower.sum()) * cellarea / 1e6,
           "area_acumulada_snap_km2": float(arrays["acc"][seed]) * cellarea / 1e6,
           "comprimento_antes_m": reaches[0].length, "comprimento_depois_m": reaches[1].length,
           "comprimento_original_m": original_line.length, "erro_fechamento_comprimento_m": length_error,
           "hausdorff_trecho_original_m": hausdorff,
           "sensibilidade_snap_vizinhos_nao_otimizada": snap_sensitivity,
           "runtime": {k: importlib.metadata.version(k) for k in ("numpy", "rasterio", "shapely", "pyproj")},
           "checks": {"grade_identica": True, "area_particionada_sem_perda": True, "disjuncao": True,
                      "toda_SB_drena_ao_outlet": True, "caminho_unico": True,
                      "comprimento_e_geometria_recompostos": True},
           "fontes": {k: {"path": str(p), "sha256": sha(p)} for k, p in
                      {**inputs, "sub_geo": subfile, "reach_geo": reachfile,
                       "inventario": a.inventario, "codigo": Path(__file__)}.items()},
           "limites": ["Divisão geográfica não aprova chuva, parâmetros nem vazão observada",
                       "Recomputar chuva e parâmetros antes da execução HEC", "Controle não integrado; não é recalibração",
                       "Datum cadastral do posto pendente; snap não substitui levantamento da seção"]}
    a.saida.mkdir(parents=True)
    (a.saida / "particao.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    (a.saida / "manifesto.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "fontes"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
