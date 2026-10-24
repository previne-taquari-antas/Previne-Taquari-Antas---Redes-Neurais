#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CNEFE 2022 → pontos residenciais e lista de revisão OSM (pesquisa).
Exemplos:
    python codigo_python/09_rota_fuga/preparar_cnefe_pilotos.py --cidade santa_tereza --baixar
    python codigo_python/09_rota_fuga/preparar_cnefe_pilotos.py --cidade mucum --baixar
    python codigo_python/09_rota_fuga/preparar_cnefe_pilotos.py --cidade mucum --arquivo /caminho/CNEFE.csv
NUNCA usar automaticamente como confirmação da ocupação ou de segurança em 2026.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_IBGE = (
    "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/"
    "Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/43_RS/"
)
CIDADES = {
    "santa_tereza": {"codigo": "4317251", "arquivo": "4317251_SANTA_TEREZA.zip"},
    "mucum": {"codigo": "4312609", "arquivo": "4312609_MUCUM.zip"},
}
CAMPOS = {"COD_MUN", "COD_ESPECIE", "LATITUDE", "LONGITUDE", "NV_GEO_COORD"}


def numero(txt):
    if txt is None or not str(txt).strip():
        return None
    try:
        return float(str(txt).strip().replace(",", "."))
    except ValueError:
        return None


def ler_texto_csv(arquivo, baixar=False, municipio=None):
    """Aceita CSV ou ZIP. ZIP só é baixado quando --baixar foi explicitado."""
    if baixar:
        if not municipio:
            raise ValueError("Município obrigatório no modo --baixar")
        url = BASE_IBGE + CIDADES[municipio]["arquivo"]
        req = urllib.request.Request(url, headers={"User-Agent": "PREVINE-pesquisa-CNEFE/1.0"})
        with urllib.request.urlopen(req, timeout=90) as resposta:
            conteudo = resposta.read()
        fonte = url
    else:
        if arquivo is None:
            raise ValueError("Forneça --arquivo ou --baixar")
        conteudo = Path(arquivo).read_bytes()
        fonte = str(arquivo)
    if zipfile.is_zipfile(io.BytesIO(conteudo)):
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            nomes = [n for n in z.namelist() if n.lower().endswith(".csv")]
            if len(nomes) != 1:
                raise ValueError("ZIP deve conter exatamente um CSV; encontrados: " + str(nomes))
            conteudo = z.read(nomes[0])
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = conteudo.decode(codificacao)
            cabecalho = texto.splitlines()[0].lstrip("\ufeff")
            if "COD_ESPECIE" in cabecalho and "LATITUDE" in cabecalho:
                return texto, fonte, codificacao
        except UnicodeDecodeError:
            continue
    raise ValueError("Codificação ou cabeçalho do CNEFE não reconhecido")


def extrair(texto, codigo, incluir_coletivos=False):
    reader = csv.DictReader(io.StringIO(texto), delimiter=";")
    colunas = set(reader.fieldnames or [])
    faltam = CAMPOS - colunas
    if faltam:
        raise ValueError("Campos CNEFE faltantes: " + ", ".join(sorted(faltam)))
    contagem = Counter()
    # Não deduplicar apenas por coordenadas: apartamentos e unidades distintas
    # podem compartilhar ponto. Também não declarar 'uma linha = uma casa'.
    agrupados = {}
    for linha in reader:
        if str(linha.get("COD_MUN", "")).strip() != codigo:
            contagem["outro_municipio"] += 1
            continue
        tipo = str(linha.get("COD_ESPECIE", "")).strip()
        if tipo != "1" and not (incluir_coletivos and tipo == "2"):
            contagem["outra_especie_excluida"] += 1
            continue
        la, lo = numero(linha.get("LATITUDE")), numero(linha.get("LONGITUDE"))
        if la is None or lo is None or not math.isfinite(la) or not math.isfinite(lo):
            contagem["coordenada_invalida"] += 1
            continue
        if not (-34 < la < -27 and -58 < lo < -49):
            contagem["fora_envelope_rs"] += 1
            continue
        geocod = str(linha.get("NV_GEO_COORD", "")).strip()
        tipo_edif = str(linha.get("COD_TIPO_ESPECIE", "")).strip()
        # Não guardar endereço nominal, nomes de moradores, estabelecimento
        # nem outros campos de identificação no GeoJSON público.
        chave = (round(la, 7), round(lo, 7), tipo, tipo_edif, geocod)
        if chave not in agrupados:
            ident = hashlib.sha256(repr((codigo, chave)).encode("utf-8")).hexdigest()[:16]
            agrupados[chave] = {
                "type": "Feature", "properties": {
                    "id_anonimo": ident, "cod_municipio": codigo,
                    "especie": tipo, "tipo_edificacao": tipo_edif or None,
                    "nivel_geocodificacao": geocod or None,
                    "geocodificacao_original": geocod == "1",
                    "quantidade_registros_cnefe_no_ponto": 0,
                    "ocupacao_atual_confirmada": False,
                    "revisao_visual": "pendente",
                },
                "geometry": {"type": "Point", "coordinates": [round(lo, 7), round(la, 7)]},
            }
        agrupados[chave]["properties"]["quantidade_registros_cnefe_no_ponto"] += 1
        contagem["especie_residencial_incluida"] += 1
        contagem["nivel_geo_" + (geocod or "nulo")] += 1
    return {"type": "FeatureCollection", "features": list(agrupados.values())}, dict(contagem)


