#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
PAINEL DE EVACUACAO (uma pagina por cidade, com abas):
  · Rotas    -> clique numa casa e veja a rota ate o abrigo (nivel de projeto).
  · Margem   -> ruas coloridas pela margem de fuga; sliders de nivel + velocidade.
  · Quem sai -> grade populacional IBGE; conta PESSOAS por situacao.

Margem de um ponto = quanto tempo a pessoa ainda pode esperar para sair:
    min sobre os pontos da rota k de [ tempo ate a agua chegar em k
                                       - tempo para a pessoa chegar em k ]
    - tempo de preparo antes de sair (seletor: 0/30/60/120 min)
A subida padrao e 90 cm/h (media de set/2023 e de 22/07/2026); o slider vai a 2 m/h.
Atalhos do nivel e validade de abrigos/candidatos usam as cheias registradas
(CFG[...]["cheias_ref"]); em Muçum a capacidade vem do Plano de Contingencia.
com a rota recalculada no nivel do slider (niveis do rota_fuga_ruas_*.json,
passo 1 m HAND). "Ilhada" = a rota ja cruza agua no nivel.

Pessoas: a populacao de cada celula IBGE e dividida entre as casas OSM dentro
dela; celula sem casa mapeada usa o no de via mais proximo do centroide.

Uso:
  python codigo_python/09_rota_fuga/gerar_painel.py --cidade mucum
  python codigo_python/09_rota_fuga/gerar_painel.py --cidade santa_tereza
  # só o template (os JSON de rota não ficam no git): relê o painel publicado
  python codigo_python/09_rota_fuga/gerar_painel.py --cidade mucum --republicar
