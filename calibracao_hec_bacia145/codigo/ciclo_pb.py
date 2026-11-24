"""Linha percolação baixa (24/11/2026, Claude): famílias lrdcfb e lrdcfvb (estrutura_v3), chuva v4, objetivo J_pico,
as mesmas 17 janelas de calibração da linha v4 (comparável com v4-g4-c024, J_pico 4,875, e pc-f8-c025, 4,958).
g0 = 48 por família perto de pc-f8-c025 (sem o centro, raio 0,25; perc, dmax, k1, p1, mr e os do Clark variável na faixa toda)
+ 8 gerações de ES por família (λ 48, μ 8); validação dos 5 melhores de cada família + pc-f8-c025 (controle).
Pré-registro em ESTADO_ATUAL §0e. Escolha só pela calibração; a validação é só relato.

Roda no GitHub (push do PEDIDO.json na branch claude/hec-bacia145-chuva-v4); o PC só espera e baixa resultados.
Uso: python ciclo_v4.py            (retoma de onde parou: pula as gerações que já têm resultado.json)
"""
import json
import subprocess
import sys
import time
from pathlib import Path

WT = Path(r"D:\PREVINE\worktrees\hec-bacia145-chuva-v4")
COD = WT / "calibracao_hec_bacia145" / "codigo"
PED = WT / "calibracao_hec_bacia145" / "rodadas" / "PEDIDO.json"
RES = Path(r"D:\PREVINE\hec_calibracao_20261005\resultados_pb")
CENTRO_DIR = Path(r"D:\PREVINE\hec_calibracao_20261005\resultados_v4")
BRANCH = "claude/hec-bacia145-chuva-v4"
REPO = "previne-taquari-antas/Previne-Taquari-Antas---Redes-Neurais"
CENTRO = CENTRO_DIR / "centro_pc-f8-c025.json"
FAM = "lrdcfb,lrdcfvb"
SIGMAS = [0.15, 0.13, 0.12, 0.11, 0.10, 0.09, 0.08, 0.07]
PY = sys.executable
JANELAS_VAL = ("S2023_07,S2023_09,S2023_10,S2023_11,S2024_05,S2024_06,S2025_06,S2026_07,X20180721,X20180821,X20180828,"
               "X20180928,X20181028,X20190525,X20191027,X20200626,X20200809,X20210125,X20210525,X20210622,X20220428,"
               "X20220525,X20220614,X20230611,X20230913,X20231028,X20231124,X20241006,X20250918,X20251104,X20260629,"
               "X20260809,X20260827")   # todas menos a de teste (X20260918), como no pc-valb do Cursor


def sh(cmd, cwd=WT, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode:
        raise RuntimeError(f"{cmd}\n{r.stdout}\n{r.stderr}")
    return r.stdout.strip()


def gerar(args):
    sh([PY, "rodada_dc.py", *args, "--familia", FAM, "--objetivo", "J_pico", "--forcamento", "forcamento_v4",
        "--saida", str(PED)], cwd=COD)


def enviar(rodada):
    sh(["git", "add", str(PED)])
    sh(["git", "commit", "-q", "-m", f"percolação baixa (lrdcfb/lrdcfvb, chuva v4): rodada {rodada}"])
    sh(["git", "push", "-q", "origin", BRANCH])
    return sh(["git", "rev-parse", "HEAD"])


def esperar(sha):
    while True:
        runs = json.loads(sh(["gh", "run", "list", "-R", REPO, "--branch", BRANCH, "--limit", "10", "--json",
                              "databaseId,headSha,status,conclusion,workflowName"]))
        r = next((x for x in runs if x["headSha"] == sha and "lote" in x["workflowName"].lower()), None)
        if r and r["status"] == "completed":
            return r["databaseId"], r["conclusion"]
        time.sleep(90)


def baixar(rid, rodada):
    d = RES / rodada
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "resultado.json").exists():
        sh(["gh", "run", "download", str(rid), "-R", REPO, "-n", f"resultado-{rodada}", "-D", str(d)])
    R = json.loads((d / "resultado.json").read_text(encoding="utf-8"))
    ok = sorted((c for c in R if c.get("J_pico") is not None and c["J_pico"] < 1e9), key=lambda c: c["J_pico"])
    print(f"{rodada}: {len(ok)}/{len(R)} válidos; melhor {ok[0]['id']} J_pico {ok[0]['J_pico']:.3f} J {ok[0]['J']:.3f}",
          flush=True)
    return R


def rodada(nome, args):
    if (RES / nome / "resultado.json").exists():
        print(nome, "já feito", flush=True)
        return
    gerar(["--rodada", nome, *args])
    sha = enviar(nome)
    print(nome, "enviado", sha[:10], flush=True)
    rid, concl = esperar(sha)
    if concl != "success":
        raise SystemExit(f"{nome}: run {rid} terminou {concl}")
    baixar(rid, nome)


def main():
    RES.mkdir(exist_ok=True)
    rodada("pb-g0", ["viz", "--centro", f"{CENTRO}:pc-f8-c025", "--raio", "0.25", "--n", "48", "--semente", "61",
                     "--livres", "perc,dmax,k1,p1,mr", "--sem-centro"])
    for g, s in enumerate(SIGMAS, start=1):
        rodada(f"pb-g{g}", ["es", "--resultados", str(RES), "--lam", "48", "--mu", "8", "--sigma", str(s),
                            "--semente", str(600 + g)])
    if not (RES / "pb-val" / "resultado.json").exists():
        gerar(["top", "--rodada", "pb-val", "--resultados", str(RES), "--n", "5", "--janelas", JANELAS_VAL])
        p = json.loads(PED.read_text(encoding="utf-8"))
        c0 = json.loads(CENTRO.read_text(encoding="utf-8"))
        c0 = next(c for c in c0 if c["id"] == "pc-f8-c025")
        p["candidatos"].append({"id": f"pb-val-c{len(p['candidatos']):03d}", "rota": "mc", "p": c0["p"]})
        p["nota"] = "último candidato = pc-f8-c025 (controle, chuva v4)"
        PED.write_text(json.dumps(p, indent=1), encoding="utf-8")
        sha = enviar("pb-val")
        rid, concl = esperar(sha)
        if concl != "success":
            raise SystemExit(f"pb-val: run {rid} terminou {concl}")
        baixar(rid, "pb-val")
    print("concluído", flush=True)


if __name__ == "__main__":
    main()
