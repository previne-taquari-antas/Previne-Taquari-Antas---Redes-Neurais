#!/usr/bin/env python3
"""Triagem de inputs para Mucum avaliada SOMENTE em grandes eventos (4h, 8h, 12h).

Complementa scripts/screen_mucum_input_candidates.py, que media o erro em todas
as horas. Aqui o erro so conta em cheia:
  - horas de cheia: nivel de Mucum >= 500 cm na emissao ou no alvo;
  - ramo de subida: variacao observada >= +50 cm no horizonte;
  - pico: previsao emitida h horas antes do pico de cada evento.

Eventos: cheias historicas (2023-2024 e jul/2026, quando a estacao existe no
arquivo) + quatro eventos de set-nov/2026. Validacao deixa um evento inteiro de
fora por vez. Cada candidato e comparado ao baseline (Mucum + Linha Jose Julio)
nas mesmas horas e nos mesmos eventos.

Modelo principal: regressao linear regularizada (Ridge), porque extrapola para
cheias maiores que as de treino; gradient boosting e reportado como contraste.

Somente pesquisa; nao altera o robo ao vivo.
Requer: pandas, scikit-learn.  Uso: python scripts/screen_mucum_flood_inputs.py
"""
from __future__ import annotations

import glob
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
G040 = ROOT / "assets/data/hec_hms_g040_full_basin"
BASE = ROOT / "assets/data/estudo_bacia_taquari_antas"
OUT = ROOT / "assets/data/research_mucum_flood_input_screening_latest.json"

M, J, P, S, C = "86510000", "86472000", "86447000", "86472600", "86500000"
HORIZONS = (4, 8, 12)
FLOOD_CM, RISE_CM = 500.0, 50.0
ZONES = ["PRATA_7868", "ANTAS_RESIDUAL", "CARREIRO_7866", "STZ_RESIDUAL", "INC_MUCUM"]
EVENTS_2026 = {
    "E2026_SET": ("2026-09-26", "2026-10-02 23:00"),
    "E2026_OUT4": ("2026-10-03", "2026-10-07 23:00"),
    "E2026_OUT9": ("2026-10-08", "2026-10-13 23:00"),
    "E2026_NOV": ("2026-11-02", "2026-11-09 23:00"),
}


def historical_events():
    out = {}
    for path in sorted(glob.glob(str(G040 / "historical_hydro_events/*.json"))):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        cols = {}
        for st in data["stations"]:
            if not st["series"] or st["code"] not in (M, J, P, S, C):
                continue
            t = pd.to_datetime([r["time_utc"] for r in st["series"]]).tz_convert("America/Sao_Paulo").tz_localize(None)
            cols[st["code"]] = pd.Series([r.get("level_source_unit") for r in st["series"]], index=t, dtype=float)
        if M not in cols:
            continue
        df = pd.DataFrame(cols)
        df = df.reindex(pd.date_range(df.index.min(), df.index.max(), freq="h")).interpolate(limit=2, limit_area="inside")
        for code in (M, J, P, S, C):
            if code not in df:
                df[code] = np.nan
        out[data["event_id"]] = df
    return out


def historical_rain(event_id):
    path = G040 / "historical_calibration_forcing" / event_id / "rain.json"
    if not path.exists():
        return None
    block = json.loads(path.read_text(encoding="utf-8"))["upper_antas_nested_forcing"]
    area = {k: v["zone_geometry_km2"] for k, v in block["diagnostics"]["grid_overlap"].items()}
    zones = pd.DataFrame({
        z["subbasin_id"]: pd.Series({pd.Timestamp(r["time_local"]): r.get("mm") for r in z["series"]}, dtype=float)
        for z in block["zones"]
    })
    out = pd.DataFrame({"r_" + k.replace("SB_", ""): zones[k] for k in zones})
    out["rain"] = sum(zones[k] * area[k] for k in zones) / sum(area.values())
    return out


