'use strict';
// Contrato de leitura pública: saídas antigas e comparativas nunca viram previsão atual.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const clock = Date.parse('2026-10-07T15:00:00-03:00');
class FixedDate extends Date {
  constructor(...args) { super(...(args.length ? args : [clock])); }
  static now() { return clock; }
}
const context = vm.createContext({window: {PrevineFmtQuando: require('../assets/js/fmt_quando.js')}, Date: FixedDate});
vm.runInContext(fs.readFileSync(path.join(root, 'assets/js/previsao_publica.js'), 'utf8'), context);
const ready = context.window.PREVINE_PUBLIC.isReady;
const valid = {modo:'ao_vivo', hora_modelo:'2026-10-07T14:00:00-03:00', hora_alvo:'2026-10-07T16:00:00-03:00', nivel_previsto_cm:400};
assert.equal(ready('2h', valid), true);
assert.equal(ready('2h', {...valid, nivel_previsto_cm:0}), true);
for (const overrides of [
  {hora_alvo:'2026-10-07T15:00:00-03:00'}, {hora_alvo:'2026-10-07T14:00:00-03:00'},
  {hora_alvo:null}, {hora_modelo:null}, {disponivel:false}, {shadow_only:true},
  {modo:'replay'}, {status:'inputs incompletos'}, {nivel_previsto_cm:null}, {nivel_previsto_cm:'inválido'}
]) assert.equal(ready('2h', {...valid, ...overrides}), false, JSON.stringify(overrides));
assert.equal(ready('2h_versao_b', valid), false);
assert.equal(ready('8h_v002', valid), false);
for (const city of ['santa_tereza', 'mucum']) {
  const html = fs.readFileSync(path.join(root, city+'_previsao_inundacao.html'), 'utf8');
  const prepare = html.match(/function prepareLiveData\(d\)\{[\s\S]*?\n\}/)[0];
  context.liveHz = '2h';
  context.liveData = null;
  context.liveHorizonReady = ready;
  context.updateLiveHzButtons = () => {};
  context.horizonHasForecast = d => d.nivel_previsto_cm != null;
  vm.runInContext(prepare, context);
  const unavailable = {modo:'ao_vivo',horizonte:'2h',passos:[],...valid,
    nivel_previsto_cm:2500,horizontes:{'2h':{disponivel:false},'4h':{disponivel:false},'8h':{disponivel:false}}};
  context.prepareLiveData(unavailable);
  assert.equal(context.liveHz, null, city+': valor residual na raiz não substitui horizonte indisponível');
  assert.equal(unavailable.horizontes['2h'].disponivel, false);
  const alternative = {...unavailable, horizontes:{'2h':{disponivel:false},'4h':valid,'8h':{disponivel:false},'2h_versao_b':valid}};
  context.prepareLiveData(alternative);
  assert.equal(context.liveHz, '4h', city+': fallback seleciona somente previsão principal disponível');
  console.log('OK público '+city+': indisponibilidade preservada e seleção sem comparativas');
}
console.log('OK público: alvo futuro, zero válido, falta de dados, replay e modelos comparativos');


// A versão B é a única RNA de 4h em ambas as páginas de Muçum.
const normalize4h = require('../assets/js/live_feed.js').selectPublicMucum4h;
const old = {modelo:'006', horizonte:'4h', disponivel:true, nivel_previsto_cm:472};
const versionB = {modelo:'015', horizonte:'4h_versao_b', disponivel:true,
  nivel_previsto_cm:423, qualidade_ao_vivo:{status:'NORMAL', mae_24h_cm:23}};
const previous = {local:'Muçum', horizontes:{
  '2h':{modelo:'2h'}, '4h':old, '4h_versao_b':versionB, '8h':{modelo:'8h'}
}};
const bothPages = normalize4h(previous, true);
assert.equal(bothPages.horizontes['4h'].modelo, '015');
assert.equal(bothPages.horizontes['4h'].nivel_previsto_cm, 423);
assert.equal(bothPages.horizontes['4h'].modelo_papel, 'principal');
assert.equal(bothPages.horizontes['4h'].horizonte, '4h');
assert.equal(bothPages.horizontes['4h_versao_b'], undefined);
assert.equal(bothPages.horizontes['2h'].modelo, '2h');
assert.equal(bothPages.horizontes['8h'].modelo, '8h');
assert.equal(previous.horizontes['4h'].modelo, '006', 'feed original imutável');
const unavailable = normalize4h({horizontes:{'4h':old,'4h_versao_b':{
  ...versionB, disponivel:false, nivel_previsto_cm:null, status:'indisponivel'
}}}, true);
assert.equal(unavailable.horizontes['4h'].modelo,'015');
assert.equal(unavailable.horizontes['4h'].disponivel,false,'nunca reativar 006');
assert.strictEqual(normalize4h(previous,false),previous,'outras cidades não alteradas');
const current = {horizontes:{'4h':{modelo:'015',horizonte:'4h'}}};
assert.strictEqual(normalize4h(current,true),current,'feed novo não precisa de cópia');
console.log('OK Muçum público e usuário: somente 4h versão B, inclusive com feed legado.');

