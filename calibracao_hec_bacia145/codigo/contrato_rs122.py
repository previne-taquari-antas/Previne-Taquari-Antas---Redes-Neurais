"""Gates de entrada e extração do runner RS122, sem HEC ou dependências GIS."""
import hashlib
import json
import re
from datetime import datetime, timedelta

from congelar_fontes_rs122 import fingerprint


def conferir_fontes(root, cfg):
    snap = json.loads((root / "experimentos/rs122/fontes.json").read_text(encoding="utf-8"))
    if snap["geometria_conferida_localmente"] != cfg["geometria"]:
        raise ValueError("Geometria não corresponde ao snapshot conferido")
    if cfg["bracos"] != ["A", "B0", "B1"] or cfg["janelas"] != ["S2023_07", "S2023_11"] or cfg["passos_min"] != [10, 5, 1]:
        raise ValueError("Desenho não corresponde ao pré-registro")
    for value in (cfg["geometria"]["manifesto_sha256"], cfg["geometria"]["particao_sha256"]):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Hash geométrico inválido")
    for name, expected in snap["entradas"].items():
        if fingerprint(root / name) != expected:
            raise ValueError("Fonte difere do controle congelado: " + name)
    return hashlib.sha256((root / "experimentos/rs122/fontes.json").read_bytes()).hexdigest()


def conferir_horas(horas, ini, fim):
    times = [datetime.fromisoformat(t) for t in horas]
    if len(times) < 2 or times[0] != ini or times[-1] != fim:
        raise ValueError("Limites da chuva incompatíveis com janela")
    if any(t.tzinfo is not None for t in times) or any(b - a != timedelta(hours=1) for a, b in zip(times, times[1:])):
        raise ValueError("Chuva não é grade horária local contínua e ordenada")


def conferir_extensao(root, cfg, passo):
    ex = json.loads((root / "experimentos/rs122/extensao_2min.json").read_text(encoding="utf-8"))
    if (ex["contrato_base_sha256_lf"] != fingerprint(root / "experimentos/rs122/contrato.json")["sha256"] or
        ex["snapshot_fontes_sha256_lf"] != fingerprint(root / "experimentos/rs122/fontes.json")["sha256"] or
        ex["passo_novo_min"] != 2 or passo != 2 or ex["passo_referencia_min"] != 1 or
        ex["janelas"] != cfg["janelas"] or ex["bracos"] != cfg["bracos"] or
        ex["triagem"] != {"pico_pct_max": 1, "volume_pct_max": 1, "instante_min_max": 10} or
        ex["exigir_ausencia_tc_floor_42403"] is not True):
        raise ValueError("Extensão não corresponde ao pré-registro/base congelada")
    if ex["referencia"]["run_id"] != "38284983152" or ex["referencia"]["codigo_commit"] != "84401448f203ae6f29ff6e3f66a9c0120e4c742d":
        raise ValueError("Referência da extensão mudou")
    for sim in cfg["janelas"]:
        if set(ex["referencia"]["vazao_sha256"][sim]) != set(cfg["bracos"]) or any(not re.fullmatch(r"[0-9a-f]{64}", v) for v in ex["referencia"]["vazao_sha256"][sim].values()):
            raise ValueError("Hashes de referência incompletos/inválidos")
    return ex


def conferir_metadata(path, requeridos, passo, total):
    rows = json.loads(path.read_text(encoding="utf-8"))
    groups = {n: [] for n in requeridos}
    for row in rows:
        n = row["node"]
        if n not in groups:
            raise ValueError("Nó inesperado na extração")
        if not row["pathname"].startswith("//" + n + "/FLOW/"):
            raise ValueError("Pathname DSS não corresponde a FLOW/nó")
        if row["units"].upper() not in ("M3/S", "CMS") or row["type"].upper() != "INST-VAL":
            raise ValueError("Unidade/tipo DSS incompatível")
        if row["interval"] != passo or row["count"] <= 0:
            raise ValueError("Passo/contagem DSS incompatível")
        groups[n].append(row)
    for n, records in groups.items():
        if not records or len({r["pathname"] for r in records}) != len(records) or sum(r["count"] for r in records) != total:
            raise ValueError("Blocos DSS incompletos/duplicados: " + n)
    return {"nos": len(groups), "registros_dss": len(rows), "tipo": "INST-VAL", "unidades": sorted({r["units"] for r in rows})}
