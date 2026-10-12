"""Adaptador experimental A/B0/B1 sobre bacia já parametrizada.

Não recalibra, não muda fontes e não afrouxa guardas do gerador titular.
B1 transfere deliberadamente chuva e resposta da mãe, para testar posição lateral.
"""
import copy
import math
import re

PAT = r"(?ms)^(Subbasin|Reach|Junction|Sink): ([^\n]+)\n(.*?)^End:"


def blocos(text):
    found = list(re.finditer(PAT, text))
    result = {m[2].strip(): (m[1], m[0]) for m in found}
    if len(result) != len(found):
        raise ValueError("Elementos duplicados")
    return result


def campo(block, label):
    found = re.findall(r"(?m)^\s*" + re.escape(label) + r": ([^\n]+)", block)
    if len(found) != 1:
        raise ValueError("Campo ausente/duplicado: " + label)
    return found[0].strip()


def rep(block, label, value):
    campo(block, label)
    return re.sub(r"(?m)^([ \t]*" + re.escape(label) + r": )[^\n]+", lambda m: m[1] + str(value), block)


def jusante(kind, name, block):
    if kind == "Sink" or (name == "J_157" and kind == "Junction" and "Downstream:" not in block):
        return None
    return campo(block, "Downstream")


def mudar_nome(block, old, new):
    return block.replace(": " + old + "\n", ": " + new + "\n", 1)


def conferir_grafo(text, ns, nr):
    bs = blocos(text)
    if sum(t == "Subbasin" for t, _ in bs.values()) != ns or sum(t == "Reach" for t, _ in bs.values()) != nr:
        raise ValueError("Contagem de elementos inesperada")
    down = {}
    for name, (kind, block) in bs.items():
        dest = jusante(kind, name, block)
        if dest is not None and dest not in bs:
            raise ValueError("Destino inexistente: " + dest)
        down[name] = dest
    for name in down:
        seen = set()
        while name is not None:
            if name in seen:
                raise ValueError("Ciclo no grafo")
            seen.add(name)
            name = down[name]
    return bs


def adaptar(text, arm, geo):
    bs = conferir_grafo(text, 145, 105)
    if arm not in ("A", "B0", "B1"):
        raise ValueError("Braço inválido")
    if arm == "A":
        return text, {"arm": arm, "modificacoes": []}
    sub, reach = bs["SB_211"][1], bs["R_211"][1]
    if campo(reach, "Route") != "Muskingum Cunge" or campo(reach, "Channel") != "Trapezoid":
        raise ValueError("Experimento exige mc trapezoidal do titular")
    if campo(reach, "Downstream") != "J_211":
        raise ValueError("Saída R211 mudou")
    inputs = {n for n, (t, b) in bs.items() if jusante(t, n, b) == "R_211"}
    if inputs != {"SB_211", "J_222", "J_089"}:
        raise ValueError("Entradas R211 mudaram")
    if any(n in bs for n in ("R_211_UP", "R_211_DOWN", "SB_211_UP", "SB_211_DOWN", "J_RS122")):
        raise ValueError("Colisão de identidade")
    au, ad = float(geo["area_local_antes_posto_km2"]), float(geo["area_local_depois_posto_km2"])
    lu, ld = float(geo["comprimento_antes_m"]), float(geo["comprimento_depois_m"])
    if not all(math.isfinite(v) and v > 0 for v in (au, ad, lu, ld)):
        raise ValueError("Geometria inválida")
    area = float(campo(sub, "Area"))
    residual = area - au - ad
    if abs(residual) > .00051 or not math.isclose(float(campo(reach, "Length")), (lu + ld) / 1.1, abs_tol=.051):
        raise ValueError("Área/comprimento incompatível com titular")
    # Conservar exatamente a área efetiva do HEC. Resíduo registrado, sem editar polígonos.
    au_model = round(au, 6)
    ad_model = round(area - au_model, 6)
    l_up = round(lu / 1.1, 1)
    l_down = round(float(campo(reach, "Length")) - l_up, 1)
    r_up = rep(rep(mudar_nome(reach, "R_211", "R_211_UP"), "Length", f"{l_up:.1f}"), "Downstream", "J_RS122")
    r_down = rep(mudar_nome(reach, "R_211", "R_211_DOWN"), "Length", f"{l_down:.1f}")
    junction = "Junction: J_RS122\n     Description: Controle experimental; datum e curva pendentes\n     Downstream: R_211_DOWN\nEnd:"
    replacements = {"R_211": r_up + "\n" + junction + "\n" + r_down}
    for name in ("J_222", "J_089"):
        replacements[name] = rep(bs[name][1], "Downstream", "R_211_UP")
    if arm == "B0":
        replacements["SB_211"] = rep(sub, "Downstream", "R_211_UP")
    else:
        if campo(sub, "Baseflow") != "Linear Reservoir" or "Initial Flow:" in sub:
            raise ValueError("B1 exige estados específicos por área do titular")
        children = []
        for suffix, ar in (("UP", au_model), ("DOWN", ad_model)):
            b = mudar_nome(sub, "SB_211", "SB_211_" + suffix)
            b = rep(rep(b, "Area", f"{ar:.6f}"), "Downstream", "R_211_" + suffix)
            children.append(b)
        replacements["SB_211"] = "\n".join(children)
    result = re.sub(PAT, lambda m: replacements.get(m[2].strip(), m[0]), text)
    after = conferir_grafo(result, 146 if arm == "B1" else 145, 106)
    # Todo bloco fora do contrato precisa permanecer idêntico, incluindo as 12 bordas.
    for name in set(bs) - set(replacements):
        if after[name] != bs[name]:
            raise ValueError("Mudança fora do escopo: " + name)
    return result, {"arm": arm, "modificacoes": sorted(replacements),
                    "area_geografica_up_km2": au, "area_geografica_down_km2": ad,
                    "area_modelo_up_km2": au_model, "area_modelo_down_km2": ad_model,
                    "residuo_area_atribuido_down_km2": residual,
                    "length_modelo_up_m": l_up, "length_modelo_down_m": l_down,
                    "energia_herdada_m_m": campo(reach, "Energy Slope"),
                    "hipotese": "Tc/R/perdas/base/chuva/ET herdados; não espacialização independente"}


