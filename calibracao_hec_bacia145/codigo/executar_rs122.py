"""Runner isolado A/B0/B1. Diretórios novos; preserva DSS/logs e titular.

--preparar gera basin/chuva/manifesto sem iniciar HEC. Cada processo trata um
par janela/passo. Não usa rodar_lote (evita limpeza de pastas e caches prévios).
"""
import argparse
import gzip
import hashlib
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path

from variante_rs122 import adaptar, chuva_transferida, blocos, conferir_transferencia
from contrato_extracao import conferir_csv
from contrato_rs122 import conferir_fontes, conferir_horas, conferir_metadata


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--janela", choices=["S2023_07", "S2023_11"], required=True)
    ap.add_argument("--passo", type=int, choices=[10, 5, 1], required=True)
    ap.add_argument("--preparar", action="store_true")
    a = ap.parse_args()
    a.raiz, a.saida = a.raiz.resolve(), a.saida.resolve()
    if a.saida.exists():
        raise ValueError("Saída existente: não sobrescrever ou reutilizar cache")
    contrato_path = a.raiz / "experimentos/rs122/contrato.json"
    config = json.loads(contrato_path.read_text(encoding="utf-8"))
    snapshot_hash = conferir_fontes(a.raiz, config)
    if a.janela not in config["janelas"] or a.passo not in config["passos_min"]:
        raise ValueError("Janela/passo fora do contrato")
    pedido_path = a.raiz / config["parametros_origem"]
    if hashlib.sha256(pedido_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != config["pedido_sha256_lf"]:
        raise ValueError("PEDIDO não corresponde à referência congelada")
    pedido = json.loads(pedido_path.read_text(encoding="utf-8"))
    if len(pedido["candidatos"]) != 1 or pedido["forcamento"] != config["forcamento"]:
        raise ValueError("Contrato do titular mudou")
    candidate = pedido["candidatos"][0]
    if candidate["id"] != "dl-piloto-c000" or candidate["rota"] != "mc":
        raise ValueError("Titular esperado não encontrado")
    os.environ["HEC_BASIN_BASE"] = str(a.raiz / "dados/basin/a00_E27.basin")
    os.environ["HEC_MDT_CSV"] = str(a.raiz / "dados/mdt_trechos_atributos.csv")
    os.environ["HEC_MDT_SUB"] = str(a.raiz / "dados/mdt_subbacias_atributos.csv")
    # Catálogo de pesquisa e papéis congelados, sem depender do ambiente do shell.
    os.environ["HEC_CATALOGO"] = str(a.raiz / "dados/catalogo_ampliado.json")
    os.environ.pop("HEC_PAPEIS", None)
    a.saida.mkdir(parents=True)
    obsdir = a.saida / "dados_ana/csv"
    obsdir.mkdir(parents=True)
    obs_sources = {}
    for source in (a.raiz / "dados/observados").glob("*" + a.janela + ".csv.gz"):
        (obsdir / source.stem).write_bytes(gzip.decompress(source.read_bytes()))
        obs_sources[source.name] = digest(source)
    if not obs_sources:
        raise ValueError("Sem observados de inicialização")
    import comum
    comum.DADOS = obsdir.parent
    for key, value in pedido["papeis"].items():
        if key in comum.EVENTOS:
            comum.EVENTOS[key]["papel"] = value
    import hec
    import bacia_inteira as bi
    import estrutura_v3 as e3
    source = a.raiz / "dados" / config["forcamento"] / (a.janela + ".json.gz")
    forcing = json.loads(gzip.decompress(source.read_bytes()))
    cfg_sim = comum.SIMULACOES[a.janela]
    conferir_horas(forcing["horas"], cfg_sim["ini"], cfg_sim["fim"])
    base = e3.bacia_v3(candidate["p"], a.janela, "mc")
    # Gerar sempre o titular a 10 min: não mudar pisos de K junto com o passo.
    # O argumento dt_h da função original captura 10 min; passar explicitamente.
    from variante_rs122 import discretizar
    base, discretizacao = discretizar(base, a.passo, hec.passos_muskingum)
    hec.PASSO_MIN = a.passo
    initial = e3.q0_controles(a.janela)
    summary = {"status": "preparado" if a.preparar else "em_execucao", "janela": a.janela,
               "passo_min": a.passo, "config": config, "inicializacao_congelada": initial,
               "discretizacao": discretizacao, "parametros": candidate,
               "snapshot_fontes_sha256": snapshot_hash,
               "contrato_sha256": digest(contrato_path), "pedido_sha256": digest(pedido_path),
               "chuva_fonte_sha256": digest(source), "observados_fontes": obs_sources,
               "codigo_commit": os.environ.get("GITHUB_SHA"), "run_id": os.environ.get("GITHUB_RUN_ID"),
               "bracos": {}}
    report = a.saida / "execucao.json"
    report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    jobs = []
    for arm in config["bracos"]:
        folder = a.saida / arm
        folder.mkdir()
        text, metadata = adaptar(base, arm, config["geometria"])
        rain = chuva_transferida(forcing, arm)
        names = {n for n, (t, _) in blocos(text).items() if t == "Subbasin"}
        if names != set(rain["chuva_por_subbacia"]):
            raise ValueError("Chuva/basin incompatíveis")
        for vals in rain["chuva_por_subbacia"].values():
            if len(vals) != len(rain["horas"]) or not all(math.isfinite(v) and v >= 0 for v in vals):
                raise ValueError("Chuva inválida; não preencher")
        rain_dir = folder / "forcamento"
        rain_dir.mkdir()
        rain_path = rain_dir / (a.janela + ".json")
        rain_path.write_text(json.dumps(rain, ensure_ascii=False), encoding="utf-8")
        (folder / "bacia_preparada.basin").write_text(text, encoding="utf-8")
        metadata.update(chuva_sha256=digest(rain_path), basin_sha256=digest(folder / "bacia_preparada.basin"))
        metadata["transferencia"] = conferir_transferencia(base, text, forcing, json.loads(rain_path.read_text(encoding="utf-8")), arm)
        summary["bracos"][arm] = metadata
        report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        jobs.append((arm, folder, text, rain_dir, names, metadata))
    # Todos os basins/forçamentos passam pelo preflight antes da primeira JVM.
    for arm, folder, text, rain_dir, names, metadata in ([] if a.preparar else jobs):
        hec.FORC = rain_dir
        hec.BASIN_NAME = "Taquari-Antas 145 SB 105 R"  # nome técnico igual ao basin gerado
        required = sorted({v[1] for v in bi.CONTROLES.values()} | ({"SB_211", "R_211"} if arm == "A" else
                           {"R_211_UP", "R_211_DOWN", "J_RS122"} | ({"SB_211"} if arm == "B0" else {"SB_211_UP", "SB_211_DOWN"})))
        hec.NOS_EXTRA = required
        project = folder / "projeto"
        hec.escrever_projeto(project, a.janela, text, e3.tabelas_v3(candidate["p"], "mc"))
        met = (project / "chuva.met").read_text(encoding="utf-8")
        gage = (project / "proj.gage").read_text(encoding="utf-8")
        if set(re.findall(r"(?m)^Subbasin: (\S+)", met)) != names:
            raise ValueError("Met não representa todas as sub-bacias")
        if set(re.findall(r"(?m)^Gage: G_(\S+)", gage)) != names:
            raise ValueError("Gages não representam todas as sub-bacias")
        et_blocks = re.findall(r"(?ms)^Subbasin: (\S+)\n(.*?)^End:", met)
        if any("Begin Et: Monthly Evaporation" not in body for _, body in et_blocks):
            raise ValueError("ET ausente em filho ou controle")
        if len({body[body.index("     Begin Et:"):] for _, body in et_blocks}) != 1:
            raise ValueError("ET não idêntica entre sub-bacias")
        metadata["meteorologia"] = {"gages_conferidos": len(names), "et_mensal_identica": True}
        result = hec._lote_jvm([project], folder / "rodar.py")
        (folder / "stdout.txt").write_text(result.stdout, encoding="utf-8")
        (folder / "stderr.txt").write_text(result.stderr, encoding="utf-8")
        if not (project / "ok.txt").exists():
            raise RuntimeError("HEC sem saída confirmada: " + str(project))
        cfg = comum.SIMULACOES[a.janela]
        epoch = datetime(1899, 12, 31)
        bounds = [int((cfg[k] - epoch).total_seconds() / 60) for k in ("ini", "fim")]
        metadata["extracao"] = conferir_csv(project / "vazao.csv", required, a.passo, *bounds)
        metadata["dss_saida"] = conferir_metadata(project / "series_metadata.json", required, a.passo, metadata["extracao"]["n_por_no"])
        metadata["vazao_sha256"] = digest(project / "vazao.csv")
        report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["status"] = "preparado_sem_HEC" if a.preparar else "executado_nao_calibrado"
    report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"status": summary["status"], "janela": a.janela, "passo": a.passo, "bracos": list(summary["bracos"])}))


if __name__ == "__main__":
    main()
