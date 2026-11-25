#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ajustes de leitura pública dos painéis de previsão ao vivo (Santa Tereza e Muçum).

Idempotente: aplica uma vez (marca o HTML com id="ajustes-publicos") e não mexe no resto
da página. Usado pelo gerador de Muçum e, para aplicar no HTML já publicado sem regenerar:

    python ajustes_publicos.py santa_tereza
    python ajustes_publicos.py mucum
"""
import os
import re
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PAGINAS = {
    "santa_tereza": "santa_tereza_previsao_inundacao.html",
    "mucum": "mucum_previsao_inundacao.html",
}

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


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in PAGINAS:
        sys.exit("uso: ajustes_publicos.py santa_tereza|mucum")
    caminho = os.path.join(RAIZ, PAGINAS[sys.argv[1]])
    antes = open(caminho, encoding="utf-8").read()
    depois = aplicar_ajustes_publicos(antes)
    if depois == antes:
        print("sem mudança (já aplicado) em", caminho)
    else:
        open(caminho, "w", encoding="utf-8", newline="").write(depois)
        print("ajustes públicos aplicados em", caminho)
