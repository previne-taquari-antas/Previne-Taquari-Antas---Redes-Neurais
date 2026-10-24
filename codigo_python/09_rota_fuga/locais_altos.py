#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Locais altos sugeridos: onde a água não chegou na maior cheia registrada.

Santa Tereza: set/2023 é a maior cheia medida (régua 23,65 m na telemetria ANA
86472600; 24,04 m na cota nivelada pelo SGB). Mai/2024 ficou em 22,42 m (SGB) e
nov/2023 em 21,61 m. Na validação de campo do HAND (05/09/2026: marcas de cheia
e limites de set/2023, nov/2023 e mai/2024 com GNSS RTK; trabalho do SBSR 2027,
pesquisas/validacao-campo-hand-santa-tereza/), o zero 1,60 m da régua anula o
viés de set/2023 e põe a cheia em HAND 22,05 m.

Um ponto é ALTO quando passa nos dois testes, ambos com 2 m de folga:
  1. HAND: só alaga acima de HAND 24,05 m (régua 25,65 m), ou não alaga até o
     topo do modelo (HAND 25 m, régua 26,6 m);
  2. altitude no LiDAR de 10 m (o mesmo do HAND) de pelo menos 78,47 m: a maior
     cota da água medida com RTK em set/2023 (76,47 m, no limite H004) + 2 m.
     Pega o que o HAND deixa seco só por ficar atrás de uma barreira no LiDAR
     (o remanso do Marrecão ainda não foi validado).
Folga de 2 m: nos pontos com RTK, o maior erro no sentido perigoso (água acima
do modelo) foi 1,84 m (H004); o MAE das 22 profundidades, 0,64 m.

Locais sugeridos (para a Defesa Civil avaliar): nós altos da rede de ruas,
escolhidos um a um pelo que mais encurta a caminhada das casas que não ficam
no alto. O local pede 1 m a mais de altitude (79,47 m), para não ficar na beira
da água. Cada casa vai pelo caminho mais rápido entre os que continuam secos
pelo menos até a água chegar na própria casa; se nenhum continua, pelo que
fica seco até o nível mais alto possível, e a casa precisa sair antes dele
(`corte_m`). Tempo do idoso com subidas (caminhada.py) no mesmo LiDAR.

Só numpy e Pillow: lê o painel publicado e a grade LiDAR em PNG. Nomes das
ruas e dos lugares próximos, quando houver, de osm_nomes_<cidade>.json
(baixar_nomes_osm.py).

  python codigo_python/09_rota_fuga/locais_altos.py   # resumo, sem gravar
