#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GT Vulnerabilidades e Riscos: diagnóstico reprodutível de isolamento de ruas.

Lê os dados espaciais já embutidos nos painéis PREVINE e REFAZ a conectividade
sem usar a penalização de água da rota antiga. Nenhuma saída equivale a uma
rota segura certificada: conexões casa->rua, pontes, HAND e abrigos ainda exigem
verificação de campo. Não utiliza coordenadas ou cadastros pessoais restritos.

Uso:
  python scripts/gt_risco_vida.py --cidade ambas --saida /tmp/gt-risco-vida
"""
from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CIDADES = {
    "santa_tereza": "santa_tereza_painel_casas.html",
    "mucum": "mucum_painel_casas.html",
}
MAX_NIVEL_HAND = 25.0
VEL_PE_MS = 0.9


def carrega_painel(path: Path) -> dict:
    s = path.read_text(encoding="utf-8")
    marker = "const D="
    at = s.find(marker)
    if at < 0:
        raise ValueError(f"{path}: painel sem payload const D=")
    doc, _ = json.JSONDecoder().raw_decode(s[at + len(marker):])
    for name in ("meta", "nos", "edges", "casas", "abrigos", "niveis", "cota_no"):
        if name not in doc:
            raise ValueError(f"{path}: falta campo {name}")
    return doc


def distancia_m(a, b) -> float:
    la1, lo1 = map(math.radians, a[:2])
    la2, lo2 = map(math.radians, b[:2])
    dl, dn = la2 - la1, lo2 - lo1
    h = math.sin(dl / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dn / 2) ** 2
    return 12742000.0 * math.asin(min(1.0, math.sqrt(h)))


def aberto(cota, nivel: float, politica: str) -> bool:
    """None na versão publicada mistura fora do raster e >25 m HAND."""
    if cota is None:
        return politica == "exploratoria"
    return float(cota) > nivel + 1e-9


def grafo_seco(doc: dict, nivel: float, politica: str) -> list:
    """Remove trechos com água, nunca multiplica custo para 'autorizar' travessia.

    A versão conservadora fecha também trechos com cota ausente; a exploratória
    mantém esses trechos, mas seu resultado é sempre condicionado à incerteza.
    """
    n = len(doc["nos"])
    out = [[] for _ in range(n)]
    for edge in doc["edges"]:
        a, b = int(edge[0]), int(edge[1])
        if not (0 <= a < n and 0 <= b < n):
            continue
        if not (aberto(edge[4], nivel, politica)
                and aberto(doc["cota_no"][a], nivel, politica)
                and aberto(doc["cota_no"][b], nivel, politica)):
            continue
        ds = distancia_m(doc["nos"][a], doc["nos"][b])
        if ds <= 0 or not math.isfinite(ds):
            continue
        # Sem MDT z por nó no painel publicado: tempo a pé em terreno plano é
        # APENAS aproximação. As rotas reais devem usar grafo+MDT reconstruídos.
        custo = ds / VEL_PE_MS * (1.5 if int(edge[3]) else 1.0)
        out[a].append((b, custo))
        out[b].append((a, custo))
    return out


def fontes(doc: dict, nivel: float, politica: str, candidatos=False) -> dict:
    src = list(doc["abrigos"]) + (list(doc.get("candidatos", [])) if candidatos else [])
    out = {}
    n = len(doc["nos"])
    for item in src:
        node = item.get("node")
        cz = item.get("cota_alaga_m")
        if not isinstance(node, int) or not 0 <= node < n:
            continue
        if not (aberto(cz, nivel, politica)
                and aberto(doc["cota_no"][node], nivel, politica)):
            continue
        out[node] = item["id"]
    return out


def rotas_secas(doc: dict, nivel: float, politica="exploratoria", candidatos=False) -> dict:
    adj = grafo_seco(doc, nivel, politica)
    src = fontes(doc, nivel, politica, candidatos)
    dist = [math.inf] * len(adj)
    dest = [None] * len(adj)
    prox = [-1] * len(adj)
    heap = []
    for node, label in src.items():
        dist[node], dest[node], prox[node] = 0.0, label, node
        heapq.heappush(heap, (0.0, node))
    while heap:
        cost, node = heapq.heappop(heap)
        if cost > dist[node] + 1e-9:
            continue
        for other, t in adj[node]:
            future = cost + t
            if future + 1e-9 < dist[other]:
                dist[other], dest[other], prox[other] = future, dest[node], node
                heapq.heappush(heap, (future, other))
    return {"dist": dist, "dest": dest, "prox": prox, "sources": len(src)}


def normaliza_niveis(doc: dict) -> list[float]:
    values = set(float(x) for x in doc["niveis"]["hand_m"])
    values.add(float(doc["meta"]["nivel_projeto_m"]))
    values.add(0.0)
    return sorted(x for x in values if 0 <= x <= MAX_NIVEL_HAND)


def diagnostica(doc: dict) -> dict:
    campos = {k: i for i, k in enumerate(doc["meta"]["casas_campos"])}
    niveis = normaliza_niveis(doc)
    cortes_exploratorios = [None] * len(doc["casas"])
    cortes_conservadores = [None] * len(doc["casas"])
    inicial_exploratorio = [None] * len(doc["casas"])
    inicial_conservador = [None] * len(doc["casas"])
    cenario = {}
    for nivel in niveis:
        e = rotas_secas(doc, nivel, "exploratoria")
        c = rotas_secas(doc, nivel, "conservadora")
        alt = rotas_secas(doc, nivel, "exploratoria", candidatos=True)
        conteio = Counter()
        linhas = []
        for i, casa in enumerate(doc["casas"]):
            no = casa[campos["no"]]
            cota = casa[campos["cota_alaga"]]
            dentro = cota is not None and float(cota) <= nivel
            desconhecido = cota is None
            acesso = isinstance(no, int) and 0 <= no < len(doc["nos"])
            ok_e = bool(acesso and math.isfinite(e["dist"][no]))
            ok_c = bool(acesso and math.isfinite(c["dist"][no]))
            ok_alt = bool(acesso and math.isfinite(alt["dist"][no]))
            # Avalia conectividade do nó de acesso apenas. Não foi verificada
            # a travessia entre a porta, o ponto projetado e a via.
            if nivel == niveis[0]:
                inicial_exploratorio[i] = ok_e
                inicial_conservador[i] = ok_c
            if not ok_e and inicial_exploratorio[i] and cortes_exploratorios[i] is None:
                cortes_exploratorios[i] = nivel
            if not ok_c and inicial_conservador[i] and cortes_conservadores[i] is None:
                cortes_conservadores[i] = nivel
            if dentro:
                categoria = "edificacao_na_mancha_modelada"
            elif ok_c:
                categoria = "rota_rede_conhecida_acesso_nao_validado"
            elif ok_e:
                categoria = "rota_dependente_de_cotas_ausentes"
            elif ok_alt:
                categoria = "somente_destino_candidato"
            elif not acesso:
                categoria = "sem_no_de_acesso"
            else:
                categoria = "sem_conexao_seca_modelada"
            if desconhecido:
                conteio["cota_edificacao_indeterminada"] += 1
            conteio[categoria] += 1
            linhas.append({
                "indice_origem_osm": i,
                "lat": casa[campos["lat"]], "lon": casa[campos["lon"]],
                "origem_na_mancha": dentro, "cota_da_origem": cota,
                "estado": categoria, "destino": e["dest"][no] if ok_e else None,
                "tempo_rede_plana_min": (round(e["dist"][no] / 60, 1) if ok_e else None),
                "destino_alternativo_de_pesquisa": alt["dest"][no] if ok_alt else None,
                "rede_conservadora": ok_c, "rede_exploratoria": ok_e,
                "acesso_porta_rua_validado": False,
            })
        cenario[str(nivel)] = {
            "nivel_hand_m": nivel,
            "nivel_regua_m": round(nivel + float(doc["meta"]["bankfull_m"]), 2),
            "contagens": dict(conteio),
            "fontes_oficiais_exploratorias": e["sources"],
            "fontes_oficiais_conservadoras": c["sources"],
            "registros": linhas,
        }

    projeto = float(doc["meta"]["nivel_projeto_m"])
    a = cenario[str(projeto)]
    cut_antes = 0
    for i, casa in enumerate(doc["casas"]):
        cf = casa[campos["cota_alaga"]]
        cr = cortes_exploratorios[i]
        if cf is not None and cr is not None and cr < float(cf):
            cut_antes += 1
        a["registros"][i]["primeira_perda_rede_exploratoria_hand_m"] = cr
        a["registros"][i]["primeira_perda_rede_conservadora_hand_m"] = cortes_conservadores[i]
        a["registros"][i]["perde_acesso_antes_inundar"] = (
            cr < float(cf) if cr is not None and cf is not None else None
        )
    report = {
        "status": "PESQUISA_NAO_VALIDADA",
        "cidade": doc["meta"]["municipio"],
        "versao_fonte_painel": doc["meta"].get("gerado_em"),
        "nivel_projeto_hand_m": projeto,
        "nivel_projeto_regua_m": a["nivel_regua_m"],
        "total_edificacoes_osm": len(doc["casas"]),
        "rede_nos": len(doc["nos"]), "rede_trechos": len(doc["edges"]),
        "edificacoes_com_perda_antes_da_inundacao_modelada": cut_antes,
        "observacoes": [
            "Edificacoes OSM nao equivalem a domicilio CNEFE comprovado.",
            "Cota nula pode significar acima de 25 m ou fora de cobertura; 'conservadora' fecha essa incerteza.",
            "A casa foi ligada ao no de rota legado; trecho porta-via pode alagar e nao foi validado.",
            "Tempos a pe usam distancia em terreno plano (0,9 m/s), sem inclinacao; nao usar em emergencias.",
            "Pontes nao tiveram integridade, acesso ou tabuleiro verificados.",
            "Destinos e capacidades nao foram verificados em campo.",
            "Primeira perda e avaliada apenas nos niveis discretizados publicados; representa limite superior do nivel de corte.",
            "Nao ha validacao de rotas por profundidade, velocidade, detritos, geotecnia nem tempo de chegada de onda.",
        ],
        "cenarios": {k: {kk: vv for kk, vv in val.items() if kk != "registros"}
                     for k, val in cenario.items()},
        "origens_cenario_projeto": a["registros"],
    }
    return report


def salva(report: dict, pasta: Path, slug: str) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    resumo = {k: v for k, v in report.items() if k != "origens_cenario_projeto"}
    (pasta / f"{slug}_resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Saída de pesquisa usa apenas coordenadas OSM e classes de cenário,
    # nunca nomes, endereços particulares ou vulnerabilidade individual.
    pontos = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {k: v for k, v in item.items() if k not in ("lat", "lon")},
         "geometry": {"type": "Point", "coordinates": [item["lon"], item["lat"]]}}
        for item in report["origens_cenario_projeto"]
    ]}
    (pasta / f"{slug}_origens_pesquisa.geojson").write_text(
        json.dumps(pontos, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    with (pasta / f"{slug}_origens_pesquisa.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(report["origens_cenario_projeto"][0]))
        writer.writeheader()
        writer.writerows(report["origens_cenario_projeto"])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cidade", choices=["ambas", *CIDADES], default="ambas")
    p.add_argument("--saida", type=Path, default=ROOT / "artifacts" / "gt_risco_vida")
    args = p.parse_args()
    cidades = list(CIDADES) if args.cidade == "ambas" else [args.cidade]
    for slug in cidades:
        doc = carrega_painel(ROOT / CIDADES[slug])
        result = diagnostica(doc)
        salva(result, args.saida, slug)
        print(json.dumps({
            "cidade": slug, "edificacoes": result["total_edificacoes_osm"],
            "perda_antes_da_inundacao": result["edificacoes_com_perda_antes_da_inundacao_modelada"],
            "cenario": result["cenarios"][str(result["nivel_projeto_hand_m"])]["contagens"]
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
