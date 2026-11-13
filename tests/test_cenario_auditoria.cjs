const { test } = require("node:test"),
  A = require("node:assert/strict");
const E = require("../assets/js/cenario_engine.js"),
  T = require("../assets/js/cenario_terreno.js");
const f = (type, coordinates, properties = {}) => ({
    type: "Feature",
    geometry: { type, coordinates },
    properties,
  }),
  fc = (features) => ({ type: "FeatureCollection", features }),
  rect = (x1, y1, x2, y2) =>
    f("Polygon", [
      [
        [x1, y1],
        [x2, y1],
        [x2, y2],
        [x1, y2],
        [x1, y1],
      ],
    ]);
const o = {
  allBuildings: true,
  speed: 1,
  minutes: 20,
  margin: 0,
  mode: "manual",
  peoplePerBuilding: 3,
};
const d = () => ({
  roads: fc([
    f("LineString", [
      [-0.002, 0],
      [0.002, 0],
    ]),
  ]),
  buildings: fc([
    f("Point", [-0.001, 0], { pessoas: 2 }),
    f("Point", [0.001, 0], { pessoas: 3 }),
  ]),
  destinations: fc([
    f("Point", [0.002, 0], { nome: "Abrigo", capacidade: 10 }),
  ]),
});
function reachable(g, a, b) {
  const seen = new Set([a]);
  for (let flag = true; flag; ) {
    flag = false;
    for (const [x, y] of g.edges)
      if (seen.has(x) !== seen.has(y)) {
        seen.add(x);
        seen.add(y);
        flag = true;
      }
  }
  return seen.has(b);
}
test("road crossing at different levels does not connect", () => {
  const g = E.graph(
    [
      f(
        "LineString",
        [
          [-0.002, 0],
          [0.002, 0],
        ],
        { layer: 0 },
      ),
      f(
        "LineString",
        [
          [0, -0.002],
          [0, 0.002],
        ],
        { layer: 1 },
      ),
    ],
    {},
  );
  A(
    !reachable(
      g,
      g.nodes.findIndex((p) => p[0] < -0.0019),
      g.nodes.findIndex((p) => p[1] > 0.0019),
    ),
  );
});
test("tunnel crossing does not connect to surface road", () => {
  const g = E.graph(
    [
      f("LineString", [
        [-0.002, 0],
        [0.002, 0],
      ]),
      f(
        "LineString",
        [
          [0, -0.002],
          [0, 0.002],
        ],
        { tunnel: "yes" },
      ),
    ],
    {},
  );
  A(
    !reachable(
      g,
      g.nodes.findIndex((p) => p[0] < -0.0019),
      g.nodes.findIndex((p) => p[1] > 0.0019),
    ),
  );
});
test("collinear partial overlaps connect without disconnected duplicate nodes", () => {
  const g = E.graph(
    [
      f("LineString", [
        [0, 0],
        [0.003, 0],
      ]),
      f("LineString", [
        [0.001, 0],
        [0.004, 0],
      ]),
    ],
    {},
  );
  A(
    reachable(
      g,
      g.nodes.findIndex((p) => p[0] === 0),
      g.nodes.findIndex((p) => p[0] === 0.004),
    ),
  );
});
test("excluded road classes and foot=no are not used", () => {
  const x = d();
  x.roads.features[0].properties = { highway: "motorway", foot: "no" };
  A.throws(() => E.plan(x, { ...o, roadTypes: ["motorway"] }), /Nenhuma via/);
});
test("polygon blockers remove crossing routes", () => {
  const x = d();
  x.blocks = fc([rect(-0.0001, -0.001, 0.0001, 0.001)]);
  A.equal(E.plan(x, o).summary.assigned, 1);
});
test("point obstruction respects 15m radius and prevents connector crossing", () => {
  const x = d();
  x.blocks = fc([f("Point", [0, 0])]);
  A.equal(E.plan(x, o).summary.assigned, 1);
});
test("out-of-AOI household does not enter demand", () => {
  const x = d();
  x.aoi = fc([rect(0, -0.001, 0.003, 0.001)]);
  A.equal(E.plan(x, o).summary.required, 1);
});
test("hole inside AOI is not used as a shortcut", () => {
  const x = d();
  x.aoi = fc([
    f("Polygon", [
      rect(-0.003, -0.003, 0.003, 0.003).geometry.coordinates[0],
      rect(-0.0001, -0.001, 0.0001, 0.001).geometry.coordinates[0],
    ]),
  ]);
  A.equal(E.plan(x, o).summary.assigned, 1);
});
test("known shelter capacity enforced together with unknown-capacity shelter", () => {
  const x = d();
  x.destinations.features.push(f("Point", [-0.002, 0], { nome: "Unknown" }));
  x.destinations.features[0].properties.capacidade = 3;
  const r = E.plan(x, o);
  A.equal(r.summary.assigned, 2);
  A.equal(r.destinations[0].used, 3);
  A.equal(r.destinations[1].used, 2);
});
test("strict capacity ignores unknown destination, respects occupancy", () => {
  const x = d();
  x.destinations.features[0].properties = {
    nome: "A",
    capacidade: 5,
    ocupacao: 2,
  };
  x.destinations.features.push(f("Point", [-0.002, 0], { nome: "Unknown" }));
  const r = E.plan(x, { ...o, enforceCapacity: true });
  A.equal(r.summary.assigned, 1);
  A.equal(r.destinations[0].used, 3);
});
test("all served people match household sum and destination sums", () => {
  for (let k = 0; k < 50; k++) {
    const x = d();
    x.destinations.features[0].properties.capacidade = k % 10;
    const r = E.plan(x, o);
    A.equal(
      r.summary.served,
      r.destinations.reduce((s, d) => s + d.used, 0),
    );
    A.equal(
      r.summary.served,
      r.buildings
        .filter((b) => b.destination != null)
        .reduce((s, b) => s + b.people, 0),
    );
    A(r.destinations.every((d) => d.used + d.occupancy <= d.capacity));
  }
});
test("safe destination rejected in flood even if allBuildings=true", () => {
  const x = d();
  x.flood = fc([rect(0.0015, -0.001, 0.0025, 0.001)]);
  const r = E.plan(x, o);
  A.equal(r.destinations.length, 0);
  A.equal(r.rejected.length, 1);
});
test("reported route duration matches geometric route length / speed", () => {
  const x = d(),
    r = E.plan(x, { ...o, speed: 0.5 });
  for (let i = 0; i < r.buildings.length; i++) {
    const path = E.route(r, i),
      dist = path.reduce(
        (s, p, j) => (j ? s + E.distance(path[j - 1], p) : s),
        0,
      );
    A(Math.abs(dist / 0.5 - r.buildings[i].seconds) < 1e-8);
  }
});
test("routes never cross a known blocker", () => {
  const x = d();
  x.blocks = fc([rect(-0.0001, -0.001, 0.0001, 0.001)]);
  const r = E.plan(x, o);
  for (let i = 0; i < r.buildings.length; i++) {
    const path = E.route(r, i);
    for (let j = 1; j < path.length; j++)
      A(!E.hit(path[j - 1], path[j], x.blocks.features));
  }
});
test("HAND larger water level contains every cell wet at smaller level", () => {
  const n = 15,
    z = Array.from(
      { length: n * n },
      (_, i) => Math.abs((i % n) - 7) * 2 + (14 - Math.floor(i / n)),
    );
  const a = T.hand(z, n, n, 900, 9000, 1, [0, 0, 1, 1]),
    b = T.hand(z, n, n, 900, 9000, 3, [0, 0, 1, 1]);
  for (let y = 0; y < n; y++)
    for (let x = 0; x < n; x++) {
      const p = [(x + 0.5) / n, 1 - (y + 0.5) / n];
      if (a.features.some((f) => E.inside(p, f.geometry)))
        A(b.features.some((f) => E.inside(p, f.geometry)));
    }
});
test("HAND rejects nodata and missing drainage", () => {
  A.throws(
    () => T.hand(Array(25).fill(NaN), 5, 5, 100, 300, 2, [0, 0, 1, 1]),
    /nodata/,
  );
  A.throws(
    () => T.hand(Array(25).fill(0), 5, 5, 100, 1e20, 2, [0, 0, 1, 1]),
    /Nenhuma drenagem/,
  );
});
test("float32 GeoTIFF roundtrip preserves negatives and georeferencing", async () => {
  const { fromArrayBuffer } = await import(
    "./frontend/node_modules/geotiff/dist-module/geotiff.js"
  );
  const z = [-12.25, 0, 2.125, 1000.5],
    buf = T.writeGeoTIFF({
      width: 2,
      height: 2,
      bbox: [-52, -30, -51, -29],
      values: z,
    }),
    im = await (await fromArrayBuffer(buf)).getImage();
  A.deepEqual(Array.from((await im.readRasters())[0]), z);
  A.deepEqual(im.getBoundingBox(), [-52, -30, -51, -29]);
  A.equal(im.getGeoKeys().GeographicTypeGeoKey, 4326);
});
// Regression cases found by independent audit.
test("AOI clips roads crossing its boundary before node filtering", () => {
  const x = {
    roads: fc([
      f("LineString", [
        [-0.001, 0],
        [0.001, 0],
      ]),
    ]),
    buildings: fc([f("Point", [0, 0], { pessoas: 3 })]),
    destinations: fc([f("Point", [0.00005, 0], { capacidade: 10 })]),
    aoi: fc([rect(-0.0001, -0.0001, 0.0001, 0.0001)]),
  };
  A.equal(E.plan(x, o).summary.assigned, 1);
});
test("GeoJSON Point rejects nested coordinates", () =>
  A.throws(() => E.validate(fc([f("Point", [[0, 0]])]), "buildings")));
