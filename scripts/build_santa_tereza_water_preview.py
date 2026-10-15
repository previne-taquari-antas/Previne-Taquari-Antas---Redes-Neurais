#!/usr/bin/env python3
"""Deriva uma PREVIA VISUAL LEVE dos contornos LEGADOS de Santa Tereza.

IMPORTANTE: nao e produto de inundacao validado nem simula o remanso do Marrecao.
Nao usar para classificar edificacoes, desenhar rotas ou inferir alcances reais.
Apenas permite animar a geometria historica na interface da pesquisa.
"""
from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets/data/santa_tereza_inundacao/contornos_mancha.json"
OUT = ROOT / "assets/data/santa_tereza_inundacao/contornos_previa_visual_leve.json"
LIMIT_BYTES = 2_200_000


def make_preview(data: dict, step: float, tolerance: float) -> dict:
    by_level = {}
    for f in data.get("features", []):
        try:
            level = round(float(f.get("properties", {}).get("nivel_m", -100)), 2)
        except (TypeError, ValueError):
            continue
        if level >= 0 and level <= 25:
            by_level[level] = f
    if not by_level:
        raise ValueError("Contornos fonte sem features de nivel_m")
    ordered = sorted(by_level)
    levels = [round(i * step, 2) for i in range(int(25 / step) + 1)]
    levels = sorted(set(levels + [25.0]))
    features = []
    for request_level in levels:
        available = [x for x in ordered if x <= request_level + 1e-8]
        if not available:
            continue
        level = max(available)
        try:
            geom = shape(by_level[level]["geometry"])
            if geom.is_empty:
                continue
            simplified = geom.simplify(tolerance, preserve_topology=True)
            if simplified.is_empty:
                continue
            geom_out = transform(lambda x, y, z=None: (round(x, 6), round(y, 6)), simplified)
            features.append({
                "type": "Feature",
                "properties": {"nivel_m": request_level},
                "geometry": mapping(geom_out),
            })
        except Exception as exc:
            print("Ignorado contorno:", level, str(exc)[:160])
    if len(features) < 5:
        raise ValueError("Contornos insuficientes para animar")
    return {
        "type": "FeatureCollection",
        "metadata": {
            "status": "previa_visual_legada_nao_validada",
            "source": str(SRC.relative_to(ROOT)),
            "river_reference_method": "legacy_pre_auditoria_marrecao",
            "backwater_hydrodynamic_calibration": False,
            "hand_zero_regua_m": 1.6,
            "hand_max_m": 25,
            "preview_only": True,
            "usable_for_building_risk": False,
            "warning": "Contornos anteriores a auditoria do remanso. Representacao exploratoria; nao e previsao de inundacao nem alcance validado.",
        },
        "features": features,
    }


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"Fonte ausente: {SRC}")
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    settings = [(1.0, 0.00010), (1.0, 0.00016), (1.0, 0.00025),
                (2.0, 0.00014), (2.0, 0.00025)]
    for step, tol in settings:
        doc = make_preview(raw, step, tol)
        encoded = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        print(f"step={step} tolerance={tol} levels={len(doc['features'])} bytes={len(encoded)}")
        if len(encoded) <= LIMIT_BYTES:
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_bytes(encoded + b"\n")
            print("OK:", OUT, len(encoded), "bytes")
            return
    raise RuntimeError("Previa permanece grande demais; manter sem publicar")


if __name__ == "__main__":
    main()
