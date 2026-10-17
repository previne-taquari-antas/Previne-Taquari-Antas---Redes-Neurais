#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Documenta como o HAND krigado da planilha (INUND_HAND_2165.tif) foi gerado.

Lê a linhagem gravada pelo ArcGIS Pro nos .xml de metadados de cada produto em
D:\\PREVINE\\FAPERGS (não há scripts, projetos .aprx/.qgz, logs nem relatórios
nessa pasta) e as propriedades dos rasters/shapefiles, e grava
`metadados_hand_krigado.json` sem coordenadas de pontos.

Uso:
  python pesquisas/validacao-campo-hand-santa-tereza/metadados_hand_krigado.py \
      [--fapergs-dir "D:\\PREVINE\\FAPERGS"]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import rasterio

HERE = Path(__file__).resolve().parent
OUT = HERE / "metadados_hand_krigado.json"

# ordem da cadeia de processamento até o INUND_HAND_2165
CADEIA = [
    "MOSAICO_LIDAR_RS.tif", "CLIP_MOSAICO_LIDAR_RS.tif", "FILL_CLIP_MOSAICO_LIDAR_RS.tif",
    "FLOWDIR_CLIP_MOSAICO_LIDAR_RS.tif", "FLOWACC_CLIP_MOSAICO_LIDAR_RS.tif",
    "CON_FLOWACC_CLIP_MOSAICO_LIDAR_RS.tif", "STREAM_CON_FLOWACC_CLIP_MOSAICO_LIDAR_RS.tif",
    "STREAM.shp", "STREAM_TAQUARI_ANTAS.shp", "STREAM_TAQUARI_ANTAS_pts.shp",
    "STREAM_TAQUARI_ANTAS_pts_elev.shp", "KRIG_HAND_2165.tif", "INUND_HAND_2165.tif",
]


def processos(xml_path: Path) -> list[dict]:
    root = ET.parse(xml_path).getroot()
    out = []
    for e in root.iter("Process"):
        cmd = (e.text or "").replace("E:\\GUI\\FAPERGS\\", "").replace("E:\\GUI\\FAPERGS", ".")
        cmd = re.sub(r'"CIMDATA=.*?&lt;/CIMStandardDataConnection&gt;"|"CIMDATA=.*?</CIMStandardDataConnection>"',
                     '"CIMDATA=…"', cmd, flags=re.S)
        out.append({"ferramenta": e.get("ToolSource", "").split("\\")[-1],
                    "data": e.get("Date"), "hora": e.get("Time"), "comando": cmd.strip()})
    return out


def env(xml_path: Path) -> dict:
    root = ET.parse(xml_path).getroot()
    g = lambda q: (root.find(q).text if root.find(q) is not None else None)  # noqa: E731
    return {"CreaDate": g(".//Esri/CreaDate"), "CreaTime": g(".//Esri/CreaTime"),
            "software": g(".//envirDesc"),
            "contato_autor": g(".//rpIndName") or g(".//rpOrgName") or g(".//idCredit")}


def ler_dbf(path: Path) -> tuple[list[str], list[dict]]:
    f = path.read_bytes()
    n = struct.unpack("<I", f[4:8])[0]
    hl, rl = struct.unpack("<H", f[8:10])[0], struct.unpack("<H", f[10:12])[0]
    campos, i = [], 32
    while f[i] != 0x0D:
        campos.append((f[i:i + 11].split(b"\0")[0].decode(), f[i + 16]))
        i += 32
    regs = []
    for k in range(n):
        rec, o, v = f[hl + k * rl + 1: hl + (k + 1) * rl], 0, {}
        for nome, tam in campos:
            v[nome] = rec[o:o + tam].decode("latin1").strip()
            o += tam
        regs.append(v)
    return [c for c, _ in campos], regs


