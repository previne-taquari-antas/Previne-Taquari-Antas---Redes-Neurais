"""Sombra da combinação de hidrogramas (25/11/2026, Claude; ESTADO_ATUAL §0f da frente de calibração):
  Q = w·Q(titular pc-f8-c025) + (1−w)·Q(membro pb-g12-c036, família lrdcfvb com Clark variável), w = 0,2, em todos os nós
  e em cada cenário; sobre Q, o d_piv reajustado só na calibração para a combinação (so_curva e todos_picos).
Roda o HEC do membro na mesma janela, com os mesmos observados e cenários do titular (partida a frio pelo q0 observado,
como na calibração). Nunca muda o que é publicado: só acrescenta pontos.*.combinacao_sombra e o bloco combinacao_sombra.
Na validação, a combinação reproduz melhor os hidrogramas, mas depois do d_piv o alarme de 15 m em Muçum piorou
(por isso fica em sombra). Parâmetros em parametros/combinacao_<conjunto>.json.
"""
import json
from pathlib import Path

import geo
import posproc as pp

PADRAO = geo.DADOS.parent / "parametros" / "combinacao_cb.json"
LIMIARES_MUCUM_CM = (1000, 1500)


def carregar(opcao, pos, parametros):
    """opcao: auto (liga só com --pos hibrido e o titular a que a combinação está ligada), nao, ou um arquivo."""
    if opcao == "nao":
        return None, "desligado (--combinacao nao)"
    if opcao == "auto" and pos != "hibrido":
        return None, "desligado (só com --pos hibrido)"
    arq = PADRAO if opcao == "auto" else Path(opcao)
    if not arq.exists():
        return None, f"sem {arq.name}"
    cfg = json.loads(arq.read_text(encoding="utf-8"))
    t = cfg["titular"]
    if t["id"] != parametros["id"] or t["sha256_p"] != parametros.get("sha256_p"):
        return None, (f"{arq.name} combina com {t['id']} ({t['sha256_p']}), não com {parametros['id']} "
                      f"({parametros.get('sha256_p')})")
    cfg["arquivo"] = arq.name
    return cfg, "ligado"


def misturar(res_tit, res_mem, w):
    """{cenario: {no: {t: q}}} combinado; só cenários e instantes presentes nos dois modelos."""
    out = {}
    for c in set(res_tit) & set(res_mem):
        out[c] = {}
        for no in set(res_tit[c]) & set(res_mem[c]):
            a, b = res_tit[c][no], res_mem[c][no]
            out[c][no] = {t: w * a[t] + (1 - w) * b[t] for t in a.keys() & b.keys()
                          if a[t] is not None and b[t] is not None}
    return out


def cotas(nivel_cm, horas, t0):
    """Primeiro cruzamento de 10 m e 15 m (Muçum) depois de t0, por cenário."""
    out = {}
    for c, niv in nivel_cm.items():
        out[c] = {}
        for lim in LIMIARES_MUCUM_CM:
            t = next((h for h, n in zip(horas, niv) if h > t0 and n is not None and n >= lim), None)
            out[c][f"{lim // 100}m"] = dict(cruza=t is not None, primeiro_cruzamento=t and str(t))
    return out


def bloco_ponto(p, nome, horas, t0, sims, obs_q, obs_n, curvas, cfg):
    """Bloco `combinacao_sombra` de um ponto: simulado combinado e d_piv por variante (None se o ponto não tem d_piv)."""
    var = {v: pp.serie_dpiv(p, nome, horas, t0, sims, obs_q, obs_n, curvas, d["pontos"][nome], cfg.get("rmax", 3.0))
           for v, d in cfg["variantes"].items() if nome in d["pontos"]}
    if not var:
        return None
    if nome == "MUCUM":
        for r in var.values():
            r["cotas"] = cotas(r["nivel_previsto_cm"], horas, t0)
    return dict(conjunto=cfg["conjunto"], w_titular=cfg["w_titular"], membro=cfg["membro"]["id"], arquivo=cfg["arquivo"],
                variante_principal=cfg.get("variante_principal"), aviso="SOMBRA — não publicado; comparar com `corrigido`",
                simulado={c: [pp._r(s.get(h)) for h in horas] for c, s in sims.items()}, variantes=var)
