"""Forçamento de chuva v4 (19/11/2026): TODOS os pluviômetros disponíveis, em todas as janelas.

Diferença para o v3 (que usou uma tabela CEMADEN antiga: 0 postos antes de 2023, 5–9 em 2023–2024, 0 em ago–set/2026):
  ANA     — inventário (130) + as telemétricas da lista oficial que faltavam (ana_faltantes_x77.json; 10 na bacia,
            17 na borda de 10 km);
  CEMADEN — todas as estações na bacia + 10 km, do bruto reprocessado (cemaden_bruto.py: 2015–jul/2026) e, de 20/10/2026
            em diante, do endpoint horário público (últimas 720 h, baixado em 19/11/2026);
  INMET   — arquivo local (até 25/11/2025). 2026 sem INMET até baixar o arquivo anual do portal ou ter token.
Mesma convenção (H = soma de (H−60 min, H] em BRT), mesmo QC iterativo por vizinhos e IDW p = 2 do v3.
CEMADEN em UTC com hora no fim do intervalo: BRT = UTC − 3 h (conferido por defasagem contra a ANA; o diagnóstico de
defasagem de cada janela vai para o comparativo).
Saída: forcamento_v4/<sim>.json + <sim>_postos.json + comparativo_v4.json (postos por fonte, v3 × v4).
Uso: HEC_SEM_CEMADEN=1 HEC_CATALOGO=catalogo_x77.json python forcamento_v4.py [janelas...]
"""
import csv
import gzip
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import numpy as np
from pyproj import Transformer

import chuva_fontes as CF
import forcamento as F1
import forcamento_v2 as V2
import forcamento_v3 as V3
from comum import AQUI, SIMULACOES

FORC4 = AQUI / "forcamento_v4"
CEM_BRUTO = Path(r"D:\PREVINE\dados_chuva_recuperados\cemaden_bruto_horario")
CEM_720 = Path(r"D:\PREVINE\dados_chuva_recuperados\cemaden_horario_20261119")
UTC_PARA_BRT = timedelta(hours=-3)
BUFFER_M = 10000


@lru_cache(maxsize=1)
def cemaden_bruto():
    """{cod: (nome, lat, lon)}, {cod: {hora BRT: mm}} de todo o bruto reprocessado."""
    P, S = {}, {}
    for r in csv.DictReader(open(CEM_BRUTO / "estacoes.csv", encoding="utf-8")):
        cod = "CEM_" + r["codigo"]
        P[cod] = (f"CEMADEN {r['nome'][:30]} ({r['municipio'][:20]})", float(r["lat"]), float(r["lon"]))
        s = {}
        with gzip.open(CEM_BRUTO / f"{r['codigo']}.csv.gz", "rt", encoding="utf-8") as f:
            for x in csv.DictReader(f):
                s[datetime.strptime(x["hora_utc_fim"], "%Y-%m-%d %H:%M") + UTC_PARA_BRT] = float(x["mm"])
        S[cod] = s
    return P, S


