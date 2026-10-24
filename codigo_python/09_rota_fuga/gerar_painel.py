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
import os, sys, json, argparse
from shapely.geometry import shape, Point
from shapely.strtree import STRtree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gerar_rota_fuga_ruas as rf_mod  # noqa: E402
from rede_casas import no_prox  # noqa: E402
import nivel_ao_vivo  # noqa: E402

RAIZ = rf_mod.RAIZ
# Cheias de referência na régua: atalhos do nível no painel e validade de cada
# abrigo/candidato ("seco até X; em set/2023 teria alagado"). Picos das séries
# em assets/data/eventos_analise.json (86472600) e mucum_eventos_analise.json
# (86510000). Muçum set/2023 fica de fora: a série termina subindo em 21,18 m.
CFG = {
    "santa_tereza": {"cod": "4317251", "rf": "rota_fuga_ruas_santa_tereza_cenario.json",
                     "html": os.path.join(RAIZ, "santa_tereza_painel_casas.html"),
                     "cheias_ref": [
                         {"rotulo": "inundação oficial", "regua_m": 15.0, "tipo": "cota_oficial"},
                         {"rotulo": "jul/2026", "regua_m": 17.46, "data": "2026-07-22"},
                         {"rotulo": "nov/2023", "regua_m": 21.61, "data": "2023-11-18"},
                         {"rotulo": "set/2023", "regua_m": 23.65, "data": "2023-09-04"},
                         {"rotulo": "ref. mai/2024", "regua_m": 25.82, "data": "2024-05", "tipo": "referencia",
                          "nota": "referência de cenário de abrigos.geojson; a telemetria parou em 22,32 m antes do pico"},
                     ]},
    "mucum": {"cod": "4312609", "rf": "rota_fuga_ruas_mucum_cenario.json",
              "html": os.path.join(RAIZ, "mucum_painel_casas.html"),
              "contingencia": os.path.join(RAIZ, "assets", "data", "mucum_contingencia_202607.json"),
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


def completa(doc, cidade, taxa_cm_h=TAXA_PADRAO_CM_H):
    """Campos do painel que não dependem das rotas: cheias, taxa padrão e capacidade do plano."""
    cfg = CFG[cidade]
    doc["meta"]["cheias_ref"] = cfg["cheias_ref"]
    doc["meta"]["taxa_cm_h"] = taxa_cm_h
    cap = capacidades_plano(cfg)
    for a in doc["abrigos"]:
        a["capacidade_plano"] = cap.get(a["id"])
    return doc


def escreve(doc, saida):
    # Preservar a navegacao para rotas de setembro/2023 nas republicacoes.
    # Este estudo e especifico de Santa Tereza, nao de Mucum.
    rotas_altas = ""
    if doc["meta"].get("municipio") == "Santa Tereza":
        rotas_altas = (
            '<div style="margin:9px 14px;padding:10px 12px;border:1px solid #bbd4c6;'
            'border-radius:9px;background:#f3faf6;font-size:13px;line-height:1.4">'
            '<b>Para onde ir sem atravessar as ruas inundadas?</b> '
            '<a href="santa_tereza_rotas_altas_set2023.html" '
            'style="display:block;color:#075d40;font-weight:700;margin-top:5px">'
            'Abrir rotas para terreno alto · setembro/2023 →</a>'
            '<small>Mostra destinos em cotas superiores e distingue rua seca,'
            ' alagada e sem classificação no modelo histórico.</small></div>'
        )
    html = _TEMPLATE.replace(
        "__DADOS__", json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    ).replace("__ROTAS_ALTAS__", rotas_altas)
    open(saida, "w", encoding="utf-8").write(html)


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
<title>Painel de evacuação</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
 html,body{height:100%;margin:0}
 body{font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#12211b}
 #map{position:fixed;top:0;left:0;width:100vw;height:100vh}
 .hud{position:absolute;z-index:500;top:10px;left:10px;width:330px;max-width:calc(100vw - 24px);max-height:calc(100vh - 40px);overflow:auto;
      background:#fff;border-radius:12px;box-shadow:0 4px 18px rgba(0,0,0,.22);padding:0 0 12px}
 .hud h1{font:600 17px Georgia,serif;margin:0;padding:12px 14px 8px}
 .dobra{float:right;margin:10px 10px 0 0;border:0;background:#eef3f0;border-radius:6px;padding:3px 9px;font-weight:600;font-size:13px;font-family:inherit;cursor:pointer}
 .hud.min .corpo{display:none}
 .tabs{display:flex;border-bottom:1px solid #e6ece9;margin:0 0 8px}
 .tabs button{flex:1;border:0;background:none;padding:10px 4px;font-weight:600;font-size:14px;font-family:inherit;color:#4a5a52;cursor:pointer;border-bottom:3px solid transparent}
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
 .leg-rota{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12.5px;color:#4a5a52;margin:6px 0 2px}
 .leg-rota i{display:inline-block;width:18px;height:5px;margin-right:5px;vertical-align:middle;border-radius:2px}
 .leg-rota i.tr{background:repeating-linear-gradient(90deg,#b3241b 0 10px,transparent 10px 16px)}
 .canais{font-size:12px;color:#4a5a52;padding:0 14px 8px}
 .cheias{display:flex;flex-wrap:wrap;gap:4px;align-items:center;margin:2px 0 6px;font-size:12px;color:#4a5a52}
 .cheias button{border:1px solid #c9d6cf;background:#f4f7f5;border-radius:12px;padding:3px 9px;font-weight:600;font-size:12px;font-family:inherit;cursor:pointer;min-height:28px}
 #selPrep{font:inherit;font-size:13px;margin-top:2px}
</style></head><body>
<div id="map"></div>
<div class="hud" id="hud">
  <button class="dobra" onclick="document.getElementById('hud').classList.toggle('min')">–</button>
  <h1><span id="tit"></span> · <span id="cid"></span></h1>
  <div class="canais">Em emergência: <b>193</b> (Bombeiros) · <b>199</b> (Defesa Civil) · alertas por SMS: envie seu CEP para <b>40199</b>.</div>
  <div class="corpo">
  __ROTAS_ALTAS__
  <div class="tabs" id="tabs"></div>
  <div class="bd">
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
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const D=__DADOS__, M=D.meta, NV=D.niveis, ZR=M.bankfull_m;
const CF=Object.fromEntries(M.casas_campos.map((k,i)=>[k,i]));
document.getElementById('cid').textContent=M.municipio;
document.getElementById('tit').textContent=M.titulo||'Evacuação';
let taxaCmH=M.taxa_cm_h,prepMin=30;
const map=L.map('map');
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Imagens Esri · Ruas e edificações © OpenStreetMap contributors (ODbL) · População IBGE'}).addTo(map);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,opacity:.9}).addTo(map);
const fm=x=>x.toFixed(1).replace('.',','),fm2=x=>x.toFixed(2).replace('.',',');
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
  const ab=D.abrigos.filter(a=>a.cota_alaga_m!=null&&a.cota_alaga_m<=h).map(a=>a.nome);
  const nc=(D.candidatos||[]).filter(c=>c.cota_alaga_m!=null&&c.cota_alaga_m<=h).length;
  if(nc)ab.push(`${nc} de ${D.candidatos.length} locais candidatos`);
  const qual=PIOR.tipo==='referencia'?'Na cheia de referência mais alta':'Na maior cheia registrada';
  return ab.length?`<div class="aviso">${qual} (${PIOR.rotulo}, régua ${fm2(PIOR.regua_m)} m) alagariam: ${ab.join(', ')}.</div>`:'';}
// cores com luminância bem diferente entre urgente (escuro) e folgado (claro); par mais
// próximo com distância de cor >= 17 (Lab) também em deuteranopia, protanopia e tritanopia
// (antes "já na água" e "ilhada" ficavam a 2,0 na protanopia)
const CORES={alagada:'#1f4e9c',ilhada:'#9d4edd',isolada:'#2b2b2b',sem_abrigo:'#6b6b6b',critica:'#9e1b1b',apertada:'#e66100',atencao:'#f6c445',confortavel:'#4fb38a',seguro:'#c9cfcc',sem_rota:'#ffffff'};
const ROT={alagada:'já na água',ilhada:'ilhada — rota já cruza água',critica:'crítica — não sai a pé a tempo',apertada:'apertada (menos de 15 min)',atencao:'atenção (menos de 1 h)',confortavel:'confortável (mais de 1 h)',seguro:'rota não alaga',isolada:'isolada — a água cortou o caminho até abrigo seco',sem_abrigo:'sem abrigo oficial seco neste nível',sem_rota:'sem rota (sem via mapeada ou sem abrigo seco)'};
const ORDEM=['alagada','ilhada','isolada','sem_abrigo','critica','apertada','atencao','confortavel','seguro','sem_rota'];
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
// sem rota agora, mas com rota com o rio baixo (nível 0): se ainda há abrigo oficial seco,
// a água cortou o caminho (isolada); se todos alagaram, falta abrigo (sem_abrigo)
const semAbrigoSeco=A=>D.abrigos.every(a=>a.cota_alaga_m!=null&&a.cota_alaga_m<=NV.hand_m[A.k]);
const semRota=(agora,rioBaixo,A)=>agora<0?(rioBaixo<0?'sem_rota':semAbrigoSeco(A)?'sem_abrigo':'isolada'):null;
function classeNo(i,A){if(A.T[i]<0)return semRota(A.T[i],NV.tempo_s[0][i],A);const c=D.cota_no[i];
  if(c!=null&&c<=A.h)return 'alagada'; if(A.g[i]<=A.h)return 'ilhada'; return faixa(A.f[i]-A.T[i]/60);}
function classeCasa(ci,A){const c=D.casas[ci],cota=c[CF.cota_alaga];
  if(cota!=null&&cota<=A.h)return 'alagada';
  const no=NV.casa_no[A.k][ci],Tc=NV.casa_tempo_s[A.k][ci];
  if(no<0||Tc<0)return semRota(-1,Math.min(NV.casa_no[0][ci],NV.casa_tempo_s[0][ci]),A);
  if(A.g[no]<=A.h||NV.casa_agua_m[A.k][ci]>0)return 'ilhada';
  return faixa(Math.min(cota==null?Infinity:(cota-A.h)/A.taxa,A.f[no]-Tc/60));}
function classeCel(c,A){
  if(c.casas.length){const cnt={};c.casas.forEach(ci=>{const k=classeCasa(ci,A);cnt[k]=(cnt[k]||0)+1;});return cnt;}
  const no=c.no;let k;
  if(c.cota!=null&&c.cota<=A.h)k='alagada';else if(A.T[no]<0)k=semRota(A.T[no],NV.tempo_s[0][no],A);else if(A.g[no]<=A.h)k='ilhada';
  else k=faixa(Math.min(c.cota==null?Infinity:(c.cota-A.h)/A.taxa,A.f[no]-A.T[no]/60));
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
    nivelManchaDesenhado=null;
    atualizarManchaNivel();
    if(modo==='impacto')renderImpacto();
  }).catch(e=>{
    manchaErro=e.message;
    if(modo==='impacto')renderImpacto();
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
  .bindPopup(()=>{const k=casaCl[ci],p=c[CF.pessoas],cota=c[CF.cota_alaga];
    return `<span class="sw" style="background:${CORES[k]}"></span><b>${ROT[k]}</b><br>`+
      (p==null?'Fora das células com moradores no Censo 2022':`~${fm(p)} pessoas (IBGE 2022)`)+
      (cota!=null?`<br>Alaga a partir de ${txtNivel(cota)}.`:'<br>Não alaga até o nível mapeado.');}));
const casasImpLayer=L.layerGroup(casasImp);
const txtDemanda=dm=>!dm?'':`<br>Demanda no cenário: ~<b>${dm.pessoas}</b> pessoas de ${dm.casas} casas na água`+
  (dm.casas_isoladas?` + ~${dm.pessoas_isoladas} de ${dm.casas_isoladas} casas isoladas`:'')+
  (dm.casas_fora_censo?` (${dm.casas_fora_censo} casas sem moradores no Censo 2022 contam 0)`:'')+'.';
const MOT={tempo:m=>`${m} passam de ${M.tempo_max_min||30} min até o abrigo oficial`,sem_rota:m=>`${m} sem caminho até abrigo oficial`,ilhada:m=>`${m} ilhadas (rota cruza água)`};
const txtMotivos=cd=>Object.entries(cd.motivos||{}).map(([k,v])=>(MOT[k]||(m=>m+' '+k))(v)).join(', ');
const abrigos=L.layerGroup(D.abrigos.map(a=>L.marker([a.lat,a.lon],{title:a.nome,alt:a.nome}).bindPopup('<b>'+a.nome+'</b><br>abrigo / ponto de encontro oficial'+
  txtValidade(a.cota_alaga_m)+txtDemanda(a.demanda)+txtCapacidade(a))));
D.abrigos.forEach(a=>b.extend([a.lat,a.lon]));
const candLayer=L.layerGroup((D.candidatos||[]).map(cd=>L.circleMarker([cd.lat,cd.lon],{radius:10,color:'#5b2a86',weight:3,dashArray:'4 3',fillColor:'#d9c6f0',fillOpacity:.7})
  .bindPopup(`<b>Local candidato</b> (não oficial)<br>Grupo de ${cd.n_casas} casas: ${txtMotivos(cd)}.<br>`+
    (cd.pior_antes_min!=null&&cd.pior_depois_min!=null?`Pior tempo: ${Math.round(cd.pior_antes_min)} → ${Math.round(cd.pior_depois_min)} min.<br>`:
     cd.pior_depois_min!=null?`Pior tempo até aqui: ${Math.round(cd.pior_depois_min)} min.<br>`:'')+
    `Rampa ${Math.round((cd.rampa||0)*100)}%`+txtValidade(cd.cota_alaga_m)+
    txtDemanda(cd.demanda)+`<br><i>Capacidade não avaliada. Validar com a Defesa Civil.</i>`)));
const EST={excede:['#6b1a1a','#c0392b'],ilhada:['#4b2c78','#a689d6'],sem_rota:['#666','#c5c5c5']};
const casasLayer=L.layerGroup(D.casas.map(c=>{b.extend([c[CF.lat],c[CF.lon]]);const st=c[CF.situacao]||'ok',dn=c[CF.na_mancha];
  const [cor,fill]=EST[st]||(dn?['#9a3412','#e8730c']:['#3d4a44','#f4f7f5']);
  return L.circleMarker([c[CF.lat],c[CF.lon]],{radius:dn||st!=='ok'?4:2.6,weight:1,color:cor,fillColor:fill,fillOpacity:.85,interactive:false});}));
const BB=b.pad(0.04);function aj(){map.invalidateSize();map.fitBounds(BB);}
// ---------- render ----------
let modo=M.modos[0];
const sld=document.getElementById('sld'),sldTaxa=document.getElementById('sldTaxa');
sld.max=Math.round(M.nivel_max_m*10);sld.value=Math.round(Math.max(0,M.nivel_projeto_m)*10);sldTaxa.value=M.taxa_cm_h;
document.getElementById('selPrep').value=String(prepMin);sld.setAttribute('aria-valuetext',txtNivel(nivelAtual()));
document.getElementById('cheias').innerHTML=CHEIAS.length?'<span>Cheias:</span>'+CHEIAS.map((c,i)=>
  `<button type="button" data-i="${i}" title="${c.nota||''}">${c.rotulo} · ${fm2(c.regua_m)} m</button>`).join(''):'';
document.querySelectorAll('#cheias button').forEach(bt=>bt.onclick=()=>{
  sld.value=Math.min(+sld.max,Math.round((CHEIAS[+bt.dataset.i].regua_m-ZR)*10));redraw();});
function nivelAtual(){return sld.value/10;}
function legenda(cnt,fmt){return ORDEM.filter(k=>cnt[k]>0).map(k=>`<div class="row"><span><span class="sw" style="background:${CORES[k]}"></span>${ROT[k]}</span><b>${fmt(cnt[k])}</b></div>`).join('');}
function renderRotas(){
  ruas.forEach(r=>r.pl.setStyle({color:r.ag?'#b3382c':'#8fa7b8',weight:r.ag?2.5:1.5,opacity:r.ag?.75:.55,dashArray:r.pe?'3 4':null}));
  document.getElementById('painel').innerHTML=`<div class="sub">Cenário: ${M.rotulo_nivel||txtNivel(M.nivel_projeto_m)}. Toque numa casa para ver a rota a pé (idoso, com subidas) até o abrigo mais próximo.</div>${avisoCheia()}<div class="leg-rota"><span><i style="background:#0f8b46"></i>rota sem água</span><span><i class="tr"></i>trecho que alaga</span><span><i style="background:#5b2a86"></i>até local candidato (não oficial)</span><span><i style="background:#2a81cb"></i>abrigo oficial (pino azul)</span></div><div class="rota" id="rota">—</div>`;
}
function renderMargem(){const A=avalia(nivelAtual());const cnt={};
  const cl=D.nos.map((_,i)=>classeNo(i,A));
  ruas.forEach(r=>{let k=pior(cl[r.a],cl[r.c]);if(r.cz!=null&&r.cz<=A.h)k='alagada';cnt[k]=(cnt[k]||0)+1;
    r.pl.setStyle({color:CORES[k],weight:k==='seguro'?1.5:3,opacity:.9,dashArray:null});});
  document.getElementById('nvtxt').textContent=txtNivel(A.h);
  document.getElementById('painel').innerHTML='<div class="sub">Ruas pela margem: quanto tempo ainda dá para esperar antes de sair a pé (trechos de rua por faixa).</div>'+legenda(cnt,v=>v)+
    `<div class="nota">Margem = menor folga ao longo da rota até o abrigo: tempo até a água chegar em cada ponto − tempo do idoso para chegar nele − ${prepMin} min de preparo.</div>`;
}
const RISCO=['alagada','ilhada','isolada','sem_abrigo','critica','apertada','atencao'];
function renderImpacto(){const A=avalia(nivelAtual());const cnt={};
  casaCl=D.casas.map((_,ci)=>classeCasa(ci,A));
  casasImp.forEach((m,ci)=>m.setStyle({fillColor:CORES[casaCl[ci]],radius:RISCO.includes(casaCl[ci])?4.2:3}));
  D.cells.forEach(c=>{const inf=classeCel(c,A);const tot=Object.values(inf).reduce((s,v)=>s+v,0);
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
  const al=D.abrigos.filter(a=>a.cota_alaga_m!=null&&a.cota_alaga_m<=NV.hand_m[k]).map(a=>a.nome);
  if(al.length)document.getElementById('painel').insertAdjacentHTML('afterbegin',
    `<div class="aviso">${al.length===D.abrigos.length?'<b>Nenhum abrigo oficial fica seco neste nível.</b> ':''}Alaga(m): ${al.join(', ')}.</div>`);
  if(h>=M.nivel_max_m)document.getElementById('painel').insertAdjacentHTML('afterbegin',
    `<div class="aviso">Acima de ${txtNivel(M.nivel_max_m)} o modelo não tem mancha: a área que alaga fica subestimada.</div>`);}
function redraw(){taxaCmH=+sldTaxa.value;document.getElementById('taxatxt').textContent=taxaCmH;sld.setAttribute('aria-valuetext',txtNivel(nivelAtual()));
  document.getElementById('taxacen').textContent=cenTaxa(taxaCmH);
  if(modo==='margem')renderMargem();else if(modo==='impacto'){atualizarManchaNivel();renderImpacto();}alertaNivel();}
// ---------- rotas: clique ----------
let cam=null,camC=null,orig=null;
function m2(la1,lo1,la2,lo2){const dy=(la1-la2)*110540,dx=(lo1-lo2)*111320*Math.cos(la1*Math.PI/180);return dy*dy+dx*dx;}
function fmin(s){const m=Math.max(1,Math.round(s/60));return m<60?m+' min':Math.floor(m/60)+' h '+String(m%60).padStart(2,'0');}
function cadeia(ini,prox,pts){let i=ini,g=0;while(i>=0&&g++<6000){pts.push(D.nos[i]);const nx=prox[i];if(nx===i||nx<0)break;i=nx;}return pts;}
// trecho que alaga no cenário sai em vermelho tracejado; verde só no seco
const ARESTA=new Map();D.edges.forEach(e=>{ARESTA.set(e[0]+','+e[1],e);ARESTA.set(e[1]+','+e[0],e);});
function rotaPorTrecho(casa,op){const g=L.featureGroup();let molhado=!!casa[CF.na_mancha],i=casa[CF.no],n=0;
  let seg=[[casa[CF.lat],casa[CF.lon]],[casa[CF.proj_lat],casa[CF.proj_lon]],D.nos[i]];
  const fecha=()=>{if(seg.length>1)L.polyline(seg,molhado?{color:'#b3241b',weight:6,opacity:op,dashArray:'10 6'}:{color:'#0f8b46',weight:5,opacity:op}).addTo(g);};
  while(i>=0&&n++<6000){const nx=D.prox[i];if(nx===i||nx<0)break;const e=ARESTA.get(i+','+nx),m=!!(e&&e[2]>0);
    if(m!==molhado){fecha();seg=[D.nos[i]];molhado=m;}seg.push(D.nos[nx]);i=nx;}
  fecha();return g;}
// nível em que a água corta a rota até o abrigo oficial (rotas por nível). casa_agua_m
// vem arredondado em metros: olha também a cota dos nós da rota, como a margem.
function cortaNoNivel(ci,k){const no=NV.casa_no[k][ci];if(no<0||NV.casa_agua_m[k][ci]>0)return true;
  const P=NV.prox[k];let j=no,g=0;
  while(j>=0&&g++<6000){const c=D.cota_no[j];if(c!=null&&c<=NV.hand_m[k])return true;const nx=P[j];if(nx===j||nx<0)break;j=nx;}
  return false;}
// a casa é ilhada no cenário: o corte nunca fica acima do nível do cenário
function txtCorte(ci){const hs=NV.hand_m,kp=kNivel(M.nivel_projeto_m);let k=0;
  while(k<kp&&!cortaNoNivel(ci,k))k++;
  return k>0?` A água corta a rota entre ${txtNivel(hs[k-1])} e ${txtNivel(hs[k])}: <b>sair antes de ${txtNivel(hs[k-1])}</b>.`:' A rota já é cortada pela água com o rio baixo.';}
map.on('click',e=>{if(modo!=='rotas')return;
  const la=e.latlng.lat,lo=e.latlng.lng;let casa=null,bc=1e18,ci=-1;
  D.casas.forEach((c,i)=>{const d=m2(la,lo,c[CF.lat],c[CF.lon]);if(d<bc){bc=d;casa=c;ci=i;}});
  if(!casa||Math.sqrt(bc)>60){document.getElementById('rota').textContent='Nenhuma casa a menos de 60 m deste ponto.';return;}
  [cam,camC,orig].forEach(l=>{if(l)map.removeLayer(l);});cam=camC=null;
  orig=L.circleMarker([casa[CF.lat],casa[CF.lon]],{radius:7,color:'#0f8b46',fillColor:'#fff',fillOpacity:1,weight:3}).addTo(map);
  const base=()=>[[casa[CF.lat],casa[CF.lon]],[casa[CF.proj_lat],casa[CF.proj_lon]]];
  let txtC='';
  if(casa[CF.cand]&&D.rota_cand&&casa[CF.no_cand]!=null){camC=L.polyline(cadeia(casa[CF.no_cand],D.rota_cand.prox,base()),{color:'#5b2a86',weight:4,opacity:.9,dashArray:'6 6'}).addTo(map);
    txtC=`<br><span style="color:#4b2c78">Até o local candidato (linha roxa, não oficial; capacidade não avaliada): <b>${fmin(casa[CF.tempo_cand_s])}</b>.</span>`;}
  if(casa[CF.no]<0){document.getElementById('rota').innerHTML=casa[CF.proj_lat]==null
    ?'<b>Casa sem rota</b><br>A via mapeada mais próxima fica longe demais.'
    :'<b>Sem caminho até abrigo oficial</b><br>As ruas desta casa não se ligam, no mapa, às do abrigo (outra margem do rio ou trecho isolado).'+txtC;return;}
  const molha=(casa[CF.agua_m]||0)>0;
  cam=rotaPorTrecho(casa,molha&&camC?.55:.95).addTo(map);
  if(molha&&camC){camC.setStyle({weight:6,dashArray:null});camC.bringToFront();}
  const ab=D.abrigos.find(x=>x.id===casa[CF.abrigo])||D.abrigos[0];
  const ag=casa[CF.agua_m]||0,st=casa[CF.situacao],cota=casa[CF.cota_alaga];
  document.getElementById('rota').innerHTML=`<b>Rota até ${ab?ab.nome:'abrigo'}</b><br>A pé: <b>${(casa[CF.dist_m]/1000).toFixed(2)} km</b> · <b>${fmin(casa[CF.tempo_s])}</b> (idoso)`+
    (cota!=null?`<br>A casa alaga a partir de ${txtNivel(cota)}.`:'<br>A casa não alaga até o nível mapeado.')+
    (st==='ilhada'?`<br><span style="color:#4b2c78"><b>Ilhada</b>: não há caminho seco até o abrigo oficial neste cenário.${txtCorte(ci)}</span>`:'')+
    (ag>0?`<br><span style="color:#9e1b1b">⚠ A rota até o abrigo oficial atravessa ${Math.round(ag)} m de área que alaga (trecho vermelho): não é caminho seguro a pé neste cenário.</span>`:'<br><span style="color:#0f8b46">Rota fora da área que alaga.</span>')+txtC;});
// ---------- abas ----------
const NOMES={rotas:'Rotas',margem:'Margem',impacto:'Quem sai'};
const tabs=document.getElementById('tabs');
if(M.modos.length>1)tabs.innerHTML=M.modos.map(m=>`<button data-m="${m}">${NOMES[m]}</button>`).join('');else tabs.style.display='none';
function setModo(m){modo=m;
  tabs.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x.dataset.m===m));
  document.getElementById('sliders').classList.toggle('hide',m==='rotas');
  [manchaLayer,manchaNivelLayer,ruasLayer,casasLayer,casasImpLayer,candLayer].forEach(l=>map.removeLayer(l));
  [cam,camC,orig].forEach(l=>{if(l)map.removeLayer(l);});cam=camC=orig=null;
  abrigos.addTo(map);
  if(m==='impacto'){manchaNivelLayer.addTo(map);casasImpLayer.addTo(map);atualizarManchaNivel();renderImpacto();alertaNivel();}
  else if(m==='margem'){ruasLayer.addTo(map);renderMargem();alertaNivel();}
  else{manchaLayer.addTo(map);ruasLayer.addTo(map);casasLayer.addTo(map);candLayer.addTo(map);renderRotas();}
}
tabs.querySelectorAll('button').forEach(x=>x.onclick=()=>setModo(x.dataset.m));
sld.oninput=redraw;sldTaxa.oninput=redraw;
document.getElementById('selPrep').onchange=e=>{prepMin=+e.target.value;redraw();};
document.getElementById('taxatxt').textContent=taxaCmH;document.getElementById('taxacen').textContent=cenTaxa(taxaCmH);
if(M.abrigos_alagados.length){const e=document.getElementById('alertas');e.classList.remove('hide');
  e.textContent='No cenário, alaga(m): '+M.abrigos_alagados.join(', ')+'. Nos níveis em que um abrigo alaga, ele sai das rotas.';}
const mIni=location.hash.slice(1);setModo(M.modos.includes(mIni)?mIni:M.modos.includes('impacto')?'impacto':M.modos[0]); carregarManchaPorNivel(); aj(); setTimeout(aj,300); window.addEventListener('resize',aj);
if(innerWidth<600)document.getElementById('hud').classList.add('min');
</script></body></html>"""


if __name__ == "__main__":
    main()
