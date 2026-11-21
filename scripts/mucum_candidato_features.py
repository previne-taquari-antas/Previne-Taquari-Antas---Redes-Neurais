"""Variáveis do candidato linear de Muçum (M + Linha José Júlio + chuva da bacia).

Módulo único, só biblioteca padrão, usado no treino
(``treinar_candidato_mucum_sombra.py``) e na operação em sombra
(``candidato_mucum_sombra.py``): o que a sombra calcula é exatamente o que o
treino viu.

Séries: dicionários ``{datetime_hora_cheia: valor}`` no rótulo horário do CSV
de pesquisa (``time_local`` = início da hora de média). Lacunas de até 2 h
dentro da série são interpoladas linearmente, como no #306; lacunas maiores
ficam ausentes e a hora não gera variável. Chuva nunca é preenchida.
"""
from __future__ import annotations

from datetime import datetime, timedelta

H = timedelta(hours=1)
MAX_GAP_H = 2

NOMES = (
    ["nM", "d1M", "d2M", "d4M", "d8M", "a2M", "a4M",
     "nJ", "d1J", "d2J", "d4J", "d8J", "a4J",
     "r3", "r6", "r12", "r24", "r48"]
)


def interpolar(serie: dict[datetime, float], max_gap_h: int = MAX_GAP_H) -> dict[datetime, float]:
    """Preenche lacunas internas de até ``max_gap_h`` horas (linear)."""
    if not serie:
        return {}
    horas = sorted(t for t, v in serie.items() if v is not None)
    out = {t: float(serie[t]) for t in horas}
    for a, b in zip(horas, horas[1:]):
        falta = int((b - a) / H) - 1
        if 0 < falta <= max_gap_h:
            va, vb = out[a], out[b]
            for i in range(1, falta + 1):
                out[a + i * H] = va + (vb - va) * i / (falta + 1)
    return out


def _d(s, u, k):
    a, b = s.get(u), s.get(u - k * H)
    return None if a is None or b is None else a - b


def _acc(s, u, k):
    a, b = _d(s, u, k), _d(s, u - k * H, k)
    return None if a is None or b is None else a - b


def _soma(chuva, u, k):
    # chuva atrasada 1 h por cautela: usa as horas u-1 ... u-k
    vals = [chuva.get(u - i * H) for i in range(1, k + 1)]
    return None if any(v is None for v in vals) else sum(vals)


def vetor(nivel_m: dict, nivel_j: dict, chuva: dict, u: datetime) -> list[float] | None:
    """Variáveis na hora ``u`` (rótulo do CSV) ou None se faltar algo."""
    m, j = nivel_m, nivel_j
    v = [
        m.get(u), _d(m, u, 1), _d(m, u, 2), _d(m, u, 4), _d(m, u, 8), _acc(m, u, 2), _acc(m, u, 4),
        j.get(u), _d(j, u, 1), _d(j, u, 2), _d(j, u, 4), _d(j, u, 8), _acc(j, u, 4),
        _soma(chuva, u, 3), _soma(chuva, u, 6), _soma(chuva, u, 12), _soma(chuva, u, 24), _soma(chuva, u, 48),
    ]
    return None if any(x is None for x in v) else [float(x) for x in v]


def prever(modelo: dict, x: list[float]) -> float:
    """Variação prevista (cm) com o modelo congelado (padronização + Ridge)."""
    if modelo["variaveis"] != NOMES:
        raise ValueError("contrato de variáveis diferente do modelo congelado")
    z = [(xi - mu) / sd for xi, mu, sd in zip(x, modelo["media"], modelo["escala"])]
    return modelo["intercepto"] + sum(c * zi for c, zi in zip(modelo["coeficientes"], z))
