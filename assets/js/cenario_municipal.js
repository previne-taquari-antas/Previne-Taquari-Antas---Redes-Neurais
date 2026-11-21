"use strict";
(() => {
  // idioma do fluxo principal (assets/js/cenario_idiomas.js); sem o arquivo, fica em português
  const I = window.CenarioIdioma || {
    tr: (t) => t,
    aplica() {},
    idioma: () => "pt",
  };
  let LANG = I.idioma();
  const LOC = () =>
    LANG === "en" ? "en-US" : LANG === "es" ? "es-ES" : "pt-BR";
  const $ = (id) => document.getElementById(id),
    E = CenarioEngine,
    fc = (features) => ({ type: "FeatureCollection", features }),
    state = {
      layers: {},
      sources: {},
      revision: 0,
      result: null,
      terrain: null,
    };
  const labels = {
      aoi: "Área de interesse",
      roads: "Vias",
      buildings: "Edificações",
      flood: "Inundação",
      eligible: "Áreas elegíveis",
      destinations: "Destinos",
      blocks: "Bloqueios",
    },
    colors = {
      aoi: "#526c62",
      roads: "#667d73",
      buildings: "#be731a",
      flood: "#2479c7",
      eligible: "#669e25",
      destinations: "#116e4a",
      blocks: "#c3382c",
    };
  const optionIds = [
    "municipality",
    "minutes",
    "speed",
    "peoplePerBuilding",
    "roadTypes",
    "allBuildings",
    "floodType",
    "floodEvent",
    "margin",
    "excludeFlood",
    "mode",
    "enforceCapacity",
    "drainArea",
    "handLevel",
  ];
  const defaultOptions = Object.fromEntries(
    optionIds.map((id) => [
      id,
      $(id).type === "checkbox" ? $(id).checked : $(id).value,
    ]),
  );
  function restoreDefaults() {
    for (const [id, value] of Object.entries(defaultOptions)) {
      if ($(id).type === "checkbox") $(id).checked = value;
      else $(id).value = value;
    }
  }
  // aviso de área reduzida pela página (cidade densa), mostrado com o resultado
  let avisoArea = "";
  let statusPt = null;
  const status = (text, error = false) => {
    statusPt = text;
    $("status").textContent = I.tr(text, LANG);
    $("status").className = "status" + (error ? " error" : "");
  };
  function download(content, name, type = "application/json") {
    const url = URL.createObjectURL(
        content instanceof Blob ? content : new Blob([content], { type }),
      ),
      a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function invalidate() {
    state.revision++;
    const tinha = !!state.result;
    state.result = null;
    if (routeLayer) routeLayer.clearLayers();
    if (resultLayer) resultLayer.clearLayers();
    // sem resultado anterior, a área do resultado fica escondida até haver um
    $("results").hidden = !tinha;
    $("results").textContent =
      "Configuração alterada. Calcule novamente para atualizar os resultados.";
    $("csv").disabled = $("routes").disabled = true;
  }
  function options() {
    return Object.fromEntries(
      optionIds.map((id) => [
        id,
        $(id).type === "checkbox" ? $(id).checked : $(id).value,
      ]),
    );
  }
  let map,
    editable,
    routeLayer,
    resultLayer,
    displayLayers = [],
    drawer = null,
    drawTarget = "blocks";
  if (!window.L) {
    status(
      "Não foi possível carregar o mapa. Verifique a conexão e recarregue.",
      true,
    );
    return;
  }
  map = L.map("map", { worldCopyJump: true }).setView([10, -20], 2);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    referrerPolicy: "strict-origin-when-cross-origin",
  }).addTo(map);
  editable = L.featureGroup().addTo(map);
  routeLayer = L.featureGroup().addTo(map);
  resultLayer = L.featureGroup().addTo(map);
  if (L.Control.Draw)
    map.addControl(
      new L.Control.Draw({
        position: "topright",
        draw: false,
        edit: { featureGroup: editable },
      }),
    );
  function popupText(text) {
    const span = document.createElement("span");
    span.textContent = text;
    return span;
  }
  function render() {
    editable.clearLayers();
    displayLayers.forEach((l) => map.removeLayer(l));
    displayLayers = [];
    $("layers").replaceChildren();
    for (const [kind, layer] of Object.entries(state.layers)) {
      const li = document.createElement("li");
      li.append(
        document.createTextNode(
          labels[kind] +
            ": " +
            layer.features.length +
            " · " +
            (state.sources[kind] || "Fonte não informada") +
            " ",
        ),
      );
      const b = document.createElement("button");
      b.textContent = "Remover";
      b.onclick = () => {
        delete state.layers[kind];
        delete state.sources[kind];
        invalidate();
        render();
      };
      li.append(b);
      $("layers").append(li);
      const geo = L.geoJSON(layer, {
        style: () => ({
          color: colors[kind],
          // a mancha gerada pelo terreno vem em muitas faixas: sem contorno, ela aparece como uma área só
          weight:
            kind === "flood" &&
            layer.features[0]?.properties?.modelo === "HAND experimental"
              ? 0
              : kind === "roads"
                ? 2
                : 2.5,
          fillOpacity: kind === "flood" ? 0.35 : 0.08,
        }),
        pointToLayer: (f, p) =>
          kind === "destinations"
            ? L.marker(p)
            : L.circleMarker(p, {
                radius: kind === "blocks" ? 8 : 3,
                color: colors[kind],
              }),
        onEachFeature: (f, l) => {
          l.bindPopup(
            popupText(
              labels[kind] +
                ": " +
                (f.properties?.nome || f.properties?.name || f.id || ""),
            ),
          );
          if (
            !["roads", "buildings"].includes(kind) &&
            layer.features.length < 2000 &&
            ["Point", "Polygon", "LineString"].includes(f.geometry.type)
          ) {
            l._scenarioKind = kind;
            l._scenarioFeature = f;
            editable.addLayer(l);
          }
        },
      });
      // Editable layers belong to their feature group only.
      geo.eachLayer((l) => {
        if (!editable.hasLayer(l)) {
          l.addTo(map);
          displayLayers.push(l);
        }
      });
    }
    renderDestinations();
  }
  function renderDestinations() {
    const box = $("destinationList");
    box.replaceChildren();
    for (const [i, f] of (
      state.layers.destinations?.features || []
    ).entries()) {
      const p = f.properties,
        wrap = document.createElement("fieldset"),
        legend = document.createElement("legend");
      legend.textContent = "Destino " + (i + 1);
      wrap.append(legend);
      for (const [key, label, type] of [
        ["nome", "Nome", "text"],
        ["tipo", "Tipo", "select"],
        ["capacidade", "Capacidade (pessoas)", "number"],
        ["ocupacao", "Ocupação atual", "number"],
      ]) {
        const l = document.createElement("label");
        l.textContent = label;
        const input = document.createElement(
          type === "select" ? "select" : "input",
        );
        if (type === "select") {
          for (const [value, text] of [
            ["ponto_de_encontro", "Ponto de encontro"],
            ["abrigo", "Abrigo"],
          ]) {
            const opt = document.createElement("option");
            opt.value = value;
            opt.textContent = text;
            input.append(opt);
          }
        } else {
          input.type = type;
          if (type === "number") {
            input.min = 0;
            input.step = 1;
            input.placeholder = key === "capacidade" ? "Desconhecida" : "0";
          }
        }
        input.value = p[key] ?? (key === "tipo" ? "ponto_de_encontro" : "");
        input.addEventListener("input", () => {
          input.setCustomValidity("");
          invalidate();
        });
        input.onchange = () => {
          invalidate();
          input.setCustomValidity("");
          if (
            type === "number" &&
            input.value !== "" &&
            (!Number.isInteger(Number(input.value)) || Number(input.value) < 0)
          ) {
            input.setCustomValidity(
              "Use capacidade e ocupação inteiras e não negativas.",
            );
            status("Use capacidade e ocupação inteiras e não negativas.", true);
            return;
          }
          p[key] =
            type === "number"
              ? input.value === ""
                ? null
                : Number(input.value)
              : input.value;
          invalidate();
        };
        l.append(input);
        wrap.append(l);
      }
      const del = document.createElement("button");
      del.textContent = "Excluir destino";
      del.onclick = () => {
        state.layers.destinations.features.splice(i, 1);
        invalidate();
        render();
      };
      wrap.append(del);
      box.append(wrap);
    }
  }
  function fit() {
    const features =
      state.layers.aoi?.features ||
      state.layers.roads?.features ||
      Object.values(state.layers).flatMap((v) => v.features);
    if (features?.length) {
      const b = L.geoJSON(fc(features)).getBounds();
      if (b.isValid()) map.fitBounds(b, { padding: [20, 20], maxZoom: 16 });
    }
  }
  function startDraw(kind, type) {
    if (drawer) drawer.disable();
    drawTarget = kind;
    if (!L.Draw) {
      status("Ferramenta de desenho indisponível. Importe um GeoJSON.", true);
      return;
    }
    drawer = new L.Draw[type](map, {
      allowIntersection: false,
      shapeOptions: { color: colors[kind] },
    });
    drawer.enable();
    status("Desenhe no mapa; finalize o desenho para registrar.");
  }
  $("drawArea").onclick = () => startDraw("aoi", "Polygon");
  $("draw").onclick = () => {
    const k = $("drawKind").value;
    startDraw(
      k === "destination"
        ? "destinations"
        : k === "eligible"
          ? "eligible"
          : k === "flood"
            ? "flood"
            : "blocks",
      k === "destination" || k === "blockPoint"
        ? "Marker"
        : k === "blockLine"
          ? "Polyline"
          : "Polygon",
    );
  };
  map.on("draw:created", (e) => {
    const f = e.layer.toGeoJSON();
    f.properties =
      drawTarget === "destinations"
        ? {
            nome: "Novo destino",
            tipo: "ponto_de_encontro",
            capacidade: null,
            ocupacao: 0,
          }
        : {};
    if (drawTarget === "aoi") state.layers.aoi = fc([f]);
    else {
      state.layers[drawTarget] ??= fc([]);
      state.layers[drawTarget].features.push(f);
    }
    state.sources[drawTarget] = "Desenho municipal";
    invalidate();
    render();
    status("Desenho registrado. Revise os parâmetros antes de calcular.");
  });
  map.on("draw:edited", (e) => {
    e.layers.eachLayer((l) => {
      l._scenarioFeature.geometry = l.toGeoJSON().geometry;
    });
    invalidate();
    queueMicrotask(render);
  });
  map.on("draw:deleted", (e) => {
    e.layers.eachLayer((l) => {
      const a = state.layers[l._scenarioKind].features,
        i = a.indexOf(l._scenarioFeature);
      if (i >= 0) a.splice(i, 1);
    });
    invalidate();
    queueMicrotask(render);
  });
  $("clearBlocks").onclick = () => {
    delete state.layers.blocks;
    invalidate();
    render();
  };
  async function fileJSON(file) {
    if (/\.tiff?$/i.test(file.name))
      throw Error(
        "Para GeoTIFF, use Importar meu MDT na etapa 1. O limite vetorial de 25 MB não se aplica ao MDT.",
      );
    if (file.size > 25 * 1024 * 1024)
      throw Error(
        "Arquivo vetorial ou de predefinições excede 25 MB. GeoTIFF deve ser importado na etapa 1, sem esse limite.",
      );
    return JSON.parse(await file.text());
  }
  async function importLayer(e, fixedKind) {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const kind = fixedKind || $("layerKind").value;
      let data;
      if (file.name.toLowerCase().endsWith(".zip")) {
        if (!window.shp) throw Error("Leitor Shapefile não carregou.");
        if (file.size > 25 * 1024 * 1024) throw Error("ZIP excede 25 MB.");
        const parsed = await shp(await file.arrayBuffer());
        data = Array.isArray(parsed)
          ? fc(parsed.flatMap((x) => x.features))
          : parsed;
      } else data = await fileJSON(file);
      data = E.validate(data, kind);
      if (kind === "destinations")
        for (const f of data.features) {
          const p = f.properties;
          p.nome ??= p.name;
          p.capacidade ??= p.capacity;
          p.ocupacao ??= p.occupancy;
          p.tipo ??= "ponto_de_encontro";
        }
      state.layers[kind] = data;
      state.sources[kind] = $("source").value.trim() || file.name;
      invalidate();
      render();
      fit();
      status("Camada importada: " + labels[kind] + ".");
    } catch (err) {
      status(err.message, true);
    } finally {
      e.target.value = "";
    }
  }
  $("upload").onchange = (e) => importLayer(e);
  $("areaUpload").onchange = (e) => importLayer(e, "aoi");
  // bases abertas para qualquer lugar do mundo (assets/js/cenario_osm.js)
  const O = window.CenarioOSM;
  async function pega(url, opts, segundos = 150, fora) {
    const c = new AbortController(),
      t = setTimeout(() => c.abort(), segundos * 1000),
      solta = () => c.abort();
    if (fora) fora.addEventListener("abort", solta);
    try {
      const r = await fetch(url, { ...opts, signal: c.signal });
      if (!r.ok) throw Error("HTTP " + r.status);
      return await r.json();
    } finally {
      clearTimeout(t);
      if (fora) fora.removeEventListener("abort", solta);
    }
  }
  const espera = (ms) => new Promise((r) => setTimeout(r, ms));
  // Os servidores de consulta do OpenStreetMap são gratuitos e às vezes ficam fora do ar.
  // Em vez de tentar um por vez (minutos de espera), começa pelo principal e, a cada poucos
  // segundos sem resposta, chama também o próximo; vale o primeiro que responder.
  function overpass(consulta, segundos = 60, prazo = 0) {
    const opts = {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "data=" + encodeURIComponent(consulta),
    };
    return new Promise((resolve) => {
      const geral = new AbortController(),
        timers = [];
      let feito = false,
        abertos = 0,
        prox = 0;
      const fim = (r) => {
        if (feito) return;
        feito = true;
        timers.forEach(clearTimeout);
        geral.abort();
        resolve(r);
      };
      const chama = () => {
        if (feito || prox >= O.SERVIDORES.length) return;
        const url = O.SERVIDORES[prox++],
          t0 = Date.now();
        abertos++;
        pega(url, opts, segundos, geral.signal)
          .then(fim)
          .catch((err) => {
            console.warn(url, Math.round((Date.now() - t0) / 1000) + " s", err);
            chama(); // falhou: o próximo entra já
          })
          .finally(() => {
            abertos--;
            if (!feito && !abertos && prox >= O.SERVIDORES.length) fim(null);
          });
      };
      chama();
      for (let k = 1; k < O.SERVIDORES.length; k++)
        timers.push(setTimeout(chama, 6000 * k));
      // prazo total (s): passou, cancela o que ainda está aberto
      if (prazo) timers.push(setTimeout(() => fim(null), prazo * 1000));
    });
  }
  // reserva: o servidor oficial do OpenStreetMap, em ladrilhos pequenos (3 de cada vez); ladrilho
  // com coisa demais é dividido em quatro
  async function mapaOficial(bbox, aviso, sinal) {
    const fila = O.ladrilhos(bbox).map((c) => [c, 0]),
      partes = [];
    let feitos = 0,
      total = fila.length;
    const um = async () => {
      while (fila.length && !(sinal && sinal.aborted)) {
        const [c, nivel] = fila.shift();
        try {
          partes.push(O.deMapa(await pega(O.urlMapa(c), {}, 60, sinal)));
          feitos++;
          aviso(feitos, total);
        } catch (err) {
          if (/HTTP 400/.test(err.message) && nivel < 2) {
            fila.push(...O.quartos(c).map((q) => [q, nivel + 1]));
            total += 3;
          } else throw err;
        }
      }
    };
    // um ladrilho que falha de vez para os outros também
    const para = new AbortController();
    if (sinal) sinal.addEventListener("abort", () => para.abort());
    sinal = para.signal;
    await Promise.all([um(), um(), um()]).catch((err) => {
      para.abort();
      throw err;
    });
    if (para.signal.aborted) throw Error("cancelado");
    return O.junta(partes);
  }

  const vaiPara = ([w, s, e, n]) =>
    map.fitBounds(
      [
        [s, w],
        [n, e],
      ],
      { maxZoom: 16 },
    );
  function usaLimite(l) {
    try {
      state.layers.aoi = E.validate(
        { type: "Feature", properties: { nome: l.nome }, geometry: l.limite },
        "aoi",
      );
      state.sources.aoi = "OpenStreetMap (Nominatim): " + l.nome;
      sugereNome(l);
      invalidate();
      render();
      fit();
      const km2 = O.areaKm2(areaBox()),
        grande = km2 > O.AREA_MAX_KM2;
      status(
        grande
          ? `O limite tem cerca de ${Math.round(km2).toLocaleString(LOC())} km², grande para baixar as ruas e edificações. Aproxime o mapa da parte que inunda e toque em “Usar esta parte do mapa” (até ${O.AREA_MAX_KM2} km²).`
          : "Área de interesse definida. Agora baixe as ruas e edificações na etapa 2.",
        grande,
      );
    } catch (err) {
      status(err.message, true);
    }
  }
  // o nome do lugar procurado identifica o cenário, enquanto a pessoa não escrever outro
  let nomeAuto = "";
  function sugereNome(l) {
    const campo = $("municipality");
    if (campo.value.trim() && campo.value !== nomeAuto) return;
    // o nome que a pessoa digitou (o do serviço de busca pode vir em outra escrita, como 熊本県)
    const digitado = $("placeQuery").value.split(",")[0].trim();
    nomeAuto = campo.value = (digitado || l.nome.split(",")[0].trim()).slice(
      0,
      140,
    );
  }
  // Lugar pequeno (um bairro): mostra ele inteiro. Município grande: abre já perto do centro da
  // cidade, numa escala em que a parte visível cabe no limite; aí basta tocar em "Usar esta parte".
  // município grande: troca o centro geométrico pela sede marcada no OSM (poucos segundos; se a
  // API não responder, fica o ponto do Nominatim)
  async function acertaSede(l) {
    if (l.sedeVista || !l.relacao || !l.centro) return;
    l.sedeVista = true;
    if (O.areaKm2(l.caixa) <= O.AREA_MAX_KM2) return;
    try {
      const ref = O.sedeDaRelacao(await pega(O.urlRelacao(l.relacao), {}, 6));
      const p = ref && O.pontoDoNo(await pega(O.urlNo(ref), {}, 6), l.caixa);
      if (p) l.centro = p;
    } catch (e) {
      // sem a sede, vale o ponto central do Nominatim
    }
  }
  function irAoLugar(l) {
    if (l.centro && O.areaKm2(l.caixa) > O.AREA_MAX_KM2)
      map.setView([l.centro[1], l.centro[0]], 15);
    else vaiPara(l.caixa);
  }
  function mostraLugares(lista) {
    const ul = $("placeResults");
    ul.replaceChildren();
    for (const l of lista) {
      const li = document.createElement("li"),
        nome = document.createElement("div"),
        ir = document.createElement("button");
      nome.textContent = l.nome;
      ir.textContent = "Ver no mapa";
      ir.onclick = async () => {
        sugereNome(l);
        await acertaSede(l);
        irAoLugar(l);
      };
      li.append(nome, ir);
      if (l.limite) {
        const usar = document.createElement("button");
        usar.textContent = "Usar o limite como área";
        usar.onclick = () => usaLimite(l);
        li.append(usar);
      }
      ul.append(li);
    }
    I.aplica([ul], LANG);
    if (lista.length) {
      sugereNome(lista[0]);
      irAoLugar(lista[0]);
    }
  }
  // a área que está na tela vira a área de interesse (mais fácil que desenhar, ainda mais no celular)
  // link de um cenário feito pelos três passos: lugar, área, nível do rio, tempo e idioma
  function linkDoCenario() {
    const f = state.layers.aoi?.features?.[0];
    if (!f || state.sources.aoi !== "Área escolhida no mapa") return null;
    if (!/OpenStreetMap/.test(state.sources.roads || "")) return null;
    const c = f.geometry.coordinates[0],
      xs = c.map((p) => p[0]),
      ys = c.map((p) => p[1]),
      r5 = (v) => v.toFixed(5),
      u = new URL(location.href.split("?")[0].split("#")[0]);
    u.searchParams.set(
      "area",
      [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]
        .map(r5)
        .join(","),
    );
    u.searchParams.set("rio", $("autoLevel").value);
    u.searchParams.set("tempo", $("minutes").value);
    if ($("municipality").value.trim())
      u.searchParams.set("lugar", $("municipality").value.trim());
    if (LANG !== "pt") u.searchParams.set("lang", LANG);
    return u.toString();
  }
  function marcaArea(caixa) {
    // arredonda como no link (5 casas, cerca de 1 m): o link refaz exatamente a mesma área
    const [w, s, e, n] = caixa.map((v) => Math.round(v * 1e5) / 1e5);
    state.layers.aoi = E.validate(
      {
        type: "Feature",
        properties: { nome: "Área visível no mapa" },
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [w, s],
              [e, s],
              [e, n],
              [w, n],
              [w, s],
            ],
          ],
        },
      },
      "aoi",
    );
    state.sources.aoi = "Área escolhida no mapa";
  }
  $("viewArea").onclick = () => {
    try {
      const b = map.getBounds().pad(-0.04),
        // o mapa dá a volta no mundo: traz a longitude de volta para -180..180
        volta = Math.round((b.getWest() + b.getEast()) / 2 / 360) * 360,
        [w, s, e, n] = [
          b.getWest() - volta,
          b.getSouth(),
          b.getEast() - volta,
          b.getNorth(),
        ],
        km2 = O.areaKm2([w, s, e, n]);
      if (w < -180 || e > 180)
        throw Error(
          "Essa parte do mapa cruza a linha de data (longitude 180°). Arraste o mapa para um lado só dela e toque de novo.",
        );
      if (km2 > O.AREA_MAX_KM2)
        throw Error(
          (km2 > 20000
            ? "A área na tela é grande demais."
            : `A área na tela tem cerca de ${Math.round(km2).toLocaleString(LOC())} km².`) +
            ` Aproxime o mapa até a parte que inunda (até ${O.AREA_MAX_KM2} km²) e toque de novo.`,
        );
      marcaArea([w, s, e, n]);
      avisoArea = "";
      invalidate();
      render();
      passoFeito(2);
      $("areaOk").hidden = false;
      $("areaOk").textContent = I.tr(
        `Área marcada: cerca de ${km2.toLocaleString(LOC(), { maximumFractionDigits: 1 })} km².`,
        LANG,
      );
      if (celular()) mostra($("passo3"));
      status(
        `Área marcada (cerca de ${km2.toLocaleString(LOC(), { maximumFractionDigits: 1 })} km²). Agora informe quanto o rio sobe e toque em Calcular.`,
      );
    } catch (err) {
      status(err.message, true);
    }
  };
  // passos do topo: marca o que já foi feito e, no celular, leva a pessoa até onde precisa olhar
  const celular = () => matchMedia("(max-width: 800px)").matches;
  const passoFeito = (n, sim = true) =>
    $("passo" + n) && $("passo" + n).classList.toggle("feito", sim);
  const mostra = (el) =>
    el && el.scrollIntoView({ behavior: "smooth", block: "start" });
  $("viewAreaMap").onclick = () => $("viewArea").click();
  $("placeSearch").onclick = () =>
    busy($("placeSearch"), async () => {
      const q = $("placeQuery").value.trim();
      if (q.length < 3) throw Error("Escreva o nome do lugar.");
      status("Procurando “" + q + "”…");
      let lista;
      try {
        try {
          lista = O.lugares(await pega(O.urlLugar(q), {}, 30));
        } catch (primeira) {
          // o serviço de busca limita pedidos seguidos: uma segunda tentativa costuma passar
          await espera(2500);
          lista = O.lugares(await pega(O.urlLugar(q), {}, 30));
        }
      } catch (err) {
        throw Error(
          "A busca de lugares não respondeu. Tente de novo em instantes ou aproxime o mapa e desenhe a área.",
        );
      }
      if (lista.length) await acertaSede(lista[0]);
      mostraLugares(lista);
      passoFeito(1, lista.length > 0);
      if (lista.length && celular()) mostra($("map"));
      status(
        lista.length
          ? "Lugar encontrado. Agora aproxime o mapa da parte que inunda e toque em “Usar esta parte do mapa”."
          : "Nenhum lugar encontrado com esse nome. Tente incluir o estado ou o país.",
        !lista.length,
      );
    });
  $("placeQuery").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      $("placeSearch").click();
    }
  });
  $("osmDownload").onclick = () =>
    busy($("osmDownload"), async () => {
      const bbox = areaBox(),
        km2 = O.areaKm2(bbox);
      if (km2 > O.AREA_MAX_KM2)
        throw Error(
          `A área de interesse tem cerca de ${Math.round(km2).toLocaleString(LOC())} km². Para baixar do OpenStreetMap, use até ${O.AREA_MAX_KM2} km²: desenhe uma área menor em volta da parte que inunda.`,
        );
      status("Baixando ruas e edificações do OpenStreetMap…");
      // os rios da área (com folga) vêm junto: servem para gerar a mancha pelo terreno
      const caixaRios = O.folga(bbox);
      // Os servidores de consulta e o oficial correm juntos: o oficial entra se os outros não
      // responderem em 15 s, e vale o primeiro que trouxer os dados.
      let acabou = false;
      const cancelaOficial = new AbortController();
      const viaConsulta = overpass(O.consulta(bbox, caixaRios)),
        viaOficial = espera(15000).then(() => {
          if (acabou) return null;
          status(
            "Os servidores de consulta estão lentos. Baixando também do servidor oficial do OpenStreetMap…",
          );
          return mapaOficial(
            O.ladrilhos(caixaRios).length <= 16 ? caixaRios : bbox,
            (f, t) => {
              if (!acabou)
                status(
                  `Baixando do servidor oficial do OpenStreetMap: parte ${f} de ${t}…`,
                );
            },
            cancelaOficial.signal,
          ).catch((err) => {
            console.warn("api.openstreetmap.org", err);
            return null;
          });
        });
      const primeiro = (ps) =>
        new Promise((ok) => {
          let falta = ps.length;
          ps.forEach((p) =>
            p.then((v) => {
              if (v) ok(v);
              else if (!--falta) ok(null);
            }),
          );
        });
      const osm = await primeiro([
        viaConsulta.then((v) => v && { v, oficial: false }),
        viaOficial.then((v) => v && { v, oficial: true }),
        // prazo total: depois de 2 min, desiste com uma mensagem em vez de ficar parado
        espera(120000).then(() => null),
      ]);
      acabou = true;
      cancelaOficial.abort(); // o servidor oficial não segue baixando depois que outro respondeu
      if (!osm)
        throw Error(
          "O mapa das ruas e das casas não chegou em 2 minutos. Tente uma área menor (aproxime mais o mapa) ou tente de novo em alguns minutos.",
        );
      const bruto = O.converte(osm.v),
        r = osm.oficial ? O.recorta(bruto, bbox) : bruto;
      state.rios = { caixa: caixaRios, elements: bruto.rios };
      if (!r.roads.features.length)
        throw Error(
          "O OpenStreetMap não tem ruas mapeadas nessa área. Confira a área de interesse ou importe os arquivos do município.",
        );
      // curvas com muitos pontos viram menos trechos (os cruzamentos ficam): cabe uma área maior no cálculo
      r.roads = O.simplifica(r.roads);
      // Cidade densa: em vez de pedir para aproximar o mapa, reduz a área em volta do centro até caber no
      // cálculo (16 mil edificações não terminaram de calcular em 10 minutos no teste com serviços reais)
      let caixaFinal = null;
      for (let vez = 0; vez < 5; vez++) {
        const nb = r.buildings.features.length,
          ntr = O.trechos(r.roads);
        if (nb <= 10000 && ntr <= 15000) break;
        const f = Math.min(
            0.85,
            Math.sqrt(9000 / Math.max(nb, 1)),
            Math.sqrt(13000 / Math.max(ntr, 1)),
          ),
          c = caixaFinal || bbox,
          cx = (c[0] + c[2]) / 2,
          cy = (c[1] + c[3]) / 2,
          hx = ((c[2] - c[0]) / 2) * f,
          hy = ((c[3] - c[1]) / 2) * f;
        caixaFinal = [cx - hx, cy - hy, cx + hx, cy + hy];
        Object.assign(r, O.recorta(r, caixaFinal));
      }
      if (caixaFinal) {
        marcaArea(caixaFinal);
        const km2 = O.areaKm2(caixaFinal);
        $("areaOk").hidden = false;
        $("areaOk").textContent = I.tr(
          `Área marcada: cerca de ${km2.toLocaleString(LOC(), { maximumFractionDigits: 1 })} km².`,
          LANG,
        );
        avisoArea = `A área tinha casas e ruas demais para o cálculo e foi reduzida para cerca de ${km2.toLocaleString(LOC(), { maximumFractionDigits: 1 })} km² em volta do centro.`;
      } else avisoArea = "";
      if (r.buildings.features.length > 10000)
        throw Error(
          `Essa área tem edificações demais para o cálculo (${r.buildings.features.length.toLocaleString(LOC())}; o limite é 10 mil). Aproxime o mapa da parte que inunda, toque em “Usar esta parte do mapa” e baixe de novo.`,
        );
      const nt = O.trechos(r.roads);
      if (nt > 15000)
        throw Error(
          `Essa área tem ruas demais para o cálculo (${nt.toLocaleString(LOC())} trechos; o limite é 15 mil). Aproxime o mapa da parte que inunda, toque em “Usar esta parte do mapa” e baixe de novo.`,
        );
      const fonte =
        "OpenStreetMap (ODbL)" +
        (r.data ? ", dados de " + r.data.slice(0, 10) : "");
      // uma geometria com defeito no mapa não derruba o download: prédio vira ponto, o resto sai
      const ruas = O.aproveita(r.roads, (c) => E.validate(c, "roads")),
        casas = O.aproveita(r.buildings, (c) => E.validate(c, "buildings"));
      if (!ruas.fc.features.length)
        throw Error(
          "As ruas dessa área no OpenStreetMap vieram com defeito. Importe os arquivos do município.",
        );
      r.roads = ruas.fc;
      r.buildings = casas.fc;
      state.layers.roads = E.validate(r.roads, "roads");
      state.sources.roads = fonte;
      if (r.buildings.features.length) {
        state.layers.buildings = E.validate(r.buildings, "buildings");
        state.sources.buildings = fonte;
      }
      const defeito = ruas.fora + casas.fora,
        aviso =
          (casas.consertadas
            ? ` ${casas.consertadas} edificações com contorno defeituoso entraram como ponto.`
            : "") +
          (defeito
            ? ` ${defeito} itens com defeito no mapa ficaram de fora.`
            : "");
      invalidate();
      render();
      fit();
      const n0 = (v) => v.toLocaleString(LOC());
      status(
        `Baixado do OpenStreetMap: ${n0(r.roads.features.length)} ruas e ${n0(r.buildings.features.length)} edificações.` +
          (r.buildings.features.length
            ? aviso +
              (avisoArea ? " " + avisoArea : "") +
              " Falta a mancha de inundação (etapa 5)."
            : " Nenhuma edificação mapeada nessa área: importe as edificações do município."),
        !r.buildings.features.length,
      );
    });
  for (const id of optionIds) {
    $(id).addEventListener("change", invalidate);
    $(id).addEventListener("input", invalidate);
  }
  let worker = null,
    request = 0;
  const jobs = new Map();
  function compute(type, data, opts) {
    if (!worker) {
      const version = [...document.scripts]
        .filter((script) =>
          /\/cenario_(engine|terreno|municipal)\.js(?:\?|$)/.test(script.src),
        )
        .map(
          (script) => new URL(script.src).searchParams.get("v") || "audit-v2",
        )
        .join("-");
      const workerUrl = new URL(
        "assets/js/cenario_worker.js",
        document.baseURI,
      );
      workerUrl.searchParams.set("v", version || "audit-v2");
      worker = new Worker(workerUrl);
      worker.onmessage = (e) => {
        const job = jobs.get(e.data.id);
        if (!job) return;
        jobs.delete(e.data.id);
        e.data.error
          ? job.reject(Error(e.data.error))
          : job.resolve(e.data.result);
      };
      worker.onerror = () => {
        for (const job of jobs.values())
          job.reject(
            Error(
              "O cálculo foi interrompido. Reduza a área ou verifique os dados.",
            ),
          );
        jobs.clear();
        worker.terminate();
        worker = null;
      };
    }
    return new Promise((resolve, reject) => {
      const id = ++request;
      jobs.set(id, { resolve, reject });
      worker.postMessage({ id, type, data, options: opts });
    });
  }
  function validFields() {
    const invalid = [...document.querySelectorAll("input, select")].find(
      (input) => !input.disabled && !input.checkValidity(),
    );
    if (!invalid) return true;
    for (
      let parent = invalid.parentElement;
      parent;
      parent = parent.parentElement
    )
      if (parent.tagName === "DETAILS") parent.open = true;
    invalid.reportValidity();
    status(
      "Revise o campo inválido antes de calcular ou salvar o cenário.",
      true,
    );
    return false;
  }
  async function busy(button, fn) {
    button.disabled = true;
    try {
      await fn();
    } catch (err) {
      status(err.message, true);
      // no celular o aviso pode estar fora da tela: leva a pessoa até ele
      $("status").scrollIntoView({ behavior: "smooth", block: "center" });
    } finally {
      button.disabled = false;
    }
  }
  $("calculate").onclick = () =>
    busy($("calculate"), async () => {
      invalidate();
      if (!validFields()) return;
      const rev = state.revision,
        o = options();
      status("Construindo a rede, aplicando bloqueios e calculando destinos…");
      // cálculo longo não fica mudo: avisa que segue trabalhando e como encurtar
      const demora = setTimeout(
        () =>
          status(
            "Ainda calculando… Áreas com muitas ruas e edificações podem levar alguns minutos. Uma área menor calcula mais rápido.",
          ),
        45000,
      );
      let r;
      try {
        r = await compute("plan", state.layers, o);
      } finally {
        clearTimeout(demora);
      }
      if (rev !== state.revision) {
        status(
          "Configuração alterada durante o cálculo. Calcule novamente.",
          true,
        );
        return;
      }
      state.result = r;
      showResults(r);
      status(
        "Cenário calculado. Toque numa edificação no mapa para ver o caminho dela.",
      );
    });
  function showResults(r) {
    const s = r.summary,
      box = $("results");
    box.hidden = false;
    box.replaceChildren();
    const h = document.createElement("h2");
    h.textContent =
      "Resultado · " +
      ($("municipality").value || "Município não identificado");
    box.append(h);
    const n0 = (v) => Number(v).toLocaleString(LOC()),
      el = (tag, cls, text) => {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text != null) e.textContent = text;
        return e;
      },
      big = (num, text) => {
        const d = el("div", "big");
        d.append(el("b", "", n0(num)), el("span", "", text));
        return d;
      };
    // ponto sugerido ganha o nome da rua com nome mais perto (até 150 m); o número interno confunde
    const ruas = (state.layers.roads?.features || []).filter(
        (f) => f.properties?.name && f.geometry?.type === "LineString",
      ),
      ruaPerto = (p) => {
        let melhor = null,
          dm = 150;
        for (const f of ruas)
          for (const c of f.geometry.coordinates) {
            const d = E.distance(p, c);
            if (d < dm) {
              dm = d;
              melhor = f.properties.name;
            }
          }
        return melhor;
      },
      nomes = new Map(
        r.destinations.map((d) => [
          d,
          /^Ponto sugerido \d+$/.test(String(d.name))
            ? ruaPerto(d.p)
              ? "Perto de " + ruaPerto(d.p)
              : "Sugerido pelo cálculo"
            : d.name,
        ]),
      ),
      nomeCurto = (t) => {
        for (const [d, n] of nomes) if (d.name === t) return n;
        return String(t).replace(
          /^(Ponto sugerido) \d+$/,
          "Sugerido pelo cálculo",
        );
      };
    const minutos = $("minutes").value,
      pct = s.people ? Math.round((100 * s.served) / s.people) : 0;
    box.append(
      big(
        r.destinations.length,
        r.destinations.length === 1
          ? "ponto de encontro"
          : "pontos de encontro",
      ),
      big(
        s.served,
        `de ${n0(s.people)} pessoas chegam a um ponto em até ${minutos} min a pé`,
      ),
    );
    const barra = el("div", "barra");
    barra.setAttribute("role", "img");
    barra.setAttribute("aria-label", pct + "% das pessoas chegam no tempo");
    const fill = el("i");
    fill.style.width = pct + "%";
    barra.append(fill);
    box.append(
      barra,
      el(
        "p",
        "",
        `${n0(s.assigned)} de ${n0(s.required)} edificações atendidas.`,
      ),
    );
    if (s.unassigned)
      box.append(
        el(
          "p",
          "alerta",
          `${n0(s.unassigned)} ${s.unassigned === 1 ? "edificação não chega" : "edificações não chegam"} a nenhum ponto no tempo escolhido (em vermelho no mapa). Aumente o tempo, cadastre outro ponto ou preveja transporte.`,
        ),
      );
    if (s.crossing)
      box.append(
        el(
          "p",
          "notice",
          `${n0(s.crossing)} ${s.crossing === 1 ? "edificação tem" : "edificações têm"} a rota passando por dentro da mancha depois de estar fora dela, por exemplo numa ponte (em amarelo no mapa). Confira se essa passagem estará aberta durante a retirada.`,
        ),
      );
    if (avisoArea) box.append(el("p", "notice", avisoArea));
    if (!s.required)
      box.append(
        el(
          "p",
          "notice",
          `Nenhuma edificação da área fica na mancha nem a menos de ${$("margin").value} m dela: com o rio subindo ${$("autoLevel").value} m, ninguém aqui precisa sair. Para outra cheia, mude quanto o rio sobe e calcule de novo.`,
        ),
      );
    if (!r.destinations.length && s.required)
      box.append(
        el(
          "p",
          "alerta",
          `Nenhum lugar seguro dentro da área marcada: ela fica toda na mancha ou a menos de ${$("margin").value} m dela. Marque uma área maior, que inclua terreno mais alto, ou confira quanto o rio sobe.`,
        ),
      );
    if (s.required && s.required < 15)
      box.append(
        el(
          "p",
          "alerta",
          `Só ${n0(s.required)} ${s.required === 1 ? "edificação" : "edificações"} na área que precisa de ponto de encontro. Confira no mapa se marcou a parte certa da cidade (a que inunda, com casas) e se a mancha azul encosta nela.`,
        ),
      );
    if (r.removed)
      box.append(
        el(
          "p",
          "muted",
          `${n0(r.removed)} trechos de rua ficaram fora da rede (bloqueios ou inundação).`,
        ),
      );
    const note = document.createElement("p");
    note.className = "notice";
    note.textContent =
      (s.estimated
        ? `População estimada em ${n0(s.estimated)} edificações (sem cadastro). `
        : "") +
      (!r.destinations.length
        ? ""
        : (r.destinations.some((d) => d.capacity === null)
            ? "Há pontos sem capacidade informada: o resultado não garante que há espaço para todos. "
            : "As capacidades cadastradas foram respeitadas. ") +
          "A escolha dos pontos é aproximada; pode existir uma solução melhor.");
    if (note.textContent) box.append(note);
    if (r.destinations.length)
      box.append(
        el(
          "p",
          "muted",
          "Toque numa linha para ver o ponto no mapa; toque numa edificação para ver o caminho dela.",
        ),
      );
    const table = document.createElement("table");
    const head = document.createElement("tr");
    for (const t of ["Nº", "Ponto de encontro", "Pessoas", "Capacidade"]) {
      const th = document.createElement("th");
      th.textContent = t;
      head.append(th);
    }
    table.append(head);
    r.destinations.forEach((d, i) => {
      const tr = document.createElement("tr");
      tr.dataset.i = i;
      tr.tabIndex = 0;
      const tdn = document.createElement("td");
      tdn.append(el("span", "dest-ic sm", String(i + 1)));
      tr.append(tdn);
      for (const t of [
        nomeCurto(d.name),
        n0(d.used),
        d.capacity === null
          ? "Não informada"
          : `${d.used + d.occupancy}/${d.capacity}`,
      ]) {
        const td = document.createElement("td");
        td.textContent = t;
        tr.append(td);
      }
      table.append(tr);
      const mk = L.marker([d.p[1], d.p[0]], {
        title: "Ponto de encontro " + (i + 1),
        alt: "Ponto de encontro " + (i + 1),
        zIndexOffset: 500,
        icon: L.divIcon({
          className: "dest-ic",
          html: String(i + 1),
          iconSize: [26, 26],
        }),
      })
        .bindPopup(
          popupText(
            "Ponto " +
              (i + 1) +
              " · " +
              nomeCurto(d.name) +
              " · " +
              n0(d.used) +
              " pessoas · capacidade " +
              (d.capacity ?? "não informada"),
          ),
        )
        .addTo(resultLayer);
      const ir = () => {
        map.setView(mk.getLatLng(), Math.max(map.getZoom(), 16));
        mk.openPopup();
      };
      tr.onclick = ir;
      tr.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          ir();
        }
      };
    });
    if (r.destinations.length) box.append(table);
    for (const d of r.rejected) {
      const n = document.createElement("p");
      n.textContent = "Ponto não usado: " + d.name + " — " + d.reason;
      box.append(n);
    }
    const reasons = {};
    for (const b of r.buildings)
      if (b.required && b.destination == null)
        reasons[b.reason] = (reasons[b.reason] || 0) + 1;
    // um único motivo "sem destino no tempo" já está dito no resumo acima
    const soTempo =
      Object.keys(reasons).length === 1 &&
      reasons["Sem destino alcançável no tempo escolhido"];
    for (const [reason, n] of soTempo ? [] : Object.entries(reasons)) {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent =
        n0(n) + (n === 1 ? " edificação: " : " edificações: ") + reason;
      box.append(p);
    }
    r.buildings.forEach((b, i) => {
      if (!b.required) return;
      // casas menores e um pouco transparentes, para a mancha azul aparecer por baixo delas
      const l = L.circleMarker([b.p[1], b.p[0]], {
        radius: 3.5,
        weight: 1,
        color:
          b.destination == null
            ? "#b91c1c"
            : b.crossesFlood
              ? "#5c4300"
              : "#126b47",
        fillColor:
          b.crossesFlood && b.destination != null ? "#ffd60a" : undefined,
        fillOpacity: 0.6,
      }).addTo(resultLayer);
      l.on("click", () => {
        routeLayer.clearLayers();
        const pts = E.route(r, i);
        if (pts.length)
          L.polyline(
            pts.map((p) => [p[1], p[0]]),
            { color: "#6c2a98", weight: 5 },
          ).addTo(routeLayer);
        l.bindPopup(
          popupText(
            "Edificação " +
              b.id +
              " · " +
              b.people +
              " pessoas" +
              (b.estimated ? " (estimadas)" : "") +
              " · " +
              (b.destination == null
                ? b.reason
                : "Ponto " +
                  (b.destination + 1) +
                  " (" +
                  nomeCurto(r.destinations[b.destination].name) +
                  ") · " +
                  (b.seconds / 60).toFixed(1) +
                  " min" +
                  (b.crossesFlood ? " · a rota passa pela mancha" : "")),
          ),
        ).openPopup();
      });
    });
    $("csv").disabled = $("routes").disabled = false;
    // o que fazer com o resultado, sem abrir as opções avançadas
    const acoes = el("div", "acoes"),
      botao = (txt, fn) => {
        const b = el("button", "", txt);
        b.type = "button";
        b.onclick = fn;
        acoes.append(b);
        return b;
      };
    botao("Baixar planilha por edificação", () => $("csv").click());
    botao("Baixar rotas (GeoJSON)", () => $("routes").click());
    const link = linkDoCenario();
    if (link) {
      const campo = el("input", "link");
      campo.readOnly = true;
      campo.value = link;
      campo.setAttribute("aria-label", "Link deste cenário");
      const copia = botao("Copiar link deste cenário", async () => {
        campo.hidden = false;
        campo.select();
        try {
          await navigator.clipboard.writeText(link);
          copia.textContent = I.tr("Link copiado", LANG);
        } catch (e) {
          copia.textContent = I.tr("Copie o link abaixo", LANG);
        }
      });
      campo.hidden = true;
      acoes.append(campo);
    }
    box.append(
      el(
        "p",
        "muted",
        "O link refaz o cálculo com o mesmo lugar, a mesma área, o mesmo nível do rio e o mesmo tempo, com os dados do mapa do dia em que for aberto.",
      ),
      acoes,
    );
    I.aplica([box], LANG);
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  $("save").onclick = () => {
    if (!validFields()) return;
    download(
      JSON.stringify(
        {
          schema: "previne-municipal-v1",
          savedAt: new Date().toISOString(),
          options: options(),
          layers: state.layers,
          sources: state.sources,
          terrainReference: state.terrain
            ? {
                source: state.terrain.source,
                bbox: state.terrain.bbox,
                note: "Reimporte o GeoTIFF para gerar outro HAND.",
              }
            : null,
        },
        null,
        2,
      ),
      "predefinicoes_municipais.json",
    );
  };
  $("load").onchange = (e) =>
    busy($("calculate"), async () => {
      try {
        if (!e.target.files[0]) return;
        const data = await fileJSON(e.target.files[0]);
        if (
          data.schema !== "previne-municipal-v1" ||
          !data.layers ||
          !data.options
        )
          throw Error("Arquivo de predefinições incompatível.");
        const layers = {};
        for (const [k, v] of Object.entries(data.layers)) {
          if (!Object.hasOwn(labels, k))
            throw Error("Camada desconhecida: " + k);
          layers[k] = E.validate(v, k, {
            allowEmpty: !["roads", "buildings"].includes(k),
          });
        }
        for (const id of optionIds)
          if (data.options[id] != null) {
            if ($(id).type === "checkbox") $(id).checked = !!data.options[id];
            else $(id).value = data.options[id];
          }
        state.layers = layers;
        state.sources = data.sources || {};
        state.terrain = null;
        updateTerrain();
        invalidate();
        render();
        fit();
        status(
          "Predefinições reabertas. Recalcule o cenário; reimporte o terreno se precisar gerar outro HAND.",
        );
      } finally {
        e.target.value = "";
      }
    });
  $("reset").onclick = () => {
    if (
      Object.keys(state.layers).length &&
      !confirm(
        "Limpar o cenário atual? Baixe as predefinições antes se quiser preservá-las.",
      )
    )
      return;
    state.layers = {};
    state.sources = {};
    state.terrain = null;
    restoreDefaults();
    invalidate();
    render();
    updateTerrain();
    map.setView([-14, -53], 4);
    status("Novo cenário municipal.");
  };
  $("downloadArea").onclick = () =>
    state.layers.aoi
      ? download(
          JSON.stringify(state.layers.aoi),
          "area_interesse.geojson",
          "application/geo+json",
        )
      : status("Desenhe ou importe a área de interesse.", true);
  function requireResult() {
    if (!state.result)
      throw Error("Calcule o cenário atual antes de exportar.");
    return state.result;
  }
  $("csv").onclick = () => {
    try {
      const r = requireResult(),
        rows = [
          [
            "edificacao",
            "pessoas",
            "populacao_estimada",
            "destino",
            "tempo_min",
            "situacao",
            "capacidade_destino",
            "municipio",
            "mancha",
            "referencia",
            "vias_inundadas_excluidas",
          ],
        ];
      for (const b of r.buildings) {
        const d = r.destinations[b.destination];
        rows.push([
          b.id,
          b.people,
          b.estimated ? "sim" : "nao",
          d?.name || "",
          b.seconds == null ? "" : (b.seconds / 60).toFixed(2),
          b.required ? (d ? "atendida" : b.reason) : "fora_do_escopo",
          d?.capacity ?? "nao_informada",
          $("municipality").value,
          $("floodType").value,
          $("floodEvent").value,
          $("excludeFlood").checked,
        ]);
      }
      const csv =
        "\ufeff" +
        rows
          .map((r) =>
            r
              .map(
                (v) =>
                  '"' +
                  String(v)
                    .replace(/^[=+@-]/, "'$&")
                    .replace(/"/g, '""') +
                  '"',
              )
              .join(";"),
          )
          .join("\r\n");
      download(csv, "relatorio_municipal.csv", "text/csv;charset=utf-8");
    } catch (e) {
      status(e.message, true);
    }
  };
  $("routes").onclick = () => {
    try {
      const r = requireResult(),
        features = [];
      r.buildings.forEach((b, i) => {
        const coordinates = E.route(r, i);
        if (coordinates.length)
          features.push({
            type: "Feature",
            properties: {
              edificacao: b.id,
              pessoas: b.people,
              estimada: b.estimated,
              destino: r.destinations[b.destination].name,
              tempo_min: b.seconds / 60,
              passa_pela_mancha: !!b.crossesFlood,
            },
            geometry: { type: "LineString", coordinates },
          });
      });
      download(
        JSON.stringify({
          type: "FeatureCollection",
          metadata: { options: options(), sources: state.sources },
          features,
        }),
        "rotas_municipais.geojson",
        "application/geo+json",
      );
    } catch (e) {
      status(e.message, true);
    }
  };
  $("example").onclick = () =>
    busy($("example"), async () => {
      if (
        Object.keys(state.layers).length &&
        !confirm("Substituir o cenário atual pelo exemplo?")
      )
        return;
      const response = await fetch(
        "assets/data/rota_fuga/santa_tereza_pontos_encontro_hand.json",
      );
      if (!response.ok) throw Error("Exemplo indisponível.");
      restoreDefaults();
      const d = await response.json(),
        idx = Object.fromEntries(d.casas_campos.map((k, i) => [k, i]));
      state.layers = {
        roads: fc(
          d.arestas.map(([a, b]) => ({
            type: "Feature",
            properties: { highway: "sem_classificacao" },
            geometry: {
              type: "LineString",
              coordinates: [d.nos[a], d.nos[b]].map((p) => [p[1], p[0]]),
            },
          })),
        ),
        buildings: fc(
          d.casas.map((b, i) => ({
            type: "Feature",
            id: i + 1,
            properties: {},
            geometry: { type: "Point", coordinates: [b[idx.lon], b[idx.lat]] },
          })),
        ),
        flood: fc([
          {
            type: "Feature",
            properties: {},
            geometry:
              d.mancha.type === "Feature" ? d.mancha.geometry : d.mancha,
          },
        ]),
        destinations: fc(
          d.plano.oficiais.map((p) => ({
            type: "Feature",
            properties: {
              nome: p.nome,
              tipo: "ponto_de_encontro",
              capacidade: null,
            },
            geometry: { type: "Point", coordinates: [p.lon, p.lat] },
          })),
        ),
      };
      state.sources = {
        roads: "OpenStreetMap · exemplo do projeto",
        buildings:
          "Base do estudo de Santa Tereza; revisar cadastro e população",
        flood: d.fonte_mancha,
        destinations: "Plano de Contingência · verificar cadastro vigente",
      };
      $("municipality").value = "Santa Tereza · exemplo provisório";
      $("floodType").value = "modelada";
      $("floodEvent").value =
        "set/2023 · HAND do projeto; contornos em revisão no Arroio Marrecão";
      $("margin").value = 100;
      $("mode").value = "misto";
      state.terrain = null;
      updateTerrain();
      invalidate();
      render();
      fit();
      status(
        "Exemplo carregado: Santa Tereza, com uma mancha de inundação simulada (não é a cheia observada). Agora toque em Calcular.",
      );
    });
  function areaBox() {
    if (!state.layers.aoi?.features.length)
      throw Error(
        "Defina a área de interesse primeiro: procure o lugar na etapa 1 e toque em “Usar esta parte do mapa”.",
      );
    const b = L.geoJSON(state.layers.aoi).getBounds();
    return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
  }
  // área de interesse ou, sem ela (bases importadas, exemplo), a extensão das ruas
  function caixaTrabalho() {
    if (state.layers.aoi?.features.length) return areaBox();
    if (!state.layers.roads?.features.length) return areaBox();
    const b = L.geoJSON(state.layers.roads).getBounds();
    return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
  }
  function updateTerrain() {
    $("terrainInfo").textContent = state.terrain
      ? `${state.terrain.source}${state.terrain.fileBytes ? " · arquivo " + (state.terrain.fileBytes / 1048576).toLocaleString(LOC(), { maximumFractionDigits: 1 }) + " MB" : ""} · ${state.terrain.width} × ${state.terrain.height} pontos sobre a área (com folga em volta).`
      : "Nenhum terreno carregado.";
  }
  async function readTerrain(tiff, bbox) {
    const im = await tiff.getImage(),
      keys = im.getGeoKeys();
    if (keys.GeographicTypeGeoKey !== 4326 || keys.ProjectedCSTypeGeoKey)
      throw Error(
        "Use um GeoTIFF geográfico EPSG:4326. Reprojete o raster antes de importar.",
      );
    const ib = im.getBoundingBox(),
      b = bbox || ib,
      inter = [
        Math.max(b[0], ib[0]),
        Math.max(b[1], ib[1]),
        Math.min(b[2], ib[2]),
        Math.min(b[3], ib[3]),
      ];
    if (inter[0] >= inter[2] || inter[1] >= inter[3])
      throw Error("Terreno não cobre a área de interesse.");
    const iw = im.getWidth(),
      ih = im.getHeight(),
      window = [
        Math.max(0, Math.floor(((inter[0] - ib[0]) / (ib[2] - ib[0])) * iw)),
        Math.max(0, Math.floor(((ib[3] - inter[3]) / (ib[3] - ib[1])) * ih)),
        Math.min(iw, Math.ceil(((inter[2] - ib[0]) / (ib[2] - ib[0])) * iw)),
        Math.min(ih, Math.ceil(((ib[3] - inter[1]) / (ib[3] - ib[1])) * ih)),
      ];
    const scale = Math.min(
        1,
        320 / Math.max(window[2] - window[0], window[3] - window[1]),
      ),
      width = Math.max(3, Math.round((window[2] - window[0]) * scale)),
      height = Math.max(3, Math.round((window[3] - window[1]) * scale)),
      nodata = im.getGDALNoData();
    const actual = [
      ib[0] + (window[0] / iw) * (ib[2] - ib[0]),
      ib[3] - (window[3] / ih) * (ib[3] - ib[1]),
      ib[0] + (window[2] / iw) * (ib[2] - ib[0]),
      ib[3] - (window[1] / ih) * (ib[3] - ib[1]),
    ];
    // GeoTIFF chooses an overview when available; the source reads only needed file slices.
    const rasters = await tiff.readRasters({
      bbox: actual,
      width,
      height,
      samples: [0],
    });
    return {
      originalWidth: iw,
      originalHeight: ih,
      values: Array.from(rasters[0], (v) => (v === nodata ? NaN : v)),
      width,
      height,
      bbox: actual,
    };
  }
  $("terrainFile").onchange = (e) =>
    busy($("generateHand"), async () => {
      try {
        const file = e.target.files[0];
        if (!file) return;
        if (!window.GeoTIFF) throw Error("Leitor GeoTIFF indisponível.");
        $("terrainFile").disabled = true;
        const revision = state.revision;
        status("Lendo o GeoTIFF por partes e preparando o recorte…");
        const tiff = await GeoTIFF.fromBlob(file);
        let t;
        try {
          t = await readTerrain(
            tiff,
            state.layers.aoi?.features.length ? areaBox() : null,
          );
        } finally {
          await tiff.close();
        }
        if (revision !== state.revision)
          throw Error(
            "Cenário alterado durante a leitura do terreno. Importe novamente para usar o recorte atual.",
          );
        state.terrain = { ...t, source: file.name, fileBytes: file.size };
        updateTerrain();
        invalidate();
        status("Terreno carregado. Revise a área e os parâmetros HAND.");
      } finally {
        $("terrainFile").disabled = false;
        e.target.value = "";
      }
    });
  // Copernicus só responde pelo servidor local (scripts/servir_cenario.py): o site não consegue ler direto
  const copernicusLocal = async () => {
    const bbox = areaBox(),
      [w, s, e, n] = bbox;
    if (e - w > 2 || n - s > 2)
      throw Error("Selecione uma área de até 2° por 2°.");
    const tiles = [];
    for (let lat = Math.floor(s); lat < Math.ceil(n); lat++)
      for (let lon = Math.floor(w); lon < Math.ceil(e); lon++) {
        const name = `Copernicus_DSM_COG_10_${lat < 0 ? "S" : "N"}${String(Math.abs(lat)).padStart(2, "0")}_00_${lon < 0 ? "W" : "E"}${String(Math.abs(lon)).padStart(3, "0")}_00_DEM`;
        tiles.push(
          `https://copernicus-dem-30m.s3.amazonaws.com/${name}/${name}.tif`,
        );
      }
    if (tiles.length > 4)
      throw Error("A área cruza mais de quatro tiles. Reduza o recorte.");
    status("Obtendo recorte público Copernicus GLO-30…");
    const parts = [];
    for (const url of tiles) {
      const name = url.split("/").at(-1).replace(".tif", "");
      try {
        parts.push(
          await readTerrain(
            await GeoTIFF.fromUrl(
              "/api/copernicus?tile=" + encodeURIComponent(name),
            ),
            bbox,
          ),
        );
      } catch (proxyError) {
        try {
          parts.push(await readTerrain(await GeoTIFF.fromUrl(url), bbox));
        } catch (directError) {
          const box = $("terrainInfo");
          box.replaceChildren(
            document.createTextNode(
              "Leitura online indisponível nesta hospedagem. Baixe os tiles abaixo e importe o GeoTIFF; o recorte pela área será aplicado automaticamente. ",
            ),
          );
          for (const tile of tiles) {
            const a = document.createElement("a");
            a.href = tile;
            a.textContent = "Baixar " + tile.split("/").at(-1);
            a.target = "_blank";
            a.rel = "noopener";
            box.append(document.createElement("br"), a);
          }
          throw Error(
            "Não foi possível acessar o terreno online. Use os links na seção de terreno para baixar e importar, ou o servidor municipal incluído.",
          );
        }
      }
    }
    const width = 320,
      height = Math.max(
        3,
        Math.min(320, Math.round((320 * (n - s)) / (e - w))),
      ),
      values = [];
    for (let y = 0; y < height; y++)
      for (let x = 0; x < width; x++) {
        const lon = w + ((x + 0.5) / width) * (e - w),
          lat = n - ((y + 0.5) / height) * (n - s),
          p = parts.find(
            (p) =>
              lon >= p.bbox[0] &&
              lon <= p.bbox[2] &&
              lat >= p.bbox[1] &&
              lat <= p.bbox[3],
          );
        if (!p) {
          values.push(NaN);
          continue;
        }
        const xx = Math.min(
            p.width - 1,
            Math.floor(((lon - p.bbox[0]) / (p.bbox[2] - p.bbox[0])) * p.width),
          ),
          yy = Math.min(
            p.height - 1,
            Math.floor(
              ((p.bbox[3] - lat) / (p.bbox[3] - p.bbox[1])) * p.height,
            ),
          );
        values.push(p.values[yy * p.width + xx]);
      }
    state.terrain = {
      values,
      width,
      height,
      bbox,
      source: "Copernicus GLO-30 (DSM) · " + tiles.join(" "),
    };
    updateTerrain();
    invalidate();
    status(
      "Recorte Copernicus obtido. Valide a resolução e a drenagem antes de gerar HAND.",
    );
  };
  // relevo carregado direto na página (sem baixar nem importar arquivo), para qualquer lugar
  function quadro(z, x, y) {
    return new Promise((ok, falha) => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        const c = document.createElement("canvas");
        c.width = c.height = 256;
        const g = c.getContext("2d", { willReadFrequently: true });
        g.drawImage(img, 0, 0);
        ok(g.getImageData(0, 0, 256, 256).data);
      };
      img.onerror = () =>
        falha(Error("quadro de relevo " + z + "/" + x + "/" + y));
      img.src = `${O.RELEVO_URL}${z}/${x}/${y}.png`;
    });
  }
  async function relevoAutomatico(area) {
    const bbox = O.folga(area),
      [w, s, e, n] = bbox,
      q = O.quadrosRelevo(bbox),
      quadros = new Map(),
      pedidos = [];
    status("Buscando o relevo da área…");
    for (let y = q.y0; y <= q.y1; y++)
      for (let x = q.x0; x <= q.x1; x++)
        pedidos.push(
          quadro(q.z, x, y).then((d) => quadros.set(x + "/" + y, d)),
        );
    try {
      await Promise.all(pedidos);
    } catch (err) {
      throw Error(
        "Não foi possível buscar o relevo agora. Verifique a internet e tente de novo, ou importe um GeoTIFF na etapa 1.",
      );
    }
    const width = 320,
      height = Math.max(
        3,
        Math.min(320, Math.round((320 * (n - s)) / (e - w))),
      ),
      values = new Array(width * height);
    for (let y = 0; y < height; y++) {
      const fy = O.ty(n - ((y + 0.5) / height) * (n - s), q.z),
        qy = Math.min(q.y1, Math.floor(fy)),
        py = Math.min(255, Math.floor((fy - qy) * 256));
      for (let x = 0; x < width; x++) {
        const fx = O.tx(w + ((x + 0.5) / width) * (e - w), q.z),
          qx = Math.min(q.x1, Math.floor(fx)),
          px = Math.min(255, Math.floor((fx - qx) * 256)),
          d = quadros.get(qx + "/" + qy),
          k = (py * 256 + px) * 4;
        values[y * width + x] = O.alturaTerrarium(d[k], d[k + 1], d[k + 2]);
      }
    }
    state.terrain = { values, width, height, bbox, source: O.RELEVO_FONTE };
    updateTerrain();
    invalidate();
  }
  // rios mapeados na caixa do relevo; null se o OpenStreetMap não responder (o HAND segue só com o relevo)
  async function riosDoMapa(t) {
    const g = state.rios,
      [w, s, e, n] = t.bbox,
      d = 1e-9;
    let osm = null;
    // já vieram com as ruas, para a mesma caixa
    if (
      g &&
      g.caixa[0] <= w + d &&
      g.caixa[1] <= s + d &&
      g.caixa[2] >= e - d &&
      g.caixa[3] >= n - d
    )
      osm = g;
    else {
      status("Buscando os rios mapeados da área…");
      // os rios são um pedido leve: se nenhum servidor responder em 20 s, a mancha segue só com o relevo
      osm = await overpass(O.consultaRios(t.bbox), 20, 20);
      // reserva: o servidor oficial, se a caixa do relevo couber em poucos ladrilhos
      if (!osm && O.ladrilhos(t.bbox).length <= 16) {
        status("Buscando os rios no servidor oficial do OpenStreetMap…");
        osm = await mapaOficial(t.bbox, (f, n) =>
          status(
            `Buscando os rios no servidor oficial do OpenStreetMap: parte ${f} de ${n}…`,
          ),
        ).catch(() => null);
        if (osm) osm = { elements: O.converte(osm).rios };
      }
      // guarda: gerar de novo com outro nível não pede os rios outra vez
      if (osm) state.rios = { caixa: t.bbox, elements: osm.elements || [] };
    }
    if (osm) {
      const r = O.mascaraRios(osm, t.bbox, t.width, t.height);
      if (r.celulas) return r;
    }
    return null;
  }
  $("copernicus").onclick = () =>
    busy($("copernicus"), async () => {
      const area = areaBox();
      try {
        await relevoAutomatico(area);
      } catch (err) {
        // sem a fonte direta: tenta o servidor local do Copernicus, se houver
        try {
          await copernicusLocal();
          return;
        } catch (e2) {
          throw err;
        }
      }
      status(
        "Relevo carregado. Na etapa 5 dá para gerar a mancha de inundação pelo terreno.",
      );
    });
  $("downloadTerrain").onclick = () => {
    try {
      const t = state.terrain;
      if (!t) throw Error("Carregue um terreno primeiro.");
      const [w, s, e, n] = t.bbox;
      const data = CenarioTerreno.writeGeoTIFF(t);
      download(
        new Blob([data], { type: "image/tiff" }),
        "terreno_recortado.tif",
      );
    } catch (e) {
      status(e.message, true);
    }
  };
  $("generateHand").onclick = () =>
    busy($("generateHand"), async () => {
      // sem relevo (ou relevo de outra área): busca sozinho, sem baixar nem importar arquivo
      const cobre = (t) => {
        if (!t) return false;
        const a = caixaTrabalho();
        return (
          a[0] >= t.bbox[0] &&
          a[1] >= t.bbox[1] &&
          a[2] <= t.bbox[2] &&
          a[3] <= t.bbox[3]
        );
      };
      if (!cobre(state.terrain)) await relevoAutomatico(caixaTrabalho());
      const t = state.terrain;
      if (!cobre(t))
        throw Error(
          "O terreno não cobre a área de interesse atual. Obtenha outro recorte.",
        );
      const rios = await riosDoMapa(t);
      const rev = state.revision,
        [w, s, e, n] = t.bbox,
        cellArea =
          ((E.distance([w, s], [e, s]) / t.width) *
            E.distance([w, s], [w, n])) /
          t.height;
      status("Condicionando terreno e calculando HAND experimental…");
      // Padrão de 10 km²: na validação com a cheia de 2024 (validacao/mancha), acertou mais que 1 km², que
      // inunda os fundos de vale de arroios pequenos. Sem canal desse tamanho na área, tenta 1 km² e depois menos.
      const hand = (limiteKm2) =>
        compute("hand", [
          t.values,
          t.width,
          t.height,
          cellArea,
          limiteKm2 * 1e6,
          Number($("handLevel").value),
          t.bbox,
          rios ? rios.mascara : null,
        ]);
      let limite = Number($("drainArea").value),
        layer;
      for (;;) {
        try {
          layer = await hand(limite);
          break;
        } catch (err) {
          if (!/Nenhuma drenagem/.test(err.message) || limite <= 0.1) throw err;
          limite = limite > 1 ? 1 : 0.1;
        }
      }
      if (rev !== state.revision)
        throw Error("Configuração alterada durante a geração. Gere novamente.");
      if (!layer.features.length)
        throw Error("O cenário não gerou área inundada. Revise os parâmetros.");
      state.layers.flood = layer;
      state.sources.flood =
        t.source +
        (rios ? " · rios do OpenStreetMap" : "") +
        " · HAND D8 experimental · área contribuinte " +
        limite +
        " km² · nível " +
        $("handLevel").value +
        " m";
      $("floodType").value = "hand";
      if ($("legInund"))
        $("legInund").textContent = I.tr(
          `inundação simulada (rio +${$("handLevel").value} m)`,
          LANG,
        );
      $("floodEvent").value =
        "HAND experimental; não calibrado com régua ou evento histórico";
      invalidate();
      render();
      status(
        "Mancha gerada pelo terreno" +
          (rios
            ? ", a partir dos rios mapeados."
            : ". Não foi possível ler os rios do OpenStreetMap: a drenagem saiu só do relevo dentro da área e pode falhar para rio que vem de fora.") +
          " Confira no mapa e ajuste o nível acima do rio antes de calcular.",
      );
    });
  // tudo de uma vez: ruas e edificações, relevo e rios, mancha e cálculo
  async function etapaAuto(id) {
    await $(id).onclick();
    if ($("status").classList.contains("error"))
      throw Error($("status").textContent);
  }
  $("autoLevel").addEventListener("input", () => {
    $("handLevel").value = $("autoLevel").value;
  });
  $("handLevel").addEventListener("input", () => {
    $("autoLevel").value = $("handLevel").value;
  });
  $("autoAll").onclick = () =>
    busy($("autoAll"), async () => {
      // sem área marcada (e sem bases importadas): usa a parte do mapa que está na tela
      if (!state.layers.aoi?.features.length && !state.layers.roads) {
        if (map.getZoom() < 11) {
          $("placeQuery").focus();
          throw Error(
            "Primeiro escreva o nome da cidade no passo 1 e toque em Procurar.",
          );
        }
        $("viewArea").click();
        if ($("status").classList.contains("error")) return;
      }
      if (!state.layers.roads) areaBox();
      if (!$("autoLevel").checkValidity() || $("autoLevel").value === "")
        throw Error("Informe quanto o rio sobe, em metros.");
      $("handLevel").value = $("autoLevel").value;
      // bases que a pessoa já importou ficam como estão
      if (!state.layers.roads || !state.layers.buildings)
        await etapaAuto("osmDownload");
      if (!state.layers.flood || $("floodType").value === "hand")
        await etapaAuto("generateHand");
      await etapaAuto("calculate");
    });
  // textos fixos do fluxo principal no idioma escolhido
  const traduziveis = () => [
    document.querySelector("header"),
    document.querySelector(".guia"),
    document.querySelector("#avancado > summary"),
    document.querySelector(".map-note"),
    $("viewAreaMap"),
    $("results"),
  ];
  function trocaIdioma(lang) {
    LANG = lang;
    try {
      localStorage.setItem("previne-idioma", lang);
    } catch (e) {}
    I.aplica(traduziveis(), lang);
    if (statusPt != null) $("status").textContent = I.tr(statusPt, lang);
    document
      .querySelectorAll("[data-lang]")
      .forEach((b) =>
        b.setAttribute("aria-pressed", String(b.dataset.lang === lang)),
      );
  }
  document
    .querySelectorAll("[data-lang]")
    .forEach((b) => (b.onclick = () => trocaIdioma(b.dataset.lang)));
  statusPt = $("status").textContent.replace(/\s+/g, " ").trim();
  trocaIdioma(LANG);
  $("csv").disabled = $("routes").disabled = true;
  render();
  // cenário aberto por link: marca a área, preenche os campos e calcula
  try {
    const q = new URLSearchParams(location.search),
      area = (q.get("area") || "").split(",").map(Number);
    if (area.length === 4 && area.every(Number.isFinite)) {
      const [w, s, e, n] = area;
      if (
        w < e &&
        s < n &&
        w >= -180 &&
        e <= 180 &&
        O.areaKm2(area) <= O.AREA_MAX_KM2
      ) {
        if (q.get("lugar"))
          $("municipality").value = q.get("lugar").slice(0, 140);
        if (q.get("rio")) $("autoLevel").value = q.get("rio");
        if (q.get("tempo")) $("minutes").value = q.get("tempo");
        $("placeQuery").value = q.get("lugar") || "";
        marcaArea(area);
        render();
        fit();
        passoFeito(1);
        passoFeito(2);
        status("Cenário aberto pelo link. Calculando…");
        setTimeout(() => $("autoAll").click(), 300);
      } else
        status(
          "O link tem uma área inválida ou grande demais. Comece pelo passo 1.",
          true,
        );
    }
  } catch (err) {
    console.warn(err);
  }
})();
