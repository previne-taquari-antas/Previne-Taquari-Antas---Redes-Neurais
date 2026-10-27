# -*- coding: utf-8 -*-
"""Compara a base viária da SEMA (BCRS25 1:25.000, vias_sema.py) com a rede do OpenStreetMap dos
painéis casa a casa (a dos pontos de encontro), em Santa Tereza e Muçum.

Na área onde a rede do painel está completa (o recorte de gerar_rota_fuga_ruas.py: caixa da cidade
± 0,003°, menos 50 m de borda, porque fora dela o painel só guarda as ruas das rotas), mede:
- o comprimento de cada base;
- quanto de cada uma tem a outra a até TOLERANCIA_M (20 m: a SEMA é 1:25.000, ~12 m de erro
  gráfico, e o OSM foi traçado sobre imagem);
- os trechos de uma que faltam na outra (pedaços contínuos de 50 m ou mais), com onde ficam;
- o deslocamento típico entre as duas onde coincidem;
- quantas casas do painel têm uma via a até CASA_VIA_M (50 m) em cada base.
A ferrovia (Trecho_Ferroviario) fica de fora: ninguém evacua por ela.

  python codigo_python/09_rota_fuga/comparar_vias.py            # resumo
  python codigo_python/09_rota_fuga/comparar_vias.py --gravar   # assets/data/rota_fuga/comparacao_vias_sema_osm.json
"""
import argparse
import json
import os
import sys

from shapely.geometry import LineString, Point, box, shape
from shapely.prepared import prep
from shapely.ops import linemerge, unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locais_altos  # noqa: E402
import pontos_encontro as pe  # noqa: E402

TOLERANCIA_M = 20.0
CASA_VIA_M = 50.0
TRECHO_MIN_M = 50.0
DESLOCADO_M = 50.0
BORDA_M = 50.0
# caixa das ruas de cada painel: gerar_rota_fuga_ruas.CIDADES[...]["bbox"] ± 0,003° (o recorte do payload)
RECORTE = {"santa_tereza": dict(S=-29.192, N=-29.158, W=-51.748, E=-51.718),
           "mucum": dict(S=-29.171, N=-29.150, W=-51.892, E=-51.855)}
FOLGA_RECORTE_GRAUS = 0.003
SAIDA = os.path.join(pe.DADOS, "comparacao_vias_sema_osm.json")


def vias_sema(cidade):
    return os.path.join(pe.DADOS, f"sema_bcrs25_vias_{cidade}.geojson")


def _linhas(g):
    return [x for x in getattr(g, "geoms", [g]) if x.geom_type == "LineString" and not x.is_empty]


def faltando(a, b, plano):
    """Pedaços de `a` a mais de TOLERANCIA_M de `b`, com TRECHO_MIN_M ou mais:
    [(metros, lat, lon do meio, distância mediana até `b` em m)], do maior para o menor.
    Distância mediana até DESLOCADO_M: a mesma via desenhada mais longe; acima disso, outro traçado."""
    u = unary_union(_linhas(a.difference(b.buffer(TOLERANCIA_M))))
    out = []
    for p in _linhas(linemerge(u) if u.geom_type == "MultiLineString" else u):
        if p.length >= TRECHO_MIN_M:
            c = plano.para_lonlat(p.interpolate(0.5, normalized=True))
            d = sorted(b.distance(p.interpolate(i / 20, normalized=True)) for i in range(21))
            out.append((round(p.length), round(c.y, 6), round(c.x, 6), round(d[10])))
    return sorted(out, reverse=True)


