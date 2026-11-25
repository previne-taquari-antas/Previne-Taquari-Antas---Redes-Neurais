# -*- coding: utf-8 -*-
"""Dados do OpenStreetMap para os critérios da versão 2 dos pontos de encontro (pontos_encontro.py):
o tipo de cada via (onde passa carro de resgate) e os lugares de reunião (praças, campos, ginásios,
escolas, estacionamentos, igrejas, centros comunitários) em volta da rede de ruas de cada cidade.

Grava assets/data/rota_fuga/osm_encontro_<cidade>.json. O Overpass não responde de todo lugar;
o download roda no CI (.github/workflows/osm-pontos-encontro.yml).

  python codigo_python/09_rota_fuga/baixar_osm_encontro.py            # as duas cidades
  python codigo_python/09_rota_fuga/baixar_osm_encontro.py mucum
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locais_altos  # noqa: E402
import pontos_encontro as pe  # noqa: E402

SERVIDORES = ("https://overpass-api.de/api/interpreter",
              "https://overpass.kumi.systems/api/interpreter",
              "https://maps.mail.ru/osm/tools/overpass/api/interpreter")
FOLGA_GRAUS = 0.01  # ~1 km além da rede do painel
LUGARES = {
    "leisure": "park|pitch|playground|sports_centre|stadium|recreation_ground|common",
    "landuse": "recreation_ground|village_green",
    "place": "square",
    "amenity": "parking|school|kindergarten|college|university|townhall|community_centre|place_of_worship|"
               "social_facility|fire_station|police|hospital|clinic",
}


def consulta(caixa):
    s, w, n, e = caixa
    bb = f"({s:.5f},{w:.5f},{n:.5f},{e:.5f})"
    partes = [f'way["highway"]{bb};'] + [f'nwr["{k}"~"^({v})$"]{bb};' for k, v in LUGARES.items()]
    return "[out:json][timeout:180];(" + "".join(partes) + ");out geom tags;"


def baixa(q):
    erro = None
    for url in SERVIDORES:
        for tentativa in range(2):
            try:
                req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                             headers={"User-Agent": "PREVINE-pontos-encontro/1.0"})
                with urllib.request.urlopen(req, timeout=240) as r:
                    return json.load(r), url
            except Exception as e:  # noqa: BLE001
                erro = e
                print(f"  {url}: {str(e)[:90]}")
                time.sleep(5 * (tentativa + 1))
    raise SystemExit(f"Overpass indisponível: {erro}")


def _coords(geometria):
    return [[round(p["lat"], 7), round(p["lon"], 7)] for p in geometria if p]


def converte(osm):
    vias, lugares = [], []
    for el in osm.get("elements", []):
        tags = el.get("tags", {})
        ident = f"{el['type']}/{el['id']}"
        tipo = next((f"{k}={tags[k]}" for k in LUGARES if k in tags and tags[k] in LUGARES[k].split("|")), None)
        if el["type"] == "way" and "highway" in tags and tipo is None:
            vias.append({"id": ident, "highway": tags["highway"], "coords": _coords(el.get("geometry", []))})
            continue
        if tipo is None:
            continue
        if el["type"] == "node":
            aneis = [[[round(el["lat"], 7), round(el["lon"], 7)]]]
        elif el["type"] == "way":
            aneis = [_coords(el.get("geometry", []))]
        else:  # relação: os anéis externos
            aneis = [_coords(m.get("geometry", [])) for m in el.get("members", []) if m.get("role") == "outer"]
        aneis = [a for a in aneis if a]
        if aneis:
            lugares.append({"id": ident, "tipo": tipo, "nome": tags.get("name"), "aneis": aneis})
    vias.sort(key=lambda v: v["id"])
    lugares.sort(key=lambda v: v["id"])
    return vias, lugares


def main(cidades):
    for cidade in cidades:
        nos = locais_altos.payload(pe.CIDADES[cidade]["painel"])["nos"]
        la, lo = [p[0] for p in nos], [p[1] for p in nos]
        caixa = (min(la) - FOLGA_GRAUS, min(lo) - FOLGA_GRAUS, max(la) + FOLGA_GRAUS, max(lo) + FOLGA_GRAUS)
        q = consulta(caixa)
        osm, servidor = baixa(q)
        vias, lugares = converte(osm)
        saida = os.path.join(pe.DADOS, f"osm_encontro_{cidade}.json")
        if not vias:
            raise SystemExit(f"{cidade}: o Overpass não devolveu vias; nada gravado")
        with open(saida, "w", encoding="utf-8") as f:
            json.dump({"fonte": "© contribuidores do OpenStreetMap (ODbL), via Overpass API", "servidor": servidor,
                       "baixado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "osm_base": osm.get("osm3s", {}).get("timestamp_osm_base"), "caixa_sul_oeste_norte_leste": caixa,
                       "consulta": q, "vias": vias, "lugares": lugares}, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{cidade}: {len(vias)} vias, {len(lugares)} lugares de reunião · {os.path.relpath(saida, pe.RAIZ)} "
              f"({os.path.getsize(saida) / 1e3:.0f} kB)")


if __name__ == "__main__":
    main(sys.argv[1:] or sorted(pe.CIDADES))
