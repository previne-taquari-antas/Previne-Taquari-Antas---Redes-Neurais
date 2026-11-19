"""Reprocessa o CEMADEN bruto (D:\\PREVINE\\estacoes_cemaden.zip, CSV mensais do RS, 2015–jul/2026) em chuva horária de
TODAS as estações da bacia Taquari-Antas e da borda de 10 km (19/11/2026).

Motivo: o forcamento_v3 usou uma tabela processada antiga (dez/2022 em diante, 5–9 postos por janela em 2023–2024 e
nenhum antes de 2023), e essa pasta sumiu. O zip tem 2015–2026.
Saída: D:\\PREVINE\\dados_chuva_recuperados\\cemaden_bruto_horario\\
  estacoes.csv           código, nome, município, lat, lon, primeiro/último registro, nº de registros
  <codEstacao>.csv.gz    hora_utc_fim, mm, n_registros  (hora = soma dos registros em (H−60 min, H], UTC)
Sem conversão de fuso aqui: o deslocamento para BRT é conferido depois, por defasagem contra a ANA.
Registros repetidos (arquivos "- 1"/"-1" duplicados) contam uma vez (por estação + datahora).
"""
import csv
import gzip
import io
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import Point

AQUI = Path(__file__).resolve().parent
ZIP = Path(r"D:\PREVINE\estacoes_cemaden.zip")
OUT = Path(r"D:\PREVINE\dados_chuva_recuperados\cemaden_bruto_horario")
BUFFER_M = 10000


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    poly = gpd.read_file(AQUI / "bacia_taquari_antas_31982.geojson").geometry.iloc[0].buffer(BUFFER_M)
    tr = Transformer.from_crs(4326, 31982, always_xy=True)
    zf = zipfile.ZipFile(ZIP)
    arqs = sorted(n for n in zf.namelist() if n.lower().endswith(".csv") and "/20" in n)
    print(len(arqs), "CSV mensais", flush=True)
    dentro, fora = {}, set()
    vistos = defaultdict(set)              # cod -> {datahora} (dedup dentro do mês: as cópias "- 1" ficam lado a lado)
    horas = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
    meta, resumo, mes_atual = {}, {}, None
    for f in OUT.glob("*.csv.gz"):
        f.unlink()

    def descarregar():
        for cod, hh in horas.items():
            novo = not (OUT / f"{cod}.csv.gz").exists()
            with gzip.open(OUT / f"{cod}.csv.gz", "at", encoding="utf-8", newline="") as g:
                gw = csv.writer(g)
                if novo:
                    gw.writerow(["hora_utc_fim", "mm", "n_registros"])
                for h in sorted(hh):
                    gw.writerow([h.strftime("%Y-%m-%d %H:%M"), round(hh[h][0], 2), hh[h][1]])
            hs = sorted(hh)
            r = resumo.setdefault(cod, [hs[0], hs[-1], 0])
            r[0], r[1], r[2] = min(r[0], hs[0]), max(r[1], hs[-1]), r[2] + len(hs)
        horas.clear()
        vistos.clear()

    for k, nome in enumerate(arqs):
        mes = nome.rsplit("/", 1)[-1][:7]
        if mes != mes_atual:
            descarregar()
            mes_atual = mes
        with zf.open(nome) as f:
            txt = io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace")
            for r in csv.reader(txt, delimiter=";"):
                if len(r) < 8 or r[1] == "codEstacao":
                    continue
                cod = r[1].strip()
                if cod in fora:
                    continue
                if cod not in dentro:
                    try:
                        lat, lon = float(r[4].replace(",", ".")), float(r[5].replace(",", "."))
                    except ValueError:
                        continue
                    ok = poly.contains(Point(*tr.transform(lon, lat)))
                    if not ok:
                        fora.add(cod)
                        continue
                    dentro[cod] = True
                    meta[cod] = {"codigo": cod, "nome": r[3], "municipio": r[0], "lat": lat, "lon": lon}
                dh = r[6].strip()
                if dh in vistos[cod]:
                    continue
                vistos[cod].add(dh)
                try:
                    t = datetime.fromisoformat(dh[:19])
                    v = float(r[7].replace(",", "."))
                except ValueError:
                    continue
                if v < 0:
                    continue
                h = t.replace(minute=0, second=0) + (timedelta(hours=1) if (t.minute or t.second) else timedelta(0))
                c = horas[cod][h]
                c[0] += v
                c[1] += 1
        if k % 10 == 0:
            print(f"{k + 1}/{len(arqs)} {nome} | estações na bacia+borda: {len(dentro)}", flush=True)
    descarregar()
    with open(OUT / "estacoes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["codigo", "nome", "municipio", "lat", "lon", "primeira_hora_utc", "ultima_hora_utc", "horas"])
        w.writeheader()
        for cod in sorted(resumo):
            a, b, n = resumo[cod]
            w.writerow({**meta[cod], "primeira_hora_utc": a, "ultima_hora_utc": b, "horas": n})
    print("pronto:", len(resumo), "estações", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
