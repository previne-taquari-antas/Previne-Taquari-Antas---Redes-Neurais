"""Água permanente (leito do rio, lagos) do OpenStreetMap na zona de cada lugar: prep/<lugar>_agua.json.
Baixa a zona em ladrilhos do servidor oficial com curl e monta os polígonos de água."""
import json
import math
import os
import subprocess
import sys

from shapely.geometry import LineString, Polygon, mapping, shape
from shapely.ops import polygonize, unary_union

base = os.path.dirname(os.path.abspath(__file__))
prep = os.path.join(base, "prep")
cache = os.path.join(base, "osm")
os.makedirs(cache, exist_ok=True)
sites = json.load(open(os.path.join(base, "sites.json")))
alvo = sys.argv[1:] or [s["slug"] for s in sites]


def baixa(w, s, e, n, nome):
    arq = os.path.join(cache, nome + ".json")
    if not os.path.exists(arq) or os.path.getsize(arq) < 100:
        url = f"https://api.openstreetmap.org/api/0.6/map.json?bbox={w:.5f},{s:.5f},{e:.5f},{n:.5f}"
        r = subprocess.run(["curl", "-sS", "-m", "120", "-o", arq, "-w", "%{http_code}", url], capture_output=True, text=True)
        if r.stdout != "200":
            os.remove(arq)
            # grande demais: em quatro
            if r.stdout == "400":
                mx, my = (w + e) / 2, (s + n) / 2
                return baixa(w, s, mx, my, nome + "a") + baixa(mx, s, e, my, nome + "b") + baixa(w, my, mx, n, nome + "c") + baixa(mx, my, e, n, nome + "d")
            print("  falha", r.stdout, nome)
            return []
    return [json.load(open(arq))]


def agua(partes):
    nos, ways, rels = {}, {}, []
    for p in partes:
        for el in p.get("elements", []):
            if el["type"] == "node":
                nos[el["id"]] = (el["lon"], el["lat"])
            elif el["type"] == "way":
                ways[el["id"]] = el
            elif el["type"] == "relation":
                rels.append(el)
    def eh_agua(t):
        return t.get("natural") == "water" or t.get("waterway") == "riverbank" or t.get("landuse") == "reservoir"
    def coords(w):
        c = [nos[i] for i in w.get("nodes", []) if i in nos]
        return c if len(c) == len(w.get("nodes", [])) else None
    polys = []
    for w in ways.values():
        if eh_agua(w.get("tags", {})):
            c = coords(w)
            if c and len(c) >= 4 and c[0] == c[-1]:
                polys.append(Polygon(c).buffer(0))
    for r in rels:
        if not eh_agua(r.get("tags", {})):
            continue
        linhas = []
        for m in r.get("members", []):
            if m["type"] == "way" and m.get("role") == "outer" and m["ref"] in ways:
                c = coords(ways[m["ref"]])
                if c and len(c) >= 2:
                    linhas.append(LineString(c))
        polys += [p.buffer(0) for p in polygonize(unary_union(linhas))] if linhas else []
    return unary_union(polys) if polys else Polygon()


for s in sites:
    if s["slug"] not in alvo:
        continue
    zona = shape(json.load(open(os.path.join(prep, s["slug"] + "_ref.json")))["zona"])
    w, so, e, n = zona.bounds
    passo = 0.02
    partes = []
    nx, ny = math.ceil((e - w) / passo), math.ceil((n - so) / passo)
    for j in range(ny):
        for i in range(nx):
            a, b = w + i * (e - w) / nx, so + j * (n - so) / ny
            partes += baixa(a, b, a + (e - w) / nx, b + (n - so) / ny, f'{s["slug"]}_{i}_{j}')
    ag = agua(partes).intersection(zona)
    json.dump(mapping(ag), open(os.path.join(prep, s["slug"] + "_agua.json"), "w"))
    print(f'{s["slug"]:14s} água permanente {100 * ag.area / zona.area:5.1f}% da zona ({nx * ny} ladrilhos)')
