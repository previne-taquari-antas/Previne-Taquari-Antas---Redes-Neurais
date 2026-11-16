"use strict";
(() => {
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
  const status = (text, error = false) => {
    $("status").textContent = text;
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
    state.result = null;
    if (routeLayer) routeLayer.clearLayers();
    if (resultLayer) resultLayer.clearLayers();
    $("results").hidden = false;
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
          weight: kind === "roads" ? 2 : 2.5,
          fillOpacity: kind === "flood" ? 0.3 : 0.08,
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
  async function pega(url, opts, segundos = 150) {
    const c = new AbortController(),
      t = setTimeout(() => c.abort(), segundos * 1000);
    try {
      const r = await fetch(url, { ...opts, signal: c.signal });
      if (!r.ok) throw Error("HTTP " + r.status);
      return await r.json();
    } finally {
      clearTimeout(t);
    }
  }
  const espera = (ms) => new Promise((r) => setTimeout(r, ms));
  // tenta cada servidor do Overpass; se estiver ocupado (429/502/504), espera e tenta de novo, mais uma vez
  async function overpass(consulta, segundos = 120) {
    const opts = {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "data=" + encodeURIComponent(consulta),
    };
    // o primeiro servidor é o principal: quando está ocupado, vale insistir nele antes de ir aos outros,
    // que costumam demorar mais
    for (const [k, url] of O.SERVIDORES.entries()) {
      const vezes = k ? 1 : 3;
      for (let vez = 0; vez < vezes; vez++) {
        if (k && !vez)
          status(
            `O servidor do OpenStreetMap não respondeu. Tentando outro (${k + 1} de ${O.SERVIDORES.length})…`,
          );
        try {
          return await pega(url, opts, k ? Math.min(segundos, 60) : segundos);
        } catch (err) {
          console.warn(url, err);
          // recusa por excesso de pedidos chega ao navegador como falha de rede, sem o código HTTP
          if (
            vez + 1 >= vezes ||
            err.name === "AbortError" ||
            /HTTP 4(?!29)\d\d/.test(err.message)
          )
            break;
          status(
            "O servidor do OpenStreetMap está ocupado. Tentando de novo em alguns segundos…",
          );
          await espera(6000 + 4000 * vez);
        }
      }
    }
    return null;
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
      if (!$("municipality").value.trim())
        $("municipality").value = l.nome.split(",")[0].slice(0, 140);
      invalidate();
      render();
      fit();
      const km2 = O.areaKm2(areaBox()),
        grande = km2 > O.AREA_MAX_KM2;
      status(
        grande
          ? `O limite tem cerca de ${Math.round(km2).toLocaleString("pt-BR")} km², grande para baixar as ruas e edificações. Aproxime o mapa da parte que inunda e toque em “Usar a área visível no mapa” (até ${O.AREA_MAX_KM2} km²).`
          : "Área de interesse definida. Agora baixe as ruas e edificações na etapa 2.",
        grande,
      );
    } catch (err) {
      status(err.message, true);
    }
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
      ir.onclick = () => vaiPara(l.caixa);
      li.append(nome, ir);
      if (l.limite) {
        const usar = document.createElement("button");
        usar.textContent = "Usar o limite como área";
        usar.onclick = () => usaLimite(l);
        li.append(usar);
      }
      ul.append(li);
    }
    if (lista.length) vaiPara(lista[0].caixa);
  }
  // a área que está na tela vira a área de interesse (mais fácil que desenhar, ainda mais no celular)
  $("viewArea").onclick = () => {
    try {
      const b = map.getBounds().pad(-0.04),
        [w, s, e, n] = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()],
        km2 = O.areaKm2([w, s, e, n]);
      if (km2 > O.AREA_MAX_KM2)
        throw Error(
          (km2 > 20000
            ? "A área na tela é grande demais."
            : `A área na tela tem cerca de ${Math.round(km2).toLocaleString("pt-BR")} km².`) +
            ` Aproxime o mapa até a parte que inunda (até ${O.AREA_MAX_KM2} km²) e toque de novo.`,
        );
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
      invalidate();
      render();
      status(
        `Área de interesse definida (cerca de ${km2.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} km²). Agora baixe as ruas e edificações na etapa 2.`,
      );
    } catch (err) {
      status(err.message, true);
    }
  };
  $("placeSearch").onclick = () =>
    busy($("placeSearch"), async () => {
      const q = $("placeQuery").value.trim();
      if (q.length < 3) throw Error("Escreva o nome do lugar.");
      status("Procurando “" + q + "”…");
      let lista;
      try {
        lista = O.lugares(await pega(O.urlLugar(q), {}, 30));
      } catch (err) {
        throw Error(
          "A busca de lugares não respondeu. Tente de novo em instantes ou aproxime o mapa e desenhe a área.",
        );
      }
      mostraLugares(lista);
      status(
        lista.length
          ? "Lugar encontrado. Aproxime o mapa da parte que inunda e toque em “Usar a área visível no mapa”."
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
          `A área de interesse tem cerca de ${Math.round(km2).toLocaleString("pt-BR")} km². Para baixar do OpenStreetMap, use até ${O.AREA_MAX_KM2} km²: desenhe uma área menor em volta da parte que inunda.`,
        );
      status(
        "Baixando ruas e edificações do OpenStreetMap… pode levar um minuto.",
      );
      // os rios da área (com folga) vêm junto: servem para gerar a mancha pelo terreno
      const caixaRios = O.folga(bbox);
      let osm = await overpass(O.consulta(bbox, caixaRios), 150);
      if (!osm) {
        // reserva: o próprio servidor do OpenStreetMap, que entrega áreas pequenas
        status(
          "Tentando direto no servidor do OpenStreetMap (funciona para áreas pequenas)…",
        );
        try {
          osm = O.deMapa(await pega(O.urlMapa(bbox), {}, 120));
        } catch (err) {
          console.warn("api.openstreetmap.org", err);
          if (/HTTP (400|509)/.test(err.message))
            throw Error(
              "Os servidores de consulta do OpenStreetMap não responderam e a área é grande para o servidor de reserva. Use uma área menor ou tente de novo em alguns minutos.",
            );
        }
      }
      if (!osm)
        throw Error(
          "O OpenStreetMap não respondeu agora. Tente de novo em alguns minutos ou importe os arquivos do município.",
        );
      const r = O.converte(osm);
      state.rios = { caixa: caixaRios, elements: r.rios };
      if (!r.roads.features.length)
        throw Error(
          "O OpenStreetMap não tem ruas mapeadas nessa área. Confira a área de interesse ou importe os arquivos do município.",
        );
      const nt = O.trechos(r.roads);
      if (nt > 15000)
        throw Error(
          `Essa área tem ruas demais para o cálculo (${nt.toLocaleString("pt-BR")} trechos; o limite é 15 mil). Aproxime o mapa da parte que inunda, toque em “Usar a área visível no mapa” e baixe de novo.`,
        );
      const fonte =
        "OpenStreetMap (ODbL)" +
        (r.data ? ", dados de " + r.data.slice(0, 10) : "");
      state.layers.roads = E.validate(r.roads, "roads");
      state.sources.roads = fonte;
      if (r.buildings.features.length) {
        state.layers.buildings = E.validate(r.buildings, "buildings");
        state.sources.buildings = fonte;
      }
      invalidate();
      render();
      fit();
      const n0 = (v) => v.toLocaleString("pt-BR");
      status(
        `Baixado do OpenStreetMap: ${n0(r.roads.features.length)} ruas e ${n0(r.buildings.features.length)} edificações.` +
          (r.buildings.features.length
            ? " Falta a mancha de inundação (etapa 5)."
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
      const r = await compute("plan", state.layers, o);
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
        "Cenário calculado. Clique nas edificações para examinar as rotas.",
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
    const n0 = (v) => Number(v).toLocaleString("pt-BR"),
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
    // o número interno do ponto sugerido confunde ao lado do nº da lista
    const nomeCurto = (t) =>
      String(t).replace(/^(Ponto sugerido) \d+$/, "Sugerido pelo cálculo");
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
      (r.destinations.some((d) => d.capacity === null)
        ? "Há pontos sem capacidade informada: o resultado não garante que há espaço para todos. "
        : "As capacidades cadastradas foram respeitadas. ") +
      "A escolha dos pontos é aproximada; pode existir uma solução melhor.";
    box.append(note);
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
    box.append(table);
    for (const d of r.rejected) {
      const n = document.createElement("p");
      n.textContent = "Ponto não usado: " + d.name + " — " + d.reason;
      box.append(n);
    }
    const reasons = {};
    for (const b of r.buildings)
      if (b.required && b.destination == null)
        reasons[b.reason] = (reasons[b.reason] || 0) + 1;
    for (const [reason, n] of Object.entries(reasons)) {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent =
        n + (n === 1 ? " edificação: " : " edificações: ") + reason;
      box.append(p);
    }
    r.buildings.forEach((b, i) => {
      if (!b.required) return;
      const l = L.circleMarker([b.p[1], b.p[0]], {
        radius: 5,
        color: b.destination == null ? "#b91c1c" : "#126b47",
        fillOpacity: 0.9,
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
                  " min"),
          ),
        ).openPopup();
      });
    });
    $("csv").disabled = $("routes").disabled = false;
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
        "Exemplo carregado. A mancha é modelada, não observada. Verifique contornos e referências antes de uso.",
      );
    });
  function areaBox() {
    if (!state.layers.aoi?.features.length)
      throw Error(
        "Defina a área de interesse primeiro: procure o lugar na etapa 1 e toque em “Usar a área visível no mapa”.",
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
      ? `${state.terrain.source}${state.terrain.fileBytes ? " · arquivo " + (state.terrain.fileBytes / 1048576).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " MB" : ""} · ${state.terrain.width} × ${state.terrain.height} pontos sobre a área (com folga em volta).`
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
      osm = await overpass(O.consultaRios(t.bbox), 100);
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
      const layer = await compute("hand", [
        t.values,
        t.width,
        t.height,
        cellArea,
        Number($("drainArea").value) * 1e6,
        Number($("handLevel").value),
        t.bbox,
        rios ? rios.mascara : null,
      ]);
      if (rev !== state.revision)
        throw Error("Configuração alterada durante a geração. Gere novamente.");
      if (!layer.features.length)
        throw Error("O cenário não gerou área inundada. Revise os parâmetros.");
      state.layers.flood = layer;
      state.sources.flood =
        t.source +
        (rios ? " · rios do OpenStreetMap" : "") +
        " · HAND D8 experimental · área contribuinte " +
        $("drainArea").value +
        " km² · nível " +
        $("handLevel").value +
        " m";
      $("floodType").value = "hand";
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
      areaBox();
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
  $("csv").disabled = $("routes").disabled = true;
  render();
})();
