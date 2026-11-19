#!/usr/bin/env python3
"""Muçum: candidato linear com chuva da bacia e Santa Tereza contra a RNA ao vivo,
nas mesmas horas, separado por regime do rio (subida, estável, descida).

Continua a triagem do PR #306 (que avaliou só horas de cheia). A avaliação
prospectiva de 19/11/2026 mostrou que as RNAs de Muçum 4h/8h erram muito com o
rio parado (26 e 66 cm contra ~4 cm da persistência) e que a 2h subestima
subidas. A pergunta aqui é se as entradas da triagem corrigem as duas coisas
ao mesmo tempo.

Dados
- 2026 contínuo (26/09 a 19/11): ``estudo_bacia_taquari_antas/mucum_observed_
  multistation_{flow,rain}_hourly.csv``.
- Cheias históricas (2023, 2024, jul/2026) do G040, sempre no treino.
- RNA ao vivo: ``historico_ao_vivo_arquivo/mucum`` (registros conferidos).

Alinhamento: o rótulo ``time_local`` do CSV fica 1 h à frente de
``hora_modelo`` do robô (diferença média 2,8 cm com o deslocamento, 10 cm
sem). Por isso a hora u do CSV corresponde à hora_modelo u-1. A chuva entra
atrasada em mais 1 h, por cautela, para não usar informação futura.

Validação: blocos de 7 dias de 2026; o bloco testado sai do treino com
margem de 48 h + horizonte de cada lado (purga). Modelo: Ridge sobre a
variação do nível (extrapola, ao contrário de árvores; ver #306).

Comparação justa: verdade e persistência vêm do próprio registro do robô;
previsão do candidato = nível do robô agora + variação prevista.

Pesquisa; não altera o robô ao vivo e não é alerta oficial.
Requer pandas e scikit-learn. Uso: python scripts/experimento_mucum_candidato_regimes.py
"""
from __future__ import annotations

import glob
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
G040 = ROOT / "assets/data/hec_hms_g040_full_basin"
BASE = ROOT / "assets/data/estudo_bacia_taquari_antas"
ARQ = ROOT / "assets/data/historico_ao_vivo_arquivo/mucum"
OUT = ROOT / "assets/data/research_mucum_candidato_regimes_latest.json"

M, J, S = "86510000", "86472000", "86472600"
HORIZONS = (2, 4, 8)
BLOCK_DAYS, PURGE_H = 7, 48
OFFSET_CSV_ROBO_H = 1
SUBIDA, ESTAVEL = 30, 10
CHEIA_CM, SUBIDA_CHEIA_CM = 500, 50  # bankfull_cm do robô de Muçum; critério do #306
CANDIDATES = {
    "base_M_LJJ": ["M", "LJJ"],
    "M_LJJ_chuva": ["M", "LJJ", "RAIN"],
    "M_LJJ_STZ_chuva": ["M", "LJJ", "STZ", "RAIN"],
}


# ---------------------------------------------------------------- dados
def historical_events() -> dict[str, pd.DataFrame]:
    out = {}
    for path in sorted(glob.glob(str(G040 / "historical_hydro_events/*.json"))):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        cols = {}
        for st in data["stations"]:
            if not st["series"] or st["code"] not in (M, J, S):
                continue
            t = pd.to_datetime([r["time_utc"] for r in st["series"]]).tz_convert("America/Sao_Paulo").tz_localize(None)
            cols[st["code"]] = pd.Series([r.get("level_source_unit") for r in st["series"]], index=t, dtype=float)
        if M not in cols:
            continue
        df = pd.DataFrame(cols)
        df = df.reindex(pd.date_range(df.index.min(), df.index.max(), freq="h")).interpolate(limit=2, limit_area="inside")
        for code in (M, J, S):
            if code not in df:
                df[code] = np.nan
        rain_path = G040 / "historical_calibration_forcing" / data["event_id"] / "rain.json"
        if rain_path.exists():
            block = json.loads(rain_path.read_text(encoding="utf-8"))["upper_antas_nested_forcing"]
            area = {k: v["zone_geometry_km2"] for k, v in block["diagnostics"]["grid_overlap"].items()}
            zones = pd.DataFrame({
                z["subbasin_id"]: pd.Series({pd.Timestamp(r["time_local"]): r.get("mm") for r in z["series"]}, dtype=float)
                for z in block["zones"]
            })
            rain = sum(zones[k] * area[k] for k in zones) / sum(area.values())
            df = df.reindex(pd.date_range(min(rain.index.min(), df.index.min()), df.index.max(), freq="h"))
            df["rain"] = rain.reindex(df.index)
        out[data["event_id"]] = df
    return out


