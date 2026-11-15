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

  function consulta([w, s, e, n]) {
    const bb = `(${s.toFixed(6)},${w.toFixed(6)},${n.toFixed(6)},${e.toFixed(6)})`;
    return `[out:json][timeout:120];(way["highway"]${bb};way["building"]${bb};relation["building"]["type"="multipolygon"]${bb};);out body geom;`;
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
    for (const el of osm.elements || []) {
      const t = el.tags || {};
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

  const api = {
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
