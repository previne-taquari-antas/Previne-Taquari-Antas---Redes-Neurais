#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nível do rio para as rotas de fuga ao vivo (Santa Tereza e Muçum).

Lido pelos dois geradores (gerar_rota_fuga_santa_tereza.py e
gerar_rota_fuga_ruas.py). Só biblioteca padrão, para testar sem LiDAR.

Regras:
  - hora sem fuso no JSON da previsão é hora de Brasília (os robôs gravam a
    hora da telemetria da ANA). O runner do GitHub roda em UTC: sem isso a
    idade do dado sai 180 min maior;
  - nível atual ausente devolve None, nunca 0: quem chama decide não publicar
    em vez de inventar um rio seco que "sobe" até a previsão;
  - o nível previsto de cada horizonte é o maior entre `nivel_previsto_cm` e o
    ÚLTIMO campo de cada passo. Os formatos diferem: Santa Tereza grava
    [hora, base, previsto] e Muçum [hora, modelo, agora, previsto] — ler o
    índice 2 em Muçum pega o nível de agora, não o previsto;
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
    for k in ("telemetria_ultima_nivel_cm", "nivel_atual_cm"):
        v = d.get(k)
        if v is not None:
            return float(v)
    return None


def previstos_cm(d, horizontes=("2h", "4h")):
    """[(horizonte, minutos à frente, nível previsto em cm)] dos horizontes disponíveis."""
    out = []
    for hk in horizontes:
        hv = (d.get("horizontes") or {}).get(hk) or {}
        if hv.get("disponivel") is False:
            continue
        vals = [hv.get("nivel_previsto_cm")]
        vals += [p[-1] for p in hv.get("passos") or [] if p]
        vals = [float(v) for v in vals if v is not None]
        if vals:
            out.append((hk, int(hk.rstrip("h")) * 60, max(vals)))
    return out
