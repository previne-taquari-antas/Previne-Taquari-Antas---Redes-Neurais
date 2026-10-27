#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera mucum_previsao_inundacao.html como CÓPIA FIEL de
santa_tereza_previsao_inundacao.html, trocando apenas os dados:
  - relevo (HAND) -> ANADEM de Muçum (recortado de mucum_inundacao.html)
  - eventos (cheias anteriores) -> campeões por horizonte de Muçum,
    reescritos no MESMO schema do ST: series [time, agora, obs, previsto]
    com o deslocamento do horizonte (agora=obs(t); obs=obs(t+H); prev=rna(t+H))
  - fonte do ao vivo -> previsao_ao_vivo_mucum.json
  - rótulos/estação/nível normal -> Muçum (86510000, montante 86472600, 500 cm)
A página e o JS ficam idênticos ao Santa Tereza — mesma aparência e interação.
"""
import os, re, json, sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ST = os.path.join(RAIZ, "santa_tereza_previsao_inundacao.html")
MANUAL = os.path.join(RAIZ, "mucum_inundacao.html")
SAIDA = os.path.join(RAIZ, "mucum_previsao_inundacao.html")
sys.path.insert(0, os.path.dirname(__file__))
from mucum_eventos_payload import COTA_INUND_CM, eventos_payload_json  # noqa: E402

ESTACAO = {"lat": -29.1672, "lon": -51.8686, "code": "86510000"}


def hand_payload():
    """HAND/mosaico de Muçum + schema da previsão (station/ponte/fonte)."""
    mh = open(MANUAL, encoding="utf-8").read()
    m = re.search(r'<script id="hand-data" type="application/json">(.*?)</script>', mh, re.DOTALL)
    p = json.loads(m.group(1))
    out = {
        "cols": p["cols"],
        "rows": p["rows"],
        "S": p["S"],
        "W": p["W"],
        "N": p["N"],
        "E": p["E"],
        "station": ESTACAO,
        "ponte": None,
        "bankfull_cm": p.get("bankfull_cm", 500),
        "fonte": p.get("fonte")
        or "Mosaico 2 m: drone + ANADEM — ver codigo_python/02_mdt_hand_mancha/gerar_mancha_mosaico.py",
        "hand_png_b64": p["hand_png_b64"],
    }
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def eventos_payload():
    return eventos_payload_json()

AJUSTES_CSS = """<style id="ajustes-publicos">
  .voltar-site{display:block;padding:8px 16px;font-size:12px;font-weight:600;color:#12654f;text-decoration:none;background:#f2f6f3;border-bottom:1px solid var(--line)}
  .voltar-site:hover,.voltar-site:focus-visible{text-decoration:underline}
  .public-defesa-civil{margin:10px 0 0;color:#5d7166;font-size:11px;line-height:1.5}
  .public-trend-espelho{display:none;margin-top:8px;padding:5px 10px;border-radius:999px;background:#edf6ef;color:#286346;font-size:12px;font-weight:700}
  @media(max-width:600px){
    body.public-forecast.has-gestor-chrome.gestor-fill-layout>main{display:flex;flex-direction:column;align-items:stretch}
    .public-forecast aside.public-sidebar{display:contents}
    .public-forecast .public-current{order:1;padding:16px 20px;border:1px solid var(--line);border-radius:16px;background:#fff}
    .public-forecast .public-current .public-number{font-size:44px}
    .public-trend-espelho:not(:empty){display:inline-block}
    .public-forecast #overview-trend-badge{display:none}
    .public-forecast #public-status{order:2;align-self:flex-start}
    .public-forecast #river-overview{order:3}
    .public-forecast .public-map-panel{order:4}
    .public-forecast .forecast-city-context{order:5}
    .public-forecast .public-prediction{order:6}
    .public-forecast .public-service-note{order:7}
    .public-forecast .public-details{order:8}
    .public-forecast .public-defesa-civil{order:9}
    .public-forecast .forecast-city-context,.public-forecast .public-details,.public-forecast .public-service-note{padding:14px 16px;border:1px solid var(--line);border-radius:16px;background:#fff}
  }
</style>
"""
AJUSTES_JS = """<script>
(function(){var o=document.getElementById('overview-trend-badge'),e=document.getElementById('public-trend-espelho');
if(!o||!e||!window.MutationObserver)return;
function s(){e.textContent=(o.textContent||'').trim()}
s();new MutationObserver(s).observe(o,{childList:true,characterData:true,subtree:true})})();
</script>
"""


def aplicar_ajustes_publicos(html):
    """Ajustes de leitura pública de Muçum (idempotente): número e tendência antes
    do gráfico no celular, sem aviso de ressalva, só Defesa Civil, sem zoom pela
    roda do mouse, link para o site do PREVINE e sem links às páginas de pesquisa."""
    if 'id="ajustes-publicos"' in html:
        return html
    # páginas de pesquisa fora do caminho público (as páginas continuam existindo)
    html = re.sub(r'\s*<section class="research-separate-link".*?</section>', "", html, count=1, flags=re.DOTALL)
    html = re.sub(r'\s*<article class="overview-insight">\s*<h3>Pesquisa separada</h3>.*?</article>',
                  "", html, count=1, flags=re.DOTALL)
    # aviso de ressalva sai; fica só a informação útil
    html = html.replace(
        '<p class="public-disclaimer">PREVINE · Pesquisa e previsão experimental.<br><strong>Não é alerta oficial.</strong></p>',
        '<p class="public-defesa-civil">Alertas da Defesa Civil: <strong>199</strong> · SMS <strong>40199</strong></p>')
    html = html.replace("Pesquisa científica; não é alerta oficial, ordem de evacuação ou autorização de rota.",
                        "Pesquisa científica.")
    html = html.replace("d.aviso||'EXPERIMENTAL — não é alerta oficial.'", "d.aviso||'Previsão experimental.'")
    # sem zoom pela roda do mouse (botões e pinça continuam)
    html = html.replace("L.map('map',{scrollWheelZoom:true})", "L.map('map',{scrollWheelZoom:false})")
    # link de volta ao site do PREVINE, no topo
    html = re.sub(r'(<body[^>]*>)', r'\1\n<a class="voltar-site" href="https://www.ufrgs.br/previne/">← Site do PREVINE</a>',
                  html, count=1)
    # tendência (subindo/baixando) espelhada junto do número principal
    html = html.replace('<span id="public-observed-when" class="public-time">',
                        '<span id="public-trend-espelho" class="public-trend-espelho" aria-live="polite"></span>\n      '
                        '<span id="public-observed-when" class="public-time">', 1)
    html = html.replace("</head>", AJUSTES_CSS + "</head>", 1)
    html = html.replace("</body>", AJUSTES_JS + "</body>", 1)
    return html


def main():
    if "--so-ajustes" in sys.argv:  # aplica só os ajustes públicos no HTML já publicado
        antes = open(SAIDA, encoding="utf-8").read()
        open(SAIDA, "w", encoding="utf-8", newline="").write(aplicar_ajustes_publicos(antes))
        print("ajustes públicos aplicados em", SAIDA)
        return
    html = open(ST, encoding="utf-8").read()

    # 1) troca o bloco de relevo (hand-data)
    html = re.sub(r'(<script id="hand-data" type="application/json">).*?(</script>)',
                  lambda m: m.group(1) + hand_payload() + m.group(2), html, count=1, flags=re.DOTALL)
    # 2) troca o bloco de eventos (event-data)
    html = re.sub(r'(<script id="event-data" type="application/json">).*?(</script>)',
                  lambda m: m.group(1) + eventos_payload() + m.group(2), html, count=1, flags=re.DOTALL)

    # 3) rótulos e config (substituições textuais)
    subs = [
        ("PREVINE · Até onde a água pode chegar — Santa Tereza",
         "PREVINE · Previsão de inundação ao vivo — Muçum"),
        ("Santa Tereza · bacia Taquari-Antas", "Muçum · bacia Taquari-Antas"),
        ("A estação 86472600 informa o nível atual do rio em Santa Tereza.",
         "A estação 86510000 informa o nível atual do rio em Muçum; a montante 86472600 (Santa Tereza) entra na RNA com ~16h de trânsito."),
        ("  {code:'86472600',name:'Santa Tereza',lat:-29.1781,lon:-51.7322,role:'Estação alvo'},\n",
         "  {code:'86510000',name:'Muçum',lat:-29.1672,lon:-51.8686,role:'Estação alvo'},\n"
         "  {code:'86472600',name:'Santa Tereza',lat:-29.1781,lon:-51.7322,role:'Montante'},\n"),
        ("const target=meta.code==='86472600';",
         "const target=meta.code==='86510000';"),
        ("const COTA_INUND=1500;", f"const COTA_INUND={COTA_INUND_CM};"),
        ("let handArr=null, curEv=Object.keys(EVENTS)[0];\nlet bankfull=400",
         "let handArr=null, curEv=Object.keys(EVENTS)[0];\nlet bankfull=500"),
        ('<input type="range" id="bankfull" min="100" max="700" step="10" value="400"',
         '<input type="range" id="bankfull" min="100" max="900" step="10" value="500"'),
        ("previsao_ao_vivo.json", "previsao_ao_vivo_mucum.json"),
        ("historico_previsoes_ao_vivo.json", "historico_previsoes_ao_vivo_mucum.json"),
        ("assets/data/santa_tereza_inundacao/contornos_extravasamento.json",
         "assets/data/mucum_inundacao/contornos_extravasamento.json"),
        ("assets/data/santa_tereza_inundacao/mdt/altitude_terreno_10m.json",
         "assets/data/mucum_inundacao/mdt/altitude_terreno_10m.json"),
        ("cota de inundação · 15 m", "cota de inundação · 18 m"),
        ('<b id="s-cota">15,00 m</b>', '<b id="s-cota">18,00 m</b>'),
        ("O nível normal usado na mancha foi estimado pelo MDT ANADEM 30 m em ~405 cm e arredondado para 400 cm. O contorno HAND 0 é removido da camada colorida para não representar o leito normal como inundação. A cota de inundação oficial permanece 15 m (SGB/SACE). O refinamento depende de máscara observada do leito e validação com manchas de cheias.",
         "Nível normal (zero operacional da mancha) adotado provisoriamente em 500 cm na régua 86510000. O contorno HAND 0 é removido da camada colorida para não representar o leito normal como inundação. A cota de inundação oficial de Muçum é 18,00 m (1800 cm) — SGB/CPRM, boletim SAH Rio Taquari; 500 cm é cota de atenção, não confirmação de inundação. O refinamento depende de máscara observada do leito e validação com manchas de cheias."),
        ("estação Santa Tereza/SGB-ANA", "estação Muçum/SGB-ANA"),
        ("Nível do rio informado pela estação 86472600",
         "Nível do rio informado pela estação 86510000"),
        ("Padrão provisório calibrado em <b>4,0 m</b>",
         "Padrão provisório adotado em <b>5,0 m</b>"),
        ("Estação de Santa Tereza sem dado recente da ANA neste momento",
         "Estação de Muçum sem dado recente da ANA neste momento"),
        ("bankfull_cm?liveData.bankfull_cm:400",
         "bankfull_cm?liveData.bankfull_cm:500"),
        ("bankfull_cm||(liveData&&liveData.bankfull_cm)||400",
         "bankfull_cm||(liveData&&liveData.bankfull_cm)||500"),
        ("bankfull_cm||400", "bankfull_cm||500"),
    ]
    for a, b in subs:
        if a not in html:
            print("AVISO: trecho não encontrado p/ substituir:", a[:60])
        html = html.replace(a, b)

    # 4) qualquer "Santa Tereza" remanescente em texto vira Muçum
    html = html.replace("em Santa Tereza", "em Muçum")

    # fallback de evento ao vivo: ST usa mai24_2h; Muçum usa a cheia histórica tipada
    html = html.replace("liveFromEvent('mai24_2h','ALT')", "liveFromEvent('ev27_2h','ALT')")
    html = html.replace('liveFromEvent("mai24_2h","ALT")', 'liveFromEvent("ev27_2h","ALT")')
    html = html.replace("mai24_2h", "ev27_2h")

    # Ao usar o template de Santa Tereza, restaurar a calibração de Muçum:
    # régua de referência da mancha = 5,00 m (não 1,60 m) e NoData = 250.
    # Os valores são específicos da cidade, mesmo com interface padronizada.
    html = html.replace("const HAND_ZERO_DEFAULT_CM=160;", "const HAND_ZERO_DEFAULT_CM=500;")
    html = html.replace("if(value===255) return null;", "if(value===255||value===250) return null;")

    # Preservar o texto amigável do popup ao regenerar Muçum a partir
    # do template de Santa Tereza: o HAND permanece apenas no cálculo.
    html = html.replace(
        "      html+='<div><b>HAND:</b> '+handTxt+'</div>';",
        "",
    )
    html = html.replace(
        "Régua para a água chegar aqui:</b>",
        "Nível da régua para a água chegar aqui:</b>",
    )

    html = html.replace('      <button data-live-hz="8h">8h</button>\n', "")
    html = html.replace('      <button data-live-hz="12h">12h</button>\n', "")

    html = aplicar_ajustes_publicos(html)
    open(SAIDA, "w", encoding="utf-8").write(html)
    ev = json.loads(re.search(r'<script id="event-data" type="application/json">(.*?)</script>', html, re.DOTALL).group(1))
    print(f"escrito {SAIDA} | eventos: {len(ev)} ({', '.join(list(ev)[:8])})")


if __name__ == "__main__":
    main()
