"""Tempo do hidrograma nas cheias médias e grandes (10/10/2026, frente propagação): atraso do pico e recessão.

Diagnóstico (_analise_prop): nas cheias grandes o pico simulado chega ~4 h depois em Castro Alves, Monte Claro, LJJ e
Muçum, e a recessão simulada tem constante ~30 h em qualquer porte, enquanto a observada cai de ~30 h (pequenas) para
~17–20 h (grandes). O J padrão quase não vê isso: o atraso entra só como |lag|/3 e a recessão só pelo NSE.

Medidas por evento x controle do objetivo (horárias, cruzamentos interpolados):
  lag = t_pico_sim - t_pico_obs (obs pelo nível onde há limite de curva; sim = máx. em ±24 h, como bacia_inteira)
  K   = constante de recessão (h) entre 70% e 30% da amplitude do próprio hidrograma (base = mín. do início do evento
        até o pico): (t30 - t70) / ln(7/3). Onde há limite de curva, K só vale se o nível do pico estiver dentro dela.
Penalidade de tempo de um par: |lag|/3 + |ln(K_sim/K_obs)|/ln(1,5) (cada termo vale 1 no limite: 3 h, fator 1,5).
T_evento = média nos controles; J_t = J_pico + média de T_evento nos eventos médios e grandes (cota máx. em Muçum
>= 900 cm), ponderada por metricas.pesos_por_pico. Só usa observados para escolher eventos e pesos."""
import math
from datetime import timedelta

import bacia_inteira as bi
import hec
import metricas
from comum import EVENTOS, SIMULACOES

LIMITE_PORTE_CM = (900, 1300)   # pequeno < 900 <= médio < 1300 <= grande (cota máx. em Muçum no evento)
FATOR_K = 1.5
LAG_H = 3.0


def porte(e):
    ev = EVENTOS[e]
    niv = hec.nivel(ev["sim"], "86510000")
    hs = [t for t in niv if ev["ini"] <= t <= ev["fim"]]
    if not hs:
        return None
    n = max(niv[t] for t in hs)
    return "pequeno" if n < LIMITE_PORTE_CM[0] else "medio" if n < LIMITE_PORTE_CM[1] else "grande"


def _cruz(Q, t0, alvo, passo, limite, teto):
    t, prev, falta = t0, (t0, Q[t0]), 0
    while True:
        t += passo
        if (passo.total_seconds() > 0 and t > limite) or (passo.total_seconds() < 0 and t < limite):
            return None
        if t not in Q:
            falta += 1
            if falta > 3:
                return None
            continue
        falta = 0
        q = Q[t]
        if q > teto:
            return None
        if q < alvo:
            tp, qp = prev
            f = (qp - alvo) / (qp - q) if qp != q else 0.0
            return tp + (t - tp) * f
        prev = (t, q)


def recessao(Q, tp, ini, fim):
    """K (h) entre 70% e 30% da amplitude depois do pico tp; None se não der para medir."""
    antes = [v for t, v in Q.items() if ini <= t <= tp]
    if not antes:
        return None
    qp, qb = Q[tp], min(antes)
    if qp - qb <= 0:
        return None
    h, lim = timedelta(hours=1), fim + timedelta(hours=72)
    t70 = _cruz(Q, tp, qb + 0.7 * (qp - qb), h, lim, qp * 1.02)
    t30 = _cruz(Q, tp, qb + 0.3 * (qp - qb), h, lim, qp * 1.02)
    if t70 is None or t30 is None or t30 <= t70:
        return None
    return (t30 - t70).total_seconds() / 3600 / math.log(7 / 3)


def medir(e, nome, simq):
    ev = EVENTOS[e]
    cod, node, limite, _ = bi.CONTROLES[nome]
    sim = ev["sim"]
    obs = {t: v for t, v in bi.obs_limpo(sim, cod).items() if t.minute == 0}
    niv = {t: v for t, v in hec.nivel(sim, cod).items() if t.minute == 0}
    q = {t: v for t, v in simq.get(node, {}).items() if t.minute == 0}
    serie = niv if limite else obs
    hs = [t for t in serie if ev["ini"] <= t <= ev["fim"]]
    if not hs or not q:
        return None
    tpo = max(hs, key=lambda t: serie[t])
    if not (all(tpo + timedelta(hours=k) in serie for k in range(-6, 7)) and ev["ini"] < tpo < ev["fim"]
            and nome not in ev.get("sem_pico", set()) and tpo in obs):
        return None
    cand = {t: v for t, v in q.items() if abs((t - tpo).total_seconds()) <= 24 * 3600}
    if not cand:
        return None
    tps = max(cand, key=cand.get)
    fim = min(ev["fim"], SIMULACOES[sim]["fim"])
    dentro = not limite or niv[tpo] <= limite
    ko = recessao(obs, tpo, ev["ini"], fim) if dentro else None
    ks = recessao(q, tps, ev["ini"], fim) if ko else None
    lag = (tps - tpo).total_seconds() / 3600
    pen = abs(lag) / LAG_H + (abs(math.log(ks / ko)) / math.log(FATOR_K) if ks else 0.0)
    return dict(evento=e, controle=nome, papel=ev["papel"], lag=lag, K_obs=ko, K_sim=ks, pen_t=min(pen, 30.0))


def medir_sim(sim, simq):
    return [m for e, v in EVENTOS.items() if v["sim"] == sim
            for nome, (_, _, _, obj) in bi.CONTROLES.items() if obj
            for m in [medir(e, nome, simq)] if m]


def J_t(J_pico, tempo, mets, papel="calibracao"):
    """J_pico + média ponderada (pesos_por_pico) de T_evento nos eventos médios/grandes do papel."""
    ev = {}
    for m in tempo:
        if m["papel"] == papel and porte(m["evento"]) in ("medio", "grande"):
            ev.setdefault(m["evento"], []).append(m["pen_t"])
    if not ev or not math.isfinite(J_pico):
        return float("inf"), None
    T = {e: sum(v) / len(v) for e, v in ev.items()}
    pesos = metricas.pesos_por_pico([m for m in mets if m["papel"] == papel], set(T))
    Tm = metricas.J_ponderado(T, pesos)
    return J_pico + Tm, Tm
