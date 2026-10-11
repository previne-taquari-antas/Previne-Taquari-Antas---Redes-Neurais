"""Compara conectividade ao controle RS122 no HEC e no D8, sem editar a rede.

Traça o caminho a partir do pixel de maior acumulação de cada unidade raster.
É auditoria da saída de cada unidade, não prova célula a célula de toda a área.
Unidade SB_211 recebe tratamento parcial explícito do manifesto geográfico.
"""
import argparse
import json
import math
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window, from_bounds
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

from preparar_controle_rs122 import OFFSETS, sha


def area_pixel_km2(src):
    """Este diagnóstico exige a grade UTM 22S, norte-acima, de 30 m."""
    t = src.transform
    if src.crs is None or src.crs.to_epsg() != 31982:
        raise ValueError("CRS esperado: EPSG:31982, métrico")
    if not all(math.isclose(x, y, abs_tol=1e-9, rel_tol=0)
               for x, y in zip((t.a, t.b, t.d, t.e), (30, 0, 0, -30))):
        raise ValueError("Grade esperada: 30 m, norte-acima, sem rotação")
    return abs(t.a * t.e - t.b * t.d) / 1e6


def grafo_basin(text):
    down, area = {}, {}
    for m in re.finditer(r"(?ms)^(Subbasin|Reach|Junction|Sink): ([^\n]+)\n(.*?)^End:", text):
        name = m[2].strip()
        d = re.search(r"(?m)^\s*Downstream:\s*([^\n]+)", m[3])
        down[name] = d[1].strip() if d else None
        if m[1] == "Subbasin":
            area[name] = float(re.search(r"(?m)^\s*Area:\s*([^\n]+)", m[3])[1])
    return down, area


def drena_grafo(n, down, targets):
    seen = set()
    while n:
        if n in targets:
            return True
        if n in seen:
            raise ValueError("Ciclo no basin")
        seen.add(n)
        n = down[n]
    return False


