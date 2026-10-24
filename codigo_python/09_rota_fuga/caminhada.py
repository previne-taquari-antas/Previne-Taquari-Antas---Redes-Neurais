# -*- coding: utf-8 -*-
"""Tempo de caminhada do idoso (r.walk do GRASS) e distância na esfera.

Só biblioteca padrão: usado pelo gerador de rotas (gerar_rota_fuga_ruas.py) e
pelos locais altos (locais_altos.py), que roda nos testes sem rasterio.
"""
import math

# r.walk (GRASS) em s/m para o caminhante de referencia (0,72 s/m = 1,39 m/s).
VEL_IDOSO = 0.9
RW_A, RW_B, RW_C, RW_D = 0.72, 6.0, 1.9998, -1.9998
RW_RAMPA_INGREME = -0.2125
FATOR_IDOSO = 1.0 / (RW_A * VEL_IDOSO)     # escala o r.walk para 0,9 m/s no plano
VEL_MAX_DESCIDA = 1.1       # idoso nao desce mais rapido que isso, mesmo em descida suave
RAMPA_MAX = 0.35            # rampas maiores no MDT em via sao ruido (muro, talude, ponte)
FATOR_ESCADA = 1.5


def haversine(lon1, lat1, lon2, lat2):
    R = 6371000.0
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def tempo_trecho(d, dh, escada=False):
    """Segundos de caminhada (idoso) num trecho de d metros com desnível dh (+ sobe)."""
    if d <= 0:
        return 0.0
    rampa = max(-RAMPA_MAX, min(RAMPA_MAX, dh / d))
    dh = rampa * d
    t = RW_A * d
    if dh > 0:
        t += RW_B * dh
    elif dh < 0:
        t += (RW_C if rampa > RW_RAMPA_INGREME else RW_D) * dh
    t = max(t * FATOR_IDOSO, d / VEL_MAX_DESCIDA)
    return t * (FATOR_ESCADA if escada else 1.0)
