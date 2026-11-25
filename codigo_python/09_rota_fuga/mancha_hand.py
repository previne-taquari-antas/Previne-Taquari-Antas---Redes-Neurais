# -*- coding: utf-8 -*-
"""Mancha do modelo HAND do projeto no nível da maior cheia registrada de cada cidade, recortada
como a do mapa único (GeoJSON WGS84, rede de ruas ± 3 km), para pontos_encontro.py --versao hand.

Enquanto o perigo hidrológico do projeto não fica pronto, é a área insegura "nossa": os mesmos
contornos HAND dos painéis (contornos_mancha.json, passo de 0,1 m), no primeiro nível que cobre
a cheia. Santa Tereza: set/2023, régua 23,65 m, régua 1,60 m = HAND 0 (calibração de campo).
Muçum: mai/2024, régua 25,51 m, régua 5 m = HAND 0 (bankfull operacional, README).

Precisa dos contornos (fora do CI enxuto) e de shapely:
  python codigo_python/09_rota_fuga/mancha_hand.py
"""
import json
import os
import sys

from shapely.geometry import mapping

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gerar_painel  # noqa: E402
import pontos_encontro as pe  # noqa: E402
import preparar_mancha  # noqa: E402

CHEIAS = {
    "santa_tereza": {"rotulo": "set/2023", "data": "2023-09-04", "regua_m": 23.65, "zero_regua_m": 1.60},
    "mucum": {"rotulo": "mai/2024", "data": "2024-05-01", "regua_m": 25.51, "zero_regua_m": 5.0},
}


def main():
    for cidade, ch in CHEIAS.items():
        hand = round(ch["regua_m"] - ch["zero_regua_m"], 2)
        u, nv = gerar_painel.contorno_hand(cidade, hand)
        m = preparar_mancha.recorta([u], cidade)
        saida = pe.mancha_padrao(cidade, "hand")
        fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": mapping(m), "properties": {
            "origem": os.path.relpath(gerar_painel.rf_mod.CIDADES[cidade]["contornos"], pe.RAIZ),
            "cheia": ch["rotulo"], "data": ch["data"], "regua_m": ch["regua_m"], "zero_regua_m": ch["zero_regua_m"],
            "hand_cheia_m": hand, "nivel_contorno_m": nv,
            "recorte": f"rede de ruas de {pe.CIDADES[cidade]['municipio']} ± {preparar_mancha.FOLGA_RECORTE_M:g} m"}}]}
        with open(saida, "w", encoding="utf-8") as f:
            json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{cidade}: {ch['rotulo']} régua {ch['regua_m']} m → HAND {hand} m, contorno {nv} m · "
              f"{os.path.relpath(saida, pe.RAIZ)} ({os.path.getsize(saida) / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
