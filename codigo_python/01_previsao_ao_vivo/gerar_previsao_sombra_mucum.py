#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robô em SOMBRA — RNAs v2 de Muçum (4 h e 8 h com estações a montante).

Não altera o feed público (previsao_ao_vivo_mucum.json). Roda de hora em hora,
grava previsao_sombra_mucum.json e um histórico permanente
(historico_previsao_sombra_mucum.jsonl) para comparar com o observado antes de
qualquer promoção ao site.

Contrato dos modelos: assets/data/mucum_modelos_sombra.json. Diferenças em
relação ao robô principal, exigidas pelo treino v2:
  * chuva "media_dos_acumulados_por_posto": acumulado de k horas por posto só
    se as k horas existem; média dos postos com valor; chuva da hora H = soma
    das leituras com carimbo em (H-1h, H];
  * limites mínimo/máximo por estação (barragens em cota absoluta);
  * controle de qualidade ao vivo: leitura <= 0, erro de bit (~16384 em régua
    < 50 m) e sensor travado (>= 6 h com o mesmo valor enquanto Muçum varia
    > 30 cm) viram dado ausente;
  * hierarquia de reserva por horizonte: usa o primeiro nível com todas as
    entradas e base com antecedência suficiente; publica o nível usado e o motivo;
  * faixa de incerteza (E95 da auditoria por situação: subida / >= 1500 cm / geral);
  * (18/11/2026) modelos lineares (tipo_modelo = "linear": intercepto + coeficientes, sem .mat) e
    entrada "chuva_exp_idw" (IDW posto -> sub-bacia com pesos fixos, média por área, filtro
    exponencial de 12 h) com o QC diário de chuva da v2 sobre `qc_chuva_postos`: reserva v4 de
    Muçum para horas sem a Linha José Júlio (4/8 h só registro, nível 0; 12 h novo horizonte).
  * (24/11/2026) receita final v4 (tipo_modelo = "mistura"): peso_xgb x xgboost raso (árvores em JSON,
    avaliadas em Python puro, faltantes permitidos) + (1 - peso_xgb) x 1º ridge da cascata com entradas
    completas; entradas novas "mm3_nivel" (média das 3 últimas variações horárias, >= 2) e "chuva_area"
    (chuva média por área de uma região do contrato, IDW de todos os postos com dado na hora; op acum / dif / exp).
O mesmo script atende Santa Tereza: `--contrato assets/data/santa_tereza_modelos_sombra.json`
(o contrato define "alvo", "saida_json" e "historico_jsonl").
EXPERIMENTAL — não é alerta oficial.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
import sys
import xml.etree.ElementTree as ET

