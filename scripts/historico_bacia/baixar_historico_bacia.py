#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROBO — Historico de forcantes da bacia Taquari-Antas (pesquisa "vai inundar ou nao").

Baixa, de forma INCREMENTAL e RETOMAVEL, tres familias de dados que hoje faltam
no repositorio para o estudo comparativo dos eventos e para montar casos
negativos (chuva forte que NAO virou cheia):

  1. ana-diario     ANA HidroSerieHistorica (series convencionais, diarias)
                    - chuva diaria dos postos pluviometricos ANA da bacia
                      (assets/data/estudo_bacia_taquari_antas/pluviometria_g040.geojson)
                    - cota diaria (e vazao, quando houver) das estacoes
                      fluviometricas-chave com serie longa (Muçum, Encantado,
                      Estrela, Passo Tainhas, Passo Carreiro, Santa Tereza...)
  2. ana-telemetria ANA DadosHidrometeorologicos (telemetria, 15 min -> horario)
                    - chuva, nivel e vazao horarios das estacoes-chave, de 2014
                      em diante (ou o que a ANA tiver retido)
  3. era5land       ERA5-Land via Open-Meteo Archive (sem credencial)
                    - chuva diaria e umidade do solo (0-7, 7-28, 28-100 cm,
                      media diaria) no centroide de cada uma das 32 sub-bacias
                      (assets/data/hec_hms_g040_full_basin/full_basin_subbasins.geojson)

Regras (iguais ao resto do PREVINE):
  - Ausencia e ausencia: nada e interpolado, lacuna nunca vira zero.
  - Nada e sobrescrito com vazio: cada rodada so ACRESCENTA observacoes.
  - Cada arquivo guarda a fonte e o nivel de consistencia (ANA: 1=bruto,
    2=consistido; quando ha os dois para o mesmo dia, fica o consistido).
  - Pesquisa apenas; nao e dado oficial e nao gera alerta.

Saida (gz para caber no Git):
  assets/data/historico_bacia/
    ana_diario/chuva/<codigo>.csv.gz      data,chuva_mm,consistencia
    ana_diario/cota/<codigo>.csv.gz       data,cota_cm,consistencia
    ana_diario/vazao/<codigo>.csv.gz      data,vazao_m3s,consistencia
    ana_telemetria/<codigo>.csv.gz        hora_local,chuva_mm,nivel_cm,vazao_m3s,n_leituras
    era5land/<sub_bacia>.csv.gz           data,chuva_mm,umid_0_7,umid_7_28,umid_28_100
    manifesto_latest.json                 cobertura por serie, erros, versao

Uso (no GitHub Actions; a sessao do Claude nao alcanca essas APIs):
  python -B scripts/historico_bacia/baixar_historico_bacia.py --fonte todas --orcamento-min 300
  python -B scripts/historico_bacia/baixar_historico_bacia.py --fonte era5land --inicio 1990-01-01
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import io
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "assets/data/historico_bacia"
MANIFESTO = SAIDA / "manifesto_latest.json"
PLUVIO_GEOJSON = RAIZ / "assets/data/estudo_bacia_taquari_antas/pluviometria_g040.geojson"
SUBBACIAS_GEOJSON = RAIZ / "assets/data/hec_hms_g040_full_basin/full_basin_subbasins.geojson"

ANA_BASES = (
    "https://telemetriaws1.ana.gov.br/ServiceANA.asmx",
    "https://www.ana.gov.br/telemetria1ws/ServiceANA.asmx",
)
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
UA = {"User-Agent": "PREVINE-historico-bacia/1.0 (pesquisa IPH/UFRGS)",
      "Accept": "text/xml,application/xml,application/json,*/*;q=0.8"}

# Estacoes fluviometricas-chave (serie convencional diaria de cota/vazao).
# Codigos conferidos em assets/data/estudo_bacia_taquari_antas/postos_g040.geojson.
FLUVIO_CHAVE = {
    "86472600": "Santa Tereza",
    "86472000": "Linha José Júlio",
    "86510000": "Muçum",
    "86720000": "Encantado",
    "86879300": "Estrela",
    "86160000": "Passo Tainhas",
    "86100000": "Passo do Gabriel",
    "86500000": "Passo Carreiro",
    "86440000": "Passo do Prata",
    "86470000": "Ponte do Rio das Antas",
    "86300000": "Nova Roma",
    "86580000": "Santa Lúcia (Guaporé)",
    "86560000": "Linha Colombo (Guaporé)",
    "86780000": "Barra do Fão (Forqueta)",
    "86895000": "Porto Mariante",
}