def decodificar_painel_html(path):
    text = Path(path).read_text(encoding="utf-8")
    marker = "const D="
    idx = text.find(marker)
    if idx < 0:
        raise ValueError("Painel não contém o payload D")
    data, _ = json.JSONDecoder().raw_decode(text[idx + len(marker):])
    return data


def verificar_osm(geojson, painel, raio_m=20):
    """Classificação exploratória por vizinhança; NÃO é verificação de prédio."""
    campos = {c: i for i, c in enumerate(painel["meta"]["casas_campos"])}
    casas = painel["casas"]
    unmatched = []
    associados = set()
    for f in geojson["features"]:
        lon, lat = f["geometry"]["coordinates"]
        radius = raio_m
        best_index = None
        for i, c in enumerate(casas):
            ca, co = c[campos["lat"]], c[campos["lon"]]
            dy = (lat - ca) * 110540.0
            dx = (lon - co) * 111320.0 * math.cos(math.radians(lat))
            distance = math.hypot(dx, dy)
            if distance < radius:
                radius, best_index = distance, i
        p = f["properties"]
        p["osm_edificacao_proxima"] = best_index is not None
        p["dist_osm_m"] = round(radius, 1) if best_index is not None else None
        p["correspondencia_confirmada"] = False
        p["qualidade_cruzamento"] = (
            "proximidade_em_estudo" if best_index is not None else "sem_edificacao_osm_proxima"
        )
        if best_index is not None:
            associados.add(best_index)
        else:
            unmatched.append(p["id_anonimo"])
    return {
        "pontos_cnefe_com_osm_a_ate_20m": sum(
            f["properties"]["osm_edificacao_proxima"] for f in geojson["features"]
        ),
        "pontos_cnefe_sem_osm_a_ate_20m": len(unmatched),
        "edificacoes_osm_sem_ponto_cnefe_proximo": len(casas) - len(associados),
        "n_edificacoes_osm_no_recorte": len(casas),
        "nota": "Vizinhança de centróides não valida uso residencial; precisa de footprint/ortofoto/campo.",
    }


def main():
    ap = argparse.ArgumentParser(description="Filtra endereços residenciais CNEFE, sem inferir ocupação atual")
    ap.add_argument("--cidade", choices=CIDADES, required=True)
    ap.add_argument("--arquivo", type=Path)
    ap.add_argument("--baixar", action="store_true")
    ap.add_argument("--incluir-coletivos", action="store_true",
                    help="inclui COD_ESPECIE=2, separado dos domicílios particulares")
    ap.add_argument("--saida", type=Path,
                    help="pasta para gerar GeoJSON e relatório (padrão: assets/data/risco_vida/cnefe_pesquisa)")
    args = ap.parse_args()
    if args.baixar and args.arquivo:
        ap.error("Escolha somente --arquivo ou --baixar")
    cod = CIDADES[args.cidade]["codigo"]
    texto, fonte, codificacao = ler_texto_csv(args.arquivo, args.baixar, args.cidade)
    geo, cont = extrair(texto, cod, args.incluir_coletivos)
    local = ROOT / ("santa_tereza_painel_casas.html" if args.cidade == "santa_tereza" else "mucum_painel_casas.html")
    comparacao = verificar_osm(geo, decodificar_painel_html(local)) if local.exists() else None
    saida = args.saida or ROOT / "assets" / "data" / "risco_vida" / "cnefe_pesquisa"
    saida.mkdir(parents=True, exist_ok=True)
    caminho_geo = saida / (args.cidade + "_cnefe_residencial_pesquisa.geojson")
    caminho_qa = saida / (args.cidade + "_cnefe_qa.json")
    caminho_geo.write_text(json.dumps(geo, ensure_ascii=False, separators=(",", ":"))+"\n", encoding="utf-8")
    report = {
        "municipio": args.cidade, "codigo": cod, "fonte": fonte, "codificacao": codificacao,
        "inclui_domicilio_coletivo": args.incluir_coletivos,
        "n_pontos_distintos": len(geo["features"]),
        "contagens": cont, "cruzamento_osm": comparacao,
        "referencia_temporal": "CNEFE/Censo 2022",
        "validacao_campo": False, "apto_rota_operacional": False,
        "politica": "Nenhum nome/endereço completo ou atributos individuais publicados; revisão manual obrigatória",
    }
    caminho_qa.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
