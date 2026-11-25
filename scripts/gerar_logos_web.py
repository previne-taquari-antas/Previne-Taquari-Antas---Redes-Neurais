#!/usr/bin/env python3
"""Cópias leves (WebP) das marcas para exibição nas páginas.

Os PNGs de assets/logos/ continuam intactos (README de logos): este script só gera
assets/logos/web/<nome>.webp reduzidos, na mesma proporção e sem recorte, com 3×
a largura máxima em que a marca aparece (moldura do CSS × escala da imagem).
O PREVINE e o LAGAM somavam ~1 MB e atrasavam em ~11 s, no 3G, a mancha de água
dos painéis; as cópias somam algumas dezenas de KB. O UFRGS original já é leve.

  python scripts/gerar_logos_web.py
"""
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
LOGOS = RAIZ / "assets" / "logos"
# largura máxima exibida (px CSS) × 3 (telas de alta densidade)
LARGURAS = {"previne": 600, "lagam": 720}


def main():
    (LOGOS / "web").mkdir(exist_ok=True)
    for nome, largura in LARGURAS.items():
        im = Image.open(LOGOS / f"{nome}.png")
        alto = round(im.height * largura / im.width)
        im = im.convert("RGBA").resize((largura, alto), Image.LANCZOS)
        destino = LOGOS / "web" / f"{nome}.webp"
        im.save(destino, "WEBP", quality=90, alpha_quality=100, method=6)
        print(f"{destino.relative_to(RAIZ)}: {destino.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
