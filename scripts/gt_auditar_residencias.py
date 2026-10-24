#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoria da correspondência espacial CNEFE (endereços) x OSM (edificações).

Proximidade NÃO comprova que uma edificação é casa. Lista divergências para
verificação por imagem datada e campo; mantém separadas unidades domiciliares,
endereços e footprints. Não associa pessoa, condição de saúde nem ocupação.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from gt_risco_vida import CIDADES, ROOT, carrega_painel, distancia_m


def corresponde(cnefe: dict, painel: dict, raio_m: float = 30.0) -> tuple:
    campos = {k: i for i, k in enumerate(painel["meta"]["casas_campos"])}
    casas = [(row[campos["lat"]], row[campos["lon"]]) for row in painel["casas"]]
    grid = defaultdict(list)
    cell = 0.0005
    for i, (lat, lon) in enumerate(casas):
        grid[(math.floor(lat / cell), math.floor(lon / cell))].append(i)
    matched_osm = set()
    contagem = defaultdict(int)
    nao_correspondentes = []
    vinculados = []
    for i, f in enumerate(cnefe["features"]):
        p = f["properties"]
        lng, lat = f["geometry"]["coordinates"]
        status = p.get("precisao")
        if status != "localizacao_individual_ou_agrupada":
            contagem["posicao_cnefe_para_revisar"] += 1
            continue
        gx, gy = math.floor(lat / cell), math.floor(lng / cell)
        near = []
        for x in range(gx - 2, gx + 3):
            for y in range(gy - 2, gy + 3):
                near.extend(grid.get((x, y), ()))
        dist, closest = min(((distancia_m((lat, lng), casas[j]), j) for j in near),
                            default=(math.inf, None))
        if dist <= raio_m and closest is not None:
            matched_osm.add(closest)
            contagem["ponto_cnefe_com_edificacao_osm_proxima"] += 1
            vinculados.append({
                "cnefe_ponto_indice": i, "osm_edificacao_indice": closest,
                "distancia_m": round(dist, 1),
                "unidades_domiciliares": p["unidades_domiciliares_cnefe_2022"],
                "confirmacao_moradia_atual": "pendente"
            })
        else:
            contagem["ponto_cnefe_sem_edificacao_osm_proxima"] += 1
            nao_correspondentes.append({
                "type": "Feature", "geometry": f["geometry"],
                "properties": {"motivo": "endereco_residencial_cnefe_sem_osm_proximo",
                               "geocodificacao": status,
                               "unidades_2022": p["unidades_domiciliares_cnefe_2022"]}})
    contagem["pontos_osm_sem_cnefe_proximo"] = len(casas) - len(matched_osm)
    contagem["total_edificacoes_osm"] = len(casas)
    contagem["total_pontos_cnefe_residenciais"] = len(cnefe["features"])
    return dict(contagem), vinculados, {"type": "FeatureCollection",
                                        "features": nao_correspondentes}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cidade", choices=list(CIDADES), required=True)
    p.add_argument("--pasta", type=Path, default=Path("artifacts/gt_risco_vida"))
    p.add_argument("--raio-m", type=float, default=30.0)
    args = p.parse_args()
    data = json.loads((args.pasta / f"{args.cidade}_cnefe_residencial_2022.geojson")
                      .read_text(encoding="utf-8"))
    painel = carrega_painel(ROOT / CIDADES[args.cidade])
    resumo, matches, divergencias = corresponde(data, painel, args.raio_m)
    resumo.update({
        "status": "proximidade_nao_e_validacao_residencial",
        "raio_referencia_m": args.raio_m,
        "limites": [
            "O CNEFE 2022 nao identifica demolicao, reconstrucao ou ocupacao posterior.",
            "Domicilio em apartamento pode ter multiplas unidades em uma coordenada.",
            "Casa OSM sem correspondencia CNEFE pode ser nova ou erro do mapa.",
            "Ponto CNEFE sem OSM proximo pode ser falta de mapeamento e nao risco.",
            "Ligacao domicilio-rua, pontes e topologia necessitam vistoria.",
        ],
    })
    args.pasta.mkdir(parents=True, exist_ok=True)
    (args.pasta / f"{args.cidade}_confronto_osm_cnefe.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.pasta / f"{args.cidade}_matches_provisorios.json").write_text(
        json.dumps(matches, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (args.pasta / f"{args.cidade}_cnefe_sem_osm.geojson").write_text(
        json.dumps(divergencias, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False))


if __name__ == "__main__":
    main()
