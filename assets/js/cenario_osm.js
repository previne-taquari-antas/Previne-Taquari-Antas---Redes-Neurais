/* Bases abertas para qualquer lugar do mundo: procura de lugar (Nominatim) e ruas e edificações
   do OpenStreetMap (Overpass) para a área de interesse. Só monta consultas e converte respostas;
   quem chama a rede é a página (cenario_municipal.js). tests/test_cenario_osm_mundial.cjs. */
(function (raiz) {
  "use strict";
  const SERVIDORES = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
  ];
  const AREA_MAX_KM2 = 60;

  // área aproximada da caixa [oeste, sul, leste, norte] em km²
  function areaKm2([w, s, e, n]) {
    const lat = ((s + n) / 2) * (Math.PI / 180);
    return Math.abs((e - w) * 111.32 * Math.cos(lat) * (n - s) * 110.57);
  }

  const caixaTxt = ([w, s, e, n]) =>
    `(${s.toFixed(6)},${w.toFixed(6)},${n.toFixed(6)},${e.toFixed(6)})`;
  // só linhas e margens de rio: a relação de um rio grande traria o rio inteiro, de fora da área.
  // geom(caixa) corta a geometria na caixa, pelo mesmo motivo.
  const RIOS = (bb) =>
    `(way["waterway"~"^(river|stream|canal)$"]${bb};way["natural"="water"]["water"~"^(river|canal)$"]${bb};way["waterway"="riverbank"]${bb};);out body geom${bb};`;
  // ruas e edificações da caixa; com caixaRios, os rios vêm no mesmo pedido (menos idas ao servidor)
  function consulta(caixa, caixaRios) {
    const bb = caixaTxt(caixa);
    // das edificações vem só o centro: é o que o cálculo usa, e o pedido fica várias vezes mais leve
    // (com o contorno de cada prédio, cidades densas estouravam o tempo do servidor)
    return `[out:json][timeout:120];way["highway"]${bb};out body geom;(way["building"]${bb};relation["building"]${bb};);out tags center;${caixaRios ? RIOS(caixaTxt(caixaRios)) : ""}`;
  }

  const anel = (g) => {
    const c = g.filter(Boolean).map((p) => [p.lon, p.lat]);
    if (c.length && (c[0][0] !== c.at(-1)[0] || c[0][1] !== c.at(-1)[1]))
      c.push(c[0]);
    return c;
  };
  const etiquetas = (el) => ({ ...(el.tags || {}), osm_id: el.id });

  function converte(osm) {
    const roads = [],
      buildings = [];
    const rios = [];
    for (const el of osm.elements || []) {
      const t = el.tags || {};
      if (t.waterway || t.natural === "water") {
        rios.push(el);
        continue;
      }
      if (t.building && el.center) {
        buildings.push({
          type: "Feature",
          id: el.type + "/" + el.id,
          properties: etiquetas(el),
          geometry: {
            type: "Point",
            coordinates: [el.center.lon, el.center.lat],
          },
        });
        continue;
      }
      if (el.type === "way" && Array.isArray(el.geometry)) {
        if (t.highway && !t.building) {
          const ok = el.geometry.every(Boolean),
            coords = el.geometry.filter(Boolean).map((p) => [p.lon, p.lat]);
          if (coords.length < 2) continue;
          const props = etiquetas(el);
          // os nós do OSM dizem onde as ruas se ligam de verdade (pontes e túneis não se ligam por cima)
          if (
            ok &&
            Array.isArray(el.nodes) &&
            el.nodes.length === coords.length
          )
            props.osm_node_ids = el.nodes.map(String);
          roads.push({
            type: "Feature",
            id: "way/" + el.id,
            properties: props,
            geometry: { type: "LineString", coordinates: coords },
          });
        } else if (t.building) {
          const c = anel(el.geometry);
          if (c.length >= 4)
            buildings.push({
              type: "Feature",
              id: "way/" + el.id,
              properties: etiquetas(el),
              geometry: { type: "Polygon", coordinates: [c] },
            });
        }
      } else if (el.type === "relation" && t.building) {
        const fora = (el.members || [])
          .filter((m) => m.role === "outer" && Array.isArray(m.geometry))
          .map((m) => anel(m.geometry))
          .filter((c) => c.length >= 4);
        if (fora.length)
          buildings.push({
            type: "Feature",
            id: "relation/" + el.id,
            properties: etiquetas(el),
            geometry:
              fora.length === 1
                ? { type: "Polygon", coordinates: [fora[0]] }
                : { type: "MultiPolygon", coordinates: fora.map((c) => [c]) },
          });
      }
    }
    return {
      roads: { type: "FeatureCollection", features: roads },
      buildings: { type: "FeatureCollection", features: buildings },
      rios,
      data: osm.osm3s?.timestamp_osm_base || null,
    };
  }

  // reserva quando nenhum Overpass responde: o próprio servidor do OpenStreetMap entrega tudo o que
  // há numa caixa pequena (até 50 mil pontos). Vem sem geometria nas linhas; aqui ela é montada.
  const urlMapa = ([w, s, e, n]) =>
    `https://api.openstreetmap.org/api/0.6/map.json?bbox=${w.toFixed(6)},${s.toFixed(6)},${e.toFixed(6)},${n.toFixed(6)}`;
  function deMapa(json) {
    const nos = new Map(),
      linhas = new Map(),
      elements = [];
    for (const el of json.elements || [])
      if (el.type === "node") nos.set(el.id, { lat: el.lat, lon: el.lon });
      else if (el.type === "way") linhas.set(el.id, el);
    const geom = (w) => (w.nodes || []).map((id) => nos.get(id) || null);
    for (const el of json.elements || []) {
      if (el.type === "way" && el.tags)
        elements.push({ ...el, geometry: geom(el) });
      else if (el.type === "relation" && el.tags)
        elements.push({
          ...el,
          members: (el.members || []).map((m) =>
            m.type === "way" && linhas.has(m.ref)
              ? { ...m, geometry: geom(linhas.get(m.ref)) }
              : m,
          ),
        });
    }
    return { osm3s: json.osm3s, elements };
  }

  // O OpenStreetMap tem geometrias com defeito (um prédio cujo contorno se cruza, por exemplo) e uma só
  // não pode derrubar o download inteiro. valida(fc) é a validação da página, que lança erro.
  // Prédio com defeito vira um ponto no meio dele (as pessoas continuam lá); o resto sai da lista.
  function aproveita(fc, valida) {
    const features = [];
    let consertadas = 0,
      fora = 0;
    const passa = (f) => {
      try {
        valida({ type: "FeatureCollection", features: [f] });
        return true;
      } catch (e) {
        return false;
      }
    };
    for (const f of fc.features) {
      if (passa(f)) {
        features.push(f);
        continue;
      }
      const g = f.geometry,
        anel =
          g.type === "Polygon"
            ? g.coordinates[0]
            : g.type === "MultiPolygon"
              ? g.coordinates[0][0]
              : null;
      if (anel && anel.length) {
        const p = {
          ...f,
          geometry: {
            type: "Point",
            coordinates: [
              anel.reduce((t, c) => t + c[0], 0) / anel.length,
              anel.reduce((t, c) => t + c[1], 0) / anel.length,
            ],
          },
        };
        if (passa(p)) {
          features.push(p);
          consertadas++;
          continue;
        }
      }
      fora++;
    }
    return { fc: { type: "FeatureCollection", features }, consertadas, fora };
  }

  // Menos trechos por rua: tira os pontos de curva que mudam o traçado em menos de tolM metros.
  // Ficam as pontas e todo ponto onde duas ruas se encontram (os cruzamentos não mudam).
  function simplifica(roads, tolM = 4) {
    const usos = new Map();
    for (const f of roads.features)
      for (const id of f.properties.osm_node_ids || [])
        usos.set(id, (usos.get(id) || 0) + 1);
    const features = roads.features.map((f) => {
      const c = f.geometry.coordinates,
        ids = f.properties.osm_node_ids;
      if (
        f.geometry.type !== "LineString" ||
        c.length < 3 ||
        !ids ||
        ids.length !== c.length
      )
        return f;
      const kx = 111320 * Math.cos((c[0][1] * Math.PI) / 180),
        ky = 110570,
        fica = new Uint8Array(c.length);
      fica[0] = fica[c.length - 1] = 1;
      for (let i = 1; i < c.length - 1; i++)
        if (usos.get(ids[i]) > 1) fica[i] = 1;
      // Douglas-Peucker em cada pedaço entre dois pontos que ficam
      const pilha = [];
      let a = 0;
      for (let i = 1; i < c.length; i++)
        if (fica[i]) {
          if (i - a > 1) pilha.push([a, i]);
          a = i;
        }
      while (pilha.length) {
        const [i0, i1] = pilha.pop(),
          x0 = c[i0][0] * kx,
          y0 = c[i0][1] * ky,
          dx = c[i1][0] * kx - x0,
          dy = c[i1][1] * ky - y0,
          L2 = dx * dx + dy * dy;
        let pior = -1,
          dmax = tolM;
        for (let i = i0 + 1; i < i1; i++) {
          const px = c[i][0] * kx - x0,
            py = c[i][1] * ky - y0,
            t = L2 ? Math.max(0, Math.min(1, (px * dx + py * dy) / L2)) : 0,
            d = Math.hypot(px - t * dx, py - t * dy);
          if (d > dmax) {
            dmax = d;
            pior = i;
          }
        }
        if (pior > 0) {
          fica[pior] = 1;
          if (pior - i0 > 1) pilha.push([i0, pior]);
          if (i1 - pior > 1) pilha.push([pior, i1]);
        }
      }
      return {
        ...f,
        properties: {
          ...f.properties,
          osm_node_ids: ids.filter((_, i) => fica[i]),
        },
        geometry: {
          type: "LineString",
          coordinates: c.filter((_, i) => fica[i]),
        },
      };
    });
    return { type: "FeatureCollection", features };
  }

  const urlLugar = (texto) =>
    "https://nominatim.openstreetmap.org/search?format=jsonv2&polygon_geojson=1&polygon_threshold=0.0005&limit=5&q=" +
    encodeURIComponent(texto);

  // respostas do Nominatim -> [{nome, caixa [o,s,l,n], limite (Polygon/MultiPolygon ou null)}]
  function lugares(lista) {
    return (lista || [])
      .map((r) => {
        const b = (r.boundingbox || []).map(Number);
        if (b.length !== 4 || !b.every(Number.isFinite)) return null;
        const g = r.geojson;
        return {
          nome: r.display_name || r.name || "",
          caixa: [b[2], b[0], b[3], b[1]],
          limite:
            g && (g.type === "Polygon" || g.type === "MultiPolygon") ? g : null,
        };
      })
      .filter(Boolean)
      .filter((l, i, t) => t.findIndex((x) => x.nome === l.nome) === i);
  }

  // rios mapeados: a drenagem do HAND sem precisar da bacia inteira
  // o mesmo pedido em duas partes menores, para quando o servidor não dá conta dele inteiro
  function consultaPartes(caixa, caixaRios) {
    const bb = caixaTxt(caixa);
    return [
      `[out:json][timeout:120];way["highway"]${bb};out body geom;${caixaRios ? RIOS(caixaTxt(caixaRios)) : ""}`,
      `[out:json][timeout:120];(way["building"]${bb};relation["building"]${bb};);out tags center;`,
    ];
  }
  function consultaRios(caixa) {
    return `[out:json][timeout:90];${RIOS(caixaTxt(caixa))}`;
  }
  // células da grade (largura x altura sobre a caixa) por onde passa rio; devolve {mascara, celulas}
  function mascaraRios(osm, [w, s, e, n], largura, altura) {
    const m = new Uint8Array(largura * altura),
      cx = (lon) => ((lon - w) / (e - w)) * largura,
      cy = (lat) => ((n - lat) / (n - s)) * altura,
      marca = (x, y) => {
        x = Math.floor(x);
        y = Math.floor(y);
        if (x >= 0 && y >= 0 && x < largura && y < altura)
          m[y * largura + x] = 1;
      };
    function linha(g) {
      // pontos fora da caixa vêm vazios: o trecho que sai da área não é ligado em linha reta
      const pts = g;
      for (let i = 1; i < pts.length; i++) {
        if (!pts[i - 1] || !pts[i]) continue;
        const x0 = cx(pts[i - 1].lon),
          y0 = cy(pts[i - 1].lat),
          x1 = cx(pts[i].lon),
          y1 = cy(pts[i].lat),
          passos = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) * 2));
        if (passos > 20000) continue;
        for (let k = 0; k <= passos; k++)
          marca(x0 + ((x1 - x0) * k) / passos, y0 + ((y1 - y0) * k) / passos);
      }
    }
    function miolo(g) {
      // interior do polígono de água, por varredura das linhas da grade
      const pts = g.filter(Boolean).map((p) => [cx(p.lon), cy(p.lat)]);
      if (pts.length < 3) return;
      const ys = pts.map((p) => p[1]),
        ya = Math.max(0, Math.floor(Math.min(...ys))),
        yb = Math.min(altura - 1, Math.ceil(Math.max(...ys)));
      for (let y = ya; y <= yb; y++) {
        const yc = y + 0.5,
          xs = [];
        for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
          const [xi, yi] = pts[i],
            [xj, yj] = pts[j];
          if (yi > yc !== yj > yc)
            xs.push(xi + ((yc - yi) * (xj - xi)) / (yj - yi));
        }
        xs.sort((a, b) => a - b);
        for (let k = 0; k + 1 < xs.length; k += 2)
          for (
            let x = Math.max(0, Math.ceil(xs[k] - 0.5));
            x <= Math.min(largura - 1, Math.floor(xs[k + 1] - 0.5));
            x++
          )
            m[y * largura + x] = 1;
      }
    }
    for (const el of osm.elements || []) {
      const t = el.tags || {};
      if (el.type === "way" && Array.isArray(el.geometry)) {
        linha(el.geometry);
        if (t.natural === "water" || t.waterway === "riverbank")
          miolo(el.geometry);
      } else if (el.type === "relation")
        for (const mb of el.members || [])
          if (Array.isArray(mb.geometry)) {
            linha(mb.geometry);
            if (mb.role === "outer") miolo(mb.geometry);
          }
    }
    let celulas = 0;
    for (const v of m) celulas += v;
    return { mascara: m, celulas };
  }

  // relevo do mundo todo que o navegador consegue ler direto (Terrain Tiles, formato terrarium)
  const RELEVO_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/",
    RELEVO_FONTE =
      "Terrain Tiles (AWS/Mapzen: SRTM e outras bases abertas, cerca de 30 m)";
  const tx = (lon, z) => ((lon + 180) / 360) * 2 ** z,
    ty = (lat, z) => {
      const r = (lat * Math.PI) / 180;
      return (
        ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * 2 ** z
      );
    };
  // maior zoom (até 13) em que a caixa cabe em poucos quadros
  function quadrosRelevo([w, s, e, n], maximo = 30) {
    for (let z = 13; z >= 5; z--) {
      const x0 = Math.floor(tx(w, z)),
        x1 = Math.floor(tx(e, z)),
        y0 = Math.floor(ty(n, z)),
        y1 = Math.floor(ty(s, z));
      if ((x1 - x0 + 1) * (y1 - y0 + 1) <= maximo) return { z, x0, x1, y0, y1 };
    }
    throw Error(
      "Área grande demais para buscar o relevo. Reduza a área de interesse.",
    );
  }
  // metros a partir das cores de um ponto do quadro
  const alturaTerrarium = (r, g, b) => r * 256 + g + b / 256 - 32768;
  // caixa aumentada em volta da área (o rio e as margens costumam passar da borda)
  function folga([w, s, e, n], f = 0.25) {
    const dx = (e - w) * f,
      dy = (n - s) * f;
    return [w - dx, Math.max(-84, s - dy), e + dx, Math.min(84, n + dy)];
  }
  const trechos = (roads) =>
    roads.features.reduce(
      (t, f) => t + Math.max(0, f.geometry.coordinates.length - 1),
      0,
    );

  const api = {
    consultaRios,
    consultaPartes,
    mascaraRios,
    RELEVO_URL,
    RELEVO_FONTE,
    tx,
    ty,
    aproveita,
    simplifica,
    urlMapa,
    deMapa,
    quadrosRelevo,
    alturaTerrarium,
    folga,
    trechos,
    SERVIDORES,
    AREA_MAX_KM2,
    areaKm2,
    consulta,
    converte,
    urlLugar,
    lugares,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else raiz.CenarioOSM = api;
})(typeof self !== "undefined" ? self : this);
