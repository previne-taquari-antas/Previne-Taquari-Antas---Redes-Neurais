const fs = require("fs"),
  path = require("path"),
  assert = require("assert/strict"),
  E = require("../assets/js/cenario_engine.js");
const root = path.join(__dirname, "fixtures/brasil_osm"),
  slugs = ["manaus", "recife", "brasilia", "sao_paulo", "curitiba", "macapa"];
const f = (type, coordinates, properties = {}) => ({
    type: "Feature",
    geometry: { type, coordinates },
    properties,
  }),
  fc = (features) => ({ type: "FeatureCollection", features }),
  poly = (w, s, e, n) =>
    f("Polygon", [
      [
        [w, s],
        [e, s],
        [e, n],
        [w, n],
        [w, s],
      ],
    ]);
const records = [];
let failed = 0;
for (const slug of slugs) {
  const filename = path.join(root, slug + ".json.gz");
  if (!fs.existsSync(filename)) {
    records.push({ slug, error: "Dataset not yet downloaded" });
    failed++;
    continue;
  }
  const source = JSON.parse(
      require("zlib").gunzipSync(fs.readFileSync(filename)).toString(),
    ),
    [w, s, e, n] = source.bbox,
    area = poly(w, s, e, n),
    data = {
      roads: source.roads,
      buildings: source.buildings,
      aoi: fc([area]),
    },
    options = {
      allBuildings: true,
      speed: 0.9,
      minutes: 20,
      margin: 0,
      mode: "automatico",
      peoplePerBuilding: 3,
      enforceCapacity: false,
    };
  const record = {
    slug,
    city: source.city,
    source: source.source,
    osm_timestamp: source.osm_timestamp,
    data_type:
      "Real OSM roads and building geometries; all destinations, flood, blocks and capacities in this test are synthetic",
    input_roads: data.roads.features.length,
    input_buildings: data.buildings.features.length,
    cases: [],
  };
  function run(name, fn) {
    const start = Date.now();
    try {
      const info = fn();
      record.cases.push({
        name,
        pass: true,
        elapsed_ms: Date.now() - start,
        ...info,
      });
    } catch (err) {
      failed++;
      record.cases.push({ name, pass: false, error: err.stack });
    }
  }
  let automatic, base;
  run("real roads/buildings, automatic baseline", () => {
    automatic = E.plan(structuredClone(data), options);
    assert(automatic.summary.required > 0);
    assert(automatic.summary.assigned > 0);
    return {
      summary: automatic.summary,
      destinations: automatic.destinations.length,
    };
  });
  if (automatic) {
    const dest = automatic.destinations[0];
    base = {
      ...data,
      destinations: fc([
        f("Point", dest.p, {
          nome: "Destino sintético de teste",
          capacidade: 10000,
          tipo: "ponto_de_encontro",
        }),
      ]),
    };
    run(
      "manual destination with synthetic large capacity and route consistency",
      () => {
        const r = E.plan(structuredClone(base), {
          ...options,
          mode: "manual",
          enforceCapacity: true,
        });
        assert(r.summary.assigned > 0);
        for (let i = 0; i < r.buildings.length; i++) {
          const b = r.buildings[i];
          if (b.destination == null) continue;
          const route = E.route(r, i),
            length = route.reduce(
              (sum, p, j) => sum + (j ? E.distance(route[j - 1], p) : 0),
              0,
            );
          assert(Math.abs(length / 0.9 - b.seconds) < 1e-5);
          assert(route.every((p) => E.inside(p, area.geometry)));
        }
        return { summary: r.summary };
      },
    );
    run("shelter capacity zero", () => {
      const d = structuredClone(base);
      d.destinations.features[0].properties.capacidade = 0;
      const r = E.plan(d, {
        ...options,
        mode: "manual",
        enforceCapacity: true,
      });
      assert.equal(r.summary.assigned, 0);
      return { summary: r.summary };
    });
    run("capacity nine with occupancy six", () => {
      const d = structuredClone(base);
      Object.assign(d.destinations.features[0].properties, {
        capacidade: 9,
        ocupacao: 6,
      });
      const r = E.plan(d, {
        ...options,
        mode: "manual",
        enforceCapacity: true,
      });
      assert(r.summary.served <= 3);
      for (const dest of r.destinations)
        assert(dest.used + dest.occupancy <= dest.capacity);
      return { summary: r.summary };
    });
    run("unknown capacity in strict mode", () => {
      const d = structuredClone(base);
      delete d.destinations.features[0].properties.capacidade;
      const r = E.plan(d, {
        ...options,
        mode: "manual",
        enforceCapacity: true,
      });
      assert.equal(r.summary.assigned, 0);
      return { summary: r.summary };
    });
    run("all area blocked by synthetic polygon", () => {
      const d = structuredClone(base);
      d.blocks = fc([poly(w - 0.001, s - 0.001, e + 0.001, n + 0.001)]);
      const r = E.plan(d, { ...options, mode: "manual" });
      assert.equal(r.summary.assigned, 0);
      assert.equal(r.available.length, 0);
      return { summary: r.summary, removed: r.removed };
    });
    run("one-minute evacuation deadline", () => {
      const r = E.plan(structuredClone(base), {
        ...options,
        mode: "manual",
        minutes: 1,
      });
      for (const b of r.buildings)
        if (b.destination != null) assert(b.seconds <= 60);
      return { summary: r.summary };
    });
    run("eligible area away from destination", () => {
      const d = structuredClone(base);
      d.eligible = fc([poly(w - 0.02, s - 0.02, w - 0.01, s - 0.01)]);
      const r = E.plan(d, { ...options, mode: "manual" });
      assert.equal(r.summary.assigned, 0);
      assert.equal(r.rejected.length, 1);
      return { summary: r.summary };
    });
    run("synthetic flood half-area, flooded roads unavailable", () => {
      const d = structuredClone(base);
      d.flood = fc([poly(w, s, (w + e) / 2, n)]);
      const r = E.plan(d, {
        ...options,
        mode: "manual",
        allBuildings: false,
        excludeFlood: true,
      });
      for (let i = 0; i < r.buildings.length; i++) {
        const route = E.route(r, i);
        for (let j = 1; j < route.length; j++)
          assert(!E.hit(route[j - 1], route[j], d.flood.features));
      }
      return { summary: r.summary, removed: r.removed };
    });
  }
  records.push(record);
  console.log(
    source.city,
    record.cases.filter((c) => c.pass).length + "/" + record.cases.length,
    "passed",
  );
}
const report = {
  checked_at: new Date().toISOString(),
  data_note: "Real OSM samples, not city-wide or hydrological validation",
  failed,
  cities: records,
};
fs.writeFileSync(
  process.env.BRASIL_OSM_REPORT ||
    path.join(require("os").tmpdir(), "previne-brasil-osm-report.json"),
  JSON.stringify(report, null, 2),
);
console.log(
  "TOTAL",
  records.reduce((s, c) => s + (c.cases?.length || 0), 0),
  "cases; failures",
  failed,
);
process.exitCode = failed ? 1 : 0;