def compara(cidade):
    doc = locais_altos.payload(pe.CIDADES[cidade]["painel"])
    plano = pe.Plano(doc["nos"])
    xy = [plano.xy(la, lo) for la, lo in doc["nos"]]
    bb, f = RECORTE[cidade], FOLGA_RECORTE_GRAUS
    x0, y0 = plano.xy(bb["S"] - f, bb["W"] - f)
    x1, y1 = plano.xy(bb["N"] + f, bb["E"] + f)
    area = box(x0 + BORDA_M, y0 + BORDA_M, x1 - BORDA_M, y1 - BORDA_M)
    osm = unary_union([LineString([xy[a], xy[b]]) for a, b, *_ in doc["edges"]]).intersection(area)
    with open(vias_sema(cidade), encoding="utf-8") as arq:
        fc = json.load(arq)
    feicoes = [ft for ft in fc["features"] if ft.get("geometry") and ft["properties"].get("_camada") != "Trecho_Ferroviario.shp"]
    sema = unary_union([plano.de_lonlat(shape(ft["geometry"])) for ft in feicoes]).intersection(area)
    osm_buf, sema_buf = osm.buffer(TOLERANCIA_M), sema.buffer(TOLERANCIA_M)
    # deslocamento: distância de pontos a cada 10 m da SEMA até o OSM, onde coincidem
    dist = []
    for l in _linhas(sema):
        n = max(1, int(l.length // 10))
        for i in range(n + 1):
            d = osm.distance(l.interpolate(i / n, normalized=True))
            if d <= TOLERANCIA_M:
                dist.append(d)
    dist.sort()
    tipos = {}
    for ft in feicoes:
        g = plano.de_lonlat(shape(ft["geometry"])).intersection(area)
        if g.is_empty:
            continue
        pr = ft["properties"]
        chave = "ponte" if pr["_camada"] == "Ponte_Lin.shp" else \
            f"{(pr.get('d_tipoTrec') or '?').lower()} {(pr.get('d_jurisdic') or '?').lower()}"
        tipos[chave] = tipos.get(chave, 0) + g.length
    F = {k: i for i, k in enumerate(doc["meta"]["casas_campos"])}
    casas = [p for p in (Point(plano.xy(c[F["lat"]], c[F["lon"]])) for c in doc["casas"]) if area.contains(p)]
    perto_osm, perto_sema = prep(osm.buffer(CASA_VIA_M)), prep(sema.buffer(CASA_VIA_M))
    so_sema, so_osm = faltando(sema, osm, plano), faltando(osm, sema, plano)
    tracado = [x for x in so_sema if x[3] > DESLOCADO_M]
    return {
        "municipio": pe.CIDADES[cidade]["municipio"],
        "area_km2": round(area.area / 1e6, 2),
        "osm_km": round(osm.length / 1000, 2), "sema_km": round(sema.length / 1000, 2),
        "osm_com_sema_pct": round(100 * osm.intersection(sema_buf).length / osm.length, 1) if osm.length else None,
        "sema_com_osm_pct": round(100 * sema.intersection(osm_buf).length / sema.length, 1) if sema.length else None,
        "deslocamento_mediano_m": round(dist[len(dist) // 2], 1) if dist else None,
        "deslocamento_p90_m": round(dist[int(len(dist) * .9)], 1) if dist else None,
        "so_na_sema_trechos": len(so_sema), "so_na_sema_m": sum(x[0] for x in so_sema),
        "so_no_osm_trechos": len(so_osm), "so_no_osm_m": sum(x[0] for x in so_osm),
        "so_na_sema_outro_tracado_trechos": len(tracado), "so_na_sema_outro_tracado_m": sum(x[0] for x in tracado),
        "so_na_sema": so_sema,             # (metros, lat, lon do meio, distância mediana ao OSM), do maior para o menor
        "so_no_osm_maiores": so_osm[:20],
        "sema_por_tipo_km": {k: round(v / 1000, 2) for k, v in sorted(tipos.items(), key=lambda kv: -kv[1])},
        "casas": len(casas),
        "casas_com_via_osm": sum(perto_osm.contains(p) for p in casas),
        "casas_com_via_sema": sum(perto_sema.contains(p) for p in casas),
        "sema_feicoes": len(feicoes), "fonte_sema": fc.get("fonte"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gravar", action="store_true")
    a = ap.parse_args()
    out = {"tolerancia_m": TOLERANCIA_M, "trecho_min_m": TRECHO_MIN_M, "deslocado_m": DESLOCADO_M, "borda_m": BORDA_M,
           "casa_via_m": CASA_VIA_M, "cidades": {}}
    for cidade in pe.CIDADES:
        if not os.path.exists(vias_sema(cidade)):
            print(f"{cidade}: sem {os.path.relpath(vias_sema(cidade), pe.RAIZ)}")
            continue
        r = out["cidades"][cidade] = compara(cidade)
        print(f"{r['municipio']}: OSM {r['osm_km']} km · SEMA {r['sema_km']} km · OSM coberto pela SEMA {r['osm_com_sema_pct']}% · "
              f"SEMA coberta pelo OSM {r['sema_com_osm_pct']}% · deslocamento mediano {r['deslocamento_mediano_m']} m "
              f"(p90 {r['deslocamento_p90_m']} m) · só na SEMA {r['so_na_sema_trechos']} trechos ({r['so_na_sema_m']} m; "
              f"com outro traçado {r['so_na_sema_outro_tracado_trechos']}, {r['so_na_sema_outro_tracado_m']} m) · "
              f"só no OSM {r['so_no_osm_trechos']} trechos ({r['so_no_osm_m']} m)")
        print(f"   casas com via a até {CASA_VIA_M:g} m: OSM {r['casas_com_via_osm']}/{r['casas']} · "
              f"SEMA {r['casas_com_via_sema']}/{r['casas']}")
        print("   tipos na SEMA (km):", r["sema_por_tipo_km"])
    if a.gravar:
        with open(SAIDA, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("gravado:", os.path.relpath(SAIDA, pe.RAIZ))


if __name__ == "__main__":
    main()
