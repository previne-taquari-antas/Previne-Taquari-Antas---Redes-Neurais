"""Recalibração do titular com a chuva v4 (todos os postos), 19/11/2026. Mesmo protocolo da linha que gerou pc-f8-c025
(README da branch cursor/hec-bacia145-perda-cheia): família lrdcf, objetivo J_pico, 17 janelas de calibração,
g0 = 48 vizinhos de pc-f8-c025 (raio 0,15; o candidato 0 é o próprio pc-f8-c025 com a chuva nova) + 6 gerações de ES
(λ 48, μ 8), e no fim a validação dos 5 melhores + pc-f8-c025 em todas as janelas menos a de teste.
Só a chuva muda (forcamento_v4). Escolha só pela calibração; a validação é só relato.

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
RES = Path(r"D:\PREVINE\hec_calibracao_20261005\resultados_v4")
BRANCH = "claude/hec-bacia145-chuva-v4"
REPO = "previne-taquari-antas/Previne-Taquari-Antas---Redes-Neurais"
CENTRO = RES / "centro_pc-f8-c025.json"
SIGMAS = [0.15, 0.13, 0.11, 0.10, 0.08, 0.07]
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
    sh([PY, "rodada_dc.py", *args, "--familia", "lrdcf", "--objetivo", "J_pico", "--forcamento", "forcamento_v4",
        "--saida", str(PED)], cwd=COD)


def enviar(rodada):
    sh(["git", "add", str(PED)])
    sh(["git", "commit", "-q", "-m", f"chuva v4 (todos os postos): rodada {rodada}"])
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
    rodada("v4-g0", ["viz", "--centro", f"{CENTRO}:pc-f8-c025", "--raio", "0.15", "--n", "48", "--semente", "41"])
    for g, s in enumerate(SIGMAS, start=1):
        rodada(f"v4-g{g}", ["es", "--resultados", str(RES), "--lam", "48", "--mu", "8", "--sigma", str(s),
                            "--semente", str(400 + g)])
    # validação: 5 melhores da calibração + o próprio pc-f8-c025 (candidato v4-g0-c000) em todas as janelas
    if not (RES / "v4-val" / "resultado.json").exists():
        gerar(["top", "--rodada", "v4-val", "--resultados", str(RES), "--n", "5", "--janelas", JANELAS_VAL])
        p = json.loads(PED.read_text(encoding="utf-8"))
        c0 = next(c for c in json.loads((RES / "v4-g0" / "resultado.json").read_text(encoding="utf-8"))
                  if c["id"] == "v4-g0-c000")
        if all(c["p"] != c0["p"] for c in p["candidatos"]):
            p["candidatos"].append({"id": f"v4-val-c{len(p['candidatos']):03d}", "rota": "mc", "p": c0["p"]})
            p["familias"]["lrdcf"]["ate"] = len(p["candidatos"]) - 1
        p["nota"] = "último candidato = pc-f8-c025 com a chuva v4 (controle)"
        PED.write_text(json.dumps(p, indent=1), encoding="utf-8")
        sha = enviar("v4-val")
        rid, concl = esperar(sha)
        if concl != "success":
            raise SystemExit(f"v4-val: run {rid} terminou {concl}")
        baixar(rid, "v4-val")
    print("concluído", flush=True)


if __name__ == "__main__":
    main()
