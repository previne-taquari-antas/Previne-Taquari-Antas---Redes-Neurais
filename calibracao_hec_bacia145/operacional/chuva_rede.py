"""Chuva observada ao vivo pela REDE recomendada pela frente de chuva ao vivo (versão 'avtelqc2', branch
cursor/hec-bacia145-aovivo): ANA telemetria (72) + CEMADEN público (66) + INMET (13, só com INMET_TOKEN), sem a
lista negra (dados/postos_rede.json, gerado por preparar_dados.py rede).
19/11/2026: + todas as ANA (dados/ana_bacia.json, 154) e CEMADEN (dados/cemaden_bacia.json, 125) da bacia + 10 km;
CEMADEN pelo endpoint horário de 720 h (cemaden.baixar_720); QC por janela (qc_janela) antes do causal. Ver LEIAME.

  hora H = (H − 1 h, H], BRT (convenção do forcamento_v3)
  ANA      HidroTelemetria em série (429 em paralelo) com backoff; hora só com todos os registros da cadência; relógio
           de Muçum corrigido; > 90 mm/h fora
  CEMADEN  histórico do coletor (cemaden.py, uma leitura a cada 10 min) + uma coleta na hora; hora exata (acc1hr com
           último dado em H:00) ou rateio do menor bloco acumulado (3/6/12… h) — ver cemaden.horarias
  INMET    apitempo com token (variável de ambiente INMET_TOKEN); sem token a fonte é pulada e registrada
  QC causal (avtelqc2): por hora, valor travado (6 h seguidas >= 2 mm com amplitude <= 1 mm) e chuva isolada
           (>= 10 mm com os 3 vizinhos com dado < 1 mm); depois, total das 72 h anteriores vs média dos 3 vizinhos
           (vizinhos > 30 mm e posto < 0,4x ou > 2,5x → posto fora naquela hora)
  IDW p = 2 no centróide (UTM 22S); hora sem nenhum posto (até a última hora observada) = 0, contada em
  horas_sem_estacao; última hora observada = a mais recente com >= max(5, 0,5 x mediana) postos.
"""
import json
import math
import time
from datetime import datetime, timedelta

import numpy as np

import cemaden
import chuva_observada as co
import geo
import inmet
import telemetria_ana as ta

H = timedelta(hours=1)
BRT = timedelta(hours=-3)
TRAVA_H, TRAVA_MIN, TRAVA_AMP = 6, 2.0, 1.0
ISOL_MIN, ISOL_VIZ = 10.0, 1.0
LIM_SUB, LIM_EXC, MIN_VIZ, JAN_QC = 0.4, 2.5, 30.0, 72
EXC_FORTE_MM, EXC_FORTE_X = 100.0, 5.0


def _vizinhos(cs, xy, k=3):
    return {c: sorted((x for x in cs if x != c), key=lambda x: math.dist(xy[c], xy[x]))[:k] for c in cs}


def qc_hora(series, horas, xy, isentas_trava=None):
    """Porta de aovivo/forcamentos.qc_hora (valor travado; chuva isolada). Altera series; devolve {posto: horas fora}.
    isentas_trava: {posto: horas} rateadas por igual (CEMADEN em bloco), que não são valor travado do sensor."""
    cs = sorted(series)
    viz = _vizinhos(cs, xy)
    isentas_trava = isentas_trava or {}
    fora, novo = {}, {}
    for c in cs:
        s, ruins = series[c], set()
        ise = isentas_trava.get(c, set())
        for i, h in enumerate(horas):
            v = s.get(h)
            if v is None:
                continue
            ult = [s.get(x) for x in horas[max(0, i - TRAVA_H + 1):i + 1]]
            if h not in ise and len(ult) == TRAVA_H and all(x is not None and x >= TRAVA_MIN for x in ult) and max(ult) - min(ult) <= TRAVA_AMP:
                ruins.add(h)
                continue
            vv = [series[x].get(h) for x in viz[c]]
            if v >= ISOL_MIN and len(vv) == 3 and all(x is not None and x < ISOL_VIZ for x in vv):
                ruins.add(h)
        novo[c] = {h: v for h, v in s.items() if h not in ruins}
        if ruins:
            fora[c] = len(ruins)
    series.clear()
    series.update({c: s for c, s in novo.items() if s})
    return fora


