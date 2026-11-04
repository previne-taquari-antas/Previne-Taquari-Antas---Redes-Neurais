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
"plano+algoritmo", o ponto oficial vem primeiro: a casa que chega a um ponto oficial até o tempo
máximo vai a ele, e só o resto vai aos pontos do algoritmo ("arvore" 1 = caminho até o oficial).
O tempo máximo é em minutos inteiros.
"""
import heapq

MODOS = ("algoritmo", "plano", "plano+algoritmo")
PONTOS_MAX = 30
INF = float("inf")


def _reversa(rede, n):
    rev = [[] for _ in range(n)]
    for a, b, tab, tba, l in rede["arestas"]:
        rev[b].append((a, tab, l))  # anda de a até b
        rev[a].append((b, tba, l))
    return rev


def _alcance(rev, s, teto):
    """Décimos de s de cada nó até s, só até o teto: {nó: tempo}."""
    t = {s: 0}
    pq = [(0, s)]
    while pq:
        tu, u = heapq.heappop(pq)
        if tu > t.get(u, INF):
            continue
        for v, w, _l in rev[u]:
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


def _destino(rev, n, fontes):
    """Dijkstra de várias fontes, sem teto: tempo, ponto, próximo nó e comprimento (dm) do caminho.
    Empate: menor índice do ponto, depois menor nó seguinte, depois a aresta mais curta."""
    tt, dono, prox, lp, dist = [INF] * n, [-1] * n, [-1] * n, [0] * n, [0] * n
    pq = []
    for k, s in enumerate(fontes):
        if tt[s] == INF:
            tt[s], dono[s] = 0, k
            pq.append((0, k, s))
    heapq.heapify(pq)
    while pq:
        tu, ku, u = heapq.heappop(pq)
        if tu != tt[u] or ku != dono[u]:
            continue
        for v, w, l in rev[u]:
            nt = tu + w
            if (nt, ku, u, l) < (tt[v], dono[v] if dono[v] >= 0 else n, prox[v] if prox[v] >= 0 else n, lp[v]):
                tt[v], dono[v], prox[v], lp[v] = nt, ku, u, l
                heapq.heappush(pq, (nt, ku, v))
    feito = [False] * n
    for v in range(n):
        pilha = []
        while v >= 0 and not feito[v]:
            pilha.append(v)
            v = prox[v]
        for u in reversed(pilha):
            dist[u] = dist[prox[u]] + lp[u] if prox[u] >= 0 else 0
            feito[u] = True
    return {"tt": tt, "dono": dono, "prox": prox, "dist": dist}


def _publica(arv):
    return {"prox": arv["prox"], "ponto_no": arv["dono"], "tempo_no_ds": [None if v == INF else v for v in arv["tt"]]}


def planeja(rede, tempo_max_min, modo="algoritmo"):
    if modo not in MODOS:
        raise ValueError(modo)
    if tempo_max_min != int(tempo_max_min) or tempo_max_min <= 0:
        raise ValueError("tempo máximo em minutos inteiros")
    tempo_max_min = int(tempo_max_min)
    teto = tempo_max_min * 600
    n = rede["n_nos"]
    rev = _reversa(rede, n)
    oficiais, vistos = [], set()
    for o in rede["oficiais"]:
        if o["seguro"] and o["no"] not in vistos:  # dois oficiais no mesmo nó viram um ponto
            vistos.add(o["no"])
            oficiais.append(o)
    todos_cands = rede["candidatos"]
    cob = _cobertura(rede, rev, [o["no"] for o in oficiais] + [c["no"] for c in todos_cands], teto)
    if modo == "algoritmo":
        oficiais = []
    cands = todos_cands if modo != "plano" else []
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
    todos = _destino(rev, n, fontes)
    n_of = sum(1 for e in escolhidos if e[0] == "plano")
    plano = _destino(rev, n, fontes[:n_of]) if 0 < n_of < len(fontes) else None
    # plano primeiro: a casa (e o toque no mapa) que chega a um ponto oficial até o teto vai a ele
    no_arv = [1 if plano and plano["tt"][v] <= teto else 0 for v in range(n)]
    arvs = [todos, plano]
    casas = []
    for i, (no, d0, dm0, _p, precisa) in enumerate(rede["casas"]):
        if not precisa or no < 0 or todos["dono"][no] < 0:
            casas.append([-1, None, None, 0, 0])
            continue
        a = 1 if plano and d0 + plano["tt"][no] <= teto else 0
        r = arvs[a]
        alc = sum(1 for s in fontes if i in cob[s])
        casas.append([r["dono"][no], d0 + r["tt"][no], round(dm0 + r["dist"][no] / 10, 1), alc, a])
    possivel = set()
    for s in cob:
        possivel |= set(cob[s])
    precisam = [i for i, c in enumerate(rede["casas"]) if c[4] and c[0] >= 0]
    no_lim = sum(1 for i in precisam if casas[i][1] is not None and casas[i][1] <= teto)
    sem = sum(1 for i in precisam if i not in possivel)
    out = {
        "tempo_max_min": tempo_max_min, "modo": modo,
        "pontos": [{"origem": e[0], "indice": e[1], "no": no_de(e)} for e in escolhidos],
        "casas": casas,
        "prox": [arvs[a]["prox"][v] for v, a in enumerate(no_arv)],
        "ponto_no": [arvs[a]["dono"][v] for v, a in enumerate(no_arv)],
        "tempo_no_ds": [None if arvs[a]["tt"][v] == INF else arvs[a]["tt"][v] for v, a in enumerate(no_arv)],
        "arvores": [_publica(todos)] + ([_publica(plano)] if plano else []),
        # sem_ponto_possivel: nenhum ponto seguro (oficial ou candidato) chega a ela no tempo;
        # fora_dos_escolhidos: daria para chegar, mas não a um dos pontos deste plano
        "resumo": {"precisam": len(precisam), "no_limite": no_lim, "sem_ponto_possivel": sem,
                   "fora_dos_escolhidos": len(precisam) - no_lim - sem},
    }
    return out
