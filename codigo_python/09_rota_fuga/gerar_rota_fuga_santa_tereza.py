#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
ROBÔ — Rota de fuga de Santa Tereza (Etapa 1: prova de conceito por quadra).

Cruza três coisas que já existem no projeto, SEM custo em token (roda no
GitHub Actions):

  1. TERRENO  -> HAND embutido em santa_tereza_previsao_inundacao.html (fonte autoritativa
     que o popup do mapa usa). Para cada célula do terreno, a cota de régua
     em que ela começa a alagar é  ZERO_REGUA + HAND.
  2. PREVISÃO -> previsao_ao_vivo.json (nível atual + trajetória da RNA de 2h/4h).
     Cruzando a trajetória com a cota da célula sai o TEMPO ATÉ A ÁGUA CHEGAR.
  3. FUGA     -> tempo de caminhada até o Ginásio de Esportes (ponto de encontro
     da Defesa Civil em assets/data/servicos/abrigos.geojson), em linha reta
     com fator de desvio, na velocidade de um idoso (a maioria da população).

  margem = tempo_ate_a_agua − tempo_de_caminhada

Saídas (commitadas pelo workflow):
  santa_tereza_rota_fuga.html          — mapa interativo (Leaflet)
  assets/data/rota_fuga_santa_tereza.json — dados por quadra (auditável)

ETAPA 1 é grosseira de propósito (grade de ~30 m, por quadra, linha reta):
serve para mostrar que a cadeia fecha e quanta margem a cidade teria numa
cheia — NÃO para orientar ninguém ainda. O terreno fino (drone), os endereços
e o roteamento por ruas entram nas etapas seguintes.

Uso:
  python codigo_python/09_rota_fuga/gerar_rota_fuga_santa_tereza.py [--cenario 22jul]
