/* Robôs calibrados em SOMBRA dentro de "Escolha a previsão".
   Lê previsao_sombra_<local>_recente.json (gravado de hora em hora por gerar_previsao_sombra_mucum.py) e mostra, por horizonte,
   a previsão mais recente de cada robô com o nome dele e o erro médio conferido nos últimos 7 dias.
   Só acompanhamento de pesquisa: não muda o mapa, o número principal nem alertas. */
(function () {
  const me = document.currentScript;
  const local = (me && me.dataset.local) || 'mucum';
  const arq = `previsao_sombra_${local}_recente.json`;
  const RAW = 'https://raw.githubusercontent.com/previne-taquari-antas/Previne-Taquari-Antas---Redes-Neurais/main/' + arq;
  const nf = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const n0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
  const ORDEM = { principal: 0, reserva: 2, componente: 1, registro_reserva_v4: 3, registro_v4: 3, sombra_horizonte: 4, controle: 5 };
  const HORIZONTES = [4, 8, 12];
  let dados = null, hzSel = null;

  const css = `
  .rs-box{margin-top:14px;padding-top:12px;border-top:1px dashed #cfe0d7}
  .rs-box h4{margin:0 0 2px;font-size:13px;color:#16352a}
  .rs-box .rs-sub{font-size:11px;color:#61716a;margin:0 0 8px;line-height:1.35}
  .rs-hz{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
  .rs-hz button{flex:1 1 56px;border:1px solid #cfe0d7;background:#fff;color:#1d5b44;border-radius:9px;padding:6px 6px;font-size:12px;font-weight:700;cursor:pointer}
  .rs-hz button.on{background:#1d5b44;color:#fff;border-color:#1d5b44}
  .rs-list{list-style:none;margin:0;padding:0;display:grid;gap:6px}
  .rs-list li{display:grid;grid-template-columns:1fr auto;gap:2px 8px;align-items:baseline;padding:7px 8px;border-radius:9px;background:#fff;border:1px solid #e3ece7}
  .rs-list li.principal{border-color:#1d5b44;box-shadow:inset 3px 0 0 #1d5b44}
  .rs-list .rs-nome{font-size:12px;font-weight:700;color:#16352a;line-height:1.3}
  .rs-list .rs-val{font-size:16px;font-weight:800;color:#16352a;white-space:nowrap}
  .rs-list .rs-info{grid-column:1/-1;font-size:11px;color:#61716a}
  .rs-box details summary{font-size:11.5px;color:#1d5b44;cursor:pointer;margin:8px 0 6px;font-weight:700}
  .rs-aviso{font-size:10.5px;color:#7a8a84;margin-top:8px;line-height:1.35}`;

  function quando(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return '—';
    return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}h`;
  }

  function robos() {
    const regs = (dados && dados.registros) || [];
    const fimObs = regs.filter(r => r.observado_cm != null).reduce((m, r) => (r.hora_alvo > m ? r.hora_alvo : m), '');
    const corte = fimObs ? new Date(new Date(fimObs).getTime() - 7 * 864e5).toISOString().slice(0, 16) : '';
    const por = new Map();
    regs.forEach(r => {
      const k = `${r.horizonte_h}|${r.modelo}`;
      let g = por.get(k);
      if (!g) { g = { h: r.horizonte_h, modelo: r.modelo, nome: r.nome_exibicao || r.modelo, papel: r.papel, ultimo: null, erros: [] }; por.set(k, g); }
      if (r.status === 'ok' && (!g.ultimo || r.hora_modelo > g.ultimo.hora_modelo)) g.ultimo = r;
      if (r.observado_cm != null && r.hora_alvo >= corte) g.erros.push(Math.abs(r.nivel_previsto_cm - r.observado_cm));
    });
    return [...por.values()].filter(g => g.ultimo);
  }

  function item(g) {
    const u = g.ultimo, mae = g.erros.length ? g.erros.reduce((a, b) => a + b, 0) / g.erros.length : null;
    const erro = mae == null ? 'ainda sem conferência' : `erro médio 7 dias ${n0.format(mae)} cm (${g.erros.length} conferidas)`;
    return `<li class="${g.papel === 'principal' ? 'principal' : ''}"><span class="rs-nome">${g.nome}</span>`
      + `<span class="rs-val">${nf.format(u.nivel_previsto_cm / 100)} m</span>`
      + `<span class="rs-info">para ${quando(u.hora_alvo)} · ${erro}</span></li>`;
  }

  function render() {
    const box = document.getElementById('rs-box');
    if (!box) return;
    const lista = robos();
    // só os horizontes calibrados; +5 h e +9 h (teste antigo de compensação do atraso) seguem só no histórico do robô
    const hs = [...new Set(lista.map(g => g.h))].filter(h => HORIZONTES.includes(h)).sort((a, b) => a - b);
    if (!hs.length) { box.hidden = true; return; }
    box.hidden = false;
    if (!hs.includes(hzSel)) hzSel = hs.includes(8) ? 8 : hs[0];
    const doH = lista.filter(g => g.h === hzSel).sort((a, b) => (ORDEM[a.papel] ?? 3) - (ORDEM[b.papel] ?? 3) || a.nome.localeCompare(b.nome, 'pt-BR'));
    const principais = doH.filter(g => g.papel !== 'componente'), partes = doH.filter(g => g.papel === 'componente');
    box.querySelector('.rs-hz').innerHTML = hs.map(h => `<button type="button" data-rs-h="${h}" class="${h === hzSel ? 'on' : ''}" aria-pressed="${h === hzSel}">+${h} h</button>`).join('');
    box.querySelector('.rs-corpo').innerHTML = `<ul class="rs-list">${principais.map(item).join('')}</ul>`
      + (partes.length ? `<details><summary>Partes das misturas (${partes.length})</summary><ul class="rs-list">${partes.map(item).join('')}</ul></details>` : '');
    box.querySelectorAll('[data-rs-h]').forEach(b => { b.onclick = () => { hzSel = Number(b.dataset.rsH); render(); }; });
    const ger = box.querySelector('.rs-gerado');
    if (ger) ger.textContent = dados.gerado_em ? `Rodada de ${quando(dados.gerado_em)}. ` : '';
  }

  async function carregar() {
    for (const url of [RAW, arq]) {
      try {
        const r = await fetch(url + '?cb=' + Date.now(), { cache: 'no-store' });
        if (!r.ok) continue;
        const j = await r.json();
        if (j && Array.isArray(j.registros)) { dados = j; render(); return; }
      } catch (e) { /* tenta a próxima fonte */ }
    }
  }

  function montar() {
    const sec = document.querySelector('.public-prediction');
    if (!sec || document.getElementById('rs-box')) return;
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const box = document.createElement('div'); box.id = 'rs-box'; box.className = 'rs-box'; box.hidden = true;
    box.innerHTML = '<h4>Robôs calibrados (em teste)</h4>'
      + '<p class="rs-sub">Cada modelo calibrado roda de hora em hora. Escolha o horizonte para comparar.</p>'
      + '<div class="rs-hz" role="group" aria-label="Horizonte dos robôs calibrados"></div><div class="rs-corpo"></div>'
      + '<p class="rs-aviso"><span class="rs-gerado"></span>'+(local==='mucum'?'Em Muçum, o principal de cada horizonte também aparece acima e no mapa, marcado como em teste. ':'Pesquisa em sombra: não muda o mapa. ')+'Não substitui os alertas da Defesa Civil.</p>';
    sec.appendChild(box);
    carregar();
    setInterval(carregar, 5 * 60 * 1000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', montar); else montar();
})();
