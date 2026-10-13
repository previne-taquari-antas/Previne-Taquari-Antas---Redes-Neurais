"""Figura diagnóstica das grades nativas; não ajusta séries nem escolhe parâmetros."""
import argparse
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from comparar_rs122 import ler, medidas, RECORTES, stamp, recortar, RUN, COMMIT


def data(t):
    return datetime(1899, 12, 31) + timedelta(minutes=t)


def maximos_locais(series):
    ts = sorted(series)
    candidates = [t for i, t in enumerate(ts[1:-1], 1)
                  if series[t] > series[ts[i - 1]] and series[t] >= series[ts[i + 1]]]
    maximum = max(series.values())
    return [{"data_hora_local": data(t).isoformat(), "q_m3s": series[t],
             "distancia_do_maximo_pct": 100 * (maximum - series[t]) / maximum if maximum else 0}
            for t in sorted(candidates, key=series.get, reverse=True)[:5]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comparacao", type=Path, required=True)
    ap.add_argument("--artefatos", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    a = ap.parse_args()
    if a.saida.exists():
        raise ValueError("Figura exige pasta nova")
    comparison = json.loads(a.comparacao.read_text(encoding="utf-8"))
    if not comparison["gates"]["A_reproduz_exatamente"] or not comparison["gates"]["soma_filhos_passou"]:
        raise ValueError("Controles de reprodução/conservação não passaram")
    out = {"run_id": RUN, "commit_hec": COMMIT,
           "comparacao_sha256": hashlib.sha256(a.comparacao.read_bytes()).hexdigest(),
           "codigo_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           "maximos_locais": [], "diferencas_grade_comum": [],
           "limites": ["Máximos locais sem pareamento de ondas e sem tolerância de quase empate",
                       "Diferença de grades inclui piso interno de Tc do HEC",
                       "Não altera a reprovação do gate temporal nem avalia erro contra observado"]}
    cache = {}
    for sim in RECORTES:
        for dt, arm in ((10, "A"), (5, "A"), (1, "A"), (1, "B0"), (1, "B1")):
            path = a.artefatos / f"rs122-{sim}-{dt}min" / arm / "projeto/vazao.csv"
            ex = comparison["fontes_execucoes"][sim + "/" + str(dt)]
            if ex["run_id"] != RUN or ex["codigo_commit"] != COMMIT or hashlib.sha256(path.read_bytes()).hexdigest() != ex["bracos"][arm]["vazao_sha256"]:
                raise ValueError("Figura não corresponde ao lote comparado")
            cache[sim, dt, arm] = ler(path)
        event, ini, fim = RECORTES[sim]
        bounds = (stamp(ini), stamp(fim))
        for node in ("J_211", "J_201"):
            for dt in (10, 5, 1):
                s = recortar(cache[sim, dt, "A"][node], bounds)
                out["maximos_locais"].append({"evento": event, "node": node, "passo_min": dt,
                                             "top5_sem_agrupamento_de_ondas": maximos_locais(s)})
            s5, s1 = [recortar(cache[sim, dt, "A"][node], bounds) for dt in (5, 1)]
            if not set(s5) <= set(s1):
                raise ValueError("Grade de 1 min não contém os instantes da grade de 5 min")
            diffs = [s1[t] - q for t, q in s5.items()]
            out["diferencas_grade_comum"].append({"evento": event, "node": node,
                                                "max_abs_m3s": max(map(abs, diffs)),
                                                "rmse_entre_simulacoes_m3s": (sum(d*d for d in diffs)/len(diffs))**.5,
                                                "n_instantes": len(diffs)})
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 3, figsize=(15, 7.8))
    colors = {"A5": "#727272", "A1": "#1f77b4", "B0": "#8a67b4", "B1": "#d55e00"}
    for row, sim in enumerate(RECORTES):
        event, ini, fim = RECORTES[sim]
        bounds = (stamp(ini), stamp(fim))
        panels = [("J_RS122", "RS-122: área contribuinte corrigida", ((1, "B0", "B0"), (1, "B1", "B1"))),
                  ("J_201", "Muçum: efeito da divisão lateral", ((1, "B0", "B0"), (1, "B1", "B1"))),
                  ("J_211", "Castro Alves: sensibilidade ao passo", ((5, "A", "A5"), (1, "A", "A1")))]
        for col, (node, title, curves) in enumerate(panels):
            ax = axes[row, col]
            reference = recortar(cache[sim, 1, curves[-1][1]][node], bounds)
            peak = medidas(reference)["pico_inicio_hec_min"]
            zoom = (max(bounds[0], peak - 12*60), min(bounds[1], peak + 12*60))
            for dt, arm, color in curves:
                s = recortar(cache[sim, dt, arm][node], bounds)
                ts = [t for t in sorted(s) if zoom[0] <= t <= zoom[1]]
                ax.plot([data(t) for t in ts], [s[t] for t in ts], color=colors[color],
                        lw=1.9 if arm != "B1" else 1.4, linestyle="--" if arm == "B1" else "-",
                        label=f"{arm} · {dt} min")
                m = medidas(s)
                ax.scatter(data(m["pico_inicio_hec_min"]), m["pico_m3s"], color=colors[color], s=24, zorder=3)
            ax.set_title(f"{event} — {title}", loc="left", fontsize=10.5)
            ax.set_ylabel("Vazão simulada (m³/s)")
            ax.grid(alpha=.2)
            ax.legend(frameon=False, fontsize=9)
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m\n%H:%M"))
            if col == 1:
                d = next(r for r in comparison["pares"] if r["recorte"] == event and r["passo_min"] == 1 and r["node"] == node and r["comparacao"] == "B1-B0")
                ax.text(.03, .04, f"B1−B0: Δpico {d['delta_pico_m3s']:+.3f} m³/s; Δt {d['delta_instante_min']:+d} min", transform=ax.transAxes, fontsize=8.5)
    fig.suptitle("HEC-HMS — diagnóstico RS-122 e repercussão em Muçum\nEventos históricos de 2023 · grades nativas · máximos marcados", fontsize=16, y=.98)
    fig.text(.02, .018, "A: modelo original. B0: divide calha. B1: divide calha e reposiciona a área lateral, herdando chuva e resposta.\nRecortes visuais de ±12 h do máximo de referência. Convergência temporal reprovada; os gráficos não são previsão nem validação contra observado.", fontsize=9)
    fig.tight_layout(rect=(0, .07, 1, .9))
    a.saida.mkdir(parents=True)
    fig.savefig(a.saida / "diagnostico_rs122.png", dpi=170)
    plt.close(fig)
    (a.saida / "diagnostico_picos.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out["diferencas_grade_comum"]))


if __name__ == "__main__":
    main()
