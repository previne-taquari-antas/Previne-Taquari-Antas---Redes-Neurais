# -*- coding: utf-8 -*-
"""Pontos de encontro, primeira versão: trechos de via fora da mancha do Mapa Único do Plano
Rio Grande (MUP RS, Área Diretamente Atingida das cheias de abril e maio de 2024), com 100 m
de afastamento. Santa Tereza e Muçum.

Critério (equipe do projeto, out/2026):
- área insegura = mancha do mapa único; área segura = fora dela, a mais de 100 m (OFFSET_M);
- ponto de encontro = trecho de via do OpenStreetMap (a rede dos painéis casa a casa) que fica
  inteiro fora dessa faixa: a via evita sugerir lugar no meio do mato. As "áreas edificadas" da
  SEMA não entram (poligonais ruins);
- é provisório: quando o perigo hidrológico do projeto ficar pronto, ele substitui o mapa único
  (qualquer mancha em GeoJSON entra por --mancha).

Escolha dos pontos como em locais_altos.py: um a um, o que mais poupa caminhada do idoso
(casa·min, teto de 60 min), até 10 pontos ou ganho abaixo de 150 casa·min. A caminhada usa o
r.walk de caminhada.py, com a subida do LiDAR onde há grade (Santa Tereza) e no plano em Muçum.

A mancha entra já em WGS84 e recortada por cidade (preparar_mancha.py converte shapefile,
GeoPackage ou KML). Só shapely, numpy e Pillow (os do CI).

  python codigo_python/09_rota_fuga/pontos_encontro.py santa_tereza            # resumo, sem gravar
  python codigo_python/09_rota_fuga/pontos_encontro.py mucum --gravar
"""
import argparse
import hashlib
import heapq
import json
import math
import os
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import unary_union
from shapely.prepared import prep

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhada import VEL_IDOSO, haversine, tempo_trecho  # noqa: E402
import locais_altos  # noqa: E402

RAIZ = locais_altos.RAIZ
DADOS = os.path.join(RAIZ, "assets", "data", "rota_fuga")
INF = math.inf
OFFSET_M = 100.0
PONTOS_MAX = locais_altos.LOCAIS_MAX
GANHO_MIN_CASA_MIN = locais_altos.GANHO_MIN_CASA_MIN
TEMPO_TETO_S = locais_altos.TEMPO_TETO_S
SIMPLIFICA_M = 5.0  # contorno do mapa (a conta usa a mancha inteira)
ESTADOS = ("fora", "faixa", "mancha", "sem_via")
CASAS_CAMPOS = ["lat", "lon", "estado", "ponto", "tempo_s", "dist_m"]
FONTE_MUP = ("Mapa Único do Plano Rio Grande (MUP RS), Área Diretamente Atingida das cheias de "
             "abril e maio de 2024 (SPGG/DEE, Governo do RS)")

CIDADES = {
    "santa_tereza": {"painel": os.path.join(RAIZ, "santa_tereza_painel_casas.html"), "municipio": "Santa Tereza",
                     "lidar": locais_altos.CIDADES["santa_tereza"]["lidar"],
                     "nomes": locais_altos.CIDADES["santa_tereza"]["nomes"]},
    "mucum": {"painel": os.path.join(RAIZ, "mucum_painel_casas.html"), "municipio": "Muçum"},
}


def mancha_padrao(cidade):
    return os.path.join(DADOS, f"mup_rs_ada_{cidade}.geojson")


def saida_padrao(cidade):
    return os.path.join(DADOS, f"{cidade}_pontos_encontro_mup.json")


class Plano:
    """Metros num plano local (equirretangular no centro da rede): erro < 0,1% em poucos km."""

    def __init__(self, nos):
        self.lat0 = sum(p[0] for p in nos) / len(nos)
        self.lon0 = sum(p[1] for p in nos) / len(nos)
        self.kx, self.ky = 111320.0 * math.cos(math.radians(self.lat0)), 110540.0

    def xy(self, lat, lon):
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)

    def de_lonlat(self, g):
        return shapely.transform(g, lambda c: np.column_stack(((c[:, 0] - self.lon0) * self.kx, (c[:, 1] - self.lat0) * self.ky)))

    def para_lonlat(self, g):
        return shapely.transform(g, lambda c: np.column_stack((c[:, 0] / self.kx + self.lon0, c[:, 1] / self.ky + self.lat0)))


