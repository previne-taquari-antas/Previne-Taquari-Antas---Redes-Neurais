(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.PrevineLiveFeed = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const apiAttempts = new Map();
  const LIVE_FILES = new Set(['previsao_ao_vivo.json','previsao_ao_vivo_mucum.json']);
  const MAX_REVISION_AGE_MS=15*60000;
  const API_COOLDOWN_MS=60000;

  const REPO = 'previne-taquari-antas/Previne-Taquari-Antas---Redes-Neurais';

  function withCacheBust(url) {
    return url + (String(url).includes('?') ? '&' : '?') + 'cb=' + Date.now();
  }

  function stampMs(data) {
    const value = data && (data.ultima_tentativa_em || data.consultado_em || data.gerado_em || data.atualizado_em || data.hora_modelo);
    if (!value) return NaN;
    const raw = String(value);
    return Date.parse(/[zZ]|[+-]\d{2}:?\d{2}$/.test(raw) ? raw : raw + '-03:00');
  }

  function pickNewest(feeds) {
    const ok = (feeds || []).filter(data => data && typeof data === 'object' && !Array.isArray(data) && Number.isFinite(stampMs(data)) && stampMs(data) <= Date.now()+5*60000);
    if (!ok.length) return null;
    ok.sort(function (a, b) { return (stampMs(b) || 0) - (stampMs(a) || 0); });
    return ok[0];
  }

  function fileName(path) {
    return String(path || '').split('?')[0].replace(/^.*\//, '');
  }

  function sourcesFor(path) {
    const file = fileName(path);
    if (!file) return [];
    return [
      ...(!LIVE_FILES.has(file) ? [{ label: 'arquivo publicado', url: file }] : []),
      { label: 'arquivo Raw', url: 'https://raw.githubusercontent.com/' + REPO + '/main/' + file },
      { label: 'CDN jsDelivr', url: 'https://cdn.jsdelivr.net/gh/' + REPO + '@main/' + file },
      { label: 'API GitHub', url: 'https://api.github.com/repos/' + REPO + '/contents/' + file + '?ref=main', kind: 'github-api' }
    ];
  }

  function primarySources(sources) {
    return (sources || []).filter(function (src) { return src.kind !== 'github-api'; });
  }

  function apiSources(sources) {
    return (sources || []).filter(function (src) { return src.kind === 'github-api'; });
  }

  async function fetchJson(url, timeoutMs) {
    const ctl = new AbortController();
    const timer = setTimeout(function () { ctl.abort(); }, timeoutMs || 8000);
    try {
      const response = await fetch(withCacheBust(url), { cache: 'no-store', signal: ctl.signal });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return await response.json();
    } finally {
      clearTimeout(timer);
    }
  }

  async function fetchGithubContents(apiUrl) {
    const meta = await fetchJson(apiUrl);
    const b64 = String(meta.content || '').replace(/\s/g, '');
    if (!b64) throw new Error('conteúdo vazio');
    return JSON.parse(decodeURIComponent(escape(atob(b64))));
  }

  async function fetchNewest(sources) {
    const list = sources || [];
    const settled = await Promise.allSettled(list.map(function (src) {
      return src.kind === 'github-api' ? fetchGithubContents(src.url) : fetchJson(src.url);
    }));
    const ok = [];
    const failures = [];
    settled.forEach(function (result, i) {
      const label = list[i].label || list[i].url;
      if (result.status === 'fulfilled' && result.value) ok.push(result.value);
      else failures.push(label + ': ' + (result.reason && result.reason.message || 'erro de rede'));
    });
    const newest = pickNewest(ok);
    if (!newest) throw new Error(failures.join(' · ') || 'fontes indisponíveis');
    return newest;
  }

  // Um único modelo +4h para Muçum (versão B), nas interfaces pública e do usuário.
  // Feeds legados ainda possuem ambas as RNAs: normalizar sem reativar a antiga.
  function selectPublicMucum4h(feed, isMucum) {
    if (!isMucum || !feed || !feed.horizontes) return feed;
    const versionB = feed.horizontes['4h_versao_b'];
    if (!versionB) return feed; // O feed novo já traz a versão B na chave 4h.
    const horizons = Object.assign({}, feed.horizontes);
    horizons['4h'] = Object.assign({}, versionB, {
      horizonte: '4h',
      rotulo: '4h · versão B',
      modelo_papel: 'principal',
      selection_rank: 1,
      origem_horizonte: '4h_versao_b'
    });
    delete horizons['4h_versao_b'];
    // Se B estiver sem previsão, manter indisponível: nunca voltar à RNA 006.
    return Object.assign({}, feed, { horizontes: horizons });
  }

  function isPublicMucumPage(path) {
    // Ambas as páginas consomem este feed; nenhuma deve mostrar a RNA 006.
    return fileName(path) === 'previsao_ao_vivo_mucum.json';
  }

  function needsRefresh(feed) {
    const revision=stampMs(feed);
    if(!Number.isFinite(revision)||Date.now()-revision>MAX_REVISION_AGE_MS) return true;
    const observation=feed && (feed.telemetria_ultima_em_utc||feed.telemetria_ultima_em||feed.nivel_rio_agora_em);
    if(!observation) return false; // Histories need only a valid revision timestamp.
    const time=stampMs({gerado_em:observation});
    return !Number.isFinite(time)||Date.now()-time>60*60000;
  }

  async function fetchLive(path) {
    const sources = sourcesFor(path);
    let feed, primaryError;
    try { feed=await fetchNewest(primarySources(sources)); }
    catch(error) { primaryError=error; }
    const fallback=apiSources(sources);
    const key=fileName(path), now=Date.now();
    const cached=apiAttempts.get(key);
    if(!feed||needsRefresh(feed)) {
      if(cached && now-cached.at<API_COOLDOWN_MS) {
        // Reuse the API response across consumers without repeating the request.
        const recovered=await cached.promise;
        feed=pickNewest([feed,recovered]);
      } else if(fallback.length) {
        const promise=fetchNewest(fallback).catch(()=>null);
        apiAttempts.set(key,{at:now,promise});
        feed=pickNewest([feed,await promise]);
      }
    }
    if(!feed) throw primaryError||new Error('fontes indisponíveis');
    return selectPublicMucum4h(feed, isPublicMucumPage(path));
  }

  return {
    needsRefresh: needsRefresh,
    stampMs: stampMs,
    pickNewest: pickNewest,
    sourcesFor: sourcesFor,
    primarySources: primarySources,
    apiSources: apiSources,
    withCacheBust: withCacheBust,
    fetchNewest: fetchNewest,
    fetchLive: fetchLive,
    selectPublicMucum4h: selectPublicMucum4h
  };
});

