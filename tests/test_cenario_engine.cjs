const { test } = require("node:test");
const assert = require("node:assert/strict");
const E = require("../assets/js/cenario_engine.js"),
  T = require("../assets/js/cenario_terreno.js");
const f = (type, coordinates, properties = {}) => ({
    type: "Feature",
    geometry: { type, coordinates },
    properties,
  }),
  fc = (features) => ({ type: "FeatureCollection", features });
const base = () => ({
  roads: fc([
    f("LineString", [
      [0, 0],
      [0.004, 0],
    ]),
  ]),
  buildings: fc([
    f("Point", [0, 0], { pessoas: 3 }),
    f("Point", [0.001, 0], { pessoas: 3 }),
  ]),
  destinations: fc([
    f("Point", [0.004, 0], { nome: "Abrigo", tipo: "abrigo", capacidade: 3 }),
  ]),
});
const opts = {
  allBuildings: true,
  speed: 0.9,
  minutes: 20,
  margin: 0,
  mode: "manual",
  enforceCapacity: false,
  snapMax: 150,
  peoplePerBuilding: 3,
};
test("known capacity always enforced, households not split", () => {
  const r = E.plan(base(), opts);
  assert.equal(r.summary.assigned, 1);
  assert.equal(r.destinations[0].used, 3);
  assert.equal(r.summary.unassigned, 1);
  assert.equal(
    r.buildings.filter((b) => b.destination == null)[0].reason,
    "Sem capacidade disponível ou informada",
  );
});
test("occupancy subtracts from capacity", () => {
  const d = base();
  d.destinations.features[0].properties.ocupacao = 2;
  assert.equal(E.plan(d, opts).summary.assigned, 0);
});
test("unknown capacity is explicit; strict mode excludes it", () => {
  const d = base();
  delete d.destinations.features[0].properties.capacidade;
  assert.equal(E.plan(d, opts).summary.assigned, 2);
  assert.equal(
    E.plan(d, { ...opts, enforceCapacity: true }).summary.assigned,
    0,
  );
  assert.equal(E.plan(d, opts).destinations[0].capacity, null);
});
test("blocking the only road prevents routing across it including snap connectors", () => {
  const d = base();
  d.blocks = fc([
    f("LineString", [
      [0.002, -0.001],
      [0.002, 0.001],
    ]),
  ]);
  const r = E.plan(d, opts);
  assert.equal(r.summary.assigned, 0);
  assert(r.removed > 0);
});
test("collinear obstructions inside road segments are detected", () => {
  assert(
    E.hit(
      [0, 0],
      [1, 0],
      [
        f("LineString", [
          [0.2, 0],
          [0.4, 0],
        ]),
      ],
    ),
  );
});
test("crossing lines noded at grade; bridge crossing remains separated", () => {
  const roads = [
    f("LineString", [
      [-0.002, 0],
      [0.002, 0],
    ]),
    f("LineString", [
      [0, -0.002],
      [0, 0.002],
    ]),
  ];
  let g = E.graph(roads, {});
  assert(g.nodes.some((p) => Math.abs(p[0]) + Math.abs(p[1]) < 1e-10));
  roads[1].properties.bridge = "yes";
  g = E.graph(roads, {});
  const a = g.nodes.findIndex((p) => p[0] < -0.0019),
    b = g.nodes.findIndex((p) => p[1] > 0.0019),
    seen = new Set([a]);
  for (let change = true; change; ) {
    change = false;
    for (const [u, v] of g.edges)
      if (seen.has(u) !== seen.has(v)) {
        seen.add(u);
        seen.add(v);
        change = true;
      }
  }
  assert(!seen.has(b));
});
test("bridge connects at shared approach endpoints", () => {
  const d = base();
  d.roads = fc([
    f("LineString", [
      [0, 0],
      [0.002, 0],
    ]),
    f(
      "LineString",
      [
        [0.002, 0],
        [0.004, 0],
      ],
      { bridge: "yes" },
    ),
  ]);
  d.destinations.features[0].properties.capacidade = 20;
  assert.equal(E.plan(d, opts).summary.assigned, 2);
});
test("flood routing policy is explicit and safe destinations excluded", () => {
  const d = base();
  d.flood = fc([
    f("Polygon", [
      [
        [-0.001, -0.001],
        [0.0015, -0.001],
        [0.0015, 0.001],
        [-0.001, 0.001],
        [-0.001, -0.001],
      ],
    ]),
  ]);
  d.destinations.features[0].properties.capacidade = 20;
  assert.equal(E.plan(d, { ...opts, allBuildings: false }).summary.assigned, 2);
  assert.equal(
    E.plan(d, { ...opts, allBuildings: false, excludeFlood: true }).summary
      .assigned,
    0,
  );
  d.destinations.features[0].geometry.coordinates = [0.001, 0];
  assert.equal(E.plan(d, opts).rejected.length, 1);
});
test("holes in flood polygons are respected", () => {
  const g = f("Polygon", [
    [
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 1],
      [0, 0],
    ],
    [
      [0.2, 0.2],
      [0.8, 0.2],
      [0.8, 0.8],
      [0.2, 0.8],
      [0.2, 0.2],
    ],
  ]).geometry;
  assert(E.inside([0.1, 0.1], g));
  assert(!E.inside([0.5, 0.5], g));
});
test("eligible areas restrict automatic candidates", () => {
  const d = base();
  d.eligible = fc([
    f("Polygon", [
      [
        [0.0025, -0.001],
        [0.005, -0.001],
        [0.005, 0.001],
        [0.0025, 0.001],
        [0.0025, -0.001],
      ],
    ]),
  ]);
  const r = E.plan(d, { ...opts, mode: "automatico" });
  assert(r.destinations.length > 0);
  assert(r.destinations.every((x) => x.p[0] >= 0.0025));
});
test("invalid coordinates and invalid capacity fail rather than using defaults", () => {
  assert.throws(
    () => E.validate(fc([f("Point", [500, 5])]), "buildings"),
    /WGS84/,
  );
  const d = base();
  d.destinations.features[0].properties.capacidade = -1;
  assert.throws(() => E.plan(d, opts), /Capacidade/);
});
test("route uses assigned tree and ends at chosen destination", () => {
  const r = E.plan(base(), opts),
    i = r.buildings.findIndex((b) => b.destination != null),
    p = E.route(r, i);
  assert.deepEqual(p[0], r.buildings[i].p);
  assert.deepEqual(p.at(-1), [0.004, 0]);
});
test("HAND uses contributing area, higher level increases extent; nodata rejected", () => {
  const w = 9,
    h = 9,
    z = [];
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) z.push(Math.abs(x - 4) * 3 + (8 - y));
  const a = T.hand(z, w, h, 100, 300, 0, [0, 0, 1, 1]),
    b = T.hand(z, w, h, 100, 300, 10, [0, 0, 1, 1]);
  const area = (fc) =>
    fc.features.reduce((s, f) => {
      const r = f.geometry.coordinates[0];
      return s + (r[1][0] - r[0][0]) * (r[2][1] - r[1][1]);
    }, 0);
  assert(area(b) >= area(a));
  assert(b.features.length);
  z[0] = NaN;
  assert.throws(() => T.hand(z, w, h, 100, 300, 1, [0, 0, 1, 1]), /nodata/);
});
