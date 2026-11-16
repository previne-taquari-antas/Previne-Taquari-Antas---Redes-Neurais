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

const T = require("../assets/js/cenario_terreno.js");

test("rios do mapa viram células da grade (linha e polígono de água)", () => {
  const caixa = [0, 0, 1, 1],
    r = O.mascaraRios(
      {
        elements: [
          { type: "way", tags: { waterway: "river" }, geometry: g([[0.05, 0.55], [0.95, 0.55]]) },
          { type: "way", tags: { natural: "water", water: "river" },
            geometry: g([[0.2, 0.1], [0.4, 0.1], [0.4, 0.3], [0.2, 0.3], [0.2, 0.1]]) },
        ],
      },
      caixa, 10, 10,
    );
  // linha do rio: latitude 0,55 fica na linha 4 da grade (o norte é a linha 0)
  for (let x = 1; x < 9; x++) assert.equal(r.mascara[4 * 10 + x], 1);
  assert.equal(r.mascara[8 * 10 + 3], 1); // miolo do polígono
  assert.equal(r.mascara[0], 0);
  assert.ok(r.celulas >= 12);
  assert.match(O.consultaRios(caixa), /waterway/);
});

test("relevo: escolha dos quadros e leitura da altura", () => {
  const q = O.quadrosRelevo([-51.98, -29.48, -51.94, -29.45]);
  assert.equal(q.z, 13);
  assert.ok((q.x1 - q.x0 + 1) * (q.y1 - q.y0 + 1) <= 30);
  assert.ok(O.quadrosRelevo([-52, -30, -51, -29]).z < 13); // área maior, zoom menor
  assert.equal(O.alturaTerrarium(128, 0, 0), 0);
  assert.equal(O.alturaTerrarium(128, 100, 128), 100.5);
  assert.deepEqual(O.folga([0, 0, 4, 2]), [-1, -0.5, 5, 2.5]);
});

test("HAND acha o rio pelo mapa mesmo sem a bacia dentro do recorte", () => {
  // vale em V com o rio no meio; o recorte é pequeno demais para o rio juntar área contribuinte
  const n = 21,
    z = [];
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) z.push(Math.abs(x - 10) * 2 + (n - y) * 0.01);
  const rios = new Uint8Array(n * n);
  for (let y = 0; y < n; y++) rios[y * n + 10] = 1;
  assert.throws(() => T.hand(z, n, n, 900, 1e9, 3, [0, 0, 1, 1]), /Nenhuma drenagem/);
  const com = T.hand(z, n, n, 900, 1e9, 3, [0, 0, 1, 1], rios);
  assert.ok(com.features.length > 0);
  // molha o rio e uma célula de cada lado (2 m acima), não a segunda (4 m)
  const xs = com.features.flatMap((f) => f.geometry.coordinates[0].map((p) => p[0]));
  assert.ok(Math.min(...xs) >= 9 / n - 1e-9 && Math.max(...xs) <= 12 / n + 1e-9);
  assert.throws(() => T.hand(z, n, n, 900, 1e9, 3, [0, 0, 1, 1], new Uint8Array(3)), /Máscara/);
});

test("conta os trechos de rua", () => {
  assert.equal(O.trechos(O.converte(osm).roads), 3);
});