def le_mancha(caminho, plano):
    """União dos polígonos do GeoJSON (WGS84), em metros no plano local."""
    with open(caminho, encoding="utf-8") as f:
        fc = json.load(f)
    feats = fc["features"] if fc.get("type") == "FeatureCollection" else [fc]
    gs = [shape(f["geometry"]) for f in feats if f.get("geometry")]
    gs = [g.buffer(0) for g in gs if g.geom_type in ("Polygon", "MultiPolygon")]
    if not gs:
        raise SystemExit(f"{caminho}: nenhum polígono")
    return plano.de_lonlat(unary_union(gs))


def _sha256(caminho):
    with open(caminho, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def grafo(doc, z):
    """Lista de adjacência reversa: radj[v] = [(u, segundos de u até v, metros)], para Dijkstra a partir do ponto."""
    nos = doc["nos"]
    radj = [[] for _ in nos]
    for a, b, *_ in doc["edges"]:
        d = haversine(nos[a][1], nos[a][0], nos[b][1], nos[b][0])
        dh = z[b] - z[a] if z[a] is not None and z[b] is not None else 0.0
        radj[b].append((a, tempo_trecho(d, dh), d))   # anda de a para b
        radj[a].append((b, tempo_trecho(d, -dh), d))  # anda de b para a
    return radj


def ate_os_pontos(radj, fontes, teto=INF):
    """Dijkstra reverso de várias fontes: segundos e metros até o ponto mais perto, o próximo nó e o ponto."""
    n = len(radj)
    t, d, prox, dono = [INF] * n, [0.0] * n, [-1] * n, [-1] * n
    pq = []
    for s in fontes:
        t[s], dono[s] = 0.0, s
        pq.append((0.0, s))
    heapq.heapify(pq)
    while pq:
        tu, u = heapq.heappop(pq)
        if tu > t[u] or tu > teto:
            continue
        for v, tvu, dvu in radj[u]:  # v anda até u
            nt = tu + tvu
            if nt < t[v]:
                t[v], d[v], prox[v], dono[v] = nt, d[u] + dvu, u, dono[u]
                heapq.heappush(pq, (nt, v))
    return t, d, prox, dono


def calcula(doc, mancha, plano, cidade, offset_m=OFFSET_M):
    """Pontos de encontro da cidade com a `mancha` (shapely, metros no `plano`). Determinístico."""
    cfg = CIDADES[cidade]
    nos, F = doc["nos"], {k: i for i, k in enumerate(doc["meta"]["casas_campos"])}
    xy = [plano.xy(la, lo) for la, lo in nos]
    zona = mancha.buffer(offset_m)
    zp, mp = prep(zona), prep(mancha)
    no_seguro = [not zp.intersects(Point(p)) for p in xy]
    aresta_segura = [no_seguro[a] and no_seguro[b] and not zp.intersects(LineString([xy[a], xy[b]]))
                     for a, b, *_ in doc["edges"]]
    # ponto de encontro: nó que é ponta de um trecho de via inteiro fora da faixa
    cand = sorted({k for (a, b, *_), ok in zip(doc["edges"], aresta_segura) if ok for k in (a, b)})
    lidar = locais_altos.Lidar(cfg["lidar"]) if cfg.get("lidar") else None
    z = [lidar(la, lo) if lidar else None for la, lo in nos]
    radj = grafo(doc, z)

    casas, pend = [], []
    for c in doc["casas"]:
        la, lo, n = c[F["lat"]], c[F["lon"]], c[F["no"]]
        if n is not None and n < 0 and c[F["proj_lat"]] is not None:
            n = locais_altos.no_mais_proximo(nos, (c[F["proj_lat"]], c[F["proj_lon"]]))
        p = Point(plano.xy(la, lo))
        estado = "mancha" if mp.contains(p) else "faixa" if zp.contains(p) else "fora"
        d0 = None if n is None or n < 0 or c[F["proj_lat"]] is None else \
            haversine(lo, la, c[F["proj_lon"]], c[F["proj_lat"]]) + \
            haversine(c[F["proj_lon"]], c[F["proj_lat"]], nos[n][1], nos[n][0])
        if estado != "fora" and d0 is None:
            estado = "sem_via"
        casas.append({"lat": la, "lon": lo, "estado": estado, "no": n, "d0": d0, "pessoas": c[F["pessoas"]] or 0})
        if estado in ("mancha", "faixa"):
            pend.append(len(casas) - 1)

    # tempo de cada casa a pé até cada candidato (teto de 60 min, como no guloso)
    M = np.full((len(pend), len(cand)), TEMPO_TETO_S, dtype=np.float64)
    for j, s in enumerate(cand):
        t, _d, _p, _o = ate_os_pontos(radj, [s], TEMPO_TETO_S)
        for i, k in enumerate(pend):
            ca = casas[k]
            tt = ca["d0"] / VEL_IDOSO + t[ca["no"]]
            if tt < M[i, j]:
                M[i, j] = tt
    atual = np.full(len(pend), TEMPO_TETO_S)
    escolhidos = []
    while len(escolhidos) < PONTOS_MAX and len(cand) and len(pend):
        ganho = (atual[:, None] - np.minimum(atual[:, None], M)).sum(axis=0)
        j = int(np.argmax(ganho))  # empate: o primeiro candidato (menor índice de nó)
        if ganho[j] / 60.0 < GANHO_MIN_CASA_MIN:
            break
        escolhidos.append(cand[j])
        atual = np.minimum(atual, M[:, j])

    # cada nó da rede segue até o ponto mais perto (a página traça o caminho de qualquer toque)
    t, d, prox, dono = ate_os_pontos(radj, escolhidos)
    idx = {s: i for i, s in enumerate(escolhidos)}
    ruas = locais_altos._json(cfg["nomes"])["ruas"] if cfg.get("nomes") and os.path.exists(cfg["nomes"]) else []
    pontos = []
    for i, s in enumerate(escolhidos):
        rr = locais_altos._rua_mais_proxima(ruas, nos[s], locais_altos.RAIO_RUA_M) if ruas else []
        rua = f"{rr[0][1]} com {rr[1][1]}" if len(rr) >= 2 else rr[0][1] if rr else None
        afast = mancha.distance(Point(xy[s]))
        pontos.append({"id": f"encontro_{i + 1}", "lat": nos[s][0], "lon": nos[s][1], "no": s, "rua": rua,
                       "dist_mancha_m": round(afast, 1)})
    saida_casas = []
    for ca in casas:
        n, ok = ca["no"], ca["estado"] in ("mancha", "faixa")
        if ok and n is not None and dono[n] >= 0 and ca["d0"] / VEL_IDOSO + t[n] <= TEMPO_TETO_S:
            ca["ponto"], ca["tempo_s"], ca["dist_m"] = idx[dono[n]], round(ca["d0"] / VEL_IDOSO + t[n]), round(ca["d0"] + d[n], 1)
        else:
            ca["ponto"], ca["tempo_s"], ca["dist_m"] = -1, None, None
        saida_casas.append([ca["lat"], ca["lon"], ESTADOS.index(ca["estado"]), ca["ponto"], ca["tempo_s"], ca["dist_m"]])
    for i, pt in enumerate(pontos):
        ts = sorted(ca["tempo_s"] for ca in casas if ca["ponto"] == i)
        pt["n_casas"] = len(ts)
        pt["pessoas"] = round(sum(ca["pessoas"] for ca in casas if ca["ponto"] == i))
        pt["tempo_mediano_min"] = round(ts[len(ts) // 2] / 60, 1) if ts else None
        pt["tempo_max_min"] = round(ts[-1] / 60, 1) if ts else None
    return {"no_seguro": no_seguro, "aresta_segura": aresta_segura, "candidatos": len(cand), "pontos": pontos,
            "casas": saida_casas, "prox": prox, "tempo_no_s": [None if v == INF else round(v) for v in t],
            "ponto_no": [idx[o] if o >= 0 else -1 for o in dono], "zona": zona}


def geojson_contorno(g, plano):
    g = plano.para_lonlat(g.simplify(SIMPLIFICA_M, preserve_topology=True))

    def arred(c):
        return [arred(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 6), round(c[1], 6)]
    m = mapping(g)
    return {"type": m["type"], "coordinates": arred(m["coordinates"])}


def documento(cidade, caminho_mancha=None, offset_m=OFFSET_M, fonte=FONTE_MUP):
    """JSON da página dos pontos de encontro (pontos_encontro.html?cidade=...)."""
    cfg = CIDADES[cidade]
    caminho_mancha = caminho_mancha or mancha_padrao(cidade)
    doc = locais_altos.payload(cfg["painel"])
    plano = Plano(doc["nos"])
    mancha = le_mancha(caminho_mancha, plano)
    r = calcula(doc, mancha, plano, cidade, offset_m)
    # recorte do desenho à volta da rede (a mancha do estado vai além)
    xs, ys = zip(*(plano.xy(la, lo) for la, lo in doc["nos"]))
    caixa = LineString([(min(xs) - 1500, min(ys) - 1500), (max(xs) + 1500, max(ys) + 1500)]).envelope
    est = [c[2] for c in r["casas"]]
    return {
        "schema_version": "previne_pontos_encontro_v1",
        "municipio": cfg["municipio"],
        "criterio": f"ponto de encontro = trecho de via (OpenStreetMap) inteiro fora da mancha com {offset_m:g} m de "
                    "afastamento; escolhidos pelo que mais poupa caminhada do idoso (r.walk, 0,9 m/s)",
        "fonte_mancha": fonte, "mancha_arquivo": os.path.relpath(caminho_mancha, RAIZ),
        "mancha_sha256": _sha256(caminho_mancha), "offset_m": offset_m,
        "aviso": "Primeira versão, provisória: sugestão técnica, não é abrigo oficial nem confirmado pela Defesa Civil. "
                 "A mancha do mapa único será trocada pelo perigo hidrológico do projeto. Em perigo, ligue 199 ou 193.",
        "resumo": {"casas": len(est), "fora": est.count(0), "faixa": est.count(1), "mancha": est.count(2),
                   "sem_via": est.count(3), "nos_seguros": sum(r["no_seguro"]), "nos": len(doc["nos"]),
                   "trechos_seguros": sum(r["aresta_segura"]), "trechos": len(doc["edges"]),
                   "candidatos": r["candidatos"]},
        "nos": doc["nos"],
        "arestas": [[a, b, int(ok)] for (a, b, *_), ok in zip(doc["edges"], r["aresta_segura"])],
        "prox": r["prox"], "ponto_no": r["ponto_no"], "tempo_no_s": r["tempo_no_s"],
        "estados": list(ESTADOS), "casas_campos": CASAS_CAMPOS, "casas": r["casas"],
        "pontos": r["pontos"],
        "mancha": geojson_contorno(mancha.intersection(caixa), plano),
        "faixa": geojson_contorno(r["zona"].intersection(caixa), plano),
    }


def resumo(d):
    s = d["resumo"]
    linhas = [f"{d['municipio']}: {s['casas']} casas · fora {s['fora']}, na faixa de {d['offset_m']:g} m {s['faixa']}, "
              f"na mancha {s['mancha']}, sem via {s['sem_via']} · trechos seguros {s['trechos_seguros']}/{s['trechos']} · "
              f"candidatos {s['candidatos']} · pontos {len(d['pontos'])}"]
    for p in d["pontos"]:
        linhas.append(f"  {p['id']}: {p['lat']:.6f}, {p['lon']:.6f} · {p['rua'] or 'rua sem nome'} · "
                      f"{p['dist_mancha_m']:.0f} m da mancha · {p['n_casas']} casas, ~{p['pessoas']} pessoas, "
                      f"mediana {p['tempo_mediano_min']} min, máx {p['tempo_max_min']} min")
    return "\n".join(linhas)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cidade", choices=sorted(CIDADES))
    ap.add_argument("--mancha", help="GeoJSON da área insegura (padrão: assets/data/rota_fuga/mup_rs_ada_<cidade>.geojson)")
    ap.add_argument("--offset", type=float, default=OFFSET_M, help="afastamento da mancha, em metros")
    ap.add_argument("--fonte", default=FONTE_MUP, help="descrição da mancha (vai para o JSON e para a página)")
    ap.add_argument("--gravar", action="store_true", help="grava assets/data/rota_fuga/<cidade>_pontos_encontro_mup.json")
    a = ap.parse_args()
    d = documento(a.cidade, a.mancha, a.offset, a.fonte)
    print(resumo(d))
    if a.gravar:
        with open(saida_padrao(a.cidade), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
        print("gravado:", os.path.relpath(saida_padrao(a.cidade), RAIZ))


if __name__ == "__main__":
    main()
