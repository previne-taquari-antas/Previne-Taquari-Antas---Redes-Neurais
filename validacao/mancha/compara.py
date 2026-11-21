"""Compara a mancha gerada pela página com a inundação observada, dentro da zona de comparação."""
import glob
import json
import math
import os
import re

from shapely.geometry import shape
from shapely.ops import unary_union

base = os.path.dirname(os.path.abspath(__file__))
prep = os.path.join(base, "prep")
saida = os.path.join(base, os.environ.get("SAIDA", "prep"))
sites = json.load(open(os.path.join(base, "sites.json")))
linhas = []
for s in sites:
    r = json.load(open(os.path.join(prep, s["slug"] + "_ref.json")))
    zona, ref = shape(r["zona"]), shape(r["ref"])
    res = []
    for f in sorted(glob.glob(os.path.join(saida, s["slug"] + "_[0-9]*.json"))):
        m = re.search(r"_(\d+)\.json$", f)
        if not m:
            continue
        nivel = int(m.group(1))
        g = json.load(open(f))
        auto = unary_union([shape(x["geometry"]) for x in g["features"]]).intersection(zona)
        inter = auto.intersection(ref).area
        uni = auto.union(ref).area
        res.append({
            "nivel": nivel,
            "coincidencia": 100 * inter / uni if uni else 0,  # interseção sobre união
            "acerto": 100 * inter / ref.area if ref.area else 0,  # quanto do observado a mancha pegou
            "sobra": 100 * (auto.area - inter) / auto.area if auto.area else 0,  # quanto da mancha não foi observado
            "auto_pct": 100 * auto.area / zona.area,
        })
    res.sort(key=lambda x: x["nivel"])
    if not res:
        print(s["slug"], "sem manchas")
        continue
    melhor = max(res, key=lambda x: x["coincidencia"])
    print(f'\n{s["nome"]}  (observado = {100 * ref.area / zona.area:.1f}% da zona)')
    for x in res:
        marca = "  <- melhor" if x is melhor else ""
        print(f'  rio +{x["nivel"]:>2} m: coincidência {x["coincidencia"]:5.1f}%  pegou {x["acerto"]:5.1f}% do observado  sobra {x["sobra"]:5.1f}%  mancha {x["auto_pct"]:5.1f}% da zona{marca}')
    linhas.append({"lugar": s["nome"], "tipo": s["tipo"], **{k: round(v, 1) for k, v in melhor.items()}, "niveis": res})
json.dump(linhas, open(os.path.join(saida, "resultado.json"), "w"), ensure_ascii=False, indent=1)
print("\nResumo (melhor nível de cada lugar):")
for l in linhas:
    print(f'  {l["lugar"]:45s} {l["tipo"]:10s} rio +{l["nivel"]:>2} m  coincidência {l["coincidencia"]:5.1f}%  pegou {l["acerto"]:5.1f}%  sobra {l["sobra"]:5.1f}%')
