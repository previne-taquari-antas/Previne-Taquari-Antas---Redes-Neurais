# -*- coding: utf-8 -*-
"""Recorta a área diretamente atingida 2024 (Mapa Único do Plano Rio Grande, FEPAM) em janelas em volta de
cidades do vale do Taquari, para validar a mancha gerada pelo terreno em cenario_municipal.html.
Só para validação: grava validacao/mancha/mup_<cidade>.geojson."""
import json
import os
import sys

from shapely.geometry import box, mapping
from shapely.ops import unary_union

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "codigo_python", "09_rota_fuga"))
from preparar_mancha import le_arquivo  # noqa: E402

CIDADES = {  # centro (lat, lon)
    "encantado": (-29.236, -51.870),
    "roca_sales": (-29.284, -51.866),
    "lajeado": (-29.467, -51.961),
    "estrela": (-29.502, -51.950),
    "arroio_do_meio": (-29.401, -51.944),
    "cruzeiro_do_sul": (-29.514, -51.985),
    "colinas": (-29.392, -51.858),
}
R = 0.035  # meia largura da janela (~3,5 km)

shps = sys.argv[1:]
for nome, (la, lo) in CIDADES.items():
    jan = (lo - R, la - R, lo + R, la + R)
    gs = []
    for p in shps:
        gs += le_arquivo(p, caixa=jan)[0]
    m = unary_union(gs).intersection(box(*jan)) if gs else None
    if not m or m.is_empty:
        print(nome, "sem mancha na janela")
        continue
    m = m.simplify(0.00001, preserve_topology=True)
    json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"cidade": nome, "janela": jan},
               "geometry": mapping(m)}]}, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"mup_{nome}.geojson"), "w"))
    print(nome, "ok", round(m.area * 111.32 * 96.9 * 110.57 / 111.32, 2), "km² (aprox.)")
