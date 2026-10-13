#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extrai dos rasters de Santa Tereza os valores nas posições de campo (SBSR 2027).

Para cada ponto × evento da validação de campo do HAND, nas posições do
celular (`_cel`) e do RTK (`_rtk`):

1. `z_lidar1m`: altitude do LiDAR bruto de 1 m (CLIP_MOSAICO_LIDAR_RS.tif),
   célula que contém o ponto;
2. `hand_conv` e `hand_barreira`: HAND em 5 m, convencional e com barreira
   (limiar hidráulico T_H), calculados exatamente como no gerador
   `codigo_python/02_mdt_hand_mancha/gerar_hand_lidar_santa_tereza.py`
   (read_dem, read_flowacc, read_flowdir, compute_hand_flowpath; rio principal
   com FLOWACC >= 50.000.000);
3. `z_dren`: cota (LiDAR 5 m) da célula do rio principal onde termina o
   caminho D8 do ponto (= z_5m − hand_conv; quando hand_conv = 0 o valor pode
   ter sido truncado em zero pelo gerador e a coluna `z_dren_truncado` avisa);
4. `hand_krig` (T_H do HAND krigado = INUND_HAND_2165 + 21,65 m) e
   `z_dren_krig = z_lidar1m − hand_krig` (cota do rio krigada no ponto): HAND da
   versão da planilha ("HAND 2165"), de `D:\PREVINE\FAPERGS\INUND_HAND_2165.tif`
   (ver `metadados_hand_krigado.json`);
5. `th_planilha_m`: T_H implícito na planilha, (H_r − 1,60) − lamina_hand_m, e
   a coluna `th_planilha_corresponde` dizendo se ele bate com o HAND
   convencional, com o com barreira ou com o HAND krigado (2165).

Posições do celular: a planilha `sumario_erros_hand.xlsx` só traz as
coordenadas RTK (linhas 21–43); a geometria dos pontos do celular ("Point ZM")
não vem com X/Y. Se houver um CSV com `id,E,N` (SIRGAS 2000 / UTM 22S) das
posições do celular, passe-o em `--cel`; sem ele, as colunas `_cel`
amostradas ficam vazias e a comparação de T_H usa a cota LiDAR que a própria
planilha registrou na posição do celular (`z_lidar_cel_planilha_m`) menos
`z_dren_rtk` (estimativa de hand_conv no celular, supondo o mesmo trecho de
drenagem) e os valores na posição RTK.

Nenhuma coordenada é gravada: só ID, tipo, evento e valores.

Uso:
  python pesquisas/validacao-campo-hand-santa-tereza/extrair_rasters_rtk.py \
      caminho/sumario_erros_hand.xlsx [--cel posicoes_celular.csv] \
      [--source-dir "D:\\PREVINE\\hand\\santa tereza"]
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import rasterio

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT_CSV = HERE / "rasters_1m_nas_posicoes.csv"
GERADOR = ROOT / "codigo_python" / "02_mdt_hand_mancha" / "gerar_hand_lidar_santa_tereza.py"
ANALISE = HERE / "analise_erros_campo.py"

ZERO_REGUA_M = 1.60
PICO_REGUA_M = {"2023-09": 23.65, "2023-11": 21.61, "2024-05": 22.33}
TOL_TH_M = 0.15  # tolerância para dizer que T_H "bate" com uma das grades
# INUND_HAND_2165 = CLIP_MOSAICO_LIDAR_RS − KRIG_HAND_2165, e KRIG_HAND_2165 é a
# krigagem do campo HAND de STREAM_TAQUARI_ANTAS_pts_elev = cota LiDAR do rio + 21,65 m.
# Logo HAND_krig = INUND_HAND_2165 + 21,65 e cota do rio krigada = z − HAND_krig.
KRIG_OFFSET_M = 21.65


def carregar(nome: str, caminho: Path):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ler_cel(path: Path | None) -> dict[str, tuple[float, float]]:
    if path is None:
        return {}
    out = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[row["id"].strip()] = (float(row["E"]), float(row["N"]))
    return out


def amostrar_1m(path: Path, pts: dict[str, tuple[float, float]]) -> dict[str, float]:
    out = {}
    with rasterio.open(path) as ds:
        nod = ds.nodata
        for k, (e, n) in pts.items():
            r, c = ds.index(e, n)
            if not (0 <= r < ds.height and 0 <= c < ds.width):
                out[k] = math.nan
                continue
            v = float(ds.read(1, window=((r, r + 1), (c, c + 1)))[0, 0])
            out[k] = math.nan if (nod is not None and v == nod) or v > 1e20 else v
    return out


