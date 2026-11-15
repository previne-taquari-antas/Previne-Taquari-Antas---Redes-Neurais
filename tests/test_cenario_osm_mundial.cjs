// Bases abertas para qualquer lugar: consulta, conversão do OpenStreetMap e uso no cálculo.
const test = require("node:test"),
  assert = require("node:assert/strict"),
  O = require("../assets/js/cenario_osm.js"),
  E = require("../assets/js/cenario_engine.js");
const g = (pts) => pts.map(([lon, lat]) => ({ lat, lon }));
// um trecho de cidade fora do Brasil (Lisboa): duas ruas que se cruzam, duas casas
const osm = {
  osm3s: { timestamp_osm_base: "2026-11-01T00:00:00Z" },
  elements: [
    {
      type: "way",
      id: 1,
      nodes: [10, 11, 12],
      tags: { highway: "residential", name: "Rua A" },
      geometry: g([
        [-9.14, 38.71],
        [-9.139, 38.71],
        [-9.138, 38.71],
      ]),
    },
    {
      type: "way",
      id: 2,
      nodes: [11, 13],
      tags: { highway: "footway" },
      geometry: g([
        [-9.139, 38.71],
        [-9.139, 38.711],
      ]),
    },
    {
      type: "way",
      id: 3,
      nodes: [20, 21, 22, 23, 20],
      tags: { building: "yes" },
      geometry: g([
        [-9.1399, 38.7101],
        [-9.1398, 38.7101],
        [-9.1398, 38.7102],
        [-9.1399, 38.7102],
        [-9.1399, 38.7101],
      ]),
    },
    {
      type: "relation",
      id: 4,
      tags: { building: "yes", type: "multipolygon" },
      members: [
        {
          role: "outer",
          geometry: g([
            [-9.1385, 38.7101],
            [-9.1384, 38.7101],
            [-9.1384, 38.7102],
            [-9.1385, 38.7102],
          ]),
        },
      ],
    },
    {
      type: "way",
      id: 5,
      nodes: [30],
      tags: { highway: "service" },
      geometry: g([[-9.1, 38.7]]),
    },
  ],
};

test("consulta usa a caixa na ordem sul, oeste, norte, leste", () => {
  const q = O.consulta([-9.14, 38.7, -9.13, 38.72]);
  assert.match(q, /\(38\.700000,-9\.140000,38\.720000,-9\.130000\)/);
  assert.match(q, /way\["highway"\]/);
  assert.match(q, /way\["building"\]/);
});

test("área da caixa em km²", () => {
  const a = O.areaKm2([-51.74, -29.18, -51.72, -29.16]);
  assert.ok(a > 4 && a < 4.6, String(a));
});

test("converte ruas (com nós) e edificações; ignora o que não serve", () => {
  const r = O.converte(osm);
  assert.equal(r.roads.features.length, 2);
  assert.equal(r.buildings.features.length, 2);
  assert.deepEqual(r.roads.features[0].properties.osm_node_ids, [
    "10",
    "11",
    "12",
  ]);
  assert.equal(r.roads.features[0].properties.highway, "residential");
  const anel = r.buildings.features[1].geometry.coordinates[0];
  assert.deepEqual(anel[0], anel.at(-1)); // anel fechado
  assert.equal(r.data, "2026-11-01T00:00:00Z");
});

test("o que vem do OpenStreetMap passa na validação e calcula", () => {
  const r = O.converte(osm),
    roads = E.validate(r.roads, "roads"),
    buildings = E.validate(r.buildings, "buildings");
  assert.equal(roads.features.length, 2);
  assert.equal(buildings.features.length, 2);
});

test("lugares do Nominatim: caixa em oeste, sul, leste, norte e limite só se for polígono", () => {
  const l = O.lugares([
    {
      display_name: "Lisboa, Portugal",
      boundingbox: ["38.69", "38.80", "-9.23", "-9.09"],
      geojson: { type: "Polygon", coordinates: [] },
    },
    {
      display_name: "Ponto",
      boundingbox: ["1", "2", "3", "4"],
      geojson: { type: "Point", coordinates: [3, 1] },
    },
    { display_name: "sem caixa" },
  ]);
  assert.equal(l.length, 2);
  assert.deepEqual(l[0].caixa, [-9.23, 38.69, -9.09, 38.8]);
  assert.equal(l[0].limite.type, "Polygon");
  assert.equal(l[1].limite, null);
  assert.match(O.urlLugar("São Paulo"), /q=S%C3%A3o%20Paulo/);
});
