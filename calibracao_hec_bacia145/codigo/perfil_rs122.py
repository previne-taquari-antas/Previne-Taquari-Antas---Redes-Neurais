"""Perfis de superfície e relevo da partição RS122; não gera parâmetros HEC.

Compara MDT de delineação e MDT dos atributos atuais, sem suavização ou
preenchimento. A cota raster não é cota de fundo nem declividade de energia.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.windows import from_bounds, Window
from rasterio.features import geometry_mask
from pyproj import Transformer
from shapely.geometry import shape, mapping, box
from shapely.ops import transform

from preparar_controle_rs122 import sha
from auditar_conectividade_rs122 import area_pixel_km2


def estatistica_perfil(xy, z):
    xy, z = np.asarray(xy, dtype=float), np.asarray(z, dtype=float)
    if len(z) < 2 or xy.shape != (len(z), 2) or not np.isfinite(xy).all() or not np.isfinite(z).all():
        raise ValueError("Perfil inválido/incompleto")
    passos = np.sqrt(np.sum(np.diff(xy, axis=0) ** 2, axis=1))
    if np.any(passos <= 0):
        raise ValueError("Vértices repetidos ou distância nula")
    dist = np.r_[0.0, np.cumsum(passos)]
    dz = np.diff(z)
    return {"n_vertices": len(z), "length_m": float(dist[-1]),
            "elev_inicio_m": float(z[0]), "elev_fim_m": float(z[-1]),
            "queda_m": float(z[0] - z[-1]),
            "declividade_superficie_extremos_m_m": float((z[0] - z[-1]) / dist[-1]),
            "segmentos_ascendentes": int(np.sum(dz > 0)),
            "maior_subida_m": float(max(0, np.max(dz))),
            "distancia_m": dist.tolist(), "elevacao_m": z.tolist()}


def amostrar_perfil(src, geom):
    xy = list(geom.coords)
    values = np.ma.array(list(src.sample(xy, masked=True)))[:, 0]
    if np.ma.getmaskarray(values).any() or not np.isfinite(values.data).all():
        raise ValueError("MDT incompleto no perfil: sem preencher")
    return estatistica_perfil(xy, values.data)


def relevo(src, geom):
    # Área coberta é geométrica; contar centros não prova cobertura em outra grade.
    if geom.difference(box(*src.bounds)).area > 1e-4:
        raise ValueError("Cobertura espacial insuficiente do MDT")
    raw = from_bounds(*geom.bounds, src.transform)
    c0, r0 = math.floor(raw.col_off), math.floor(raw.row_off)
    win = Window(c0, r0, math.ceil(raw.col_off + raw.width) - c0, math.ceil(raw.row_off + raw.height) - r0)
    cells = src.read(1, window=win, masked=True)
    touched = geometry_mask([mapping(geom)], transform=src.window_transform(win),
                            out_shape=cells.shape, all_touched=True, invert=True)
    if np.any(touched & (np.ma.getmaskarray(cells) | ~np.isfinite(cells.data))):
        raise ValueError("Cobertura com pixels inválidos: sem preencher")
    band, _ = mask(src, [mapping(geom)], crop=True, filled=False)
    z = band[0].compressed().astype(float)
    if len(z) < 3 or not np.isfinite(z).all():
        raise ValueError("MDT incompleto no polígono")
    p10, p90 = np.percentile(z, [10, 90])
    area = geom.area / 1e6
    return {"n_pixels_centros_no_poligono": len(z), "area_km2": area, "elev_p10_m": float(p10),
            "elev_p90_m": float(p90), "relevo_p90_p10_m": float(p90 - p10),
            "S_proxy_formula_atual": float(min(.15, max(.003, (p90 - p10) / (1.4 * area ** .6 * 1000))))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--particao", type=Path, required=True)
    ap.add_argument("--mdt-atributos", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    a = ap.parse_args()
    if a.saida.exists():
        raise ValueError("Preservar saída anterior")
    manifest_path = a.particao / "manifesto.json"
    geo_path = a.particao / "particao.geojson"
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    geo = json.loads(geo_path.read_text(encoding="utf-8"))
    conv = Transformer.from_crs(4326, 31982, always_xy=True).transform
    geoms = {f["properties"]["id"]: transform(conv, shape(f["geometry"])) for f in geo["features"]}
    required = {"SB_211_UP", "SB_211_DOWN", "R_211_UP", "R_211_DOWN"}
    if set(geoms) != required or len(geo["features"]) != 4:
        raise ValueError("Identidades da partição inválidas")
    up, down = geoms["R_211_UP"], geoms["R_211_DOWN"]
    if math.dist(up.coords[-1], down.coords[0]) > .01:
        raise ValueError("Descontinuidade na junção")
    from shapely.geometry import LineString
    geoms["R_211_PARENT"] = LineString(list(up.coords) + list(down.coords)[1:])
    sources = {"delineacao": Path(m["fontes"]["dem"]["path"]), "atributos": a.mdt_atributos}
    if sha(sources["delineacao"]) != m["fontes"]["dem"]["sha256"]:
        raise ValueError("MDT de delineação mudou")
    result = {}
    for name, path in sources.items():
        with rasterio.open(path) as src:
            area_pixel_km2(src)
            result[name] = {"path": str(path.resolve()), "sha256": sha(path),
                            "crs": str(src.crs), "transform": list(src.transform),
                            "perfis": {k: amostrar_perfil(src, g) for k, g in geoms.items() if k.startswith("R_")},
                            "subbacias": {k: relevo(src, g) for k, g in geoms.items() if k.startswith("SB_")}}
    contrasts = {}
    for key in ("R_211_UP", "R_211_DOWN", "R_211_PARENT"):
        delta = np.asarray(result["atributos"]["perfis"][key]["elevacao_m"]) - np.asarray(result["delineacao"]["perfis"][key]["elevacao_m"])
        contrasts[key] = {"diferenca_media_m": float(delta.mean()), "diferenca_max_abs_m": float(np.max(np.abs(delta)))}
    out = {"status": "perfis_superficie_nao_parametros_hidraulicos", "fontes": result,
           "comparacao_mesmos_vertices": contrasts, "particao_sha256": sha(geo_path),
           "manifesto_sha256": sha(manifest_path), "codigo_sha256": sha(Path(__file__)),
           "limites": ["Cotas raster não são batimetria", "Sem suavizar perfil ou impor declividade positiva",
                       "S_proxy reproduz fórmula atual; não é tempo de concentração recalibrado",
                       "Não altera HEC, chuva ou parâmetros"]}
    a.saida.parent.mkdir(parents=True, exist_ok=True)
    a.saida.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    brief = {name: {k: {a: b for a, b in p.items() if a not in ("distancia_m", "elevacao_m")}
                   for k, p in item["perfis"].items()} for name, item in result.items()}
    print(json.dumps({"perfis": brief, "comparacao": contrasts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
