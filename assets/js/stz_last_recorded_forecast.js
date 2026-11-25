/* Último resultado verificável das RNAs de Santa Tereza.
 * Apenas histórico: nunca habilita previsão ao vivo, mapa de avanço ou alerta.
 */
(function () {
  'use strict';
  const owner = 'previne-taquari-antas/Previne-Taquari-Antas---Redes-Neurais';
  const raw = 'https://raw.githubusercontent.com/' + owner + '/main/';
  const panel = document.getElementById('stz-last-recorded');
  if (!panel || typeof fetch !== 'function') return;
  const formatLevel = n => {
    const value = Number(n);
    return Number.isFinite(value) ? (value / 100).toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' m' : '—';
  };
  const formatTime = v => {
    const match = String(v || '').match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    return match ? match[4] + ':' + match[5] + ' de ' + match[3] + '/' + match[2] : 'horário indisponível';
  };
  async function loadJson(name) {
    const response = await fetch(raw + name + '?t=' + Date.now(), {cache: 'no-store'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response.json();
  }
  function makeLine(text, strong) {
    const el = document.createElement('div');
    if (strong) {
      const bold = document.createElement('strong');
      bold.textContent = text;
      el.appendChild(bold);
    } else {
      el.textContent = text;
    }
    el.style.marginTop = '5px';
    return el;
  }
  function render(history, feed) {
    const rows = (history && Array.isArray(history.registros) ? history.registros : [])
      .filter(r => r && r.local === 'Santa Tereza' &&
        ['2h', '4h'].includes(r.horizonte) &&
        r.hora_modelo && r.hora_alvo &&
        r.nivel_previsto_cm !== null && r.nivel_previsto_cm !== '' &&
        Number.isFinite(Number(r.nivel_previsto_cm)));
    const latestFor = hz => rows.filter(r => r.horizonte === hz)
      .sort((a, b) => String(b.hora_modelo).localeCompare(String(a.hora_modelo)) ||
        String(b.criado_em || '').localeCompare(String(a.criado_em || '')))[0];
    panel.replaceChildren();
    panel.appendChild(makeLine('Últimas previsões registradas · histórico, não ao vivo', true));
    let hasForecast = false;
    for (const hz of ['2h', '4h']) {
      const r = latestFor(hz);
      if (!r) continue;
      hasForecast = true;
      const title = makeLine('RNA ' + hz + ': ' + formatLevel(r.nivel_previsto_cm), true);
      panel.appendChild(title);
      panel.appendChild(makeLine('Base ' + formatTime(r.hora_modelo) +
        ' → previsão para ' + formatTime(r.hora_alvo) +
        (r.criado_em ? ' · registro ' + formatTime(r.criado_em) : '')));
    }
    if (!hasForecast) panel.appendChild(makeLine('Nenhuma previsão numérica consta no histórico publicado.'));
    const observed = feed && Array.isArray(feed.serie_observada_ana) ? feed.serie_observada_ana : [];
    const day = String(feed && feed.telemetria_ultima_em || '').slice(0, 10);
    const at14 = day ? observed.find(r => r.hora === day + 'T14:00' || r.hora === day + 'T14:00:00') : null;
    if (at14 && Number.isFinite(Number(at14.nivel_cm))) {
      panel.appendChild(makeLine('Leitura observada às 14h (' + day.slice(8, 10) +
        '/' + day.slice(5, 7) + '): ' + formatLevel(at14.nivel_cm) +
        ' · medição ANA, não previsão.'));
    }
    const target14 = day ? rows.find(r => r.hora_alvo.startsWith(day + 'T14:')) : null;
    const base14 = day ? rows.find(r => r.hora_modelo.startsWith(day + 'T14:')) : null;
    if (day && !target14 && !base14) {
      panel.appendChild(makeLine('Não há previsão da RNA com base ou alvo às 14h registrada para esse dia.'));
    }
    panel.hidden = false;
  }
  Promise.allSettled([
    loadJson('historico_previsoes_ao_vivo.json'),
    loadJson('previsao_ao_vivo.json')
  ]).then(results => {
    const history = results[0].status === 'fulfilled' ? results[0].value : null;
    const feed = results[1].status === 'fulfilled' ? results[1].value : null;
    if (!history) {
      panel.replaceChildren(makeLine('Histórico de previsões temporariamente indisponível.'));
      panel.hidden = false;
      return;
    }
    render(history, feed);
  });
})();