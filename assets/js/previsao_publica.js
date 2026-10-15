/* Leitura pública do mesmo feed: sem modelos comparativos ou replay histórico. */
(function () {
  'use strict';
  const keys = ['2h', '4h', '8h'];
  let connectionError = false;
  const fmt = () => window.PrevineFmtQuando;
  const put = (id, value) => { const node = document.getElementById(id); if (node) node.textContent = value; };
  const numeric = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
  const level = cm => numeric(cm) ? (Number(cm) / 100).toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' m' : '—';
  function age(value) {
    const date = fmt().parseWhen(value);
    return date ? Math.max(0, (Date.now() - date.getTime()) / 60000) : null;
  }
  function isReady(key, data) {
    if (!keys.includes(key) || !data || data.disponivel === false || data.shadow_only || String(data.modo).toLowerCase() === 'replay') return false;
    if (/sem hora v[aá]lida|sem previs[aã]o|inputs incompletos|indispon[ií]vel/.test(String(data.status || '').toLowerCase())) return false;
    const base = fmt().parseWhen(data.hora_modelo), target = fmt().parseWhen(data.hora_alvo);
    const hasValue = numeric(data.nivel_previsto_cm) || (Array.isArray(data.passos) && data.passos.some(row => Array.isArray(row) && numeric(row.length > 3 ? row[3] : row[2])));
    return !!(hasValue && base && target && target.getTime() > Date.now());
  }
  function qualityNote(data) {
    return data && data.qualidade_ao_vivo && data.qualidade_ao_vivo.status === 'ATENCAO'
      ? 'em atenção: desempenho recente abaixo do esperado' : '';
  }
  function targetLabel(value) {
    const date = fmt().parseWhen(value);
    if (!date) return 'Horário indisponível';
    const day = fmt().fmtWhen(date).split(' ')[0];
    const today = fmt().fmtWhen(new Date()).split(' ')[0];
    return (day === today ? 'Hoje, ' : day + ', ') + fmt().fmtClock(date);
  }
  function unavailableReason(data) {
    const reason = String(data && (data.status || '')).toLowerCase() + ' ' + String(data && data.qualidade_ao_vivo && data.qualidade_ao_vivo.status || '').toLowerCase();
    if (/telemetria.inv[aá]lida|suspenso_telemetria|suspens/.test(reason)) return 'suspensa para revisão dos dados';
    if (/base.desatualizada|base da rna|inputs incompletos|entradas/.test(reason)) return 'aguardando atualização das entradas';
    const target = data && fmt().parseWhen(data.hora_alvo);
    if (target && target.getTime() <= Date.now()) return 'aguardando uma nova previsão';
    return 'indisponível no momento';
  }
  function forecastText(point) {
    const quality = point.quality ? '. ' + point.quality : '';
    return 'Previsão para ' + fmt().fmtClockDate(point.time) + ': ' + level(point.cm) +
      '. Horizonte de ' + point.hours + ' horas, calculada com dados de ' + fmt().fmtClockDate(point.baseTime) + quality;
  }
  function mapHorizonLabel(key, data) {
    return isReady(key, data) ? 'Para ' + fmt().fmtClockDate(data.hora_alvo) + ' · ' + key.replace('h', ' h')
      : 'Previsão de ' + key.replace('h', ' h');
  }
  function renderHorizons(live, active, ready) {
    connectionError = false;
    const horizons = live && live.horizontes || {};
    const missing = [];
    document.querySelectorAll('#live-hz [data-live-hz]').forEach(button => {
      const key = button.dataset.liveHz, data = horizons[key];
      const ok = ready(key, data);
      // 8 h só aparece quando a própria validação do feed a habilitar.
      button.style.display = (key === '8h' && !ok) ? 'none' : '';
      button.disabled = !ok;
      button.classList.toggle('on', ok && key === active);
      button.setAttribute('aria-pressed', ok && key === active ? 'true' : 'false');
      const quality = ok && qualityNote(data);
      button.classList.toggle('forecast-attention', !!quality);
      const label = document.createElement('span'); label.textContent = ok ? targetLabel(data.hora_alvo) : key.replace('h', ' h');
      const when = document.createElement('small'); when.textContent = ok ? 'Horizonte de ' + key.replace('h', ' h') : 'indisponível';
      const nodes = [label, when];
      if (quality) { const warning = document.createElement('small'); warning.className = 'horizon-warning'; warning.textContent = 'Em atenção'; nodes.push(warning); }
      button.replaceChildren(...nodes);
      button.title = ok ? 'Previsão para ' + fmt().fmtClockDate(data.hora_alvo) + '. Calculada com dados de ' + fmt().fmtClockDate(data.hora_modelo) + (quality ? '. ' + quality : '')
        : 'Previsão de ' + key.replace('h', ' horas') + ': ' + unavailableReason(data);
      button.setAttribute('aria-label', button.title);
      if (!ok && key !== '8h') missing.push(key.replace('h', ' h') + ': ' + unavailableReason(data));
    });
    const group = document.getElementById('live-hz');
    if (group) group.classList.toggle('two-horizons', !ready('8h', horizons['8h']));
    const status = document.getElementById('live-horizon-status');
    if (status) {
      status.textContent = missing.length ? missing.join('. ') + '.' : '';
      status.style.display = missing.length ? '' : 'none';
    }
  }
  function update(options) {
    const live = options.live;
    if (!live) return;
    document.body.dataset.publicState = 'ready';
    const selected = options.selected || live;
    const telemetryWhen = live.telemetria_ultima_em || live.nivel_rio_agora_em || selected.telemetria_ultima_em;
    const telemetryAge = age(telemetryWhen);
    const robotAge = age(live.consultado_em || live.gerado_em);
    const ready = options.readyKeys || [];
    const hasForecast = ready.includes(options.horizon) && numeric(options.forecastCm);
    const notes = [];
    if (connectionError) notes.push('Não foi possível confirmar a atualização. Os últimos dados carregados continuam visíveis.');
    if (telemetryAge === null) notes.push('O horário da última leitura não está disponível.');
    else if (telemetryAge > 60) notes.push('A leitura do rio está atrasada. Confira o horário abaixo do nível observado.');
    if (robotAge !== null && robotAge > 15) notes.push('A atualização do painel está atrasada.');
    if (!ready.length) notes.push('As previsões estão indisponíveis no momento.');
    const attention = ready.filter(key => qualityNote(live.horizontes && live.horizontes[key]));
    if (attention.length) notes.push('Previsão de ' + attention.map(key => key.replace('h', ' h')).join(' e ') + ' em atenção: desempenho recente abaixo do esperado.');
    const notice = String(live.aviso || '').trim();
    if (notice && !/^EXPERIMENTAL\b/i.test(notice)) notes.push(notice);
    const qualityWarning = attention.length > 0;
    const warning = connectionError || telemetryAge === null || telemetryAge > 60 || robotAge > 15 || !ready.length || qualityWarning;
    const badge = document.getElementById('public-status');
    badge.classList.toggle('warn', warning);
    badge.textContent = connectionError ? 'Atualização não confirmada' : telemetryAge > 60 ? 'Leitura com atraso' : robotAge > 15 ? 'Atualização com atraso' : !ready.length ? 'Previsão indisponível' : telemetryAge === null ? 'Horário indisponível' : qualityWarning ? 'Previsão em atenção' : 'Leitura recente';
    put('s-now-label', 'Último nível observado');
    put('s-now', level(options.nowCm));
    put('public-observed-when', telemetryWhen ? fmt().fmtClockDate(telemetryWhen) + (telemetryAge !== null ? ' · ' + fmt().fmtAge(telemetryAge) : '') : 'Horário da leitura indisponível');
    put('s-hz', hasForecast ? '+' + options.horizon.replace('h', ' h') : 'sem previsão');
    put('s-fore', hasForecast ? level(options.forecastCm) : '—');
    put('public-forecast-when', hasForecast ? 'Para ' + fmt().fmtClockDate(selected.hora_alvo) : 'Aguardando uma nova previsão');
    put('public-forecast-base', hasForecast ? 'Calculada com dados de ' + fmt().fmtClockDate(selected.hora_modelo) : '');
    put('public-map-caption', 'Água estimada em ' + document.body.dataset.cityName + (hasForecast ? ' · previsão para ' + fmt().fmtClockDate(selected.hora_alvo) : ' · sem previsão disponível'));
    put('map-accessible-summary', document.body.dataset.cityName + ': último nível observado ' + level(options.nowCm) + '. ' + (hasForecast ? 'Previsão de ' + options.horizon.replace('h', ' horas') + ': ' + level(options.forecastCm) + ', para ' + fmt().fmtClockDate(selected.hora_alvo) + '. ' : 'Sem previsão disponível. ') + 'A mancha é uma estimativa de pesquisa. Não é alerta oficial.');
    const note = document.getElementById('public-service-note');
    note.textContent = notes.join(' ');
    note.hidden = !notes.length;
  }
  function failed(initial) {
    connectionError = true;
    const badge = document.getElementById('public-status');
    badge.classList.add('warn');
    badge.textContent = 'Atualização não confirmada';
    if (initial) {
      document.body.dataset.publicState = 'error';
      put('public-observed-when', 'Não foi possível carregar os dados atuais.');
      put('public-forecast-when', 'Previsão indisponível');
      put('public-forecast-base', '');
      put('public-map-caption', 'Dados atuais indisponíveis para ' + document.body.dataset.cityName);
    }
    const note = document.getElementById('public-service-note');
    note.textContent = initial ? 'Os dados atuais não carregaram. Tente novamente em instantes.' : 'Não foi possível confirmar a atualização. Os últimos dados carregados continuam visíveis.';
    note.hidden = false;
  }
  const spatial = {contours: 'loading', base: 'loading'};
  let retrySpatial = null;
  async function fetchContours(url, minimumMax) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(url, {cache:'no-store', signal:controller.signal});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      if (data.type !== 'FeatureCollection' || !Array.isArray(data.features) || !data.features.length) throw new Error('Contornos inválidos');
      const max = Math.max(...data.features.map(row => Number(row.properties && row.properties.nivel_m)));
      if (!Number.isFinite(max) || max < minimumMax) throw new Error('Contornos incompletos ou desatualizados');
      data._maxNivel = max;
      return data;
    } finally { clearTimeout(timer); }
  }
  function spatialStatus(part, status) {
    spatial[part] = status;
    const unavailable = spatial.contours === 'error';
    const loading = spatial.contours === 'loading';
    const baseError = spatial.base === 'error';
    const node = document.getElementById('public-spatial-status');
    if (!node) return;
    node.hidden = !unavailable && !loading && !baseError;
    node.classList.toggle('warn', unavailable || baseError);
    put('public-spatial-message', unavailable ? 'Estimativa espacial indisponível: a camada de água não carregou. Os níveis numéricos continuam disponíveis.'
      : loading ? 'Carregando a estimativa espacial…'
      : 'Imagem de satélite indisponível. O mapa de ruas foi selecionado; a estimativa de água é uma camada separada.');
    const button = document.getElementById('public-spatial-retry');
    if (button) button.hidden = !unavailable || !retrySpatial;
  }
  function bindSpatialRetry(callback) {
    retrySpatial = callback;
    const button = document.getElementById('public-spatial-retry');
    if (button) button.onclick = async () => {
      button.disabled = true;
      spatialStatus('contours', 'loading');
      try { await callback(); } catch (_) { spatialStatus('contours', 'error'); }
      finally { button.disabled = false; }
    };
    spatialStatus('contours', spatial.contours);
  }
  function setupMap(options) {
    const {map, sat, osm, labels, bounds, layerControl} = options;
    L.control.zoom({zoomInTitle: 'Ampliar mapa', zoomOutTitle: 'Reduzir mapa'}).addTo(map);
    const toggle = document.querySelector('.leaflet-control-layers-toggle');
    if (toggle) { toggle.title = 'Camadas do mapa'; toggle.setAttribute('aria-label', 'Camadas do mapa'); }
    map.on('popupopen', event => {
      const popup = event.popup && event.popup.getElement();
      const close = popup && popup.querySelector('.leaflet-popup-close-button');
      if (close) {
        close.title = 'Fechar informações';
        close.setAttribute('aria-label', 'Fechar informações');
      }
    });
    const extent = L.rectangle(bounds, {color:'#49675d',weight:1.5,dashArray:'6 5',fill:false,interactive:false}).addTo(map);
    layerControl.addOverlay(extent, 'Recorte do terreno (pode ter lacunas)');
    let failures = 0, switched = false;
    sat.on('tileerror', () => {
      if (!map.hasLayer(sat) || switched) return;
      if (++failures < 3) return;
      switched = true;
      map.removeLayer(sat);
      if (labels && map.hasLayer(labels)) map.removeLayer(labels);
      osm.addTo(map);
      spatialStatus('base', 'error');
    });
    sat.on('tileload', () => { failures = 0; });
    map.on('baselayerchange', event => {
      if (event.layer === sat) { failures = 0; switched = false; }
      spatialStatus('base', 'ready');
    });
    spatialStatus('base', 'ready');
  }
  window.PREVINE_PUBLIC = {isReady, renderHorizons, update, failed, qualityNote, targetLabel, unavailableReason, forecastText, mapHorizonLabel, spatialStatus, bindSpatialRetry, setupMap, fetchContours};
})();
