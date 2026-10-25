#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Locais altos sugeridos: onde a água não chegou na maior cheia registrada.

Santa Tereza: set/2023 é a maior cheia medida (régua 23,65 m na telemetria ANA
86472600; 24,04 m na cota nivelada pelo SGB). Mai/2024 ficou em 22,42 m (SGB) e
nov/2023 em 21,61 m. Na validação de campo do HAND (05/09/2026: marcas de cheia
e limites de set/2023, nov/2023 e mai/2024 com GNSS RTK; trabalho do SBSR 2027,
pesquisas/validacao-campo-hand-santa-tereza/), o zero 1,60 m da régua anula o
viés de set/2023 e põe a cheia em HAND 22,05 m. As métricas do artigo (MAE 0,64 m,
erro perigoso de 1,84 m) são do HAND krigado de 1 m; o painel usa o HAND D8 de 5 m
(contornos_mancha.json), que nos 19 vértices RTK válidos tem viés +0,69 m, MAE
1,02 m e erro perigoso máximo de 1,25 m (H007: o HAND põe a água 1,25 m abaixo).

TERRENO ALTO = o que ficou FORA da mancha de set/2023, visto no MDT (LiDAR de
10 m, o mesmo do HAND; a mancha é rasterizada pelo centro do pixel):
  - água na borda = mediana, num raio de 300 m, do meio entre o pixel de
    dentro e os de fora da borda externa da mancha (o pixel de dentro sozinho
    fica ~1 m abaixo da água em barranco), levada a cada pixel pela borda mais
    próxima;
  - nível da água = o maior entre a borda e a maior água medida em campo
    (76,47 m). Na cidade a água de 2023 ficou plana e, em três limites, 1,4 a
    1,8 m acima da borda do HAND; a borda sozinha baixa para 72–73 m no sul;
  - fora da mancha, o pixel é "alto" se o terreno fica pelo menos 2 m acima do
    nível da água; "abaixo da água" quando fica abaixo da água na borda sem
    estar na mancha (atrás de aterro ou barreira no modelo: pode ter alagado; o
    remanso do Marrecão ainda não foi validado); o resto é "sem folga" (fora da
    mancha, mas sem 2 m sobre a água estimada; pode ficar abaixo de 76,47 m);
  - casa ou rua que o HAND alaga com menos de 2 m sobre a cheia (HAND < 24,05 m)
    não é "alta", mesmo com o MDT alto: os dois modelos discordam em ±1–2 m.
Folga de 2 m: o erro que conta aqui é o do terreno de 10 m. LiDAR 10 m − RTK nos
19 vértices: NMAD 0,71 m, máximo +1,46 m (H003, um limite de set/2023: a água
chegou lá e o LiDAR o põe 1,23 m acima do nível de 76,47 m; com folga de 1 m ele
seria "alto"). O HAND krigado do artigo tem MAE 0,64 m e erro perigoso máximo de
1,84 m (H004, já dentro do nível de 76,47 m).

Ilhas: um local ou uma casa no alto pode ficar sem saída seca. `ilha_m` é o nível
(HAND) em que a última ligação seca com as saídas da cidade (ruas que deixam o
recorte em terreno alto) é cortada.

Locais sugeridos (para a Defesa Civil avaliar): nós de rua em terreno alto,
escolhidos um a um pelo que mais encurta a caminhada das casas que não ficam
no alto. O local pede 1 m a mais (3 m acima da água) no pixel mais baixo do
entorno de 3×3 (30 m: a grade de 10 m é o vizinho mais próximo do LiDAR de 1 m e
erra ±1–2 m em declive) e fica a mais de 100 m das cicatrizes de deslizamento
do inventário de 2024 (landslides_poly.geojson): na chuva que enche o rio, o pé
do morro também é perigoso.
Nós de rua e casas que o HAND alaga na cheia ficam "dentro" mesmo que o pixel
de 10 m na borda caia fora da mancha. Cada casa vai pelo caminho mais rápido
entre os que continuam secos pelo menos até a água chegar na própria casa; se
nenhum continua, pelo que
fica seco até o nível mais alto possível, e a casa precisa sair antes dele
(`corte_m`). O acesso da casa até a rua (até o pé da perpendicular e dali ao
nó) entra no corte: `doc["acesso_cota"]`, o nível HAND em que esse trecho
alaga, vem dos contornos (gerar_painel.cota_acesso). Tempo do idoso com subidas
(caminhada.py) no mesmo LiDAR.

Saídas da cidade (para as ilhas): pontas de rua altas na borda da rede e pontas
de via principal (primary/secondary/tertiary do OSM) que seguem para fora dela,
como a Estrada do Vinho, que a rede de ruas corta a 600 m da borda.

Só numpy e Pillow: lê o painel publicado, a grade LiDAR em PNG e a mancha da
cheia (contorno HAND recortado por gerar_painel.mancha_cheia). Nomes das ruas e
dos lugares próximos, quando houver, de osm_nomes_<cidade>.json
(baixar_nomes_osm.py).

  python codigo_python/09_rota_fuga/locais_altos.py   # resumo, sem gravar
