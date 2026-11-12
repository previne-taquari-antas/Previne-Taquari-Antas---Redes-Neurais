/* Synthetic scenarios at Brazilian coordinates. These are NOT municipal risk maps,
   actual streets, shelter registrations, observed flood outlines or validation of safety. */
const { test, after } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const E = require("../assets/js/cenario_engine.js");
const cities = [
  { name: "Boa Vista", region: "Norte", lon: -60.6733, lat: 2.8235 },
  { name: "Manaus", region: "Norte", lon: -60.0217, lat: -3.119 },
  { name: "Recife", region: "Nordeste", lon: -34.877, lat: -8.0476 },
  { name: "Brasília", region: "Centro-Oeste", lon: -47.8825, lat: -15.7942 },
  { name: "São Paulo", region: "Sudeste", lon: -46.6333, lat: -23.5505 },
  { name: "Curitiba", region: "Sul", lon: -49.2733, lat: -25.4284 },
];
const feature = (type, coordinates, properties = {}) => ({
  type: "Feature",
  properties,
  geometry: { type, coordinates },
});
const fc = (features) => ({ type: "FeatureCollection", features });
const opts = {
  allBuildings: true,
  speed: 1,
  minutes: 20,
  margin: 0,
  mode: "manual",
  peoplePerBuilding: 3,
  snapMax: 150,
  enforceCapacity: false,
};
const evidence = [];
function caseTest(city, name, fn) {
  test(`${city.name} · synthetic · ${name}`, () => {
    const row = {
      city: city.name,
      region: city.region,
      center: [city.lon, city.lat],
      scenario: name,
      data_kind: "synthetic",
      pass: false,
    };
    try {
      const detail = fn();
      row.pass = true;
      if (detail) row.detail = detail;
    } catch (error) {
      row.error = error.message;
      throw error;
    } finally {
      evidence.push(row);
    }
  });
}
function p(c, x, y) {
  return [
    c.lon + x / (111195 * Math.cos((c.lat * Math.PI) / 180)),
    c.lat + y / 111195,
  ];
}
function rect(c, x1, y1, x2, y2) {
  return feature("Polygon", [
    [p(c, x1, y1), p(c, x2, y1), p(c, x2, y2), p(c, x1, y2), p(c, x1, y1)],
  ]);
}
function base(c) {
  return {
    roads: fc(
      [0, 200, 400].flatMap((v) => [
        feature("LineString", [p(c, 0, v), p(c, 400, v)], {
          highway: "residential",
        }),
        feature("LineString", [p(c, v, 0), p(c, v, 400)], {
          highway: "residential",
        }),
      ]),
    ),
    buildings: fc(
      [
        [0, 0, 1],
        [0, 200, 2],
        [200, 0, 4],
      ].map(([x, y, n], i) =>
        feature("Point", p(c, x, y), { id: `${c.name}-${i}`, pessoas: n }),
      ),
    ),
    destinations: fc([
      feature("Point", p(c, 400, 400), {
        nome: "Synthetic shelter",
        tipo: "abrigo",
        capacidade: 100,
        ocupacao: 0,
      }),
    ]),
  };
}
function connected(g, a, b) {
  const seen = new Set([a]);
  for (let changed = true; changed; ) {
    changed = false;
    for (const [x, y] of g.edges)
      if (seen.has(x) !== seen.has(y)) {
        seen.add(x);
        seen.add(y);
        changed = true;
      }
  }
  return seen.has(b);
}
for (const c of cities) {
  caseTest(c, "baseline and route metric consistency", () => {
    const r = E.plan(base(c), opts);
    assert.equal(r.summary.assigned, 3);
    assert.equal(r.summary.served, 7);
    for (let i = 0; i < r.buildings.length; i++) {
      const path = E.route(r, i),
        length = path.reduce(
          (sum, q, j) => (j ? sum + E.distance(path[j - 1], q) : sum),
          0,
        );
      assert(Math.abs(length - r.buildings[i].seconds) < 1e-6);
      assert(!r.buildings[i].estimated);
    }
    return {
      served: r.summary.served,
      max_seconds: Math.max(...r.buildings.map((b) => b.seconds)),
    };
  });
  caseTest(c, "short time leaves unreachable demand explicit", () => {
    const r = E.plan(base(c), { ...opts, minutes: 5 });
    assert.equal(r.summary.assigned, 0);
    assert.equal(r.summary.unassigned, 3);
    assert(r.buildings.every((b) => b.reason.includes("tempo")));
  });
  caseTest(c, "closed shelter represented by zero capacity", () => {
    const d = base(c);
    d.destinations.features[0].properties.capacidade = 0;
    const r = E.plan(d, opts);
    assert.equal(r.summary.served, 0);
    assert.equal(r.destinations[0].used, 0);
  });
  caseTest(
    c,
    "occupied shelter respects remaining places and household groups",
    () => {
      const d = base(c);
      d.destinations.features[0].properties.capacidade = 7;
      d.destinations.features[0].properties.ocupacao = 5;
      const r = E.plan(d, opts);
      assert(r.summary.served <= 2);
      assert(r.destinations[0].used + 5 <= 7);
      assert(r.buildings.every((b) => b.destination == null || b.people <= 2));
    },
  );
  caseTest(c, "unknown capacity is rejected in strict capacity mode", () => {
    const d = base(c);
    delete d.destinations.features[0].properties.capacidade;
    const r = E.plan(d, { ...opts, enforceCapacity: true });
    assert.equal(r.summary.assigned, 0);
  });
  caseTest(c, "unknown capacity remains explicit when allowed", () => {
    const d = base(c);
    delete d.destinations.features[0].properties.capacidade;
    const r = E.plan(d, opts);
    assert.equal(r.summary.assigned, 3);
    assert.equal(r.destinations[0].capacity, null);
  });
  caseTest(
    c,
    "observed-vs-future road availability hypothesis changes reachability",
    () => {
      const d = base(c);
      d.flood = fc([rect(c, -30, -30, 80, 280)]);
      const before = E.plan(structuredClone(d), {
          ...opts,
          allBuildings: false,
        }),
        during = E.plan(structuredClone(d), {
          ...opts,
          allBuildings: false,
          excludeFlood: true,
        });
      assert.equal(before.summary.required, 2);
      assert.equal(before.summary.assigned, 2);
      assert.equal(during.summary.assigned, 0);
      return {
        before: before.summary.assigned,
        already_inundated: during.summary.assigned,
      };
    },
  );
  caseTest(
    c,
    "multiple obstructions preserve an available alternative route",
    () => {
      const d = base(c);
      d.blocks = fc([
        feature("Point", p(c, 200, 0)),
        feature("LineString", [p(c, 180, 180), p(c, 220, 220)]),
      ]);
      const r = E.plan(d, opts);
      assert(r.summary.assigned > 0);
      for (let i = 0; i < r.buildings.length; i++) {
        const path = E.route(r, i);
        for (let j = 1; j < path.length; j++)
          assert(!E.hit(path[j - 1], path[j], d.blocks.features));
      }
    },
  );
  caseTest(c, "AOI hole cannot be crossed as a shortcut", () => {
    const d = base(c);
    d.aoi = fc([
      feature("Polygon", [
        rect(c, -50, -50, 450, 450).geometry.coordinates[0],
        rect(c, 170, 170, 230, 230).geometry.coordinates[0],
      ]),
    ]);
    const r = E.plan(d, opts);
    assert.equal(r.summary.assigned, 3);
    const hole = rect(c, 170, 170, 230, 230);
    for (let i = 0; i < 3; i++) {
      const path = E.route(r, i);
      for (let j = 1; j < path.length; j++)
        assert(!E.hit(path[j - 1], path[j], [hole]));
    }
  });
  caseTest(
    c,
    "two disjoint AOI islands do not gain a fictitious crossing",
    () => {
      const d = base(c);
      d.aoi = fc([rect(c, -50, -50, 80, 450), rect(c, 320, -50, 450, 450)]);
      const r = E.plan(d, opts);
      assert.equal(r.summary.required, 2);
      assert.equal(r.summary.assigned, 0);
    },
  );
  caseTest(
    c,
    "eligibility polygon restricts every automatic suggestion",
    () => {
      const d = base(c);
      d.eligible = fc([rect(c, 320, 320, 450, 450)]);
      const r = E.plan(d, { ...opts, mode: "automatico" });
      assert(r.destinations.length);
      assert(
        r.destinations.every((v) =>
          d.eligible.features.some((f) => E.inside(v.p, f.geometry)),
        ),
      );
    },
  );
  caseTest(c, "narrow area preserves a crossing road", () => {
    const d = {
      roads: fc([feature("LineString", [p(c, -200, 0), p(c, 200, 0)])]),
      buildings: fc([feature("Point", p(c, 0, 0), { pessoas: 1 })]),
      destinations: fc([feature("Point", p(c, 5, 0), { capacidade: 1 })]),
      aoi: fc([rect(c, -10, -10, 10, 10)]),
    };
    assert.equal(E.plan(d, opts).summary.assigned, 1);
  });
  caseTest(c, "no road inside area leaves demand explicitly unserved", () => {
    const d = base(c);
    d.aoi = fc([rect(c, 80, 80, 120, 120)]);
    d.buildings = fc([feature("Point", p(c, 100, 100), { pessoas: 2 })]);
    const r = E.plan(d, opts);
    assert.equal(r.summary.required, 1);
    assert.equal(r.summary.assigned, 0);
    assert.match(r.buildings[0].reason, /rede/);
  });
  caseTest(
    c,
    "missing flood rejected unless all-buildings scope is explicit",
    () => {
      assert.throws(
        () => E.plan(base(c), { ...opts, allBuildings: false }),
        /mancha/,
      );
      assert.equal(E.plan(base(c), opts).summary.required, 3);
    },
  );
  caseTest(
    c,
    "projected metric coordinates are rejected before replacing a base",
    () => {
      assert.throws(
        () =>
          E.validate(fc([feature("Point", [500000, 9200000])]), "buildings"),
        /WGS84/,
      );
    },
  );
  caseTest(
    c,
    "bridge approach without explicit level remains connected",
    () => {
      const g = E.graph(
        [
          feature("LineString", [p(c, 0, 0), p(c, 200, 0)]),
          feature("LineString", [p(c, 200, 0), p(c, 400, 0)], {
            bridge: "yes",
          }),
        ],
        {},
      );
      assert(connected(g, 0, g.nodes.length - 1));
    },
  );
}
const c = cities[1];
caseTest(
  c,
  "coincident endpoints at explicit different levels must not create a ramp",
  () => {
    const g = E.graph(
      [
        feature("LineString", [p(c, 0, 0), p(c, 200, 0)], { layer: 0 }),
        feature("LineString", [p(c, 200, 0), p(c, 200, 200)], {
          layer: 1,
          bridge: "yes",
        }),
      ],
      {},
    );
    assert(
      !connected(g, 0, g.nodes.length - 1),
      "Ground road and elevated endpoint were merged without evidence of a ramp",
    );
  },
);
caseTest(
  c,
  "explicit shared OSM node may connect a bridge approach between levels",
  () => {
    const g = E.graph(
      [
        feature("LineString", [p(c, 0, 0), p(c, 200, 0)], {
          layer: 0,
          node_ids: [11, 12],
        }),
        feature("LineString", [p(c, 200, 0), p(c, 200, 200)], {
          layer: 1,
          bridge: "yes",
          node_ids: [12, 13],
        }),
      ],
      {},
    );
    assert(connected(g, 0, g.nodes.length - 1));
  },
);
caseTest(
  c,
  "different OSM nodes at different levels must stay disconnected",
  () => {
    const g = E.graph(
      [
        feature("LineString", [p(c, 0, 0), p(c, 200, 0)], {
          layer: 0,
          node_ids: [11, 12],
        }),
        feature("LineString", [p(c, 200, 0), p(c, 200, 200)], {
          layer: 1,
          bridge: "yes",
          node_ids: [99, 13],
        }),
      ],
      {},
    );
    assert(!connected(g, 0, g.nodes.length - 1));
  },
);
caseTest(
  c,
  "outside-area roads must not exhaust the in-area node budget",
  () => {
    const d = {
      roads: fc([
        feature("LineString", [p(c, -100, 0), p(c, 100, 0)]),
        ...Array.from({ length: 32 }, (_, i) =>
          feature("LineString", [
            p(c, 2000, 1000 + i * 100),
            p(c, 82000, 1000 + i * 100),
          ]),
        ),
      ]),
      buildings: fc([feature("Point", p(c, 0, 0), { pessoas: 1 })]),
      destinations: fc([feature("Point", p(c, 5, 0), { capacidade: 1 })]),
      aoi: fc([rect(c, -20, -20, 20, 20)]),
    };
    assert.equal(E.plan(d, opts).summary.assigned, 1);
  },
);
caseTest(c, "polygon hole outside its exterior ring is rejected", () => {
  const polygon = feature("Polygon", [
    rect(c, 0, 0, 100, 100).geometry.coordinates[0],
    rect(c, 200, 200, 250, 250).geometry.coordinates[0],
  ]);
  assert.throws(() => E.validate(polygon, "aoi"));
});
caseTest(c, "polygon hole crossing its exterior ring is rejected", () => {
  const polygon = feature("Polygon", [
    rect(c, 0, 0, 100, 100).geometry.coordinates[0],
    rect(c, 80, 20, 120, 80).geometry.coordinates[0],
  ]);
  assert.throws(() => E.validate(polygon, "aoi"));
});
caseTest(c, "intersecting polygon holes are rejected", () => {
  const polygon = feature("Polygon", [
    rect(c, 0, 0, 100, 100).geometry.coordinates[0],
    rect(c, 20, 20, 60, 60).geometry.coordinates[0],
    rect(c, 40, 40, 80, 80).geometry.coordinates[0],
  ]);
  assert.throws(() => E.validate(polygon, "aoi"));
});
caseTest(
  c,
  "automatic mode retains the sole eligible node when a manual point occupies it",
  () => {
    const d = {
      roads: fc([feature("LineString", [p(c, 0, 0), p(c, 200, 0)])]),
      buildings: fc([feature("Point", p(c, 0, 0), { pessoas: 1 })]),
      destinations: fc([feature("Point", p(c, 200, 0), { capacidade: 1 })]),
      eligible: fc([rect(c, 195, -5, 205, 5)]),
    };
    const withoutManual = structuredClone(d);
    withoutManual.destinations = fc([]);
    const expected = E.plan(withoutManual, { ...opts, mode: "automatico" }),
      actual = E.plan(d, { ...opts, mode: "automatico" });
    assert.equal(expected.summary.assigned, 1);
    assert.equal(actual.summary.assigned, 1);
    assert(actual.destinations.some((v) => v.origin === "algoritmo"));
  },
);
after(() => {
  const reportPath=process.env.BRASIL_MOTOR_REPORT||require('path').join(require('os').tmpdir(),'previne-brasil-motor.json');
  fs.mkdirSync(require('path').dirname(reportPath), { recursive: true });
  fs.writeFileSync(
    reportPath,
    JSON.stringify(
      {
        checked_at_utc: new Date().toISOString(),
        data_kind: "synthetic",
        not_real_municipal_risk_validation: true,
        cities,
        tests: evidence,
        summary: {
          total: evidence.length,
          passed: evidence.filter((x) => x.pass).length,
          failed: evidence.filter((x) => !x.pass).length,
        },
      },
      null,
      2,
    ),
  );
});