class RasterPath:
    def __init__(self, src, target):
        self.src = src
        self.memo = {target: True}

    @lru_cache(maxsize=128)
    def block(self, br, bc):
        return self.src.read(1, window=Window(bc * 256, br * 256,
                             min(256, self.src.width - bc * 256), min(256, self.src.height - br * 256)))

    def drena(self, seed):
        path, seen = [], set()
        pos = seed
        while pos not in self.memo:
            r, c = pos
            if not (0 <= r < self.src.height and 0 <= c < self.src.width):
                result = False
                break
            if pos in seen:
                raise ValueError("Ciclo D8")
            seen.add(pos)
            path.append(pos)
            code = int(self.block(r // 256, c // 256)[r % 256, c % 256])
            if code not in OFFSETS:
                if code not in (0, self.src.nodata):
                    raise ValueError(f"D8 desconhecido {code}")
                result = False
                break
            dr, dc = OFFSETS[code]
            pos = (r + dr, c + dc)
        else:
            result = self.memo[pos]
        for p in path:
            self.memo[p] = result
        return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--basin", type=Path, required=True)
    ap.add_argument("--particao", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    a = ap.parse_args()
    if a.saida.exists():
        raise ValueError("Preservar saída anterior")
    m = json.loads(a.particao.read_text(encoding="utf-8"))
    for k in ("sub", "acc", "d8"):
        assert sha(Path(m["fontes"][k]["path"])) == m["fontes"][k]["sha256"]
    sub_geo = Path(m["fontes"]["sub_geo"]["path"])
    assert sha(sub_geo) == m["fontes"]["sub_geo"]["sha256"]
    features = json.loads(sub_geo.read_text(encoding="utf-8"))["features"]
    to_utm = Transformer.from_crs(4326, 31982, always_xy=True).transform
    down, areas = grafo_basin(a.basin.read_text(encoding="utf-8"))
    rows = []
    with rasterio.open(m["fontes"]["sub"]["path"]) as sub, rasterio.open(m["fontes"]["acc"]["path"]) as acc, \
            rasterio.open(m["fontes"]["d8"]["path"]) as d8:
        signatures = {(s.crs, s.transform, s.width, s.height) for s in (sub, acc, d8)}
        assert len(signatures) == 1
        pixel_km2 = area_pixel_km2(sub)
        tracer = RasterPath(d8, tuple(m["row_col_global"]))
        for f in features:
            p = f["properties"]
            if p["sub_id"] == "SB_211":
                continue
            geom = transform(to_utm, shape(f["geometry"]))
            raw = from_bounds(*geom.buffer(60).bounds, sub.transform)
            r0, c0 = math.floor(raw.row_off), math.floor(raw.col_off)
            win = Window(c0, r0, math.ceil(raw.col_off + raw.width) - c0, math.ceil(raw.row_off + raw.height) - r0)
            labels, flow = sub.read(1, window=win), acc.read(1, window=win)
            mask = labels == p["raster_label"]
            if not mask.any():
                raise ValueError("Rótulo ausente: " + p["sub_id"])
            cells = np.argwhere(mask)
            local = cells[np.argmax(flow[mask])]
            seed = (int(local[0] + win.row_off), int(local[1] + win.col_off))
            via_d8 = tracer.drena(seed)
            via_hec = drena_grafo(p["sub_id"], down, {"J_222", "J_089"})
            rows.append({"sub_id": p["sub_id"], "outlet_raster": list(seed), "hec": via_hec,
                         "d8": via_d8, "hec_downstream": down[p["sub_id"]], "link_original": p["link_id"],
                         "area_hec_km2": areas[p["sub_id"]], "area_geo_km2": p["area_km2"],
                         "area_raster_km2": p["area_pixel_km2"]})
        # Reconciliar também rótulos presentes no raster de contexto mas ausentes
        # dos 145 polígonos recortados. Não converter área bruta em área oficial.
        counts, maxima, seeds = {}, {}, {}
        for r0 in range(0, sub.height, 512):
            win = Window(0, r0, sub.width, min(512, sub.height - r0))
            labels, flow = sub.read(1, window=win), acc.read(1, window=win)
            valid = (labels > 0) & (labels != sub.nodata)
            ids, nums = np.unique(labels[valid], return_counts=True)
            for label, n in zip(ids, nums):
                label = int(label)
                counts[label] = counts.get(label, 0) + int(n)
                positions = np.flatnonzero(labels == label)
                index = positions[np.argmax(flow.ravel()[positions])]
                peak = float(flow.ravel()[index])
                if peak > maxima.get(label, -1):
                    maxima[label] = peak
                    r, c = np.unravel_index(index, labels.shape)
                    seeds[label] = (int(r + r0), int(c))
        all_labels = []
        known = {int(f["properties"]["raster_label"]) for f in features}
        for label, count in sorted(counts.items()):
            if label == 211:
                continue
            all_labels.append({"label": label, "cells": count, "area_km2": count * pixel_km2,
                               "drena_posto": tracer.drena(seeds[label]), "presente_145": label in known})
    diffs = [r for r in rows if r["hec"] != r["d8"]]
    local = m["area_local_antes_posto_km2"]
    summary = {"n_unidades": len(rows), "n_divergentes": len(diffs),
               "area_grafo_mais_parcela_km2": sum(r["area_hec_km2"] for r in rows if r["hec"]) + local,
               "area_geo_d8_mais_parcela_km2": sum(r["area_geo_km2"] for r in rows if r["d8"]) + local,
               "area_raster_d8_mais_parcela_km2": sum(r["area_raster_km2"] for r in rows if r["d8"]) + local,
               "area_acumulacao_d8_km2": m["area_acumulada_snap_km2"]}
    total_raw = sum(r["area_km2"] for r in all_labels if r["drena_posto"]) + local
    summary["area_rotulos_raster_completo_mais_parcela_km2"] = total_raw
    summary["erro_fechamento_rotulos_vs_acc_km2"] = total_raw - m["area_acumulada_snap_km2"]
    out = {"status": "auditoria_outlets_nao_correcao", "resumo": summary, "divergencias": diffs, "unidades": rows,
           "rotulos_contexto": all_labels,
           "basin_sha256": sha(a.basin), "particao_sha256": sha(a.particao), "codigo_sha256": sha(Path(__file__)),
           "limites": ["Caminho do outlet representativo, não classificação de todo pixel recortado",
                       "Não corrige conectividade ou recalibra", "Áreas cadastradas, recortadas e raster não são intercambiáveis"]}
    a.saida.parent.mkdir(parents=True, exist_ok=True)
    a.saida.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"resumo": summary, "divergencias": diffs}, ensure_ascii=False))


if __name__ == "__main__":
    main()