"""
import base64
import heapq
import io
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

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
                  # métricas do artigo: HAND krigado de 1 m (outro produto, não o do painel)
                  "hand_krigado_artigo": {"erro_max_perigoso_m": 1.84, "mae_profundidade_m": 0.64, "n": 22},
                  # HAND D8 de 5 m, o dos contornos do painel, nos vértices RTK válidos (V001, RTK a conferir: -1,75 m)
                  "hand_painel": {"vies_m": 0.69, "mae_m": 1.02, "erro_max_perigoso_m": 1.25, "ponto": "H007", "n": 19},
                  "fonte": "validação de campo de 05/09/2026 (marcas e limites com RTK), "
                           "pesquisas/validacao-campo-hand-santa-tereza/; SBSR 2027"},
        "folga_m": 2.0,
        "folga_local_m": 1.0,
        "terreno_erro": {"lidar10_menos_rtk_nmad_m": 0.71, "lidar10_menos_rtk_max_m": 1.46, "ponto_max": "H003",
                         "h003_acima_do_nivel_m": 1.23},
        # margem no "quando sair": cobre o erro perigoso máximo do HAND do painel (1,25 m em H007),
        # não só o erro médio (MAE 1,02 m)
        "margem_corte_m": 1.5,
        "cicatrizes": os.path.join(RAIZ, "assets", "data", "landslides_poly.geojson"),
    },
}
RAIO_NIVEL_M = 300.0         # nível da água local: borda externa da mancha num raio de 300 m
MARGEM_RECORTE_GRAUS = 0.004  # recorte da mancha e do MDT: nós de rua ± ~400 m
GANHO_MIN_CASA_MIN = 150.0   # novo local precisa poupar 150 casa·min (~30 casas × 5 min)
LOCAIS_MAX = 10
TEMPO_TETO_S = 3600.0        # casa sem local até aqui conta 60 min no guloso
RAIO_RUA_M = 25.0            # nome da rua do local: trecho com nome a até 25 m
RAIO_LUGAR_M = 150.0         # lugares com nome perto do local
ESTADOS = ("sem_via", "no_alto", "rota")
CASAS_CAMPOS = ["estado", "local", "tempo_s", "dist_m", "corte_m", "rota", "terreno", "acima_agua_m",
                "ilha_m", "alt_local", "alt_tempo_s", "alt_rota", "alt_corte_m", "rampa_pct", "ilha_tempo_s"]
SAIDA_BORDA_M = 150.0        # saída da cidade: ponta de rua alta a até 150 m da borda da rede...
VIAS_SAIDA = ("trunk", "primary", "secondary", "tertiary")
SAIDA_VIA_M = 30.0           # ... ou ponta de via principal (a até 30 m) que segue para fora da rede
FORA_DA_REDE_M = 300.0       # vértice da via a mais de 300 m de qualquer nó: a via sai da rede
CICATRIZ_MIN_M = 100.0       # ponto alto a mais de 100 m de cicatriz de deslizamento
ENCOSTA_RAIO_M = 100.0       # aviso de encosta íngreme num raio de 100 m do ponto...
ENCOSTA_GRAUS = 30.0         # ... a partir de 30° (suscetível a deslizamento na chuva forte)
RAMPA_TRECHO_M = 40.0        # rampa da rota: a maior inclinação média em 40 m de caminho
SUPERAMOSTRA = 5             # mancha rasterizada pelo centro do pixel (PIL pinta o contorno)
ALT_EXTRA_MAX_S = 900.0      # ponto alternativo (que não vira ilha): no máximo 15 min a mais...
ALT_TOTAL_MAX_S = 1800.0     # ... e 30 min no total


def _json(caminho):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def payload(html_path):
    with open(html_path, encoding="utf-8") as f:
        s = f.read()
    return json.JSONDecoder().raw_decode(s, s.index("const D=") + len("const D="))[0]


class Lidar:
    """Altitude (m) da grade LiDAR de 10 m do site (PNG RG em decímetros)."""

    def __init__(self, meta_path):
        m = _json(meta_path)
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
    ch, f = cfg["cheia"], cfg["folga_m"]
    return {"acima_agua_min_m": f, "acima_agua_min_local_m": f + cfg["folga_local_m"], "raio_nivel_m": RAIO_NIVEL_M,
            # células IBGE fora do recorte do MDT: fora da mancha HAND + folga e acima da água mais alta medida + folga
            "celula_hand_min_m": round(ch["hand_m"] + f, 2), "celula_altitude_min_m": round(ch["agua_max_rtk_m"] + f, 2)}


def recorte(nos):
    """(S, W, N, E) dos nós de rua com margem: área da mancha e do MDT analisados."""
    la, lo = [p[0] for p in nos], [p[1] for p in nos]
    m = MARGEM_RECORTE_GRAUS
    return min(la) - m, min(lo) - m, max(la) + m, max(lo) + m


class Terreno:
    """O que ficou fora da mancha da cheia, no MDT (LiDAR 10 m), por classe de pixel."""

    CLASSES = ("dentro", "alto", "sem_folga", "abaixo_da_agua", "sem_dado")
    # verde claro: marca o terreno alto sem esconder a rota verde por cima
    CORES = {"alto": (27, 127, 59, 60), "sem_folga": (246, 196, 69, 150), "abaixo_da_agua": (198, 40, 40, 160)}

    def __init__(self, lidar, mancha, caixa, folga, agua_min):
        m = lidar.m
        self.dx, self.dy = (m["E"] - m["W"]) / m["cols"], (m["N"] - m["S"]) / m["rows"]
        S, W, N, E = caixa
        self.c0, self.r0 = int((W - m["W"]) / self.dx), int((m["N"] - N) / self.dy)
        c1, r1 = int((E - m["W"]) / self.dx) + 1, int((m["N"] - S) / self.dy) + 1
        # (S, W, N, E) das bordas dos pixels recortados: limites da imagem no mapa
        self.lim = (m["N"] - r1 * self.dy, m["W"] + self.c0 * self.dx, m["N"] - self.r0 * self.dy, m["W"] + c1 * self.dx)
        self.m = m
        z = lidar.z[self.r0:r1, self.c0:c1]
        ok = lidar.ok[self.r0:r1, self.c0:c1]
        h, w = z.shape

        def raster(aneis_por_poligono, com_buracos):
            # pelo centro do pixel: o PIL pinta também o contorno (um quadrado de 4×4 px vira 5×5),
            # o que inflava a mancha e a "água na borda"; com 5 subpixels por pixel, vale o do meio
            k5 = SUPERAMOSTRA
            img = Image.new("L", (w * k5, h * k5), 0)
            dr = ImageDraw.Draw(img)
            for aneis in aneis_por_poligono:
                for k, anel in enumerate(aneis if com_buracos else aneis[:1]):
                    dr.polygon([(x * k5 - 0.5, y * k5 - 0.5) for x, y in (self._px(la, lo) for la, lo in anel)],
                               fill=0 if k else 1)
            return np.asarray(img)[k5 // 2::k5, k5 // 2::k5].astype(bool)

        dentro = raster(mancha, True)
        externo = raster(mancha, False)  # sem as ilhas: a borda delas fica no leito, não na água
        fora_viz = np.zeros_like(externo)
        for sh in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            fora_viz |= ~np.roll(externo, sh, axis=(0, 1))
        borda = externo & fora_viz & ok
        # moldura do recorte não é margem (2 px: pelo centro, a linha de recorte cai na coluna 1)
        borda[:2, :] = borda[-2:, :] = borda[:, :2] = borda[:, -2:] = False
        yb, xb = np.nonzero(borda)
        if not len(yb):
            raise SystemExit("mancha sem borda no recorte: confira os polígonos da cheia")
        # a margem fica entre o pixel de dentro e os de fora: média dos dois lados
        zfora, nfora = np.zeros(z.shape), np.zeros(z.shape)
        for sh in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            viz_fora = np.roll(~externo & ok, sh, axis=(0, 1))
            zfora += np.where(viz_fora, np.roll(z, sh, axis=(0, 1)), 0.0)
            nfora += viz_fora
        zb = np.where(nfora[yb, xb] > 0, (z[yb, xb] + zfora[yb, xb] / np.maximum(nfora[yb, xb], 1)) / 2, z[yb, xb])
        # nível da água: mediana da borda num raio de RAIO_NIVEL_M (a borda de 10 m em barranco é ruidosa)
        my, mx = self.dy * 110540.0, self.dx * 111320.0 * math.cos(math.radians((S + N) / 2))
        wb = np.empty(len(yb))
        for k in range(len(yb)):
            perto = ((yb - yb[k]) * my) ** 2 + ((xb - xb[k]) * mx) ** 2 <= RAIO_NIVEL_M ** 2
            wb[k] = np.median(zb[perto])
        # leva o nível a cada pixel pela borda mais próxima (camadas de vizinhança, média dos vizinhos já conhecidos)
        agua = np.full(z.shape, np.nan)
        agua[yb, xb] = wb
        conhecido = ~np.isnan(agua)
        while not conhecido.all():
            soma, n = np.zeros(z.shape), np.zeros(z.shape)
            for sh in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                kn = np.roll(conhecido, sh, axis=(0, 1))
                soma += np.where(kn, np.roll(np.nan_to_num(agua), sh, axis=(0, 1)), 0.0)
                n += kn
            novo = ~conhecido & (n > 0)
            if not novo.any():
                break
            agua[novo] = soma[novo] / n[novo]
            conhecido |= novo
        acima_borda = z - agua
        agua = np.maximum(agua, agua_min)
        acima = z - agua
        cl = np.full(z.shape, self.CLASSES.index("sem_folga"), np.uint8)
        fora = ~dentro & ok
        cl[fora & (acima >= folga)] = self.CLASSES.index("alto")
        cl[fora & (acima_borda < 0)] = self.CLASSES.index("abaixo_da_agua")
        cl[~fora] = self.CLASSES.index("dentro")
        cl[~ok] = self.CLASSES.index("sem_dado")
        self.z, self.agua, self.acima, self.cl, self.ok = z, agua, acima, cl, ok
        self.my, self.mx = my, mx
        la_b = m["N"] - (self.r0 + yb + 0.5) * self.dy
        lo_b = m["W"] + (self.c0 + xb + 0.5) * self.dx
        ruas = (la_b >= S + MARGEM_RECORTE_GRAUS) & (la_b <= N - MARGEM_RECORTE_GRAUS) & \
               (lo_b >= W + MARGEM_RECORTE_GRAUS) & (lo_b <= E - MARGEM_RECORTE_GRAUS)
        self.agua_borda = {k: round(float(np.percentile(wb[ruas], q)), 2) for k, q in (("p10", 10), ("mediana", 50), ("p90", 90))}

    def _px(self, lat, lon):
        return (lon - self.m["W"]) / self.dx - self.c0, (self.m["N"] - lat) / self.dy - self.r0

    def ponto(self, lat, lon):
        """(classe, metros acima do nível da água, nível da água) no pixel; None fora do recorte."""
        x, y = self._px(lat, lon)
        x, y = int(math.floor(x)), int(math.floor(y))
        if not (0 <= y < self.cl.shape[0] and 0 <= x < self.cl.shape[1]):
            return None
        k = self.CLASSES[self.cl[y, x]]
        if k == "sem_dado":
            return k, None, None
        return k, round(float(self.acima[y, x]), 1), round(float(self.agua[y, x]), 1)

    def acima_min3(self, lat, lon):
        """Metros acima da água no pixel mais baixo do entorno 3×3 (30 m) e a altitude dele: a grade de
        10 m é o vizinho mais próximo do LiDAR de 1 m, e em declive um pixel erra ±1–2 m de posição."""
        x, y = self._px(lat, lon)
        x, y = int(math.floor(x)), int(math.floor(y))
        h, w = self.z.shape
        if not (1 <= y < h - 1 and 1 <= x < w - 1) or np.isnan(self.agua[y, x]):
            return None, None
        jan, ok = self.z[y - 1:y + 2, x - 1:x + 2], self.ok[y - 1:y + 2, x - 1:x + 2]
        if not ok.any():
            return None, None
        zmin = float(jan[ok].min())
        return round(zmin - float(self.agua[y, x]), 1), round(zmin, 1)

    def encosta_graus(self, lat, lon, raio_m):
        """Maior declividade (graus) do terreno num raio de `raio_m` m do ponto."""
        x, y = self._px(lat, lon)
        x, y = int(math.floor(x)), int(math.floor(y))
        r = max(1, int(round(raio_m / min(self.my, self.mx))))
        y0, y1, x0, x1 = max(0, y - r), min(self.z.shape[0], y + r + 1), max(0, x - r), min(self.z.shape[1], x + r + 1)
        z, ok = self.z[y0:y1, x0:x1], self.ok[y0:y1, x0:x1]
        if z.shape[0] < 3 or z.shape[1] < 3:
            return None
        gy, gx = np.gradient(np.where(ok, z, np.nan), self.my, self.mx)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        perto = ((yy - y) * self.my) ** 2 + ((xx - x) * self.mx) ** 2 <= raio_m ** 2
        g = np.hypot(gx, gy)[perto]
        g = g[~np.isnan(g)]
        return round(math.degrees(math.atan(float(g.max()))), 0) if len(g) else None

    def area_ha(self):
        px_ha = self.dy * 110540.0 * self.dx * 111320.0 * math.cos(math.radians((self.lim[0] + self.lim[2]) / 2)) / 1e4
        return {k: round(float((self.cl == i).sum()) * px_ha, 1) for i, k in enumerate(self.CLASSES) if k in self.CORES}

    def png(self):
        rgba = np.zeros(self.cl.shape + (4,), np.uint8)
        for k, cor in self.CORES.items():
            rgba[self.cl == self.CLASSES.index(k)] = cor
        buf = io.BytesIO()
        Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def amostrador(terreno_doc):
    """Classe do terreno publicado (png + limites) num ponto; None fora do recorte."""
    cl = classes_do_png(terreno_doc["png"])
    (S, W), (N, E) = terreno_doc["limites"]

    def classe(lat, lon):
        x, y = int((lon - W) / (E - W) * cl.shape[1]), int((N - lat) / (N - S) * cl.shape[0])
        return Terreno.CLASSES[cl[y, x]] if 0 <= x < cl.shape[1] and 0 <= y < cl.shape[0] else None
    return classe


def classes_do_png(uri):
    """Classes de Terreno lidas de volta do PNG publicado (para conferir o painel)."""
    rgba = np.asarray(Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGBA"))
    cl = np.zeros(rgba.shape[:2], np.uint8)
    for k, cor in Terreno.CORES.items():
        cl[(rgba == np.array(cor, np.uint8)).all(axis=-1)] = Terreno.CLASSES.index(k)
    return cl


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
        for p in _json(cfg["nomes"])["lugares"]:
            if "place" in p["tags"]:  # localidade (vila, linha, município), não é lugar de referência
                continue
            out.append({"nome": p["nome"], "lat": p["lat"], "lon": p["lon"], "fonte": "OSM " + p["osm"]})
    for caminho in cfg["servicos"]:
        for f in _json(caminho)["features"]:
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


def nomeia(local, ruas, lugares, terreno):
    p = (local["lat"], local["lon"])
    rr = _rua_mais_proxima(ruas, p, RAIO_RUA_M) if ruas else []
    perto = sorted((round(_dist(p, (q["lat"], q["lon"]))), q["nome"], q["lat"], q["lon"]) for q in lugares if q["nome"])
    # a referência também diz se ficou na água: ninguém deve ir até um prédio que alagou
    perto = [{"nome": n, "m": d, "terreno": (terreno.ponto(la, lo) or ("sem_dado",))[0]}
             for d, n, la, lo in perto if d <= RAIO_LUGAR_M][:3]
    if len(rr) >= 2:
        nome = f"{rr[0][1]} com {rr[1][1]}"
    elif rr:
        nome = rr[0][1]
    else:
        nome = None
    local["rua"] = nome
    local["perto"] = perto


def no_mais_proximo(nos, p):
    clat = math.cos(math.radians(p[0]))
    return min(range(len(nos)), key=lambda k: (nos[k][0] - p[0]) ** 2 + ((nos[k][1] - p[1]) * clat) ** 2)


def saidas_da_cidade(doc, no_alto, ruas=()):
    """Pontas de rua em terreno alto por onde se sai do recorte sem descer: na borda da rede ou na ponta
    de uma via principal do OSM que segue para fora dela (a rede corta a Estrada do Vinho a 600 m da
    borda, mas ela continua 4 km para leste)."""
    grau = {}
    for a, b, *_ in doc["edges"]:
        grau[a] = grau.get(a, 0) + 1
        grau[b] = grau.get(b, 0) + 1
    nos = np.asarray(doc["nos"], float)
    S, N, W, E = nos[:, 0].min(), nos[:, 0].max(), nos[:, 1].min(), nos[:, 1].max()
    clat = math.cos(math.radians((S + N) / 2))
    xy = np.column_stack(((nos[:, 1] - W) * 111320 * clat, (nos[:, 0] - S) * 110540))

    def na_borda(p):
        return min((p[0] - S) * 110540, (N - p[0]) * 110540, (p[1] - W) * 111320 * clat,
                   (E - p[1]) * 111320 * clat) <= SAIDA_BORDA_M
    pontas = [k for k in range(len(nos)) if grau.get(k) == 1 and no_alto[k]]
    vias = []
    for r in ruas:
        if r.get("highway") not in VIAS_SAIDA:
            continue
        v = np.asarray(r["coords"], float)
        v = np.column_stack(((v[:, 1] - W) * 111320 * clat, (v[:, 0] - S) * 110540))
        longe = np.sqrt(((v[:, None, :] - xy[None, :, :]) ** 2).sum(-1)).min(axis=1) > FORA_DA_REDE_M
        if longe.any():
            vias.append(v)

    def ponta_de_via(k):
        for v in vias:
            a, b = v[:-1], v[1:]
            d = b - a
            L = np.maximum((d ** 2).sum(-1), 1e-9)
            f = np.clip(((xy[k] - a) * d).sum(-1) / L, 0, 1)
            if np.sqrt(((a + f[:, None] * d - xy[k]) ** 2).sum(-1)).min() <= SAIDA_VIA_M:
                return True
        return False
    return [k for k in pontas if na_borda(nos[k]) or ponta_de_via(k)]


def cicatrizes(caminho, caixa):
    """Anéis externos (lat, lon) das cicatrizes de deslizamento (inventário RS 2024) na caixa (S, W, N, E)."""
    if not caminho or not os.path.exists(caminho):
        return []
    S, W, N, E = caixa
    out = []
    for f in _json(caminho)["features"]:
        g = f["geometry"]
        for P in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
            anel = [(y, x) for x, y, *_ in P[0]]
            la, lo = [p[0] for p in anel], [p[1] for p in anel]
            if max(la) >= S and min(la) <= N and max(lo) >= W and min(lo) <= E:
                out.append(anel)
    return out


def dist_cicatriz(p, aneis):
    """Metros do ponto à cicatriz mais próxima (0 dentro dela); INF sem cicatriz."""
    clat = math.cos(math.radians(p[0]))
    best = INF
    for anel in aneis:
        xy = [((lo - p[1]) * 111320 * clat, (la - p[0]) * 110540) for la, lo in anel]
        dentro = False
        for (ax, ay), (bx, by) in zip(xy, xy[1:] + xy[:1]):
            if (ay > 0) != (by > 0) and 0 < (bx - ax) * (0 - ay) / (by - ay) + ax:
                dentro = not dentro
            dx, dy = bx - ax, by - ay
            L = dx * dx + dy * dy
            f = 0.0 if L == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L))
            best = min(best, math.hypot(ax + f * dx, ay + f * dy))
        if dentro:
            return 0.0
    return best


def rampa_max(rota, nos, z, trecho_m=RAMPA_TRECHO_M):
    """Maior inclinação média (%) em `trecho_m` m de caminho ao longo da rota (subindo ou descendo)."""
    acum = [0.0]
    for u, v in zip(rota, rota[1:]):
        acum.append(acum[-1] + _dist(nos[u], nos[v]))
    best, j = 0.0, 0
    for i in range(len(rota)):
        while j < len(rota) and acum[j] - acum[i] < trecho_m:
            j += 1
        if j >= len(rota):
            break
        if z[rota[i]] is not None and z[rota[j]] is not None:
            best = max(best, abs(z[rota[j]] - z[rota[i]]) / (acum[j] - acum[i]))
    return round(best * 100)


def _nivel_ilha(v):
    """HAND em que a ligação seca com as saídas é cortada; None = nunca (até o topo do modelo);
    -1 = sem rua mapeada até uma saída (outra margem ou trecho solto da rede)."""
    return None if v == INF else -1.0 if v == -INF else round(v, 1)


def _corte(adj, cota_no, rota):
    return min([INF] + [c for u, v in zip(rota, rota[1:]) for w, _t, _d, c in adj[u] if w == v]
               + [cota_no[k] for k in rota])


def calcula(doc, mancha, cidade="santa_tereza"):
    """Locais altos do painel `doc` (payload de gerar_painel.py) fora da `mancha` da cheia
    ({"nivel_hand_m", "poligonos": [[anel externo, buracos...]] em [lat, lon]}, recortada em
    `recorte`). Determinístico."""
    cfg = CIDADES[cidade]
    crit = criterios(cfg)
    lidar = Lidar(cfg["lidar"])
    caixa = recorte(doc["nos"])
    terreno = Terreno(lidar, mancha["poligonos"], caixa, crit["acima_agua_min_m"], cfg["cheia"]["agua_max_rtk_m"])
    nos = doc["nos"]
    F = {k: i for i, k in enumerate(doc["meta"]["casas_campos"])}
    cota_no = [_cota(c) for c in doc["cota_no"]]
    z = [lidar(la, lo) for la, lo in nos]
    hand_cheia = mancha["nivel_hand_m"]  # o mesmo nível do contorno desenhado (22,1 m para 22,05 m)
    hand_alto = crit["celula_hand_min_m"]  # HAND da cheia + folga, o critério fora do recorte do MDT

    def no_terreno(la, lo, cota):
        """Classe do pixel; ponto que o HAND alaga na cheia fica "dentro" (na borda, o pixel de 10 m erra);
        com o MDT alto mas o HAND a menos da folga sobre a cheia, "sem_folga" (os dois discordam em ±1–2 m)."""
        t = terreno.ponto(la, lo) or ("sem_dado", None, None)
        if cota <= hand_cheia:
            return ("dentro",) + t[1:]
        return ("sem_folga",) + t[1:] if t[0] == "alto" and cota < hand_alto else t
    t_no = [no_terreno(la, lo, cota_no[k]) for k, (la, lo) in enumerate(nos)]
    no_alto = [t[0] == "alto" for t in t_no]
    aneis_cic = cicatrizes(cfg.get("cicatrizes"), caixa)

    def bom_sitio(k):
        """Ponto alto: 3 m acima da água também no pixel mais baixo do entorno e longe de deslizamento."""
        if t_no[k][0] != "alto" or t_no[k][1] < crit["acima_agua_min_local_m"]:
            return False
        a3 = terreno.acima_min3(*nos[k])[0]
        return a3 is not None and a3 >= crit["acima_agua_min_local_m"] and dist_cicatriz(nos[k], aneis_cic) > CICATRIZ_MIN_M
    sitios = {k for k in range(len(nos)) if bom_sitio(k)}
    alto_nos = {k for k in range(len(nos)) if no_alto[k]}
    adj = grafo(doc, z)
    B = gargalo(adj, cota_no, [k for k in range(len(nos)) if no_alto[k]])
    ruas = _json(cfg["nomes"])["ruas"] if os.path.exists(cfg["nomes"]) else []
    saidas = saidas_da_cidade(doc, no_alto, ruas)
    ilha = gargalo(adj, cota_no, saidas)  # nível em que o nó perde a última ligação seca com uma saída
    # nível HAND em que o acesso da casa até a rua alaga (contornos; gerar_painel.cota_acesso)
    acesso = doc.get("acesso_cota") or [None] * len(doc["casas"])

    casas = []
    for i, c in enumerate(doc["casas"]):
        la, lo, n = c[F["lat"]], c[F["lon"]], c[F["no"]]
        cc, ca = _cota(c[F["cota_alaga"]]), _cota(acesso[i])
        tc = no_terreno(la, lo, cc)
        item = {"cota": cc, "acesso": ca, "terreno": tc, "pessoas": c[F["pessoas"]] or 0}
        if n is not None and n < 0 and c[F["proj_lat"]] is not None:
            # sem caminho até o abrigo oficial (outra margem): o gerador não grava o nó; vale o mais
            # próximo do pé da perpendicular na rua
            n = no_mais_proximo(nos, (c[F["proj_lat"]], c[F["proj_lon"]]))
        d0 = None if n is None or n < 0 or c[F["proj_lat"]] is None else \
            _dist((la, lo), (c[F["proj_lat"]], c[F["proj_lon"]])) + _dist((c[F["proj_lat"]], c[F["proj_lon"]]), nos[n])
        if tc[0] == "alto":
            item.update(estado="no_alto", no=n, d0=d0 or 0.0)
        elif d0 is None:
            item["estado"] = "sem_via"
        else:
            limiar = min(cc, ca, B[n])
            achados, dist, ant = caminhos(adj, cota_no, n, d0 / VEL_IDOSO, d0, limiar, sitios)
            # nenhum ponto possível ao alcance (outra margem, morro com deslizamento): o terreno alto mais perto
            perto = {} if achados else caminhos(adj, cota_no, n, d0 / VEL_IDOSO, d0, limiar, alto_nos)
            if perto:
                perto, dist, ant = perto
            item.update(estado="rota" if achados or perto else "sem_via", no=n, limiar=limiar,
                        achados=achados, perto=perto, dist=dist, ant=ant)
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

    lugares = lugares_conhecidos(cfg)
    idx = {s: j for j, s in enumerate(escolhidos)}
    locais = []
    for j, s in enumerate(escolhidos):
        a3, z3 = terreno.acima_min3(*nos[s])
        # altitude e folga no pixel mais baixo do entorno de 30 m (o valor que vale para o ponto)
        loc = {"id": f"alto_{j + 1}", "lat": nos[s][0], "lon": nos[s][1], "no": s, "altitude_m": z3,
               "agua_m": t_no[s][2], "acima_agua_m": a3,
               "cota_alaga_m": None if cota_no[s] == INF else cota_no[s],
               "ilha_m": _nivel_ilha(ilha[s]),
               "encosta_graus": terreno.encosta_graus(nos[s][0], nos[s][1], ENCOSTA_RAIO_M)}
        nomeia(loc, ruas, lugares, terreno)
        locais.append(loc)
    ligados = {s for s in escolhidos if ilha[s] > hand_cheia}  # não ficam ilhados numa cheia como a de referência

    def tempo_ilha(n, d0):
        """Segundos a pé da casa no alto até passar o gargalo: um nó que fica ilhado mais tarde."""
        achados, _d, _a = caminhos(adj, cota_no, n, d0 / VEL_IDOSO, d0, ilha[n],
                                   {k for k in range(len(nos)) if ilha[k] > ilha[n] + 0.05})
        return round(min(achados.values())) if achados else None

    saida_casas = []
    for it in casas:
        tr = [Terreno.CLASSES.index(it["terreno"][0]), it["terreno"][1]]
        if it["estado"] != "rota":
            n = it.get("no")
            il = None if n is None or n < 0 else _nivel_ilha(ilha[n])
            t_il = tempo_ilha(n, it["d0"]) if it["estado"] == "no_alto" and il is not None and 0 <= il <= hand_cheia else None
            saida_casas.append([ESTADOS.index(it["estado"]), -1, None, None, None, None] + tr +
                               [il, None, None, None, None, None, t_il])
            continue
        alc = [(t, s) for s, t in it["achados"].items() if s in idx]
        if not alc:  # nenhum local escolhido alcança: fica com o nó alto mais próximo (local -1)
            alc = [min((t, s) for s, t in (it["achados"] or it["perto"]).items())]
        t, s = min(alc)
        rota = _rota(it["ant"], s)
        corte = min(_corte(adj, cota_no, rota), it["acesso"])
        # local que vira ilha antes da cheia de referência: o mais perto entre os que não viram, se houver
        # um a uma caminhada razoável; com o traçado e o corte próprios
        alt = None if s in ligados else min(((tt, ss) for ss, tt in it["achados"].items() if ss in ligados
                                             and tt <= min(t + ALT_EXTRA_MAX_S, ALT_TOTAL_MAX_S)), default=None)
        rota_alt = _rota(it["ant"], alt[1]) if alt else None
        corte_alt = min(_corte(adj, cota_no, rota_alt), it["acesso"]) if alt else INF
        r1 = lambda v: None if v == INF else round(v, 1)  # noqa: E731
        saida_casas.append([ESTADOS.index("rota"), idx.get(s, -1), round(t), round(it["dist"][s], 1), r1(corte), rota] + tr +
                           [_nivel_ilha(ilha[s]), idx[alt[1]] if alt else None, round(alt[0]) if alt else None,
                            rota_alt, r1(corte_alt) if alt else None, rampa_max(rota, nos, z), None])

    # margem das ruas até o local alto (aba Margem): por nó, o mesmo critério das casas
    margem_nos = []
    alvos = set(escolhidos)
    for k in range(len(nos)):
        if no_alto[k]:
            margem_nos.append(None)
            continue
        achados, _dd, ant = caminhos(adj, cota_no, k, 0.0, 0.0, min(cota_no[k], B[k]), alvos)
        if not achados:
            margem_nos.append(None)
            continue
        t, s = min((tt, ss) for ss, tt in achados.items())
        c = _corte(adj, cota_no, _rota(ant, s))
        margem_nos.append([round(t), None if c == INF else round(c, 1)])

    for j, loc in enumerate(locais):
        ts = sorted(c[2] for c in saida_casas if c[1] == j)
        loc["n_casas"] = len(ts)
        loc["pessoas"] = round(sum(casas[i]["pessoas"] for i, c in enumerate(saida_casas) if c[1] == j))
        loc["tempo_mediano_min"] = round(ts[len(ts) // 2] / 60, 1) if ts else None
        loc["tempo_max_min"] = round(ts[-1] / 60, 1) if ts else None

    ch = cfg["cheia"]
    S, W, N, E = terreno.lim
    return {
        "meta": {"cheia": ch, "criterios": crit, "folga_m": cfg["folga_m"], "folga_local_m": cfg["folga_local_m"],
                 "terreno_erro": cfg["terreno_erro"], "margem_corte_m": cfg["margem_corte_m"],
                 "nivel_mancha_m": hand_cheia, "saidas": saidas,
                 "cicatrizes": os.path.relpath(cfg["cicatrizes"], RAIZ) if aneis_cic else None,
                 "encosta_graus_aviso": ENCOSTA_GRAUS, "rampa_trecho_m": RAMPA_TRECHO_M,
                 "lidar": os.path.relpath(cfg["lidar"], RAIZ),
                 "nomes": os.path.relpath(cfg["nomes"], RAIZ) if ruas else None,
                 "casas_campos": CASAS_CAMPOS, "estados": list(ESTADOS), "classes_terreno": list(Terreno.CLASSES)},
        "terreno": {"png": terreno.png(), "limites": [[round(S, 7), round(W, 7)], [round(N, 7), round(E, 7)]],
                    "area_ha": terreno.area_ha(), "agua_borda_m": terreno.agua_borda},
        "locais": locais,
        "no_alto": [int(v) for v in no_alto],
        "casas": saida_casas,
        "margem_nos": margem_nos,
    }


def pagina_rotas_altas(doc):
    """Dados de santa_tereza_rotas_altas_set2023.html (rotas no pico até qualquer trecho alto), com o
    mesmo critério e os mesmos dados do painel: nós altos, mancha da cheia, terreno e pontos altos."""
    alt = doc["altos"]
    F = {k: i for i, k in enumerate(doc["meta"]["casas_campos"])}
    A = {k: i for i, k in enumerate(alt["meta"]["casas_campos"])}
    ch, nos = alt["meta"]["cheia"], doc["nos"]
    casas = []
    for c, a in zip(doc["casas"], alt["casas"]):
        n, pj = c[F["no"]], (c[F["proj_lat"]], c[F["proj_lon"]])
        if n is not None and n < 0 and pj[0] is not None:
            n = no_mais_proximo(nos, pj)  # outra margem: como em calcula
        casas.append([c[F["lat"]], c[F["lon"]], pj[0], pj[1], n, c[F["cota_alaga"]], a[A["terreno"]], a[A["acima_agua_m"]],
                      a[A["ilha_m"]] if a[A["estado"]] == ESTADOS.index("no_alto") else None])
    return {
        "schema_version": "previne_rota_alta_historica_v2",
        "local": f"{doc['meta']['municipio']}/RS", "evento": f"Cheia de {ch['rotulo']}", "data_pico": ch["data"],
        "nivel_regua_m": ch["regua_m"], "nivel_regua_sgb_m": ch["regua_sgb_m"], "zero_regua_hand_m": ch["zero_regua_m"],
        "nivel_hand_m": ch["hand_m"], "nivel_mancha_m": alt["meta"]["nivel_mancha_m"], "folga_m": alt["meta"]["folga_m"],
        "fonte": "santa_tereza_painel_casas.html (codigo_python/09_rota_fuga/locais_altos.py)",
        "criterio": "terreno alto = fora da mancha da cheia e pelo menos folga_m acima do nível da água no MDT "
                    "(LiDAR 10 m); o mesmo critério do painel de rotas",
        "aviso_estudo": doc["meta"].get("aviso_estudo"),
        "nos": nos, "cota_alaga_nos": doc["cota_no"], "no_alto": alt["no_alto"],
        "arestas": [[a, b, cz] for a, b, _ag, _pe, cz in doc["edges"]],
        "casas_campos": ["lat", "lon", "proj_lat", "proj_lon", "no", "cota_alaga", "terreno", "acima_agua_m", "ilha_m"],
        "casas": casas, "classes_terreno": alt["meta"]["classes_terreno"],
        "terreno": {"png": alt["terreno"]["png"], "limites": alt["terreno"]["limites"]},
        "mancha_cheia": alt["mancha_cheia"],
        "locais": [{"id": l["id"], "lat": l["lat"], "lon": l["lon"], "rua": l["rua"]} for l in alt["locais"]],
        "abrigo_referencia": [{"nome": a["nome"], "lat": a["lat"], "lon": a["lon"], "cota_alaga_m": a["cota_alaga_m"]}
                              for a in doc["abrigos"]],
    }


def resumo(alt, doc):
    cs = alt["casas"]
    F = {k: i for i, k in enumerate(doc["meta"]["casas_campos"])}
    est = [ESTADOS[c[0]] for c in cs]
    rot = [(c, _cota(doc["casas"][i][F["cota_alaga"]])) for i, c in enumerate(cs) if c[0] == ESTADOS.index("rota")]
    ts = sorted(c[2] / 60 for c, _ in rot)
    linhas = [f"terreno fora da mancha (ha): {alt['terreno']['area_ha']} · água na borda (m): {alt['terreno']['agua_borda_m']}",
              f"nós altos: {sum(alt['no_alto'])}/{len(alt['no_alto'])} · casas no alto: {est.count('no_alto')}, "
              f"com rota: {len(rot)}, sem via: {est.count('sem_via')}"]
    if ts:
        antes = sum(1 for c, cc in rot if c[4] is not None and c[4] < cc)
        linhas.append(f"tempo até o local (idoso): mediana {ts[len(ts) // 2]:.1f} min, p90 {ts[int(0.9 * (len(ts) - 1))]:.1f}, "
                      f"máx {ts[-1]:.1f} · rota cortada antes de a água chegar na casa: {antes}")
        nm = alt["meta"]["nivel_mancha_m"]
        ilhadas = sum(1 for c in cs if c[0] == ESTADOS.index("no_alto") and c[8] is not None and c[8] <= nm)
        alt_ok = sum(1 for c in cs if c[9] is not None)
        linhas.append(f"casas no alto que ficam ilhadas até a cheia: {ilhadas} · casas com local que vira ilha e alternativa ligada: {alt_ok}")
    for loc in alt["locais"]:
        perto = ", ".join(f"{p['nome']} ({p['m']} m)" for p in loc["perto"]) or "-"
        linhas.append(f"  {loc['id']}: {loc['lat']:.6f},{loc['lon']:.6f} alt {loc['altitude_m']} m, ilha a partir de HAND {loc['ilha_m']}, "
                      f"{loc['acima_agua_m']} m acima da água ({loc['agua_m']} m) · {loc['n_casas']} casas, ~{loc['pessoas']} pessoas, "
                      f"mediana {loc['tempo_mediano_min']} min, máx {loc['tempo_max_min']} min · "
                      f"{loc['rua'] or 'rua sem nome'} · perto: {perto}")
    return "\n".join(linhas)


if __name__ == "__main__":
    cid = sys.argv[1] if len(sys.argv) > 1 else "santa_tereza"
    d = payload(CIDADES[cid]["painel"])
    if not (d.get("altos") or {}).get("mancha_cheia"):
        raise SystemExit("o painel publicado não tem a mancha da cheia: rode gerar_painel.py --republicar")
    print(resumo(calcula(d, d["altos"]["mancha_cheia"], cid), d))
