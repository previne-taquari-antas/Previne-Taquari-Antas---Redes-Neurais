# -*- coding: utf-8 -*-
"""Pontos de encontro: trechos de via fora da mancha do Mapa Único do Plano
Rio Grande (MUP RS, Área Diretamente Atingida das cheias de abril e maio de 2024), com 100 m
de afastamento. Santa Tereza e Muçum.

Critério (equipe do projeto, out/2026):
- área insegura = mancha do mapa único; área segura = fora dela, a mais de 100 m (OFFSET_M);
- ponto de encontro = trecho de via do OpenStreetMap (a rede dos painéis casa a casa) que fica
  inteiro fora dessa faixa: a via evita sugerir lugar no meio do mato. As "áreas edificadas" da
  SEMA não entram (poligonais ruins);
- é provisório: quando o perigo hidrológico do projeto ficar pronto, ele substitui o mapa único
  (qualquer mancha em GeoJSON entra por --mancha).

Versões (--versao): "mup" usa o mapa único; "hand" usa, enquanto o perigo hidrológico não chega,
o modelo HAND do projeto no nível da maior cheia registrada (set/2023 em Santa Tereza, mai/2024
em Muçum; mancha_hand.py), com o mesmo afastamento e a mesma escolha de pontos.

Escolha dos pontos como em locais_altos.py: um a um, o que mais poupa caminhada do idoso
(casa·min, teto de 60 min), até 10 pontos ou ganho abaixo de 150 casa·min. A caminhada usa o
r.walk de caminhada.py, com a subida do LiDAR onde há grade (Santa Tereza) e no plano em Muçum.

Versão 2 dos critérios (--criterios v2, o padrão), sugestões da equipe em nov/2026:
- longe de deslizamento: o ponto fica a mais de DESLIZAMENTO_M (100 m) das cicatrizes de
  deslizamento mapeadas depois de maio/2024 (assets/data/landslides_poly.geojson);
- passa carro de resgate: o ponto é ponta de um trecho seguro de via em que passa carro no OSM
  (VIAS_CARRO: de rodovia a rua residencial e via de serviço; trilha, caminho, escadaria e estrada
  de chão "track" ficam de fora);
- lugar de reunião: o ponto a até LUGAR_M (80 m) de praça, campo, ginásio, escola, estacionamento,
  igreja, centro comunitário (OSM), escola do cadastro estadual ou abrigo da Defesa Civil vale
  BONUS_LUGAR (30%) a mais na escolha. É preferência, não exigência: onde não há lugar assim, a rua
  segura continua valendo.
Os dados do OSM vêm de baixar_osm_encontro.py (assets/data/rota_fuga/osm_encontro_<cidade>.json).
"v1" refaz a primeira versão, só com a mancha e as ruas.

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
from shapely.strtree import STRtree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhada import VEL_IDOSO, haversine, tempo_trecho  # noqa: E402
import locais_altos  # noqa: E402
import plano_pontos  # noqa: E402

RAIZ = locais_altos.RAIZ
DADOS = os.path.join(RAIZ, "assets", "data", "rota_fuga")
INF = math.inf
OFFSET_M = 100.0
PONTOS_MAX = locais_altos.LOCAIS_MAX
GANHO_MIN_CASA_MIN = locais_altos.GANHO_MIN_CASA_MIN
TEMPO_TETO_S = locais_altos.TEMPO_TETO_S
SIMPLIFICA_M = 5.0  # contorno do mapa (a conta usa a mancha inteira)
TEMPO_SUGERIDO_MIN = 20   # tempo máximo a pé sugerido (equipe, nov/2026); a página deixa mudar
CRITERIOS = ("v1", "v2", "v3")
DESLIZAMENTO_M = 100.0
BORDA_SAIDA_M = 150.0  # saída seca: ruas fora da mancha que chegam a menos disso da borda da rede (saem da cidade)
LUGAR_M = 80.0
BONUS_LUGAR = 0.3
VIA_OSM_M = 10.0  # trecho do painel recebe o tipo da via do OSM a até 10 m do seu meio
VIAS_CARRO = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
              "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street", "service"}
DESLIZAMENTOS = os.path.join(RAIZ, "assets", "data", "landslides_poly.geojson")
SERVICOS = os.path.join(RAIZ, "assets", "data", "servicos")
NOME_LUGAR = {
    "leisure=park": "praça ou parque", "leisure=pitch": "campo ou quadra", "leisure=playground": "parquinho",
    "leisure=sports_centre": "ginásio ou centro esportivo", "leisure=stadium": "estádio",
    "leisure=recreation_ground": "área de lazer", "leisure=common": "área comum",
    "landuse=recreation_ground": "área de lazer", "landuse=village_green": "praça", "place=square": "praça",
    "amenity=parking": "estacionamento", "amenity=school": "escola", "amenity=kindergarten": "escola infantil",
    "amenity=college": "escola técnica ou faculdade", "amenity=university": "universidade",
    "amenity=townhall": "prefeitura", "amenity=community_centre": "centro comunitário",
    "amenity=place_of_worship": "igreja ou templo", "amenity=social_facility": "assistência social",
    "amenity=fire_station": "bombeiros", "amenity=police": "polícia", "amenity=hospital": "hospital",
    "amenity=clinic": "posto de saúde", "escola_iede": "escola (cadastro estadual)",
    "abrigo": "ponto da Defesa Civil",
}
ESTADOS = ("fora", "faixa", "mancha", "sem_via")
CASAS_CAMPOS = ["lat", "lon", "estado", "ponto", "tempo_s", "dist_m"]
FONTE_MUP = ("Mapa Único do Plano Rio Grande (MUP RS), Área Diretamente Atingida das cheias de "
             "abril e maio de 2024 (SPGG/DEE, Governo do RS)")
AVISO = "sugestão técnica, não é abrigo oficial nem confirmado pela Defesa Civil. Em perigo, ligue 199 ou 193."
# textos da página por versão; "observada": a mancha é área atingida de fato (e não modelada)
VERSOES = {
    # o mapa único é só 2024: em Santa Tereza a cheia de set/2023 foi maior em partes da cidade, então a área
    # insegura soma a maior cheia registrada pelo modelo do projeto (a mesma da versão "hand")
    "mup": {"mancha": "mup_rs_ada_{cidade}.geojson", "somar": "hand_maior_cheia_{cidade}.geojson",
            "saida": "{cidade}_pontos_encontro_mup.json",
            "rotulo": "mapa único e da maior cheia", "titulo": "Mapa Único do Plano Rio Grande somado à maior cheia registrada",
            "observada": True,  # quase toda observada (2024); a cheia do modelo cabe nela em Muçum
            "evento": {"santa_tereza": "cheias de abril e maio de 2024 (mapa único) e de set/2023, régua 23,65 m (modelo do projeto)",
                       "mucum": "cheias de abril e maio de 2024 (mapa único e modelo do projeto, régua 25,51 m)"},
            "evento_curto": {"santa_tereza": "2023 e 2024", "mucum": "2024"},
            "fonte": {"santa_tereza": FONTE_MUP + "; somada à cheia de set/2023 pelo modelo HAND do projeto",
                      "mucum": FONTE_MUP + "; somada à cheia de mai/2024 pelo modelo HAND do projeto"},
            "aviso": "Versão provisória: sugestão técnica, não é abrigo oficial nem confirmado pela Defesa "
                     "Civil. A mancha será trocada pelo perigo hidrológico do projeto. Em perigo, ligue 199 ou 193."},
    "hand": {"mancha": "hand_maior_cheia_{cidade}.geojson", "saida": "{cidade}_pontos_encontro_hand.json",
             "rotulo": "modelo do projeto", "titulo": "modelo HAND do projeto", "observada": False,
             "evento": {"santa_tereza": "maior cheia registrada, set/2023, régua 23,65 m",
                        "mucum": "maior cheia registrada, mai/2024, régua 25,51 m"},
             "evento_curto": {"santa_tereza": "set/2023", "mucum": "mai/2024"},
             "fonte": {"santa_tereza": "Modelo HAND do projeto PREVINE (LiDAR, HAND 5 m; régua 1,60 m = HAND 0) no "
                                       "nível da cheia de set/2023 (régua 23,65 m, HAND 22,1 m); contornos em "
                                       "revisão (Arroio Marrecão)",
                       "mucum": "Modelo HAND do projeto PREVINE (mosaico 2 m, drone + ANADEM; régua 5 m = HAND 0) no "
                                "nível da cheia de mai/2024 (régua 25,51 m, HAND 20,6 m)"},
             "aviso": "Versão provisória com o modelo HAND do projeto, até o perigo hidrológico ficar pronto: "
                      "a mancha é modelada, não observada. " + AVISO[0].upper() + AVISO[1:]},
}

CIDADES = {
    "santa_tereza": {"painel": os.path.join(RAIZ, "santa_tereza_painel_casas.html"), "municipio": "Santa Tereza",
                     "lidar": locais_altos.CIDADES["santa_tereza"]["lidar"],
                     "nomes": locais_altos.CIDADES["santa_tereza"]["nomes"]},
    "mucum": {"painel": os.path.join(RAIZ, "mucum_painel_casas.html"), "municipio": "Muçum"},
}


def osm_encontro(cidade):
    return os.path.join(DADOS, f"osm_encontro_{cidade}.json")


def _caixa(xy, folga):
    from shapely.geometry import box
    xs, ys = zip(*xy)
    return box(min(xs) - folga, min(ys) - folga, max(xs) + folga, max(ys) + folga)


def deslizamentos(plano, caixa):
    """Cicatrizes de deslizamento perto da rede, em metros no plano."""
    with open(DESLIZAMENTOS, encoding="utf-8") as f:
        fc = json.load(f)
    gs = []
    for ft in fc["features"]:
        g = plano.de_lonlat(shape(ft["geometry"]))
        if g.intersects(caixa):
            gs.append(g.buffer(0))
    return unary_union(gs) if gs else None


def lugares(cidade, plano, caixa):
    """[(tipo, nome, geometria no plano)] dos lugares de reunião: OSM, escolas do cadastro estadual e abrigos."""
    out = []
    with open(osm_encontro(cidade), encoding="utf-8") as f:
        osm = json.load(f)
    for lg in osm["lugares"]:
        aneis = [[plano.xy(la, lo) for la, lo in a] for a in lg["aneis"]]
        g = unary_union([Point(a[0]) if len(a) < 3 else shapely.Polygon(a).buffer(0) if a[0] == a[-1] else LineString(a)
                         for a in aneis])
        out.append((lg["tipo"], lg.get("nome"), g))
    for arq, tipo in (("escolas.geojson", "escola_iede"), ("abrigos.geojson", "abrigo")):
        with open(os.path.join(SERVICOS, arq), encoding="utf-8") as f:
            for ft in json.load(f)["features"]:
                lo, la = ft["geometry"]["coordinates"][:2]
                out.append((tipo, ft["properties"].get("nome"), Point(plano.xy(la, lo))))
    return [x for x in out if not x[2].is_empty and x[2].intersects(caixa)]


def saida_seca(doc, xy, mancha):
    """Nós cuja rede de ruas fora da mancha chega à borda da rede mapeada: com a água no auge, dali ainda dá
    para sair da cidade sem atravessar água. Ponto fora disso vira ilha."""
    mp = prep(mancha)
    n = len(xy)
    adj = [[] for _ in range(n)]
    for a, b, *_ in doc["edges"]:
        if not mp.intersects(LineString([xy[a], xy[b]])):
            adj[a].append(b)
            adj[b].append(a)
    xs, ys = [p[0] for p in xy], [p[1] for p in xy]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    borda = [min(x - x0, x1 - x, y - y0, y1 - y) < BORDA_SAIDA_M for x, y in xy]
    ok, visto = [False] * n, [False] * n
    for s in range(n):
        if visto[s] or not adj[s]:
            continue
        comp, pilha = [], [s]
        visto[s] = True
        while pilha:
            u = pilha.pop()
            comp.append(u)
            for w in adj[u]:
                if not visto[w]:
                    visto[w] = True
                    pilha.append(w)
        if any(borda[u] for u in comp):
            for u in comp:
                ok[u] = True
    return ok


def tipo_das_arestas(doc, cidade, plano):
    """highway do OSM de cada trecho do painel (a via a até VIA_OSM_M do meio do trecho), ou None."""
    with open(osm_encontro(cidade), encoding="utf-8") as f:
        vias = [v for v in json.load(f)["vias"] if len(v["coords"]) >= 2]
    linhas = [LineString([plano.xy(la, lo) for la, lo in v["coords"]]) for v in vias]
    arvore = STRtree(linhas)
    nos = doc["nos"]
    tipos = []
    for a, b, *_ in doc["edges"]:
        (xa, ya), (xb, yb) = plano.xy(*nos[a]), plano.xy(*nos[b])
        meio = Point((xa + xb) / 2, (ya + yb) / 2)
        i = arvore.query_nearest(meio, max_distance=VIA_OSM_M, all_matches=False)
        tipos.append(vias[int(i[0])]["highway"] if len(i) else None)
    return tipos


def mancha_padrao(cidade, versao="mup"):
    return os.path.join(DADOS, VERSOES[versao]["mancha"].format(cidade=cidade))


def mancha_somada(cidade, versao="mup"):
    """Mancha que a versão soma à principal (ou None)."""
    v = VERSOES[versao].get("somar")
    return os.path.join(DADOS, v.format(cidade=cidade)) if v else None


def saida_padrao(cidade, versao="mup"):
    return os.path.join(DADOS, VERSOES[versao]["saida"].format(cidade=cidade))


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
    """União dos polígonos do(s) GeoJSON (WGS84), em metros no plano local."""
    gs = []
    for c in ([caminho] if isinstance(caminho, (str, os.PathLike)) else caminho):
        with open(c, encoding="utf-8") as f:
            fc = json.load(f)
        feats = fc["features"] if fc.get("type") == "FeatureCollection" else [fc]
        gs += [shape(f["geometry"]) for f in feats if f.get("geometry")]
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


def oficiais(cidade):
    """Pontos do plano de contingência e da Defesa Civil da cidade (assets/data/servicos/abrigos.geojson)."""
    with open(os.path.join(SERVICOS, "abrigos.geojson"), encoding="utf-8") as f:
        fs = json.load(f)["features"]
    return [{"nome": ft["properties"]["nome"], "tipo": ft["properties"].get("tipo"),
             "lon": ft["geometry"]["coordinates"][0], "lat": ft["geometry"]["coordinates"][1]}
            for ft in fs if ft["properties"].get("municipio") == CIDADES[cidade]["municipio"]]


def calcula(doc, mancha, plano, cidade, offset_m=OFFSET_M, criterios="v3", tempo_max_min=TEMPO_SUGERIDO_MIN,
            modo="algoritmo"):
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
    filtro = {"candidatos_v1": len(cand)}
    via_no, desl_no, lugar_no, bonus = {}, {}, {}, {}
    desl = None
    if criterios in ("v2", "v3"):
        caixa = _caixa(xy, 3000.0)
        tipos = tipo_das_arestas(doc, cidade, plano)
        for (a, b, *_), ok, tp in zip(doc["edges"], aresta_segura, tipos):
            if ok and tp:
                for k in (a, b):  # a melhor via da ponta: a de carro, se houver
                    if via_no.get(k) not in VIAS_CARRO:
                        via_no[k] = tp
        cand = [k for k in cand if via_no.get(k) in VIAS_CARRO]
        filtro["com_carro"] = len(cand)
        desl = deslizamentos(plano, caixa)
        for k in cand:
            desl_no[k] = desl.distance(Point(xy[k])) if desl is not None else INF
        cand = [k for k in cand if desl_no[k] > DESLIZAMENTO_M]
        filtro["longe_de_deslizamento"] = len(cand)
    sai = None
    if criterios == "v3":
        sai = saida_seca(doc, xy, mancha)
        cand = [k for k in cand if sai[k]]
        filtro["com_saida_seca"] = len(cand)
    if criterios in ("v2", "v3"):
        lgs = [x for x in lugares(cidade, plano, caixa) if not zona.contains(x[2])]
        arv = STRtree([g for _t, _n, g in lgs])
        for k in cand:
            i = arv.query_nearest(Point(xy[k]), max_distance=LUGAR_M, return_distance=True, all_matches=True)
            if len(i[0]):
                # o mais perto; empate: abrigo e escola antes, depois a ordem do arquivo
                ordem = sorted(zip(i[1], i[0]), key=lambda x: (round(x[0], 3), lgs[int(x[1])][0] not in ("abrigo", "escola_iede"), int(x[1])))
                dist, j = ordem[0]
                tp, nome, _g = lgs[int(j)]
                lugar_no[k] = {"tipo": NOME_LUGAR.get(tp, tp), "nome": nome, "dist_m": round(float(dist), 1)}
        bonus = {k: 1.0 + BONUS_LUGAR for k in lugar_no}
        filtro["com_lugar_de_reuniao"] = len(lugar_no)
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

    ruas = locais_altos._json(cfg["nomes"])["ruas"] if cfg.get("nomes") and os.path.exists(cfg["nomes"]) else []

    def meta(k):
        rr = locais_altos._rua_mais_proxima(ruas, nos[k], locais_altos.RAIO_RUA_M) if ruas else []
        m = {"rua": f"{rr[0][1]} com {rr[1][1]}" if len(rr) >= 2 else rr[0][1] if rr else None,
             "dist_mancha_m": round(mancha.distance(Point(xy[k])), 1)}
        if criterios in ("v2", "v3"):
            dd = desl_no.get(k, desl.distance(Point(xy[k])) if desl is not None else INF)
            m.update({"via": via_no.get(k), "dist_deslizamento_m": None if dd == INF else round(dd),
                      "lugar": lugar_no.get(k)})
        return m

    if criterios == "v3":
        return _calcula_cobertura(doc, nos, xy, z, casas, cand, meta, no_seguro, aresta_segura, zp, cidade, plano,
                                  filtro, tempo_max_min, modo, zona, mancha, sai)

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
    peso = np.array([bonus.get(k, 1.0) for k in cand])
    escolhidos = []
    while len(escolhidos) < PONTOS_MAX and len(cand) and len(pend):
        ganho = (atual[:, None] - np.minimum(atual[:, None], M)).sum(axis=0)
        # o bônus do lugar de reunião só desempata entre candidatos que já valem um ponto
        escolha = np.where(ganho / 60.0 >= GANHO_MIN_CASA_MIN, ganho * peso, -1.0)
        j = int(np.argmax(escolha))  # empate: o primeiro candidato (menor índice de nó)
        if escolha[j] < 0:
            break
        escolhidos.append(cand[j])
        atual = np.minimum(atual, M[:, j])
    # ponto escolhido cedo pode perder todas as casas para os seguintes: sai (não muda o tempo de ninguém)
    while escolhidos:
        cols = [cand.index(k) for k in escolhidos]
        sub = M[:, cols]
        alcanca = sub.min(axis=1) < TEMPO_TETO_S
        donos = set(int(x) for x in np.argmin(sub, axis=1)[alcanca])
        vazios = [k for i, k in enumerate(escolhidos) if i not in donos]
        if not vazios:
            break
        escolhidos = [k for k in escolhidos if k not in vazios]

    # cada nó da rede segue até o ponto mais perto (a página traça o caminho de qualquer toque)
    t, d, prox, dono = ate_os_pontos(radj, escolhidos)
    idx = {s: i for i, s in enumerate(escolhidos)}
    pontos = [{"id": f"encontro_{i + 1}", "lat": nos[s][0], "lon": nos[s][1], "no": s, **meta(s)}
              for i, s in enumerate(escolhidos)]
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
        pt["pessoas"] = round(math.fsum(ca["pessoas"] for ca in casas if ca["ponto"] == i))  # sum() mudou no Python 3.12
        pt["tempo_mediano_min"] = round(ts[len(ts) // 2] / 60, 1) if ts else None
        pt["tempo_max_min"] = round(ts[-1] / 60, 1) if ts else None
    return {"no_seguro": no_seguro, "aresta_segura": aresta_segura, "candidatos": len(cand), "filtro": filtro,
            "pontos": pontos, "casas_campos": CASAS_CAMPOS,
            "casas": saida_casas, "prox": prox, "tempo_no_s": [None if v == INF else round(v) for v in t],
            "ponto_no": [idx[o] if o >= 0 else -1 for o in dono], "zona": zona}


def rede_plano(doc, nos, xy, z, casas, cand, meta, no_seguro, zp, cidade, plano, mancha, sai=None):
    """Bloco "plano" do JSON: a rede em inteiros que plano_pontos.py e assets/js/pontos_plano.js usam."""
    arestas = []
    for a, b, *_ in doc["edges"]:
        d = haversine(nos[a][1], nos[a][0], nos[b][1], nos[b][0])
        dh = z[b] - z[a] if z[a] is not None and z[b] is not None else 0.0
        arestas.append([a, b, int(round(tempo_trecho(d, dh) * 10)), int(round(tempo_trecho(d, -dh) * 10)), int(round(d * 10))])
    cs = []
    for ca in casas:
        ok = ca["no"] is not None and ca["no"] >= 0 and ca["d0"] is not None
        cs.append([ca["no"] if ok else -1, int(round(ca["d0"] / VEL_IDOSO * 10)) if ok else 0,
                   round(ca["d0"], 1) if ok else 0, round(ca["pessoas"], 2), int(ca["estado"] in ("mancha", "faixa"))])
    ofs = []
    for o in oficiais(cidade):
        p = plano.xy(o["lat"], o["lon"])
        k = min(range(len(nos)), key=lambda i: ((xy[i][0] - p[0]) ** 2 + (xy[i][1] - p[1]) ** 2, i))
        fora = bool(no_seguro[k] and not zp.contains(Point(p)))
        ilha = bool(fora and sai is not None and not sai[k])
        ofs.append({**o, "no": k, "dist_no_m": round(math.dist(p, xy[k]), 1), "ilhado": ilha,
                    "seguro": fora and not ilha, **meta(k),
                    "dist_mancha_m": round(mancha.distance(Point(p)), 1)})  # do ponto oficial, não do nó
    return {"n_nos": len(nos), "arestas": arestas, "casas": cs, "candidatos": [{"no": k, **meta(k)} for k in cand],
            "oficiais": ofs, "tempo_sugerido_min": TEMPO_SUGERIDO_MIN, "modos": list(plano_pontos.MODOS),
            "pontos_max": plano_pontos.PONTOS_MAX}


def oficiais_seguros(rede):
    """Os oficiais que o plano usa, na ordem dele (fora da área insegura; um por nó)."""
    out, vistos = [], set()
    for o in rede["oficiais"]:
        if o["seguro"] and o["no"] not in vistos:
            vistos.add(o["no"])
            out.append(o)
    return out


def pontos_do_plano(rede, r):
    """Pontos (com o que a página mostra) e casas no formato do JSON, a partir de plano_pontos.planeja."""
    teto = r["tempo_max_min"] * 600
    pontos = []
    for i, p in enumerate(r["pontos"]):
        base = oficiais_seguros(rede)[p["indice"]] if p["origem"] == "plano" else rede["candidatos"][p["indice"]]
        info = {k: v for k, v in base.items() if k not in ("seguro", "dist_no_m")}
        ts = sorted(c[1] for c in r["casas"] if c[0] == i)
        pess = [rede["casas"][j][3] for j, c in enumerate(r["casas"]) if c[0] == i]
        pontos.append({"id": f"encontro_{i + 1}", "origem": p["origem"], **info,
                       "lat": base.get("lat", None), "lon": base.get("lon", None),
                       "n_casas": len(ts), "n_casas_no_limite": sum(1 for t in ts if t <= teto),
                       "pessoas": round(math.fsum(pess)),
                       "tempo_mediano_min": round(ts[len(ts) // 2] / 600, 1) if ts else None,
                       "tempo_max_min": round(ts[-1] / 600, 1) if ts else None})
    return pontos


def _calcula_cobertura(doc, nos, xy, z, casas, cand, meta, no_seguro, aresta_segura, zp, cidade, plano, filtro,
                       tempo_max_min, modo, zona, mancha, sai):
    rede = rede_plano(doc, nos, xy, z, casas, cand, meta, no_seguro, zp, cidade, plano, mancha, sai)
    r = plano_pontos.planeja(rede, tempo_max_min, modo)
    pontos = pontos_do_plano(rede, r)
    for p, q in zip(pontos, r["pontos"]):
        if p["lat"] is None or p["origem"] == "algoritmo":  # o ponto fica no nó da rede
            p["lat"], p["lon"] = nos[q["no"]]
    saida_casas = []
    for ca, (pk, tds, dm, alc, _arv) in zip(casas, r["casas"]):
        saida_casas.append([ca["lat"], ca["lon"], ESTADOS.index(ca["estado"]), pk,
                            None if tds is None else round(tds / 10), dm, alc])
    filtro = {**filtro, "oficiais": len(rede["oficiais"]), "oficiais_seguros": sum(o["seguro"] for o in rede["oficiais"])}
    return {"no_seguro": no_seguro, "aresta_segura": aresta_segura, "candidatos": len(cand), "filtro": filtro,
            "pontos": pontos, "casas_campos": CASAS_CAMPOS + ["alcance"], "casas": saida_casas,
            "prox": r["prox"], "ponto_no": r["ponto_no"],
            "tempo_no_s": [None if v is None else round(v / 10) for v in r["tempo_no_ds"]], "zona": zona,
            "plano": {**rede, "padrao": {"tempo_max_min": tempo_max_min, "modo": modo}, "resumo": r["resumo"]}}


def geojson_contorno(g, plano):
    g = plano.para_lonlat(g.simplify(SIMPLIFICA_M, preserve_topology=True))

    def arred(c):
        return [arred(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 6), round(c[1], 6)]
    m = mapping(g)
    return {"type": m["type"], "coordinates": arred(m["coordinates"])}


def documento(cidade, caminho_mancha=None, offset_m=OFFSET_M, fonte=None, versao="mup", criterios="v3",
              tempo_max_min=TEMPO_SUGERIDO_MIN, modo="algoritmo"):
    """JSON da página dos pontos de encontro (pontos_encontro.html?cidade=...&mancha=<versao>)."""
    cfg, v = CIDADES[cidade], VERSOES[versao]
    somada = mancha_somada(cidade, versao) if caminho_mancha is None else None
    caminho_mancha = caminho_mancha or mancha_padrao(cidade, versao)
    fonte = fonte or v["fonte"][cidade]
    doc = locais_altos.payload(cfg["painel"])
    plano = Plano(doc["nos"])
    mancha = le_mancha([caminho_mancha] + ([somada] if somada else []), plano)
    r = calcula(doc, mancha, plano, cidade, offset_m, criterios, tempo_max_min, modo)
    # recorte do desenho à volta da rede (a mancha do estado vai além)
    xs, ys = zip(*(plano.xy(la, lo) for la, lo in doc["nos"]))
    caixa = LineString([(min(xs) - 1500, min(ys) - 1500), (max(xs) + 1500, max(ys) + 1500)]).envelope
    est = [c[2] for c in r["casas"]]
    criterio = (f"ponto de encontro = trecho de via (OpenStreetMap) inteiro fora da mancha com {offset_m:g} m de "
                "afastamento")
    if criterios == "v3":
        criterio += ", com saída seca (ruas fora da mancha que levam para fora da cidade)"
    if criterios in ("v2", "v3"):
        criterio += (f", onde passa carro, a mais de {DESLIZAMENTO_M:g} m de cicatriz de deslizamento" +
                     (f"; praça, campo, escola, ginásio ou estacionamento a até {LUGAR_M:g} m só desempata"
                      if criterios == "v3" else
                      f", com preferência para praça, campo, escola, ginásio ou estacionamento a até {LUGAR_M:g} m"))
    if criterios == "v3":
        criterio += (f"; o menor número de pontos que leva as casas da mancha e da faixa a um ponto em até "
                     f"{tempo_max_min:g} min a pé no passo do idoso (r.walk, 0,9 m/s)")
    else:
        criterio += "; escolhidos pelo que mais poupa caminhada do idoso (r.walk, 0,9 m/s)"
    extra = {}
    if criterios in ("v2", "v3"):
        with open(osm_encontro(cidade), encoding="utf-8") as f:
            osm = json.load(f)
        extra = {"osm_encontro": {"arquivo": os.path.relpath(osm_encontro(cidade), RAIZ),
                                  "sha256": _sha256(osm_encontro(cidade)), "osm_base": osm.get("osm_base")},
                 "deslizamentos_arquivo": os.path.relpath(DESLIZAMENTOS, RAIZ),
                 "parametros": {"deslizamento_m": DESLIZAMENTO_M, "lugar_m": LUGAR_M, "bonus_lugar": BONUS_LUGAR,
                                "vias_carro": sorted(VIAS_CARRO)}}
    return {
        "schema_version": f"previne_pontos_encontro_{criterios}",
        "criterios": criterios, **extra,
        "municipio": cfg["municipio"], "versao": versao,
        "mancha_rotulo": v["rotulo"], "mancha_titulo": v["titulo"], "mancha_observada": v["observada"],
        "evento": v["evento"][cidade], "evento_curto": v["evento_curto"][cidade],
        "criterio": criterio,
        "fonte_mancha": fonte, "mancha_arquivo": os.path.relpath(caminho_mancha, RAIZ),
        "mancha_sha256": _sha256(caminho_mancha), "offset_m": offset_m,
        **({"mancha_somada": {"arquivo": os.path.relpath(somada, RAIZ), "sha256": _sha256(somada)}} if somada else {}),
        "aviso": v["aviso"],
        "resumo": {"casas": len(est), "fora": est.count(0), "faixa": est.count(1), "mancha": est.count(2),
                   "sem_via": est.count(3), "nos_seguros": sum(r["no_seguro"]), "nos": len(doc["nos"]),
                   "trechos_seguros": sum(r["aresta_segura"]), "trechos": len(doc["edges"]),
                   "candidatos": r["candidatos"], "filtro": r["filtro"]},
        "nos": doc["nos"],
        "arestas": [[a, b, int(ok)] for (a, b, *_), ok in zip(doc["edges"], r["aresta_segura"])],
        "prox": r["prox"], "ponto_no": r["ponto_no"], "tempo_no_s": r["tempo_no_s"],
        "estados": list(ESTADOS), "casas_campos": r["casas_campos"], "casas": r["casas"],
        "pontos": r["pontos"], **({"plano": r["plano"]} if "plano" in r else {}),
        "mancha": geojson_contorno(mancha.intersection(caixa), plano),
        "faixa": geojson_contorno(r["zona"].intersection(caixa), plano),
    }


def resumo(d):
    s = d["resumo"]
    linhas = [f"{d['municipio']}: {s['casas']} casas · fora {s['fora']}, na faixa de {d['offset_m']:g} m {s['faixa']}, "
              f"na mancha {s['mancha']}, sem via {s['sem_via']} · trechos seguros {s['trechos_seguros']}/{s['trechos']} · "
              f"candidatos {s['candidatos']} {s.get('filtro', '')} · pontos {len(d['pontos'])}"]
    for p in d["pontos"]:
        linhas.append(f"  {p['id']}: {p['lat']:.6f}, {p['lon']:.6f} · {p['rua'] or 'rua sem nome'} · "
                      f"{p['dist_mancha_m']:.0f} m da mancha · {p['n_casas']} casas, ~{p['pessoas']} pessoas, "
                      f"mediana {p['tempo_mediano_min']} min, máx {p['tempo_max_min']} min"
                      + (f" · via {p['via']} · deslizamento a {p['dist_deslizamento_m']} m · "
                         f"{(p['lugar'] or {}).get('tipo') or 'sem lugar de reunião'}"
                         + (f" ({p['lugar']['nome']})" if p.get('lugar') and p['lugar'].get('nome') else '')
                         if 'via' in p else ""))
    return "\n".join(linhas)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cidade", choices=sorted(CIDADES))
    ap.add_argument("--versao", choices=sorted(VERSOES), default="mup", help="mup (mapa único) ou hand (modelo do projeto)")
    ap.add_argument("--mancha", help="GeoJSON da área insegura (padrão: o da versão em assets/data/rota_fuga/)")
    ap.add_argument("--offset", type=float, default=OFFSET_M, help="afastamento da mancha, em metros")
    ap.add_argument("--fonte", help="descrição da mancha (padrão: a da versão; vai para o JSON e para a página)")
    ap.add_argument("--criterios", choices=CRITERIOS, default="v3",
                    help="v3: menos pontos dentro do tempo máximo; v2: carro, deslizamento e lugar de reunião")
    ap.add_argument("--tempo-max", type=int, default=TEMPO_SUGERIDO_MIN, help="v3: tempo máximo a pé, em minutos inteiros")
    ap.add_argument("--modo", choices=plano_pontos.MODOS, default="algoritmo", help="v3: quem define os pontos")
    ap.add_argument("--gravar", action="store_true", help="grava assets/data/rota_fuga/<cidade>_pontos_encontro_<versao>.json")
    a = ap.parse_args()
    d = documento(a.cidade, a.mancha, a.offset, a.fonte, a.versao, a.criterios, a.tempo_max, a.modo)
    print(resumo(d))
    if a.gravar:
        saida = saida_padrao(a.cidade, a.versao)
        with open(saida, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
        print("gravado:", os.path.relpath(saida, RAIZ))


if __name__ == "__main__":
    main()
