#!/usr/bin/env python3
"""Testes offline (sem rede) do robo de historico da bacia.

Roda com:  python -B scripts/historico_bacia/test_baixar_historico_bacia.py
"""
import datetime as dt
import gzip
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import baixar_historico_bacia as R  # noqa: E402

SERIE_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<DataTable><DocumentElement>
 <SerieHistorica><EstacaoCodigo>2851044</EstacaoCodigo><NivelConsistencia>1</NivelConsistencia>
  <DataHora>2023-09-01 00:00:00</DataHora><Chuva01>10,5</Chuva01><Chuva02>0</Chuva02>
  <Chuva03></Chuva03><Chuva04>120.2</Chuva04><Chuva30>1</Chuva30><Chuva31>2</Chuva31></SerieHistorica>
 <SerieHistorica><EstacaoCodigo>2851044</EstacaoCodigo><NivelConsistencia>2</NivelConsistencia>
  <DataHora>2023-09-01 00:00:00</DataHora><Chuva01>11.0</Chuva01></SerieHistorica>
 <SerieHistorica><EstacaoCodigo>2851044</EstacaoCodigo><NivelConsistencia>1</NivelConsistencia>
  <DataHora>2024-02-01 00:00:00</DataHora><Chuva29>5</Chuva29><Chuva30>9</Chuva30></SerieHistorica>
</DocumentElement></DataTable>"""

TELE_XML = b"""<DataTable><DocumentElement>
 <DadosHidrometereologicos><DataHora>2024-05-01 10:00:00</DataHora><Chuva>2.0</Chuva><Nivel>800</Nivel></DadosHidrometereologicos>
 <DadosHidrometereologicos><DataHora>2024-05-01 10:15:00</DataHora><Chuva>3.0</Chuva><Nivel>810</Nivel></DadosHidrometereologicos>
 <DadosHidrometereologicos><DataHora>2024-05-01 10:15:00</DataHora><Chuva>3.0</Chuva><Nivel>810</Nivel></DadosHidrometereologicos>
 <DadosHidrometereologicos><DataHora>2024-05-01 11:00:00</DataHora><Chuva></Chuva><Nivel>830</Nivel></DadosHidrometereologicos>
</DocumentElement></DataTable>"""


def test_serie_historica():
    d = R.parse_serie_historica(SERIE_XML, "chuva")
    assert d["2023-09-01"] == (11.0, 2), d["2023-09-01"]       # consistido vence
    assert d["2023-09-02"] == (0.0, 1)                         # zero real preservado
    assert "2023-09-03" not in d                               # vazio nunca vira zero
    assert d["2023-09-04"] == (120.2, 1)
    assert d["2023-09-30"] == (1.0, 1)
    assert "2023-09-31" not in d and "2023-10-01" not in d     # dia inexistente ignorado
    assert d["2024-02-29"] == (5.0, 1)                         # bissexto
    assert "2024-02-30" not in d
    assert len([k for k in d if k.startswith("2023-09")]) == 4  # todos os dias do mes (01,02,04,30), nao so o 1o


def test_telemetria():
    h = R.parse_telemetria(TELE_XML)
    assert h["2024-05-01 10:00"]["chuva_mm"] == 5.0            # duplicata contada uma vez
    assert h["2024-05-01 10:00"]["nivel_cm"] == 805.0
    assert h["2024-05-01 11:00"]["chuva_mm"] is None           # chuva ausente != 0
    assert h["2024-05-01 11:00"]["nivel_cm"] == 830.0


def test_open_meteo():
    horas = [f"2024-05-01T{i:02d}:00" for i in range(24)] + ["2024-05-02T00:00"]
    j = {"daily": {"time": ["2024-05-01", "2024-05-02"], "precipitation_sum": [210.4, None]},
         "hourly": {"time": horas, "soil_moisture_0_to_7cm": [0.40] * 25,
                    "soil_moisture_7_to_28cm": [0.42] * 25, "soil_moisture_28_to_100cm": [None] * 25}}
    d = R.parse_open_meteo(json.dumps(j).encode())
    assert d["2024-05-01"]["chuva_mm"] == 210.4
    assert d["2024-05-01"]["umid_0_7"] == 0.4
    assert "umid_28_100" not in d["2024-05-01"]                # sem dado -> sem valor
    assert "umid_0_7" not in d.get("2024-05-02", {})           # dia incompleto nao vira media


def test_centroides():
    c = R.centroides_subbacias()
    assert len(c) == 32, len(c)
    for sb in c:   # todos dentro da caixa da bacia Taquari-Antas
        assert -30.4 < sb["lat"] < -27.7 and -53.3 < sb["lon"] < -49.4, sb


def test_csv_gz_deterministico():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.csv.gz"
        linhas = {"2024-01-02": {"data": "2024-01-02", "v": 1}, "2024-01-01": {"data": "2024-01-01", "v": 0}}
        R.gravar_csv_gz(p, ["data", "v"], linhas)
        b1 = p.read_bytes()
        R.gravar_csv_gz(p, ["data", "v"], linhas)
        assert b1 == p.read_bytes()                            # sem diff espurio no Git
        txt = gzip.decompress(b1).decode()
        assert txt.splitlines()[1].startswith("2024-01-01")    # ordenado
        assert R.ler_csv_gz(p, "data")["2024-01-02"]["v"] == "1"


def test_pluviometros():
    cods = R.codigos_pluviometricos_ana()
    assert len(cods) >= 100 and all(len(c) in (7, 8) for c, _ in cods)


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
