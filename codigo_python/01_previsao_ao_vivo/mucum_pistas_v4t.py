# -*- coding: utf-8 -*-
"""Pistas da versão final (v4t, 25/11/2026) de Muçum — numpy puro, mesmas contas do treino.

Usado pelo robô-sombra (gerar_previsao_sombra_mucum.py) e pelo exportador do treino, que confere estas funções
contra as tabelas de treino antes de publicar. Constantes em assets/data/mucum_v4t/pistas_v4t.json.

  * chuva por sub-bacia: IDW (p = 2, distância mínima 1 km) de TODOS os postos com dado na hora (ANA + CEMADEN
    ao vivo; o INMET entrou no treino mas exige token ao vivo); hora sem posto nenhum = NaN;
  * índice de chegada (CHEG_*): chuva já caída (<= t) propagada até Muçum por hidrograma triangular no tempo de
    viagem do MDT (cru e com umidade antecedente API7);
  * balde PDM (Smax 50 mm): chuva efetiva com umidade do solo, também propagada (PDM50_*);
  * postos a montante: nível normalizado (UP_NIV*) e subida na janela que chega a Muçum (UPS*);
  * nowcast dos pluviômetros (NC_* entradas, NOW_* chuva prevista das próximas k horas, árvores xgboost);
  * árvores xgboost em arrays (arquivo .npz) e GRU em numpy.
EXPERIMENTAL — não é alerta oficial."""
from __future__ import annotations

import math

import numpy as np

SMAX, B_PDM, ET_PDM, KD_PDM = 50.0, 0.5, 0.12, 0.003


# ------------------------------------------------------------------ chuva por sub-bacia
def pesos_idw(sub_xy, posto_xy, p=2.0, dmin=1000.0):
    sx, sy = np.asarray(sub_xy, float).T
    px, py = np.asarray(posto_xy, float).T
    return 1.0 / np.maximum(np.hypot(sx[:, None] - px[None, :], sy[:, None] - py[None, :]), dmin) ** p


def chuva_subbacias(V, W):
    """V (horas x postos) com NaN = sem dado; W (sub-bacias x postos) -> S (horas x sub-bacias), NaN se nenhum posto."""
    V = np.asarray(V, float)
    ok = np.isfinite(V)
    num = np.where(ok, V, 0.0) @ W.T
    den = ok.astype(float) @ W.T
    return np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)


def media_area(S, areas, mascara=None):
    """média ponderada pela área das sub-bacias com dado (NaN se nenhuma), como media_area da base v4t"""
    a = np.asarray(areas, float) * (1.0 if mascara is None else np.asarray(mascara, float))
    ok = np.isfinite(S)
    den = ok @ a
    return np.where(den > 0, np.where(ok, S, 0.0) @ a / np.where(den > 0, den, 1.0), np.nan)


def filtro_exp(x, tau):
    """c_t = exp(-1/tau) c_{t-1} + x_t (NaN = 0), desde o início da série"""
    a, c, out = math.exp(-1.0 / tau), 0.0, np.empty(len(x))
    for i, v in enumerate(x):
        c = a * c + (0.0 if not np.isfinite(v) else float(v))
        out[i] = c
    return out


# ------------------------------------------------------------------ hidrogramas
def _tri(tt, n):
    w = max(3.0, 0.4 * tt)
    m = np.arange(0, n)
    u = np.clip(1 - np.abs(m - tt) / w, 0, None)
    return u / u.sum()


def _chegada(E, i, A, kernels):
    """sum_j A_j sum_m E_j[i-m] k_j[m]  (= np.convolve(E_j, k_j)[i] do treino)"""
    tot = 0.0
    for j, k in enumerate(kernels):
        L = min(len(k), i + 1)
        if L <= 0:
            continue
        tot += A[j] * float(E[i - L + 1:i + 1, j][::-1] @ k[:L])
    return tot