def qc_causal(series, horas, xy):
    """Porta de aovivo/forcamentos.qc_causal (72 h anteriores vs 3 vizinhos). Altera series; devolve {posto: horas fora}."""
    cs = sorted(series)
    if len(cs) < 4:
        return {}
    viz = _vizinhos(cs, xy)
    V = np.array([[series[c].get(h, np.nan) for c in cs] for h in horas])
    fora = {}
    novo = {c: dict(series[c]) for c in cs}
    for j, c in enumerate(cs):
        iv = [cs.index(x) for x in viz[c]]
        ok = np.isfinite(V[:, j]) & np.isfinite(V[:, iv]).all(1)
        a = np.where(ok, V[:, j], 0.0).cumsum()
        b = np.where(ok, np.nanmean(np.where(ok[:, None], V[:, iv], 0.0), 1), 0.0).cumsum()
        A = a - np.r_[np.zeros(JAN_QC), a[:-JAN_QC]] if len(a) > JAN_QC else a
        B = b - np.r_[np.zeros(JAN_QC), b[:-JAN_QC]] if len(b) > JAN_QC else b
        ruim = (B > MIN_VIZ) & ((A < LIM_SUB * B) | (A > LIM_EXC * B)) & np.isfinite(V[:, j])
        for i in np.where(ruim)[0]:
            novo[c].pop(horas[i], None)
        if ruim.any():
            fora[c] = int(ruim.sum())
    series.clear()
    series.update({c: s for c, s in novo.items() if s})
    return fora


def cobertura_minima(series, horas, frac=0.5):
    """Regra de entrada da chuva da calibração (forcamento_v3/v4: MIN_COBERTURA = 0,5): só entra posto com dado em
    >= frac das horas da janela e total > 0. 19/11/2026: no X77 um posto morto (só zeros) e um com 77 de 260 h
    deixaram passar um posto com 468 mm espúrios (86195000) e derrubaram o vizinho bom. Altera series."""
    fora = {}
    for c in list(series):
        s = series[c]
        n = sum(1 for h in horas if h in s)
        if n < frac * len(horas):
            fora[c] = f"cobertura {n}/{len(horas)} h"
        elif sum(s.values()) <= 0:
            fora[c] = "total zero"
        if c in fora:
            series.pop(c)
    return fora


def qc_janela(series, horas, xy, min_horas=24):
    """QC da chuva da calibração (forcamento_v2.qc_iterativo, usado no v3/v3b/v4) sobre a janela inteira até a última
    hora pedida — só passado, então vale ao vivo. Total do posto vs média dos 3 vizinhos nas horas em que todos têm dado:
    vizinhos > 30 mm e posto < 0,4x (subregistro) ou > 2,5x (excesso) → posto fora da janela toda. Remove um por
    rodada (o mais distante da razão 1 em log) e recalcula. 19/11/2026: no X77 o QC só por hora deixava entrar
    estações CEMADEN zeradas no início da chuva (os vizinhos ainda não somavam 30 mm em 72 h).
    Altera series; devolve {posto: motivo}, {posto: razão}."""
    excl, razoes = {}, {}
    while True:
        cs = list(series)
        novos = {}
        for c in cs:
            viz = sorted((x for x in cs if x != c), key=lambda x: math.dist(xy[c], xy[x]))[:3]
            hs = [h for h in horas if h in series[c] and all(h in series[v] for v in viz)]
            if len(hs) < min_horas:
                continue
            tc = sum(series[c][h] for h in hs)
            tv = sum(sum(series[v][h] for h in hs) for v in viz) / len(viz)
            razoes[c] = round(tc / tv, 2) if tv > 0 else None
            if tv > MIN_VIZ and tc < LIM_SUB * tv:
                novos[c] = "subregistro"
            elif tv > MIN_VIZ and tc > LIM_EXC * tv:
                novos[c] = "excesso"
            elif tc > EXC_FORTE_MM and tc > EXC_FORTE_X * tv:
                # só ao vivo: no começo do evento os vizinhos ainda não somam 30 mm e um posto com picos espúrios passava
                # (X77, −24 h: 86195000 com 465 mm contra 26 mm dos vizinhos)
                novos[c] = "excesso_forte"
        if not novos:
            return excl, razoes
        pior = max(novos, key=lambda c: abs(math.log(max(razoes[c] or 1e-3, 1e-3))))
        excl[pior] = novos[pior]
        series.pop(pior)


