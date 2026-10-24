#!/usr/bin/env python3
"""Refinamento das cotas de corte e hierarquia de trechos críticos em Santa Tereza.

Base: grafo OSM, cota de alagamento por aresta e cotas nodais
do painel PREVINE (outubro/2026). Resultados não são guia de evacuação.
A 'cota de corte' é o primeiro estágio discreto sem CONEXÃO até um destino
cadastrado; usa um nó de rua projetado, NÃO o caminho porta-rua.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from gt_risco_vida import ROOT, CIDADES, carrega_painel, rotas_secas


def analisa(doc, passo=0.1, nivel_max=25.0):
    assert passo > 0 and nivel_max > 0
    names = {k: i for i, k in enumerate(doc["meta"]["casas_campos"])}
    origens = doc["casas"]
    # A série original começa em zero e só aumenta: um corte nunca se reabre.
    niveis = [round(i * passo, 5) for i in range(int(nivel_max / passo) + 1)]
    inicial = rotas_secas(doc, 0, "exploratoria")
    elegiveis = []
    for i, c in enumerate(origens):
        n = c[names["no"]]
        if isinstance(n, int) and 0 <= n < len(doc["nos"]) and math.isfinite(inicial["dist"][n]):
            elegiveis.append((i, n))
    cortes = [None] * len(origens)
    for lv in niveis[1:]:
        atual = rotas_secas(doc, lv, "exploratoria")
        restantes = []
        for idx, n in elegiveis:
            if math.isfinite(atual["dist"][n]):
                restantes.append((idx, n))
            else:
                cortes[idx] = lv
        elegiveis = restantes
        if not elegiveis:
            break
    produtos = []
    for i, casa in enumerate(origens):
        hand = casa[names["cota_alaga"]]
        loss = cortes[i]
        delta = None if hand is None or loss is None else round(float(hand) - loss, 2)
        produtos.append({
            "osm_index": i, "lat": casa[names["lat"]], "lon": casa[names["lon"]],
            "hand_inundacao_m": hand, "hand_perda_rede_m": loss,
            "diferenca_inundacao_menos_corte_m": delta,
            "corte_antes_da_inundacao": bool(delta is not None and delta > 0),
            "corte_apenas_intervalo_m": passo,
            "ligacao_porta_rua_validada": False
        })
    n_known = sum(p["corte_antes_da_inundacao"] for p in produtos)
    return {
        "meta": {"municipio": doc["meta"]["municipio"], "painel_fonte":doc["meta"].get("gerado_em"),
                 "passo_HAND_m": passo, "zero_regua_m": doc["meta"].get("bankfull_m"),
                 "estagio_maximo_hand_m":nivel_max,
                 "total_osm":len(origens), "corte_antes_de_alagar":n_known,
                 "validade":"investigacao, nao verificado para emergencia"},
        "origens": produtos,
    }


def auditoria_trechos(doc, diagnostico, top=100):
    """Prioriza trechos baixos usados por mais origens em rotas secas a nível 0.

    CONTAGEM DE EXPOSIÇÃO NA REDE, NÃO efeito causal do corte de uma aresta.
    """
    names = {k: i for i, k in enumerate(doc["meta"]["casas_campos"])}
    out = rotas_secas(doc, 0, "exploratoria")
    by_edge = {}
    for i,e in enumerate(doc["edges"]):
        a,b = int(e[0]),int(e[1])
        by_edge[tuple(sorted((a,b)))] = (i,e)
    tally=Counter()
    for casa in doc["casas"]:
        n=casa[names["no"]]
        if not isinstance(n,int) or n<0 or n>=len(doc["nos"]) or not math.isfinite(out["dist"][n]):
            continue
        seen=set()
        while n not in seen and out["prox"][n] >= 0:
            seen.add(n)
            nextn=out["prox"][n]
            if nextn==n: break
            key=tuple(sorted((n,nextn)))
            if key in by_edge:
                tally[key]+=1
            n=nextn
    selected=[]
    for key,score in tally.most_common():
        ix,e=by_edge[key]
        if e[4] is None: continue
        a,b=key
        selected.append({
            "edge_index":ix,"lat_inicio":doc["nos"][a][0],"lon_inicio":doc["nos"][a][1],
            "lat_fim":doc["nos"][b][0],"lon_fim":doc["nos"][b][1],
            "cota_alaga_trecho_hand_m":e[4],
            "cota_alaga_trecho_regua_m":round(e[4]+doc["meta"]["bankfull_m"],2),
            "origens_osm_em_rota_inicial":score,
            "tipo_via_pe":bool(e[3]),"acesso_ponte_validado":False,
            "interpretacao":"centralidade de rota na rede hipotetica, nao severidade causal"
        })
    selected.sort(key=lambda x:(-x["origens_osm_em_rota_inicial"],x["cota_alaga_trecho_hand_m"]))
    return selected[:top]


def grava(doc, saida:Path, passo):
    diagnostico=analisa(doc, passo=passo)
    critical=auditoria_trechos(doc,diagnostico)
    saida.mkdir(parents=True, exist_ok=True)
    meta=diagnostico["meta"]
    (saida/"santa_tereza_refinamento_resumo.json").write_text(
        json.dumps({**meta,"trechos_para_conferencia":len(critical)},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (saida/"santa_tereza_refinamento_cortes.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(diagnostico["origens"][0]))
        w.writeheader();w.writerows(diagnostico["origens"])
    geo={"type":"FeatureCollection","features":[
        {"type":"Feature","geometry":{"type":"LineString","coordinates":[[x["lon_inicio"],x["lat_inicio"]],[x["lon_fim"],x["lat_fim"]]]},
         "properties":{k:v for k,v in x.items() if not k.startswith(("lat_","lon_"))}} for x in critical
    ]}
    (saida/"santa_tereza_trechos_prioritarios.geojson").write_text(
        json.dumps(geo,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print(json.dumps({**meta,"top_trechos":critical[:5]},ensure_ascii=False))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--passo",type=float,default=0.1)
    p.add_argument("--saida",type=Path,default=ROOT/"artifacts/gt_risco_vida")
    args=p.parse_args()
    doc=carrega_painel(ROOT/CIDADES["santa_tereza"])
    grava(doc,args.saida,args.passo)
