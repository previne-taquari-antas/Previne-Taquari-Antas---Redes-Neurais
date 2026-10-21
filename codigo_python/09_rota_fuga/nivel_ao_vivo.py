#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nível do rio para as rotas de fuga ao vivo (Santa Tereza e Muçum).

Lido pelos dois geradores (gerar_rota_fuga_santa_tereza.py e
gerar_rota_fuga_ruas.py). Só biblioteca padrão, para testar sem LiDAR.

Regras:
  - hora sem fuso no JSON da previsão é hora de Brasília (os robôs gravam a
    hora da telemetria da ANA). O runner do GitHub roda em UTC: sem isso a
    idade do dado sai 180 min maior;
  - nível atual = leitura da régua COM a hora da leitura; sem uma delas devolve
    None, nunca 0 (quem chama não publica). O `nivel_atual_cm` da previsão não
    serve: quando a telemetria é rejeitada ele cai para o nível de base do
    modelo, sem hora;
  - o nível previsto é o ÚLTIMO campo de cada passo (e `nivel_previsto_cm`). Os
    formatos diferem: Santa Tereza grava [hora, base, previsto] e Muçum
    [hora, modelo, agora, previsto] — ler o índice 2 em Muçum pega o nível de
    agora, não o previsto;
  - o previsto vale para hora do modelo + horizonte, não para a hora da
    leitura + horizonte (a leitura costuma ser 45-75 min mais nova que o
    modelo: contar do lugar errado dava margem a mais);
  - horizonte com disponivel=False fica de fora.
"""
import datetime as dt
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")
TELEMETRIA_VELHA_MIN = 180


def agora():
    return dt.datetime.now(FUSO)


def para_brt(iso):
    """ISO da previsão -> datetime em Brasília. Sem fuso = já é Brasília."""
    if not iso:
        return None
    try:
        t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=FUSO)
    return t.astimezone(FUSO)


def idade_min(iso, ref=None):
    t = para_brt(iso)
    if t is None:
        return None
    return round(((ref or agora()) - t).total_seconds() / 60.0)


def nivel_atual_cm(d):
    v = d.get("telemetria_ultima_nivel_cm")
    if v is None or para_brt(d.get("telemetria_ultima_em")) is None:
        return None
    return float(v)


def previstos_cm(d, horizontes=("2h", "4h")):
    """[(horizonte, minutos depois da leitura da régua, nível previsto em cm)],
    em ordem de tempo. Previsto cujo alvo já passou fica de fora: a leitura vale mais."""
    ref = para_brt(d.get("telemetria_ultima_em"))
    out = []
    for hk in horizontes:
        hv = (d.get("horizontes") or {}).get(hk) or {}
        if hv.get("disponivel") is False:
            continue
        horas = int(hk.rstrip("h"))
        pontos = [(p[0], p[-1]) for p in hv.get("passos") or [] if p]
        pontos.append((hv.get("hora_modelo"), hv.get("nivel_previsto_cm")))
        for hora, cm in pontos:
            if cm is None:
                continue
            base = para_brt(hora)
            if base is None or ref is None:
                minutos = horas * 60
            else:
                minutos = round((base + dt.timedelta(hours=horas) - ref).total_seconds() / 60.0)
            if minutos > 0:
                out.append((hk, minutos, float(cm)))
    return sorted(set(out), key=lambda x: (x[1], x[2]))
