#!/usr/bin/env python3
"""Triagem de inputs candidatos para a previsao de nivel de Mucum (4h, 8h, 12h).

Pergunta: quais sinais da bacia, alem dos que o ao vivo ja usa (Mucum +
Linha Jose Julio), reduzem o erro da previsao de Mucum em 4, 8 e 12 horas?

Metodo (somente pesquisa, nada aqui altera o robo ao vivo):
  1. Base horaria observada de todas as estacoes a montante de Mucum
     (mucum_observed_multistation_*), mais chuva areal por sub-bacia.
  2. Baseline = mesmas estacoes do ao vivo de 4h (Mucum + Linha Jose Julio),
     re-treinado com gradient boosting, alvo = variacao do nivel em h horas.
  3. Cada candidato e somado ao baseline e avaliado em validacao cruzada por
     blocos de tempo (cada cheia fica inteira em um unico bloco), comparando
     o erro nas MESMAS horas.
  4. Selecao gulosa dos grupos que somam ganho, por horizonte.
  5. Diagnosticos de dinamica: defasagem ate Mucum por regime (aguas baixas
     x cheia), amplitude diaria por operacao de usinas e comparacao pareada
     com o historico conferido do ao vivo.

Limites: ~51 dias de dados e duas cheias; a selecao gulosa usa a mesma
validacao que reporta, entao os ganhos combinados sao levemente otimistas.
Estacoes de PCH/UHE tem ~45% de lacunas nesta base (coleta rotativa).

Requer: pandas, scikit-learn (scripts/requirements_ai_lab_shadow.txt).
Uso:    python scripts/screen_mucum_input_candidates.py
"""
from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "assets/data/estudo_bacia_taquari_antas"
FLOW_CSV = BASE / "mucum_observed_multistation_flow_hourly.csv"
RAIN_CSV = BASE / "mucum_observed_multistation_rain_hourly.csv"
LIVE_HISTORY = ROOT / "historico_previsoes_ao_vivo_mucum.json"
OUT = ROOT / "assets/data/research_mucum_input_screening_latest.json"

TARGET = "86510000"   # Mucum
LJJ = "86472000"      # Linha Jose Julio (Rio das Antas)
STZ = "86472600"      # Santa Tereza (Rio Taquari)
HORIZONS = (4, 8, 12)
FLOOD_CM = 400.0      # separa regime de cheia do regime de aguas baixas
# Blocos de validacao: cada cheia fica inteira dentro de um bloco.
FOLDS = [
    ("2026-09-26", "2026-10-02 23:00"),
    ("2026-10-03", "2026-10-07 23:00"),
    ("2026-10-08", "2026-10-14 23:00"),
    ("2026-10-15", "2026-10-31 23:00"),
    ("2026-11-01", "2026-11-08 23:00"),
    ("2026-11-09", "2026-11-16 23:00"),
]
RAIN_ZONES = {
    "INC_MUCUM": "subbasin_SB_INC_MUCUM_mm",
    "CARREIRO": "subbasin_SB_CARREIRO_7866_mm",
    "STZ_RESIDUAL": "subbasin_SB_STZ_RESIDUAL_mm",
    "PRATA": "subbasin_SB_PRATA_7868_mm",
    "ANTAS_RESIDUAL": "subbasin_SB_ANTAS_RESIDUAL_mm",
}


def load():
    flow = pd.read_csv(FLOW_CSV, dtype={"code": str}, parse_dates=["time_local"])
    level = flow.pivot_table(index="time_local", columns="code", values="level", aggfunc="last")
    discharge = flow.pivot_table(index="time_local", columns="code", values="flow_m3s", aggfunc="last")
    idx = pd.date_range(level.index.min(), level.index.max(), freq="h")
    # Lacunas de ate 2h sao interpoladas apenas para a triagem; o resto fica ausente.
    level = level.reindex(idx).interpolate(limit=2, limit_area="inside")
    discharge = discharge.reindex(idx).interpolate(limit=2, limit_area="inside")
    meta = flow.drop_duplicates("code").set_index("code")[["name", "upg"]]
    rain = pd.read_csv(RAIN_CSV, parse_dates=["time_local"]).set_index("time_local").reindex(idx)
    return level, discharge, meta, rain


L, Q, META, RAIN = load()
Y = L[TARGET]
FOLD = pd.Series(-1, index=L.index)
for _i, (_a, _b) in enumerate(FOLDS):
    FOLD.loc[_a:_b] = _i