test("GeoJSON LineString rejects coordinate tuple instead of positions", () =>
  A.throws(() => E.validate(fc([f("LineString", [0, 0])]), "roads")));

test("self-intersecting rings fail before rendering", () =>
  A.throws(
    () =>
      E.validate(
        fc([
          f("Polygon", [
            [
              [0, 0],
              [1, 1],
              [0, 1],
              [1, 0],
              [0, 0],
            ],
          ]),
        ]),
        "flood",
      ),
    /auto-interseção/,
  ));
test("nonfinite routing parameters fail explicitly", () => {
  for (const k of ["speed", "minutes", "margin"])
    A.throws(() => E.plan(d(), { ...o, [k]: Infinity }), /inválidos/);
});
test("optional empty layers survive configuration validation", () => {
  for (const k of ["destinations", "blocks", "flood", "eligible", "aoi"])
    A.deepEqual(E.validate(fc([]), k, { allowEmpty: true }).features, []);
  A.throws(() => E.validate(fc([]), "roads"), /vazia/);
});
test("GeoJSON altitude is ignored consistently for network matching", () => {
  const x = d();
  x.roads.features[0].geometry.coordinates =
    x.roads.features[0].geometry.coordinates.map((p) => [...p, 200]);
  A.equal(E.plan(x, o).summary.assigned, 2);
});

test("valid polygon hole may touch shell at an isolated point", () => {
  const shell = rect(0, 0, 1, 1).geometry.coordinates[0];
  const hole = [
    [0, 0.5],
    [0.25, 0.25],
    [0.5, 0.5],
    [0.25, 0.75],
    [0, 0.5],
  ];
  A.doesNotThrow(() => E.validate(f("Polygon", [shell, hole]), "flood"));
});
test("hole touching shell at two distinct points is rejected", () => {
  const shell = rect(0, 0, 1, 1).geometry.coordinates[0];
  const hole = [
    [0, 0.5],
    [0.5, 0.2],
    [1, 0.5],
    [0.5, 0.8],
    [0, 0.5],
  ];
  A.throws(() => E.validate(f("Polygon", [shell, hole]), "flood"));
});
test("published Santa Tereza flood geometry remains valid for the planner", () => {
  const fs = require("fs"),
    path = require("path"),
    d = JSON.parse(
      fs.readFileSync(
        path.join(
          __dirname,
          "../assets/data/rota_fuga/santa_tereza_pontos_encontro_hand.json",
        ),
      ),
    );
  A.doesNotThrow(() => E.validate(d.mancha, "flood"));
});