def continuous_2026() -> pd.DataFrame:
    flow = pd.read_csv(BASE / "mucum_observed_multistation_flow_hourly.csv", dtype={"code": str}, parse_dates=["time_local"])
    level = flow.pivot_table(index="time_local", columns="code", values="level", aggfunc="last")
    level = level.reindex(pd.date_range(level.index.min(), level.index.max(), freq="h")).interpolate(limit=2, limit_area="inside")
    rain = pd.read_csv(BASE / "mucum_observed_multistation_rain_hourly.csv", parse_dates=["time_local"]).set_index("time_local")
    df = level[[M, J, S]].copy()
    df["rain"] = rain["basin_mean_mm"].reindex(df.index)
    return df


def diff(x, k):
    return x - x.shift(k)


def features(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    y, x, z = df[M], df[J], df[S]
    g = {
        "M": pd.DataFrame({"nM": y, **{f"d{k}M": diff(y, k) for k in (1, 2, 4, 8)},
                           "a2M": diff(y, 2) - diff(y, 2).shift(2), "a4M": diff(y, 4) - diff(y, 4).shift(4)}),
        "LJJ": pd.DataFrame({"nJ": x, **{f"d{k}J": diff(x, k) for k in (1, 2, 4, 8)},
                             "a4J": diff(x, 4) - diff(x, 4).shift(4)}),
        "STZ": pd.DataFrame({"nSTZ": z, **{f"d{k}STZ": diff(z, k) for k in (2, 4, 8)}}),
    }
    if "rain" in df and df["rain"].notna().any():
        r = df["rain"].shift(1)  # cautela: 1 h a mais de atraso
        g["RAIN"] = pd.DataFrame({f"r{k}": r.rolling(k, min_periods=k).sum() for k in (3, 6, 12, 24, 48)})
    return g


def table(df: pd.DataFrame, groups: list[str], h: int, tag: str) -> pd.DataFrame | None:
    f = features(df)
    if any(gname not in f for gname in groups):
        return None
    X = pd.concat([f[gname] for gname in groups], axis=1)
    X["_t"] = df[M].shift(-h) - df[M]
    X["_tag"] = tag
    X["_time"] = X.index
    return X.dropna()


# ---------------------------------------------------------------- modelo
def blocked_predictions(hist: list[pd.DataFrame], cont: pd.DataFrame, h: int) -> pd.Series:
    cols = [c for c in cont.columns if not c.startswith("_")]
    hist = [t[cols + ["_t"]] for t in hist if t is not None and len(t) and set(cols) <= set(t.columns)]
    pred = pd.Series(np.nan, index=cont.index)
    t0 = cont["_time"].min().normalize()
    edges = pd.date_range(t0, cont["_time"].max() + pd.Timedelta(days=BLOCK_DAYS), freq=f"{BLOCK_DAYS}D")
    margin = pd.Timedelta(hours=PURGE_H + h)
    for a, b in zip(edges, edges[1:]):
        test = (cont["_time"] >= a) & (cont["_time"] < b)
        if not test.any():
            continue
        train = (cont["_time"] < a - margin) | (cont["_time"] >= b + margin)
        Xtr = pd.concat([cont.loc[train, cols + ["_t"]]] + hist)
        if len(Xtr) < 200:
            continue
        model = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 12)))
        model.fit(Xtr[cols], Xtr["_t"])
        pred[test] = model.predict(cont.loc[test, cols])
    return pred


# ---------------------------------------------------------------- avaliação
def live_records() -> pd.DataFrame:
    regs = []
    for arq in sorted(ARQ.glob("????-??.json")):
        regs += json.loads(arq.read_text("utf-8"))["registros"]
    d = pd.DataFrame(regs)
    d = d[(d.status_auditoria == "conferido") & d.observado_cm.notna() & d.nivel_previsto_cm.notna()]
    d["t"] = pd.to_datetime(d.hora_modelo)
    return d


def regime(delta: float) -> str:
    if delta >= SUBIDA:
        return "subida"
    if delta <= -SUBIDA:
        return "descida"
    if abs(delta) < ESTAVEL:
        return "estavel"
    return "variacao_moderada"


