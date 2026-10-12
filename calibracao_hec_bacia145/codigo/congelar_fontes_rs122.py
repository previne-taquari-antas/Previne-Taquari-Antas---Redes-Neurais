"""Gera snapshot de fontes locais conferidas para o experimento RS122."""
import argparse
import hashlib
import json
from pathlib import Path


def fingerprint(path):
    raw = path.read_bytes()
    mode = "binario" if path.suffix == ".gz" else "texto_lf"
    if mode == "texto_lf":
        raw = raw.replace(b"\r\n", b"\n")
    return {"modo": mode, "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", type=Path, required=True)
    ap.add_argument("--particao", type=Path, required=True)
    a = ap.parse_args()
    dest = a.raiz / "experimentos/rs122/fontes.json"
    if dest.exists():
        raise ValueError("Snapshot já existe")
    cfg = json.loads((a.raiz / "experimentos/rs122/contrato.json").read_text(encoding="utf-8"))
    m = json.loads((a.particao / "manifesto.json").read_text(encoding="utf-8"))
    for name, key in (("manifesto.json", "manifesto_sha256"), ("particao.geojson", "particao_sha256")):
        if hashlib.sha256((a.particao / name).read_bytes()).hexdigest() != cfg["geometria"][key]:
            raise ValueError("Proveniência geométrica não confere")
    for k, v in cfg["geometria"].items():
        if not k.endswith("sha256") and m[k] != v:
            raise ValueError("Valor geométrico não confere")
    paths = [a.raiz / cfg["parametros_origem"], a.raiz / "dados/basin/a00_E27.basin",
             a.raiz / "dados/mdt_subbacias_atributos.csv", a.raiz / "dados/mdt_trechos_atributos.csv",
             a.raiz / "dados/catalogo_ampliado.json"]
    for sim in cfg["janelas"]:
        paths += [a.raiz / "dados" / cfg["forcamento"] / (sim + ".json.gz")]
        paths += sorted((a.raiz / "dados/observados").glob("*" + sim + ".csv.gz"))
    out = {"geometria_conferida_localmente": cfg["geometria"],
           "geometria_bruta_nao_distribuida_na_nuvem": True,
           "entradas": {p.relative_to(a.raiz).as_posix(): fingerprint(p) for p in paths}}
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(len(paths), "fontes congeladas; geometria conferida contra arquivos locais")


if __name__ == "__main__":
    main()
