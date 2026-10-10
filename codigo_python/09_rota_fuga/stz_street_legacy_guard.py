"""Fail closed for the unvalidated Santa Tereza street/house pipeline.

Its uint16 surface conflates outside-raster/unknown with no threshold up to
25 m and its slopes still use the historical mosaic. A 1.60 m label alone
does not establish the field HAND contract. Preserve the exercise artifacts;
do not regenerate or aggregate them as current field-informed routes.
Muçum is deliberately outside this Santa Tereza-only guard.
"""
from __future__ import annotations


def require_supported_street_pipeline(city: str | None) -> None:
    if city in ("santa_tereza", "Santa Tereza", "4317251"):
        raise RuntimeError(
            "Execução bloqueada: ruas/casas de Santa Tereza ainda não validam "
            "NoData, saturação e MDT no contrato HAND de campo do rio principal "
            "(régua 1,60 m = HAND 0). Ausência de mancha não significa segurança. "
            "Use os painéis de pesquisa revisados; não é alerta oficial."
        )