"""
import os
import re
import io
import sys
import json
import base64
import argparse
from math import radians, cos, sin, asin, sqrt

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nivel_ao_vivo  # noqa: E402

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PAGINA_HAND = os.path.join(RAIZ, "santa_tereza_previsao_inundacao.html")
FORECAST = os.path.join(RAIZ, "previsao_ao_vivo.json")
ABRIGOS = os.path.join(RAIZ, "assets", "data", "servicos", "abrigos.geojson")


def caminhos_saida(cenario):
    if cenario == "ao_vivo":
        return (os.path.join(RAIZ, "santa_tereza_rota_fuga.html"),
                os.path.join(RAIZ, "assets", "data", "rota_fuga_santa_tereza.json"))
    return (os.path.join(RAIZ, "santa_tereza_rota_fuga_cenario.html"),
            os.path.join(RAIZ, "assets", "data", "rota_fuga_santa_tereza_cenario.json"))

# ------------------------------------------------------------------ parâmetros
ZERO_REGUA_M = 1.60         # calibração de campo: 1,60 m na régua = HAND 0
BLOCO_M = 30.0              # tamanho da "quadra" na Etapa 1
HAND_MAX_HABITAVEL = 25.0   # topo do HAND LiDAR; quadra que a previsão não alcança já fica fora do mapa
VEL_IDOSO_MS = 0.9          # caminhada de idoso/criança (m/s) — conservador
VEL_ADULTO_MS = 1.3         # caminhada adulto (m/s), para comparação
FATOR_DESVIO = 1.4          # linha reta -> caminho real (Etapa 1; ruas entram depois)
HORIZONTE_MIN = 360         # projeta a trajetória por até 6 h à frente


def ponto_seguro_oficial():
    """Ginásio de Esportes, o mesmo ponto de encontro das rotas por ruas."""
    for f in json.load(open(ABRIGOS, encoding="utf-8"))["features"]:
        pr = f["properties"]
        if pr.get("municipio") == "Santa Tereza":
            lon, lat = f["geometry"]["coordinates"][:2]
            return {"lat": lat, "lon": lon, "nome": pr["nome"], "id": pr["id"],
                    "fonte": pr.get("fonte"), "confirmado": True}
    raise SystemExit(f"Santa Tereza sem ponto de encontro em {ABRIGOS}")


PONTO_SEGURO = ponto_seguro_oficial()

# recorte urbano aproximado (bbox) para a Etapa 1 — evita espalhar a grade pela
# encosta/mata. Ajustável quando os endereços (CNEFE) entrarem.
URBANO_BBOX = {"S": -29.190, "N": -29.160, "W": -51.745, "E": -51.720}


# --------------------------------------------------------------------- terreno
def carrega_hand():
    s = open(PAGINA_HAND, encoding="utf-8").read()
    m = re.search(r'id="hand-data"[^>]*>(\{.*?\})</script>', s, re.S)
    d = json.loads(m.group(1))
    png = base64.b64decode(d["hand_png_b64"])
    dm = np.asarray(Image.open(io.BytesIO(png)).convert("L"), dtype=np.float32)
    hand = dm / 10.0                          # decímetros -> metros
    return hand, d


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


# ------------------------------------------------------------------- previsão
def trajetoria_nivel(cenario):
    """Devolve ([(minutos, nivel_m), ...] crescente no tempo, rótulo, nível atual
    em cm, hora da telemetria). Fonte normal: previsao_ao_vivo.json; sem nível
    atual devolve pontos=None (não publicar: nada de rio "seco" que sobe até a
    previsão). Cenário '22jul': taxa de subida de cheia documentada para
    demonstrar a Etapa 1 mesmo com o rio baixo hoje."""
    d = json.load(open(FORECAST, encoding="utf-8"))
    nivel_atual_cm = nivel_ao_vivo.nivel_atual_cm(d)
    tele_em = d.get("telemetria_ultima_em")

    if cenario == "22jul":
        # subida ~ 40 cm/h (ordem de grandeza da cheia de 22/07/2026), partindo
        # do nível atual, projetada por HORIZONTE_MIN. Demonstra a margem.
        base = (400 if nivel_atual_cm is None else nivel_atual_cm) / 100.0
        taxa_m_por_min = 0.40 / 60.0
        pts = [(m, base + taxa_m_por_min * m) for m in range(0, HORIZONTE_MIN + 1, 10)]
        rotulo = "cenário de cheia (subida ~40 cm/h, referência 22/07)"
    else:
        if nivel_atual_cm is None:
            return None, "previsão sem nível atual do rio", None, tele_em
        pts = [(0, nivel_atual_cm / 100.0)]
        pts += [(m, cm / 100.0) for _hk, m, cm in nivel_ao_vivo.previstos_cm(d)]
        # extrapola a última inclinação até o horizonte
        if len(pts) >= 2:
            (ma, na), (mb, nb) = pts[-2], pts[-1]
            incl = (nb - na) / max(mb - ma, 1)
            if mb < HORIZONTE_MIN:
                pts.append((HORIZONTE_MIN, nb + incl * (HORIZONTE_MIN - mb)))
        rotulo = "previsão ao vivo (RNA 2h/4h)"
    return pts, rotulo, nivel_atual_cm, tele_em


def tempo_ate(cota_m, pts):
    """Minutos até a trajetória atingir cota_m. None se não atinge no horizonte.
    <=0 se a célula já está alagada agora."""
    if pts[0][1] >= cota_m:
        return 0.0
    for (ma, na), (mb, nb) in zip(pts, pts[1:]):
        if nb >= cota_m:
            if nb == na:
                return mb
            return ma + (mb - ma) * (cota_m - na) / (nb - na)
    return None


# --------------------------------------------------------------------- grade
def monta_quadras(hand, geo, pts):
    ny, nx = hand.shape
    S, W, N, E = geo["S"], geo["W"], geo["N"], geo["E"]
    dlat = (N - S) / ny            # graus por pixel (lat, positivo p/ cima na img invertida)
    dlon = (E - W) / nx
    lat0 = (S + N) / 2
    m_por_grau_lat = 111320.0
    m_por_grau_lon = 111320.0 * cos(radians(lat0))
    px_por_bloco_y = max(1, int(round(BLOCO_M / (abs(dlat) * m_por_grau_lat))))
    px_por_bloco_x = max(1, int(round(BLOCO_M / (abs(dlon) * m_por_grau_lon))))

    quadras = []
    for by in range(0, ny, px_por_bloco_y):
        for bx in range(0, nx, px_por_bloco_x):
            blk = hand[by:by + px_por_bloco_y, bx:bx + px_por_bloco_x]
            if blk.size == 0:
                continue
            h = float(np.min(blk))                 # ponto mais baixo = alaga primeiro
            if h <= 0 or h > HAND_MAX_HABITAVEL:
                continue
            # centro da célula em lat/lon (imagem: linha 0 = Norte)
            cy = by + blk.shape[0] / 2
            cx = bx + blk.shape[1] / 2
            lat = N - dlat * cy
            lon = W + dlon * cx
            if not (URBANO_BBOX["S"] <= lat <= URBANO_BBOX["N"]
                    and URBANO_BBOX["W"] <= lon <= URBANO_BBOX["E"]):
                continue
            cota = ZERO_REGUA_M + h
            tw = tempo_ate(cota, pts)
            if tw is None:
                continue                            # não alaga no horizonte -> fora do mapa
            dist = haversine_m(lat, lon, PONTO_SEGURO["lat"], PONTO_SEGURO["lon"]) * FATOR_DESVIO
            t_idoso = dist / VEL_IDOSO_MS / 60.0
            t_adulto = dist / VEL_ADULTO_MS / 60.0
            margem = tw - t_idoso
            quadras.append({
                "lat": round(lat, 6), "lon": round(lon, 6),
                "hand_m": round(h, 2), "cota_alaga_m": round(cota, 2),
                "min_ate_agua": round(tw, 1),
                "dist_m": round(dist, 0),
                "min_caminhada_idoso": round(t_idoso, 1),
                "min_caminhada_adulto": round(t_adulto, 1),
                "margem_min": round(margem, 1),
                "classe": classe(margem, tw),
            })
    passo_lat = abs(dlat) * px_por_bloco_y
    passo_lon = abs(dlon) * px_por_bloco_x
    return quadras, passo_lat, passo_lon


def classe(margem, tw):
    if tw <= 0:
        return "alagada"          # já está na água
    if margem < 0:
        return "critica"          # não sai a pé sozinho -> precisa de resgate
    if margem < 15:
        return "apertada"
    if margem < 60:
        return "atencao"
    return "confortavel"


# ---------------------------------------------------------------------- saída
CORES = {"alagada": "#1e5fbf", "critica": "#b3382c", "apertada": "#e8730c",
         "atencao": "#e3b100", "confortavel": "#1b7a5a"}


def escreve_json(quadras, meta, SAIDA_JSON):
    os.makedirs(os.path.dirname(SAIDA_JSON), exist_ok=True)
    resumo = {c: sum(1 for q in quadras if q["classe"] == c) for c in CORES}
    doc = {"meta": meta, "resumo": resumo, "quadras": quadras}
    json.dump(doc, open(SAIDA_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    return resumo


def mesmo_conteudo(SAIDA_JSON, quadras, meta):
    """True se a rodada só mudaria o carimbo de hora (não comitar a cada 5 min).
    A idade do dado a página calcula sozinha, a partir de telemetria_em."""
    try:
        velho = json.load(open(SAIDA_JSON, encoding="utf-8"))
    except (OSError, ValueError):
        return False
    tempo = ("gerado_em", "idade_telemetria_min", "dados_desatualizados")
    limpa = lambda m: {k: v for k, v in (m or {}).items() if k not in tempo}
    novo = json.loads(json.dumps({"quadras": quadras, "meta": meta}))
    return velho.get("quadras") == novo["quadras"] and limpa(velho.get("meta")) == limpa(novo["meta"])


def escreve_html(quadras, passo_lat, passo_lon, meta, resumo, SAIDA_HTML):
    ps = PONTO_SEGURO
    banner = ('<div class="aviso">⚠ Prova de conceito (Etapa 1: grade de 30 m, linha reta até o '
              + ps["nome"] + '). Não usar para orientar evacuação real.</div>')
    dados = json.dumps({"quadras": quadras, "dlat": passo_lat, "dlon": passo_lon,
                        "seguro": ps, "estacao": meta["estacao"], "ponte": meta["ponte"],
                        "cores": CORES, "telemetria_em": meta.get("telemetria_em"),
                        "velho_min": nivel_ao_vivo.TELEMETRIA_VELHA_MIN}, ensure_ascii=False)
    html = _TEMPLATE.replace("__DADOS__", dados).replace("__BANNER__", banner) \
                    .replace("__NIVEL__", meta["nivel_txt"]).replace("__CENARIO__", meta["cenario_rotulo"]) \
                    .replace("__GERADO__", meta["gerado_em"]).replace("__RESUMO__", json.dumps(resumo))
    open(SAIDA_HTML, "w", encoding="utf-8").write(html)


_TEMPLATE = r"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rota de fuga — Santa Tereza (prova de conceito)</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
 body{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#12211b}
 #map{position:absolute;top:0;bottom:0;left:0;right:0}
 .hud{position:absolute;z-index:500;top:10px;left:10px;background:#fff;border-radius:10px;
      box-shadow:0 2px 12px rgba(0,0,0,.15);padding:12px 14px;max-width:300px}
 .hud h1{font:600 16px Georgia,serif;margin:0 0 4px}
 .hud .lv{font-variant-numeric:tabular-nums;color:#0f6b4a;font-weight:700}
 .hud .sub{color:#5b6b62;font-size:12.5px;margin:2px 0}
 .aviso{background:#fdecea;border:1px solid #f2b8b2;color:#b3382c;border-radius:8px;
        padding:8px 10px;font-size:12px;margin-top:8px}
 .canais{background:#f3f6f4;border-radius:8px;padding:6px 9px;font-size:12px;margin-top:8px;color:#12211b}
 .leg{position:absolute;z-index:500;bottom:14px;left:10px;background:#fff;border-radius:10px;
      box-shadow:0 2px 12px rgba(0,0,0,.15);padding:10px 12px;font-size:12.5px}
 .leg i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-2px}
 .leaflet-popup-content{font-size:13px}
</style></head><body>
<div id="map"></div>
<div class="hud">
  <h1>Rota de fuga · Santa Tereza</h1>
  <div class="sub">Prova de conceito (Etapa 1) — <b>__CENARIO__</b></div>
  <div class="sub">Nível do rio: <span class="lv">__NIVEL__</span></div>
  <div class="sub" id="leitura"></div>
  <div class="sub">Página gerada: __GERADO__ (horário de Brasília)</div>
  <div class="sub" id="nota-leito"></div>
  <div class="aviso" id="velho" hidden></div>
  __BANNER__
  <div class="canais">Em emergência: <b>193</b> (Bombeiros) · <b>199</b> (Defesa Civil). Alertas oficiais por SMS: envie seu CEP para <b>40199</b>. Siga a Defesa Civil municipal.</div>
</div>
<div class="leg" id="leg"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const D=__DADOS__, RES=__RESUMO__;
// idade da leitura calculada no navegador: vale mesmo se o robô parar de rodar
let VELHO=false;
if(D.telemetria_em){const t=new Date(D.telemetria_em),min=Math.round((Date.now()-t)/60000);
  const f=new Intl.DateTimeFormat('pt-BR',{timeZone:'America/Sao_Paulo',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
  document.getElementById('leitura').textContent='Leitura do rio: '+f.format(t)+' (Brasília) · há '+
    (min<60?min+' min':Math.floor(min/60)+' h '+String(min%60).padStart(2,'0')+' min');
  if(min>D.velho_min){VELHO=true;const v=document.getElementById('velho');v.hidden=false;
    v.innerHTML='<b>Dado desatualizado</b>: a última leitura do rio tem mais de '+Math.round(D.velho_min/60)+' h. Este mapa não mostra a situação de agora.';}}
const map=L.map('map',{zoomControl:false});
L.control.zoom({position:'topright'}).addTo(map);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
 {maxZoom:19,attribution:'Esri World Imagery'}).addTo(map);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
 {maxZoom:19,opacity:.9}).addTo(map);
const ROT={alagada:'abaixo do nível atual (leito e margens do rio)',critica:'margem negativa — a água chega antes',
 apertada:'margem curta (menos de 15 min)',atencao:'margem de 15 a 60 min',confortavel:'margem de mais de 1 h'};
const b=L.latLngBounds();
D.quadras.forEach(q=>{
  const dy=D.dlat/2, dx=D.dlon/2;
  const op=(q.classe==='alagada'?.55:.72)*(VELHO?.3:1);
  const rect=L.rectangle([[q.lat-dy,q.lon-dx],[q.lat+dy,q.lon+dx]],
    {stroke:false,fillColor:D.cores[q.classe],fillOpacity:op});
  rect.bindPopup(`<b>Quadra</b><br>${q.min_ate_agua<=0?'<b>Abaixo do nível atual do rio</b>':'Água chega em <b>'+q.min_ate_agua+' min</b>'}<br>`+
    `Caminhada até ${D.seguro.nome} (idoso, linha reta × 1,4): <b>${q.min_caminhada_idoso} min</b> · ${q.dist_m} m<br>`+
    (q.min_ate_agua<=0?'':`Margem: <b>${q.margem_min} min</b> — ${ROT[q.classe]}<br>`)+
    `<span style="color:#5b6b62">cota que alaga: ${q.cota_alaga_m} m · HAND ${q.hand_m} m</span>`);
  rect.addTo(map); b.extend([q.lat,q.lon]);
});
if(D.quadras.length&&D.quadras.every(q=>q.classe==='alagada'))
  document.getElementById('nota-leito').textContent='Fora do leito e das margens baixas do rio, nenhuma quadra é alcançada no horizonte desta previsão.';
// ponto de encontro
const seg=L.marker([D.seguro.lat,D.seguro.lon],{title:D.seguro.nome,alt:D.seguro.nome}).addTo(map);
seg.bindPopup('<b>'+D.seguro.nome+'</b><br>ponto de encontro da Defesa Civil'); b.extend([D.seguro.lat,D.seguro.lon]);
L.circleMarker([D.estacao.lat,D.estacao.lon],{radius:6,color:'#1e5fbf',fillColor:'#1e5fbf',fillOpacity:1})
  .bindPopup('Estação '+D.estacao.code).addTo(map);
if(D.ponte) L.circleMarker([D.ponte.lat,D.ponte.lon],{radius:5,color:'#555',fillColor:'#999',fillOpacity:1})
  .bindPopup(D.ponte.label||'Ponte').addTo(map);
map.fitBounds(b.pad(0.15));
// legenda
const ordem=['confortavel','atencao','apertada','critica','alagada'];
document.getElementById('leg').innerHTML='<b>Margem de tempo</b><br>'+ordem.map(c=>
 `<i style="background:${D.cores[c]}"></i>${ROT[c]} <span style="color:#5b6b62">(${RES[c]||0})</span>`).join('<br>');
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cenario", default="ao_vivo", choices=["ao_vivo", "22jul"])
    args = ap.parse_args()

    SAIDA_HTML, SAIDA_JSON = caminhos_saida(args.cenario)
    hand, geo = carrega_hand()
    pts, rotulo, nivel_cm, tele_em = trajetoria_nivel(args.cenario)
    if pts is None:
        print(f"{rotulo}: página mantida (ela mostra a idade da última leitura)")
        return
    quadras, passo_lat, passo_lon = monta_quadras(hand, geo, pts)

    ao_vivo = args.cenario == "ao_vivo"
    tele = nivel_ao_vivo.para_brt(tele_em) if ao_vivo else None
    idade = nivel_ao_vivo.idade_min(tele_em) if ao_vivo else None
    nivel_txt = (f"{nivel_cm/100:.2f} m" if nivel_cm is not None else "sem telemetria")
    meta = {
        "gerado_em": nivel_ao_vivo.agora().strftime("%Y-%m-%d %H:%M"),
        "fuso": "America/Sao_Paulo",
        "cenario": args.cenario, "cenario_rotulo": rotulo,
        "nivel_atual_cm": nivel_cm, "nivel_txt": nivel_txt,
        "telemetria_em": tele.isoformat() if tele else None,
        "idade_telemetria_min": idade,
        "dados_desatualizados": ao_vivo and (idade is None or idade > nivel_ao_vivo.TELEMETRIA_VELHA_MIN),
        "zero_regua_m": ZERO_REGUA_M, "bloco_m": BLOCO_M,
        "ponto_seguro": PONTO_SEGURO, "etapa": 1,
        "estacao": geo["station"], "ponte": geo.get("ponte"),
        "aviso": "Etapa 1: grade 30 m, linha reta até o ponto de encontro da Defesa Civil. Não usar para evacuação real.",
    }
    if ao_vivo and mesmo_conteudo(SAIDA_JSON, quadras, meta):
        print(f"cenario={args.cenario} nivel={nivel_txt}: sem mudança desde a última rodada, página mantida")
        return
    resumo = escreve_json(quadras, meta, SAIDA_JSON)
    escreve_html(quadras, passo_lat, passo_lon, meta, resumo, SAIDA_HTML)
    print(f"cenario={args.cenario} nivel={nivel_txt} quadras={len(quadras)} resumo={resumo}")
    print(f"-> {SAIDA_HTML}")
    print(f"-> {SAIDA_JSON}")


if __name__ == "__main__":
    main()