class RedeAoVivo(co.FonteChuvaObservada):
    nome = "rede ao vivo ANA + CEMADEN (todas da bacia, endpoint 720 h) + INMET (QC causal avtelqc2, IDW p=2)"

    def __init__(self, pasta_cemaden=None, coletar_agora=True, paralelo_ana=1, min_estacoes_hora=5,
                 frac_ultima_hora=0.5, rede=None, fontes=("ANA", "CEMADEN", "INMET"), todos_postos=True,
                 qc_janela=True):
        r = rede or json.loads((geo.DADOS / "postos_rede.json").read_text(encoding="utf-8"))
        self.negra = set(r.get("lista_negra", []))
        self.postos = {c: p for c, p in r["postos"].items() if c not in self.negra and p["fonte"] in fontes}
        # 19/11/2026: todas as estações ANA telemétricas da bacia + 10 km (não só as 72 vivas em 09/10/2026)
        if todos_postos and "ANA" in fontes:
            for c, e in json.loads((geo.DADOS / "ana_bacia.json").read_text(encoding="utf-8"))["estacoes"].items():
                if c not in self.negra:
                    self.postos.setdefault(c, dict(fonte="ANA", lat=e["lat"], lon=e["lon"], origem=e["origem"]))
        # 19/11/2026: todas as estações CEMADEN com chuva na bacia + 10 km (não só as 66 da rede), pelo endpoint de 720 h
        self.cem_720 = {}
        if todos_postos and "CEMADEN" in fontes:
            for c, e in cemaden.estacoes_bacia().items():
                if c in self.negra:
                    continue
                self.cem_720[c] = e["idestacao"]
                self.postos.setdefault(c, dict(fonte="CEMADEN", lat=e["lat"], lon=e["lon"], nome_publico=e["nome"],
                                               municipio=e["municipio"], origem="cemaden_bacia.json"))
        self.pasta_cem, self.coletar_agora = pasta_cemaden, coletar_agora
        self.paralelo, self.min_est, self.frac = paralelo_ana, min_estacoes_hora, frac_ultima_hora
        self.fontes = fontes
        self.qc_janela = qc_janela

    def _fonte(self, c):
        return self.postos[c]["fonte"]

    def obter(self, ini, ate, contexto=None):
        contexto = contexto or {}
        corrige = contexto.get("corrige_relogio", lambda c, t: t)
        horas = co.grade(ini, ate)
        series, info, tempos = {}, {}, {}

        # ANA
        t = time.time()
        ana = sorted(c for c in self.postos if self._fonte(c) == "ANA")
        extra = sorted(set(contexto.get("postos_extra", [])) - set(ana))
        n429 = ta.N_429[0]
        regs, falhas = ta.baixar_varios(ana + extra, ini - H, ate, self.paralelo) if ana or extra else ({}, {})
        susp, cad = {}, {}
        for c in ana:
            s, k, sp = co.chuva_horaria(regs.get(c, {}), horas, corrige=lambda t_, c=c: corrige(c, t_), tolerar=False)
            cad[c] = k
            if sp:
                susp[c] = sp
            if s:
                series[c] = s
        info["ANA"] = dict(consultados=len(ana), com_registro=sum(1 for c in ana if regs.get(c)),
                           com_chuva_horaria=sum(1 for c in ana if c in series), falhas_rede=falhas,
                           respostas_429=ta.N_429[0] - n429, horas_acima_90mm=susp,
                           cadencia_min={c: k for c, k in cad.items() if k})
        tempos["ANA"] = round(time.time() - t, 1)

        # CEMADEN
        t = time.time()
        cem = sorted(c for c in self.postos if self._fonte(c) == "CEMADEN")
        rateio = {}
        if cem:
            ini_u, ate_u = ini - BRT, ate - BRT
            coletas = cemaden.ler(self.pasta_cem, ini_u, ate_u) if self.pasta_cem else []
            n_hist = len(coletas)
            erro = None
            if self.coletar_agora:
                inst, est, n_pub, erro = cemaden.coletar()
                if est:
                    coletas.append((inst, est))
                    if self.pasta_cem:
                        cemaden.gravar(self.pasta_cem, inst, est, dict(n_publicas=n_pub, origem="ciclo"))
            sc, ic, rateio = cemaden.horarias(coletas, horas)
            # endpoint horário (720 h): manda nas horas que publica; o coletor só completa as que faltam (hora corrente)
            hs = set(horas)
            s720, falhas_720 = cemaden.baixar_720({c: self.cem_720[c] for c in cem if c in self.cem_720})                 if self.cem_720 else ({}, {})
            n_720 = {}
            for c in cem:
                s = dict(sc.get(c, {}))
                d720 = {h: v for h, v in s720.get(c, {}).items() if h in hs}
                if d720:
                    s.update(d720)
                    n_720[c] = len(d720)
                    rateio[c] = rateio.get(c, set()) - set(d720)
                s = {h: v for h, v in s.items() if 0 <= v <= co.MAX_MM_H}
                if s:
                    series[c] = s
            soma = {k: sum(v[k] for c, v in ic.items() if c in cem) for k in ("exatas", "aproximadas", "bloco")}
            info["CEMADEN"] = dict(consultados=len(cem), com_dado=sum(1 for c in cem if c in ic),
                                   com_chuva_horaria=sum(1 for c in cem if c in series), coletas_historico=n_hist,
                                   pasta_historico=str(self.pasta_cem) if self.pasta_cem else None,
                                   coleta_agora=self.coletar_agora, erro_coleta=erro,
                                   horas_exatas=soma["exatas"], horas_leitura_ate_30min=soma["aproximadas"],
                                   horas_por_bloco=soma["bloco"],
                                   ultima_coleta_utc=str(max(c[0] for c in coletas)) if coletas else None,
                                   endpoint_720h=dict(consultados=len([c for c in cem if c in self.cem_720]),
                                                      com_horas_na_janela=len(n_720), horas=sum(n_720.values()),
                                                      falhas=falhas_720,
                                                      ultima_hora_brt=str(max((max(s) for s in s720.values() if s),
                                                                              default=None))))
        tempos["CEMADEN"] = round(time.time() - t, 1)

        # INMET
        t = time.time()
        inm = sorted(c for c in self.postos if self._fonte(c) == "INMET")
        if inm:
            tk = inmet.token()
            if not tk:
                info["INMET"] = dict(consultados=0, pulado="sem INMET_TOKEN no ambiente")
            else:
                fal = {}
                for c in inm:
                    s, e = inmet.baixar(c.split("_", 1)[1], ini, ate, tk)
                    if e:
                        fal[c] = e
                    s = {h: v for h, v in s.items() if h in set(horas) and v <= co.MAX_MM_H}
                    if s:
                        series[c] = s
                info["INMET"] = dict(consultados=len(inm), com_chuva_horaria=sum(1 for c in inm if c in series),
                                     falhas_rede=fal)
        tempos["INMET"] = round(time.time() - t, 1)

        # QC causal + IDW
        cs = sorted(self.postos)
        xs, ys = geo.utm22s([self.postos[c]["lon"] for c in cs], [self.postos[c]["lat"] for c in cs])
        xy = {c: (x, y) for c, x, y in zip(cs, xs, ys)}
        fora_h = qc_hora(series, horas, xy, rateio)
        h_ate = [h for h in horas if h <= ate]
        fora_cob = cobertura_minima(series, h_ate) if self.qc_janela else {}
        fora_j, razoes_j = qc_janela(series, h_ate, xy) if self.qc_janela else ({}, {})
        fora_c = qc_causal(series, horas, xy)
        codes = sorted(series)
        n_est = [sum(1 for c in codes if h in series[c]) for h in horas]
        ref = float(np.median(n_est)) if n_est else 0.0
        ok_h = [i for i, n in enumerate(n_est) if n >= max(self.min_est, self.frac * ref)]
        ate_obs = horas[ok_h[-1]] if ok_h else ini - H
        sub = geo.subbacias()
        nomes = geo.nomes()
        px, py = geo.utm22s([sub[n]["lon"] for n in nomes], [sub[n]["lat"] for n in nomes])
        chuva = {n: [] for n in nomes}
        sem = []
        if codes:
            sx = np.array([xy[c][0] for c in codes])
            sy = np.array([xy[c][1] for c in codes])
            w = 1 / np.maximum(np.hypot(px[:, None] - sx, py[:, None] - sy), 1.0) ** 2
        for i, h in enumerate(horas):
            if h > ate_obs:
                for n in nomes:
                    chuva[n].append(None)
                continue
            vals = np.array([series[c].get(h, np.nan) for c in codes]) if codes else np.array([])
            ok = np.isfinite(vals)
            if ok.sum() < 1:
                sem.append(str(h))
                for n in nomes:
                    chuva[n].append(0.0)
                continue
            v = (w[:, ok] @ vals[ok]) / w[:, ok].sum(axis=1)
            for j, n in enumerate(nomes):
                chuva[n].append(round(float(v[j]), 4))
        por_fonte_h = {f: [sum(1 for c in codes if self._fonte(c) == f and h in series[c]) for h in horas]
                       for f in self.fontes}
        degradado = [str(h) for h, n in zip(horas, n_est) if h <= ate_obs and n < 10]
        cob = dict(rede="dados/postos_rede.json", lista_negra=sorted(self.negra), por_fonte=info,
                   postos_usados=codes, postos_usados_por_fonte={f: sum(1 for c in codes if self._fonte(c) == f)
                                                                 for f in self.fontes},
                   qc_horas_fora_trava_ou_isolada=fora_h, qc_fora_cobertura_minima=fora_cob, qc_fora_janela_inteira=fora_j,
                   qc_razao_total_vizinhos={c: r for c, r in razoes_j.items() if c in fora_j},
                   qc_horas_fora_72h_vizinhos=fora_c,
                   estacoes_por_hora=n_est, estacoes_por_hora_por_fonte=por_fonte_h,
                   horas_sem_estacao=sem, horas_degradadas_menos_10_postos=degradado,
                   ultima_hora_pedida=str(ate), ultima_hora_observada=str(ate_obs),
                   regra_ultima_hora=f">= max({self.min_est}, {self.frac} x mediana de estacoes/hora)",
                   tempos_s=tempos)
        return co.ChuvaObservada(horas=horas, chuva=chuva, ate=ate_obs, fonte=self.nome, cobertura=cob, registros=regs)