# Estacoes telemetricas-chave (chuva/nivel horarios). Cobrem cabeceiras do
# Antas, Tainhas, Prata, Carreiro e o trecho Santa Tereza-Muçum.
TELEMETRIA_CHAVE = {
    "86472600": "Santa Tereza",
    "86472000": "Linha José Júlio",
    "86510000": "Muçum",
    "86095100": "Bom Jesus/Jaquirana",
    "86100600": "PCH Pezzi Arroio Pinheiro Alto",
    "86160000": "Passo Tainhas",
    "86120050": "São Francisco de Paula-Cambará do Sul",
    "86125130": "PCH Morro Grande Jusante 2",
    "86297995": "Flores da Cunha-Antônio Prado",
    "86298000": "UHE Castro Alves RS-122",
    "86329001": "Nova Roma/Farroupilha",
    "86342000": "Muitos Capões/Lagoa Vermelha",
    "86410001": "Protásio Alves/Ipê",
    "86447000": "UHE Monte Claro Balsa do Prata",
    "86471000": "UHE 14 de Julho Jusante",
    "86479000": "PCH Caçador Ponte São Domingos",
    "86500000": "Passo Carreiro",
    "86507000": "PCH Cotiporã Jusante",
    "86507220": "Cotiporã/Dois Lajeados",
    "86640900": "Putinga",
}

TIPO_ANA = {"cota": 1, "chuva": 2, "vazao": 3}
PREFIXO_ANA = {"cota": "Cota", "chuva": "Chuva", "vazao": "Vazao"}
COLUNA_ANA = {"cota": "cota_cm", "chuva": "chuva_mm", "vazao": "vazao_m3s"}


# --------------------------------------------------------------- utilidades
class Orcamento:
    """Para o robo com folga antes do limite do job do Actions."""

    def __init__(self, minutos: float):
        self.fim = time.monotonic() + minutos * 60

    def esgotado(self) -> bool:
        return time.monotonic() >= self.fim


