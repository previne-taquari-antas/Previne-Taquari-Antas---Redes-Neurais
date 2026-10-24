#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CNEFE 2022: identificação residencial verificável para os dois pilotos.

Lê o arquivo oficial municipal (ZIP/CSV) e separa espécies de endereço.
COD_ESPECIE=1 é domicílio particular; 2 é coletivo; 4,5,6,8 não são moradias.
Uma coordenada pode representar múltiplas unidades e usos. Não inventar uma
'casa' por ponto nem certificar ocupação em 2026.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

IBGE_RS = ("https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/"
           "Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/43_RS/")
CODIGOS = {"mucum": "4312609", "santa_tereza": "4317251"}


def arquivo_ibge(cod: str) -> bytes:
    """Encontra o ZIP pelo código IBGE no índice oficial, sem supor nome com acento."""
    with urllib.request.urlopen(IBGE_RS, timeout=40) as r:
        pagina = r.read().decode("utf-8", errors="replace")
    import re
    links = re.findall(r'href=["\x27]([^"\x27]+\.zip)["\x27]', pagina, re.I)
    encontrados = [x for x in links if Path(urllib.parse.unquote(x)).name.startswith(cod + "_")]
    if len(encontrados) != 1:
        raise RuntimeError(f"IBGE: esperava 1 ZIP de {cod}, encontrei {len(encontrados)}")
    url = urllib.parse.urljoin(IBGE_RS, encontrados[0])
    with urllib.request.urlopen(url, timeout=90) as r:
        return r.read()


def linhas_csv(conteudo: bytes):
    if conteudo[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            arquivos = [x for x in z.namelist() if x.lower().endswith(".csv")]
            if len(arquivos) != 1:
                raise ValueError("ZIP municipal nao tem exatamente um CSV")
            conteudo = z.read(arquivos[0])
    for enc in ("utf-8-sig", "cp1252"):
        try:
            texto = conteudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Codificacao de CSV nao suportada")
    rd = csv.DictReader(io.StringIO(texto), delimiter=";")
    campos = set(rd.fieldnames or [])
    campos_minimos = {"COD_ESPECIE", "LATITUDE", "LONGITUDE", "NV_GEO_COORD"}
    if not campos_minimos.issubset(campos):
        raise ValueError(f"Colunas CNEFE obrigatorias ausentes: {campos_minimos-campos}")
    yield from rd


def pontos_residenciais(registros, cod_mun: str):
    coords = defaultdict(lambda: {"particulares": 0, "coletivos": 0,
                                  "nao_residenciais": 0, "niveis_geo": Counter(),
                                  "tipo_edificacao": Counter()})
    total = Counter()
    for row in registros:
        if row.get("COD_MUN") and row["COD_MUN"].strip() != cod_mun:
            continue
        especie = (row.get("COD_ESPECIE") or "").strip()
        total["linhas_" + especie] += 1
        if especie not in ("1", "2", "3", "4", "5", "6", "7", "8"):
            total["codigos_nao_reconhecidos"] += 1
            continue
        try:
            lat = float((row.get("LATITUDE") or "").strip().replace(",", "."))
            lon = float((row.get("LONGITUDE") or "").strip().replace(",", "."))
        except ValueError:
            total["coordenadas_invalidas"] += 1
            continue
        if not (-35.0 <= lat <= -26.0 and -58.0 <= lon <= -49.0):
            total["coordenadas_fora_rs"] += 1
            continue
        # Nunca deduplicar domicílios distintos apenas porque compartilham ponto.
        # Agrupamento retém multiplicidade no local (prédio, condomínio, sítio).
        key = (round(lat, 7), round(lon, 7))
        item = coords[key]
        if especie == "1":
            item["particulares"] += 1
            nivel = (row.get("NV_GEO_COORD") or "").strip()
            item["niveis_geo"][nivel] += 1
            item["tipo_edificacao"][(row.get("COD_TIPO_ESPECIE") or "").strip()] += 1
        elif especie == "2":
            item["coletivos"] += 1
        else:
            item["nao_residenciais"] += 1
    features = []
    for (lat, lon), v in sorted(coords.items()):
        if not v["particulares"]:
            continue
        niveis = {str(k): int(n) for k, n in v["niveis_geo"].items()}
        precisao = ("localizacao_individual_ou_agrupada" if
                    all(k in ("1", "2") for k in niveis) else
                    "coordenada_imprecisa_revisar")
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "unidades_domiciliares_cnefe_2022": v["particulares"],
                "residencia_2026_confirmada": False,
                "coletivos_no_ponto": v["coletivos"],
                "outros_usos_no_ponto": v["nao_residenciais"],
                "niveis_geocodificacao": niveis,
                "tipo_edificacao": dict(v["tipo_edificacao"]),
                "precisao": precisao,
                "origem": "IBGE CNEFE 2022; ponto de enderecos, nao footprint"
            }
        })
    resumo = {
        "municipio_codigo": cod_mun,
        "linhas_por_especie": dict(total),
        "pontos_com_uso_domiciliar_particular": len(features),
        "unidades_particulares": sum(f["properties"]["unidades_domiciliares_cnefe_2022"] for f in features),
        "pontos_necessitam_revisao_posicional": sum(f["properties"]["precisao"] !=
                                                    "localizacao_individual_ou_agrupada" for f in features),
        "observacoes": [
            "Uma coordenada nao equivale a uma edificacao individual.",
            "Nao identifica se casa existe ou esta ocupada em 2026; inspeção/imagens atualizadas sao necessarias.",
            "Pontos de baixa precisao nao podem fundamentar trajetos porta-a-porta sem validacao.",
            "Uso misto nao elimina a residencia se COD_ESPECIE=1 tambem existe.",
            "Nenhuma informacao pessoal, nomes de moradores ou variaveis sensiveis foi exportada.",
        ],
    }
    return {"type": "FeatureCollection", "features": features}, resumo


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cidade", choices=list(CODIGOS), required=True)
    p.add_argument("--arquivo", type=Path, help="ZIP ou CSV oficial ja baixado")
    p.add_argument("--baixar", action="store_true", help="Baixar arquivo original do IBGE")
    p.add_argument("--saida", type=Path, default=Path("artifacts/gt_risco_vida"))
    args = p.parse_args()
    if not args.arquivo and not args.baixar:
        p.error("use --arquivo /caminho/arquivo.zip ou --baixar")
    dados = args.arquivo.read_bytes() if args.arquivo else arquivo_ibge(CODIGOS[args.cidade])
    gj, resumo = pontos_residenciais(linhas_csv(dados), CODIGOS[args.cidade])
    args.saida.mkdir(parents=True, exist_ok=True)
    (args.saida / f"{args.cidade}_cnefe_residencial_2022.geojson").write_text(
        json.dumps(gj, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.saida / f"{args.cidade}_cnefe_qualidade.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False))


if __name__ == "__main__":
    main()