def build_events():
    events = historical_events()
    for event_id in list(events):
        rain = historical_rain(event_id)
        if rain is None:
            continue
        df = events[event_id]
        df = df.reindex(pd.date_range(rain.index.min(), df.index.max(), freq="h"))
        for col in rain:
            df[col] = rain[col].reindex(df.index)
        events[event_id] = df
    flow = pd.read_csv(BASE / "mucum_observed_multistation_flow_hourly.csv", dtype={"code": str}, parse_dates=["time_local"])
    level = flow.pivot_table(index="time_local", columns="code", values="level", aggfunc="last")
    level = level.reindex(pd.date_range(level.index.min(), level.index.max(), freq="h")).interpolate(limit=2, limit_area="inside")
    rain = pd.read_csv(BASE / "mucum_observed_multistation_rain_hourly.csv", parse_dates=["time_local"]).set_index("time_local")
    for event_id, (a, b) in EVENTS_2026.items():
        df = level.loc[a:b, [M, J, P, S, C]].copy()
        df["rain"] = rain["basin_mean_mm"].reindex(df.index)
        for z in ZONES:
            df["r_" + z] = rain[f"subbasin_SB_{z}_mm"].reindex(df.index)
        events[event_id] = df
    return events


def diff(x, k):
    return x - x.shift(k)


def accel(x, k):
    return (x - x.shift(k)) - (x.shift(k) - x.shift(2 * k))


def feature_groups(df):
    y, x = df[M], df[J]
    groups = {
        "M": pd.DataFrame({"nM": y, **{f"d{k}M": diff(y, k) for k in (1, 2, 4, 8)}, "a2M": accel(y, 2), "a4M": accel(y, 4)}),
        "LJJ": pd.DataFrame({"nJ": x, **{f"d{k}J": diff(x, k) for k in (1, 2, 4, 8)}, "a4J": accel(x, 4)}),
    }
    for name, code in (("STZ", S), ("PRATA", P), ("CARR", C)):
        z = df[code]
        groups[name] = pd.DataFrame({"n" + name: z, **{f"d{k}{name}": diff(z, k) for k in (2, 4, 8)}})
    if "rain" in df:
        r = df["rain"]
        groups["RAIN"] = pd.DataFrame({f"r{k}": r.rolling(k, min_periods=k).sum() for k in (3, 6, 12, 24, 48)})
        groups["RZONE"] = pd.DataFrame(
            {f"r_{z}_{k}": df["r_" + z].rolling(k, min_periods=k).sum() for z in ZONES for k in (6, 12, 24)}
        )
    return groups


EVENTS = build_events()
FEATS = {e: feature_groups(df) for e, df in EVENTS.items()}


def table(groups, h, future_rain=False):
    rows = []
    for event_id, df in EVENTS.items():
        if any(g not in FEATS[event_id] for g in groups):
            continue
        X = pd.concat([FEATS[event_id][g] for g in groups], axis=1)
        if future_rain:  # chuva dos proximos h horas, como se a previsao de chuva fosse perfeita
            X["fut"] = df["rain"].rolling(h, min_periods=h).sum().shift(-h)
        X["_t"], X["_y"], X["_e"] = df[M].shift(-h) - df[M], df[M], event_id
        rows.append(X.dropna())
    return pd.concat(rows).reset_index(drop=True) if rows else None


def leave_one_event_out(T, cols, kind="ridge"):
    pred = pd.Series(np.nan, index=T.index)
    for event_id in T._e.unique():
        train = T._e != event_id
        if train.sum() < 100:
            continue
        if kind == "ridge":
            model = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 12)))
        else:
            model = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_depth=3,
                                                  min_samples_leaf=8, l2_regularization=1.0)
        model.fit(T.loc[train, cols], T.loc[train, "_t"])
        pred[~train] = model.predict(T.loc[~train, cols])
    return pred


def r1(v):
    return None if v is None or not np.isfinite(v) else round(float(v), 1)


def metrics(T, pred):
    ok = pred.notna()
    T, err = T[ok], (pred - T._t)[ok]
    flood = np.maximum(T._y, T._y + T._t) >= FLOOD_CM
    rise = T._t >= RISE_CM
    peaks = {}
    for event_id, g in T.groupby("_e"):
        target_level = g._y + g._t
        if target_level.max() >= FLOOD_CM:
            peaks[event_id] = r1(err[target_level.idxmax()])
    return {
        "eventos": sorted(T._e.unique()), "n_horas_cheia": int(flood.sum()), "n_horas_subida": int(rise.sum()),
        "mae_cheia_cm": r1(err[flood].abs().mean()), "mae_subida_cm": r1(err[rise].abs().mean()),
        "vies_subida_cm": r1(err[rise].mean()),
        "erro_abs_medio_pico_cm": r1(np.mean([abs(v) for v in peaks.values()])) if peaks else None,
        "erro_pico_por_evento_cm": peaks,
    }