def numero(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", ".")
    if s == "":
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def http_get(url: str, timeout: int = 90, tentativas: int = 4) -> bytes:
    ultimo = None
    for k in range(1, tentativas + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                dados = resp.read()
            if dados[:2] == b"\x1f\x8b":
                dados = gzip.decompress(dados)
            return dados
        except urllib.error.HTTPError as e:
            ultimo = e
            # 429/503: a ANA e o Open-Meteo limitam taxa; espera progressiva.
            espera = 20 * k if e.code in (429, 503) else 4 * k
            time.sleep(espera)
        except Exception as e:  # rede, timeout, XML truncado
            ultimo = e
            time.sleep(4 * k)
    raise ultimo


def raizes_xml(raw: bytes):
    """A ANA as vezes devolve o XML de dados como texto dentro do envelope."""
    root = ET.fromstring(raw)
    raizes = [root]
    txt = (root.text or "").strip()
    if txt.startswith("<"):
        try:
            raizes.append(ET.fromstring(txt))
        except ET.ParseError:
            pass
    return raizes


def ler_csv_gz(caminho: Path, chave: str) -> dict:
    if not caminho.exists():
        return {}
    with gzip.open(caminho, "rt", encoding="utf-8", newline="") as f:
        return {linha[chave]: linha for linha in csv.DictReader(f)}


def gravar_csv_gz(caminho: Path, colunas: list, linhas: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=colunas, lineterminator="\n")
    w.writeheader()
    for k in sorted(linhas):
        w.writerow({c: linhas[k].get(c, "") for c in colunas})
    # mtime=0 -> gzip deterministico (sem diff no Git quando nada mudou)
    with open(tmp, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        gz.write(buf.getvalue().encode("utf-8"))
    os.replace(tmp, caminho)


def carregar_manifesto() -> dict:
    if MANIFESTO.exists():
        try:
            return json.loads(MANIFESTO.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"schema_version": 1, "series": {}}


def resumo_serie(linhas: dict, coluna: str) -> dict:
    validos = [k for k, v in linhas.items() if v.get(coluna) not in (None, "")]
    if not validos:
        return {"n_validos": 0}
    return {"n_validos": len(validos), "primeiro": min(validos), "ultimo": max(validos)}


# ------------------------------------------------------ 1. ANA diario (HidroWeb)
def parse_serie_historica(raw: bytes, tipo: str) -> dict:
    """Converte HidroSerieHistorica em {AAAA-MM-DD: (valor, consistencia)}.

    Cada registro e um MES (DataHora = 1o dia do mes) com colunas
    <Prefixo>01..<Prefixo>31. Todos os dias do mes sao lidos (o bug antigo de
    ler so o primeiro valor deixava apenas janeiro). Quando existem registro
    bruto (1) e consistido (2) para o mesmo dia, prevalece o consistido.
    """
    prefixo = PREFIXO_ANA[tipo]
    saida: dict = {}
    for rt in raizes_xml(raw):
        for no in rt.iter():
            campos = {local(ch.tag): (ch.text or "").strip() for ch in no}
            if "DataHora" not in campos or not any(k.startswith(prefixo) for k in campos):
                continue
            try:
                mes = dt.datetime.strptime(campos["DataHora"][:10], "%Y-%m-%d").date()
            except ValueError:
                try:
                    mes = dt.datetime.strptime(campos["DataHora"][:10], "%d/%m/%Y").date()
                except ValueError:
                    continue
            consist = int(numero(campos.get("NivelConsistencia")) or 1)
            for dia in range(1, 32):
                v = numero(campos.get(f"{prefixo}{dia:02d}"))
                if v is None:
                    continue
                try:
                    data = mes.replace(day=dia)
                except ValueError:  # 30/02 etc.
                    continue
                chave = data.isoformat()
                antigo = saida.get(chave)
                if antigo is None or consist > antigo[1]:
                    saida[chave] = (v, consist)
    return saida


def baixar_ana_diario(cod: str, tipo: str, inicio: dt.date, fim: dt.date) -> dict:
    params = urllib.parse.urlencode({
        "codEstacao": cod,
        "dataInicio": inicio.strftime("%d/%m/%Y"),
        "dataFim": fim.strftime("%d/%m/%Y"),
        "tipoDados": TIPO_ANA[tipo],
        "nivelConsistencia": "",
    })
    erros = []
    for base in ANA_BASES:
        try:
            raw = http_get(f"{base}/HidroSerieHistorica?{params}", timeout=150)
            return parse_serie_historica(raw, tipo)
        except Exception as e:
            erros.append(f"{base}: {e}")
    raise RuntimeError(" | ".join(erros))


def codigos_pluviometricos_ana() -> list:
    gj = json.loads(PLUVIO_GEOJSON.read_text(encoding="utf-8"))
    cods = []
    for f in gj["features"]:
        p = f["properties"]
        if p.get("rede") == "ANA" and p.get("codigo"):
            cods.append((str(p["codigo"]).zfill(7), p.get("nome") or ""))
    return sorted(set(cods))


def rodar_ana_diario(inicio, fim, orc, manifesto):
    tarefas = [(c, n, "chuva") for c, n in codigos_pluviometricos_ana()]
    for c, n in FLUVIO_CHAVE.items():
        tarefas += [(c, n, "cota"), (c, n, "vazao")]
    for cod, nome, tipo in tarefas:
        if orc.esgotado():
            print("[ana-diario] orcamento de tempo esgotado; continua na proxima rodada")
            return
        chave_m = f"ana_diario/{tipo}/{cod}"
        reg = manifesto["series"].get(chave_m, {})
        # Retomavel: ja consultada ate 'consultado_ate' -> pede so o resto
        # (com 400 dias de sobreposicao, para captar dados consistidos depois).
        ini = inicio
        if reg.get("consultado_ate"):
            ini = max(inicio, dt.date.fromisoformat(reg["consultado_ate"]) - dt.timedelta(days=400))
        caminho = SAIDA / "ana_diario" / tipo / f"{cod}.csv.gz"
        coluna = COLUNA_ANA[tipo]
        try:
            novos = baixar_ana_diario(cod, tipo, ini, fim)
        except Exception as e:
            reg.update({"nome": nome, "erro": str(e)[:300], "ultima_tentativa": hoje_iso()})
            manifesto["series"][chave_m] = reg
            print(f"[ana-diario] {tipo} {cod} ERRO {e}")
            continue
        linhas = ler_csv_gz(caminho, "data")
        for data, (v, consist) in novos.items():
            antigo = linhas.get(data)
            if antigo and int(antigo.get("consistencia") or 1) > consist:
                continue
            linhas[data] = {"data": data, coluna: f"{v:g}", "consistencia": consist}
        if linhas:
            gravar_csv_gz(caminho, ["data", coluna, "consistencia"], linhas)
        reg.update({"nome": nome, "fonte": "ANA HidroSerieHistorica", "consultado_ate": fim.isoformat(),
                    "ultima_tentativa": hoje_iso(), "erro": None, **resumo_serie(linhas, coluna)})
        manifesto["series"][chave_m] = reg
        print(f"[ana-diario] {tipo} {cod} {nome}: +{len(novos)} dias (total {len(linhas)})")
        time.sleep(1.0)


# --------------------------------------------- 2. ANA telemetria (horario)
def parse_telemetria(raw: bytes) -> dict:
    """{(AAAA-MM-DD HH:MM local): {chuva, nivel, vazao, n}} a partir de leituras
    de 15 min. Chuva: soma das leituras distintas dentro da hora (rotulo = hora
    de inicio, mesma convencao de chuvas_horarias.csv). Nivel/vazao: media.
    Leituras repetidas (mesmo DataHora) sao contadas uma unica vez."""
    vistos = {}
    for rt in raizes_xml(raw):
        for no in rt.iter():
            campos = {local(ch.tag): (ch.text or "").strip() for ch in no}
            dh = campos.get("DataHora") or campos.get("Data_Hora")
            if not dh:
                continue
            s = dh.replace("T", " ").strip()
            t = None
            for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%d/%m/%Y %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16)):
                try:
                    t = dt.datetime.strptime(s[:n], fmt)
                    break
                except ValueError:
                    continue
            if t is None:
                continue
            vistos[t] = (numero(campos.get("Chuva")), numero(campos.get("Nivel")),
                         numero(campos.get("Vazao")))
    horas: dict = {}
    for t, (ch, nv, vz) in vistos.items():
        h = t.replace(minute=0, second=0).strftime("%Y-%m-%d %H:00")
        b = horas.setdefault(h, {"chuva": [], "nivel": [], "vazao": []})
        if ch is not None and 0 <= ch <= 200:
            b["chuva"].append(ch)
        if nv is not None:
            b["nivel"].append(nv)
        if vz is not None and 0 <= vz <= 60000:
            b["vazao"].append(vz)
    out = {}
    for h, b in horas.items():
        out[h] = {
            "chuva_mm": round(sum(b["chuva"]), 2) if b["chuva"] else None,
            "nivel_cm": round(sum(b["nivel"]) / len(b["nivel"]), 1) if b["nivel"] else None,
            "vazao_m3s": round(sum(b["vazao"]) / len(b["vazao"]), 3) if b["vazao"] else None,
            "n_leituras": max(len(b["chuva"]), len(b["nivel"]), len(b["vazao"])),
        }
    return out


def meses(inicio: dt.date, fim: dt.date):
    m = inicio.replace(day=1)
    while m <= fim:
        prox = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield m, min(prox - dt.timedelta(days=1), fim)
        m = prox


def rodar_ana_telemetria(inicio, fim, orc, manifesto):
    colunas = ["hora_local", "chuva_mm", "nivel_cm", "vazao_m3s", "n_leituras"]
    for cod, nome in TELEMETRIA_CHAVE.items():
        chave_m = f"ana_telemetria/{cod}"
        reg = manifesto["series"].get(chave_m, {"meses_consultados": []})
        feitos = set(reg.get("meses_consultados", []))
        caminho = SAIDA / "ana_telemetria" / f"{cod}.csv.gz"
        linhas = ler_csv_gz(caminho, "hora_local")
        mudou = False
        mes_atual = fim.strftime("%Y-%m")
        for ini_m, fim_m in meses(inicio, fim):
            rotulo = ini_m.strftime("%Y-%m")
            # Meses fechados ja consultados nao sao refeitos; os 2 ultimos sim.
            if rotulo in feitos and rotulo < (fim - dt.timedelta(days=45)).strftime("%Y-%m"):
                continue
            if orc.esgotado():
                break
            params = urllib.parse.urlencode({"codEstacao": cod, "dataInicio": ini_m.strftime("%d/%m/%Y"),
                                             "dataFim": fim_m.strftime("%d/%m/%Y")})
            novos = None
            for base in ANA_BASES:
                try:
                    novos = parse_telemetria(http_get(f"{base}/DadosHidrometeorologicos?{params}", timeout=60))
                    break
                except Exception as e:
                    print(f"[telemetria] {cod} {rotulo} {base}: {e}")
            if novos is None:
                continue  # mes nao marcado como feito -> tenta de novo depois
            for h, v in novos.items():
                antigo = linhas.get(h, {})
                linha = {"hora_local": h}
                for c in colunas[1:]:
                    nv = v.get(c)
                    linha[c] = nv if nv is not None else antigo.get(c, "")
                linhas[h] = linha
            if rotulo != mes_atual:
                feitos.add(rotulo)
            mudou = mudou or bool(novos)
            print(f"[telemetria] {cod} {nome} {rotulo}: {len(novos)} horas")
            time.sleep(0.8)
        if mudou:
            gravar_csv_gz(caminho, colunas, linhas)
        reg.update({"nome": nome, "fonte": "ANA DadosHidrometeorologicos (telemetria)",
                    "meses_consultados": sorted(feitos), "ultima_tentativa": hoje_iso(),
                    "chuva": resumo_serie(linhas, "chuva_mm"), "nivel": resumo_serie(linhas, "nivel_cm")})
        manifesto["series"][chave_m] = reg
        if orc.esgotado():
            print("[telemetria] orcamento de tempo esgotado; continua na proxima rodada")
            return


# ------------------------------------------------- 3. ERA5-Land (Open-Meteo)
def centroides_subbacias() -> list:
    """Centroide de area (formula do poligono) do anel externo de cada sub-bacia.
    Sem dependencias externas; para MultiPolygon usa o maior poligono."""
    gj = json.loads(SUBBACIAS_GEOJSON.read_text(encoding="utf-8"))
    out = []
    for f in gj["features"]:
        g = f["geometry"]
        aneis = [g["coordinates"][0]] if g["type"] == "Polygon" else [p[0] for p in g["coordinates"]]
        melhor = None
        for anel in aneis:
            a = cx = cy = 0.0
            for (x0, y0), (x1, y1) in zip(anel, anel[1:] + anel[:1]):
                cr = x0 * y1 - x1 * y0
                a += cr
                cx += (x0 + x1) * cr
                cy += (y0 + y1) * cr
            if a == 0:
                continue
            c = (abs(a) / 2, cx / (3 * a), cy / (3 * a))
            if melhor is None or c[0] > melhor[0]:
                melhor = c
        if melhor:
            p = f["properties"]
            out.append({"id": p["id"], "nome": p.get("name"), "area_km2": p.get("area_km2"),
                        "lon": round(melhor[1], 4), "lat": round(melhor[2], 4)})
    return out


def parse_open_meteo(raw: bytes) -> dict:
    j = json.loads(raw)
    diario = {}
    d = j.get("daily", {})
    for t, p in zip(d.get("time", []), d.get("precipitation_sum", [])):
        diario.setdefault(t, {})["chuva_mm"] = p
    h = j.get("hourly", {})
    acum = {}
    for i, t in enumerate(h.get("time", [])):
        dia = t[:10]
        for var, col in (("soil_moisture_0_to_7cm", "umid_0_7"), ("soil_moisture_7_to_28cm", "umid_7_28"),
                         ("soil_moisture_28_to_100cm", "umid_28_100")):
            v = (h.get(var) or [None] * (i + 1))[i]
            if v is not None:
                acum.setdefault((dia, col), []).append(v)
    for (dia, col), vals in acum.items():
        # Media diaria so com o dia completo (24 h) — dia parcial fica vazio.
        if len(vals) == 24:
            diario.setdefault(dia, {})[col] = round(sum(vals) / 24, 4)
    return diario


def rodar_era5land(inicio, fim, orc, manifesto):
    colunas = ["data", "chuva_mm", "umid_0_7", "umid_7_28", "umid_28_100"]
    # ERA5-Land tem ~5 dias de atraso; nao pede o que ainda nao existe.
    fim = min(fim, dt.date.today() - dt.timedelta(days=7))
    for sb in centroides_subbacias():
        chave_m = f"era5land/{sb['id']}"
        reg = manifesto["series"].get(chave_m, {"anos_consultados": []})
        feitos = set(reg.get("anos_consultados", []))
        caminho = SAIDA / "era5land" / f"{sb['id']}.csv.gz"
        linhas = ler_csv_gz(caminho, "data")
        mudou = False
        for ano in range(inicio.year, fim.year + 1):
            if str(ano) in feitos and ano < fim.year:
                continue
            if orc.esgotado():
                break
            a0 = max(inicio, dt.date(ano, 1, 1))
            a1 = min(fim, dt.date(ano, 12, 31))
            params = urllib.parse.urlencode({
                "latitude": sb["lat"], "longitude": sb["lon"],
                "start_date": a0.isoformat(), "end_date": a1.isoformat(),
                "daily": "precipitation_sum",
                "hourly": "soil_moisture_0_to_7cm,soil_moisture_7_to_28cm,soil_moisture_28_to_100cm",
                "models": "era5_land", "timezone": "America/Sao_Paulo",
            })
            try:
                novos = parse_open_meteo(http_get(f"{OPEN_METEO_ARCHIVE}?{params}", timeout=120))
            except Exception as e:
                print(f"[era5land] {sb['id']} {ano}: {e}")
                time.sleep(10)
                continue
            for dia, v in novos.items():
                linha = linhas.get(dia, {"data": dia})
                for c in colunas[1:]:
                    if v.get(c) is not None:
                        linha[c] = v[c]
                linhas[dia] = linha
            if ano < fim.year:
                feitos.add(str(ano))
            mudou = True
            print(f"[era5land] {sb['id']} {ano}: {len(novos)} dias")
            time.sleep(1.5)  # respeita o limite gratuito do Open-Meteo
        if mudou:
            gravar_csv_gz(caminho, colunas, linhas)
        reg.update({"nome": sb["nome"], "lat": sb["lat"], "lon": sb["lon"], "area_km2": sb["area_km2"],
                    "fonte": "ERA5-Land via Open-Meteo Archive (centroide da sub-bacia)",
                    "anos_consultados": sorted(feitos), "ultima_tentativa": hoje_iso(),
                    **resumo_serie(linhas, "chuva_mm")})
        manifesto["series"][chave_m] = reg
        if orc.esgotado():
            print("[era5land] orcamento de tempo esgotado; continua na proxima rodada")
            return


# ------------------------------------------------------------------- main
def hoje_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fonte", choices=["todas", "ana-diario", "ana-telemetria", "era5land"], default="todas")
    ap.add_argument("--inicio", default=None, help="AAAA-MM-DD (padrao por fonte: 1980 / 2014 / 1990)")
    ap.add_argument("--fim", default=None, help="AAAA-MM-DD (padrao: hoje)")
    ap.add_argument("--orcamento-min", type=float, default=300.0,
                    help="minutos de trabalho antes de parar e salvar (o job do Actions vai ate 360)")
    a = ap.parse_args(argv)

    fim = dt.date.fromisoformat(a.fim) if a.fim else dt.date.today()
    orc = Orcamento(a.orcamento_min)
    manifesto = carregar_manifesto()
    SAIDA.mkdir(parents=True, exist_ok=True)

    padrao = {"ana-diario": "1980-01-01", "ana-telemetria": "2014-01-01", "era5land": "1990-01-01"}
    fontes = ["era5land", "ana-diario", "ana-telemetria"] if a.fonte == "todas" else [a.fonte]
    for fonte in fontes:
        inicio = dt.date.fromisoformat(a.inicio or padrao[fonte])
        print(f"== {fonte}: {inicio} -> {fim}")
        try:
            {"ana-diario": rodar_ana_diario, "ana-telemetria": rodar_ana_telemetria,
             "era5land": rodar_era5land}[fonte](inicio, fim, orc, manifesto)
        finally:
            manifesto.update({"schema_version": 1, "research_only": True, "official_alert": False,
                              "gerado_em_utc": hoje_iso(),
                              "regras": "ausencia nunca vira zero; nada interpolado; consistido > bruto",
                              "script": "scripts/historico_bacia/baixar_historico_bacia.py"})
            MANIFESTO.write_text(json.dumps(manifesto, ensure_ascii=False, indent=1, sort_keys=True),
                                 encoding="utf-8")
        if orc.esgotado():
            break
    n = len(manifesto["series"])
    erros = sum(1 for v in manifesto["series"].values() if v.get("erro"))
    print(f"manifesto: {n} series, {erros} com erro na ultima tentativa")
    return 0


if __name__ == "__main__":
    sys.exit(main())