def _m(e: pd.Series) -> dict | None:
    if not e.size:
        return None
    return {"n": int(e.size), "mae_cm": round(float(e.abs().mean()), 1), "vies_cm": round(float(e.mean()), 1)}


def summarize(err: pd.Series, reg: pd.Series, cheia: pd.Series | None = None,
              subida_cheia: pd.Series | None = None) -> dict:
    out = {"geral": _m(err)}
    if cheia is not None:
        out["cheia"] = _m(err[cheia])
        out["subida_em_cheia"] = _m(err[subida_cheia])
    for name, g in err.groupby(reg):
        out[name] = {"n": int(g.size), "mae_cm": round(float(g.abs().mean()), 1), "vies_cm": round(float(g.mean()), 1)}
    return out


def main() -> None:
    events = historical_events()
    cont = continuous_2026()
    live = live_records()
    resultados = []
    for h in HORIZONS:
        lv = live[live.horizonte == f"{h}h"]
        # um modelo ao vivo por horizonte e hora: o principal (sem "versao_b")
        lv = lv.sort_values("criado_em").drop_duplicates("t", keep="last").set_index("t")
        preds = {}
        for name, groups in CANDIDATES.items():
            T = table(cont, groups, h, "2026")
            hist = [table(df, groups, h, eid) for eid, df in events.items()]
            p = blocked_predictions(hist, T, h)
            # hora u do CSV -> hora_modelo u-1 do robô
            preds[name] = pd.Series(p.values, index=T["_time"] - pd.Timedelta(hours=OFFSET_CSV_ROBO_H))
        idx = lv.index
        for p in preds.values():
            idx = idx.intersection(p.dropna().index)
        j = lv.loc[idx]
        verdade, agora = j.observado_cm.astype(float), j.nivel_rio_agora_cm.astype(float)
        reg = (verdade - agora).map(regime)
        cheia = np.maximum(agora, verdade) >= CHEIA_CM
        sub_cheia = cheia & ((verdade - agora) >= SUBIDA_CHEIA_CM)
        linha = {
            "horizonte_h": h,
            "periodo": [str(idx.min()), str(idx.max())],
            "modelos_ao_vivo": sorted(j.modelo.unique()),
            "persistencia": summarize(agora - verdade, reg, cheia, sub_cheia),
            "rna_ao_vivo": summarize(j.nivel_previsto_cm.astype(float) - verdade, reg, cheia, sub_cheia),
        }
        for name, p in preds.items():
            linha[name] = summarize(agora + p.loc[idx] - verdade, reg, cheia, sub_cheia)
        resultados.append(linha)
        print(f"{h}h cheia: n={int(cheia.sum())}", {k: linha[k]["cheia"]["mae_cm"] for k in linha
                                                   if isinstance(linha[k], dict) and linha[k].get("cheia")})
    payload = {
        "schema_version": "mucum_candidato_regimes_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "research_only": True,
        "aviso": "Pesquisa. Não altera o robô ao vivo nem constitui alerta.",
        "metodo": {
            "validacao": f"blocos de {BLOCK_DAYS} dias em 2026 com purga de {PURGE_H} h + horizonte; cheias históricas sempre no treino",
            "modelo": "RidgeCV sobre a variação do nível (StandardScaler)",
            "alinhamento": f"hora do CSV = hora_modelo do robô + {OFFSET_CSV_ROBO_H} h; chuva atrasada mais 1 h",
            "cheia": f"nivel agora ou observado >= {CHEIA_CM} cm (bankfull_cm do robô); subida em cheia: + >= {SUBIDA_CHEIA_CM} cm",
            "regimes_cm": {"subida": f">= +{SUBIDA}", "descida": f"<= -{SUBIDA}", "estavel": f"|delta| < {ESTAVEL}"},
            "candidatos": CANDIDATES,
        },
        "limitacoes": [
            "Período contínuo de 2026 tem ~8 semanas e poucas cheias grandes.",
            "Santa Tereza só existe em 2026 nas séries usadas: o candidato com STZ treina com menos cheias.",
            "O CSV de pesquisa é média horária; o robô lê o último valor. Diferença média 2,8 cm após alinhamento.",
            "Regime definido pelo observado; não é conhecido na hora da previsão.",
        ],
        "resultados": resultados,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("gravado", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