class Pistas:
    def __init__(self, C):
        self.C = C
        self.A_km2 = np.asarray(C["area_km2"], float)
        self.A = self.A_km2 / self.A_km2.sum()
        self.TT = np.asarray(C["tt_h"], float)
        self.LAT, self.LON = np.asarray(C["lat"], float), np.asarray(C["lon"], float)
        la0, lo0 = np.median(self.LAT), np.median(self.LON)
        tt = self.TT
        self.REG_NC = {"BACIA": np.ones(len(tt))}
        for n, (lo, hi) in {"T0_8": (0, 8), "T8_16": (8, 16), "T16_24": (16, 24), "T24_36": (24, 36), "T36_P": (36, 999)}.items():
            self.REG_NC[n] = ((tt >= lo) & (tt < hi)).astype(float)
        self.REG_NC.update({"QN": (self.LAT >= la0) * 1.0, "QS": (self.LAT < la0) * 1.0, "QW": (self.LON < lo0) * 1.0, "QE": (self.LON >= lo0) * 1.0})
        self._k = {}

    # ---------- índice de chegada (28_indice_chegada.py)
    def _kc(self, H, desl):
        chave = ("c", H, desl)
        if chave not in self._k:
            self._k[chave] = [_tri(tt, int(tt + max(3.0, 0.4 * tt) + H + 2))[H + desl:] for tt in self.TT]
        return self._k[chave]

    def cheg(self, S, i, Hs=(8, 12)):
        P = np.nan_to_num(np.asarray(S[:i + 1], float), nan=0.0)
        cs = np.vstack([np.zeros((1, P.shape[1])), np.cumsum(P, 0)])
        ini = np.maximum(np.arange(len(P)) - 168, 0)
        api7 = cs[np.arange(len(P))] - cs[ini]                        # soma das 168 h anteriores (sem a hora)
        E = {"cru": P, "api": P * (api7 / (api7 + 60.0))}
        out = {}
        for v, Ev in E.items():
            k0 = [_tri(tt, int(tt + max(3.0, 0.4 * tt) + 2)) for tt in self.TT]
            t0 = _chegada(Ev, i, self.A, k0)
            for H in Hs:
                ch = {d: _chegada(Ev, i, self.A, self._kc(H, d)) for d in range(-3, 4)}
                out[f"CHEG_H{H}_{v}"] = ch[0]
                out[f"CHEG_M{H}_{v}"] = max(ch.values())
                out[f"CHEG_D{H}_{v}"] = ch[0] - t0
        return out

    # ---------- balde PDM50 (HID_feats.py)
    def pdm50(self, S, i, Hs=(8, 12)):
        P = np.nan_to_num(np.asarray(S[:i + 1], float), nan=0.0)
        s = np.full(P.shape[1], 0.5 * SMAX)
        E = np.zeros_like(P)
        for r in range(len(P)):
            f = 1 - (1 - s / SMAX) ** B_PDM
            q = P[r] * f
            s = s + P[r] - q
            ex = np.maximum(s - SMAX, 0)
            q = q + ex
            s = s - ex
            s = np.maximum(s - ET_PDM * s / SMAX - KD_PDM * s, 0)
            E[r] = q
        if "u" not in self._k:
            self._k["u"] = [_tri(tt, int(tt + max(3.0, 0.4 * tt) + 40)) for tt in self.TT]
        U = self._k["u"]
        Q = {h: _chegada(E, i, self.A, [u[h:] if h < len(u) else np.zeros(1) for u in U]) for h in range(0, 25)}
        out = {}
        for H in Hs:
            M = [Q[h] for h in range(H, min(H + 13, 25))]
            out[f"PDM50_H{H}"], out[f"PDM50_D{H}"] = Q[H], Q[H] - Q[0]
            out[f"PDM50_M{H}"], out[f"PDM50_AM{H}"] = max(M), float(int(np.argmax(M)))
        return out

    # ---------- postos a montante (HID_feats.py UP_NIV, HID_feats2.py UPS)
    def montante(self, nivel, Hs=(8, 12)):
        """nivel(cod, h_atras) -> nível (cm) em t - h_atras ou None"""
        out = {}
        for H in Hs:
            num, den = {}, {}
            for p in self.C["up_niv"]:
                v = nivel(p["cod"], 0)
                if v is None:
                    continue
                w = p["corr"] ** 2
                num[p["ramo"]] = num.get(p["ramo"], 0.0) + (v - p["q50"]) / p["esc"] * w
                den[p["ramo"]] = den.get(p["ramo"], 0.0) + w
            for rb in self.C["ramos_up_niv"]:
                out[f"UP_NIV{H}_{rb}"] = num[rb] / den[rb] if den.get(rb) else None
            num, den = {}, {}
            for p in self.C["ups"][str(H)]:
                L = int(p["L"])
                a, b = nivel(p["cod"], max(L - H, 0)), nivel(p["cod"], L)
                if a is None or b is None:
                    continue
                v = min(max((a - b) / max(p["e1"], 5.0), -2.0), 4.0)
                w = p["corr"] ** 2
                for rr in (p["ramo"], "TODOS"):
                    num[rr] = num.get(rr, 0.0) + v * w
                    den[rr] = den.get(rr, 0.0) + w
            for rr in self.C["ramos_ups"]:
                out[f"UPS{H}_{rr}"] = num[rr] / den[rr] if den.get(rr) else None
        return out

    # ---------- nowcast dos pluviômetros (CHV_01_nowcast.py): entradas em t
    def nc(self, S, i, hora, mes):
        S = np.asarray(S[:i + 1], float)
        F = {}
        for n, m in self.REG_NC.items():
            s0 = np.nan_to_num(media_area(S, self.A_km2, m), nan=0.0)
            for k in (1, 2, 3, 6, 12, 24, 72):
                F[f"NC_{n}_p{k}h"] = float(s0[max(0, i - k + 1):i + 1].sum())
            F[f"NC_{n}_tend3"] = F[f"NC_{n}_p3h"] - (float(s0[max(0, i - 5):i - 2].sum()) if i >= 3 else 0.0)
        P0 = np.nan_to_num(S, nan=0.0)
        P3 = P0[max(0, i - 2):i + 1].sum(0)
        P3a = P0[max(0, i - 5):i - 2].sum(0) if i >= 3 else np.zeros(P0.shape[1])

        def centro(M):
            w = M * self.A_km2
            sw = w.sum()
            if not sw > 0.5 * self.A_km2.sum() / 1000:
                return (np.nan,) * 3
            return w @ self.LAT / sw, w @ self.LON / sw, w @ self.TT / sw
        c1, c0 = centro(P3), centro(P3a)
        F["NC_cen_lat"], F["NC_cen_lon"], F["NC_cen_tt"] = c1
        F["NC_dlat"], F["NC_dlon"], F["NC_dtt"] = c1[0] - c0[0], c1[1] - c0[1], c1[2] - c0[2]
        F["NC_frac_area_1mm3h"] = float((P3 >= 1.0) @ self.A_km2 / self.A_km2.sum())
        F["NC_max_sub3h"], F["NC_max_sub1h"] = float(P3.max()), float(P0[i].max())
        F["NC_hora_sin"], F["NC_hora_cos"] = math.sin(2 * math.pi * hora / 24), math.cos(2 * math.pi * hora / 24)
        F["NC_mes_sin"], F["NC_mes_cos"] = math.sin(2 * math.pi * mes / 12), math.cos(2 * math.pi * mes / 12)
        return F


