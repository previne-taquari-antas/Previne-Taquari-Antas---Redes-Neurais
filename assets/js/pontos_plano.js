/* Menos pontos de encontro para um tempo máximo a pé: a mesma conta de
   codigo_python/09_rota_fuga/plano_pontos.py, para a página pontos_encontro.html refazer no navegador
   quando o usuário muda o tempo ou quem define os pontos. Inteiros (décimos de segundo) e as mesmas
   regras de empate: tests/test_pontos_encontro.py (PlanoParidadeTest) confere que as duas dão o mesmo resultado. */
(function (raiz) {
  'use strict';
  const MODOS = ['algoritmo', 'plano', 'plano+algoritmo'];
  const PONTOS_MAX = 30;

  function menor(a, b) { for (let i = 0; i < a.length; i++) { if (a[i] !== b[i]) return a[i] < b[i]; } return false; }
  function Fila() {
    const h = [];
    return {
      get size() { return h.length; },
      push(x) { h.push(x); let i = h.length - 1; while (i > 0) { const p = (i - 1) >> 1; if (!menor(x, h[p])) break; h[i] = h[p]; i = p; } h[i] = x; },
      pop() {
        const topo = h[0], fim = h.pop();
        if (h.length) {
          let i = 0;
          for (;;) {
            const l = 2 * i + 1, r = l + 1; let m = -1, melhor = fim;
            if (l < h.length && menor(h[l], melhor)) { m = l; melhor = h[l]; }
            if (r < h.length && menor(h[r], melhor)) { m = r; melhor = h[r]; }
            if (m < 0) break;
            h[i] = h[m]; i = m;
          }
          h[i] = fim;
        }
        return topo;
      }
    };
  }

  function reversa(rede) {
    const rev = Array.from({ length: rede.n_nos }, () => []);
    for (const [a, b, tab, tba] of rede.arestas) { rev[b].push([a, tab]); rev[a].push([b, tba]); }
    return rev;
  }

  function alcance(rev, s, teto) {
    const t = new Map([[s, 0]]), q = Fila(); q.push([0, s]);
    while (q.size) {
      const [tu, u] = q.pop();
      if (tu > (t.has(u) ? t.get(u) : Infinity)) continue;
      for (const [v, w] of rev[u]) {
        const nt = tu + w;
        if (nt <= teto && nt < (t.has(v) ? t.get(v) : Infinity)) { t.set(v, nt); q.push([nt, v]); }
      }
    }
    return t;
  }

  function cobertura(rede, rev, fontes, teto) {
    const out = new Map();
    for (const s of fontes) {
      if (out.has(s)) continue;
      const t = alcance(rev, s, teto), cob = new Map();
      rede.casas.forEach(([no, d0, , , precisa], i) => {
        if (precisa && no >= 0 && t.has(no) && d0 + t.get(no) <= teto) cob.set(i, d0 + t.get(no));
      });
      out.set(s, cob);
    }
    return out;
  }

  function destino(rede, rev, fontes) {
    const n = rede.n_nos, tt = Array(n).fill(Infinity), dono = Array(n).fill(-1), prox = Array(n).fill(-1), dist = Array(n).fill(0);
    const q = Fila();
    fontes.forEach((s, k) => { if (tt[s] === Infinity || k < dono[s]) { tt[s] = 0; dono[s] = k; q.push([0, k, s]); } });
    while (q.size) {
      const [tu, ku, u] = q.pop();
      if (tu !== tt[u] || ku !== dono[u]) continue;
      for (const [v, w] of rev[u]) {
        const nt = tu + w;
        if (menor([nt, ku, u], [tt[v], dono[v] >= 0 ? dono[v] : n, prox[v] >= 0 ? prox[v] : n])) {
          tt[v] = nt; dono[v] = ku; prox[v] = u; q.push([nt, ku, v]);
        }
      }
    }
    const comp = new Map();
    for (const [a, b, , , l] of rede.arestas) {
      for (const k of [a + ',' + b, b + ',' + a]) comp.set(k, Math.min(l, comp.has(k) ? comp.get(k) : l));
    }
    const feito = Array(n).fill(false);
    for (let v0 = 0; v0 < n; v0++) {
      const pilha = []; let v = v0;
      while (v >= 0 && !feito[v]) { pilha.push(v); v = prox[v]; }
      for (let j = pilha.length - 1; j >= 0; j--) {
        const u = pilha[j];
        dist[u] = prox[u] >= 0 ? dist[prox[u]] + comp.get(u + ',' + prox[u]) : 0; feito[u] = true;
      }
    }
    return { tt, dono, prox, dist };
  }

  function planeja(rede, tempoMaxMin, modo) {
    modo = modo || 'algoritmo';
    if (!MODOS.includes(modo)) throw Error('modo ' + modo);
    const teto = Math.round(tempoMaxMin * 600), rev = reversa(rede);
    const oficiais = modo !== 'algoritmo' ? rede.oficiais.filter(o => o.seguro) : [];
    const cands = modo !== 'plano' ? rede.candidatos : [];
    const cob = cobertura(rede, rev, oficiais.map(o => o.no).concat(cands.map(c => c.no)), teto);
    let escolhidos = oficiais.map((o, j) => ['plano', j]);
    const coberta = new Set(), usados = new Set(oficiais.map(o => o.no));
    for (const o of oficiais) for (const i of cob.get(o.no).keys()) coberta.add(i);
    while (escolhidos.length < PONTOS_MAX) {
      let melhor = null, chave = null;
      cands.forEach((c, j) => {
        if (usados.has(c.no)) return;
        let qtd = 0, soma = 0;
        for (const [i, t] of cob.get(c.no)) if (!coberta.has(i)) { qtd++; soma += t; }
        if (!qtd) return;
        const k = [-qtd, c.lugar ? 0 : 1, soma, c.no];
        if (chave === null || menor(k, chave)) { melhor = j; chave = k; }
      });
      if (melhor === null) break;
      escolhidos.push(['algoritmo', melhor]); usados.add(cands[melhor].no);
      for (const i of cob.get(cands[melhor].no).keys()) coberta.add(i);
    }
    const noDe = e => e[0] === 'plano' ? oficiais[e[1]].no : cands[e[1]].no;
    const doAlgoritmo = escolhidos.filter(e => e[0] === 'algoritmo').reverse();
    for (const e of doAlgoritmo) {
      const outros = escolhidos.filter(x => x !== e), resto = new Set();
      for (const x of outros) for (const i of cob.get(noDe(x)).keys()) resto.add(i);
      if ([...cob.get(noDe(e)).keys()].every(i => resto.has(i))) escolhidos = outros;
    }
    const fontes = escolhidos.map(noDe), r = destino(rede, rev, fontes), possivel = new Set();
    const nOf = escolhidos.filter(e => e[0] === 'plano').length;
    if (nOf > 0 && nOf < fontes.length) { // plano primeiro: nó que chega a um ponto oficial até o teto vai a ele
      const r1 = destino(rede, rev, fontes.slice(0, nOf));
      for (let v = 0; v < rede.n_nos; v++) {
        if (r1.tt[v] <= teto) { r.tt[v] = r1.tt[v]; r.dono[v] = r1.dono[v]; r.prox[v] = r1.prox[v]; r.dist[v] = r1.dist[v]; }
      }
    }
    for (const c of cob.values()) for (const i of c.keys()) possivel.add(i);
    const casas = rede.casas.map(([no, d0, dm0, , precisa], i) => {
      if (!precisa || no < 0 || r.dono[no] < 0) return [-1, null, null, 0];
      const alc = fontes.filter(s => cob.get(s).has(i)).length;
      return [r.dono[no], d0 + r.tt[no], Math.round((dm0 + r.dist[no] / 10) * 10) / 10, alc];
    });
    const precisam = rede.casas.map((c, i) => c[4] && c[0] >= 0 ? i : -1).filter(i => i >= 0);
    return {
      tempo_max_min: tempoMaxMin, modo,
      pontos: escolhidos.map(e => ({ origem: e[0], indice: e[1], no: noDe(e) })),
      casas, prox: r.prox, ponto_no: r.dono, tempo_no_ds: r.tt.map(v => v === Infinity ? null : v),
      resumo: {
        precisam: precisam.length,
        no_limite: precisam.filter(i => casas[i][1] !== null && casas[i][1] <= teto).length,
        sem_ponto_possivel: precisam.filter(i => !possivel.has(i)).length
      }
    };
  }

  const api = { planeja, MODOS, PONTOS_MAX };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else raiz.PontosPlano = api;
})(typeof self !== 'undefined' ? self : this);
