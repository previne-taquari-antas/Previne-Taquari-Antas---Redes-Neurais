#!/usr/bin/env python3
"""Robô SOMBRA — mancha prevista com incerteza para Muçum (pesquisa, não é alerta).

Lê a previsão ao vivo (previsao_ao_vivo_mucum.json) e, para cada horizonte principal
disponível, calcula:
  - faixa do nível (P10/P50/P90) = previsão + quantis dos erros fora da amostra
    do mesmo grupo (situação do rio × faixa de nível) — tabela_incerteza.json;
  - três níveis HAND (contornos de 90 %, 50 % e 10 % de chance de alagar), somando
    a incerteza da conversão régua→HAND (Normal, σ = 1,5 m). Os contornos já
    publicados (contornos_extravasamento.json) são reaproveitados por nível;
  - expostos acumulados em cada contorno e esperados (expostos_por_hand.json).
Depois confere as previsões antigas cuja hora-alvo já passou (cobertura real).

Saídas: assets/data/mucum_mancha_incerteza/sombra_atual.json e historico_sombra.jsonl.
Só biblioteca padrão (math/json) — sem numpy.
Uso: python -B codigo_python/01_previsao_ao_vivo/gerar_mancha_incerteza_mucum_sombra.py [--raiz .]
"""
import argparse, json, math, os
from datetime import datetime, timedelta, timezone

PASTA = os.path.join("assets", "data", "mucum_mancha_incerteza")
PREV = "previsao_ao_vivo_mucum.json"
CACHE = os.path.join("assets", "data", "mucum_niveis_observados_cache.json")
ESTACAO = "86510000"
PROBS = (90, 50, 10)
# horizonte publicado -> tabela de resíduos usada (2 h usa a de 4 h: mais larga, conservadora)
TABELA_DO_HORIZONTE = {2: 4, 4: 4, 8: 8, 12: 12}
MAX_HIST = 3000
AVISO = ("PESQUISA EM SOMBRA — não é alerta oficial. Faixas a partir dos erros fora da amostra do "
         "controle LJJ (modelo candidato), aplicadas ao modelo publicado; conversão régua→HAND com σ 1,5 m.")


def ler_json(caminho, padrao=None):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def niveis_observados(raiz):
    c = ler_json(os.path.join(raiz, CACHE), {}) or {}
    serie = (c.get("estacoes") or {}).get(ESTACAO) or []
    out = {}
    for t, v in serie:
        if v is not None:
            out[t[:16]] = float(v)
    return out


def situacao(taxa):
    if taxa is None:
        return "todos"
    if taxa < -2:
        return "descendo"
    if taxa < 5:
        return "estavel"
    if taxa < 20:
        return "subindo"
    return "subindo forte"


def faixa(nivel_cm):
    return "<8 m" if nivel_cm < 800 else ("8-12 m" if nivel_cm < 1200 else ">12 m")


def escolhe_grupo(grupos, sit, fx):
    for k in (f"{sit}|{fx}", f"{sit}|todos", "todos|todos"):
        if k in grupos:
            return k, grupos[k]
    raise KeyError("tabela sem grupo 'todos|todos'")