AQUI = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("robo_mucum", os.path.join(AQUI, "gerar_previsao_ao_vivo_mucum.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

RAIZ = R.RAIZ
CONTRATO = os.path.join(RAIZ, "assets", "data", "mucum_modelos_sombra.json")
SAIDA = os.path.join(RAIZ, "previsao_sombra_mucum.json")
HISTORICO = os.path.join(RAIZ, "historico_previsao_sombra_mucum.jsonl")
ALVO = R.ALVO
DIAS_JANELA = 4          # lags até 24 h + chuva 48 h + diferença 24/48 h
TRAVADO_H = 6
TRAVADO_VARIACAO_ALVO_CM = 30.0
REGIOES_CHUVA = {}       # contrato['regioes_chuva'] (receita v4)
POSTOS_IDW = []          # contrato['postos_chuva_idw']
_CACHE_AREA = {}


# ---------------------------------------------------------------- leitura ANA
def _parse_xml(xml):
    root = ET.fromstring(xml)
    linhas = [row for row in root.iter()]
    if not any(_campo(r, "DataHora") for r in linhas) and (root.text or "").strip().startswith("<"):
        linhas = list(ET.fromstring(root.text).iter())
    return linhas


def _campo(row, nome):
    for ch in row:
        if R._local(ch.tag) == nome:
            return (ch.text or "").strip()
    return None


def series_da_resposta(xml):
    """(nível em hora cheia exata, chuva por hora com rótulo (H-1, H])."""
    niveis, chuva = {}, {}
    for row in _parse_xml(xml):
        dh = _campo(row, "DataHora")
        if not dh:
            continue
        t = R._parse_hora(dh)
        if t is None:
            continue
        nv = _campo(row, "Nivel")
        if nv not in (None, "") and t.minute == 0 and t.second == 0:
            try:
                niveis[t] = float(nv.replace(",", "."))
            except ValueError:
                pass
        ch = _campo(row, "Chuva")
        if ch not in (None, ""):
            try:
                v = float(ch.replace(",", "."))
            except ValueError:
                continue
            if v < 0 or v > 100:
                continue
            hora = t if (t.minute == 0 and t.second == 0) else t.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
            chuva[hora] = chuva.get(hora, 0.0) + v
    return niveis, chuva


def baixar(cod):
    xml = R._obter_xml_ana(cod, DIAS_JANELA, R.ANA_TIMEOUT_NIVEL_S, R.ANA_RETRIES_NIVEL, R._serie_de_xml, "ANA sombra")
    if xml is None:
        return {}, {}
    return series_da_resposta(xml)


# ------------------------------------------------------- controle de qualidade
def qc_niveis(cod, serie, limites, alvo_serie=None):
    lim = limites.get(cod, {})
    mn, mx = float(lim.get("min", 0.0)), float(lim.get("max", R.NIVEL_PLAUSIVEL_MAX_CM))
    limpa = {}
    for t, v in serie.items():
        if v <= 0 or v < mn or v > mx:
            continue
        if mx <= 5000 and 16000 <= v <= 21384:
            continue
        limpa[t] = v
    # salto impossível (mesma regra do treino): |v - última leitura aceita| > salto_max_1h
    # é descartado até o nível voltar; só uma interrupção real da série bruta (> 3 h sem
    # leitura) refaz a âncora
    salto = lim.get("salto_max_1h")
    if salto:
        ancora, anterior = None, None
        for t in sorted(limpa):
            v = limpa[t]
            continua = anterior is not None and t - anterior <= dt.timedelta(hours=3)
            anterior = t
            if ancora is not None and continua and abs(v - ancora) > float(salto):
                limpa.pop(t)
                continue
            ancora = v
    if cod == ALVO or not limpa:
        return limpa
    horas = sorted(limpa)
    i = 0
    while i < len(horas):
        j = i
        while (j + 1 < len(horas) and horas[j + 1] - horas[j] == dt.timedelta(hours=1)
               and limpa[horas[j + 1]] == limpa[horas[i]]):
            j += 1
        if j - i + 1 >= TRAVADO_H and alvo_serie:
            vals = [alvo_serie[h] for h in horas[i:j + 1] if h in alvo_serie]
            if vals and max(vals) - min(vals) > TRAVADO_VARIACAO_ALVO_CM:
                for h in horas[i:j + 1]:
                    limpa.pop(h, None)
        i = j + 1
    return limpa


# -------------------------------------------------------------------- entradas
def _n(niveis, cod, t):
    return (niveis.get(cod) or {}).get(t)


def _acum_posto(chuva, posto, fim, janela):
    vals = [(chuva.get(posto) or {}).get(fim - dt.timedelta(hours=h)) for h in range(janela)]
    return None if any(v is None for v in vals) else float(sum(vals))


def _media_acumulados(inp, chuva, t, deslocamento=0):
    fim = t - dt.timedelta(hours=deslocamento)
    acc = [_acum_posto(chuva, p, fim, int(inp["janela_h"])) for p in inp["estacoes"]]
    acc = [a for a in acc if a is not None]
    return sum(acc) / len(acc) if acc else None


def qc_chuva_postos(chuva, postos):
    """QC diário da v2 (qc_chuva) sobre os postos baixados: total do dia (rótulo da hora) contra a mediana
    dos demais; subregistro (< 0,2 x mediana com mediana >= 15 mm) ou excesso (> 4 x mediana + 50 e > 80 mm)
    anula o dia inteiro; hora > 100 mm é anulada."""
    dia = {p: {} for p in postos}
    for p in postos:
        for h, v in (chuva.get(p) or {}).items():
            dia[p][h.date()] = dia[p].get(h.date(), 0.0) + v
    limpa = dict(chuva)
    for p in postos:
        serie = chuva.get(p) or {}
        ruins = set()
        for d, tot in dia[p].items():
            outros = sorted(dia[q][d] for q in postos if q != p and d in dia[q])
            if not outros:
                continue
            k = len(outros)
            med = outros[k // 2] if k % 2 else (outros[k // 2 - 1] + outros[k // 2]) / 2
            if (tot < 0.2 * med and med >= 15) or (tot > 4 * med + 50 and tot > 80):
                ruins.add(d)
        limpa[p] = {h: v for h, v in serie.items() if h.date() not in ruins and v <= 100}
    return limpa


def _chuva_exp_idw(inp, chuva, t):
    """Chuva média da região (IDW posto -> sub-bacia com pesos fixos, só postos com dado na hora; média ponderada
    pela área) filtrada por c_t = exp(-1/tau) c_{t-1} + p_t, desde o início da janela baixada; hora sem posto = 0."""
    import math
    postos, W, areas = inp["postos"], inp["pesos_idw_sub_x_posto"], inp["areas_km2"]
    a = math.exp(-1.0 / float(inp.get("tau_h", 12)))
    horas = [h for p in postos for h in (chuva.get(p) or {})]
    if not horas or max(horas) < t - dt.timedelta(hours=int(inp.get("horas_minimas_recentes", 3))):
        return None
    inicio = min(horas)
    if t - inicio < dt.timedelta(hours=int(inp.get("aquecimento_h", 48))):
        return None
    c, h = 0.0, inicio
    while h <= t:
        num_area = den_area = 0.0
        vals = [(j, (chuva.get(p) or {}).get(h)) for j, p in enumerate(postos)]
        vals = [(j, v) for j, v in vals if v is not None]
        if vals:
            for i, ar in enumerate(areas):
                den = sum(W[i][j] for j, _ in vals)
                if den > 0:
                    num_area += ar * sum(W[i][j] * v for j, v in vals) / den
                    den_area += ar
        c = a * c + (num_area / den_area if den_area > 0 else 0.0)
        h += dt.timedelta(hours=1)
    return c


def _media_area_hora(reg, chuva, h):
    """Chuva média ponderada pela área da região na hora h: IDW (pesos fixos sub-bacia x posto) só com os postos
    que têm dado na hora; nenhum posto com dado -> None (como a base: NaN, nunca zero)."""
    chave = (id(chuva), reg, h)
    if chave in _CACHE_AREA:
        return _CACHE_AREA[chave]
    import numpy as np
    g = REGIOES_CHUVA[reg]
    if "_W" not in g:
        g["_W"] = np.asarray(g["pesos_idw_sub_x_posto"], float)
        g["_a"] = np.asarray(g["areas_km2"], float)
    js, vs = [], []
    for j, p in enumerate(POSTOS_IDW):
        v = (chuva.get(p) or {}).get(h)
        if v is not None:
            js.append(j)
            vs.append(v)
    if not js:
        r = None
    else:
        Wj = g["_W"][:, js]
        sub = Wj @ np.asarray(vs, float) / Wj.sum(axis=1)
        r = float(sub @ g["_a"] / g["_a"].sum())
    _CACHE_AREA[chave] = r
    return r


def _acum_area(reg, chuva, fim, k):
    vals = [_media_area_hora(reg, chuva, fim - dt.timedelta(hours=i)) for i in range(k)]
    return None if any(v is None for v in vals) else float(sum(vals))


def _chuva_area(inp, chuva, t):
    reg, op = inp["regiao"], inp["op"]
    if op == "acum":
        return _acum_area(reg, chuva, t, int(inp["janela_h"]))
    if op == "dif":
        k = int(inp["janela_h"])
        a, b = _acum_area(reg, chuva, t, k), _acum_area(reg, chuva, t - dt.timedelta(hours=k), k)
        return None if None in (a, b) else a - b
    if op == "exp":
        import math
        horas = [h for p in POSTOS_IDW for h in (chuva.get(p) or {})]
        if not horas or max(horas) < t - dt.timedelta(hours=int(inp.get("horas_minimas_recentes", 3))):
            return None
        inicio = min(horas)
        if t - inicio < dt.timedelta(hours=int(inp.get("aquecimento_h", 48))):
            return None
        a, c, h = math.exp(-1.0 / float(inp["tau_h"])), 0.0, inicio
        while h <= t:
            v = _media_area_hora(reg, chuva, h)
            c = a * c + (v if v is not None else 0.0)
            h += dt.timedelta(hours=1)
        return c
    raise ValueError(f"op de chuva_area não suportada: {op}")


def montar_entradas(inputs, niveis, chuva, t):
    x, faltam = [], []
    for inp in inputs:
        cod, tipo, h = inp.get("estacao"), inp["tipo"], int(inp.get("defasagem_h") or 0)
        v = None
        if tipo == "nivel":
            v = _n(niveis, cod, t - dt.timedelta(hours=h))
        elif tipo == "vel_nivel":
            a, b = _n(niveis, cod, t), _n(niveis, cod, t - dt.timedelta(hours=h))
            v = None if None in (a, b) else a - b
        elif tipo == "acel_nivel":
            a, b = _n(niveis, cod, t), _n(niveis, cod, t - dt.timedelta(hours=1))
            c, d = _n(niveis, cod, t - dt.timedelta(hours=h)), _n(niveis, cod, t - dt.timedelta(hours=h + 1))
            v = None if None in (a, b, c, d) else (a - b) - (c - d)
        elif tipo == "chuva_acum":
            v = _media_acumulados(inp, chuva, t)
        elif tipo == "chuva_diferenca":
            # mesma definição do treino: média, entre os postos, da diferença de cada posto
            difs = []
            for p in inp["estacoes"]:
                pa = _acum_posto(chuva, p, t, int(inp["janela_h"]))
                pb = _acum_posto(chuva, p, t - dt.timedelta(hours=int(inp.get("janela_anterior_h") or inp["janela_h"])), int(inp["janela_h"]))
                if pa is not None and pb is not None:
                    difs.append(pa - pb)
            v = sum(difs) / len(difs) if difs else None
        elif tipo == "chuva_exp_idw":
            v = _chuva_exp_idw(inp, chuva, t)
        elif tipo == "mm3_nivel":
            difs = [(_n(niveis, cod, t - dt.timedelta(hours=k)), _n(niveis, cod, t - dt.timedelta(hours=k + 1))) for k in range(3)]
            difs = [a - b for a, b in difs if a is not None and b is not None]
            v = sum(difs) / len(difs) if len(difs) >= 2 else None
        elif tipo == "chuva_area":
            v = _chuva_area(inp, chuva, t)
        else:
            raise ValueError(f"tipo de entrada não suportado: {tipo}")
        x.append(v)
        if v is None:
            faltam.append(inp.get("nome") or f"inp{inp.get('ordem')}")
    return x, faltam


# ------------------------------------------------------------------- previsão
def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest().upper()


def faixa(modelo, nivel_base, subindo, previsto):
    fx = modelo.get("faixa_e95_cm") or {}
    if previsto >= 1500 and fx.get("acima_1500"):
        e, motivo = fx["acima_1500"], "nível previsto >= 1500 cm"
    elif subindo and fx.get("subida"):
        e, motivo = fx["subida"], "rio subindo"
    else:
        e, motivo = fx.get("geral"), "geral"
    if e is None:
        return None
    return {"min_cm": round(previsto - e), "max_cm": round(previsto + e), "e95_cm": round(e, 1), "situacao": motivo}


_XGB = {}


def carregar_xgb(caminho):
    if caminho not in _XGB:
        with open(caminho, encoding="utf-8") as f:
            _XGB[caminho] = json.load(f)
    return _XGB[caminho]


def avaliar_xgb(mod, x):
    """Árvores do xgboost em Python puro: nó = [coluna, limiar, sim, não, faltante, folha]; x < limiar (float32) -> sim;
    None -> ramo de faltante; média das sementes."""
    import numpy as np
    tot = 0.0
    for m in mod["modelos"]:
        s = m["base_score"]
        for arv in m["arvores"]:
            i = 0
            while arv[i][0] >= 0:
                f, thr, sim, nao, falt, _ = arv[i]
                v = x[f]
                i = falt if v is None else (sim if np.float32(v) < np.float32(thr) else nao)
            s += arv[i][5]
        tot += s
    return tot / len(mod["modelos"])


def _linear(m, x):
    return float(m["intercepto"]) + sum(float(b) * v for b, v in zip(m["coeficientes"], x))


def _base_mistura(m, niveis, chuva, horas_alvo):
    """Hora-base mais recente (até 12 h atrás) em que algum ridge da cascata tem todas as entradas."""
    for t in reversed(horas_alvo[-13:]):
        for lin in m["lineares"]:
            x, faltam = montar_entradas(lin["inputs"], niveis, chuva, t)
            if not faltam:
                return t, lin, x
    return None


def prever_horizonte(nivel_cfg, niveis, chuva, horas_alvo, agora):
    """Percorre a hierarquia do horizonte; devolve (escolhido, todos)."""
    resultados, escolhido = [], None
    H = int(nivel_cfg["horizonte_h"])
    for m in sorted(nivel_cfg["modelos"], key=lambda m: m["nivel_hierarquia"]):
        tipo = m.get("tipo_modelo")
        linear, mistura = tipo == "linear", tipo == "mistura"
        mat = None if (linear or mistura) else os.path.join(RAIZ, m["mat"])
        item = {"modelo": m["modelo_id"], "nivel_hierarquia": m["nivel_hierarquia"], "papel": m.get("papel"),
                "horizonte_h": H, "disponivel": False}
        if mistura:
            arq = os.path.join(RAIZ, m["xgb"]["arquivo"])
            if not os.path.exists(arq):
                item["status"] = "árvores do xgboost ausentes"
                resultados.append(item)
                continue
            if m["xgb"].get("sha256") and _sha256(arq) != m["xgb"]["sha256"].upper():
                item["status"] = "sha256 das árvores não confere"
                resultados.append(item)
                continue
            base = _base_mistura(m, niveis, chuva, horas_alvo)
            if base is None:
                lin = m["lineares"][-1]
                _, faltam = montar_entradas(lin["inputs"], niveis, chuva, horas_alvo[-1]) if horas_alvo else ([], ["sem dado de Muçum"])
                item.update({"status": f"entradas incompletas ({len(faltam)})", "entradas_faltando": faltam})
                resultados.append(item)
                continue
            t, lin, xl = base
            xx, falt_x = montar_entradas(m["xgb"]["inputs"], niveis, chuva, t)
            v_x, v_l = avaliar_xgb(carregar_xgb(arq), xx), _linear(lin, xl)
            w = float(m["peso_xgb"])
            variacao = w * v_x + (1 - w) * v_l
            item.update({"linear_usado": lin["nome"], "variacao_xgb_cm": round(v_x, 1), "variacao_linear_cm": round(v_l, 1),
                         "xgb_entradas_faltando": falt_x})
        else:
            if linear:
                pass
            elif not os.path.exists(mat):
                item["status"] = "MAT ausente"
                resultados.append(item)
                continue
            if m.get("modelo_sha256") and _sha256(mat) != m["modelo_sha256"].upper():
                item["status"] = "sha256 do MAT não confere"
                resultados.append(item)
                continue
            base = None
            for t in reversed(horas_alvo[-13:]):
                x, faltam = montar_entradas(m["inputs"], niveis, chuva, t)
                if not faltam:
                    base = (t, x)
                    break
            if base is None:
                x, faltam = montar_entradas(m["inputs"], niveis, chuva, horas_alvo[-1]) if horas_alvo else ([], ["sem dado de Muçum"])
                item.update({"status": f"entradas incompletas ({len(faltam)})", "entradas_faltando": faltam})
                resultados.append(item)
                continue
            t, x = base
            variacao = _linear(m, x) if linear else R.prever(mat, x)
        antecedencia, ok = R.antecedencia_efetiva({"horizonte_h": H}, t, agora)
        nivel_base = niveis[ALVO][t]
        previsto = nivel_base + variacao
        subindo = (niveis[ALVO].get(t - dt.timedelta(hours=1)) or nivel_base) < nivel_base
        item.update({
            "hora_modelo": t.isoformat(timespec="minutes"),
            "hora_alvo": (t + dt.timedelta(hours=H)).isoformat(timespec="minutes"),
            "nivel_base_cm": round(nivel_base, 1), "nivel_previsto_cm": round(previsto, 1),
            "antecedencia_efetiva_h": round(antecedencia, 2),
            "faixa_incerteza": faixa(m, nivel_base, subindo, previsto),
            "fora_do_treino": bool(previsto > float(m.get("maximo_treino_nivel_cm", 1e9))),
        })
        if not ok:
            item["status"] = f"base desatualizada (antecedência {antecedencia:.1f} h)"
        elif not R.nivel_plausivel(previsto, ALVO):
            item["status"] = "previsão fora da faixa plausível"
        else:
            item["status"], item["disponivel"] = "ok", True
            if escolhido is None and m["nivel_hierarquia"] >= 1:   # nível 0 = controle, só registro
                escolhido = item
        resultados.append(item)
    return escolhido, resultados


# ------------------------------------------------------------------ histórico
def atualizar_historico(registros_novos, niveis_alvo):
    hist = {}
    if os.path.exists(HISTORICO):
        with open(HISTORICO, encoding="utf-8") as f:
            for linha in f:
                if linha.strip():
                    r = json.loads(linha)
                    hist[(r["modelo"], r["hora_modelo"])] = r
    for r in registros_novos:
        hist.setdefault((r["modelo"], r["hora_modelo"]), r)
    for r in hist.values():
        if r.get("observado_cm") is None:
            alvo = R._parse_hora(r["hora_alvo"])
            if alvo in niveis_alvo:
                r["observado_cm"] = round(niveis_alvo[alvo], 1)
                r["erro_cm"] = round(r["nivel_previsto_cm"] - r["observado_cm"], 1)
    with open(HISTORICO, "w", encoding="utf-8") as f:
        for r in sorted(hist.values(), key=lambda r: (r["hora_modelo"], r["modelo"])):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(hist)


def main(argv=None):
    global ALVO, SAIDA, HISTORICO, CONTRATO
    argv = sys.argv[1:] if argv is None else argv
    if "--contrato" in argv:
        CONTRATO = os.path.join(RAIZ, argv[argv.index("--contrato") + 1])
    agora = R.agora_brt()
    contrato = json.load(open(CONTRATO, encoding="utf-8"))
    ALVO = str(contrato.get("alvo") or ALVO)
    SAIDA = os.path.join(RAIZ, contrato.get("saida_json") or os.path.basename(SAIDA))
    HISTORICO = os.path.join(RAIZ, contrato.get("historico_jsonl") or os.path.basename(HISTORICO))
    limites = contrato.get("limites_estacao_cm", {})
    global REGIOES_CHUVA, POSTOS_IDW
    REGIOES_CHUVA = contrato.get("regioes_chuva", {})
    POSTOS_IDW = contrato.get("postos_chuva_idw", [])
    estacoes = [ALVO] + sorted({c for hz in contrato["horizontes"].values() for m in hz["modelos"]
                                for c in m.get("estacoes_nivel", []) + m.get("estacoes_chuva", [])} - {ALVO})
    estacoes = estacoes + sorted(set(contrato.get("qc_chuva_postos", [])) - set(estacoes))
    estacoes = estacoes + sorted(set(POSTOS_IDW) - set(estacoes))
    niveis, chuva = {}, {}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        for cod, (n, c) in zip(estacoes, ex.map(baixar, estacoes)):
            niveis[cod], chuva[cod] = n, c
    if contrato.get("qc_chuva_postos"):
        chuva = qc_chuva_postos(chuva, [p for p in contrato["qc_chuva_postos"] if p in chuva])
    niveis[ALVO] = qc_niveis(ALVO, niveis.get(ALVO, {}), limites)
    for cod in estacoes:
        if cod != ALVO:
            niveis[cod] = qc_niveis(cod, niveis.get(cod, {}), limites, niveis[ALVO])
    horas_alvo = sorted(niveis[ALVO])
    saida = {"gerado_em": agora.isoformat(timespec="seconds"), "aviso": "SOMBRA EXPERIMENTAL — não publicado no site; não é alerta oficial.",
             "contrato": os.path.relpath(CONTRATO, RAIZ), "alvo": ALVO, "ultima_hora_alvo": horas_alvo[-1].isoformat() if horas_alvo else None,
             "estacoes_sem_dado": [c for c in estacoes if not niveis.get(c) and not chuva.get(c)], "horizontes": {}}
    novos = []
    for chave, cfg in contrato["horizontes"].items():
        escolhido, todos = prever_horizonte(cfg, niveis, chuva, horas_alvo, agora) if horas_alvo else (None, [])
        saida["horizontes"][chave] = {
            "horizonte_h": cfg["horizonte_h"],
            "nivel_usado": escolhido["nivel_hierarquia"] if escolhido else None,
            "modelo_usado": escolhido["modelo"] if escolhido else None,
            "previsao": escolhido,
            "motivo": None if escolhido else "nenhum nível da hierarquia com entradas completas e base atual",
            "niveis": todos,
        }
        for it in todos:
            if it.get("nivel_previsto_cm") is not None:
                novos.append({k: it.get(k) for k in ("modelo", "nivel_hierarquia", "horizonte_h", "hora_modelo", "hora_alvo",
                                                      "nivel_base_cm", "nivel_previsto_cm", "antecedencia_efetiva_h", "status")}
                             | {"observado_cm": None, "erro_cm": None, "usado": bool(escolhido and it["modelo"] == escolhido["modelo"])})
    saida["historico_registros"] = atualizar_historico(novos, niveis.get(ALVO, {}))
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)
    for chave, h in saida["horizontes"].items():
        p = h["previsao"]
        print(chave, "nível", h["nivel_usado"], h["modelo_usado"], p and p["nivel_previsto_cm"], p and p["antecedencia_efetiva_h"])


if __name__ == "__main__":
    sys.exit(main())