FLOOD = (Y >= FLOOD_CM) | (Y.shift(-12) >= FLOOD_CM)


def diff(x, k):
    return x - x.shift(k)


def accel(x, k):
    return (x - x.shift(k)) - (x.shift(k) - x.shift(2 * k))


def station_features(code, ks=(2, 4, 8, 12), source=None, prefix=""):
    x = (L if source is None else source)[code]
    out = {f"{prefix}n_{code}": x}
    for k in ks:
        out[f"{prefix}d{k}_{code}"] = diff(x, k)
    return pd.DataFrame(out)


def rain_features(columns, ks=(3, 6, 12, 24)):
    out = {}
    for col in columns:
        for k in ks:
            out[f"{col}_{k}h"] = RAIN[col].rolling(k, min_periods=max(1, k // 2)).sum()
    return pd.DataFrame(out)


def baseline_features():
    """Mesmas estacoes do ao vivo de 4h: Mucum + Linha Jose Julio."""
    out = {"n_M": Y}
    for k in (1, 2, 4, 8, 12):
        out[f"d{k}_M"] = diff(Y, k)
        out[f"a{k}_M"] = accel(Y, k)
    x = L[LJJ]
    out["n_LJJ"] = x
    for k in (1, 2, 4, 8):
        out[f"d{k}_LJJ"] = diff(x, k)
    for k in (4, 12, 20):
        out[f"a{k}_LJJ"] = accel(x, k)
    return pd.DataFrame(out)


def cv_error(X, h):
    """Erro (previsto - observado) fora da amostra, deixando um bloco de fora por vez."""
    target = Y.shift(-h) - Y
    valid = target.notna() & Y.notna() & (FOLD >= 0)
    pred = pd.Series(np.nan, index=Y.index)
    for i in range(len(FOLDS)):
        train, test = valid & (FOLD != i), valid & (FOLD == i)
        if not test.any():
            continue
        model = HistGradientBoostingRegressor(
            max_iter=250, learning_rate=0.05, max_depth=3, min_samples_leaf=8, l2_regularization=1.0
        )
        model.fit(X[train], target[train])
        pred[test] = model.predict(X[test])
    return pred - target


def r1(value):
    return None if value is None or not np.isfinite(value) else round(float(value), 1)


def summary(err, mask=None):
    m = err.notna() if mask is None else (err.notna() & mask)
    return {
        "n": int(m.sum()),
        "mae_cm": r1(err[m].abs().mean()),
        "mae_cheia_cm": r1(err[m & FLOOD].abs().mean()),
        "mae_aguas_baixas_cm": r1(err[m & ~FLOOD].abs().mean()),
        "p90_cm": r1(err[m].abs().quantile(0.9)),
        "mae_por_bloco_cm": [r1(err[m & (FOLD == i)].abs().mean()) for i in range(len(FOLDS))],
    }


def usable_stations():
    out = []
    for code in L.columns:
        if code in (TARGET, LJJ):
            continue
        spread = L[code].quantile(0.99) - L[code].quantile(0.01)
        if 20 < spread < 3000:  # descarta sensor parado e cota de reservatorio com salto espurio
            out.append(code)
    return out


def candidate_library():
    cands = {}
    for code in usable_stations():
        cands[f"nivel {code} {META.name[code]} [{META.upg[code]}]"] = station_features(code)
    for code in (LJJ, "86500000", "86447000", "86450000", "86450500", "86470900"):
        if Q[code].notna().sum() > 400:
            cands[f"vazao {code} {META.name[code]}"] = station_features(code, source=Q, prefix="q")
    for zone, col in RAIN_ZONES.items():
        cands[f"chuva observada sub-bacia {zone}"] = rain_features([col])
    cands["chuva observada media da bacia"] = rain_features(["basin_mean_mm"])
    hour = pd.Series(L.index.hour, index=L.index)
    cands["hora do dia (sen/cos)"] = pd.DataFrame(
        {"h_sin": np.sin(2 * np.pi * hour / 24), "h_cos": np.cos(2 * np.pi * hour / 24)}
    )
    return cands


def screen(base_X, base_err):
    """Ganho de cada candidato isolado sobre o baseline, nas mesmas horas."""
    rows = []
    cands = candidate_library()
    for h in HORIZONS:
        extra = {
            "Mucum ontem na mesma janela (t-24 -> t+h-24)": pd.DataFrame(
                {"m24": Y.shift(24 - h) - Y.shift(24), "m24_nivel": Y.shift(24 - h)}
            )
        }
        for name, feats in {**cands, **extra}.items():
            err = cv_error(pd.concat([base_X, feats], axis=1), h)
            have = feats.notna().any(axis=1) & base_err[h].notna() & err.notna()
            if have.sum() < 250:
                continue
            b, a = base_err[h][have].abs().mean(), err[have].abs().mean()
            row = {"horizonte_h": h, "candidato": name, "n_horas": int(have.sum()),
                   "mae_baseline_cm": r1(b), "mae_com_candidato_cm": r1(a), "ganho_pct": r1(100 * (1 - a / b))}
            for label, reg in (("cheia", FLOOD), ("aguas_baixas", ~FLOOD)):
                m = have & reg
                row[f"ganho_{label}_pct"] = (
                    r1(100 * (1 - err[m].abs().mean() / base_err[h][m].abs().mean())) if m.sum() > 80 else None
                )
            blocks = [i for i in range(len(FOLDS)) if (have & (FOLD == i)).sum() > 20]
            row["blocos_melhores"] = int(sum(
                err[have & (FOLD == i)].abs().mean() < base_err[h][have & (FOLD == i)].abs().mean() for i in blocks
            ))
            row["blocos_avaliados"] = len(blocks)
            rows.append(row)
        print(f"triagem {h}h concluida", flush=True)
    return rows


def greedy_groups():
    hour = pd.Series(L.index.hour, index=L.index)
    return {
        "nivel Santa Tereza 86472600": station_features(STZ, ks=(1, 2, 4, 8)),
        "chuva observada media da bacia (3/6/12/24h)": rain_features(["basin_mean_mm"]),
        "chuva observada por sub-bacia (5 zonas)": rain_features(list(RAIN_ZONES.values())),
        "Rio da Prata: Balsa do Prata 86447000": station_features("86447000"),
        "Rio da Prata: PCH Jararaca 86125500": station_features("86125500"),
        "Rio da Prata: PCH Morro Grande Jusante 2 86125130": station_features("86125130"),
        "Rio Carreiro: vazao Passo Carreiro 86500000": station_features("86500000", source=Q, prefix="q"),
        "Rio Carreiro: Cotipora/Dois Lajeados 86507220": station_features("86507220"),
        "UHE Monte Claro Jusante 1 86450000": station_features("86450000"),
        "UHE Monte Claro Jusante 2 86450500": station_features("86450500"),
        "vazao Linha Jose Julio 86472000": station_features(LJJ, source=Q, prefix="q"),
        "hora do dia (sen/cos)": pd.DataFrame(
            {"h_sin": np.sin(2 * np.pi * hour / 24), "h_cos": np.cos(2 * np.pi * hour / 24)}
        ),
    }


def greedy(base_X, base_err, max_steps=5, min_gain=0.015):
    groups, result, final_err = greedy_groups(), {}, {}
    for h in HORIZONS:
        current, best, chosen, steps = base_X, base_err[h].abs().mean(), [], []
        final_err[h] = base_err[h]
        for _ in range(max_steps):
            trials = {n: cv_error(pd.concat([current, f], axis=1), h) for n, f in groups.items() if n not in chosen}
            name = min(trials, key=lambda n: trials[n].abs().mean())
            mae = trials[name].abs().mean()
            if mae > best * (1 - min_gain):
                break
            chosen.append(name)
            current, best, final_err[h] = pd.concat([current, groups[name]], axis=1), mae, trials[name]
            steps.append({"adicionado": name, **summary(trials[name])})
        result[str(h)] = {"baseline": summary(base_err[h]), "passos": steps, "conjunto_final": chosen,
                          "reducao_mae_pct": r1(100 * (1 - best / base_err[h].abs().mean()))}
        print(f"selecao {h}h: {chosen}", flush=True)
    return result, final_err


def regime_lags():
    """Defasagem (h) que maximiza a correlacao entre variacoes de 2h da estacao e de Mucum."""
    stations = [STZ, LJJ, "86470900", "86450500", "86450000", "86447000", "86125500", "86500000"]
    low, high = Y < FLOOD_CM, Y >= 450

    def best(x, regime):
        dx, scores = diff(x, 2), []
        for lag in range(0, 21):
            dy = diff(Y, 2).shift(-lag)
            m = dx.notna() & dy.notna() & regime
            scores.append(np.corrcoef(dx[m], dy[m])[0, 1] if m.sum() >= 120 else np.nan)
        arr = np.array(scores)
        if np.all(np.isnan(arr)):
            return None
        i = int(np.nanargmax(arr))
        return {"defasagem_h": i, "corr": round(float(arr[i]), 2)}

    return [{"codigo": c, "nome": META.name[c], "aguas_baixas": best(L[c], low), "cheia": best(L[c], high)}
            for c in stations]


def hydropeaking():
    low = Y[Y < FLOOD_CM]
    amp = low.resample("D").agg(lambda s: s.max() - s.min() if s.notna().sum() >= 18 else np.nan).dropna()
    return {"dias_avaliados": int(len(amp)), "amplitude_diaria_mediana_cm": r1(amp.median()),
            "dias_com_amplitude_acima_80cm": int((amp > 80).sum()),
            "nota": "oscilacao diaria de Mucum em aguas baixas, sem chuva: operacao das usinas a montante"}


def live_comparison(base_err, final_err):
    """Mesmos instantes do historico conferido do ao vivo x modelos desta triagem."""
    if not LIVE_HISTORY.exists():
        return []
    hist = pd.DataFrame(json.loads(LIVE_HISTORY.read_text(encoding="utf-8"))["registros"])
    hist = hist[hist.status_auditoria == "conferido"].copy()
    hist["t"] = pd.to_datetime(hist.hora_modelo)
    out = []
    for label, h in (("4h", 4), ("8h", 8)):
        x = hist[hist.horizonte == label].drop_duplicates("t").set_index("t")
        b, f = base_err[h].reindex(x.index), final_err[h].reindex(x.index)
        m = b.notna() & f.notna()
        for regime, mask in (("todos", m), ("aguas_baixas_<400cm", m & (x.nivel_modelo_cm < FLOOD_CM)),
                             ("cheia_>=400cm", m & (x.nivel_modelo_cm >= FLOOD_CM))):
            out.append({"horizonte": label, "modelo_ao_vivo": x.modelo.iloc[0], "regime": regime, "n": int(mask.sum()),
                        "mae_ao_vivo_cm": r1(x.erro_abs_cm[mask].mean()),
                        "mae_baseline_retreinado_cm": r1(b[mask].abs().mean()),
                        "mae_conjunto_proposto_cm": r1(f[mask].abs().mean()),
                        "mae_persistencia_cm": r1((x.observado_cm - x.nivel_modelo_cm)[mask].abs().mean())})
    return out


def main():
    base_X = baseline_features()
    base_err = {h: cv_error(base_X, h) for h in HORIZONS}
    print({h: summary(base_err[h])["mae_cm"] for h in HORIZONS}, flush=True)
    rows = screen(base_X, base_err)
    sets, final_err = greedy(base_X, base_err)
    payload = {
        "schema_version": "mucum_input_screening_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "research_only": True,
        "aviso": "Triagem de pesquisa. Nao altera o robo ao vivo nem constitui alerta.",
        "dados": {"inicio": str(L.index.min()), "fim": str(L.index.max()), "horas": int(len(L)),
                  "estacoes_com_nivel": int(L.shape[1]), "fonte_nivel": str(FLOW_CSV.relative_to(ROOT)),
                  "fonte_chuva": str(RAIN_CSV.relative_to(ROOT))},
        "metodo": {"alvo": "variacao do nivel de Mucum em h horas", "modelo": "HistGradientBoostingRegressor",
                   "baseline": "Mucum + Linha Jose Julio (niveis, variacoes e aceleracoes)",
                   "validacao": "deixa-um-bloco-de-fora", "blocos": FOLDS, "limiar_cheia_cm": FLOOD_CM},
        "limitacoes": [
            "Cerca de 51 dias de dados e duas cheias; confirmar com eventos historicos antes de promover.",
            "A selecao gulosa usa a mesma validacao que reporta: ganho combinado levemente otimista.",
            "Estacoes de PCH/UHE tem ~45% de lacunas nesta base (coleta rotativa), o que subestima o potencial delas.",
            "Latencia em tempo real de cada estacao candidata ainda precisa ser medida no robo.",
        ],
        "operacao_usinas_aguas_baixas": hydropeaking(),
        "defasagem_ate_mucum_por_regime": regime_lags(),
        "ao_vivo_x_triagem_mesmos_instantes": live_comparison(base_err, final_err),
        "conjuntos_recomendados": sets,
        "triagem_candidatos": sorted(rows, key=lambda r: (r["horizonte_h"], -(r["ganho_pct"] or -999))),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=lambda o: o.item()) + "\n", encoding="utf-8")
    print(f"gravado {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
