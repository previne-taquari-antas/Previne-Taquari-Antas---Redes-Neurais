/* Bases abertas para qualquer lugar do mundo: procura de lugar (Nominatim) e ruas e edificações
   do OpenStreetMap (Overpass) para a área de interesse. Só monta consultas e converte respostas;
   quem chama a rede é a página (cenario_municipal.js). tests/test_cenario_osm_mundial.cjs. */
(function (raiz) {
  "use strict";
  const SERVIDORES = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
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
    return `[out:json][timeout:120];(way["highway"]${bb};way["building"]${bb};relation["building"]["type"="multipolygon"]${bb};);out body geom;${caixaRios ? RIOS(caixaTxt(caixaRios)) : ""}`;
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
    mascaraRios,
    RELEVO_URL,
    RELEVO_FONTE,
    tx,
    ty,
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
