"""Avaliacao prospectiva das previsoes ao vivo a partir do arquivo permanente.

Le ``assets/data/historico_ao_vivo_arquivo/<local>/AAAA-MM.json`` e publica
``assets/data/avaliacao_prospectiva_ao_vivo_latest.json`` com, por local,
horizonte e modelo:

- erro medio absoluto (MAE), P95 e vies contra a persistencia (nivel de agora);
- os mesmos numeros por regime do rio na hora-alvo: subida (>= +30 cm),
  estavel (|variacao| < 10 cm) e descida (<= -30 cm);
- disponibilidade: horas cheias com previsao / horas do periodo do modelo
  e as maiores lacunas.

So considera registros ``conferido`` (observado na hora-alvo exata).
Persistencia = ``nivel_rio_agora_cm`` -> ``observado_cm``.

Somente biblioteca padrao. Pesquisa; nao e alerta oficial.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVO = RAIZ / "assets" / "data" / "historico_ao_vivo_arquivo"
SAIDA = RAIZ / "assets" / "data" / "avaliacao_prospectiva_ao_vivo_latest.json"

# Cota de transbordamento do robô (bankfull_cm): o foco da avaliação é a cheia.
CHEIA_CM = {"santa_tereza": 1500, "mucum": 500}
SUBIDA_CHEIA_CM = 50
SUBIDA_CM = 30
ESTAVEL_CM = 10
MIN_REGISTROS = 30


def carregar(local: str, pasta: Path = ARQUIVO) -> list[dict]:
    regs = []
    for arq in sorted((pasta / local).glob("????-??.json")):
        regs += json.loads(arq.read_text("utf-8")).get("registros", [])
    return regs


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    i = (len(s) - 1) * q
    lo, hi = math.floor(i), math.ceil(i)
    return round(s[lo] + (s[hi] - s[lo]) * (i - lo), 1)


def metricas(pares: list[tuple[float, float, float]]) -> dict | None:
    """pares = (previsto, persistencia, observado)."""
    if not pares:
        return None
    em = [p - o for p, _, o in pares]
    ep = [a - o for _, a, o in pares]
    mae = sum(abs(e) for e in em) / len(em)
    mae_p = sum(abs(e) for e in ep) / len(ep)
    return {
        "n": len(pares),
        "mae_cm": round(mae, 1),
        "mae_persistencia_cm": round(mae_p, 1),
        # >0: a rede erra menos que a persistencia; <0: erra mais.
        "skill_mae_vs_persistencia": (round(1 - mae / mae_p, 3) if mae_p > 0 else None),
        "vies_cm": round(sum(em) / len(em), 1),
        "p95_erro_abs_cm": _pct([abs(e) for e in em], 0.95),
    }


def regime(agora: float, obs: float) -> str:
    d = obs - agora
    if d >= SUBIDA_CM:
        return "subida"
    if d <= -SUBIDA_CM:
        return "descida"
    if abs(d) < ESTAVEL_CM:
        return "estavel"
    return "variacao_moderada"


def disponibilidade(horas: list[str]) -> dict:
    ts = sorted({dt.datetime.fromisoformat(h[:13]) for h in horas})
    if not ts:
        return {}
    total = int((ts[-1] - ts[0]).total_seconds() // 3600) + 1
    lacunas = sorted(
        ((int((b - a).total_seconds() // 3600) - 1, a) for a, b in zip(ts, ts[1:])),
        reverse=True,
    )
    return {
        "horas_com_previsao": len(ts),
        "horas_no_periodo": total,
        "fracao": round(len(ts) / total, 3),
        "maiores_lacunas": [
            {"horas_sem_previsao": g, "apos": a.strftime("%Y-%m-%dT%H:00")}
            for g, a in lacunas[:3] if g > 0
        ],
    }


def avaliar_local(regs: list[dict], cheia_cm: float | None = None) -> list[dict]:
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    for r in regs:
        grupos[(r.get("horizonte"), r.get("modelo"))].append(r)
    linhas = []
    for (hz, modelo), rs in sorted(grupos.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        pares, por_regime, cheia, subida_cheia = [], defaultdict(list), [], []
        for r in rs:
            if r.get("status_auditoria") != "conferido":
                continue
            p, a, o = (_num(r.get(k)) for k in ("nivel_previsto_cm", "nivel_rio_agora_cm", "observado_cm"))
            if None in (p, a, o):
                continue
            pares.append((p, a, o))
            por_regime[regime(a, o)].append((p, a, o))
            if cheia_cm is not None and max(a, o) >= cheia_cm:
                cheia.append((p, a, o))
                if o - a >= SUBIDA_CHEIA_CM:
                    subida_cheia.append((p, a, o))
        if len(pares) < MIN_REGISTROS:
            continue
        horas = [r["hora_modelo"] for r in rs if r.get("hora_modelo")]
        linhas.append({
            "horizonte": hz,
            "modelo": modelo,
            "primeira_hora_modelo": min(horas),
            "ultima_hora_modelo": max(horas),
            "registros": len(rs),
            "cheia": metricas(cheia),
            "subida_em_cheia": metricas(subida_cheia),
            "geral": metricas(pares),
            "por_regime": {k: metricas(v) for k, v in sorted(por_regime.items())},
            "disponibilidade": disponibilidade(horas),
        })
    return linhas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arquivo", type=Path, default=ARQUIVO)
    ap.add_argument("--saida", type=Path, default=SAIDA)
    args = ap.parse_args(argv)

    locais = sorted(p.name for p in args.arquivo.glob("*") if p.is_dir())
    resultado = {
        "schema_version": "previne_avaliacao_prospectiva_ao_vivo_v1",
        "aviso": "Pesquisa. Avaliacao das previsoes ao vivo ja conferidas; nao e alerta oficial.",
        "definicoes": {
            "persistencia": "nivel do rio na hora da previsao repetido na hora-alvo",
            "skill_mae_vs_persistencia": "1 - MAE_rede / MAE_persistencia (>0 = rede melhor)",
            "cheia": "nivel agora ou observado >= cota de transbordamento do robo (bankfull_cm)",
            "cheia_cm": CHEIA_CM,
            "subida_em_cheia": f"cheia e observado - nivel_agora >= {SUBIDA_CHEIA_CM} cm",
            "subida": f"observado - nivel_agora >= {SUBIDA_CM} cm",
            "descida": f"observado - nivel_agora <= -{SUBIDA_CM} cm",
            "estavel": f"|observado - nivel_agora| < {ESTAVEL_CM} cm",
            "min_registros_conferidos": MIN_REGISTROS,
        },
        "locais": {},
    }
    for local in locais:
        resultado["locais"][local] = avaliar_local(carregar(local, args.arquivo), CHEIA_CM.get(local))
    texto = json.dumps(resultado, ensure_ascii=False, indent=1) + "\n"
    args.saida.write_text(texto, encoding="utf-8")
    for local, linhas in resultado["locais"].items():
        for l in linhas:
            g = l["cheia"]
            if not g:
                continue
            print(f"{local:12s} {l['horizonte']:12s} {l['modelo'][:40]:40s} cheia n={g['n']:4d} "
                  f"MAE {g['mae_cm']:6.1f} pers {g['mae_persistencia_cm']:6.1f} vies {g['vies_cm']:6.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