@lru_cache(maxsize=1)
def cemaden_720(poly_wkb):
    from shapely import wkb
    from shapely.geometry import Point
    buf = wkb.loads(poly_wkb)
    tr = Transformer.from_crs(4326, 31982, always_xy=True)
    P, S = {}, {}
    for f in sorted(CEM_720.glob("[0-9]*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        e = d["estacao"]
        if not buf.contains(Point(*tr.transform(e["longitude"], e["latitude"]))):
            continue
        cod = "CEM_" + e["codEstacao"]
        s = {}
        for data, vals in zip(d["datas"], d["acumulados"]):
            dia = datetime.strptime(data, "%d/%m/%Y")
            for i, v in enumerate(vals):
                if v is not None:
                    s[dia + timedelta(hours=int(d["horarios"][i].rstrip("h"))) + UTC_PARA_BRT] = float(v)
        P[cod] = (f"CEMADEN {e['nome'][:30]} ({e['idMunicipio']['cidade'][:20]})", e["latitude"], e["longitude"])
        S[cod] = s
    return P, S


def postos(poly):
    P = {c: v for c, v in V3.todos_postos().items() if not c.startswith("CEM_")}   # ANA do inventário + INMET
    for c, v in json.loads((AQUI / "ana_faltantes_x77.json").read_text(encoding="utf-8")).items():
        P.setdefault(c, (f"ANA {v['nome'][:30]}", v["lat"], v["lon"]))
    Pb, Sb = cemaden_bruto()
    P7, S7 = cemaden_720(poly.buffer(BUFFER_M).wkb)
    cem = {}
    for cod in set(Sb) | set(S7):
        cem[cod] = {**Sb.get(cod, {}), **S7.get(cod, {})}
        P[cod] = Pb.get(cod) or P7[cod]
    return P, cem


def fonte_de(c):
    return "CEMADEN" if c.startswith("CEM_") else "INMET" if c.startswith("INMET_") else "ANA"


def main():
    FORC4.mkdir(exist_ok=True)
    so = [a for a in sys.argv[1:] if not a.startswith("-")]
    poly = gpd.read_file(AQUI / "bacia_taquari_antas_31982.geojson").geometry.iloc[0]
    P, cem = postos(poly)
    tr = Transformer.from_crs(4326, 31982, always_xy=True)
    geo = json.loads((AQUI / "geometria_subbacias.json").read_text(encoding="utf-8"))
    px, py = tr.transform([g["lon"] for g in geo], [g["lat"] for g in geo])
    area = np.array([g["area_km2"] for g in geo])
    arq_comp = FORC4 / "comparativo_v4.json"
    comp = json.loads(arq_comp.read_text(encoding="utf-8")) if arq_comp.exists() else {}
    for sim, cfg in SIMULACOES.items():
        if so and sim not in so:
            continue
        horas = F1.grade(cfg["ini"], cfg["fim"])
        hs = set(horas)
        series, ledger = {}, []
        for cod in P:
            f = fonte_de(cod)
            if f == "ANA":
                s, cad, susp = F1.chuva_horaria(cod, sim, horas)
            elif f == "CEMADEN":
                s, cad, susp = {h: v for h, v in cem[cod].items() if h in hs}, 60, []
            else:
                s, cad, susp = CF.serie(cod, horas), 60, []
            if f != "ANA" and not s:
                continue
            ledger.append({"posto": cod, "nome": P[cod][0], "fonte": f, "lat": P[cod][1], "lon": P[cod][2],
                           "cadencia_min": cad, "horas_validas": len(s), "horas_esperadas": len(horas),
                           "total_mm": round(sum(s.values()), 1), "horas_suspeitas": susp})
            if len(s) >= V3.MIN_COBERTURA * len(horas) and sum(s.values()) > 0:
                series[cod] = s
        ana = {c: s for c, s in series.items() if fonte_de(c) == "ANA"}
        lag_cem = Counter()
        for c in [c for c in series if fonte_de(c) == "CEMADEN"]:
            L, r = V2.lag_horario({**ana, c: series[c]}, horas, P, tr, c)
            if r > 0.5:
                lag_cem[L] += 1
        excl, razoes = V2.qc_iterativo(series, horas, P, tr)
        lags = {}
        for c in series:
            L, r = V2.lag_horario(series, horas, P, tr, c)
            if L != 0 and r > 0.6:
                lags[c] = {"lag_h": L, "corr": round(r, 2)}
        for row in ledger:
            row["usado"] = row["posto"] in series
            row["excluido_qc"] = excl.get(row["posto"])
            row["razao_total_vizinhos"] = razoes.get(row["posto"])
            row["lag_suspeito"] = lags.get(row["posto"])
        codes = sorted(series)
        sx, sy = tr.transform([P[c][2] for c in codes], [P[c][1] for c in codes])
        w = 1 / np.maximum(np.hypot(np.array(px)[:, None] - sx, np.array(py)[:, None] - sy), 1.0) ** 2
        chuva, n_disp, vazias = [], [], []
        for h in horas:
            vals = np.array([series[c].get(h, np.nan) for c in codes])
            ok = np.isfinite(vals)
            if not ok.any():
                vazias.append(str(h))
                chuva.append(np.full(len(geo), np.nan))
                n_disp.append(0)
                continue
            chuva.append((w[:, ok] @ vals[ok]) / w[:, ok].sum(axis=1))
            n_disp.append(int(ok.sum()))
        if vazias:
            print(sim, f"SEM CHUVA em {len(vazias)} h: janela descartada", flush=True)
            continue
        chuva = np.asarray(chuva)
        media = chuva @ area / area.sum()
        por_fonte = {f: sum(1 for c in codes if fonte_de(c) == f) for f in ("ANA", "CEMADEN", "INMET")}
        out = {"sim": sim, "horas": [str(h) for h in horas], "convencao": "hora H = soma (H-60min, H]",
               "versao": "v4 (todos os postos: ANA completa, CEMADEN bruto 2015–2026 + 720 h, INMET local até 11/2025)",
               "por_fonte": por_fonte, "postos_usados": codes, "postos_excluidos_qc": excl,
               "razao_total_vizinhos": razoes, "estacoes_disponiveis_por_hora": n_disp,
               "chuva_por_subbacia": {g["sub_id"]: [round(float(v), 4) for v in chuva[:, i]] for i, g in enumerate(geo)},
               "chuva_media_bacia_mm": [round(float(v), 4) for v in media]}
        (FORC4 / f"{sim}.json").write_text(json.dumps(out), encoding="utf-8")
        (FORC4 / f"{sim}_postos.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")
        v3 = {}
        if (V3.FORC3 / f"{sim}.json").exists():
            d3 = json.loads((V3.FORC3 / f"{sim}.json").read_text(encoding="utf-8"))
            a3 = np.array([d3["chuva_por_subbacia"][g["sub_id"]] for g in geo]).T
            v3 = {"postos_usados": len(d3["postos_usados"]),
                  "total_bacia_mm": round(float(a3.sum(axis=0) @ area / area.sum()), 1),
                  "v4_vs_v3_pct_subbacias_p10_p50_p90": [round(float(x), 1) for x in np.percentile(
                      (chuva.sum(axis=0) - a3.sum(axis=0)) / np.maximum(a3.sum(axis=0), 1) * 100, [10, 50, 90])]}
        comp[sim] = {"postos_usados": len(codes), "por_fonte": por_fonte, "excluidos_qc": len(excl),
                     "min_estacoes_por_hora": min(n_disp), "total_bacia_mm": round(float(media.sum()), 1),
                     "defasagem_cemaden_vs_ana": sorted(lag_cem.items()), "v3": v3}
        print(sim, json.dumps(comp[sim], ensure_ascii=False), flush=True)
        arq_comp.write_text(json.dumps(comp, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