def grade_hand(gen, source_dir: Path):
    terrain, transform, crs, _, _ = gen.read_dem(source_dir / "CLIP_MOSAICO_LIDAR_RS.tif")
    routing, rt, rcrs, _, _ = gen.read_dem(source_dir / "FILL_CLIP_MOSAICO_LIDAR_RS.tif")
    if terrain.shape != routing.shape or not transform.almost_equals(rt):
        raise RuntimeError("CLIP e FILL não estão na mesma grade")
    acc_path = source_dir / "FLOWACC_CLIP_MOSAICO_LIDAR_RS.tif"
    with rasterio.open(acc_path) as ds:
        flowacc = gen.read_flowacc(acc_path, terrain.shape, transform, crs, ds.nodata)
    flowdir = gen.read_flowdir(source_dir / "FLOWDIR_CLIP_MOSAICO_LIDAR_RS.tif", terrain.shape, transform, crs)
    hand, hyd, river, diag = gen.compute_hand_flowpath(terrain, routing, flowdir, flowacc)
    return terrain, hand, hyd, transform, diag


def amostrar_grade(arr, transform, e, n):
    c, r = ~transform * (e, n)
    r, c = int(math.floor(r)), int(math.floor(c))
    if 0 <= r < arr.shape[0] and 0 <= c < arr.shape[1]:
        return float(arr[r, c])
    return math.nan


def r3(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 3)


def classificar(th, conv, barr, krig=None):
    """Diz qual grade reproduz o T_H da planilha (tolerância TOL_TH_M)."""
    if th is None:
        return ""
    cand = {"convencional": conv, "barreira": barr, "krig2165": krig}
    dif = {k: abs(th - v) for k, v in cand.items() if v is not None and not math.isnan(v)}
    if not dif:
        return ""
    ok = sorted(k for k, d in dif.items() if d <= TOL_TH_M)
    if not ok:
        return "nenhum"
    return "+".join(ok)


# --------------------------------------------------------------------------
# Metadados do LiDAR
# --------------------------------------------------------------------------
OUT_META = HERE / "metadados_lidar.json"


def _gdalinfo_json(path: Path) -> dict:
    """`gdalinfo -json` se o executável existir; senão o equivalente via rasterio."""
    import datetime as dt
    import shutil
    import subprocess
    import xml.etree.ElementTree as ET

    if shutil.which("gdalinfo"):
        info = json.loads(subprocess.run(["gdalinfo", "-json", "-nomd", str(path)], check=True,
                                         capture_output=True, text=True).stdout)
        info["_fonte"] = "gdalinfo -json"
    else:
        with rasterio.open(path) as ds:
            info = {
                "_fonte": f"rasterio {rasterio.__version__} / GDAL {rasterio.__gdal_version__} "
                          "(gdalinfo não disponível no ambiente; mesmos campos)",
                "driverShortName": ds.driver,
                "size": [ds.width, ds.height],
                "coordinateSystem": {"wkt": ds.crs.to_wkt(version="WKT2_2019") if ds.crs else None},
                "epsg_compound": ds.crs.to_epsg() if ds.crs else None,
                "geoTransform": list(ds.transform.to_gdal()),
                "resolucao_m": list(ds.res),
                "cornerCoordinates_utm": dict(zip(("west", "south", "east", "north"), ds.bounds)),
                "metadata": {(ns or ""): ds.tags(ns=ns) for ns in [None] + [n for n in ds.tag_namespaces()
                                                                     if n != "DERIVED_SUBDATASETS"]},
                "bands": [{"band": 1, "type": ds.dtypes[0], "noDataValue": ds.nodata,
                           "description": ds.descriptions[0], "unit": ds.units[0],
                           "overviews_factor": ds.overviews(1), "metadata": ds.tags(1)}],
                "compression": str(ds.compression.value if ds.compression else None),
            }
    vizinhos = sorted(p.name for p in path.parent.iterdir() if p.name.startswith(path.name))
    info["arquivos_associados"] = vizinhos
    info["datas_arquivo"] = {
        n: dt.datetime.fromtimestamp((path.parent / n).stat().st_mtime).isoformat(timespec="seconds")
        for n in vizinhos
    }
    xmlp = path.with_name(path.name + ".xml")
    if xmlp.exists():
        root = ET.parse(xmlp).getroot()
        g = lambda q: (root.find(q).text if root.find(q) is not None else None)  # noqa: E731
        wkt = g(".//coordRef/peXml")
        info["esri_xml"] = {
            "CreaDate": g(".//Esri/CreaDate"), "ModDate": g(".//Esri/ModDate"),
            "projcsn": g(".//coordRef/projcsn"),
            "vertcs_no_wkt_esri": (wkt[wkt.find("VERTCS"):wkt.find("</WKT>")].replace("&quot;", '"')
                                   if wkt and "VERTCS" in wkt else None),
            "lineage": [{"tool": e.get("ToolSource", "").split("\\")[-1], "date": e.get("Date"),
                         "cmd": (e.text or "").replace("E:\\GUI\\FAPERGS\\", "")}
                        for e in root.iter("Process")],
            "software": g(".//envirDesc"),
        }
    return info