// Cenários de comunicação e falha: verificar o que o visitante recebe, inclusive
// quando o horizonte em atenção não é o selecionado e o mapa falha separadamente.
class Node {
  constructor() {
    this.dataset = {}; this.attributes = {}; this.children = []; this.style = {};
    this.hidden = false; this.disabled = false; this.value = '';
    const classes = new Set();
    this.classList = {
      add: name => classes.add(name), contains: name => classes.has(name),
      toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name)
    };
  }
  set textContent(value) { this.value = String(value); this.children = []; }
  get textContent() { return this.value + this.children.map(child => child.textContent).join(' '); }
  setAttribute(name, value) { this.attributes[name] = value; }
  replaceChildren(...nodes) { this.value = ''; this.children = nodes; }
}
const ids = ['public-status','s-now-label','s-now','s-hz','s-fore','public-observed-when',
  'public-forecast-when','public-forecast-base','public-map-caption','map-accessible-summary',
  'public-service-note','live-hz','live-horizon-status','public-spatial-status','public-spatial-message','public-spatial-retry'];
const nodes = Object.fromEntries(ids.map(id => [id, new Node()]));
const buttons = ['2h','4h','8h'].map(key => { const node = new Node(); node.dataset.liveHz = key; return node; });
const body = new Node(); body.dataset.cityName = 'Santa Tereza';
context.document = {body, getElementById: id => nodes[id], createElement: () => new Node(),
  querySelectorAll: () => buttons, querySelector: () => null};
context.AbortController = AbortController;
context.setTimeout = setTimeout; context.clearTimeout = clearTimeout;
const ui = context.window.PREVINE_PUBLIC;
const h4 = {...valid, hora_modelo:'2026-10-07T13:00:00-03:00', hora_alvo:'2026-10-07T17:00:00-03:00',
  nivel_previsto_cm:435, qualidade_ao_vivo:{status:'ATENCAO'}};
const live = {...valid, telemetria_ultima_em:'2026-10-07T14:45:00-03:00',
  consultado_em:'2026-10-07T14:59:00-03:00',
  horizontes:{'2h':valid, '4h':h4, '8h':{disponivel:false,status:'SUSPENSO_TELEMETRIA_INVALIDA'}}};
const options = {live, selected:valid, horizon:'2h', readyKeys:['2h','4h'], nowCm:398, forecastCm:400};
ui.renderHorizons(live, '2h', ready);
ui.update(options);
assert.equal(nodes['public-status'].textContent, 'Previsão em atenção');
assert.match(nodes['public-service-note'].textContent, /4 h em atenção/);
assert.equal(buttons[0].attributes['aria-pressed'], 'true');
assert.equal(buttons[1].attributes['aria-pressed'], 'false');
assert.match(buttons[1].textContent, /Hoje, 17h.*Em atenção/);
assert.match(buttons[1].attributes['aria-label'], /07\/10 17h BRT.*07\/10 13h BRT/);
assert.equal(buttons[2].style.display,'none','8 h indisponível conserva a ocultação atual de main');
assert.equal(nodes['live-hz'].classList.contains('two-horizons'),true);
assert.equal(nodes['live-horizon-status'].style.display,'none');
assert.equal(ui.unavailableReason(live.horizontes['8h']),'suspensa para revisão dos dados');
assert.equal(ui.mapHorizonLabel('4h',h4),'Para 07/10 17h BRT · 4 h');
assert.equal(ui.mapHorizonLabel('4h',null),'Previsão de 4 h');
ui.renderHorizons({...live,horizontes:{...live.horizontes,'8h':valid}},'2h',ready);
assert.equal(buttons[2].style.display,'','8 h retorna quando o feed o habilita');
assert.equal(nodes['live-hz'].classList.contains('two-horizons'),false);
ui.renderHorizons(live,'2h',ready);
assert.match(nodes['public-forecast-base'].textContent, /07\/10 14h BRT/);
assert.match(ui.forecastText({hours:4, time:h4.hora_alvo, baseTime:h4.hora_modelo, cm:435,
  quality:ui.qualityNote(h4)}), /17h BRT: 4,35 m.*13h BRT.*em atenção/);
assert.equal(ui.targetLabel('2026-10-08T01:00:00-03:00'), '08/10, 1h');
assert.equal(ui.unavailableReason({status:'BASE_DESATUALIZADA'}), 'aguardando atualização das entradas');
assert.equal(ui.unavailableReason({...valid,hora_alvo:'2026-10-07T14:00:00-03:00'}), 'aguardando uma nova previsão');
ui.update({...options,readyKeys:[],horizon:null,forecastCm:null});
assert.equal(nodes['s-fore'].textContent, '—');
assert.equal(nodes['public-forecast-base'].textContent, '');
ui.update(options);

