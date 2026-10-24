#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoria de destinos Muçum/Santa Tereza: plano x mapa x acessibilidade.

O inventário inclui alojamentos fora do grafo publicado; NÃO os torna
automaticamente destinos válidos. A capacidade é planejada, não atual.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "assets/data"


def inventario():
    data = json.loads((DATA / "mucum_contingencia_202607.json").read_text(encoding="utf-8"))
    geo = json.loads((DATA / "servicos/abrigos.geojson").read_text(encoding="utf-8"))
    publicados = {(x.get("properties") or {}).get("id"): x for x in geo["features"]}
    destinos = []
    for origem, tipo in (("abrigos", "alojamento_planejado"), ("pontos_encontro", "ponto_de_encontro")):
        for x in data.get(origem, []):
            ids = x["id"]
            incluido = ids in publicados
            lat, lon = x.get("lat"), x.get("lon")
            valores = [v for v in (x.get("capacidade_quadro_13"), x.get("capacidade_ficha_tecnica"),
                                   x.get("capacidade_planejada")) if isinstance(v, (int, float))]
            destinos.append({
                "id": ids, "nome": x["nome"], "classe_plano": tipo,
                "integrado_camada_rotas": incluido,
                "coordenada_disponivel": isinstance(lat, (int, float)) and isinstance(lon, (int, float)),
                "lat": lat, "lon": lon,
                "origem_posicao": x.get("coordenada_status", "conferir_fonte"),
                "operacao_atual": x.get("status_operacional", "desconhecido"),
                "capacidade_planejada_min": min(valores) if valores else None,
                "capacidade_planejada_max": max(valores) if valores else None,
                "capacidade_disponivel_atual": None,
                "cota_acesso_critico": None,
                "abrigo_certificado_pela_analise": False,
            })
    santa = [p for p in geo["features"] if p["properties"].get("municipio") == "Santa Tereza"]
    resumen = {
        "versao_plano_mucum": data["meta"].get("versao"),
        "mucum_alojamentos_no_plano": len(data.get("abrigos", [])),
        "mucum_pontos_encontro_no_plano": len(data.get("pontos_encontro", [])),
        "mucum_destinos_planejados_total": len(destinos),
        "mucum_destinos_na_camada_rotas": sum(x["integrado_camada_rotas"] for x in destinos),
        "mucum_destinos_ausentes_camada_rotas": [x["nome"] for x in destinos if not x["integrado_camada_rotas"]],
        "mucum_destinos_sem_coordenadas": [x["nome"] for x in destinos if not x["coordenada_disponivel"]],
        "mucum_inconsistencia_capacidade_pessoas": {
            "quadro_2": data["resumo_capacidade"].get("capacidade_quadro_2_pessoas"),
            "quadro_13": data["resumo_capacidade"].get("capacidade_quadro_13_pessoas"),
            "anexo_5": data["resumo_capacidade"].get("capacidade_anexo_5_pessoas"),
        },
        "santa_tereza_destinos_no_cadastro": [x["properties"].get("nome") for x in santa],
        "santa_tereza_centros_elevados_requerem_vistoria": True,
        "aviso": "Cadastros e capacidades não equivalem a disponibilidade, acessibilidade ou segurança.",
    }
    pontos = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x["lon"], x["lat"]]},
         "properties": {k: v for k, v in x.items() if k not in ("lat", "lon")}}
        for x in destinos if x["coordenada_disponivel"]
    ]}
    return resumen, destinos, pontos


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--saida", type=Path, default=Path("artifacts/gt_risco_vida"))
    args = p.parse_args()
    resumo, destinos, pts = inventario()
    args.saida.mkdir(parents=True, exist_ok=True)
    for name, content in {
        "inventario_destinos_auditoria.json": resumo,
        "inventario_destinos_mucum.json": destinos,
        "inventario_destinos_mucum.geojson": pts,
    }.items():
        (args.saida / name).write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False))


if __name__ == "__main__":
    main()
