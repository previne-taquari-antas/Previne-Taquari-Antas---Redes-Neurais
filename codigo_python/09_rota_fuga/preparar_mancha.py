# -*- coding: utf-8 -*-
"""Converte a mancha de uma área insegura (shapefile, GeoPackage, KML ou GeoJSON, em qualquer
sistema de coordenadas) no GeoJSON WGS84 recortado por cidade que pontos_encontro.py lê.

Feito para a Área Diretamente Atingida do Mapa Único do Plano Rio Grande (MUP RS) e, depois,
para o perigo hidrológico do projeto. Junta todos os polígonos do arquivo (alagamento,
inundação, enxurrada e deslizamento contam como área atingida) e recorta a caixa da rede de
ruas da cidade com 3 km de folga. Os atributos não vão para a saída; o arquivo de origem
fica registrado no "properties" (nome e sha256).

Precisa de pyogrio e pyproj (não estão no CI; só quem converte):
  pip install pyogrio pyproj
  python codigo_python/09_rota_fuga/preparar_mancha.py ~/Downloads/mup_rs_ada.shp
  python codigo_python/09_rota_fuga/preparar_mancha.py perigo.gpkg --camada perigo_alto --saida-prefixo perigo_hidrologico
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np
import shapely
from shapely.geometry import box, mapping
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locais_altos  # noqa: E402
import pontos_encontro as pe  # noqa: E402

FOLGA_RECORTE_M = 3000.0
SIMPLIFICA_M = 1.0


def le_arquivo(caminho, camada=None):
    import pyogrio
    from pyproj import CRS, Transformer
    info = pyogrio.read_info(caminho, layer=camada)
    _meta, _fids, geoms, _campos = pyogrio.raw.read(caminho, layer=camada, read_geometry=True, columns=[])
    gs = [shapely.from_wkb(g) for g in geoms if g is not None]
    crs = info.get("crs")
    if crs and not CRS.from_user_input(crs).equals(CRS.from_epsg(4326)):
        tr = Transformer.from_crs(CRS.from_user_input(crs), CRS.from_epsg(4326), always_xy=True)
        gs = [shapely.transform(g, lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1]))) for g in gs]
    elif not crs:
        print("aviso: arquivo sem sistema de coordenadas; supondo lon/lat (WGS84 ou SIRGAS 2000 geográfico)")
    gs = [g.buffer(0) for g in gs if g.geom_type in ("Polygon", "MultiPolygon")]
    if not gs:
        raise SystemExit(f"{caminho}: nenhum polígono")
    return gs, crs


def recorta(gs, cidade):
    doc = locais_altos.payload(pe.CIDADES[cidade]["painel"])
    plano = pe.Plano(doc["nos"])
    xs, ys = zip(*(plano.xy(la, lo) for la, lo in doc["nos"]))
    caixa = box(min(xs) - FOLGA_RECORTE_M, min(ys) - FOLGA_RECORTE_M, max(xs) + FOLGA_RECORTE_M, max(ys) + FOLGA_RECORTE_M)
    m = unary_union([plano.de_lonlat(g) for g in gs]).intersection(caixa)
    return None if m.is_empty else plano.para_lonlat(m.simplify(SIMPLIFICA_M, preserve_topology=True))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("arquivo")
    ap.add_argument("--camada", help="camada do GeoPackage/KML (padrão: a primeira)")
    ap.add_argument("--cidades", nargs="+", default=sorted(pe.CIDADES), choices=sorted(pe.CIDADES))
    ap.add_argument("--saida-prefixo", default="mup_rs_ada",
                    help="arquivo de saída: assets/data/rota_fuga/<prefixo>_<cidade>.geojson")
    a = ap.parse_args()
    gs, crs = le_arquivo(a.arquivo, a.camada)
    with open(a.arquivo, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    for cidade in a.cidades:
        m = recorta(gs, cidade)
        if m is None:
            print(f"{cidade}: a mancha não chega perto da rede de ruas; nada gravado")
            continue
        saida = os.path.join(pe.DADOS, f"{a.saida_prefixo}_{cidade}.geojson")
        fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": mapping(m), "properties": {
            "origem": os.path.basename(a.arquivo), "origem_sha256": sha, "origem_crs": str(crs) if crs else None,
            "recorte": f"rede de ruas de {pe.CIDADES[cidade]['municipio']} ± {FOLGA_RECORTE_M:g} m"}}]}
        with open(saida, "w", encoding="utf-8") as f:
            json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{cidade}: {os.path.relpath(saida, pe.RAIZ)} ({os.path.getsize(saida) / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
