# -*- coding: utf-8 -*-
"""Menos pontos de encontro para um tempo máximo a pé: a conta que a página pontos_encontro.html
refaz no navegador (assets/js/pontos_plano.js). As duas versões têm de dar o mesmo resultado
(tests/test_pontos_encontro.py, PlanoParidadeTest); por isso tudo é em inteiros (tempo em décimos de segundo) e
os empates têm regra fixa.

`rede` é o bloco "plano" do JSON da página:
- arestas: [a, b, décimos de s de a para b, de b para a, comprimento em dm]
- casas: [nó, décimos de s da casa até o nó, metros da casa até o nó, pessoas, precisa (1/0)]
- candidatos: [{"no", "lugar", ...}] (pontos que o algoritmo pode escolher)
- oficiais: [{"no", "seguro", "nome", ...}] (pontos do plano de contingência)

Modos: "algoritmo" (só candidatos), "plano" (só os pontos oficiais fora da área insegura) e
"plano+algoritmo" (os oficiais e, para as casas que ficam além do tempo, candidatos).
Escolha gulosa: a cada passo, o ponto que leva mais casas ainda sem ponto até o tempo máximo
(empate: com lugar de reunião, depois menor soma de tempos, depois menor nó); depois sai todo
ponto do algoritmo sem o qual nenhuma casa fica sem ponto. Cada casa vai ao ponto mais perto; em
"plano+algoritmo", o ponto oficial vem primeiro: a rua que chega a um ponto oficial até o tempo
máximo vai a ele, e só o resto vai aos pontos do algoritmo.
"""
import heapq

MODOS = ("algoritmo", "plano", "plano+algoritmo")
PONTOS_MAX = 30
INF = float("inf")


def _reversa(rede, n):
    rev = [[] for _ in range(n)]
    for a, b, tab, tba, _l in rede["arestas"]:
        rev[b].append((a, tab))  # anda de a até b
        rev[a].append((b, tba))
    return rev


def _alcance(rev, s, teto):
    """Décimos de s de cada nó até s, só até o teto: {nó: tempo}."""
    t = {s: 0}
    pq = [(0, s)]
    while pq:
        tu, u = heapq.heappop(pq)
        if tu > t.get(u, INF):
            continue
        for v, w in rev[u]:
            nt = tu + w
            if nt <= teto and nt < t.get(v, INF):
                t[v] = nt
                heapq.heappush(pq, (nt, v))
    return t


def _cobertura(rede, rev, nos_fonte, teto):
    """Para cada nó-fonte: {casa: tempo} das casas que precisam de ponto e chegam até o teto."""
    casas = rede["casas"]
    out = {}
    for s in nos_fonte:
        if s in out:
            continue
        t = _alcance(rev, s, teto)
        cob = {}
        for i, (no, d0, _dm, _p, precisa) in enumerate(casas):
            if precisa and no >= 0 and no in t and d0 + t[no] <= teto:
                cob[i] = d0 + t[no]
        out[s] = cob
    return out


def _destino(rede, rev, n, fontes):
    """Dijkstra de várias fontes, sem teto. Empate: menor índice do ponto, depois menor nó anterior."""
    tt, dono, prox, dist = [INF] * n, [-1] * n, [-1] * n, [0] * n
    pq = []
    for k, s in enumerate(fontes):
        if tt[s] == INF or k < dono[s]:
            tt[s], dono[s] = 0, k
            pq.append((0, k, s))
    heapq.heapify(pq)
    while pq:
        tu, ku, u = heapq.heappop(pq)
        if tu != tt[u] or ku != dono[u]:
            continue
        for v, w in rev[u]:
            nt = tu + w
            if (nt, ku, u) < (tt[v], dono[v] if dono[v] >= 0 else n, prox[v] if prox[v] >= 0 else n):
                tt[v], dono[v], prox[v] = nt, ku, u
                heapq.heappush(pq, (nt, ku, v))
    # comprimento do caminho em dm, seguindo prox (já final)
    comp = {}
    for a, b, _tab, _tba, l in rede["arestas"]:
        comp[(a, b)] = comp[(b, a)] = min(l, comp.get((a, b), l))
    feito = [False] * n
    for v in range(n):
        pilha = []
        while v >= 0 and not feito[v]:
            pilha.append(v)
            v = prox[v]
        for u in reversed(pilha):
            dist[u] = dist[prox[u]] + comp[(u, prox[u])] if prox[u] >= 0 else 0
            feito[u] = True
    return tt, dono, prox, dist


