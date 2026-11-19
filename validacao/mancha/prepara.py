"""Para cada lugar: referência (união dos polígonos), zona de comparação e área de interesse em GeoJSON (prep/).
Referências do Copernicus EMS: baixe os produtos (ver README) em z/<pasta de sites.json>."""
import glob
import json
import os
import sys

from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

base = os.path.dirname(os.path.abspath(__file__))
sites = json.load(open(os.path.join(base, "sites.json")))
out = os.path.join(base, "prep")
os.makedirs(out, exist_ok=True)


def le(arq):
    g = json.load(open(arq))
    return [shape(f["geometry"]).buffer(0) for f in g["features"] if f.get("geometry")]


for s in sites:
    if s.get("ref_geojson"):
        ref = unary_union(le(os.path.join(base, s["ref_geojson"])))
        aoi = box(*s["janela"]) if s.get("janela") else ref.envelope.buffer(0.004)
    else:
        d = os.path.join(base, "z", s["dir"])
        obs = [f for f in glob.glob(d + "/*observedEventA*.json")] or [f for f in glob.glob(d + "/*floodDepthA*.json")]
        ref = unary_union(le(obs[0]))
        aoi = unary_union(le(glob.glob(d + "/*areaOfInterestA*.json")[0]))
    if s.get("janela"):
        jan = box(*s["janela"])
    else:
        w, so, e, n = ref.bounds
        jan = box(w - 0.004, so - 0.004, e + 0.004, n + 0.004)
    zona = jan.intersection(aoi)
    refz = ref.intersection(zona)
    json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"nome": s["nome"]}, "geometry": mapping(zona.envelope)}]}, open(os.path.join(out, s["slug"] + "_area.geojson"), "w"))
    json.dump({"zona": mapping(zona), "ref": mapping(refz)}, open(os.path.join(out, s["slug"] + "_ref.json"), "w"))
    import math
    lat = (zona.bounds[1] + zona.bounds[3]) / 2
    k = 111.32 * math.cos(math.radians(lat)) * 110.57
    print(f'{s["slug"]:14s} zona {zona.area * k:6.1f} km²  observado {refz.area * k:6.1f} km²  ({100 * refz.area / zona.area:4.1f}%)')