def gerar_metadados(lidar: Path, fapergs: Path, resumo_csv: dict) -> dict:
    meta = {"arquivo": lidar.name, "gdalinfo": _gdalinfo_json(lidar)}
    mos = fapergs / "MOSAICO_LIDAR_RS.tif"
    if mos.exists():
        meta["mosaico_origem"] = _gdalinfo_json(mos)
        with rasterio.open(mos) as m:
            meta["mosaico_origem"]["geoTransform_vs_folhas"] = m.transform.to_gdal()
    folhas = sorted(fapergs.glob("SH-22-*/*_MDT_RS.tif"))
    if folhas:
        with rasterio.open(folhas[0]) as f0:
            gt = f0.transform
            area = f0.tags().get("AREA_OR_POINT")
        with rasterio.open(lidar) as ds:
            t = ds.transform
            area_m = ds.tags().get("AREA_OR_POINT")
        meta["folhas_originais"] = {
            "n_folhas_tif": len(folhas),
            "padrao_nome": "SH-22-V-D-II-2-SE-A-I-1_MDT_RS.tif (articulação 1:2.000 em quadrículas de 1:25.000)",
            "zips_data_arquivo": sorted({dt for dt in (
                __import__("datetime").datetime.fromtimestamp(z.stat().st_mtime).date().isoformat()
                for z in fapergs.glob("SH-22-*.zip"))}),
            "conteudo_zip": "somente .tif/.tfw/.prj/.aux.xml por folha; sem relatório, xml de metadados, data de voo ou acurácia",
            "prj_folha": "SIRGAS 2000 / UTM 22S, sem componente vertical",
            "AREA_OR_POINT_folha": area, "AREA_OR_POINT_clip": area_m,
            "deslocamento_grade_clip_vs_folhas_m": [round((t.c - gt.c) % 1.0, 4), round((t.f - gt.f) % 1.0, 4)],
        }
    meta["achados"] = {
        "crs_horizontal": "SIRGAS 2000 / UTM zone 22S (EPSG:31982)",
        "crs_vertical": "não declarado: COMPOUNDCRS com VERTCRS 'unknown' (VDATUM unknown, unidade metro); as folhas originais não trazem componente vertical",
        "indicio_referencial_vertical": (
            "altitude ortométrica: LiDAR 1 m − RTK (H = h − 6,46 m) tem mediana "
            f"{resumo_csv['dz_lidar1m_menos_rtk_validos']['mediana_m']} m nos vértices válidos; se fosse "
            "elipsoidal a diferença seria ~+6,4 m (como no MDT de drone). Compatível com hgeoHNOR2020/Imbituba, "
            "com viés positivo de ~0,2–0,3 m"),
        "data_do_voo": "não encontrada nos arquivos locais (tif, xml ESRI, aux.xml, prj, zips); as datas disponíveis são de download (2026-08-19) e processamento no ArcGIS Pro (2026-09-02)",
        "acuracia_densidade_fornecedor": "não encontrados nos arquivos locais",
        "contexto_programa": (
            "Santa Tereza fica na porção leste/central do RS, coberta pelo aerolevantamento do MIDR "
            "(Consórcio Hidro Sul: SAI Especializados, Aerosat e Fototerra; LiDAR, MDS/MDT; 186 municípios, "
            "R$ 45,9 mi, prazo de 18 meses). O Edital Sema 0069/2025 cobre o Oeste e parte do Litoral Norte "
            "com as mesmas especificações do MIDR. Especificações (densidade, PEC/RMSE, referencial vertical) "
            "e datas de voo estão no termo de referência/relatórios de entrega, não nos arquivos baixados."),
        "fontes_web": [
            "https://www.gov.br/mdr/pt-br/noticias/midr-contrata-mapeamento-aereo-para-apoiar-reconstrucao-no-rio-grande-do-sul",
            "https://www.estado.rs.gov.br/governo-abre-edital-para-mapeamento-topografico-com-tecnologia-de-ponta",
            "https://www.compras.rs.gov.br/editais/0069_2025/338985",
        ],
        "regua_86472600_na_data_do_voo": "não comparada: sem data de voo",
        "outros_arquivos_vizinhos_verificados": [
            "D:/PREVINE/hand/santa tereza (*.tif.xml, *.aux.xml, *.tfw, *.vat.dbf)",
            "D:/PREVINE/FAPERGS (MOSAICO_LIDAR_RS.tif.xml, 25 zips SH-22-*, articulacao_50_latlong, STREAM*.shp.xml)",
            "D:/PREVINE/ENTREGA SIG SANTA TEREZA (relatórios usam Copernicus DEM, não o LiDAR)",
        ],
        "observacoes": [
            "Pirâmides (.ovr) com reamostragem NEAREST (tag Esri PyramidResamplingType); a leitura decimada a 5 m do gerador pode usar essas pirâmides.",
            "O MOSAICO_LIDAR_RS (MosaicToNewRaster) foi reamostrado para uma grade deslocada da grade das folhas; ver deslocamento_grade_clip_vs_folhas_m.",
            "INUND_HAND_2165.tif = CLIP − KRIG_HAND_2165; KRIG_HAND_2165 = krigagem (esférico) do campo HAND de STREAM_TAQUARI_ANTAS_pts_elev = cota do rio + 21,65 m. É a fonte do T_H da planilha.",
        ],
    }
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("planilha", type=Path)
    ap.add_argument("--cel", type=Path, default=None, help="CSV id,E,N das posições do celular (UTM 22S)")
    ap.add_argument("--source-dir", type=Path, default=Path(r"D:\PREVINE\hand\santa tereza"))
    ap.add_argument("--fapergs-dir", type=Path, default=Path(r"D:\PREVINE\FAPERGS"),
                    help="pasta com INUND_HAND_2165.tif (HAND da planilha, LiDAR − krigagem do rio)")
    args = ap.parse_args()

    analise = carregar("analise_erros_campo", ANALISE)
    gen = carregar("gerar_hand_lidar_santa_tereza", GERADOR)
    rtk, linhas = analise.ler_planilha(args.planilha)
    regs, _ = analise.montar_registros(rtk, linhas)
    cel = ler_cel(args.cel)

    # posições únicas por ID-base (V001 e V001b compartilham a posição)
    pos_rtk, pos_cel = {}, {}
    for r in regs:
        base = "V001" if r["id"] == "V001b" else r["id"]
        if "_E" in r:
            pos_rtk[base] = (r["_E"], r["_N"])
        if base in cel:
            pos_cel[base] = cel[base]

    lidar = args.source_dir / "CLIP_MOSAICO_LIDAR_RS.tif"
    z1 = {"rtk": amostrar_1m(lidar, pos_rtk), "cel": amostrar_1m(lidar, pos_cel)}
    inund = args.fapergs_dir / "INUND_HAND_2165.tif"
    hk = {"rtk": {}, "cel": {}}
    if inund.exists():
        hk = {k: {b: v + KRIG_OFFSET_M for b, v in amostrar_1m(inund, pos).items()}
              for k, pos in (("rtk", pos_rtk), ("cel", pos_cel))}

    terrain5, hand, hyd, T, diag = grade_hand(gen, args.source_dir)

    def em5(base, pos):
        if base not in pos:
            return math.nan, math.nan, math.nan, math.nan
        e, n = pos[base]
        z5 = amostrar_grade(terrain5, T, e, n)
        hc = amostrar_grade(hand, T, e, n)
        hb = amostrar_grade(hyd, T, e, n)
        return z5, hc, hb, z5 - hc

    out = []
    for r in regs:
        base = "V001" if r["id"] == "V001b" else r["id"]
        z5r, hcr, hbr, zdr = em5(base, pos_rtk)
        z5c, hcc, hbc, zdc = em5(base, pos_cel)
        hkr = hk["rtk"].get(base, math.nan)
        hkc = hk["cel"].get(base, math.nan)
        th = (PICO_REGUA_M[r["evento"]] - ZERO_REGUA_M) - r["lamina_hand_m"]
        z_cel_pl = r["z_lidar_m"]
        z_rtk = r["z_rtk_m"]
        z1r = z1["rtk"].get(base, math.nan)
        # HAND krigado no celular estimado: mesmo rio krigado, terreno da planilha
        hk_cel_est = z_cel_pl - (z1r - hkr) if not math.isnan(hkr) else math.nan
        hc_cel_est = z_cel_pl - zdr if not math.isnan(zdr) else math.nan
        hb_cel_est = hc_cel_est + (hbr - hcr) if not math.isnan(hbr) else math.nan
        if base in pos_cel:
            corresp = classificar(th, hcc, hbc, hkc)
            base_comp = "celular (amostrado)"
        elif not math.isnan(hc_cel_est):
            corresp = classificar(th, hc_cel_est, hb_cel_est, hk_cel_est)
            base_comp = "celular estimado: z_lidar_cel_planilha − cota de drenagem/krigagem no RTK"
        else:
            corresp, base_comp = "", "sem RTK"
        out.append({
            "id": r["id"], "tipo": r["tipo"], "evento": r["evento"],
            "rtk_valido": r["rtk_valido"],
            "z_lidar1m_cel_m": r3(z1["cel"].get(base, math.nan)),
            "z_lidar_cel_planilha_m": r3(z_cel_pl),
            "z_lidar1m_rtk_m": r3(z1r),
            "z_rtk_m": r3(z_rtk),
            "dz_lidar1m_rtk_m": r3(z1r - z_rtk) if z_rtk is not None and not math.isnan(z1r) else None,
            "z_lidar5m_cel_m": r3(z5c), "z_lidar5m_rtk_m": r3(z5r),
            "hand_conv_cel_m": r3(hcc), "hand_barreira_cel_m": r3(hbc),
            "hand_conv_rtk_m": r3(hcr), "hand_barreira_rtk_m": r3(hbr),
            "z_dren_cel_m": r3(zdc), "z_dren_rtk_m": r3(zdr),
            "z_dren_truncado": bool((not math.isnan(hcr) and hcr == 0) or (not math.isnan(hcc) and hcc == 0)),
            "hand_krig_cel": r3(hkc), "hand_krig_rtk": r3(hkr),
            "z_dren_krig_cel": r3(z1["cel"].get(base, math.nan) - hkc) if not math.isnan(hkc) else None,
            "z_dren_krig_rtk": r3(z1r - hkr) if not math.isnan(hkr) else None,
            "lamina_hand_m": r["lamina_hand_m"],
            "th_planilha_m": r3(th),
            "hand_conv_cel_estimado_m": r3(hc_cel_est),
            "hand_barreira_cel_estimado_m": r3(hb_cel_est),
            "hand_krig_cel_estimado": r3(hk_cel_est),
            "th_planilha_corresponde": corresp,
            "base_comparacao_th": base_comp,
            "nota": r.get("nota", ""),
        })

    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    unicos = [o for o in out if o["id"] != "V001b" and o["dz_lidar1m_rtk_m"] is not None]
    validos = [o for o in unicos if o["rtk_valido"]]
    dz = np.array([o["dz_lidar1m_rtk_m"] for o in validos], dtype=float)

    def dif(col):
        a = np.array([o["th_planilha_m"] - o[col] for o in out if o[col] is not None], dtype=float)
        return {"n": int(a.size), "mediana_m": r3(np.median(a)) if a.size else None,
                "mediana_abs_m": r3(np.median(np.abs(a))) if a.size else None,
                "max_abs_m": r3(np.abs(a).max()) if a.size else None}

    resumo = {
        "registros": len(out),
        "posicoes_rtk_amostradas": len(pos_rtk),
        "posicoes_celular_amostradas": len(pos_cel),
        "dz_lidar1m_menos_rtk_validos": {
            "n": int(dz.size), "mediana_m": r3(np.median(dz)), "mediana_abs_m": r3(np.median(np.abs(dz))),
            "casos_abs_gt_1m": {o["id"]: o["dz_lidar1m_rtk_m"] for o in validos if abs(o["dz_lidar1m_rtk_m"]) > 1.0},
        },
        "dz_lidar1m_menos_rtk_inclui_V001": {o["id"]: o["dz_lidar1m_rtk_m"] for o in unicos if not o["rtk_valido"]},
        "th_planilha_menos": {
            "hand_conv_cel_estimado": dif("hand_conv_cel_estimado_m"),
            "hand_barreira_cel_estimado": dif("hand_barreira_cel_estimado_m"),
            "hand_krig_cel_estimado": dif("hand_krig_cel_estimado"),
        },
        "th_planilha_corresponde": {k: sum(1 for o in out if o["th_planilha_corresponde"] == k)
                                    for k in sorted({o["th_planilha_corresponde"] for o in out})},
        "roteamento": {k: diag[k] for k in ("d8_scheme", "celulas_rio_principal", "drained_fraction")},
    }
    (HERE / "rasters_1m_nas_posicoes_resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    gerar_metadados(lidar, args.fapergs_dir, resumo)
    print(f"metadados: {OUT_META.name}")


if __name__ == "__main__":
    main()
