"""Comparação pelas casas: das edificações do OpenStreetMap na zona, quais a inundação observada atingiu e
quais a mancha da página marcou. Uso: SAIDA=v2 python3 casas.py"""
import glob
import json
import os
import re

from shapely import STRtree
from shapely.geometry import Point, Polygon, shape
from shapely.ops import unary_union

base = os.path.dirname(os.path.abspath(__file__))
prep = os.path.join(base, "prep")
saida = os.path.join(base, os.environ.get("SAIDA", "prep"))
sites = json.load(open(os.path.join(base, "sites.json")))
TOL = 0.00015  # ~15 m: o radar não vê água colada aos prédios


def casas_do(slug, zona):
    nos, pts = {}, {}
    for f in glob.glob(os.path.join(base, "osm", slug + "_*.json")):
        d = json.load(open(f))
        for el in d.get("elements", []):
            if el["type"] == "node":
                nos[el["id"]] = (el["lon"], el["lat"])
        for el in d.get("elements", []):
            if el["type"] == "way" and "building" in el.get("tags", {}):
                c = [nos[i] for i in el.get("nodes", []) if i in nos]
                if len(c) >= 3:
                    x = sum(p[0] for p in c) / len(c)
                    y = sum(p[1] for p in c) / len(c)
                    pts[el["id"]] = Point(x, y)
    return [p for p in pts.values() if zona.contains(p)]


resumo = []
for s in sites:
    r = json.load(open(os.path.join(prep, s["slug"] + "_ref.json")))
    zona, ref = shape(r["zona"]), shape(r["ref"]).buffer(TOL)
    casas = casas_do(s["slug"], zona)
    if not casas:
        print(s["slug"], "sem casas no OSM")
        continue
    obs = [ref.contains(p) for p in casas]
    n_obs = sum(obs)
    linhas = []
    for f in sorted(glob.glob(os.path.join(saida, s["slug"] + "_[0-9]*.json")), key=lambda f: int(re.search(r"_(\d+)\.json$", f).group(1)) if re.search(r"_(\d+)\.json$", f) else -1):
        m = re.search(r"_(\d+)\.json$", f)
        if not m:
            continue
        geoms = [shape(x["geometry"]) for x in json.load(open(f))["features"]]
        arvore = STRtree(geoms)
        prev = [len(arvore.query(p, predicate="intersects")) > 0 for p in casas]
        vp = sum(1 for a, b in zip(obs, prev) if a and b)
        n_prev = sum(prev)
        sens = 100 * vp / n_obs if n_obs else 0
        prec = 100 * vp / n_prev if n_prev else 0
        f1 = 2 * sens * prec / (sens + prec) if sens + prec else 0
        linhas.append((int(m.group(1)), sens, prec, f1, n_prev))
    if not linhas:
        continue
    melhor = max(linhas, key=lambda x: x[3])
    print(f'\n{s["nome"]}: {len(casas)} casas na zona, {n_obs} atingidas ({100 * n_obs / len(casas):.0f}%)')
    for nv, sens, prec, f1, n_prev in linhas:
        print(f"  rio +{nv:>2} m: pegou {sens:5.1f}% das atingidas | das marcadas, {prec:5.1f}% foram atingidas | nota {f1:5.1f} | marcou {n_prev}{'  <- melhor' if (nv, sens, prec, f1, n_prev) == melhor else ''}")
    resumo.append((s["nome"], s["tipo"], len(casas), n_obs) + melhor)
print("\nResumo (melhor nível):")
for nome, tipo, nc, no, nv, sens, prec, f1, npv in resumo:
    print(f"  {nome:45s} {tipo:9s} {no:5d}/{nc:<5d} atingidas | rio +{nv:>2} m: pegou {sens:5.1f}%  acertou {prec:5.1f}%  nota {f1:5.1f}")