"""
import os, sys, json, math, argparse
from functools import lru_cache
from shapely.geometry import shape, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gerar_rota_fuga_ruas as rf_mod  # noqa: E402
from rede_casas import no_prox  # noqa: E402
import nivel_ao_vivo  # noqa: E402
import locais_altos  # noqa: E402

RAIZ = rf_mod.RAIZ
# leitura da régua agora: os robôs comitam com [skip ci] e o Pages não é republicado a cada leitura
RAW_MAIN = "https://raw.githubusercontent.com/previne-taquari-antas/Previne-Taquari-Antas---Redes-Neurais/main/"
# Cheias de referência na régua: atalhos do nível no painel e validade de cada
# abrigo/candidato ("seco até X; em set/2023 teria alagado"). Picos das séries
# em assets/data/eventos_analise.json (86472600) e mucum_eventos_analise.json
# (86510000). Muçum set/2023 fica de fora: a série termina subindo em 21,18 m.
# Santa Tereza mai/2024: a telemetria parou em 22,32 m antes do pico; vale a cota
# nivelada pelo SGB (22,42 m), a mesma da validação de campo do HAND. Os 25,82 m
# de "referência" que estavam aqui não têm fonte primária: set/2023 é a maior.
# "locais_altos": locais_altos.py (onde a água não chegou em set/2023, com folga);
# substituem os locais candidatos do gerador, calculados para a régua 15 m.
CFG = {
    "santa_tereza": {"cod": "4317251", "rf": "rota_fuga_ruas_santa_tereza_cenario.json",
                     "html": os.path.join(RAIZ, "santa_tereza_painel_casas.html"),
                     "cheias_ref": [
                         {"rotulo": "inundação oficial", "regua_m": 15.0, "tipo": "cota_oficial"},
                         {"rotulo": "jul/2026", "regua_m": 17.46, "data": "2026-07-22"},
                         {"rotulo": "nov/2023", "regua_m": 21.61, "data": "2023-11-18"},
                         {"rotulo": "mai/2024", "regua_m": 22.42, "data": "2024-05", "tipo": "sgb",
                          "nota": "cota nivelada pelo SGB; a telemetria parou em 22,32 m antes do pico"},
                         {"rotulo": "set/2023", "regua_m": 23.65, "data": "2023-09-04",
                          "nota": "telemetria ANA; o SGB nivelou o pico em 24,04 m"},
                     ],
                     "locais_altos": "santa_tereza", "exige_eixo_principal": True,
                     "ao_vivo": RAW_MAIN + "previsao_ao_vivo.json",
                     # página de rotas no pico até qualquer trecho alto, com os mesmos dados do painel
                     "rotas_altas_json": os.path.join(RAIZ, "assets", "data", "rota_fuga", "santa_tereza_rotas_altas_set2023.json"),
                     "link_extra": {"href": "santa_tereza_rotas_altas_set2023.html",
                                    "texto": "Rotas para qualquer trecho alto · setembro/2023 (página exploratória) →"}},
    "mucum": {"cod": "4312609", "rf": "rota_fuga_ruas_mucum_cenario.json",
              "html": os.path.join(RAIZ, "mucum_painel_casas.html"),
              "contingencia": os.path.join(RAIZ, "assets", "data", "mucum_contingencia_202607.json"),
              "ao_vivo": RAW_MAIN + "previsao_ao_vivo_mucum.json",
              "cheias_ref": [
                  {"rotulo": "inundação oficial", "regua_m": 18.0, "tipo": "cota_oficial"},
                  {"rotulo": "jul/2020", "regua_m": 22.11, "data": "2020-07-13"},
                  {"rotulo": "nov/2023", "regua_m": 22.99, "data": "2023-11-18"},
                  {"rotulo": "mai/2024", "regua_m": 25.51, "data": "2024-05-01"},
              ]},
}
MODOS = ("rotas", "margem", "impacto")
# subida média observada em set/2023 e em 22/07/2026 (~90 cm/h); 40 cm/h dava
# margem 2 a 5 vezes maior que a real. O slider vai até 2 m/h (trechos de set/2023).
TAXA_PADRAO_CM_H = 90.0


def capacidades_plano(cfg):
    """Capacidade planejada por abrigo (id) no Plano de Contingência; faixa quando o plano diverge."""
    if not cfg.get("contingencia"):
        return {}
    d = json.load(open(cfg["contingencia"], encoding="utf-8"))
    fonte = f"{d['meta'].get('documento', 'Plano de Contingência')} ({d['meta'].get('versao', 's/ versão')})"
    out = {}
    for a in d.get("pontos_encontro") or []:
        if a.get("capacidade_planejada") is not None:
            out[a["id"]] = {"min": a["capacidade_planejada"], "max": a["capacidade_planejada"],
                            "tipo": "ponto de encontro", "fonte": fonte}
    for a in d.get("abrigos") or []:
        vs = [v for v in (a.get("capacidade_quadro_13"), a.get("capacidade_ficha_tecnica")) if v is not None]
        if vs:
            out[a["id"]] = {"min": min(vs), "max": max(vs), "tipo": "alojamento", "fonte": fonte}
    return out


@lru_cache(maxsize=2)
def _contornos(cidade):
    return json.load(open(rf_mod.CIDADES[cidade]["contornos"], encoding="utf-8"))


# Santa Tereza: os contornos publicados são anteriores à auditoria do Marrecão (README de
# santa_tereza_inundacao); enquanto o produto novo não trouxer o eixo dominante, o painel avisa.
EIXO_VALIDADO = "eixo_dominante_taquari_D8"
AVISO_ESTUDO = ("Estudo em validação: a mancha do modelo é anterior à revisão do Arroio Marrecão e está "
                "sendo refeita. Use como apoio e siga sempre a Defesa Civil (199).")


def aviso_estudo(cidade):
    meta = _contornos(cidade).get("metadata") or {}
    return None if meta.get("river_reference_method") == EIXO_VALIDADO else AVISO_ESTUDO


def contorno_hand(cidade, nivel_hand):
    """União dos contornos HAND no primeiro nível >= nivel_hand (passo 0,1 m) e o nível usado."""
    d = _contornos(cidade)
    niveis = sorted({f["properties"]["nivel_m"] for f in d["features"]})
    nv = min((v for v in niveis if v >= nivel_hand - 1e-6), default=niveis[-1])
    return unary_union([shape(f["geometry"]) for f in d["features"] if abs(f["properties"]["nivel_m"] - nv) < 1e-6]), nv


def celulas_altas(cells, mancha_folga, lidar, z_min, classe, passo_m=20.0):
    """Células IBGE sem casa mapeada inteiras no alto (amostras a cada ~20 m): dentro do recorte do
    MDT, todo pixel em terreno "alto" (`classe`); fora dele, a célula fora da mancha HAND da cheia +
    folga e o LiDAR acima de z_min. Quem mora nelas já está em local alto; as outras seguem pelo
    acesso ao abrigo oficial."""
    out = []
    for c in cells:
        poly = Polygon([(x, y) for y, x in c["poly"]])
        if c["casas"] or poly.intersects(mancha_folga):
            out.append(False)
            continue
        w, s_, e, n = poly.bounds
        ny = max(2, int((n - s_) * 110540 / passo_m))
        nx = max(2, int((e - w) * 111320 * math.cos(math.radians((s_ + n) / 2)) / passo_m))
        pts = [(s_ + (n - s_) * i / ny, w + (e - w) * j / nx) for i in range(ny + 1) for j in range(nx + 1)]
        pts = [(la, lo) for la, lo in pts if poly.contains(Point(lo, la))]

        def alto(la, lo):
            k = classe(la, lo)
            if k is not None:
                return k == "alto"
            z = lidar(la, lo)
            return z is not None and z >= z_min
        out.append(bool(pts) and all(alto(la, lo) for la, lo in pts))
    return out


def mancha_cheia(cidade, nivel_hand, nos):
    """Contorno HAND da cheia (anéis [lat, lon], com ilhas secas) no entorno das ruas do painel."""
    u, nv = contorno_hand(cidade, nivel_hand)
    S, W, N, E = locais_altos.recorte(nos)
    u = u.intersection(box(W, S, E, N)).simplify(0.00003).buffer(0)
    def anel(r):
        return [[round(y, 6), round(x, 6)] for x, y in r.coords]
    # ilhas secas menores que ~100 m² somem no mapa
    polys = [p for p in getattr(u, "geoms", [u]) if p.geom_type == "Polygon" and p.area > 1e-8]
    return {"nivel_hand_m": nv,
            "poligonos": [[anel(p.exterior)] + [anel(i) for i in p.interiors if Polygon(i).area > 1e-8] for p in polys]}


def cota_acesso(cidade, doc, passo_m=2.0):
    """Nível HAND em que o acesso de cada casa até a rua alaga: o menor contorno que cobre um ponto do
    caminho da casa ao pé da perpendicular e dali ao nó de partida (a rota por nível só começa no nó).
    None = não alaga até o topo dos contornos, ou casa sem rua."""
    from caminhada import haversine
    F = {k: i for i, k in enumerate(doc["meta"]["casas_campos"])}
    pts, dono = [], []
    for i, c in enumerate(doc["casas"]):
        n, pj = c[F["no"]], (c[F["proj_lat"]], c[F["proj_lon"]])
        if pj[0] is None or n is None:
            continue
        if n < 0:  # outra margem: como em locais_altos.calcula
            n = locais_altos.no_mais_proximo(doc["nos"], pj)
        for j, (a, b) in enumerate((((c[F["lat"]], c[F["lon"]]), pj), (pj, tuple(doc["nos"][n])))):
            k = max(1, int(haversine(a[1], a[0], b[1], b[0]) / passo_m))
            for t in range(1 if j == 0 else 0, k + 1):  # a casa já tem a cota própria
                pts.append(Point(a[1] + (b[1] - a[1]) * t / k, a[0] + (b[0] - a[0]) * t / k))
                dono.append(i)
    out = [None] * len(doc["casas"])
    tree = STRtree(pts)  # um contorno por vez contra os pontos: o polígono grande é preparado uma vez
    for f in _contornos(cidade)["features"]:
        nv = f["properties"]["nivel_m"]
        for p in tree.query(shape(f["geometry"]), predicate="contains"):
            i = dono[p]
            if out[i] is None or nv < out[i]:
                out[i] = nv
    return [None if v is None else round(v, 1) for v in out]


def completa(doc, cidade, taxa_cm_h=TAXA_PADRAO_CM_H):
    """Campos do painel que não dependem das rotas: cheias, taxa padrão, capacidade do plano e locais altos."""
    cfg = CFG[cidade]
    doc["meta"]["cheias_ref"] = cfg["cheias_ref"]
    doc["meta"]["taxa_cm_h"] = taxa_cm_h
    doc["meta"]["link_extra"] = cfg.get("link_extra")
    doc["meta"]["ao_vivo_url"] = cfg.get("ao_vivo")
    doc["meta"]["aviso_estudo"] = aviso_estudo(cidade) if cfg.get("exige_eixo_principal") else None
    cap = capacidades_plano(cfg)
    for a in doc["abrigos"]:
        a["capacidade_plano"] = cap.get(a["id"])
    if cfg.get("locais_altos"):
        cla = locais_altos.CIDADES[cfg["locais_altos"]]
        mancha = mancha_cheia(cidade, cla["cheia"]["hand_m"], doc["nos"])
        doc["acesso_cota"] = cota_acesso(cidade, doc)
        alt = locais_altos.calcula(doc, mancha, cfg["locais_altos"])
        alt["mancha_cheia"] = mancha
        crit = alt["meta"]["criterios"]
        folga, _nv = contorno_hand(cidade, crit["celula_hand_min_m"])
        alt["cel_alta"] = [int(v) for v in celulas_altas(doc["cells"], folga, locais_altos.Lidar(cla["lidar"]),
                                                         crit["celula_altitude_min_m"], locais_altos.amostrador(alt["terreno"]))]
        doc["altos"] = alt
        doc["candidatos"], doc["rota_cand"] = [], None
    return doc


def escreve(doc, saida):
    # "<" escapado: um nome do OSM com "</script>" fecharia o script e rodaria o resto como HTML
    dados = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    dados = dados.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    open(saida, "w", encoding="utf-8").write(_TEMPLATE.replace("__DADOS__", dados))
    cfg = next((c for c in CFG.values() if c["html"] == saida), {})
    if doc.get("altos") and cfg.get("rotas_altas_json"):
        with open(cfg["rotas_altas_json"], "w", encoding="utf-8") as f:
            json.dump(locais_altos.pagina_rotas_altas(doc), f, ensure_ascii=False, separators=(",", ":"))


def payload_publicado(saida):
    """Dados embutidos num painel já publicado (const D=... no template)."""
    s = open(saida, encoding="utf-8").read()
    return json.JSONDecoder().raw_decode(s, s.index("const D=") + len("const D="))[0]


def republica(cidade):
    """Reaplica o template atual ao painel publicado, sem os JSON de rota (que não ficam no git)."""
    saida = CFG[cidade]["html"]
    escreve(completa(payload_publicado(saida), cidade), saida)
    print(f"{cidade}: template atual reaplicado -> {saida} ({os.path.getsize(saida) / 1e6:.1f} MB)")


def gera(cidade, rf_nome=None, html=None, modos=MODOS, titulo="Evacuação", taxa_cm_h=TAXA_PADRAO_CM_H):
    cfg = CFG[cidade]
    rf = json.load(open(os.path.join(RAIZ, "assets", "data", "rota_fuga", rf_nome or cfg["rf"]), encoding="utf-8"))
    if "niveis" not in rf:
        raise SystemExit("rota_fuga_ruas_*.json sem rotas por nível: rode gerar_rota_fuga_ruas.py de novo")
    inund = rf_mod.Inundacao(rf_mod.CIDADES[cidade])
    meta_rf = rf["meta"]
    F = {k: i for i, k in enumerate(meta_rf["casas_campos"])}
    pts = [Point(c[F["lon"]], c[F["lat"]]) for c in rf["casas"]]
    tree = STRtree(pts)

    grade = json.load(open(os.path.join(RAIZ, "assets", "data", "vulnerabilidade", "grade", f"{cfg['cod']}.geojson"), encoding="utf-8"))
    cells = []; pop_total = 0
    for f in grade["features"]:
        pop = float(f["properties"].get("pop", 0) or 0)
        if pop <= 0:
            continue
        g = shape(f["geometry"]); c = g.centroid
        dentro = sorted(int(i) for i in tree.query(g, predicate="contains"))
        cz = float(inund.cota(c.x, c.y)[0])
        cells.append({"pop": round(pop), "casas": dentro, "no": no_prox(rf["nos"], c.y, c.x),
                      "cota": None if cz == float("inf") else round(cz, 1),
                      "poly": [[round(y, 6), round(x, 6)] for x, y in g.simplify(0.0001).exterior.coords]})
        pop_total += pop

    nivel = meta_rf.get("nivel") or {}
    doc = {
        "meta": {"municipio": meta_rf["municipio"], "vel_idoso_ms": meta_rf.get("vel_idoso_ms", 0.9),
                 "taxa_cm_h": taxa_cm_h, "pop_total": round(pop_total),
                 "bankfull_m": nivel.get("bankfull_m"), "alarmes_regua_m": nivel.get("alarmes_regua_m") or {},
                 "nivel_projeto_m": meta_rf["nivel_projeto_m"], "rotulo_nivel": nivel.get("rotulo"),
                 "nivel_max_m": meta_rf.get("nivel_max_mapeado_m", 25.0),
                 "casas_campos": meta_rf["casas_campos"], "tempo_max_min": meta_rf.get("tempo_max_min"),
                 "abrigos_alagados": meta_rf.get("abrigos_alagados") or [],
                 "modos": list(modos), "titulo": titulo,
                 "gerado_em": nivel_ao_vivo.agora().strftime("%Y-%m-%d %H:%M")},
        "nos": rf["nos"], "cota_no": rf["cota_alaga_m"],
        "prox": rf["prox"], "dest": rf["dest"], "dist_m": rf["dist_m"], "agua_m": rf["agua_m"],
        "tempo_s": rf["tempo_s"], "rota_cand": rf.get("rota_cand"), "niveis": rf["niveis"],
        "edges": rf["edges"], "casas": rf["casas"], "candidatos": rf.get("candidatos") or [],
        "abrigos": rf["abrigos"], "mancha": rf["mancha"], "cells": cells,
    }
    saida = html or cfg["html"]
    escreve(completa(doc, cidade, taxa_cm_h), saida)
    print(f"{meta_rf['municipio']}: {len(rf['nos'])} nos, {len(rf['casas'])} casas, {len(cells)} celulas "
          f"(pop {pop_total:.0f}, {sum(bool(c['casas']) for c in cells)} com casa mapeada), "
          f"abas {'/'.join(modos)} -> {saida} ({os.path.getsize(saida) / 1e6:.1f} MB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cidade", choices=list(CFG), required=True)
    ap.add_argument("--rf", default=None, help="rota_fuga_ruas_*.json em assets/data/rota_fuga/ (padrão: cenário)")
    ap.add_argument("--republicar", action="store_true",
                    help="reaplica o template atual ao painel publicado, sem rodar as rotas")
    args = ap.parse_args()
    if args.republicar:
        republica(args.cidade)
    else:
        gera(args.cidade, args.rf)


_TEMPLATE = r"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evacuação casa a casa</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" onerror="this.onerror=null;this.href='https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css'">
<style>
 html,body{height:100%;margin:0}
 body{font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#12211b}
 #map{position:fixed;top:0;left:0;width:100vw;height:100vh}
 .hud{position:absolute;z-index:500;top:10px;left:10px;width:330px;max-width:calc(100vw - 24px);max-height:calc(100vh - 40px);overflow:auto;
      background:#fff;border-radius:12px;box-shadow:0 4px 18px rgba(0,0,0,.22);padding:0 0 12px}
 .hud h1{font:600 17px Georgia,serif;margin:0;padding:12px 14px 8px}
 /* cabeçalho fixo na folha: o botão de esconder não some quando o cartão rola para o alto */
 .topo{position:sticky;top:0;z-index:2;background:#fff;border-radius:12px 12px 0 0}
 .hud.semmapa{position:static;width:auto;max-width:720px;max-height:none!important;margin:0 auto;box-shadow:none}
 .bt-local{border:1px solid #9cc5ae;background:#eaf5ef;border-radius:8px;padding:8px 12px;min-height:40px;font:600 14px inherit;font-family:inherit;color:#075d40;cursor:pointer;margin:2px 0 6px}
 .leaflet-container:focus-visible::after{content:'';position:absolute;left:50%;top:50%;width:22px;height:22px;margin:-13px 0 0 -13px;
   border:2px solid #fff;border-radius:50%;box-shadow:0 0 0 2px #12211b;z-index:1000;pointer-events:none}
 @media (forced-colors:active){.sw,.leg-rota i{forced-color-adjust:none}}
 .dobra{float:right;margin:8px 8px 0 0;border:0;background:#eef3f0;border-radius:8px;padding:8px 12px;min-height:40px;font-weight:600;font-size:13px;font-family:inherit;cursor:pointer}
 .hud.min .corpo{display:none}
 .tabs{display:flex;border-bottom:1px solid #e6ece9;margin:0 0 8px}
 .tabs button{flex:1;border:0;background:none;padding:10px 4px;min-height:44px;font-weight:600;font-size:14px;font-family:inherit;color:#4a5a52;cursor:pointer;border-bottom:3px solid transparent}
 .tabs button.on{color:#0f6b4a;border-bottom-color:#0f8b46}
 .bd{padding:0 14px}
 .sub{color:#4a5a52;font-size:13.5px;margin:3px 0}
 .lv{font-variant-numeric:tabular-nums;font-weight:700;color:#0f6b4a}
 input[type=range]{width:100%;margin:6px 0 2px;height:28px}
 .row{display:flex;justify-content:space-between;align-items:center;font-size:14px;margin:3px 0}
 .row b{font-variant-numeric:tabular-nums;font-size:15px}
 .sw{display:inline-block;width:14px;height:14px;border-radius:3px;margin-right:7px;vertical-align:-2px;border:1px solid rgba(0,0,0,.35)}
 .rota{background:#eaf5ef;border:1px solid #bfe0cd;border-radius:8px;padding:8px 10px;font-size:14px;margin-top:6px}
 .aviso{background:#fdecea;border:1px solid #f2b8b2;color:#8f2a20;border-radius:8px;padding:7px 10px;font-size:13px;margin-top:6px}
 .big{font-size:14px;color:#5c4300;margin-top:8px}
 .nota{font-size:12.5px;color:#5c4300;margin-top:6px}
 .hide{display:none}
 .leg-rota{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:13px;color:#4a5a52;margin:6px 0 2px}
 .leg-mais summary{cursor:pointer;font-size:13px;color:#0f6b4a;font-weight:600;margin-top:4px}
 .leg-rota i{display:inline-block;width:18px;height:5px;margin-right:5px;vertical-align:middle;border-radius:2px}
 .leg-rota i.tr{background:repeating-linear-gradient(90deg,#b3241b 0 10px,transparent 10px 16px)}
 .canais{font-size:13px;color:#4a5a52;padding:0 14px 8px}
 .rio{font-size:14px;color:#12211b;padding:0 14px 8px}
 .cheias{display:flex;flex-wrap:wrap;gap:4px;align-items:center;margin:2px 0 6px;font-size:12px;color:#4a5a52}
 .cheias button{border:1px solid #c9d6cf;background:#f4f7f5;border-radius:12px;padding:6px 10px;font-weight:600;font-size:13px;font-family:inherit;cursor:pointer;min-height:36px}
 #selPrep{font:inherit;font-size:14px;margin-top:2px;min-height:36px}
 .lista{margin:0 14px 8px;font-size:14px}
 .lista summary{cursor:pointer;font-weight:600;color:#0f6b4a}
 .lista li{margin:4px 0}
 .cartao p{margin:5px 0}
 .cartao .nota,.rota details{color:#4a5a52;font-size:12.5px}
 .rota details{margin-top:8px}
 .rota summary{cursor:pointer;font-weight:600;color:#0f6b4a}
 .extra{margin:0 14px 8px;padding:8px 10px;border:1px solid #bbd4c6;border-radius:9px;background:#f3faf6;font-size:13px;line-height:1.4}
 .extra a{color:#075d40;font-weight:600}
 .alto-ic{filter:drop-shadow(0 0 1.5px #fff) drop-shadow(0 1px 2px rgba(0,0,0,.5))}
 .alto-ic i{position:absolute;inset:0;background:#14532d;clip-path:polygon(50% 0,100% 100%,0 100%)}
 .alto-ic b{position:absolute;left:0;right:0;bottom:3px;text-align:center;color:#fff;font:700 13px/1 sans-serif}
 /* celular: o painel vira uma folha na parte de baixo; recolhida, fica só o título */
 @media (max-width:700px){
  .hud{top:auto;bottom:0;left:0;right:0;width:auto;max-width:none;max-height:58vh;border-radius:14px 14px 0 0;padding-bottom:14px}
  /* no Pages, o CSS dos logos põe o painel a 84 px do topo e com 100% da altura: no celular ele cobria o mapa */
  body[data-previne-map-signature]>.hud.hud{margin-top:0;max-height:58vh;max-height:58dvh}
  .hud h1{font-size:16px}
 }
 .leg-rota i.tri{width:12px;height:11px;background:#14532d;clip-path:polygon(50% 0,100% 100%,0 100%);border-radius:0}
 .leg-rota i.c23{background:repeating-linear-gradient(90deg,#0b3d91 0 6px,transparent 6px 10px)}
</style></head><body>
<div class="hud" id="hud">
  <div class="topo" id="topo"><button class="dobra" id="dobra" type="button" aria-expanded="true" aria-controls="corpo" onclick="dobra()">Esconder ▼</button>
  <h1><span id="tit"></span> · <span id="cid"></span></h1></div>
  <div class="canais">Em emergência: <b>193</b> (Bombeiros) · <b>199</b> (Defesa Civil) · alertas por SMS: envie seu CEP para <b>40199</b>.</div>
  <div class="rio hide" id="rioAgora" aria-live="polite"></div>
  <div class="aviso hide" id="avisoEstudo" role="note" style="margin:0 14px 8px"></div>
  <div class="aviso hide" id="semMapa" role="alert" style="margin:0 14px 8px"></div>
  <div class="corpo" id="corpo">
  <div class="extra hide" id="extra"></div>
  <details class="lista hide" id="listaPontos"><summary>Lista dos pontos altos</summary><ol id="listaOl"></ol></details>
  <div class="tabs" id="tabs"></div>
  <div class="bd" id="painelAba" role="tabpanel">
    <div id="sliders" class="hide">
      <div class="sub">Nível do rio: <span class="lv" id="nvtxt"></span></div>
      <input type="range" id="sld" min="0" max="250" value="0" aria-label="nível do rio">
      <div class="cheias" id="cheias"></div>
      <div class="sub">Velocidade de subida: <span class="lv" id="taxatxt"></span> cm/h <span id="taxacen" style="color:#5c4300;font-size:12px"></span></div>
      <input type="range" id="sldTaxa" min="10" max="200" value="90" step="5" aria-label="velocidade de subida do rio, em centímetros por hora">
      <div class="sub"><label for="selPrep">Tempo para se preparar antes de sair:</label>
        <select id="selPrep"><option value="0">0 min</option><option value="30" selected>30 min (de dia)</option><option value="60">60 min (à noite)</option><option value="120">120 min (mobilidade reduzida)</option></select></div>
    </div>
    <div id="painel"></div>
    <div class="aviso hide" id="alertas"></div>
  </div>
  </div>
</div>
<div id="map"></div>
<script src="assets/js/live_feed.js?v=20261025-rotas"></script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>window.L||document.write('<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"><\/script>')</script>
<script>
const D=__DADOS__, M=D.meta, NV=D.niveis, ZR=M.bankfull_m;
// texto vindo do OSM e de cadastros vai para o HTML escapado
// abrigo "oficial" só com plano de contingência no repositório (Muçum); sem ele (Santa Tereza), ponto de referência
const AB_OFICIAL=D.abrigos.some(a=>a.capacidade_plano),ABN=AB_OFICIAL?'abrigo oficial':'ponto de referência';
const esc=t=>String(t??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fm=x=>x.toFixed(1).replace('.',','),fm2=x=>x.toFixed(2).replace('.',',');
function dobra(abre){const h=document.getElementById('hud'),bt=document.getElementById('dobra');
  const min=abre===undefined?!h.classList.contains('min'):!abre;h.classList.toggle('min',min);
  bt.textContent=min?'Ver instruções ▲':'Esconder ▼';bt.setAttribute('aria-expanded',String(!min));}
document.getElementById('cid').textContent=M.municipio;
if(M.aviso_estudo){const e=document.getElementById('avisoEstudo');e.textContent=M.aviso_estudo;e.classList.remove('hide');}
document.getElementById('tit').textContent=(M.titulo||'Evacuação')+' casa a casa';
document.title='Evacuação casa a casa · '+M.municipio+' — PREVINE';
// <puras> funções sem DOM nem mapa (testadas com node em tests/test_rota_fuga_painel.py)
const LEITURA_MAX_MIN=60;  // o robô chama de atrasada a telemetria com mais de 1 h; a 90 cm/h, 1 h = 0,9 m
function horaLeitura(j){const s=j&&(j.telemetria_ultima_em_utc||j.telemetria_ultima_em);if(!s)return NaN;
  const r=String(s);return Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(r)?r:r+'-03:00');}
// minutos desde a leitura; NaN se a hora é inválida ou está mais de 5 min no futuro (fuso ou relógio errado)
function idadeMin(t,agora){const m=(agora-t)/6e4;return isFinite(m)&&m>=-5?Math.max(0,m):NaN;}
// "quando sair": lim = HAND em que a água corta o caminho, cota = HAND em que chega na casa,
// y = régua de saída, rio = régua agora (null sem leitura recente), zr = zero da régua
function situacaoSaida(lim,cota,y,rio,zr){
  if(rio!=null&&cota!=null&&rio>=cota+zr)return 'casa_atingida';
  if(rio!=null&&lim!=null&&rio>=lim+zr)return 'caminho_cortado';
  if(rio!=null&&rio>=y)return 'agora';
  return y<=zr?'alerta':'nivel';}
// </puras>
// régua agora (telemetria da previsão ao vivo): relida a cada 5 min e ao voltar para a página
let RIOL=null,rioFalhou=false,aoMudarRio=()=>{};
function rioAtual(){if(!RIOL)return null;const id=idadeMin(RIOL.t,Date.now());return id<=LEITURA_MAX_MIN?RIOL.nv:null;}
function mostraRio(){const e=document.getElementById('rioAgora');
  if(!RIOL){if(rioFalhou){e.textContent='Leitura do rio indisponível agora (sem conexão com a telemetria).';e.classList.remove('hide');}return;}
  const id=idadeMin(RIOL.t,Date.now()),d=new Date(RIOL.t),tz='America/Sao_Paulo';
  const dia=d.toLocaleDateString('pt-BR',{timeZone:tz}),hoje=new Date().toLocaleDateString('pt-BR',{timeZone:tz});
  const hora=d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',timeZone:tz});
  const ha=id<60?Math.round(id)+' min':id<2880?Math.round(id/60)+' h':Math.round(id/1440)+' dias';
  e.innerHTML=`Rio agora: <b>${fm2(RIOL.nv)} m</b> na régua (leitura ${dia===hoje?'das '+hora:'de '+dia+' às '+hora}, há ${ha}`+
    (id>LEITURA_MAX_MIN?'; <b>atrasada</b>: não entra no "quando sair"':'')+(rioFalhou?'; a última busca falhou':'')+').';
  e.classList.remove('hide');}
async function leRio(){
  try{const j=window.PrevineLiveFeed?await PrevineLiveFeed.fetchLive(M.ao_vivo_url):
      await fetch(M.ao_vivo_url,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json();});
    const t=horaLeitura(j),cm=j&&j.telemetria_ultima_nivel_cm;
    if(cm==null||!isFinite(idadeMin(t,Date.now())))throw Error('sem leitura válida');
    const antes=rioAtual();RIOL={nv:cm/100,t};rioFalhou=false;mostraRio();if(rioAtual()!==antes)aoMudarRio();}
  catch(e){rioFalhou=true;mostraRio();}}
if(M.ao_vivo_url){leRio();setInterval(()=>{if(!document.hidden)leRio();},5*60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)leRio();});
  let usado=null;setInterval(()=>{mostraRio();const r=rioAtual();if(r!==usado){usado=r;aoMudarRio();}},60000);}
// lista dos pontos altos em texto: funciona sem mapa e com leitor de tela
if(D.altos){const f1=x=>x.toFixed(1).replace('.',','),il=D.altos.meta.nivel_mancha_m;
  document.getElementById('listaOl').innerHTML=D.altos.locais.map((l,j)=>`<li><b>Ponto alto ${j+1}</b>`+
    (l.rua?` — ${esc(l.rua)}`:'')+(l.perto.length?`, perto de ${esc(l.perto[0].nome)}`:'')+
    (l.ilha_m!=null&&l.ilha_m<=il?(l.ilha_m<0?'; sem rua mapeada até o resto da cidade':`; vira ilha com o rio em ${f1(l.ilha_m+ZR)} m`):'')+
    ` (<a href="geo:${l.lat.toFixed(6)},${l.lon.toFixed(6)}">${l.lat.toFixed(5)}, ${l.lon.toFixed(5)}</a>)</li>`).join('');
  document.getElementById('listaPontos').classList.remove('hide');}
if(!window.L){const e=document.getElementById('semMapa');e.classList.remove('hide');
  document.getElementById('hud').classList.add('semmapa');document.getElementById('map').style.display='none';
  e.textContent='O mapa não carregou (sem internet ou bloqueio). '+(D.altos?'Abaixo, a lista dos pontos altos (toque nas coordenadas para abrir no mapa do celular). ':'')+'Em emergência, ligue 199 (Defesa Civil) ou 193.';
  if(D.altos)document.getElementById('listaPontos').open=true;
  throw Error('Leaflet indisponível');}
const CF=Object.fromEntries(M.casas_campos.map((k,i)=>[k,i]));
let taxaCmH=M.taxa_cm_h,prepMin=30;
const map=L.map('map',{zoomControl:false});
L.control.zoom({position:'topright'}).addTo(map);
// no celular a folha cobre a parte de baixo: a atribuição (ODbL) vai para o alto
if(innerWidth<=700)map.attributionControl.setPosition('topleft');
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Imagens Esri · Ruas e edificações © OpenStreetMap contributors (ODbL) · População IBGE'}).addTo(map);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,opacity:.9}).addTo(map);
const txtNivel=h=>ZR!=null?`régua ${fm(h+ZR)} m (HAND ${fm(h)})`:`HAND ${fm(h)} m`;
// cheias registradas na régua (M.cheias_ref): atalhos do nível e validade de abrigos e candidatos
const CHEIAS=ZR!=null?(M.cheias_ref||[]):[];
const HIST=CHEIAS.filter(c=>c.tipo!=='cota_oficial');
const PIOR=HIST.reduce((p,c)=>!p||c.regua_m>p.regua_m?c:p,null);
function txtValidade(cota){
  let t=cota==null?`<br>Não alaga até ${txtNivel(M.nivel_max_m)} (topo do modelo).`:`<br>Alaga a partir de ${txtNivel(cota)}.`;
  if(HIST.length)t+='<br><span style="font-size:12px">Nas cheias registradas: '+HIST.map(c=>{const h=c.regua_m-ZR;
    return c.rotulo+' ('+fm2(c.regua_m)+' m) '+(cota!=null&&cota<=h?'<b style="color:#9e1b1b">alagaria</b>':cota!=null&&cota-h<0.5?'<b>no limite</b>':'seco');}).join(' · ')+'</span>';
  return t;}
function txtCapacidade(a){const c=a.capacidade_plano;if(!c)return '';
  const dm=a.demanda&&a.demanda.pessoas;
  return `<br>Capacidade planejada (${c.tipo}; ${c.fonte}): <b>${c.min===c.max?c.min:c.min+'–'+c.max}</b> pessoas. Não é vaga disponível.`+
    (dm!=null&&dm>c.max?`<br><b style="color:#9e1b1b">Demanda no cenário (~${dm} pessoas) acima da capacidade planejada.</b>`:
     dm!=null&&dm>c.min?`<br><b style="color:#9a3412">Demanda no cenário (~${dm} pessoas) acima do menor número do plano (${c.min}); o plano diverge entre ${c.min} e ${c.max}.</b>`:'');}
function avisoCheia(){if(!PIOR)return '';const h=PIOR.regua_m-ZR;
  const ab=D.abrigos.filter(a=>a.cota_alaga_m!=null&&a.cota_alaga_m<=h).map(a=>esc(a.nome));
  const nc=(D.candidatos||[]).filter(c=>c.cota_alaga_m!=null&&c.cota_alaga_m<=h).length;
  if(nc)ab.push(`${nc} de ${D.candidatos.length} locais candidatos`);
  const qual=PIOR.tipo==='referencia'?'Na cheia de referência mais alta':'Na maior cheia registrada';
  return ab.length?`<div class="aviso">${qual} (${PIOR.rotulo}, régua ${fm2(PIOR.regua_m)} m) alagariam: ${ab.join(', ')}.`+
    (AL?` Os ${AL.locais.length} pontos altos sugeridos (▲) ficam fora dela.`:'')+'</div>':'';}
// cores com luminância bem diferente entre urgente (escuro) e folgado (claro); par mais
// próximo com distância de cor >= 17 (Lab) também em deuteranopia, protanopia e tritanopia
// (antes "já na água" e "ilhada" ficavam a 2,0 na protanopia)
const CORES={alagada:'#1f4e9c',ilhada:'#9d4edd',isolada:'#2b2b2b',sem_abrigo:'#6b6b6b',critica:'#9e1b1b',apertada:'#e66100',atencao:'#f6c445',confortavel:'#4fb38a',seguro:'#c9cfcc',sem_rota:'#ffffff'};
const ROT={alagada:'já na água',ilhada:'ilhada — rota já cruza água',critica:'crítica — não sai a pé a tempo',apertada:'apertada (menos de 15 min)',atencao:'atenção (menos de 1 h)',confortavel:'confortável (mais de 1 h)',seguro:'rota não alaga',isolada:'isolada — a água cortou o caminho até abrigo seco',sem_abrigo:'sem abrigo oficial seco neste nível',sem_rota:'sem rota (sem via mapeada ou sem abrigo seco)'};
const ORDEM=['alagada','ilhada','isolada','sem_abrigo','critica','apertada','atencao','confortavel','seguro','sem_rota'];
ROT.sem_abrigo=`sem ${ABN} seco neste nível`;
if(D.altos){ROT.seguro='fora da água: casa no alto ou caminho que não alaga';ROT.sem_rota='sem avaliação (sem casa ou rua mapeada)';
  ROT.ilhada='ilhada — a água cortou o caminho ou a saída da rua (precisa de apoio)';}
const URG=k=>ORDEM.indexOf(k);
const pior=(x,y)=>URG(x)<=URG(y)?x:y;
// ---------- margem pela rota inteira ----------
function kNivel(h){const hs=NV.hand_m;for(let k=0;k<hs.length;k++)if(hs[k]>=h-1e-6)return k;return hs.length-1;}
function avalia(h){
  const k=kNivel(h),T=NV.tempo_s[k],P=NV.prox[k],taxa=taxaCmH/100/60,n=D.nos.length;
  const f=new Float64Array(n).fill(NaN),g=new Float64Array(n).fill(NaN);
  for(let i=0;i<n;i++){
    if(!isNaN(f[i])||T[i]<0)continue;
    const pilha=[];let j=i,fb=Infinity,gb=Infinity,guard=0;
    while(guard++<20000){
      if(j<0||T[j]<0)break;
      if(!isNaN(f[j])){fb=f[j];gb=g[j];break;}
      pilha.push(j);const nx=P[j];if(nx===j||nx<0)break;j=nx;}
    for(let q=pilha.length-1;q>=0;q--){const x=pilha[q],c=D.cota_no[x];
      if(c!=null){fb=Math.min(fb,(c-h)/taxa+T[x]/60);gb=Math.min(gb,c);}
      f[x]=fb;g[x]=gb;}
  }
  return {k,T,f,g,h,taxa};
}
const faixa=m=>m===Infinity?'seguro':(m-=prepMin)<0?'critica':m<15?'apertada':m<60?'atencao':'confortavel';
// com locais altos, Margem e Quem sai descontam o mesmo erro do modelo do "quando sair" do cartão
// (sem isso, no nível em que o cartão manda sair, a casa aparecia "confortável")
const MARG=D.altos?D.altos.meta.margem_corte_m:0;
const faixaM=(m,A)=>faixa(m-MARG/A.taxa);
// casa fora da mancha mas abaixo da maior água medida (MDT): pode ter alagado em 2023, então não alaga
// depois do nível da mancha, mesmo que o HAND diga que sim
const COTA_EF=D.casas.map((c,ci)=>{const cota=c[CF.cota_alaga];if(!D.altos)return cota;
  const a=D.altos.casas[ci],ac=a[D.altos.meta.casas_campos.indexOf('acima_agua_m')],nm=D.altos.meta.nivel_mancha_m;
  return ac!=null&&ac<0&&D.altos.meta.classes_terreno[a[D.altos.meta.casas_campos.indexOf('terreno')]]!=='dentro'?(cota==null?nm:Math.min(cota,nm)):cota;});
// sem rota agora, mas com rota com o rio baixo (nível 0): se ainda há abrigo oficial seco,
// a água cortou o caminho (isolada); se todos alagaram, falta abrigo (sem_abrigo)
const semAbrigoSeco=A=>D.abrigos.every(a=>a.cota_alaga_m!=null&&a.cota_alaga_m<=NV.hand_m[A.k]);
const semRota=(agora,rioBaixo,A)=>agora<0?(rioBaixo<0?'sem_rota':semAbrigoSeco(A)?'sem_abrigo':'isolada'):null;
function classeNo(i,A){if(A.T[i]<0)return semRota(A.T[i],NV.tempo_s[0][i],A);const c=D.cota_no[i];
  if(c!=null&&c<=A.h)return 'alagada'; if(A.g[i]<=A.h)return 'ilhada'; return faixaM(A.f[i]-A.T[i]/60,A);}
// Margem com locais altos: a rua vale pela melhor saída (abrigo oficial ou ponto alto), como as casas
function classeNoAlto(i,A){if(AL.no_alto[i])return 'seguro';const m=AL.margem_nos[i];if(!m)return null;
  const c=D.cota_no[i],lim=m[1]==null?c:c==null?m[1]:Math.min(m[1],c);if(lim==null)return 'seguro';
  return lim<=A.h?'ilhada':faixaM((lim-A.h)/A.taxa-m[0]/60,A);}
function classeNoMelhor(i,A){const k=classeNo(i,A);if(!AL||k==='alagada')return k;
  const ka=classeNoAlto(i,A);return ka&&(k==='sem_rota'||URG(ka)>URG(k))?ka:k;}
function classeOficial(ci,A){const cota=COTA_EF[ci];
  if(cota!=null&&cota<=A.h)return 'alagada';
  const no=NV.casa_no[A.k][ci],Tc=NV.casa_tempo_s[A.k][ci];
  if(no<0||Tc<0)return semRota(-1,Math.min(NV.casa_no[0][ci],NV.casa_tempo_s[0][ci]),A);
  if(A.g[no]<=A.h||NV.casa_agua_m[A.k][ci]>0)return 'ilhada';
  return faixaM(Math.min(cota==null?Infinity:(cota-A.h)/A.taxa,A.f[no]-Tc/60),A);}
// com locais altos (Santa Tereza), o caminho até o local alto também é saída: vale a melhor das
// duas. Casa no alto fica segura; senão, a margem vai até o nível em que a água corta o caminho
// ou chega na casa (o que vier antes), menos a caminhada.
// casa no alto que fica ilhada no nível conta como precisa de apoio (a rua perdeu a saída seca)
function limCasa(ci){const a=AL.casas[ci],corte=a[ACF.corte_m],cota=COTA_EF[ci];return corte==null?cota:cota==null?corte:Math.min(corte,cota);}
function classeAlto(ci,A){const a=AL.casas[ci],st=AL.meta.estados[a[ACF.estado]],il=a[ACF.ilha_m];
  if(st==='no_alto')return il!=null&&il>=0&&il<=A.h?'ilhada':'seguro';
  if(st!=='rota')return null;
  const lim=limCasa(ci);
  if(lim==null)return 'seguro';
  return lim<=A.h?'ilhada':faixaM((lim-A.h)/A.taxa-a[ACF.tempo_s]/60,A);}
// a melhor das duas saídas; sem abrigo oficial seco ou sem rota oficial, vale o que diz o ponto alto
function classeCasa(ci,A){const k=classeOficial(ci,A);
  if(!AL||k==='alagada')return k;
  const ka=classeAlto(ci,A);
  return ka&&(k==='sem_rota'||k==='sem_abrigo'||URG(ka)>URG(k))?ka:k;}
function classeCel(c,ci,A){
  if(c.casas.length){const cnt={};c.casas.forEach(ci=>{const k=classeCasa(ci,A);cnt[k]=(cnt[k]||0)+1;});return cnt;}
  const no=c.no;let k;
  if(AL&&AL.cel_alta[ci]&&(c.cota==null||c.cota>A.h))return {seguro:1};
  // com locais altos, célula sem casa mapeada (rural) não vai mais ao abrigo oficial por um nó a km
  // de distância: fica sem avaliação, fora da contagem de risco, a não ser que o centro alague
  if(AL&&!(c.cota!=null&&c.cota<=A.h))return {sem_rota:1};
  if(c.cota!=null&&c.cota<=A.h)k='alagada';else if(A.T[no]<0)k=semRota(A.T[no],NV.tempo_s[0][no],A);else if(A.g[no]<=A.h)k='ilhada';
  else k=faixaM(Math.min(c.cota==null?Infinity:(c.cota-A.h)/A.taxa,A.f[no]-A.T[no]/60),A);
  return {[k]:1};}
// ---------- camadas ----------
// A aba Rotas mantém a mancha do cenário de referência. Quem sai usa a mancha correspondente ao slider.
const manchaLayer=L.layerGroup(D.mancha.map(p=>L.polygon(p,{color:'#1f4e9c',weight:1,fillColor:'#1f4e9c',fillOpacity:.18})));
const manchaNivelLayer=L.layerGroup();
const URL_CONTORNOS=M.municipio==='Santa Tereza'?'assets/data/santa_tereza_inundacao/contornos_mancha.json':null;
let contornosNiveis=null, nivelManchaDesenhado=null, manchaErro=null, timerMancha=null;
const rendererMancha=L.canvas({padding:.3});
function poligonoAgua(p){
  return L.polygon(p,{renderer:rendererMancha,interactive:false,color:'#1467b5',weight:1.2,
    fillColor:'#1d76d2',fillOpacity:.30});
}
function atualizarManchaNivel(){
  if(modo!=='impacto')return;
  const h=nivelAtual();
  if(!URL_CONTORNOS){
    if(nivelManchaDesenhado==='referencia')return;
    manchaNivelLayer.clearLayers();
    D.mancha.forEach(p=>manchaNivelLayer.addLayer(poligonoAgua(p)));
    nivelManchaDesenhado='referencia';
    return;
  }
  if(!contornosNiveis){
    // Durante o carregamento: somente a mancha de referência, sem fingir que foi recalculada.
    const chave=h>=M.nivel_projeto_m?'aguardando-referencia':'aguardando-seco';
    if(nivelManchaDesenhado===chave)return;
    manchaNivelLayer.clearLayers();
    if(chave==='aguardando-referencia')D.mancha.forEach(p=>manchaNivelLayer.addLayer(poligonoAgua(p)));
    nivelManchaDesenhado=chave;
    return;
  }
  const nivel=contornosNiveis.niveis.filter(v=>v<=h+1e-6).at(-1);
  if(nivelManchaDesenhado===nivel)return;
  if(timerMancha!==null)clearTimeout(timerMancha);
  const nivelSolicitado=nivel;
  timerMancha=setTimeout(()=>{
    timerMancha=null;
    if(modo!=='impacto'||Math.abs(nivelAtual()-h)>.01)return;
    manchaNivelLayer.clearLayers();
    if(nivelSolicitado!==undefined){
      const fs=contornosNiveis.porNivel.get(nivelSolicitado)||[];
      L.geoJSON({type:'FeatureCollection',features:fs},{renderer:rendererMancha,interactive:false,
        style:{color:'#1467b5',weight:1,fillColor:'#1d76d2',fillOpacity:.30}})
        .eachLayer(layer=>manchaNivelLayer.addLayer(layer));
    }
    nivelManchaDesenhado=nivelSolicitado;
  },90);
}
function carregarManchaPorNivel(){
  if(!URL_CONTORNOS)return;
  fetch(URL_CONTORNOS,{cache:'force-cache'}).then(r=>{
    if(!r.ok)throw Error('HTTP '+r.status);
    return r.json();
  }).then(geo=>{
    if(!Array.isArray(geo.features)||!geo.features.length)throw Error('Contornos vazios');
    const porNivel=new Map();
    for(const f of geo.features){
      const n=Number(f?.properties?.nivel_m);
      if(!Number.isFinite(n)||!f.geometry)continue;
      if(!porNivel.has(n))porNivel.set(n,[]);
      porNivel.get(n).push(f);
    }
    if(!porNivel.size)throw Error('Contornos sem níveis');
    contornosNiveis={niveis:[...porNivel.keys()].sort((a,b)=>a-b),porNivel,
      referencialValidado:geo.metadata?.river_reference_method==='eixo_dominante_taquari_D8'};
    nivelManchaDesenhado=null;manchaErro=null;
    atualizarManchaNivel();
    if(modo==='impacto'){renderImpacto();alertaNivel();}
  }).catch(e=>{
    manchaErro='não foi possível baixar a mancha por nível; tenta de novo ao voltar a esta aba';
    carregouContornos=false;
    if(modo==='impacto'){renderImpacto();alertaNivel();}
  });
}
const b=L.latLngBounds();
const ruas=D.edges.map(e=>{const A=D.nos[e[0]],C=D.nos[e[1]];
  return {pl:L.polyline([A,C],{weight:2,opacity:.85}),a:e[0],c:e[1],ag:e[2],pe:e[3],cz:e[4]};});
const ruasLayer=L.layerGroup(ruas.map(r=>r.pl));
// Células IBGE: somente base estatística. Não desenhar polígonos/quadrados nem enquadrar o
// mapa por elas (as rurais, a quilômetros, deixavam a cidade pequena atrás do painel).
const cv=L.canvas({padding:.3});
let casaCl=[];
const casasImp=D.casas.map((c,ci)=>L.circleMarker([c[CF.lat],c[CF.lon]],{renderer:cv,radius:3.6,weight:1,color:'#1b2620',fillOpacity:.95})
  .bindPopup(()=>{const k=casaCl[ci],p=c[CF.pessoas],cota=COTA_EF[ci];
    return `<span class="sw" style="background:${CORES[k]}"></span><b>${ROT[k]}</b><br>`+
      (p==null?'Fora das células com moradores no Censo 2022':`~${fm(p)} pessoas (IBGE 2022)`)+
      (cota!=null?`<br>${cota!==c[CF.cota_alaga]?'Pode alagar':'Alaga'} a partir de ${txtNivel(cota)}.`:'<br>Não alaga até o nível mapeado.');}));
const casasImpLayer=L.layerGroup(casasImp);
const txtDemanda=dm=>!dm?'':`<br>Demanda no cenário: ~<b>${dm.pessoas}</b> pessoas de ${dm.casas} casas na água`+
  (dm.casas_isoladas?` + ~${dm.pessoas_isoladas} de ${dm.casas_isoladas} casas isoladas`:'')+
  (dm.casas_fora_censo?` (${dm.casas_fora_censo} casas sem moradores no Censo 2022 contam 0)`:'')+'.';
const MOT={tempo:m=>`${m} passam de ${M.tempo_max_min||30} min até o abrigo oficial`,sem_rota:m=>`${m} sem caminho até abrigo oficial`,ilhada:m=>`${m} ilhadas (rota cruza água)`};
const txtMotivos=cd=>Object.entries(cd.motivos||{}).map(([k,v])=>(MOT[k]||(m=>m+' '+k))(v)).join(', ');
const abrigos=L.layerGroup(D.abrigos.map(a=>L.marker([a.lat,a.lon],{title:a.nome,alt:a.nome}).bindPopup('<b>'+esc(a.nome)+'</b><br>'+(AB_OFICIAL?'abrigo / ponto de encontro oficial':'ponto de referência do município — <b>não confirmado pela Defesa Civil</b>')+
  txtValidade(a.cota_alaga_m)+txtDemanda(a.demanda)+txtCapacidade(a))));
D.abrigos.forEach(a=>b.extend([a.lat,a.lon]));
const candLayer=L.layerGroup((D.candidatos||[]).map(cd=>L.circleMarker([cd.lat,cd.lon],{radius:10,color:'#5b2a86',weight:3,dashArray:'4 3',fillColor:'#d9c6f0',fillOpacity:.7})
  .bindPopup(`<b>Local candidato</b> (não oficial)<br>Grupo de ${cd.n_casas} casas: ${txtMotivos(cd)}.<br>`+
    (cd.pior_antes_min!=null&&cd.pior_depois_min!=null?`Pior tempo: ${Math.round(cd.pior_antes_min)} → ${Math.round(cd.pior_depois_min)} min.<br>`:
     cd.pior_depois_min!=null?`Pior tempo até aqui: ${Math.round(cd.pior_depois_min)} min.<br>`:'')+
    `Rampa ${Math.round((cd.rampa||0)*100)}%`+txtValidade(cd.cota_alaga_m)+
    txtDemanda(cd.demanda)+`<br><i>Capacidade não avaliada. Validar com a Defesa Civil.</i>`)));
// locais altos (locais_altos.py): o que ficou fora da mancha da maior cheia registrada, visto no
// MDT; terreno "alto" = pelo menos meta.folga_m acima do nível da água
const AL=D.altos||null,ACF=AL?Object.fromEntries(AL.meta.casas_campos.map((k,i)=>[k,i])):{};
const TER=AL?{alto:['#1b7f3b','terreno alto: fora da água de '+AL.meta.cheia.rotulo+', '+fm(AL.meta.folga_m)+' m ou mais acima dela'],
  sem_folga:['#f6c445','fora da mancha, mas sem '+fm(AL.meta.folga_m)+' m de folga sobre a água estimada (pode ter ficado perto ou abaixo dela)'],
  abaixo_da_agua:['#c62828','fora da mancha, mas abaixo do nível da água (aterro ou barreira no modelo): pode ter alagado']}:{};
const popOpt=()=>innerWidth<=700?{maxWidth:300,autoPanPaddingBottomRight:L.point(10,Math.round(innerHeight*.6))}:{maxWidth:320,autoPanPaddingTopLeft:L.point(350,10)};
const terrenoLayer=AL&&AL.terreno?L.imageOverlay(AL.terreno.png,AL.terreno.limites,{interactive:false,alt:'Terreno alto e baixo fora da mancha de '+AL.meta.cheia.rotulo}):L.layerGroup();
const fmMin=m=>m==null?'—':fmin(m*60);
const reg=h=>fm(h+ZR)+' m';
const fmDist=m=>m<1000?Math.round(m/10)*10+' m':fm2(m/1000)+' km';
// nível da ilha: null = não vira ilha até o topo do modelo; -1 = sem rua mapeada até uma saída da cidade
const ilhaTxt=v=>v<0?'não tem rua mapeada até o resto da cidade':'vira ilha com o rio em '+reg(v);
const ilhado=v=>v!=null&&v<=AL.meta.nivel_mancha_m;
const PERTO={dentro:' — alagou em 2023',abaixo_da_agua:' — pode ter alagado em 2023',sem_folga:' — a água passou perto em 2023'};
function txtAlto(l,j){const ch=AL.meta.cheia;
  return `<b>Ponto alto ${j+1}</b>${l.rua?' · '+esc(l.rua):''}`+
    (l.perto.length?`<br>Perto de: ${l.perto.map(p=>`${esc(p.nome)} (${p.m} m${PERTO[p.terreno]||''})`).join(', ')}.`:'')+
    `<br>Em ${ch.rotulo}, a maior cheia registrada, a água ficou cerca de <b>${fm(l.acima_agua_m)} m abaixo</b> deste ponto (estimativa do modelo, ±1 m).`+
    (ilhado(l.ilha_m)?`<br><b style="color:#9e1b1b">Atenção: ${ilhaTxt(l.ilha_m)}.</b> Quem ficar aqui fica sem saída seca até a água baixar.`:'')+
    (l.encosta_graus!=null&&l.encosta_graus>=AL.meta.encosta_graus_aviso?`<br><b style="color:#9a3412">Barranco ou encosta íngreme por perto</b> (até ${Math.round(l.encosta_graus)}° a menos de 100 m): em chuva forte, fique longe do pé do morro e da beira do barranco.`:'')+
    `<br>É o ponto alto mais perto para ${l.n_casas} casas (${l.pessoas?'~'+l.pessoas+' pessoas no Censo 2022':'sem moradores no Censo 2022 — conferir no local'}): mediana de ${fmMin(l.tempo_mediano_min)}, no máximo ${fmMin(l.tempo_max_min)} a pé no passo de um idoso.`+
    '<br><b>Não é abrigo oficial:</b> não tem garantia de espaço, cobertura ou atendimento. Em perigo: 199 (Defesa Civil) ou 193.'+
    `<details><summary>Detalhes técnicos</summary>Terreno a pelo menos ${fm(l.altitude_m)} m num raio de 15 m (LiDAR 10 m); água de referência de ${ch.rotulo} ${fm(l.agua_m)} m `+
    `(régua ${fm2(ch.regua_m)} m na telemetria; ${fm2(ch.regua_sgb_m)} m pelo SGB). Pelo HAND, ${l.cota_alaga_m==null?`não alaga até o topo do modelo, ${txtNivel(M.nivel_max_m)}`:`alaga a partir de ${txtNivel(l.cota_alaga_m)}`}. `+
    'Sugestão técnica do PREVINE para a Defesa Civil avaliar.</details>';}
const altosLayer=L.layerGroup(AL?AL.locais.map((l,j)=>L.marker([l.lat,l.lon],{title:'Ponto alto '+(j+1),alt:'Ponto alto '+(j+1),
  icon:L.divIcon({className:'alto-ic',html:`<i></i><b>${j+1}</b>`,iconSize:[32,28],iconAnchor:[16,25],popupAnchor:[0,-22]})}).bindPopup(()=>txtAlto(l,j),popOpt())):[]);
const cheiaLayer=L.layerGroup(AL&&AL.mancha_cheia?AL.mancha_cheia.poligonos.map(p=>L.polygon(p,{color:'#0b3d91',weight:2,dashArray:'6 4',fill:false,interactive:false})):[]);
if(AL)AL.locais.forEach(l=>b.extend([l.lat,l.lon]));
const ex=document.getElementById('extra');
if(AL||M.link_extra){ex.classList.remove('hide');
  ex.innerHTML=(AL?`<b>Terreno alto</b> (verde, aba Rotas): o que ficou fora da água de ${AL.meta.cheia.rotulo}, a maior cheia registrada, com pelo menos ${fm(AL.meta.folga_m)} m de folga. <b>▲</b> ${AL.locais.length} pontos altos sugeridos (não são abrigos); toque numa casa para ver para onde ir e quando sair.`:'')+
    (M.link_extra?`${AL?'<br>':''}<a href="${esc(M.link_extra.href)}">${esc(M.link_extra.texto)}</a>`:'');}
const EST={excede:['#6b1a1a','#c0392b'],ilhada:['#4b2c78','#a689d6'],sem_rota:['#666','#c5c5c5']};
const casasLayer=L.layerGroup(D.casas.map(c=>{b.extend([c[CF.lat],c[CF.lon]]);const st=c[CF.situacao]||'ok',dn=c[CF.na_mancha];
  const [cor,fill]=AL?['#3d4a44','#f4f7f5']:EST[st]||(dn?['#9a3412','#e8730c']:['#3d4a44','#f4f7f5']);
  return L.circleMarker([c[CF.lat],c[CF.lon]],{radius:AL?3:dn||st!=='ok'?4:2.6,weight:1,color:cor,fillColor:fill,fillOpacity:.85,interactive:false});}));
const BB=b.pad(0.04);function aj(){map.invalidateSize();
  map.fitBounds(BB,innerWidth<=700?{paddingBottomRight:[0,Math.round(innerHeight*.2)]}:{paddingTopLeft:[350,0]});}
// ---------- render ----------
let modo=M.modos[0];
const sld=document.getElementById('sld'),sldTaxa=document.getElementById('sldTaxa');
sld.max=Math.round(M.nivel_max_m*10);sld.value=Math.round(Math.max(0,M.nivel_projeto_m)*10);sldTaxa.value=M.taxa_cm_h;
document.getElementById('selPrep').value=String(prepMin);sld.setAttribute('aria-valuetext',txtNivel(nivelAtual()));
document.getElementById('cheias').innerHTML=CHEIAS.length?'<span>Cheias:</span>'+CHEIAS.map((c,i)=>
  `<button type="button" data-i="${i}" title="${c.nota||''}">${c.rotulo} · ${fm2(c.regua_m)} m</button>`).join(''):'';
document.querySelectorAll('#cheias button').forEach(bt=>bt.onclick=()=>{
  sld.value=Math.min(+sld.max,Math.ceil((CHEIAS[+bt.dataset.i].regua_m-ZR)*10-1e-6));redraw();});
function nivelAtual(){return sld.value/10;}
function legenda(cnt,fmt){return ORDEM.filter(k=>cnt[k]>0).map(k=>`<div class="row"><span><span class="sw" style="background:${CORES[k]}"></span>${ROT[k]}</span><b>${fmt(cnt[k])}</b></div>`).join('');}
function renderRotas(){
  // com locais altos o mapa mostra a cheia de referência (tracejado) e não o cenário de 15 m: o azul e
  // as ruas vermelhas do cenário, sem legenda à vista, faziam quem está fora deles se achar seguro
  ruas.forEach(r=>{const ag=r.ag&&!AL;r.pl.setStyle({color:ag?'#b3382c':'#8fa7b8',weight:ag?2.5:1.5,opacity:ag?.75:.55,dashArray:r.pe?'3 4':null});});
  const cen=(M.rotulo_nivel||txtNivel(M.nivel_projeto_m)).replace(/^cenário de /,'');
  const oficial='<span><i style="background:#0f8b46"></i>rota sem água até o '+ABN+'</span><span><i class="tr"></i>trecho que alaga ('+cen+')</span>';
  document.getElementById('painel').innerHTML=AL?
    `<div class="sub">Toque na sua casa (aproxime o mapa) para ver para onde ir e quando sair.</div>${BT_LOCAL}<div class="rota" id="rota" aria-live="polite">—</div>${avisoCheia()}`+
    `<div class="leg-rota"><span><i class="tri"></i>ponto alto (não é abrigo)</span><span><i style="background:#5b2a86"></i>caminho até o ponto alto</span>`+
    `<span><i style="background:#2a81cb"></i>${ABN} (pino azul)</span><span><i class="c23"></i>limite da água em ${AL.meta.cheia.rotulo}</span>`+
    `<span><i style="background:${TER.alto[0]};height:10px;opacity:.6"></i>terreno alto</span></div>`+
    `<details class="leg-mais"><summary>Mais camadas</summary><div class="leg-rota">${oficial}`+
    Object.entries(TER).filter(([k])=>k!=='alto').map(([,[c,t]])=>`<span><i style="background:${c};height:10px;opacity:.75"></i>${t}</span>`).join('')+'</div></details>':
    `<div class="sub">Cenário: ${cen}. Toque numa casa para ver a rota a pé (idoso, com subidas) até o abrigo mais próximo.</div>${BT_LOCAL}${avisoCheia()}<div class="leg-rota">${oficial}`+
    ((D.candidatos||[]).length?'<span><i style="background:#5b2a86"></i>até local candidato (não oficial)</span>':'')+
    '<span><i style="background:#2a81cb"></i>'+ABN+' (pino azul)</span></div><div class="rota" id="rota" aria-live="polite">—</div>';
}
const BT_LOCAL='geolocation' in navigator?'<button type="button" class="bt-local" id="btLocal">Usar minha localização</button>':'';
function renderMargem(){const A=avalia(nivelAtual());const cnt={};
  const cl=D.nos.map((_,i)=>classeNoMelhor(i,A));
  ruas.forEach(r=>{let k=pior(cl[r.a],cl[r.c]);if(r.cz!=null&&r.cz<=A.h)k='alagada';cnt[k]=(cnt[k]||0)+1;
    r.pl.setStyle({color:CORES[k],weight:k==='seguro'?1.5:3,opacity:.9,dashArray:null});});
  document.getElementById('nvtxt').textContent=txtNivel(A.h);
  document.getElementById('painel').innerHTML='<div class="sub">Ruas pela margem: quanto tempo ainda dá para esperar antes de sair a pé (trechos de rua por faixa).</div>'+legenda(cnt,v=>v)+
    `<div class="nota">Margem = menor folga ao longo da rota até o abrigo: tempo até a água chegar em cada ponto − tempo do idoso para chegar nele − ${prepMin} min de preparo`+
    (MARG?` − o que o rio sobe em ${fm(MARG)} m de erro do modelo (o mesmo desconto do "quando sair" do cartão)`:'')+'.</div>';
}
const RISCO=['alagada','ilhada','isolada','sem_abrigo','critica','apertada','atencao'];
function renderImpacto(){const A=avalia(nivelAtual());const cnt={};
  casaCl=D.casas.map((_,ci)=>classeCasa(ci,A));
  casasImp.forEach((m,ci)=>m.setStyle({fillColor:CORES[casaCl[ci]],radius:RISCO.includes(casaCl[ci])?4.2:3}));
  D.cells.forEach((c,ci)=>{const inf=classeCel(c,ci,A);const tot=Object.values(inf).reduce((s,v)=>s+v,0);
    if(tot>0)for(const k in inf)cnt[k]=(cnt[k]||0)+c.pop*inf[k]/tot;});
  document.getElementById('nvtxt').textContent=txtNivel(A.h);
  const risco=RISCO.reduce((s,k)=>s+(cnt[k]||0),0),casasRisco=casaCl.filter(k=>RISCO.includes(k)).length;
  document.getElementById('painel').innerHTML=legenda(cnt,v=>Math.round(v).toLocaleString('pt-BR'))+
    `<div class="big"><b>${Math.round(risco).toLocaleString('pt-BR')}</b> pessoas precisam sair ou de apoio · de <b>${M.pop_total.toLocaleString('pt-BR')}</b>`+
    ` (<b>${casasRisco.toLocaleString('pt-BR')}</b> de ${D.casas.length.toLocaleString('pt-BR')} casas mapeadas)</div>`+
    '<div class="nota"><b>Água azul:</b> mancha simulada no nível selecionado da régua. '+
    (!URL_CONTORNOS?'Mancha do cenário de referência (sem atualização por nível). ':
      !contornosNiveis?(manchaErro?'Contornos por nível indisponíveis ('+manchaErro+'); referência fixa quando exibida. ':
        'Carregando contornos por nível; referência fixa provisória quando exibida. '):
      '')+
    (URL_CONTORNOS?'Os contornos do remanso do Marrecão ainda precisam de reprocessamento e validação hidráulica; a representação é exploratória. ':'')+
    'Cada ponto representa uma edificação do OpenStreetMap. As células IBGE permanecem nos cálculos populacionais, mas não são desenhadas. Pontos não são domicílios verificados.</div>';
}
function cenTaxa(t){return t<40?'(cheia lenta)':t<90?'':t<150?'(média de set/2023 e de 22/07/2026)':t<190?'(acima da média observada)':'(trechos mais rápidos de set/2023, ~2 m/h)';}
function alertaNivel(){if(modo==='rotas')return;const h=nivelAtual(),k=kNivel(h);
  const al=D.abrigos.filter(a=>a.cota_alaga_m!=null&&a.cota_alaga_m<=NV.hand_m[k]).map(a=>esc(a.nome));
  if(al.length)document.getElementById('painel').insertAdjacentHTML('afterbegin',
    `<div class="aviso">${al.length===D.abrigos.length?`<b>Nenhum ${ABN} fica seco neste nível.</b> `:''}Alaga(m): ${al.join(', ')}.`+
    (AL?' '+txtPontosSecos(NV.hand_m[k]):'')+'</div>');
  if(h>=M.nivel_max_m)document.getElementById('painel').insertAdjacentHTML('afterbegin',
    `<div class="aviso">Acima de ${txtNivel(M.nivel_max_m)} o modelo não tem mancha: a área que alaga fica subestimada.</div>`);}
// pontos altos secos no nível, separando os que já perderam a saída seca (ilha): "9 de 9 secos" escondia 4 ilhados
function txtPontosSecos(hk){const sec=AL.locais.filter(l=>l.cota_alaga_m==null||l.cota_alaga_m>hk);
  const il=sec.filter(l=>l.ilha_m!=null&&l.ilha_m<=hk);
  return `Pontos altos (▲) secos neste nível: ${sec.length} de ${AL.locais.length}`+
    (il.length?`; ${il.length} deles já sem saída seca (ilhados): ${il.map(l=>AL.locais.indexOf(l)+1).join(', ')}.`:'.');}
function redraw(){taxaCmH=+sldTaxa.value;document.getElementById('taxatxt').textContent=taxaCmH;sld.setAttribute('aria-valuetext',txtNivel(nivelAtual()));
  document.getElementById('taxacen').textContent=cenTaxa(taxaCmH);
  if(modo==='margem')renderMargem();else if(modo==='impacto'){atualizarManchaNivel();renderImpacto();}alertaNivel();}
// ---------- rotas: clique ----------
function m2(la1,lo1,la2,lo2){const dy=(la1-la2)*110540,dx=(lo1-lo2)*111320*Math.cos(la1*Math.PI/180);return dy*dy+dx*dx;}
function fmin(s){const m=Math.max(1,Math.round(s/60));return m<60?m+' min':Math.floor(m/60)+' h '+String(m%60).padStart(2,'0')+' min';}
function cadeia(ini,prox,pts){let i=ini,g=0;while(i>=0&&g++<6000){pts.push(D.nos[i]);const nx=prox[i];if(nx===i||nx<0)break;i=nx;}return pts;}
// trecho que alaga no cenário sai em vermelho tracejado; verde só no seco
const ARESTA=new Map();D.edges.forEach(e=>{ARESTA.set(e[0]+','+e[1],e);ARESTA.set(e[1]+','+e[0],e);});
function rotaPorTrecho(casa,op){const g=L.featureGroup();let molhado=!!casa[CF.na_mancha],i=casa[CF.no],n=0;
  let seg=[[casa[CF.lat],casa[CF.lon]],[casa[CF.proj_lat],casa[CF.proj_lon]],D.nos[i]];
  const fecha=()=>{if(seg.length<2)return;L.polyline(seg,{color:'#fff',weight:molhado?10:9,opacity:op}).addTo(g);
    L.polyline(seg,molhado?{color:'#b3241b',weight:6,opacity:op,dashArray:'10 6'}:{color:'#0f8b46',weight:5,opacity:op}).addTo(g);};
  while(i>=0&&n++<6000){const nx=D.prox[i];if(nx===i||nx<0)break;const e=ARESTA.get(i+','+nx),m=!!(e&&e[2]>0);
    if(m!==molhado){fecha();seg=[D.nos[i]];molhado=m;}seg.push(D.nos[nx]);i=nx;}
  fecha();return g;}
// nível em que a água corta a rota até o abrigo oficial (rotas por nível). casa_agua_m
// vem arredondado em metros: olha também a cota dos nós da rota, como a margem.
function cortaNoNivel(ci,k){const no=NV.casa_no[k][ci];if(no<0||NV.casa_agua_m[k][ci]>0)return true;
  const P=NV.prox[k];let j=no,g=0;
  while(j>=0&&g++<6000){const c=D.cota_no[j];if(c!=null&&c<=NV.hand_m[k])return true;const nx=P[j];if(nx===j||nx<0)break;j=nx;}
  return false;}
// nível da régua para sair: onde a água corta o caminho (ou chega na casa) menos o erro do modelo
// e menos o que o rio sobe durante o preparo e a caminhada (seletor de preparo e subida do painel)
function regSair(lim,tempoS,prep=prepMin){const y=lim-AL.meta.margem_corte_m-(prep+tempoS/60)/60*(taxaCmH/100);
  return Math.floor((y+ZR)*10)/10;}
// nível em que a água corta o caminho até o abrigo oficial (rotas por nível); null = não corta
function corteOficial(ci){const hs=NV.hand_m;let k=0;while(k<hs.length&&!cortaNoNivel(ci,k))k++;
  return k>=hs.length?null:k>0?hs[k-1]:0;}
const roxo=(pts,trac)=>L.featureGroup([L.polyline(pts,{color:'#fff',weight:10,opacity:.95}),
  L.polyline(pts,{color:'#5b2a86',weight:6,opacity:.95,dashArray:trac?'10 8':null})]);
// cartão da casa: uma instrução só, em ordem de decisão; o abrigo oficial e os números vão para os detalhes
function cartao(casa,ci){const a=AL.casas[ci],st=AL.meta.estados[a[ACF.estado]],ch=AL.meta.cheia,fol=AL.meta.folga_m;
  const ter=AL.meta.classes_terreno[a[ACF.terreno]],ac=a[ACF.acima_agua_m],cota=COTA_EF[ci],il=a[ACF.ilha_m],RIO=rioAtual();
  const ab=D.abrigos[0],abAlaga=ab&&ab.cota_alaga_m!=null&&ab.cota_alaga_m<=AL.meta.nivel_mancha_m;
  const inicio=[[casa[CF.lat],casa[CF.lon]],[casa[CF.proj_lat],casa[CF.proj_lon]]];
  let sua=st==='no_alto'?`Fica no alto. Em ${ch.rotulo}, a maior cheia registrada, a água ficou cerca de ${fm(ac)} m abaixo daqui (estimativa do modelo).`:
    ter==='dentro'?`Em ${ch.rotulo}, a maior cheia registrada, a água chegou aqui`+(ac!=null&&ac<0?` (cerca de ${fm(-ac)} m de água, estimativa do modelo)`:'')+'.':
    ter==='abaixo_da_agua'?`Fica fora da mancha do modelo, mas abaixo do nível da água de ${ch.rotulo}: pode ter alagado.`:
    ter==='sem_folga'?(ac!=null&&ac<0?`Fica abaixo da maior água medida em ${ch.rotulo}: pode ter alagado.`:`Em ${ch.rotulo} a água passou a menos de ${fm(fol)} m daqui.`):'Sem dado de terreno.';
  if(cota!=null&&st!=='no_alto')sua+=cota!==casa[CF.cota_alaga]?` Conte com água a partir de ${reg(cota)} na régua (o nível de ${ch.rotulo}) ou antes.`:` Alaga com o rio em ${reg(cota)} na régua.`;
  let para,quando,evite='',cam=null,camAlt=null,tec='';
  const remedio=(nivel,tempoS,onde)=>{const ys=regSair(nivel,tempoS);
    return RIO!=null&&RIO>=nivel+ZR?` <b>A saída seca já pode ter sido cortada</b> (rio em ${fm2(RIO)} m): quem depende de remédio, oxigênio ou diálise deve ligar para a Defesa Civil (199) e pedir remoção.`:
      RIO!=null&&RIO>=ys?` <b>Quem depende de remédio, oxigênio ou diálise deve sair agora</b>: o rio já está em ${fm2(RIO)} m, acima de ${fm(ys)} m.`:
      ` Quem depende de remédio, oxigênio ou diálise deve sair antes de o rio chegar a <b>${fm(ys)} m</b> ${onde}.`;};
  if(st==='no_alto'){
    if(ilhado(il))sua+=` A rua ${ilhaTxt(il)}: tenha água, comida e remédios para alguns dias.`;
    para='fique em casa ou num lugar alto perto. Não desça para as partes baixas.';
    quando=`numa cheia como a de ${ch.rotulo}, não precisa sair.`+
      (ilhado(il)&&il>=0?remedio(il,a[ACF.ilha_tempo_s]||0,'e ir para fora da área que fica ilhada (combine com a Defesa Civil, 199)'):'');
    if(ab)evite=`descer até o ${esc(ab.nome)}`+(abAlaga?`: ele fica dentro da água de ${ch.rotulo}.`:'.');
  }else if(st!=='rota'){
    para='não há rua mapeada até um ponto alto. Combine a saída com a Defesa Civil (199).';
    quando='quando a Defesa Civil mandar.';
  }else{
    const j=a[ACF.local],l=j>=0?AL.locais[j]:null,corte=a[ACF.corte_m],lim=limCasa(ci),rp=a[ACF.rampa_pct];
    cam=roxo([...inicio,...a[ACF.rota].map(i=>D.nos[i])],false);
    para=(l?`<b>ponto alto ${j+1}</b>${l.rua?' ('+esc(l.rua)+')':''}`:'<b>o terreno alto mais perto</b> (não é um dos pontos sugeridos)')+
      `, a ${fmDist(a[ACF.dist_m])}: cerca de ${fmin(a[ACF.tempo_s])} a pé no passo de um idoso (linha roxa).`+
      (l&&ilhado(l.ilha_m)?` Atenção: ele ${ilhaTxt(l.ilha_m)}.`:'')+
      (rp!=null&&rp>8.33?` O caminho tem trecho íngreme (${rp}% em ${AL.meta.rampa_trecho_m} m; o limite para cadeira de rodas é 8,33%): quem usa cadeira ou andador vai precisar de ajuda ou de carro.`:'');
    if(a[ACF.alt_local]!=null){const k2=a[ACF.alt_local],l2=AL.locais[k2],c2=a[ACF.alt_corte_m];
      const lim2=c2==null?cota:cota==null?c2:Math.min(c2,cota);
      camAlt=roxo([...inicio,...a[ACF.alt_rota].map(i=>D.nos[i])],true);
      para+=` Melhor ainda, se der tempo: o <b>ponto ${k2+1}</b>${l2.rua?' ('+esc(l2.rua)+')':''}, que não fica ilhado, a ${fmin(a[ACF.alt_tempo_s])} a pé (linha roxa tracejada)`+
        (lim2!=null?`; para ir até ele, saia antes de o rio chegar a ${fm(regSair(lim2,a[ACF.alt_tempo_s]))} m.`:'.');}
    if(lim==null)quando='o caminho não alaga até o topo do modelo: saia quando a Defesa Civil mandar.';
    else{const y=regSair(lim,a[ACF.tempo_s]),sit=situacaoSaida(lim,cota,y,RIO,ZR);
      quando=sit==='casa_atingida'?`<b>a água já pode ter chegado aqui</b> (rio em ${fm2(RIO)} m). Não entre na água: suba para o ponto mais alto da casa ou de um vizinho e ligue 193 ou 199.`:
        sit==='caminho_cortado'?`<b>a água já pode ter cortado o caminho</b> (rio em ${fm2(RIO)} m; corta com ${reg(lim)}). Não entre na água: fique no ponto mais alto da casa ou de um vizinho e ligue 193 ou 199.`:
        sit==='agora'?`<b>agora</b>: o rio já está em ${fm2(RIO)} m na régua, acima de ${fm(y)} m.`:
        sit==='alerta'?'<b>assim que houver alerta de cheia</b>: o caminho alaga cedo.':`<b>quando o rio chegar a ${fm(y)} m na régua</b>, ou antes se a Defesa Civil mandar.`;
      if(sit==='nivel'){const mais=[[60,'à noite (1 h para se preparar)'],[120,'com acamado ou cadeirante (2 h)']].filter(([p])=>p>prepMin);
        if(mais.length)quando+=' '+mais.map(([p,t])=>`${t[0].toUpperCase()+t.slice(1)}: com ${fm(regSair(lim,a[ACF.tempo_s],p))} m.`).join(' ');}
      if(l&&ilhado(l.ilha_m)&&l.ilha_m>=0&&a[ACF.alt_local]==null)
        quando+=remedio(Math.min(l.ilha_m,lim),a[ACF.tempo_s],`: o ponto ${j+1} fica ilhado com o rio em ${reg(l.ilha_m)}; combine com a Defesa Civil (199) a ida para fora da área`);
      quando+=(lim>AL.meta.nivel_mancha_m?` Numa cheia como a de ${ch.rotulo} a água chega perto: saia por precaução.`:'')+
        `<br><span class="nota">A água corta o caminho com o rio em ${reg(lim)}; já estão descontados ${prepMin} min de preparo, a caminhada, a subida de ${taxaCmH} cm/h e ${fm(AL.meta.margem_corte_m)} m de erro do modelo.</span>`;
      tec=`<br>Ponto alto: caminho cortado em ${txtNivel(lim)}${corte!=null&&cota!=null&&corte<cota?' (antes de a água chegar na casa)':''}.`;}
    if(ab){const co=casa[CF.no]<0?null:corteOficial(ci);
      evite=casa[CF.no]<0?`ir até o ${esc(ab.nome)}: não há rua mapeada até ele daqui.`:
        `ir a pé até o ${esc(ab.nome)}`+(abAlaga?`: ele fica dentro da água de ${ch.rotulo}`:'')+(co!=null&&(lim==null||co<lim)?`${abAlaga?',':':'} e o caminho até ele alaga antes, com o rio em ${reg(co)}`:'')+'.';}
  }
  if(ac!=null)tec+=`<br>Terreno da casa: ${ac>=0?fm(ac)+' m acima':fm(-ac)+' m abaixo'} da água de referência de ${ch.rotulo} (LiDAR 10 m).`;
  return {cam,camAlt,tec,html:`<div class="cartao"><p><b>Sua casa:</b> ${sua}</p><p><b>Para onde ir:</b> ${para}</p><p><b>Quando sair:</b> ${quando}</p>`+
    (evite?`<p><b>Evite:</b> ${evite}</p>`:'')+
    '<p class="nota">A casa escolhida tem um círculo verde no mapa: confira se é a sua. '+
    (st==='rota'?'O ponto alto não é abrigo oficial: não tem garantia de espaço, cobertura ou atendimento. Chegando lá, avise a Defesa Civil (199).':'Em perigo: 199 (Defesa Civil) ou 193.')+'</p></div>'};}
// a casa é ilhada no cenário: o corte nunca fica acima do nível do cenário
function txtCorte(ci){const hs=NV.hand_m,kp=kNivel(M.nivel_projeto_m);let k=0;
  while(k<kp&&!cortaNoNivel(ci,k))k++;
  return k>0?` A água corta a rota entre ${txtNivel(hs[k-1])} e ${txtNivel(hs[k])}: <b>sair antes de ${txtNivel(hs[k-1])}</b>.`:' A rota já é cortada pela água com o rio baixo.';}
let cam=null,camC=null,camA=null,camAlt=null,orig=null,casaSel=-1;
function limpaCasa(){[cam,camC,camA,camAlt,orig].forEach(l=>{if(l)map.removeLayer(l);});cam=camC=camA=camAlt=orig=null;}
// toque com o mapa longe: 1 px passa de 8 m e o dedo pegaria a casa do vizinho; primeiro aproxima
const ZOOM_CASA=matchMedia('(pointer:coarse)').matches?17:16;
const avisoMapa=(ll,txt)=>L.popup({maxWidth:260}).setLatLng(ll).setContent(txt).openOn(map);
function casaPerto(ll){let bc=1e18,ci=-1;D.casas.forEach((c,i)=>{const d=m2(ll.lat,ll.lng,c[CF.lat],c[CF.lon]);if(d<bc){bc=d;ci=i;}});return [ci,Math.sqrt(bc)];}
map.on('click',e=>{if(modo!=='rotas')return;
  if(map.getZoom()<ZOOM_CASA){map.flyTo(e.latlng,ZOOM_CASA+1);avisoMapa(e.latlng,'Aproximei o mapa para você escolher a casa certa: toque de novo em cima da sua casa.');return;}
  const [ci,d]=casaPerto(e.latlng);
  if(ci<0||d>60){limpaCasa();casaSel=-1;document.getElementById('rota').textContent='—';
    avisoMapa(e.latlng,'Nenhuma casa a menos de 60 m daqui: toque em cima da sua casa.');return;}
  map.closePopup();mostraCasa(ci,true);});
// no celular a folha abre no cartão e o mapa enquadra a casa e o caminho na parte que sobra
function enquadra(){const hud=document.getElementById('hud'),cel=innerWidth<=700;
  if(cel)dobra(true);
  setTimeout(()=>{const r=document.getElementById('rota');
    if(r)hud.scrollTop+=r.getBoundingClientRect().top-document.getElementById('topo').getBoundingClientRect().bottom-6;
    const bb=L.featureGroup([orig,camA||cam].filter(Boolean)).getBounds();
    if(cel)map.fitBounds(bb,{paddingTopLeft:[24,24],paddingBottomRight:[24,hud.offsetHeight+16],maxZoom:17});
    else if(!map.getBounds().contains(bb))map.fitBounds(bb,{paddingTopLeft:[hud.offsetWidth+30,24],paddingBottomRight:[60,24],maxZoom:17});},0);}
function mostraCasa(ci,novo){desenhaCasa(ci);if(novo)enquadra();}
aoMudarRio=()=>{if(modo==='rotas'&&casaSel>=0)mostraCasa(casaSel,false);};
function desenhaCasa(ci){const casa=D.casas[ci];limpaCasa();casaSel=ci;
  const RA=AL?cartao(casa,ci):null;if(RA&&RA.camAlt)camAlt=RA.camAlt.addTo(map);if(RA&&RA.cam)camA=RA.cam.addTo(map);
  const saida=html=>{document.getElementById('rota').innerHTML=RA?RA.html+
    `<details><summary>${ABN[0].toUpperCase()+ABN.slice(1)} e detalhes técnicos</summary>${html}${RA.tec}</details>`:html;};
  orig=L.circleMarker([casa[CF.lat],casa[CF.lon]],{radius:7,color:'#0f8b46',fillColor:'#fff',fillOpacity:1,weight:3}).addTo(map);
  const base=()=>[[casa[CF.lat],casa[CF.lon]],[casa[CF.proj_lat],casa[CF.proj_lon]]];
  let txtC='';
  if(casa[CF.cand]&&D.rota_cand&&casa[CF.no_cand]!=null){camC=L.polyline(cadeia(casa[CF.no_cand],D.rota_cand.prox,base()),{color:'#5b2a86',weight:4,opacity:.9,dashArray:'6 6'}).addTo(map);
    const cd=(D.candidatos||[]).find(x=>x.id===casa[CF.cand]),cz=cd?cd.cota_alaga_m:null;
    const alagou=cz==null?[]:HIST.filter(c=>cz<=c.regua_m-ZR).map(c=>c.rotulo);
    txtC=`<br><span style="color:#4b2c78">Até o local candidato (linha roxa, não oficial; capacidade não avaliada): <b>${fmin(casa[CF.tempo_cand_s])}</b>.</span>`+
      (cz!=null?`<br><span style="color:#9e1b1b"><b>Atenção:</b> este local alaga a partir de ${txtNivel(cz)}`+(alagou.length?` (teria alagado em ${alagou.join(', ')})`:'')+
        '. Só serve em cheias menores: numa cheia grande, vá ao abrigo oficial ou siga a Defesa Civil (199).</span>':'');}
  if(casa[CF.no]<0){saida(casa[CF.proj_lat]==null
    ?'<b>Casa sem rota</b><br>A via mapeada mais próxima fica longe demais.'
    :'<b>Sem caminho até '+ABN+'</b><br>As ruas desta casa não se ligam, no mapa, às do abrigo (outra margem do rio ou trecho isolado).'+txtC);return;}
  const molha=(casa[CF.agua_m]||0)>0;
  // com o cartão do ponto alto, a rota oficial fica de fundo (mais fina e clara)
  cam=rotaPorTrecho(casa,RA?.4:molha&&camC?.55:.95).addTo(map);if(camAlt)camAlt.bringToFront();if(camA)camA.bringToFront();
  if(molha&&camC){camC.setStyle({weight:6,dashArray:null});camC.bringToFront();}
  const ab=D.abrigos.find(x=>x.id===casa[CF.abrigo])||D.abrigos[0];
  const ag=casa[CF.agua_m]||0,st=casa[CF.situacao],cota=casa[CF.cota_alaga];
  saida(`<b>Rota até ${ab?esc(ab.nome):'abrigo'}</b><br>A pé: <b>${fm2(casa[CF.dist_m]/1000)} km</b> · <b>${fmin(casa[CF.tempo_s])}</b> (idoso)`+
    (cota!=null?`<br>A casa alaga a partir de ${txtNivel(cota)}.`:'<br>A casa não alaga até o nível mapeado.')+
    (st==='ilhada'?`<br><span style="color:#4b2c78"><b>Ilhada</b>: não há caminho seco até o ${ABN} neste cenário.${txtCorte(ci)}</span>`:'')+
    (ag>0?`<br><span style="color:#9e1b1b">⚠ A rota até o ${ABN} atravessa ${Math.round(ag)} m de área que alaga (trecho vermelho): não é caminho seguro a pé neste cenário.</span>`:'<br><span style="color:#0f6b4a">Rota fora da área que alaga.</span>')+txtC);}
// teclado: Enter no mapa escolhe a casa sob a mira do centro
map.getContainer().addEventListener('keydown',ev=>{if(ev.key==='Enter'&&ev.target===map.getContainer()&&modo==='rotas'){ev.preventDefault();map.fire('click',{latlng:map.getCenter()});}});
// localização do celular: só escolhe a casa sozinha quando o GPS é preciso
document.addEventListener('click',ev=>{const bt=ev.target;if(!bt||bt.id!=='btLocal')return;
  const volta=()=>{bt.disabled=false;bt.textContent='Usar minha localização';};bt.disabled=true;bt.textContent='Procurando sua localização…';
  navigator.geolocation.getCurrentPosition(p=>{volta();const ll=L.latLng(p.coords.latitude,p.coords.longitude),[ci,d]=casaPerto(ll),ac=p.coords.accuracy||999;
    if(ci<0||d>60||ac>60){map.setView(ll,18);avisoMapa(ll,`Você está por aqui (precisão de ${Math.round(ac)} m). Toque em cima da sua casa.`);return;}
    map.setView([D.casas[ci][CF.lat],D.casas[ci][CF.lon]],17);mostraCasa(ci,true);},
    ()=>{volta();document.getElementById('rota').textContent='Não foi possível obter a localização (permissão negada ou sem GPS). Toque na sua casa no mapa.';},
    {enableHighAccuracy:true,timeout:15000,maximumAge:60000});});
// ---------- abas ----------
const NOMES={rotas:'Rotas',margem:'Margem',impacto:'Quem sai'};
const tabs=document.getElementById('tabs');
tabs.setAttribute('role','tablist');
if(M.modos.length>1)tabs.innerHTML=M.modos.map(m=>`<button type="button" role="tab" id="aba-${m}" aria-controls="painelAba" aria-selected="false" tabindex="-1" data-m="${m}">${NOMES[m]}</button>`).join('');else tabs.style.display='none';
// abas no padrão WAI-ARIA: setas, Home e End trocam de aba
tabs.addEventListener('keydown',ev=>{const bs=[...tabs.querySelectorAll('button')],i=bs.indexOf(document.activeElement);if(i<0)return;
  const j={ArrowRight:(i+1)%bs.length,ArrowLeft:(i-1+bs.length)%bs.length,Home:0,End:bs.length-1}[ev.key];
  if(j===undefined)return;ev.preventDefault();bs[j].focus();setModo(bs[j].dataset.m);});
function setModo(m){modo=m;
  tabs.querySelectorAll('button').forEach(x=>{const on=x.dataset.m===m;x.classList.toggle('on',on);x.setAttribute('aria-selected',String(on));x.tabIndex=on?0:-1;});
  document.getElementById('painelAba').setAttribute('aria-labelledby','aba-'+m);
  if(m==='impacto'&&!carregouContornos){carregouContornos=true;carregarManchaPorNivel();}
  document.getElementById('sliders').classList.toggle('hide',m==='rotas');
  [terrenoLayer,manchaLayer,manchaNivelLayer,ruasLayer,casasLayer,casasImpLayer,candLayer,cheiaLayer].forEach(l=>map.removeLayer(l));
  limpaCasa();casaSel=-1;map.closePopup();
  abrigos.addTo(map);altosLayer.addTo(map);
  if(m==='impacto'){manchaNivelLayer.addTo(map);casasImpLayer.addTo(map);atualizarManchaNivel();renderImpacto();alertaNivel();}
  else if(m==='margem'){ruasLayer.addTo(map);renderMargem();alertaNivel();}
  else{terrenoLayer.addTo(map);if(!AL)manchaLayer.addTo(map);cheiaLayer.addTo(map);ruasLayer.addTo(map);casasLayer.addTo(map);candLayer.addTo(map);renderRotas();}
}
tabs.querySelectorAll('button').forEach(x=>x.onclick=()=>setModo(x.dataset.m));
sld.oninput=redraw;sldTaxa.oninput=redraw;
document.getElementById('selPrep').onchange=e=>{prepMin=+e.target.value;redraw();};
document.getElementById('taxatxt').textContent=taxaCmH;document.getElementById('taxacen').textContent=cenTaxa(taxaCmH);
if(M.abrigos_alagados.length){const e=document.getElementById('alertas');e.classList.remove('hide');
  e.textContent='No cenário, alaga(m): '+M.abrigos_alagados.join(', ')+'. Nos níveis em que um abrigo alaga, ele sai das rotas.';}
let carregouContornos=false;
const mIni=location.hash.slice(1);setModo(M.modos.includes(mIni)?mIni:AL?'rotas':M.modos.includes('impacto')?'impacto':M.modos[0]); aj(); setTimeout(aj,300);
// girar a tela ou dar zoom no navegador não tira a casa escolhida do mapa
let tRz=null;window.addEventListener('resize',()=>{clearTimeout(tRz);tRz=setTimeout(()=>{if(orig)map.invalidateSize();else aj();},200);});
if(innerWidth<=700)dobra(false);
</script></body></html>"""


if __name__ == "__main__":
    main()