"""
import heapq
import json
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from caminhada import VEL_IDOSO, haversine, tempo_trecho  # noqa: E402

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INF = math.inf

CIDADES = {
    "santa_tereza": {
        "painel": os.path.join(RAIZ, "santa_tereza_painel_casas.html"),
        "lidar": os.path.join(RAIZ, "assets", "data", "santa_tereza_inundacao", "mdt", "altitude_terreno_lidar_10m.json"),
        "nomes": os.path.join(RAIZ, "assets", "data", "rota_fuga", "osm_nomes_santa_tereza.json"),
        "servicos": [os.path.join(RAIZ, "assets", "data", "servicos", f"{s}.geojson") for s in ("escolas", "ubs")],
        "municipio": "Santa Tereza",
        "cheia": {"rotulo": "set/2023", "data": "2023-09-04", "regua_m": 23.65, "regua_sgb_m": 24.04,
                  "zero_regua_m": 1.60, "hand_m": 22.05,
                  "agua_max_rtk_m": 76.47, "ponto_agua_max": "H004",
                  "erro_max_perigoso_m": 1.84, "mae_profundidade_m": 0.64, "n_profundidades": 22,
                  "fonte": "validação de campo de 05/09/2026 (marcas e limites com RTK), "
                           "pesquisas/validacao-campo-hand-santa-tereza/; SBSR 2027"},
        "folga_hand_m": 2.0,
        "folga_altitude_m": 2.0,
        "folga_local_m": 1.0,
    },
}
GANHO_MIN_CASA_MIN = 150.0   # novo local precisa poupar 150 casa·min (~30 casas × 5 min)
LOCAIS_MAX = 8
TEMPO_TETO_S = 3600.0        # casa sem local até aqui conta 60 min no guloso
RAIO_RUA_M = 25.0            # nome da rua do local: trecho com nome a até 25 m
RAIO_LUGAR_M = 150.0         # lugares com nome perto do local
ESTADOS = ("sem_via", "no_alto", "rota")


def payload(html_path):
    s = open(html_path, encoding="utf-8").read()
    return json.JSONDecoder().raw_decode(s, s.index("const D=") + len("const D="))[0]


class Lidar:
    """Altitude (m) da grade LiDAR de 10 m do site (PNG RG em decímetros)."""

    def __init__(self, meta_path):
        m = json.load(open(meta_path, encoding="utf-8"))
        if m.get("codificacao") != "uint16_decimetros_em_rg" or not m.get("same_source_as_hand"):
            raise SystemExit(f"{meta_path}: grade inesperada (precisa ser o LiDAR do HAND, uint16 em RG)")
        im = np.asarray(Image.open(os.path.join(os.path.dirname(meta_path), m["png"])).convert("RGBA")).astype(np.int64)
        self.z = (im[..., 0] * 256 + im[..., 1]) * float(m["escala"])
        self.ok = im[..., 3] > 0
        self.m = m

    def __call__(self, lat, lon):
        m = self.m
        x = int((lon - m["W"]) / (m["E"] - m["W"]) * m["cols"])
        y = int((m["N"] - lat) / (m["N"] - m["S"]) * m["rows"])
        if 0 <= x < m["cols"] and 0 <= y < m["rows"] and self.ok[y, x]:
            return round(float(self.z[y, x]), 1)
        return None


def _dist(a, b):
    return haversine(a[1], a[0], b[1], b[0])


def _cota(v):
    return INF if v is None else float(v)


def criterios(cfg):
    ch = cfg["cheia"]
    return {"hand_min_m": round(ch["hand_m"] + cfg["folga_hand_m"], 2),
            "altitude_min_m": round(ch["agua_max_rtk_m"] + cfg["folga_altitude_m"], 2),
            "altitude_min_local_m": round(ch["agua_max_rtk_m"] + cfg["folga_altitude_m"] + cfg["folga_local_m"], 2)}


def grafo(doc, z):
    """Lista de adjacência dirigida: (vizinho, segundos, metros, cota em que o trecho alaga)."""
    nos = doc["nos"]
    adj = [[] for _ in nos]
    for a, b, _ag, pe, cz in doc["edges"]:
        d = _dist(nos[a], nos[b])
        dh = z[b] - z[a] if z[a] is not None and z[b] is not None else 0.0
        c = _cota(cz)
        adj[a].append((b, tempo_trecho(d, dh), d, c))
        adj[b].append((a, tempo_trecho(d, -dh), d, c))
    return adj


def gargalo(adj, cota_no, alvos):
    """Para cada nó, o maior nível que um caminho até algum alvo aguenta seco (máx-mín)."""
    B = [-INF] * len(adj)
    pq = []
    for k in alvos:
        B[k] = INF
        pq.append((-INF, k))
    heapq.heapify(pq)
    while pq:
        nb, u = heapq.heappop(pq)
        nb = -nb
        if nb < B[u]:
            continue
        for v, _t, _d, c in adj[u]:
            w = min(nb, c, cota_no[v])
            if w > B[v]:
                B[v] = w
                heapq.heappush(pq, (-w, v))
    return B


def caminhos(adj, cota_no, origem, t0, d0, limiar, alvos):
    """Dijkstra só por trechos e nós que alagam em `limiar` ou acima; tempo até cada alvo."""
    tempo, dist, ant = {origem: t0}, {origem: d0}, {origem: -1}
    pq = [(t0, origem)]
    achados = {}
    while pq:
        t, u = heapq.heappop(pq)
        if t > tempo[u]:
            continue
        if u in alvos:
            achados[u] = t
        for v, tv, dv, c in adj[u]:
            if c < limiar or cota_no[v] < limiar:
                continue
            nt = t + tv
            if nt < tempo.get(v, INF):
                tempo[v], dist[v], ant[v] = nt, dist[u] + dv, u
                heapq.heappush(pq, (nt, v))
    return achados, dist, ant


def _rota(ant, fim):
    out = []
    while fim >= 0:
        out.append(fim)
        fim = ant[fim]
    return out[::-1]


def _rua_mais_proxima(ruas, p, raio):
    """[(distância, nome)] dos trechos com nome a até `raio` m do ponto, um por nome."""
    clat = math.cos(math.radians(p[0]))
    melhor = {}
    for r in ruas:
        cs = r["coords"]
        for (la1, lo1), (la2, lo2) in zip(cs, cs[1:]):
            ax, ay = (lo1 - p[1]) * clat * 111320, (la1 - p[0]) * 110540
            bx, by = (lo2 - p[1]) * clat * 111320, (la2 - p[0]) * 110540
            dx, dy = bx - ax, by - ay
            L = dx * dx + dy * dy
            f = 0.0 if L == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L))
            d = math.hypot(ax + f * dx, ay + f * dy)
            if d <= raio and d < melhor.get(r["nome"], INF):
                melhor[r["nome"]] = d
    return sorted((d, n) for n, d in melhor.items())


def lugares_conhecidos(cfg):
    """Lugares com nome: OSM (osm_nomes_<cidade>.json) + escolas e UBS de assets/data/servicos."""
    out = []
    if os.path.exists(cfg["nomes"]):
        for p in json.load(open(cfg["nomes"], encoding="utf-8"))["lugares"]:
            if "place" in p["tags"]:  # localidade (vila, linha, município), não é lugar de referência
                continue
            out.append({"nome": p["nome"], "lat": p["lat"], "lon": p["lon"], "fonte": "OSM " + p["osm"]})
    for caminho in cfg["servicos"]:
        for f in json.load(open(caminho, encoding="utf-8"))["features"]:
            pr = f["properties"]
            if pr.get("municipio") != cfg["municipio"] and cfg["municipio"] not in json.dumps(pr, ensure_ascii=False):
                continue
            lon, lat = f["geometry"]["coordinates"][:2]
            out.append({"nome": nome_cadastro(pr.get("nome") or pr.get("name") or "", cfg["municipio"]),
                        "lat": lat, "lon": lon, "fonte": os.path.basename(caminho)})
    return out


SIGLAS = {"ESF", "UBS", "EMEI", "EMEF", "EEEF", "EEEM", "CEI"}
MINUSCULAS = {"de", "da", "do", "das", "dos", "e"}
ABREV = {"ESC": "Escola", "EST": "Estadual", "ENS": "Ensino", "MED": "Médio", "FUND": "Fundamental"}


def nome_cadastro(s, municipio):
    """'ESF SANTA TEREZA SANTA TEREZA' -> 'ESF Santa Tereza' (cadastros em maiúsculas)."""
    s = " ".join(s.split())
    dup = f"{municipio} {municipio}".upper()
    if s.upper().endswith(dup):
        s = s[: -len(dup)] + municipio
    out = []
    for i, w in enumerate(s.split()):
        u = w.upper()
        out.append(u if u in SIGLAS else ABREV.get(u) or (w.lower() if i and w.lower() in MINUSCULAS else w.capitalize()))
    return " ".join(out)


def nomeia(local, ruas, lugares, z):
    p = (local["lat"], local["lon"])
    rr = _rua_mais_proxima(ruas, p, RAIO_RUA_M) if ruas else []
    perto = sorted((round(_dist(p, (q["lat"], q["lon"]))), q["nome"]) for q in lugares if q["nome"])
    perto = [{"nome": n, "m": d} for d, n in perto if d <= RAIO_LUGAR_M][:3]
    if len(rr) >= 2:
        nome = f"{rr[0][1]} com {rr[1][1]}"
    elif rr:
        nome = rr[0][1]
    else:
        nome = None
    local["rua"] = nome
    local["perto"] = perto


def calcula(doc, cidade="santa_tereza"):
    """Locais altos do painel `doc` (payload de gerar_painel.py). Determinístico."""
    cfg = CIDADES[cidade]
    crit = criterios(cfg)
    lidar = Lidar(cfg["lidar"])
    nos = doc["nos"]
    F = {k: i for i, k in enumerate(doc["meta"]["casas_campos"])}
    cota_no = [_cota(c) for c in doc["cota_no"]]
    z = [lidar(la, lo) for la, lo in nos]

    def alto(c, zz, z_min):
        return c >= crit["hand_min_m"] and zz is not None and zz >= z_min

    no_alto = [alto(cota_no[k], z[k], crit["altitude_min_m"]) for k in range(len(nos))]
    sitios = {k for k in range(len(nos)) if no_alto[k] and z[k] >= crit["altitude_min_local_m"]}
    adj = grafo(doc, z)
    B = gargalo(adj, cota_no, [k for k in range(len(nos)) if no_alto[k]])

    casas = []
    for c in doc["casas"]:
        la, lo, n = c[F["lat"]], c[F["lon"]], c[F["no"]]
        cc = _cota(c[F["cota_alaga"]])
        zc = lidar(la, lo)
        item = {"cota": cc, "z": zc, "pessoas": c[F["pessoas"]] or 0}
        if alto(cc, zc, crit["altitude_min_m"]):
            item["estado"] = "no_alto"
        elif n is None or n < 0 or c[F["proj_lat"]] is None:
            item["estado"] = "sem_via"
        else:
            proj = (c[F["proj_lat"]], c[F["proj_lon"]])
            d0 = _dist((la, lo), proj) + _dist(proj, nos[n])
            limiar = min(cc, B[n])
            achados, dist, ant = caminhos(adj, cota_no, n, d0 / VEL_IDOSO, d0, limiar, sitios)
            item.update(estado="rota" if achados else "sem_via", no=n, limiar=limiar,
                        achados=achados, dist=dist, ant=ant)
        casas.append(item)

    # guloso: cada local novo é o que mais poupa caminhada (casa·min, teto de 60 min)
    pend = [i for i, it in enumerate(casas) if it["estado"] == "rota"]
    atual = {i: TEMPO_TETO_S for i in pend}
    escolhidos = []
    while len(escolhidos) < LOCAIS_MAX:
        ganho = {}
        for i in pend:
            for s, t in casas[i]["achados"].items():
                g = atual[i] - min(atual[i], t)
                if g > 0:
                    ganho[s] = ganho.get(s, 0.0) + g
        if not ganho:
            break
        s, g = max(ganho.items(), key=lambda kv: (kv[1], -kv[0]))
        if g / 60.0 < GANHO_MIN_CASA_MIN:
            break
        escolhidos.append(s)
        for i in pend:
            atual[i] = min(atual[i], casas[i]["achados"].get(s, INF))

    ruas = json.load(open(cfg["nomes"], encoding="utf-8"))["ruas"] if os.path.exists(cfg["nomes"]) else []
    lugares = lugares_conhecidos(cfg)
    idx = {s: j for j, s in enumerate(escolhidos)}
    locais = []
    for j, s in enumerate(escolhidos):
        loc = {"id": f"alto_{j + 1}", "lat": nos[s][0], "lon": nos[s][1], "no": s,
               "cota_alaga_m": None if cota_no[s] == INF else cota_no[s], "altitude_m": z[s],
               "folga_altitude_m": round(z[s] - cfg["cheia"]["agua_max_rtk_m"], 1),
               "folga_hand_m": None if cota_no[s] == INF else round(cota_no[s] - cfg["cheia"]["hand_m"], 1)}
        nomeia(loc, ruas, lugares, z)
        locais.append(loc)

    saida_casas = []
    for it in casas:
        if it["estado"] != "rota":
            saida_casas.append([ESTADOS.index(it["estado"]), -1, None, None, None, None])
            continue
        alc = [(t, s) for s, t in it["achados"].items() if s in idx]
        if not alc:  # nenhum local escolhido alcança: fica com o nó alto mais próximo
            alc = [min((t, s) for s, t in it["achados"].items())]
        t, s = min(alc)
        rota = _rota(it["ant"], s)
        corte = min([INF] + [c for u, v in zip(rota, rota[1:]) for w, _t, _d, c in adj[u] if w == v]
                    + [cota_no[k] for k in rota])
        saida_casas.append([ESTADOS.index("rota"), idx.get(s, -1), round(t), round(it["dist"][s], 1),
                            None if corte == INF else round(corte, 1), rota])

    for j, loc in enumerate(locais):
        ts = sorted(c[2] for c in saida_casas if c[1] == j)
        loc["n_casas"] = len(ts)
        loc["pessoas"] = round(sum(casas[i]["pessoas"] for i, c in enumerate(saida_casas) if c[1] == j))
        loc["tempo_mediano_min"] = round(ts[len(ts) // 2] / 60, 1) if ts else None
        loc["tempo_max_min"] = round(ts[-1] / 60, 1) if ts else None

    ch = cfg["cheia"]
    return {
        "meta": {"cheia": ch, "criterios": crit, "folga_hand_m": cfg["folga_hand_m"],
                 "folga_altitude_m": cfg["folga_altitude_m"], "folga_local_m": cfg["folga_local_m"],
                 "lidar": os.path.relpath(cfg["lidar"], RAIZ),
                 "nomes": os.path.relpath(cfg["nomes"], RAIZ) if ruas else None,
                 "casas_campos": ["estado", "local", "tempo_s", "dist_m", "corte_m", "rota"],
                 "estados": list(ESTADOS)},
        "locais": locais,
        "no_alto": [int(v) for v in no_alto],
        "casas": saida_casas,
    }


def resumo(alt, doc):
    cs = alt["casas"]
    F = {k: i for i, k in enumerate(doc["meta"]["casas_campos"])}
    est = [ESTADOS[c[0]] for c in cs]
    rot = [(c, _cota(doc["casas"][i][F["cota_alaga"]])) for i, c in enumerate(cs) if c[0] == ESTADOS.index("rota")]
    ts = sorted(c[2] / 60 for c, _ in rot)
    linhas = [f"nós altos: {sum(alt['no_alto'])}/{len(alt['no_alto'])} · casas no alto: {est.count('no_alto')}, "
              f"com rota: {len(rot)}, sem via: {est.count('sem_via')}"]
    if ts:
        antes = sum(1 for c, cc in rot if c[4] is not None and c[4] < cc)
        linhas.append(f"tempo até o local (idoso): mediana {ts[len(ts) // 2]:.1f} min, p90 {ts[int(0.9 * (len(ts) - 1))]:.1f}, "
                      f"máx {ts[-1]:.1f} · rota cortada antes de a água chegar na casa: {antes}")
    for loc in alt["locais"]:
        linhas.append(f"  {loc['id']}: {loc['lat']:.6f},{loc['lon']:.6f} alt {loc['altitude_m']} m "
                      f"(+{loc['folga_altitude_m']} m) · {loc['n_casas']} casas, ~{loc['pessoas']} pessoas, "
                      f"mediana {loc['tempo_mediano_min']} min, máx {loc['tempo_max_min']} min · "
                      f"{loc['rua'] or 'rua sem nome'} · perto: {', '.join(p['nome'] + f' ({p['m']} m)' for p in loc['perto']) or '-'}")
    return "\n".join(linhas)


if __name__ == "__main__":
    cid = sys.argv[1] if len(sys.argv) > 1 else "santa_tereza"
    d = payload(CIDADES[cid]["painel"])
    print(resumo(calcula(d, cid), d))
