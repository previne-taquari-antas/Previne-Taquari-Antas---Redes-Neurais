#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Divide os contornos de extravasamento em um arquivo por nível, para as páginas de previsão.

As páginas de previsão de Santa Tereza e Muçum desenham um nível por vez, mas baixavam o
FeatureCollection inteiro (40 MB e 13 MB). Com este divisor, elas baixam um índice leve, com as
propriedades de todos os níveis (inclusive a área), e a geometria de cada nível só quando ela
vai ser desenhada (ver assets/js/contornos_por_nivel.js). A geometria de cada arquivo é a mesma
do arquivo completo, sem simplificação.

Roda no deploy (deploy-pages.yml) sobre a cópia do site, então os arquivos gerados não são
versionados e sempre correspondem ao arquivo completo publicado. Saída, ao lado de cada fonte:

  <fonte sem .json>_niveis/indice.json     propriedades de cada nível + sha256 da fonte
  <fonte sem .json>_niveis/n0010.json      Feature do nível 0,1 m (nome = nível em cm, 4 dígitos)

Uso:
  python codigo_python/02_mdt_hand_mancha/dividir_contornos_por_nivel.py --site-dir _site
  # lendo do checkout (publish-pages.yml não copia arquivos > 20 MB para o _site):
  python codigo_python/02_mdt_hand_mancha/dividir_contornos_por_nivel.py --fonte-dir . --site-dir _site
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

FONTES = (
    "assets/data/santa_tereza_inundacao/contornos_extravasamento.json",
    "assets/data/mucum_inundacao/contornos_extravasamento.json",
)


def pasta_niveis(fonte: Path) -> Path:
    return fonte.with_name(fonte.stem + "_niveis")


def compacto(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def dividir(fonte: Path, destino: Path | None = None) -> dict:
    """Grava o índice e um arquivo por nível (ao lado da fonte, ou em destino); devolve um resumo."""
    bruto = fonte.read_bytes()
    fc = json.loads(bruto)
    if fc.get("type") != "FeatureCollection" or not fc.get("features"):
        raise ValueError(f"{fonte}: esperado FeatureCollection com feições")
    destino = destino or pasta_niveis(fonte)
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    niveis, vistos = [], set()
    for feat in fc["features"]:
        nivel = float(feat["properties"]["nivel_m"])
        cm = round(nivel * 100)
        if cm in vistos:
            raise ValueError(f"{fonte}: nível {nivel} m repetido")
        vistos.add(cm)
        arquivo = f"n{cm:04d}.json"
        (destino / arquivo).write_text(compacto(feat), encoding="utf-8")
        niveis.append({"arquivo": arquivo, "properties": feat["properties"]})
    indice = {
        "fonte": fonte.name,
        "fonte_sha256": hashlib.sha256(bruto).hexdigest(),
        "metadata": fc.get("metadata"),
        "niveis": niveis,
    }
    (destino / "indice.json").write_text(compacto(indice), encoding="utf-8")
    maior = max((destino / n["arquivo"]).stat().st_size for n in niveis)
    return {"fonte": str(fonte), "niveis": len(niveis), "indice_bytes": (destino / "indice.json").stat().st_size,
            "maior_nivel_bytes": maior, "fonte_bytes": len(bruto)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site-dir", default=".", help="raiz do site (cópia do deploy ou o próprio repositório)")
    ap.add_argument("--fonte-dir", default=None, help="onde ler os arquivos completos (padrão: --site-dir)")
    args = ap.parse_args()
    raiz = Path(args.site_dir)
    origem = Path(args.fonte_dir) if args.fonte_dir else raiz
    for rel in FONTES:
        fonte = origem / rel
        if not fonte.exists():
            print(f"sem {rel}; nada a dividir")
            continue
        print(json.dumps(dividir(fonte, pasta_niveis(raiz / rel)), ensure_ascii=False))


if __name__ == "__main__":
    main()