def sf_normal(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def prob_por_dm(previsto_cm, quantis, bankfull, sigma_m):
    """P(HAND verdadeiro >= h) para h = 0,0..24,9 m."""
    hand_i = [(previsto_cm + q - bankfull) / 100.0 for q in quantis]
    n = len(hand_i)
    return [sum(sf_normal((dm / 10.0 - hi) / sigma_m) for hi in hand_i) / n for dm in range(250)]


def nivel_da_prob(p_dm, p):
    """Maior HAND com chance >= p; None = água dentro da calha (nenhum ponto acima do leito)."""
    ok = [dm for dm, v in enumerate(p_dm) if dm >= 1 and v >= p]
    return max(ok) / 10.0 if ok else None


def expostos_ate(series, hand_m):
    if hand_m is None:
        return {k: 0 for k in series}
    dm = hand_m * 10
    dm = max(0, min(249, int(round(dm))))
    return {k: v[dm] for k, v in series.items()}


def expostos_esperados(series, p_dm):
    out = {}
    for k, v in series.items():
        tot, ant = 0.0, v[0]
        for dm in range(1, 250):
            novos = v[dm] - ant
            ant = v[dm]
            tot += novos * p_dm[dm]
        out[k] = int(round(tot))
    return out


def taxa_cm_h(obs, hora_modelo):
    try:
        t = datetime.fromisoformat(hora_modelo[:16])
    except (TypeError, ValueError):
        return None
    a, b = obs.get(t.strftime("%Y-%m-%dT%H:%M")), obs.get((t - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"))
    return None if a is None or b is None else a - b


def calcula(h_publicado, d, tab, series, obs):
    H = int(d.get("horizonte_h") or 0)
    base = {"horizonte_h": H, "modelo": d.get("modelo"), "hora_modelo": d.get("hora_modelo"),
            "hora_alvo": d.get("hora_alvo"), "disponivel": False}
    if not d.get("disponivel") or d.get("nivel_previsto_cm") is None or H not in TABELA_DO_HORIZONTE:
        base["motivo"] = d.get("status") or "previsão indisponível"
        return base
    atual = d.get("nivel_modelo_cm") if d.get("nivel_modelo_cm") is not None else d.get("nivel_atual_cm")
    prev = float(d["nivel_previsto_cm"])
    tx = taxa_cm_h(obs, d.get("hora_modelo"))
    sit = situacao(tx)
    fx = faixa(max(float(atual), prev))
    Ht = TABELA_DO_HORIZONTE[H]
    chave, g = escolhe_grupo(tab["horizontes"][str(Ht)], sit, fx)
    q = g["q"]
    p_dm = prob_por_dm(prev, q, tab["bankfull_cm"], tab["sigma_conversao_m"])
    hand = {str(p): nivel_da_prob(p_dm, p / 100) for p in PROBS}
    base.update({
        "disponivel": True, "nivel_atual_cm": atual, "nivel_previsto_cm": round(prev),
        "taxa_cm_h": tx, "situacao": sit, "faixa_nivel": fx,
        "tabela_residuos_h": Ht, "proxy_horizonte": Ht != H, "grupo": chave, "eventos_grupo": g["eventos"],
        "faixa_nivel_cm": {"p10": round(prev + q[9]), "p50": round(prev + q[49]), "p90": round(prev + q[89])},
        "hand_m": hand,
        "expostos": {p: expostos_ate(series, hand[p]) for p in hand},
        "expostos_esperados": expostos_esperados(series, p_dm),
    })
    return base


def confere(hist, obs, bankfull):
    for r in hist:
        if r.get("obs_cm") is not None or not r.get("disponivel"):
            continue
        v = obs.get((r.get("hora_alvo") or "")[:16])
        if v is None:
            continue
        r["obs_cm"] = v
        f = r["faixa_nivel_cm"]
        r["obs_dentro_p10_p90"] = f["p10"] <= v <= f["p90"]
        ho = (v - bankfull) / 100.0
        r["hand_obs_m"] = round(ho, 2)
        hm = r["hand_m"]
        lo, hi = (hm["90"] or 0.0), (hm["10"] or 0.0)
        r["hand_obs_dentro_90_10"] = (lo <= ho <= hi) if (ho > 0 or hi > 0) else None
    return hist


def resumo_verificacao(hist):
    out = {}
    for r in hist:
        if r.get("obs_cm") is None:
            continue
        k = f"{r['horizonte_h']}h"
        o = out.setdefault(k, {"n": 0, "dentro_p10_p90": 0, "n_cheia": 0, "dentro_cheia": 0})
        o["n"] += 1
        o["dentro_p10_p90"] += bool(r["obs_dentro_p10_p90"])
        if r["obs_cm"] >= 500:
            o["n_cheia"] += 1
            o["dentro_cheia"] += bool(r["obs_dentro_p10_p90"])
    for o in out.values():
        o["cobertura"] = round(o["dentro_p10_p90"] / o["n"], 3) if o["n"] else None
        o["cobertura_acima_500cm"] = round(o["dentro_cheia"] / o["n_cheia"], 3) if o["n_cheia"] else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=".")
    a = ap.parse_args()
    raiz = a.raiz
    tab = ler_json(os.path.join(raiz, PASTA, "tabela_incerteza.json"))
    exp = ler_json(os.path.join(raiz, PASTA, "expostos_por_hand.json"))
    prev = ler_json(os.path.join(raiz, PREV))
    if not tab or not exp or not prev:
        raise SystemExit("faltam tabelas ou previsão ao vivo")
    obs = niveis_observados(raiz)
    series = exp["series"]
    horizontes = {}
    for nome, d in (prev.get("horizontes") or {}).items():
        if d.get("modelo_papel") != "principal":
            continue
        horizontes[nome] = calcula(nome, d, tab, series, obs)

    hist_path = os.path.join(raiz, PASTA, "historico_sombra.jsonl")
    hist = []
    if os.path.exists(hist_path):
        with open(hist_path, encoding="utf-8") as f:
            hist = [json.loads(l) for l in f if l.strip()]
    vistos = {(r.get("horizonte_h"), r.get("hora_modelo")) for r in hist}
    for r in horizontes.values():
        if r.get("disponivel") and (r["horizonte_h"], r["hora_modelo"]) not in vistos:
            hist.append({k: r[k] for k in ("horizonte_h", "modelo", "hora_modelo", "hora_alvo", "disponivel",
                                            "nivel_atual_cm", "nivel_previsto_cm", "situacao", "faixa_nivel",
                                            "grupo", "faixa_nivel_cm", "hand_m")})
    hist = confere(hist, obs, tab["bankfull_cm"])[-MAX_HIST:]
    with open(hist_path, "w", encoding="utf-8") as f:
        for r in hist:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    saida = {"versao": 1, "modo": "sombra", "aviso": AVISO,
             "gerado_em_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "previsao_gerada_em": prev.get("gerado_em"),
             "contornos": "assets/data/mucum_inundacao/contornos_extravasamento.json (usar o nível HAND de cada probabilidade)",
             "horizontes": horizontes, "verificacao": resumo_verificacao(hist)}
    with open(os.path.join(raiz, PASTA, "sombra_atual.json"), "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)
    for k, r in horizontes.items():
        print(k, r.get("disponivel"), r.get("faixa_nivel_cm"), r.get("hand_m"), r.get("motivo", ""))


if __name__ == "__main__":
    main()
