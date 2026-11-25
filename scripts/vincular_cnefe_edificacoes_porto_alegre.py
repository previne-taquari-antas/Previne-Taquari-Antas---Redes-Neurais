#!/usr/bin/env python3
"""Auditoria CNEFE 2022 x edificações OSM de Porto Alegre (IBGE 4314902).

Não converte a distância ao telhado em residência validada. Mantém um registro
por finalidade domiciliar e separa contagem de endereços da de edificações.

Exemplo:
 python scripts/vincular_cnefe_edificacoes_porto_alegre.py \
   --cnefe 4314902_PORTO_ALEGRE.csv --osm edificios_poa.geojson --saida saida_poa
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import io
import zipfile
import urllib.request
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import Point, shape, mapping
from shapely.ops import transform
from shapely.strtree import STRtree

COD_MUNICIPIO = "4314902"
TO_METERS = Transformer.from_crs("EPSG:4326", "EPSG:31982", always_xy=True).transform
TO_GEO = Transformer.from_crs("EPSG:31982", "EPSG:4326", always_xy=True).transform
EXCLUIR = {"industrial", "warehouse", "commercial", "retail", "office", "school",
           "university", "college", "kindergarten", "hospital", "public", "civic",
           "church", "religious", "transportation", "train_station", "hotel",
           "supermarket", "kiosk", "manufacture", "factory", "hangar", "barn",
           "stable", "farm_auxiliary", "storage_tank", "garages", "garage", "shed",
           "roof", "construction", "greenhouse", "service", "toilets"}
RESIDENCIAL = {"residential", "house", "detached", "semidetached_house", "terrace",
               "apartments", "bungalow", "cabin", "farm", "dormitory", "static_caravan"}


def norm(v: Any) -> str:
    s = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def as_float(v):
    try:
        return float(str(v).strip().replace(",", "."))
    except (ValueError, TypeError):
        return None


def field(row, *names):
    return next((row.get(x) for x in names if row.get(x) not in (None, "")), "")


def endereco(row):
    tipo = field(row, "NOM_TIPO_SEGLOGR")
    nome = field(row, "NOM_SEGLOGR")
    titulo = field(row, "NOM_TITULO_SEGLOGR")
    return norm(" ".join(x for x in (tipo, titulo, nome) if x))


def num(row):
    v = field(row, "NUM_ENDERECO")
    return norm(v)


def osm_addr(props):
    return (norm(field(props, "addr:street", "addr_street")),
            norm(field(props, "addr:housenumber", "addr_housenumber")))


def extrair_predios(path):
    src = json.loads(Path(path).read_text(encoding="utf8"))
    fs = src.get("features", []) if src.get("type") == "FeatureCollection" else []
    predios = []
    for i, f in enumerate(fs):
        g = f.get("geometry")
        if not g or g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        p = dict(f.get("properties") or {})
        tags = p.get("tags")
        if isinstance(tags, dict):
            p = {**tags, **p}
        tipo = norm(field(p, "building")).lower()
        if tipo in EXCLUIR or norm(field(p, "landuse")).lower() in {"industrial", "commercial"}:
            continue
        if norm(field(p, "amenity")).lower() in {"school", "hospital", "place_of_worship", "university"}:
            continue
        try:
            poly = transform(TO_METERS, shape(g))
            if not poly.is_valid:
                poly = poly.buffer(0)
        except Exception:
            continue
        if poly.is_empty or poly.area < 20 or poly.area > 20000:
            continue
        ident = str(field(p, "@id", "osm_id", "id") or f"feature-{i}")
        street, number = osm_addr(p)
        predios.append({"id": ident, "geom": poly, "centro": poly.representative_point(),
                        "tipo": tipo or "sem_tag", "street": street, "number": number,
                        "area_m2": round(poly.area),
                        "residencial_explicito": tipo in RESIDENCIAL})
    return predios


def baixar_cnefe(saida):
    """Baixa o ZIP municipal público do IBGE, sem alterar seus registros."""
    url = ("https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/"
           "Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/43_RS/"
           "4314902_PORTO_ALEGRE.zip")
    path = Path(saida) / "4314902_PORTO_ALEGRE.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        urllib.request.urlretrieve(url, path)
    return path


def ler_cnefe(path):
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            names = [x for x in z.namelist() if x.lower().endswith(".csv")]
            if len(names) != 1:
                raise ValueError("ZIP CNEFE precisa conter exatamente um CSV municipal")
            with z.open(names[0]) as h:
                yield from _ler_cnefe_stream(io.TextIOWrapper(h, encoding="utf-8-sig", errors="replace", newline=""))
    else:
        with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
            yield from _ler_cnefe_stream(fh)


def _ler_cnefe_stream(fh):
    reader = csv.DictReader(fh, delimiter=";")
    if not reader.fieldnames or "COD_ESPECIE" not in reader.fieldnames:
        fh.seek(0)
        reader = csv.DictReader(fh, delimiter=",")
    if not reader.fieldnames or "COD_ESPECIE" not in reader.fieldnames:
        raise ValueError("CSV CNEFE sem campo COD_ESPECIE")
    for i, row in enumerate(reader):
        if str(field(row, "COD_MUNICIPIO", "COD_MUN")).strip() != COD_MUNICIPIO:
            continue
        if str(field(row, "COD_ESPECIE")).strip() != "1":
            continue
        la = as_float(field(row, "LATITUDE"))
        lo = as_float(field(row, "LONGITUDE"))
        if la is not None and lo is not None and not (-30.7 < la < -29.7 and -52 < lo < -50):
            la, lo = None, None
        yield {"chave": str(field(row, "COD_UNICO_ENDERECO") or f"linha-{i+2}"),
               "linha": i+2, "lat": la, "lon": lo, "nv": str(field(row, "NV_GEO_COORD")),
               "rua": endereco(row), "numero": num(row),
               "cep": str(field(row, "CEP")),
               "setor": str(field(row, "COD_SETOR")),
               "tipo_domicilio": str(field(row, "COD_TIPO_ESPECIE"))}


def pontuar(addr, building, distancia, dentro):
    # Endereços OSM são escassos; distância por si nunca é confirmação.
    has_num = bool(addr["numero"] and building["number"])
    nmatch = has_num and addr["numero"] == building["number"]
    nconflict = has_num and not nmatch
    has_rua = bool(addr["rua"] and building["street"])
    rua_match = has_rua and (addr["rua"] == building["street"] or
                               addr["rua"].endswith(" " + building["street"]) or
                               building["street"].endswith(" " + addr["rua"]))
    rua_conflict = has_rua and not rua_match
    if nconflict or rua_conflict:
        return None
    s = (70 if nmatch and rua_match else 37 if nmatch else 0)
    s += 12 if rua_match else 0
    s += 16 if dentro else max(0, 14 - distancia / 3)
    s += 5 if building["residencial_explicito"] else 0
    return round(s, 2), nmatch, rua_match


def processar(cnefe, osm, saida, max_dist=40, revisao_max=2500, revisoes=None):
    predios = extrair_predios(osm)
    if not predios:
        raise ValueError("Nenhuma edificação utilizável no GeoJSON OSM")
    geoms = [x["geom"] for x in predios]
    tree = STRtree(geoms)
    rows = list(ler_cnefe(cnefe))
    seen = Counter((round(r["lat"], 6), round(r["lon"], 6)) for r in rows
                   if r["lat"] is not None and r["lon"] is not None)
    out = Path(saida)
    out.mkdir(parents=True, exist_ok=True)
    status_counts = Counter()
    nv_counts = Counter(r["nv"] for r in rows)
    tipo_counts = Counter(r["tipo_domicilio"] for r in rows)
    shared_groups = sum(v>1 for v in seen.values())
    links = Counter()
    aprovadas = {}
    if revisoes:
        with open(revisoes, encoding="utf-8-sig", newline="") as f:
            for rev in csv.DictReader(f):
                if (rev.get("tipo_confirmado", "").strip().lower() == "domicilio"
                    and rev.get("evidencia", "").strip()
                    and rev.get("id_cnefe") and rev.get("osm_id")):
                    if rev["id_cnefe"] in aprovadas:
                        raise ValueError("revisão duplicada no CSV: " + rev["id_cnefe"])
                    aprovadas[rev["id_cnefe"]] = rev
    ids_b = {b["id"]:b for b in predios}
    aceitas = []
    geom_features = []
    candidatos = []
    with (out/"associacoes_auditoria.csv").open("w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=["id_cnefe", "linha_origem", "nv_geo_coord", "setor",
                           "rua_ibge", "numero_ibge", "tipo_domicilio_ibge", "lat_original", "lon_original",
                           "endereco_agrupado", "quantidade_mesmo_ponto", "status", "osm_candidato",
                           "distancia_footprint_m", "tipo_osm", "candidatos_competidores",
                           "justificativa", "lat_proposta", "lon_proposta", "street_view_url"])
        wr.writeheader()
        for r in rows:
            lat, lon = r["lat"], r["lon"]
            cluster = seen[(round(lat, 6), round(lon, 6))] if lat is not None else 0
            agrupado = cluster > 1
            base = {"id_cnefe": r["chave"], "linha_origem": r["linha"],
                    "nv_geo_coord": r["nv"], "setor": r["setor"],
                    "rua_ibge": r["rua"], "numero_ibge": r["numero"], "tipo_domicilio_ibge": r["tipo_domicilio"],
                    "lat_original": lat, "lon_original": lon, "endereco_agrupado": int(agrupado),
                    "quantidade_mesmo_ponto": cluster, "status": "pendente", "osm_candidato": "",
                    "distancia_footprint_m": "", "tipo_osm": "",
                    "candidatos_competidores": 0, "justificativa": "",
                    "lat_proposta": "", "lon_proposta": "", "street_view_url": ""}
            if lat is None:
                base["justificativa"] = "coordenada inválida/ausente"
            else:
                pt = transform(TO_METERS, Point(lon, lat))
                inds = tree.query(pt.buffer(max_dist))
                options = []
                for j in inds:
                    b = predios[int(j)]
                    dist = pt.distance(b["geom"])
                    if dist > max_dist:
                        continue
                    score = pontuar(r, b, dist, b["geom"].covers(pt))
                    if score is not None:
                        options.append((score[0], int(j), dist, score[1], score[2]))
                options.sort(key=lambda x: (-x[0], x[2]))
                if options:
                    s, k, d, numero_ok, rua_ok = options[0]
                    b = predios[k]
                    second = options[1][0] if len(options) > 1 else -math.inf
                    unambiguous = s-second >= 12
                    base.update(osm_candidato=b["id"], distancia_footprint_m=round(d, 1),
                                tipo_osm=b["tipo"], candidatos_competidores=len(options))
                    # Nunca publicar correção automática do CNEFE com base só em distância.
                    if numero_ok and rua_ok and unambiguous and b["residencial_explicito"]:
                        base["status"] = "candidato_forte_revisao_visual"
                        base["justificativa"] = "logradouro + número OSM coincidentes, tipo residencial; requer inspeção visual"
                    else:
                        base["status"] = "candidato_incertamente_residencial"
                        base["justificativa"] = "sem endereço OSM completo, uso ambíguo ou competidores próximos"
                    if agrupado and (r["nv"] in {"3","4","5","6"} or not (numero_ok and rua_ok)) and not (r["nv"] == "2" and r["tipo_domicilio"] == "103"):
                        base["status"] = "esquina_ou_aglomerado_revisar"
                        base["justificativa"] = "várias unidades na mesma coordenada; não redistribuir sem identificação"
                    if agrupado and r["nv"] == "2" and r["tipo_domicilio"] == "103":
                        base["status"] = "apartamentos_mesmo_edificio_revisar"
                        base["justificativa"] = "agrupamento legítimo de apartamentos em edifício; não espalhar unidades"
                    # Sugestão interna, não localização corrigida confirmada.
                    dest = b["centro"]
                    lon2, lat2 = transform(TO_GEO, dest).coords[0]
                    base["lat_proposta"] = round(lat2, 7)
                    base["lon_proposta"] = round(lon2, 7)
                    base["street_view_url"] = ("https://www.google.com/maps/@?api=1&map_action=pano"
                                               f"&viewpoint={lat2:.7f}%2C{lon2:.7f}")
                    links[b["id"]] += 1
                else:
                    base["status"] = "sem_edificacao_compativel"
                    base["justificativa"] = "nenhuma geometria candidata no raio/sem divergência cadastral"
            if lat is not None and not base["street_view_url"]:
                base["street_view_url"] = ("https://www.google.com/maps/@?api=1&map_action=pano"
                    f"&viewpoint={lat:.7f}%2C{lon:.7f}")
            rev = aprovadas.get(r["chave"])
            if rev:
                conf = ids_b.get(rev["osm_id"])
                if conf is None:
                    raise ValueError("OSM não encontrado na revisão de " + r["chave"])
                if not (conf["residencial_explicito"] or rev.get("uso_residencial_conferido", "").strip().lower() == "sim"):
                    raise ValueError("uso residencial não confirmado para " + r["chave"])
                dest = conf["centro"]
                novo_lon, novo_lat = transform(TO_GEO, dest).coords[0]
                base["status"] = "revisado_aprovado"
                base["justificativa"] = "inspeção manual; evidência: " + rev["evidencia"]
                base["osm_candidato"] = conf["id"]
                base["lat_proposta"] = round(novo_lat, 7)
                base["lon_proposta"] = round(novo_lon, 7)
                aceitas.append({"type":"Feature","geometry":{"type":"Point","coordinates":[novo_lon,novo_lat]},
                               "properties":{"id_cnefe":r["chave"],"osm_id":conf["id"],
                                             "situacao":"aprovado_com_inspecao_manual", "edificacao_unica":conf["id"]}})
            status_counts[base["status"]] += 1
            wr.writerow(base)
            if base["status"] in ("candidato_forte_revisao_visual", "esquina_ou_aglomerado_revisar",
                                  "candidato_incertamente_residencial", "apartamentos_mesmo_edificio_revisar", "sem_edificacao_compativel"):
                # Amostragem determinística para revisão visual prioritária.
                if len(candidatos) < revisao_max or base["status"] == "esquina_ou_aglomerado_revisar":
                    candidatos.append(base)
            if lat is not None:
                # Geometria original sempre conservada, não transfere os pontos às propostas.
                if len(geom_features) < revisao_max and (agrupado or base["status"] != "sem_edificacao_compativel"):
                    geom_features.append({"type":"Feature", "geometry":{"type":"Point", "coordinates":[lon,lat]},
                                          "properties":{"id":r["chave"], "nv":r["nv"], "status":base["status"],
                                                        "unidades_mesmo_ponto":cluster,
                                                        "osm_sugerido":base["osm_candidato"]}})
    candidatos.sort(key=lambda x: (x["status"] != "esquina_ou_aglomerado_revisar",
                                    x["status"] != "apartamentos_mesmo_edificio_revisar",
                                    -int(x["quantidade_mesmo_ponto"] or 0)))
    with (out/"revisao_street_view.csv").open("w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=list(candidatos[0]) if candidatos else
                            ["id_cnefe", "status", "street_view_url"])
        wr.writeheader()
        wr.writerows(candidatos[:revisao_max])
    (out/"pontos_revisados.geojson").write_text(json.dumps({"type":"FeatureCollection","features":aceitas},ensure_ascii=False),encoding="utf8")
    (out/"amostra_mapa.geojson").write_text(json.dumps({"type":"FeatureCollection",
                                     "features":geom_features}, ensure_ascii=False), encoding="utf8")
    relatorio = {"municipio":"Porto Alegre", "cod_municipio":COD_MUNICIPIO,
                 "fonte":"CNEFE 2022 IBGE + edificações OSM (entrada da execução)",
                 "data_processamento":date.today().isoformat(),
                 "domicilios_particulares_cnefe":len(rows),
                 "edificacoes_osm_candidatas":len(predios),
                 "pontos_cnefe_distintos_com_coordenada":len(seen),
                 "coordenadas_compartilhadas_grupos":shared_groups,
                 "por_nivel_geocodificacao_ibge":dict(nv_counts),
                 "por_tipo_domicilio_ibge":dict(tipo_counts),
                 "domicilios_em_pontos_compartilhados":sum(seen[(round(r['lat'],6),round(r['lon'],6))]>1
                     for r in rows if r['lat'] is not None),
                 "status":dict(status_counts), "edificacoes_com_cnefe_candidato":len(links),
                 "nenhuma_correcao_confirmada_automaticamente":True,
                 "enderecos_aprovados_por_revisao_humana":len(aceitas),
                 "observacao":"Amostra visual limitada; CSV de auditoria contém 100% dos domicílios. Pontos propostos não substituem posições originais."}
    (out/"resumo.json").write_text(json.dumps(relatorio,ensure_ascii=False,indent=2),encoding="utf8")
    return relatorio


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cnefe", help="ZIP ou CSV municipal integral IBGE 4314902; se omitido, baixar ZIP oficial")
    ap.add_argument("--osm", required=True, help="GeoJSON Polygon/MultiPolygon de edificações OSM Porto Alegre")
    ap.add_argument("--saida", default="saida_porto_alegre")
    ap.add_argument("--max-dist", type=float, default=40)
    ap.add_argument("--revisao-max", type=int, default=2500)
    ap.add_argument("--revisoes", help="CSV de decisões manuais com id_cnefe,osm_id,tipo_confirmado,evidencia,uso_residencial_conferido")
    a = ap.parse_args()
    cnefe = a.cnefe or baixar_cnefe(a.saida)
    print(json.dumps(processar(cnefe,a.osm,a.saida,a.max_dist,a.revisao_max,a.revisoes),ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