# ------------------------------------------------------------------ árvores xgboost em arrays
def arvores_de_npz(z):
    """z: dict/NpzFile com feat, thr, esq, dir, falt, folha (nós concatenados), raiz (nó inicial de cada árvore),
    modelo (modelo de cada árvore), base_score (por modelo), alvos (nomes dos modelos, opcional)"""
    return {k: np.asarray(z[k]) for k in z.files} if hasattr(z, "files") else {k: np.asarray(v) for k, v in z.items()}


def avaliar_arvores(T, x, modelo=None):
    """soma das folhas + base_score do modelo; x com None/NaN = faltante; comparação em float32 como no xgboost.
    modelo=None -> média dos modelos (sementes)."""
    xv = np.array([np.nan if v is None else v for v in x], dtype=np.float32)
    feat, thr, esq, dir_, falt, folha = T["feat"], T["thr"], T["esq"], T["dir"], T["falt"], T["folha"]
    ms = range(len(T["base_score"])) if modelo is None else [modelo]
    tot = 0.0
    for mi in ms:
        s = float(T["base_score"][mi])
        for r in T["raiz"][T["modelo"] == mi]:
            i = int(r)
            while feat[i] >= 0:
                v = xv[feat[i]]
                i = int(falt[i]) if v != v else (int(esq[i]) if v < thr[i] else int(dir_[i]))
            s += float(folha[i])
        tot += s
    return tot / len(ms)


# ------------------------------------------------------------------ GRU (PyTorch nn.GRU 1 camada + cabeça) em numpy
def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def gru_prever(G, seq, est):
    """seq (L x s) já relativizada (níveis - nível em t; faltante 0), est (nst) com None/NaN -> média do treino.
    Devolve a variação prevista (cm), média dos modelos."""
    seq = np.asarray(seq, float)
    est = np.array([np.nan if v is None else v for v in est], float)
    out = []
    for m in G["modelos"]:
        X = (seq - np.asarray(m["ms"])) / np.asarray(m["ss"])
        z = np.where(np.isfinite(est), est, np.asarray(m["mz"]))
        z = (z - np.asarray(m["mz"])) / np.asarray(m["sz"])
        Wih, Whh = np.asarray(m["weight_ih"]), np.asarray(m["weight_hh"])
        bih, bhh = np.asarray(m["bias_ih"]), np.asarray(m["bias_hh"])
        nh = Whh.shape[1]
        h = np.zeros(nh)
        for xt in X:
            gi, gh = Wih @ xt + bih, Whh @ h + bhh
            r = _sig(gi[:nh] + gh[:nh])
            u = _sig(gi[nh:2 * nh] + gh[nh:2 * nh])
            n = np.tanh(gi[2 * nh:] + r * gh[2 * nh:])
            h = (1 - u) * n + u * h
        a = np.asarray(m["f0_w"]) @ np.concatenate([h, z]) + np.asarray(m["f0_b"])
        a = 0.5 * a * (1 + np.vectorize(math.erf)(a / math.sqrt(2)))          # GELU exata
        out.append((float(np.asarray(m["f2_w"]) @ a + float(m["f2_b"]))) * float(m["ys"]))
    return float(np.mean(out))