CANDIDATES = {
    "chuva observada media da bacia (3/6/12/24/48h)": ["RAIN"],
    "chuva observada por sub-bacia (5 zonas)": ["RZONE"],
    "nivel Santa Tereza 86472600": ["STZ"],
    "Rio da Prata: Balsa do Prata 86447000": ["PRATA"],
    "Rio Carreiro: Passo Carreiro 86500000": ["CARR"],
    "Santa Tereza + chuva media": ["STZ", "RAIN"],
    "Balsa do Prata + chuva media": ["PRATA", "RAIN"],
}


def feature_cols(T):
    return [c for c in T.columns if not c.startswith("_")]


def main():
    base_groups = ["M", "LJJ"]
    results, rain_ceiling = [], []
    for h in HORIZONS:
        base_cols = feature_cols(table(base_groups, h))
        for name, groups in CANDIDATES.items():
            T = table(base_groups + groups, h)
            if T is None or T._e.nunique() < 3:
                continue
            for kind in ("ridge", "hgb"):
                b = metrics(T, leave_one_event_out(T, base_cols, kind))
                a = metrics(T, leave_one_event_out(T, feature_cols(T), kind))
                results.append({
                    "horizonte_h": h, "modelo": kind, "candidato": name, "eventos": a["eventos"],
                    "baseline": b, "com_candidato": a,
                    "ganho_cheia_pct": r1(100 * (1 - a["mae_cheia_cm"] / b["mae_cheia_cm"])),
                    "ganho_subida_pct": r1(100 * (1 - a["mae_subida_cm"] / b["mae_subida_cm"])),
                })
        # Teto da chuva prevista: soma a chuva futura observada (previsao perfeita).
        T = table(base_groups + ["RAIN"], h, future_rain=True)
        cols = feature_cols(T)
        rain_ceiling.append({
            "horizonte_h": h,
            "baseline": metrics(T, leave_one_event_out(T, base_cols, "ridge")),
            "com_chuva_observada": metrics(T, leave_one_event_out(T, [c for c in cols if c != "fut"], "ridge")),
            "com_chuva_observada_e_futura_perfeita": metrics(T, leave_one_event_out(T, cols, "ridge")),
        })
        print(f"{h}h concluido", flush=True)
    inventory = [{
        "evento": e, "pico_mucum_cm": r1(df[M].max()), "horas_acima_500cm": int((df[M] >= FLOOD_CM).sum()),
        "tem": {"linha_jose_julio": bool(df[J].notna().sum() > 24), "santa_tereza": bool(df[S].notna().sum() > 24),
                "balsa_do_prata": bool(df[P].notna().sum() > 24), "passo_carreiro": bool(df[C].notna().sum() > 24),
                "chuva": "rain" in df},
    } for e, df in EVENTS.items()]
    payload = {
        "schema_version": "mucum_flood_input_screening_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "research_only": True,
        "aviso": "Triagem de pesquisa. Nao altera o robo ao vivo nem constitui alerta.",
        "criterios": {"cheia_cm": FLOOD_CM, "subida_cm_no_horizonte": RISE_CM,
                      "pico": "previsao emitida h horas antes do pico do evento",
                      "validacao": "deixa um evento inteiro de fora", "baseline": "Mucum + Linha Jose Julio"},
        "limitacoes": [
            "Chuva testada em 6 eventos (2 de 2023 + 4 de 2026); Santa Tereza e Passo Carreiro so nos 4 de 2026.",
            "Balsa do Prata tem cobertura irregular nas cheias historicas; resultado inconclusivo.",
            "O erro de pico e uma unica previsao por evento: leitura qualitativa.",
        ],
        "eventos": inventory,
        "resultados": results,
        "teto_chuva_prevista": rain_ceiling,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=lambda o: o.item()) + "\n", encoding="utf-8")
    print(f"gravado {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
