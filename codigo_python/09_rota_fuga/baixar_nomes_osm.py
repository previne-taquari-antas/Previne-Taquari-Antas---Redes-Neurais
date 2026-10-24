#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nomes de ruas e de lugares do OpenStreetMap, para nomear os locais altos.

Só biblioteca padrão. Grava as ruas com nome (geometria) e os lugares com
nome (escola, igreja, praça, salão, campo...) no recorte das rotas:

  python codigo_python/09_rota_fuga/baixar_nomes_osm.py santa_tereza

Saída: assets/data/rota_fuga/osm_nomes_<cidade>.json
(© contribuidores do OpenStreetMap, licença ODbL).
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# recorte um pouco maior que o dos nós de rua do painel (gerar_rota_fuga_ruas.py)
RECORTES = {"santa_tereza": dict(S=-29.200, W=-51.760, N=-29.150, E=-51.700)}
SERVIDORES = ("https://overpass-api.de/api/interpreter",
              "https://overpass.kumi.systems/api/interpreter")
LUGARES = ("amenity", "leisure", "office", "tourism", "historic", "place")
CHAVES_LUGAR = ("name", "amenity", "leisure", "building", "office", "tourism",
                "historic", "place", "religion", "sport")


def consulta(b):
    caixa = f"{b['S']},{b['W']},{b['N']},{b['E']}"
    lugares = "".join(f'nwr["{k}"]["name"]({caixa});' for k in LUGARES)
    return (f"[out:json][timeout:120];"
            f'way["highway"]["name"]({caixa});out tags geom;'
            f'({lugares}nwr["building"]["name"]({caixa}););out tags center;')


def baixa(q):
    erro = None
    for url in SERVIDORES:
        for tentativa in range(3):
            try:
                req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                             headers={"User-Agent": "PREVINE-rotas-de-fuga/1.0"})
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.loads(r.read().decode("utf-8")), url
            except Exception as e:  # noqa: BLE001 - tenta o próximo servidor
                erro = e
                time.sleep(10 * (tentativa + 1))
    raise SystemExit(f"Overpass indisponível: {erro}")


def main():
    cidade = sys.argv[1] if len(sys.argv) > 1 else "santa_tereza"
    b = RECORTES[cidade]
    d, url = baixa(consulta(b))
    ruas, lugares, vistos = [], [], set()
    for e in d["elements"]:
        t = e.get("tags") or {}
        if e["type"] == "way" and "highway" in t and "geometry" in e:
            ruas.append({"nome": t["name"], "highway": t["highway"],
                         "coords": [[round(p["lat"], 6), round(p["lon"], 6)] for p in e["geometry"]]})
            continue
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        lon = e.get("lon", (e.get("center") or {}).get("lon"))
        if lat is None or (e["type"], e["id"]) in vistos:
            continue
        vistos.add((e["type"], e["id"]))
        lugares.append({"nome": t["name"], "osm": f"{e['type']}/{e['id']}",
                        "lat": round(lat, 6), "lon": round(lon, 6),
                        "tags": {k: t[k] for k in CHAVES_LUGAR if k in t and k != "name"}})
    ruas.sort(key=lambda r: (r["nome"], r["coords"][0]))
    lugares.sort(key=lambda p: (p["nome"], p["osm"]))
    out = {"fonte": "© contribuidores do OpenStreetMap (ODbL), via Overpass API",
           "servidor": url, "baixado_em": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "osm_base": (d.get("osm3s") or {}).get("timestamp_osm_base"),
           "recorte": b, "ruas": ruas, "lugares": lugares}
    caminho = os.path.join(RAIZ, "assets", "data", "rota_fuga", f"osm_nomes_{cidade}.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{cidade}: {len(ruas)} trechos de rua com nome, {len(lugares)} lugares -> {caminho}")


if __name__ == "__main__":
    main()
