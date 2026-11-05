#!/usr/bin/env python3
"""Diagnostico isolado, somente observacional, das entradas STZ 8h V001/V002.

Nao executa modelos, nao publica previsao e nao altera a suspensao operacional.
Uma resposta sem dados significa NAO CONFIRMADO; nunca prova estacao inativa.
"""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
from previne.robo import gerar_previsao_ao_vivo as R

OUT = Path("assets/data/stz_8h_inputs_audit_latest.json")
LEVELS = (
    "86472600", "86472000", "86125500", "86298000",
    "86306000", "86430900", "86448000", "86447000", "86505500",
)
TIMEOUT_S = 6

def main():
    R.CHUVA_ANA_CACHE.clear()
    R.ANA_XML_CACHE.clear()
    R.ULTIMA_RAW.clear()
    R.ANA_TIMEOUT_NIVEL_S = TIMEOUT_S
    R.ANA_TIMEOUT_CHUVA_S = TIMEOUT_S
    series = {}
    errors = {}
    # Somente os nove postos realmente exigidos pelas formulas 8h,
    # sem consultar todos os demais modelos suspensos.
    for cod in LEVELS:
        try:
            R.CHUVA_ANA_CACHE.pop(cod, None)
            series[cod] = R.buscar_ana(cod, dias=3, tentativas_rede=1)
        except Exception as exc:
            series[cod] = {}
            errors[cod] = repr(exc)
        print(f"[8h check] {cod}: {len(series[cod])} leituras de nivel reais", flush=True)
    try:
        series["__chuva8h_postos__"] = R.buscar_chuvas_8h(series)
    except Exception as exc:
        errors["chuva"] = repr(exc)
        series["__chuva8h_postos__"] = {}
    now = R.agora_brt()
    grade = now.replace(minute=0, second=0, microsecond=0)
    # Bases recentes 0-3h; compara ambas na mesma grade real, sem extrapolacao.
    bases = [grade - dt.timedelta(hours=h) for h in range(4)]
    modelos = {}
    for cfg in R.MODELOS:
        if cfg["horizonte"] not in ("8h", "8h_v002"):
            continue
        key = cfg["horizonte"]
        por_base = []
        for t in bases:
            try:
                values, _ = R.montar_inputs_modelo(cfg, series, t)
                audit = R.auditoria_inputs_8h(cfg, t, values)
                missing = R.diagnosticar_inputs_modelo(cfg, series, t, values)
                por_base.append({
                    "hora_base": t.isoformat(timespec="minutes"),
                    "pronta": audit["status"] == "NORMAL",
                    "n_inputs": len(values),
                    "n_presentes": len(values) - sum(v is None for v in values),
                    "n_ausentes": sum(v is None for v in values),
                    "entradas_ausentes": missing,
                    "auditoria_status": audit["status"],
                })
            except Exception as exc:
                por_base.append({
                    "hora_base": t.isoformat(timespec="minutes"),
                    "pronta": False, "erro_diagnostico": repr(exc)
                })
        modelos[key] = {"nome": cfg["modelo"], "n_inputs": cfg["inputs_total"],
                        "bases_recentes": por_base,
                        "ha_base_completa": any(x["pronta"] for x in por_base)}
    status_estacoes = {}
    for cod in LEVELS:
        dados = series.get(cod) or {}
        last = max(dados) if dados else None
        status_estacoes[cod] = {
            "observacoes_n": len(dados),
            "ultima_hora": last.isoformat(timespec="minutes") if last else None,
            "ultima_leitura_cm": dados[last] if last else None,
            "idade_ultima_leitura_min": round((now-last).total_seconds()/60) if last else None,
            "fonte": "ANA observada / coleta diagnostica independente",
            "situacao": "com_dados_observados" if dados else "nao_confirmada_neste_teste",
        }
    status_chuva = {}
    for cod, dados in (series.get("__chuva8h_postos__") or {}).items():
        last = max(dados) if dados else None
        status_chuva[cod] = {
            "observacoes_n": len(dados),
            "ultima_hora": last.isoformat(timespec="minutes") if last else None,
            "situacao": "com_dados_observados" if dados else "nao_confirmada_neste_teste",
        }
    resultado = {
        "schema_version": 1, "gerado_em": now.isoformat(timespec="seconds"),
        "status": "diagnostico_de_entradas_sem_inferencia",
        "alerta_oficial": False, "alterou_suspensao": False, "publicou_previsao": False,
        "nota": "Ausencia no endpoint de teste nao prova inatividade do sensor. Previsoes 8h permanecem suspensas.",
        "estacoes": status_estacoes, "chuva": status_chuva,
        "modelos": modelos, "falhas": errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(resultado, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    for k,m in modelos.items():
        print(f"[8h check] {k}: "+ "; ".join(
            f'{b["hora_base"]}: {b.get("n_presentes",0)}/{b.get("n_inputs",m["n_inputs"])}'
            for b in m["bases_recentes"]), flush=True)
    print("[8h check] relatorio escrito em", OUT, flush=True)

if __name__ == "__main__":
    main()