def props_raster(p: Path) -> dict:
    with rasterio.open(p) as ds:
        t = ds.tags(1)
        return {"largura": ds.width, "altura": ds.height, "resolucao_m": list(ds.res),
                "tipo": ds.dtypes[0], "nodata": ds.nodata,
                "crs": ds.crs.to_string() if ds.crs else None,
                "mesma_grade_que_CLIP": None,
                "min": t.get("STATISTICS_MINIMUM"), "max": t.get("STATISTICS_MAXIMUM"),
                "media": t.get("STATISTICS_MEAN"), "_transform": ds.transform}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fapergs-dir", type=Path, default=Path(r"D:\PREVINE\FAPERGS"))
    d = ap.parse_args().fapergs_dir

    cadeia = []
    for nome in CADEIA:
        xmlp = d / (nome + ".xml")
        if not xmlp.exists():
            continue
        ultimo = processos(xmlp)
        cadeia.append({"produto": nome, **env(xmlp), "processos": ultimo,
                       "data_arquivo": dt.datetime.fromtimestamp((d / nome).stat().st_mtime)
                       .isoformat(timespec="seconds")})

    rasters = {n: props_raster(d / n) for n in ("CLIP_MOSAICO_LIDAR_RS.tif", "KRIG_HAND_2165.tif",
                                                "INUND_HAND_2165.tif")}
    t0 = rasters["CLIP_MOSAICO_LIDAR_RS.tif"]["_transform"]
    for r in rasters.values():
        r["mesma_grade_que_CLIP"] = r.pop("_transform").almost_equals(t0)

    _, arcos_all = ler_dbf(d / "STREAM.dbf")
    _, arcos = ler_dbf(d / "STREAM_TAQUARI_ANTAS.dbf")
    campos_pts, pts = ler_dbf(d / "STREAM_TAQUARI_ANTAS_pts_elev.dbf")
    z = np.array([float(p["RASTERVALU"]) for p in pts])
    hand = np.array([float(p["HAND"]) for p in pts])

    meta = {
        "produto": "INUND_HAND_2165.tif (HAND da versão 'HAND 2165' da planilha sumario_erros_hand.xlsx)",
        "fonte_da_informacao": (
            "linhagem (geoprocessing history) gravada pelo ArcGIS Pro nos .xml de cada arquivo em "
            "D:/PREVINE/FAPERGS; a pasta não tem scripts, projetos .aprx/.qgz, logs, readme nem relatórios"),
        "resumo": {
            "mdt_de_origem": "CLIP_MOSAICO_LIDAR_RS.tif — LiDAR bruto 1 m (recorte do MOSAICO_LIDAR_RS, "
                             "mosaico de 4 folhas MDT_RS do LiDAR do Governo do RS)",
            "resolucao": "1 m (KRIG e INUND na mesma grade do CLIP: 12988 × 19426 células)",
            "rede_de_drenagem": "FILL → FLOWDIR (D8) → FLOWACC → Con(FLOWACC ≥ 1.000.000 células ≈ 1 km²) "
                                "→ StreamLink → StreamToFeature (STREAM, %d arcos) → exportados %d arcos para "
                                "STREAM_TAQUARI_ANTAS (sem cláusula SQL no comando: seleção manual no mapa)"
                                % (len(arcos_all), len(arcos)),
            "o_que_foi_krigado": (
                "o campo HAND de STREAM_TAQUARI_ANTAS_pts_elev = RASTERVALU + 21,65, em que RASTERVALU é a "
                "cota do LiDAR bruto 1 m (ExtractValuesToPoints, sem interpolação) em todos os %d vértices "
                "dos arcos do rio. Ou seja, krigou-se uma superfície de água 21,65 m acima da cota do leito." % len(pts)),
            "krigagem": "Kriging ordinária (ArcGIS Spatial Analyst), modelo esférico: lag 32,08 m, alcance "
                        "13.345,28 m, patamar parcial 63,386, pepita 0; célula de saída 1 m; raio de busca "
                        "variável, 12 pontos",
            "inund_hand_2165": "RasterCalculator: CLIP_MOSAICO_LIDAR_RS − KRIG_HAND_2165. Negativo = abaixo "
                               "da superfície de água de 21,65 m. HAND krigado = INUND_HAND_2165 + 21,65 = "
                               "z_LiDAR − cota do rio krigada.",
            "significado_de_2165": "limiar de 21,65 m = pico de set/2023 na régua (23,65 m) − zero antigo de "
                                   "2,00 m (versão 'HAND 2165' / 'lâmina modelo1' da planilha)",
            "diferenca_para_o_hand_do_site": (
                "não segue o caminho D8 até o rio: a cota de referência é a do rio krigada no próprio local "
                "(interpolação espacial, sem conectividade hidrológica nem barreiras). O HAND 5 m do site "
                "(gerar_hand_lidar_santa_tereza.py) usa a célula do rio para onde o ponto escoa."),
            "data": "2026-09-02 (13:39 recorte do LiDAR; 14:14 cálculo do campo HAND; 15:20 krigagem; "
                    "15:27 INUND_HAND_2165), hora local do computador que processou",
            "autor": "não registrado nos metadados (sem contato/autor nos .xml). Processado em ArcGIS Pro 3.3 "
                     "(13.3.0.52636) no Windows build 26200, na pasta E:\\GUI\\FAPERGS",
        },
        "cadeia_de_processamento": cadeia,
        "rasters": rasters,
        "pontos_do_rio": {
            "arquivo": "STREAM_TAQUARI_ANTAS_pts_elev.shp", "campos": campos_pts, "n": len(pts),
            "arcos": len({p["arcid"] for p in pts}),
            "cota_lidar_m": {"min": round(float(z.min()), 3), "mediana": round(float(np.median(z)), 3),
                             "max": round(float(z.max()), 3)},
            "hand_menos_cota_m": round(float(np.median(hand - z)), 4),
        },
    }
    OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(meta["resumo"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