for (const city of ['santa_tereza','mucum']) {
  const html = fs.readFileSync(path.join(root, city+'_previsao_inundacao.html'), 'utf8');
  assert.ok(html.indexOf('id="river-overview"') < html.indexOf('<aside class="public-sidebar"'));
  assert.ok(html.indexOf('<aside class="public-sidebar"') < html.indexOf('<section class="public-map-panel"'));
  assert.equal((html.match(/id="live-hz"/g)||[]).length, 1);
  assert.match(html, /Sem mancha não significa local seguro/);
  assert.match(html, /margem ilustrativa fixa por horizonte/);
}
const muHtml = fs.readFileSync(path.join(root,'mucum_previsao_inundacao.html'),'utf8');
const zeroContext = vm.createContext({});
vm.runInContext(muHtml.match(/const HAND_ZERO_DEFAULT_CM=500;[\s\S]*?\n\}/)[0], zeroContext);
assert.equal(zeroContext.handZeroCm({bankfull_cm:1800}), 500, 'cota oficial não substitui zero espacial provisório');
assert.equal(zeroContext.handZeroCm({hand_zero_cm:0}), 0, 'zero explícito válido');
assert.equal(zeroContext.handZeroCm({hand_zero_cm:'inválido'}), 500);
vm.runInContext('let bankfull=500;'+muHtml.match(/function stageToHand\(cm\)\{[^}]+\}/)[0],zeroContext);
for (const [cm, expected] of [[398,-1.02],[435,-.65],[500,0],[600,1],[1800,13]]) {
  assert.equal(zeroContext.stageToHand(cm),expected,'conversão provisória conservada: '+cm+' cm');
}

async function spatialTests() {
  const collection = {type:'FeatureCollection',features:[{properties:{nivel_m:25},geometry:{type:'Polygon',coordinates:[]}}]};
  context.fetch = async () => ({ok:false,status:503});
  await assert.rejects(ui.fetchContours('/fixture',24.9), /HTTP 503/);
  context.fetch = async () => ({ok:true,json:async()=>({type:'FeatureCollection',features:[]})});
  await assert.rejects(ui.fetchContours('/fixture',24.9), /Contornos inválidos/);
  context.fetch = async () => ({ok:true,json:async()=>({...collection,features:[{properties:{nivel_m:15}}]})});
  await assert.rejects(ui.fetchContours('/fixture',24.9), /incompletos/);
  context.fetch = async () => ({ok:true,json:async()=>collection});
  assert.equal((await ui.fetchContours('/fixture',24.9))._maxNivel,25);
  ui.bindSpatialRetry(async () => { await ui.fetchContours('/fixture',24.9); ui.spatialStatus('contours','ready'); });
  ui.spatialStatus('base','ready'); ui.spatialStatus('contours','error');
  assert.match(nodes['public-spatial-message'].textContent,/Estimativa espacial indisponível/);
  assert.equal(nodes['public-spatial-retry'].hidden,false);
  assert.equal(nodes['s-fore'].textContent,'4,00 m','falha espacial preserva previsão numérica');
  await nodes['public-spatial-retry'].onclick();
  assert.equal(nodes['public-spatial-status'].hidden,true);
  assert.equal(nodes['public-spatial-retry'].disabled,false);

  const handlers = {}, mapHandlers = {}, sat = {on:(name,fn)=>{handlers[name]=fn;}}, labels = {};
  const active = new Set([sat,labels]);
  const map = {hasLayer:layer=>active.has(layer), removeLayer:layer=>active.delete(layer), on:(name,fn)=>{mapHandlers[name]=fn;}};
  const osm = {addTo:()=>active.add(osm)};
  context.L = {control:{zoom:()=>({addTo:()=>{}})}, rectangle:()=>({addTo:()=>({})})};
  ui.setupMap({map,sat,osm,labels,bounds:[],layerControl:{addOverlay:()=>{}}});
  handlers.tileerror(); handlers.tileerror(); handlers.tileload(); handlers.tileerror(); handlers.tileerror();
  assert.equal(active.has(sat),true,'tile carregado interrompe a sequência de falhas');
  handlers.tileerror();
  assert.equal(active.has(sat),false); assert.equal(active.has(labels),false); assert.equal(active.has(osm),true);
  assert.match(nodes['public-spatial-message'].textContent,/Imagem de satélite indisponível/);
  assert.equal(nodes['s-fore'].textContent,'4,00 m');
  mapHandlers.baselayerchange({layer:sat});
  assert.equal(nodes['public-spatial-status'].hidden,true);
  console.log('OK público: avisos por horizonte, base/alvo, falta de previsão, ordem móvel, zero HAND separado, falha/recarga espacial e fallback do satélite');
}
spatialTests().catch(error => { console.error(error); process.exitCode = 1; });
