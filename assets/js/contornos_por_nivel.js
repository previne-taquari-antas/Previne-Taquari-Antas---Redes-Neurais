// Contornos HAND por nível para as páginas de previsão.
// Baixa um índice leve (propriedades de todos os níveis, sem geometria) e busca a geometria de
// cada nível só quando ela vai ser desenhada. Se o índice não existir (ex.: arquivo aberto fora
// do Pages), baixa o arquivo completo, como antes. O índice e os arquivos por nível são gerados
// no deploy por codigo_python/02_mdt_hand_mancha/dividir_contornos_por_nivel.py.
(function (root, factory) {
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.PrevineContornos = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  'use strict';

  function indiceDe(url) {
    return String(url).replace(/\.json(?:\?.*)?$/, '_niveis/indice.json');
  }

  function buscarJson(url, opcoes) {
    const runtime = root.PrevineSiteRuntime;
    const pedido = runtime ? runtime.fetchResource(url, opcoes) : root.fetch(url, opcoes);
    return pedido.then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status + ' em ' + url);
      return r.json();
    });
  }

  function colecaoPorNivel(indice, urlIndice) {
    const base = new URL('.', new URL(urlIndice, root.document ? root.document.baseURI : urlIndice)).href;
    // A versão no endereço deixa o navegador guardar cada nível até a fonte mudar.
    const versao = indice.fonte_sha256 ? '?v=' + String(indice.fonte_sha256).slice(0, 16) : '';
    const pendentes = {};
    const features = indice.niveis.map(function (n) {
      return { type: 'Feature', properties: n.properties, geometry: null, _arquivo: n.arquivo };
    });
    return {
      type: 'FeatureCollection',
      features: features,
      metadata: indice.metadata,
      _porNivel: true,
      carregarGeometria: function (feat) {
        if (feat.geometry) return Promise.resolve(feat);
        const arquivo = feat._arquivo;
        if (!pendentes[arquivo]) {
          pendentes[arquivo] = buscarJson(base + arquivo + versao, {}).then(function (f) {
            if (!f || !f.geometry) throw new Error('nível sem geometria: ' + arquivo);
            feat.geometry = f.geometry;
            return feat;
          }).catch(function (erro) {
            delete pendentes[arquivo];
            throw erro;
          });
        }
        return pendentes[arquivo];
      },
    };
  }

  function carregar(urlCompleto) {
    const urlIndice = indiceDe(urlCompleto);
    return buscarJson(urlIndice, { cache: 'no-store' }).then(function (indice) {
      if (!indice || !Array.isArray(indice.niveis) || !indice.niveis.length) throw new Error('índice de contornos vazio');
      return colecaoPorNivel(indice, urlIndice);
    }).catch(function (erro) {
      if (root.console) root.console.warn('contornos por nível indisponíveis; usando o arquivo completo', erro);
      // O arquivo completo tem dezenas de MB: 12 s (padrão do runtime) não bastam numa rede lenta.
      return buscarJson(urlCompleto, { cache: 'no-store', timeoutMs: 90000 });
    });
  }

  return { carregar: carregar, indiceDe: indiceDe };
});
