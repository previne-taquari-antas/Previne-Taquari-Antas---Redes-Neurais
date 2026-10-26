'use strict';
// Contrato do carregador de contornos por nível: índice leve, geometria sob demanda e volta ao arquivo completo.
const assert = require('node:assert/strict');
const path = require('node:path');

const pedidos = [];
let respostas = {};
globalThis.document = { baseURI: 'https://exemplo.test/site/pagina.html' };
globalThis.console = { ...console, warn: () => {} };
globalThis.PrevineSiteRuntime = {
  fetchResource(url, opcoes) {
    pedidos.push({ url, opcoes });
    const chave = url.replace(/^https:\/\/exemplo\.test\/site\//, '').split('?')[0];
    const corpo = respostas[chave];
    return Promise.resolve(corpo === undefined
      ? { ok: false, status: 404, json: async () => { throw new Error('404'); } }
      : { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(corpo)) });
  },
};
const { carregar, indiceDe } = require(path.join(__dirname, '..', 'assets', 'js', 'contornos_por_nivel.js'));

const FONTE = 'assets/data/x/contornos_extravasamento.json';
const geometria = { type: 'MultiPolygon', coordinates: [[[[0, 0], [1, 0], [1, 1], [0, 0]]]] };

(async () => {
  assert.equal(indiceDe(FONTE), 'assets/data/x/contornos_extravasamento_niveis/indice.json');

  // 1) Com índice: features sem geometria, área disponível, geometria baixada uma vez só.
  respostas = {
    'assets/data/x/contornos_extravasamento_niveis/indice.json': {
      fonte_sha256: 'abcdef0123456789ffff', metadata: { cidade: 'x' },
      niveis: [{ arquivo: 'n0010.json', properties: { nivel_m: 0.1, area_ha: 3.4 } },
               { arquivo: 'n0020.json', properties: { nivel_m: 0.2, area_ha: 5.0 } }],
    },
    'assets/data/x/contornos_extravasamento_niveis/n0020.json': { type: 'Feature', properties: { nivel_m: 0.2, area_ha: 5.0 }, geometry: geometria },
  };
  pedidos.length = 0;
  const fc = await carregar(FONTE);
  assert.equal(fc._porNivel, true);
  assert.equal(fc.features.length, 2);
  assert.equal(fc.features[1].properties.area_ha, 5.0);
  assert.equal(fc.features[1].geometry, null);
  const [a, b] = await Promise.all([fc.carregarGeometria(fc.features[1]), fc.carregarGeometria(fc.features[1])]);
  assert.equal(a, b);
  assert.deepEqual(fc.features[1].geometry, geometria);
  const niveis = pedidos.filter((p) => p.url.includes('n0020.json'));
  assert.equal(niveis.length, 1, 'pedidos simultâneos do mesmo nível viram um só');
  assert.ok(niveis[0].url.endsWith('n0020.json?v=abcdef0123456789'), 'versão da fonte no endereço do nível');
  await fc.carregarGeometria(fc.features[1]);
  assert.equal(pedidos.filter((p) => p.url.includes('n0020.json')).length, 1, 'nível em cache não é baixado de novo');

  // 2) Nível que falha pode ser tentado de novo.
  await assert.rejects(fc.carregarGeometria(fc.features[0]));
  respostas['assets/data/x/contornos_extravasamento_niveis/n0010.json'] = { type: 'Feature', properties: {}, geometry: geometria };
  await fc.carregarGeometria(fc.features[0]);
  assert.deepEqual(fc.features[0].geometry, geometria);

  // 3) Sem índice: volta ao arquivo completo, com prazo maior que o padrão do runtime.
  respostas = { [FONTE]: { type: 'FeatureCollection', features: [{ type: 'Feature', properties: { nivel_m: 0.1 }, geometry: geometria }] } };
  pedidos.length = 0;
  const completo = await carregar(FONTE);
  assert.equal(completo._porNivel, undefined);
  assert.deepEqual(completo.features[0].geometry, geometria);
  const pedidoCompleto = pedidos.find((p) => p.url.endsWith(FONTE));
  assert.ok(pedidoCompleto.opcoes.timeoutMs >= 60000);

  console.log('OK contornos por nível: índice, cache, nova tentativa e arquivo completo');
})().catch((erro) => { console.error(erro); process.exit(1); });
