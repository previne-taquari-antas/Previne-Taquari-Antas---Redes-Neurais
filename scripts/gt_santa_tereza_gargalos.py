#!/usr/bin/env python3
"""Gargalos causais: remove uma rua de cada vez e mede perda de conectividade.

O teste diferencia (a) tráfego nas rotas mínimas e (b) residências que ficam
SEM qualquer alternativa seca quando se fecha exclusivamente aquela ligação.
Não extrapola um resultado de roteamento OSM para orientação de evacuação.
"""
import argparse, csv, json, math
from collections import Counter, deque
from pathlib import Path
from gt_risco_vida import ROOT, CIDADES, carrega_painel, aberto


def components(doc, nivel, excluded=None):
    n=len(doc["nos"])
    adj=[[] for _ in range(n)]
    policy="exploratoria"
    for i,e in enumerate(doc["edges"]):
        if i==excluded: continue
        a,b=int(e[0]),int(e[1])
        if not (aberto(e[4],nivel,policy) and aberto(doc["cota_no"][a],nivel,policy)
                and aberto(doc["cota_no"][b],nivel,policy)): continue
        adj[a].append(b);adj[b].append(a)
    destinations=set()
    for a in doc["abrigos"]:
        no=a.get("node")
        if isinstance(no,int) and 0<=no<n and aberto(a.get("cota_alaga_m"),nivel,policy) and aberto(doc["cota_no"][no],nivel,policy):
            destinations.add(no)
    seen=set(destinations)
    queue=deque(destinations)
    while queue:
        for v in adj[queue.popleft()]:
            if v not in seen:seen.add(v);queue.append(v)
    return seen


def analyze(doc, levels):
    f={k:i for i,k in enumerate(doc["meta"]["casas_campos"])}
    results=[]
    for level in levels:
        reachable=components(doc,level)
        origins=[(i,c[f["no"]]) for i,c in enumerate(doc["casas"])
                 if isinstance(c[f["no"]],int) and c[f["no"]] in reachable
                 and (c[f["cota_alaga"]] is None or c[f["cota_alaga"]]>level)]
        # Provisional; check if a single cut disconnects already reachable dry origins.
        for edge_index,edge in enumerate(doc["edges"]):
            if not aberto(edge[4],level,"exploratoria"): continue
            a,b=int(edge[0]),int(edge[1])
            if a not in reachable or b not in reachable:continue
            after=components(doc,level,edge_index)
            impacted=[i for i,no in origins if no not in after]
            if not impacted:continue
            coords=[doc["nos"][a],doc["nos"][b]]
            results.append({"nivel_hand_m":level,"nivel_regua_m":round(level+doc["meta"]["bankfull_m"],2),
               "aresta_indice":edge_index,"cota_alaga_trecho_hand_m":edge[4],
               "edificacoes_sec_as_com_perda_adicional_de_conexao":len(impacted),
               "amostra_indices_osm":impacted[:15],
               "geometria":{"type":"LineString","coordinates":[[coords[0][1],coords[0][0]],[coords[1][1],coords[1][0]]]},
               "validacao_campo":"pendente"})
    results.sort(key=lambda d:(-d["edificacoes_sec_as_com_perda_adicional_de_conexao"],d["nivel_hand_m"]))
    return results


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--saida",type=Path,default=ROOT/"artifacts/gt_risco_vida")
    args=p.parse_args()
    d=carrega_painel(ROOT/CIDADES["santa_tereza"])
    # Stage-specific static interventions. Early water threshold not extrapolated
    # as certified gauge zero; existing anchor is provisional.
    stages=[0,4,8,12,13.4,15,17,19,21,23]
    ranked=analyze(d,stages)
    args.saida.mkdir(parents=True,exist_ok=True)
    fc={"type":"FeatureCollection","features":[{"type":"Feature","geometry":v["geometria"],
           "properties":{k:x for k,x in v.items() if k!="geometria"}} for v in ranked]}
    (args.saida/"santa_tereza_gargalos_causais.geojson").write_text(json.dumps(fc,ensure_ascii=False)+"\n",encoding="utf-8")
    (args.saida/"santa_tereza_gargalos_causais_resumo.json").write_text(json.dumps({
        "aviso":"SIMULACAO OSM NAO VALIDADA. Remocao de uma unica aresta; desconsidera porta-rua, passagem nao mapeada e capacidade.",
        "estagios_hand_m":stages,"n_trechos_com_perda_adicional":len(ranked),"top_15":ranked[:15]
        },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"n_casos_criticos":len(ranked),"top_5":[{k:v for k,v in x.items() if k not in ("geometria","amostra_indices_osm")} for x in ranked[:5]]},ensure_ascii=False))


if __name__=="__main__":main()