def chuva_transferida(forcing, arm):
    if arm not in ("A", "B0", "B1"):
        raise ValueError("Braço inválido")
    result = copy.deepcopy(forcing)
    series = result["chuva_por_subbacia"]
    if len(series) != 145 or "SB_211" not in series:
        raise ValueError("Forçamento deve ter as 145 SB originais")
    if arm == "B1":
        parent = series.pop("SB_211")
        series["SB_211_UP"] = parent.copy()
        series["SB_211_DOWN"] = parent.copy()
    return result


def conferir_transferencia(base, text, original, rain, arm):
    bs, actual = blocos(base), blocos(text)
    names = {n for n, (t, _) in actual.items() if t == "Subbasin"}
    series = rain["chuva_por_subbacia"]
    if set(series) != names or rain["horas"] != original["horas"]:
        raise ValueError("Identidades/horas de chuva incompatíveis")
    for n in names - {"SB_211_UP", "SB_211_DOWN"}:
        if series[n] != original["chuva_por_subbacia"][n]:
            raise ValueError("Mudança de chuva fora da transferência")
    if arm != "B1":
        return {"erro_max_volume_horario_mm_km2": 0.0, "chuva_identica": True}
    parent = bs["SB_211"][1]
    au, ad = [float(campo(actual["SB_211_" + s][1], "Area")) for s in ("UP", "DOWN")]
    area = float(campo(parent, "Area"))
    for side in ("UP", "DOWN"):
        block = actual["SB_211_" + side][1]
        restored = mudar_nome(rep(rep(block, "Area", campo(parent, "Area")), "Downstream", "R_211"), "SB_211_" + side, "SB_211")
        if restored != parent or series["SB_211_" + side] != original["chuva_por_subbacia"]["SB_211"]:
            raise ValueError("Parâmetros/estados/chuva dos filhos não são herdados")
    errs = [abs(au * u + ad * d - area * p) for u, d, p in zip(series["SB_211_UP"], series["SB_211_DOWN"], original["chuva_por_subbacia"]["SB_211"])]
    error = max(errs, default=0.0)
    if error > 1e-7:
        raise ValueError("Volume de chuva não conservado")
    return {"erro_max_volume_horario_mm_km2": error, "resposta_e_estados_especificos_identicos": True,
            "outros_144_hietogramas_identicos": True}


def discretizar(text, passo_min, calcular):
    """Refina somente Steps; K/x físicos ficam congelados no titular 10 min."""
    if passo_min not in (10, 5, 1):
        raise ValueError("Passo não previsto")
    changes = {}
    def replace(m):
        kind, name, block = m[1], m[2].strip(), m[0]
        if kind != "Reach" or campo(block, "Route") != "Muskingum":
            return block
        k, x = float(campo(block, "Muskingum K")), float(campo(block, "Muskingum x"))
        try:
            n = calcular(k, x, dt_h=passo_min / 60)
        except ValueError as exc:
            raise ValueError(f"{name}, K={k}, x={x}, dt={passo_min}: {exc}") from exc
        old = int(campo(block, "Muskingum Steps"))
        if passo_min == 10:
            # Texto do titular permanece exato, inclusive arredondamentos originais.
            return block
        changes[name] = {"antes": old, "depois": n, "K_inalterado": k, "x_inalterado": x}
        return rep(block, "Muskingum Steps", n)
    return re.sub(PAT, replace, text), changes
