#!/usr/bin/env python3
"""Sombra do candidato linear de Muçum (4h e 8h). Pesquisa; não é alerta oficial.

A cada execução:
1. lê os CSVs horários de pesquisa (atualizados pelo robô HEC a cada 10 min);
2. pega a hora completa mais recente (rótulo u com u + 1 h <= agora) que tenha
   todas as variáveis, desde que não tenha mais de ``MAX_ATRASO_H`` horas;
3. prevê com o modelo congelado em ``config/mucum_candidato_ridge_v1.json``;
4. confere previsões antigas quando a hora-alvo aparece no CSV;
5. grava em ``assets/data/mucum_candidato_sombra/mucum/AAAA-MM.json`` (mesmo
   formato do arquivo permanente das previsões ao vivo) e ``sombra_atual.json``.

Nunca grava previsão para hora antiga: cada registro é emitido na hora em que
os dados estavam disponíveis (``criado_em_utc``). ``hora_modelo`` segue a
convenção do robô principal (hora do CSV - 1 h) para comparar com a RNA.

Não lê nem altera o robô principal, a RNA ou as páginas. Só biblioteca padrão.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import arquivar_historico_ao_vivo as ARQ  # noqa: E402
import mucum_candidato_features as F  # noqa: E402

BASE = ROOT / "assets/data/estudo_bacia_taquari_antas"
FLOW_CSV = BASE / "mucum_observed_multistation_flow_hourly.csv"
RAIN_CSV = BASE / "mucum_observed_multistation_rain_hourly.csv"
MODELO = ROOT / "config/mucum_candidato_ridge_v1.json"
DESTINO = ROOT / "assets/data/mucum_candidato_sombra"
LOCAL = "mucum"
BRT = timezone(timedelta(hours=-3))
MAX_ATRASO_H = 3
SEM_DADO_APOS_H = 6
OFFSET_ROBO_H = 1
NOME_MODELO = "CAND_RIDGE_M_LJJ_CHUVA_V1"


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.strip()).replace(minute=0, second=0, microsecond=0)


def ler_niveis(caminho: Path, codigos: tuple[str, ...]) -> dict[str, dict[datetime, float]]:
    out = {c: {} for c in codigos}
    with open(caminho, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            c = str(row.get("code", "")).strip()
            if c in out and row.get("level") not in (None, ""):
                try:
                    out[c][_t(row["time_local"])] = float(row["level"])
                except ValueError:
                    pass
    return out


def ler_chuva(caminho: Path) -> dict[datetime, float]:
    out = {}
    with open(caminho, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v = row.get("basin_mean_mm")
            if v not in (None, ""):
                try:
                    out[_t(row["time_local"])] = float(v)
                except ValueError:
                    pass
    return out


def carregar_registros(destino: Path) -> dict[str, dict]:
    regs = {}
    for arq in sorted((destino / LOCAL).glob("????-??.json")):
        regs.update(ARQ.carregar_mes(arq))
    return regs


def conferir(regs: dict[str, dict], m_raw: dict, agora_local: datetime, agora_utc: str) -> int:
    n = 0
    for r in regs.values():
        if r.get("status_auditoria") == "conferido":
            continue
        alvo = _t(r["hora_alvo_csv"])
        obs = m_raw.get(alvo)
        if obs is not None:
            erro = r["nivel_previsto_cm"] - obs
            r.update({"observado_cm": round(obs, 1), "erro_cm": round(erro, 1),
                      "erro_abs_cm": round(abs(erro), 1), "status_auditoria": "conferido",
                      "auditado_em_utc": agora_utc})
            n += 1
        elif alvo + timedelta(hours=1 + SEM_DADO_APOS_H) <= agora_local:
            if r.get("status_auditoria") != "sem_dado":
                r.update({"status_auditoria": "sem_dado", "auditado_em_utc": agora_utc})
                n += 1
    return n


def executar(agora_utc_dt: datetime | None = None, destino: Path = DESTINO,
             flow_csv: Path = FLOW_CSV, rain_csv: Path = RAIN_CSV, modelo_path: Path = MODELO) -> dict:
    agora_utc_dt = agora_utc_dt or datetime.now(timezone.utc)
    agora_local = agora_utc_dt.astimezone(BRT).replace(tzinfo=None)
    agora_utc = agora_utc_dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    cfg = json.loads(modelo_path.read_text(encoding="utf-8"))
    cod_m, cod_j = cfg["estacoes"]["M"], cfg["estacoes"]["J"]
    niveis = ler_niveis(flow_csv, (cod_m, cod_j))
    m_raw = niveis[cod_m]
    m, j = F.interpolar(m_raw), F.interpolar(niveis[cod_j])
    chuva = ler_chuva(rain_csv)

    regs = carregar_registros(destino)
    conferidos = conferir(regs, m_raw, agora_local, agora_utc)

    # hora completa mais recente com todas as variáveis
    limite = agora_local.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    emitidos, motivo, u_usado, x = [], None, None, None
    u = limite
    while u >= limite - timedelta(hours=MAX_ATRASO_H):
        if u in m_raw:
            x = F.vetor(m, j, chuva, u)
            if x is not None:
                u_usado = u
                break
        u -= timedelta(hours=1)
    if u_usado is None:
        motivo = f"sem hora completa com todas as variáveis nas últimas {MAX_ATRASO_H} h"
    else:
        for chave, mod in cfg["modelos"].items():
            h = int(mod["horizonte_h"])
            hora_modelo = u_usado - timedelta(hours=OFFSET_ROBO_H)
            rid = f"Muçum|{h}h|{NOME_MODELO}|{hora_modelo.isoformat()}"
            if rid in regs:
                continue  # previsão desta hora já emitida: nunca reescrever
            delta = F.prever(mod, x)
            base = m_raw[u_usado]
            regs[rid] = {
                "id": rid, "local": "Muçum", "estacao": cod_m, "horizonte": f"{h}h", "horizonte_h": h,
                "modelo": NOME_MODELO, "modelo_sha256": cfg.get("sha256_modelos"),
                "hora_modelo": hora_modelo.isoformat(), "hora_csv": u_usado.isoformat(),
                "hora_alvo_csv": (u_usado + timedelta(hours=h)).isoformat(),
                "hora_alvo": (hora_modelo + timedelta(hours=h)).isoformat(),
                "nivel_base_cm": round(base, 1), "delta_previsto_cm": round(delta, 1),
                "nivel_previsto_cm": round(base + delta, 1),
                "status_auditoria": "aguardando", "criado_em_utc": agora_utc,
                "posterior_ao_congelamento": u_usado > _t(cfg["congelado_ate"]),
            }
            emitidos.append(rid)

    ARQ.arquivar(LOCAL, list(regs.values()), destino)
    atual = {
        "schema_version": "mucum_candidato_sombra_atual_v1",
        "aviso": "Pesquisa em sombra. Não é alerta oficial nem substitui a RNA publicada.",
        "modelo": NOME_MODELO, "modelo_sha256": cfg.get("sha256_modelos"),
        "congelado_ate": cfg["congelado_ate"],
        "hora_csv_usada": u_usado.isoformat() if u_usado else None,
        "motivo_sem_previsao": motivo,
        "previsoes": [regs[r] for r in emitidos] or [
            r for r in regs.values()
            if u_usado and r.get("hora_csv") == u_usado.isoformat()
        ],
        "conferidos_nesta_execucao": conferidos,
    }
    texto = json.dumps(atual, ensure_ascii=False, indent=1) + "\n"
    caminho = destino / "sombra_atual.json"
    # só regrava quando muda algo além do relógio
    if emitidos or conferidos or not caminho.exists():
        destino.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
    return {"emitidos": emitidos, "conferidos": conferidos, "hora_csv": atual["hora_csv_usada"], "motivo": motivo}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.parse_args(argv)
    print("[sombra candidato Muçum]", json.dumps(executar(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