def planeja(rede, tempo_max_min, modo="algoritmo"):
    if modo not in MODOS:
        raise ValueError(modo)
    teto = int(round(tempo_max_min * 600))
    n = rede["n_nos"]
    rev = _reversa(rede, n)
    oficiais = [o for o in rede["oficiais"] if o["seguro"]] if modo != "algoritmo" else []
    cands = rede["candidatos"] if modo != "plano" else []
    cob = _cobertura(rede, rev, [o["no"] for o in oficiais] + [c["no"] for c in cands], teto)
    escolhidos = [("plano", j) for j in range(len(oficiais))]
    coberta = set()
    for o in oficiais:
        coberta |= set(cob[o["no"]])
    usados = {o["no"] for o in oficiais}
    while len(escolhidos) < PONTOS_MAX:
        melhor, chave = None, None
        for j, c in enumerate(cands):
            if c["no"] in usados:
                continue
            novas = [t for i, t in cob[c["no"]].items() if i not in coberta]
            if not novas:
                continue
            k = (-len(novas), 0 if c.get("lugar") else 1, sum(novas), c["no"])
            if chave is None or k < chave:
                melhor, chave = j, k
        if melhor is None:
            break
        escolhidos.append(("algoritmo", melhor))
        usados.add(cands[melhor]["no"])
        coberta |= set(cob[cands[melhor]["no"]])

    def no_de(e):
        return oficiais[e[1]]["no"] if e[0] == "plano" else cands[e[1]]["no"]
    # tira, do último para o primeiro, ponto do algoritmo que não faz falta a nenhuma casa
    for e in [e for e in escolhidos if e[0] == "algoritmo"][::-1]:
        outros = [x for x in escolhidos if x != e]
        resto = set()
        for x in outros:
            resto |= set(cob[no_de(x)])
        if set(cob[no_de(e)]) <= resto:
            escolhidos = outros

    fontes = [no_de(e) for e in escolhidos]
    tt, dono, prox, dist = _destino(rede, rev, n, fontes)
    n_of = sum(1 for e in escolhidos if e[0] == "plano")
    if 0 < n_of < len(fontes):  # plano primeiro: nó que chega a um ponto oficial até o teto vai a ele
        t1, d1, p1, s1 = _destino(rede, rev, n, fontes[:n_of])
        for v in range(n):
            if t1[v] <= teto:
                tt[v], dono[v], prox[v], dist[v] = t1[v], d1[v], p1[v], s1[v]
    casas = []
    for i, (no, d0, dm0, _p, precisa) in enumerate(rede["casas"]):
        if not precisa or no < 0 or dono[no] < 0:
            casas.append([-1, None, None, 0])
            continue
        alc = sum(1 for s in fontes if i in cob[s])
        casas.append([dono[no], d0 + tt[no], round(dm0 + dist[no] / 10, 1), alc])
    possivel = set()
    for s in cob:
        possivel |= set(cob[s])
    precisam = [i for i, c in enumerate(rede["casas"]) if c[4] and c[0] >= 0]
    return {
        "tempo_max_min": tempo_max_min, "modo": modo,
        "pontos": [{"origem": e[0], "indice": e[1], "no": no_de(e)} for e in escolhidos],
        "casas": casas, "prox": prox, "ponto_no": dono,
        "tempo_no_ds": [None if v == INF else v for v in tt],
        "resumo": {"precisam": len(precisam), "no_limite": sum(1 for i in precisam if casas[i][1] is not None and casas[i][1] <= teto),
                   "sem_ponto_possivel": sum(1 for i in precisam if i not in possivel)},
    }
