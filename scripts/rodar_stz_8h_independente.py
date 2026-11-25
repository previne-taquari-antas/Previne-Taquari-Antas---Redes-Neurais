#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Retoma a coleta/inferencia RNA 8h de Santa Tereza sem bloquear os robos 2h/4h.

Este robo publica um feed separado. Somente entradas horarias exatas, modelos
MAT com hash confirmado e bases recentes podem produzir previsao disponivel.
Dados ausentes resultam em diagnostico explicito, jamais em nivel inventado.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from previne.robo import gerar_previsao_ao_vivo as R

OUT = Path("previsao_stz_8h.json")
CACHE_OBSERVADO = Path("assets/data/stz_8h_niveis_observados_cache.json")
LEVELS = (
    "86472600", "86472000", "86125500", "86298000",
    "86306000", "86430900", "86448000", "86447000", "86505500",
)
HORIZONTES = ("8h", "8h_v002")
MAX_BASE_AGE = dt.timedelta(hours=2)
MAX_TELEMETRY_AGE = dt.timedelta(minutes=90)


def completar_lags_ana_observados(series: dict) -> dict:
    """Mescla SOMENTE leituras reais de outros ciclos, preservando a hora ANA.

    Nao altera ULTIMA_RAW, portanto a idade da ultima observacao continua
    sendo a idade do servico consultado no ciclo atual. Nenhum zero artificial,
    interpolacao ou previsao entra no cache.
    """
    agora = R.agora_brt()
    corte = agora - dt.timedelta(days=4)
    anterior = {"schema_version": 1, "estacoes": {}}
    if CACHE_OBSERVADO.exists():
        try:
            anterior = json.loads(CACHE_OBSERVADO.read_text(encoding="utf-8"))
            if anterior.get("schema_version") != 1 or not isinstance(anterior.get("estacoes"), dict):
                raise ValueError("schema do cache incorreto")
        except Exception as exc:
            print("[8h cache] cache invalido; sem uso:", exc)
            anterior = {"schema_version": 1, "estacoes": {}}
    resumo = {}
    mudou = not CACHE_OBSERVADO.exists()
    for cod in LEVELS:
        atuais = dict(series.get(cod) or {})
        salvos = anterior["estacoes"].get(cod, [])
        mescla = {}
        for registro in salvos:
            if not isinstance(registro, (list, tuple)) or len(registro) != 2:
                continue
            try:
                hora = dt.datetime.fromisoformat(str(registro[0]))
                valor = float(registro[1])
            except (ValueError, TypeError):
                continue
            if corte <= hora <= agora and hora.tzinfo is None and R._nivel_plausivel(valor, cod):
                mescla[hora] = valor
        recuperados = sum(h not in atuais for h in mescla)
        mescla.update({
            h: float(v) for h, v in atuais.items()
            if isinstance(h, dt.datetime) and h.tzinfo is None
            and corte <= h <= agora and R._nivel_plausivel(v, cod)
        })
        # Fonte atual prevalece na duplicidade; nenhuma lacuna e preenchida.
        series[cod] = dict(sorted(mescla.items()))
        registros = [[h.isoformat(timespec="seconds"), v] for h, v in sorted(mescla.items())]
        if registros != salvos:
            mudou = True
        anterior["estacoes"][cod] = registros
        resumo[cod] = {"niveis_reais": len(registros), "lags_recuperados": recuperados}
    if mudou:
        CACHE_OBSERVADO.parent.mkdir(parents=True, exist_ok=True)
        CACHE_OBSERVADO.write_text(json.dumps(anterior, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return resumo


def bloquear(out: dict, motivo: str) -> dict:
    if out.get("nivel_previsto_cm") is not None:
        out["previsao_candidata_nao_publicada_cm"] = out["nivel_previsto_cm"]
    out["nivel_previsto_cm"] = None
    out["delta_previsto_cm"] = None
    out["disponivel"] = False
    out["passos"] = []
    out["status"] = "indisponivel: " + motivo
    out["bloqueio_publicacao"] = "entrada_ou_frescor_invalido"
    return out


def main() -> None:
    agora = R.agora_brt()
    R.ANA_XML_CACHE.clear()
    R.CHUVA_ANA_CACHE.clear()
    R.ULTIMA_RAW.clear()
    # Processo separado, sem atrasar a rotina de 2h/4h.
    R.ANA_TIMEOUT_NIVEL_S = 12
    R.ANA_TIMEOUT_CHUVA_S = 12
    R.ANA_RETRIES_NIVEL = 1
    R.ANA_RETRIES_CHUVA = 1
    errors = {}

    try:
        series = R.buscar_series_paralelo(LEVELS, R.buscar_ana, max_workers=1)
    except Exception as exc:
        series = {cod: {} for cod in LEVELS}
        errors["niveis"] = str(exc)

    try:
        print("[8h cache]", completar_lags_ana_observados(series))
    except Exception as exc:
        errors["cache"] = str(exc)

    try:
        # As fontes usam chuva observada ou CSV de observacoes reais, nunca
        # preenchem lacunas com zero. O modelo nao roda com input ausente.
        series["__chuva36h_postos__"] = {}
        series["__chuva8h_postos__"] = R.buscar_chuvas_8h(series)
    except Exception as exc:
        series["__chuva8h_postos__"] = {}
        errors["chuvas"] = str(exc)

    horas_st = sorted(series.get("86472600", {}))
    raw_st = R.ULTIMA_RAW.get("86472600")
    hora_telemetria = raw_st[0] if raw_st else None
    configs = {cfg["horizonte"]: cfg for cfg in R.MODELOS if cfg["horizonte"] in HORIZONTES}
    horizontes = {}
    status_estacoes = R.resumo_estacoes(series)

    for chave in HORIZONTES:
        cfg = dict(configs[chave], ativo_ao_vivo=True)
        aviso = "EXPERIMENTAL: RNA de 8h em acompanhamento; nao e alerta oficial."
        t = R.escolher_hora_modelo(cfg, series, horas_st)
        out = R.gerar_saida_modelo(cfg, series, t, aviso, status_estacoes)
        out["proxima_base_diagnostico"] = R.diagnosticar_proxima_base(cfg, series, t)
        out["origem_execucao"] = "robo_independente_8h"
        out["qualidade_ao_vivo"] = {
            "status": "ENTRADAS_VERIFICADAS" if out.get("disponivel") else "ENTRADAS_INCOMPLETAS",
            "regra": "inputs horarios exatos; modelo SHA256; base < 2h; telemetria < 90min",
        }

        # Quando nao existe hora-base completa, registrar quais entradas faltam.
        if t is None and horas_st:
            tentativa = agora.replace(minute=0, second=0, microsecond=0)
            try:
                valores, _ = R.montar_inputs_modelo(cfg, series, tentativa)
                faltantes = R.diagnosticar_inputs_modelo(cfg, series, tentativa, valores)
                out["inputs_faltantes_n"] = len(faltantes)
                out["inputs_faltantes"] = faltantes
                out["auditoria_inputs"] = R.auditoria_inputs_8h(cfg, tentativa, valores)
                out["proxima_base_diagnostico"] = {
                    "hora": tentativa.isoformat(timespec="minutes"),
                    "pronta": False,
                    "inputs_faltantes_n": len(faltantes),
                    "inputs_faltantes": faltantes[:15],
                    "auditoria_status": "INVALIDO",
                }
            except Exception as exc:
                errors[chave] = str(exc)

        if out.get("disponivel"):
            hora_base = R._parse_hora(out.get("hora_modelo") or "")
            hora_alvo = R._parse_hora(out.get("hora_alvo") or "")
            if (
                not hora_base or not hora_alvo or
                not hora_telemetria or
                hora_base > agora or
                agora - hora_base >= MAX_BASE_AGE or
                agora - hora_telemetria > MAX_TELEMETRY_AGE or
                hora_alvo <= agora or
                (out.get("auditoria_inputs") or {}).get("status") != "NORMAL" or
                out.get("modelo_sha256", "").upper() != cfg["modelo_sha256"].upper()
            ):
                bloquear(out, "base, telemetria, contrato ou hash de modelo nao validado")
                out["qualidade_ao_vivo"]["status"] = "INVALIDO"
        horizontes[chave] = out

    pacote = {
        "schema_version": 1,
        "modo": "ao_vivo",
        "estacao": "86472600",
        "local": "Santa Tereza",
        "consultado_em": R.agora_brt().isoformat(timespec="seconds"),
        "gerado_em": R.agora_brt().isoformat(timespec="seconds"),
        "status": "8h disponivel com entradas validadas" if any(
            h.get("disponivel") for h in horizontes.values()
        ) else "8h em coleta; aguardando entradas completas",
        "pesquisa_experimental": True,
        "alerta_oficial": False,
        "horizontes": horizontes,
        "erros_consulta": errors,
    }
    OUT.write_text(json.dumps(pacote, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("STZ 8h:", pacote["status"])
    for key, value in horizontes.items():
        print(key, value.get("status"), "faltantes=", value.get("inputs_faltantes_n"))


if __name__ == "__main__":
    main()
