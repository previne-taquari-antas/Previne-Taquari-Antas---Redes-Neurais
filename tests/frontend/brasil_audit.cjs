/* Browser audit. All city-positioned features below are SYNTHETIC.
 * Default: start an ephemeral local HTTP server and use installed CDN dependencies.
 * Published: BRASIL_ORIGIN=https://previne-taquari-antas.github.io/Previne-Taquari-Antas---Redes-Neurais node tests/frontend/brasil_audit.cjs
 * Optional: BRASIL_REPORT=/absolute/path/report.json
 */
const { chromium } = require("playwright");
const fs = require("fs"),
  assert = require("assert/strict"),
  path = require("path"),
  http = require("http");
let URL = process.env.BRASIL_ORIGIN
  ? process.env.BRASIL_ORIGIN.replace(/\/$/, "") +
    "/cenario_municipal.html?v=brasil-audit"
  : "";
const local =
  !URL || /^http:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\//.test(URL);
const out =
  process.env.BRASIL_REPORT || path.join(require('os').tmpdir(), "previne-brasil-ui-report.json");
const cities = [
  ["Manaus", "Norte", -60.0217, -3.119],
  ["Recife", "Nordeste", -34.877, -8.0476],
  ["Brasília", "Centro-Oeste", -47.8825, -15.7942],
  ["São Paulo", "Sudeste", -46.6333, -23.5505],
  ["Curitiba", "Sul", -49.2733, -25.4284],
  ["Boa Vista", "Norte", -60.6753, 2.8235],
];
const feature = (type, coordinates, properties = {}) => ({
  type: "Feature",
  geometry: { type, coordinates },
  properties,
});
const fc = (features) => ({ type: "FeatureCollection", features });
// Small uncompressed ZIP writer keeps generated SHP fixtures self-contained in CI.
class StoredZip {
  constructor() {
    this.files = [];
  }
  file(name, data) {
    this.files.push({
      name: Buffer.from(name),
      data: Buffer.isBuffer(data) ? data : Buffer.from(data),
    });
  }
  generateAsync() {
    const chunks = [],
      central = [];
    let offset = 0;
    for (const { name, data } of this.files) {
      let crc = 0xffffffff;
      for (const byte of data) {
        crc ^= byte;
        for (let k = 0; k < 8; k++)
          crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
      }
      crc = (crc ^ 0xffffffff) >>> 0;
      const h = Buffer.alloc(30);
      h.writeUInt32LE(0x04034b50);
      h.writeUInt16LE(20, 4);
      h.writeUInt32LE(crc, 14);
      h.writeUInt32LE(data.length, 18);
      h.writeUInt32LE(data.length, 22);
      h.writeUInt16LE(name.length, 26);
      chunks.push(h, name, data);
      const c = Buffer.alloc(46);
      c.writeUInt32LE(0x02014b50);
      c.writeUInt16LE(20, 4);
      c.writeUInt16LE(20, 6);
      c.writeUInt32LE(crc, 16);
      c.writeUInt32LE(data.length, 20);
      c.writeUInt32LE(data.length, 24);
      c.writeUInt16LE(name.length, 28);
      c.writeUInt32LE(offset, 42);
      central.push(c, name);
      offset += h.length + name.length + data.length;
    }
    const directory = Buffer.concat(central),
      end = Buffer.alloc(22);
    end.writeUInt32LE(0x06054b50);
    end.writeUInt16LE(this.files.length, 8);
    end.writeUInt16LE(this.files.length, 10);
    end.writeUInt32LE(directory.length, 12);
    end.writeUInt32LE(offset, 16);
    return Buffer.concat([...chunks, directory, end]);
  }
}
async function shapeZip(layer) {
  const zip = new StoredZip(),
    line = layer.features[0].geometry.type === "LineString",
    shapeType = line ? 3 : 1;
  const all = layer.features.flatMap((f) =>
      line ? f.geometry.coordinates : [f.geometry.coordinates],
    ),
    bounds = [
      Math.min(...all.map((p) => p[0])),
      Math.min(...all.map((p) => p[1])),
      Math.max(...all.map((p) => p[0])),
      Math.max(...all.map((p) => p[1])),
    ];
  const header = (size) => {
    const b = Buffer.alloc(100);
    b.writeInt32BE(9994, 0);
    b.writeInt32BE(size / 2, 24);
    b.writeInt32LE(1000, 28);
    b.writeInt32LE(shapeType, 32);
    bounds.forEach((x, i) => b.writeDoubleLE(x, 36 + i * 8));
    return b;
  };
  let offset = 100;
  const records = [],
    indices = [];
  layer.features.forEach((f, i) => {
    const points = line ? f.geometry.coordinates : [f.geometry.coordinates],
      b = Buffer.alloc(line ? 48 + points.length * 16 : 20);
    b.writeInt32LE(shapeType);
    if (line) {
      const bb = [
        Math.min(...points.map((p) => p[0])),
        Math.min(...points.map((p) => p[1])),
        Math.max(...points.map((p) => p[0])),
        Math.max(...points.map((p) => p[1])),
      ];
      bb.forEach((x, j) => b.writeDoubleLE(x, 4 + j * 8));
      b.writeInt32LE(1, 36);
      b.writeInt32LE(points.length, 40);
      points.forEach((p, j) => {
        b.writeDoubleLE(p[0], 48 + j * 16);
        b.writeDoubleLE(p[1], 56 + j * 16);
      });
    } else {
      b.writeDoubleLE(points[0][0], 4);
      b.writeDoubleLE(points[0][1], 12);
    }
    const rh = Buffer.alloc(8);
    rh.writeInt32BE(i + 1);
    rh.writeInt32BE(b.length / 2, 4);
    records.push(rh, b);
    const idx = Buffer.alloc(8);
    idx.writeInt32BE(offset / 2);
    idx.writeInt32BE(b.length / 2, 4);
    indices.push(idx);
    offset += b.length + 8;
  });
  zip.file("layer.shp", Buffer.concat([header(offset), ...records]));
  zip.file(
    "layer.shx",
    Buffer.concat([header(100 + indices.length * 8), ...indices]),
  );
  const keys = Object.keys(layer.features[0].properties),
    widths = keys.map((k) =>
      typeof layer.features[0].properties[k] === "number" ? 10 : 64,
    ),
    hlen = 33 + keys.length * 32,
    rlen = 1 + widths.reduce((a, b) => a + b, 0),
    dbf = Buffer.alloc(hlen + rlen * layer.features.length + 1, 32);
  dbf[0] = 3;
  dbf[1] = 126;
  dbf[2] = 11;
  dbf[3] = 7;
  dbf.writeUInt32LE(layer.features.length, 4);
  dbf.writeUInt16LE(hlen, 8);
  dbf.writeUInt16LE(rlen, 10);
  dbf.fill(0, 12, 32);
  keys.forEach((k, i) => {
    const at = 32 + i * 32;
    dbf.fill(0, at, at + 32);
    dbf.write(k, at, 10, "ascii");
    dbf[at + 11] =
      typeof layer.features[0].properties[k] === "number" ? 78 : 67;
    dbf[at + 16] = widths[i];
  });
  dbf[hlen - 1] = 13;
  layer.features.forEach((f, i) => {
    let at = hlen + i * rlen + 1;
    keys.forEach((k, j) => {
      const value = String(f.properties[k]);
      dbf.write(
        typeof f.properties[k] === "number" ? value.padStart(widths[j]) : value,
        at,
        widths[j],
        "utf8",
      );
      at += widths[j];
    });
  });
  dbf[dbf.length - 1] = 26;
  zip.file("layer.dbf", dbf);
  zip.file("layer.cpg", "UTF-8");
  zip.file(
    "layer.prj",
    'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]',
  );
  return zip.generateAsync({ type: "nodebuffer" });
}
function scene(c) {
  const [name, region, lon, lat] = c,
    p = (x, y = 0) => [
      lon + x / (111320 * Math.cos((lat * Math.PI) / 180)),
      lat + y / 111320,
    ];
  return {
    data: {
      schema: "previne-municipal-v1",
      options: {
        municipality: `TESTE SINTÉTICO ${name} ${region}`,
        allBuildings: true,
        mode: "manual",
        margin: 0,
        roadTypes: "residential",
        minutes: 20,
        speed: 1,
        peoplePerBuilding: 3,
        enforceCapacity: false,
        excludeFlood: false,
      },
      layers: {
        roads: fc([
          feature("LineString", [p(0), p(600)], { highway: "residential" }),
        ]),
        buildings: fc([
          feature("Point", p(0), { pessoas: 3, id: "H1" }),
          feature("Point", p(100), { pessoas: 3, id: "H2" }),
        ]),
        destinations: fc([
          feature("Point", p(600), {
            nome: `Abrigo sintético ${name}`,
            tipo: "abrigo",
            capacidade: 10,
            ocupacao: 0,
          }),
        ]),
      },
      sources: {
        roads: "Rede sintética de teste, sem validade operacional",
        buildings: "Pontos sintéticos de teste",
        destinations: "Abrigo sintético de teste",
      },
    },
    p,
  };
}
(async () => {
  let server;
  if (!URL) {
    const root = path.resolve(__dirname, "../..");
    server = http.createServer((req, res) => {
      const file = path.resolve(
        root,
        "." + decodeURIComponent(req.url.split("?")[0]),
      );
      if (
        !file.startsWith(root + path.sep) ||
        !fs.existsSync(file) ||
        !fs.statSync(file).isFile()
      ) {
        res.statusCode = 404;
        return res.end();
      }
      res.setHeader(
        "Content-Type",
        {
          ".html": "text/html",
          ".js": "text/javascript",
          ".json": "application/json",
          ".css": "text/css",
        }[path.extname(file)] || "application/octet-stream",
      );
      res.end(fs.readFileSync(file));
    });
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    URL =
      "http://127.0.0.1:" +
      server.address().port +
      "/cenario_municipal.html?v=brasil-audit";
  }
  const executable =
    process.env.CHROME_PATH ||
    (fs.existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : undefined);
  const report = {
    url: URL,
    startedAt: new Date().toISOString(),
    scope:
      "Cenários inteiramente sintéticos, apenas posicionados nas cidades. Não valida bases locais, topografia ou hidrologia.",
    browser: {
      executable: executable || chromium.executablePath(),
      proxyEnabled: !local && !!process.env.HTTPS_PROXY,
      tlsVerification: true,
      localDependencies: local,
    },
    checks: [],
    pageErrors: [],
    requestFailures: [],
    httpErrors: [],
    consoleErrors: [],
  };
  const browser = await chromium.launch({
    ...(executable ? { executablePath: executable } : {}),
    headless: true,
    args: ["--no-sandbox"],
    ...(!local && process.env.HTTPS_PROXY
      ? { proxy: { server: process.env.HTTPS_PROXY } }
      : {}),
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  page.on("pageerror", (e) => report.pageErrors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") report.consoleErrors.push(m.text());
  });
  page.on("response", (r) => {
    if (r.status() >= 400 && !r.url().includes("tile.openstreetmap.org"))
      report.httpErrors.push({ url: r.url(), status: r.status() });
  });
  page.on("requestfailed", (r) => {
    if (!r.url().includes("tile.openstreetmap.org"))
      report.requestFailures.push({
        url: r.url(),
        error: r.failure()?.errorText,
      });
  });
  if (local) {
    await page.route("https://cdn.jsdelivr.net/npm/**", async (route) => {
      const dependency = route
        .request()
        .url()
        .replace("https://cdn.jsdelivr.net/npm/", "")
        .replace(/@[^/]+/, "");
      await route.fulfill({
        path: require("path").join(__dirname, "node_modules", dependency),
      });
    });
    await page.route("https://tile.openstreetmap.org/**", (route) =>
      route.abort(),
    );
  }
  const persist = () => {
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, JSON.stringify(report, null, 2));
  };
  const check = async (name, fn) => {
    try {
      const evidence = await fn();
      report.checks.push({ name, pass: true, evidence });
      console.log("PASS", name);
    } catch (e) {
      report.checks.push({ name, pass: false, error: e.stack });
      console.log("FAIL", name, e.message);
    }
    persist();
  };
  let serial = 0;
  const load = async (data) => {
    const copy = structuredClone(data);
    copy.options.municipality += " / " + ++serial;
    await page
      .locator("#load")
      .setInputFiles({
        name: "synthetic.json",
        mimeType: "application/json",
        buffer: Buffer.from(JSON.stringify(copy)),
      });
    await page.waitForFunction(
      (name) =>
        document.getElementById("municipality").value === name &&
        !document.getElementById("calculate").disabled,
      copy.options.municipality,
    );
    return copy;
  };
  const calc = async (assigned, required = 2) => {
    await page.locator("#calculate").click();
    await page.waitForFunction(
      () => !document.getElementById("calculate").disabled,
    );
    const text = await page.locator("#results").innerText();
    assert.match(
      text,
      new RegExp(`${assigned} de ${required} edificações atendidas`),
    );
    return text;
  };
  const download = async (id) => {
    const event = page.waitForEvent("download");
    await page.locator("#" + id).click();
    return fs.readFileSync(await (await event).path(), "utf8");
  };
  const upload = async (kind, data, name = "synthetic.geojson") => {
    await page.locator("#layerKind").selectOption(kind);
    await page
      .locator("#source")
      .fill("TESTE SINTÉTICO - sem validade operacional");
    await page
      .locator("#upload")
      .setInputFiles({
        name,
        mimeType: "application/geo+json",
        buffer: Buffer.from(JSON.stringify(data)),
      });
    await page.waitForFunction(() =>
      document
        .getElementById("status")
        .textContent.startsWith("Camada importada:"),
    );
  };
  try {
    await page.goto(URL, { waitUntil: "networkidle", timeout: 60000 });
    await check(
      local
        ? "Local dependencies and municipal interface loaded"
        : "Live CDNs and municipal interface loaded",
      async () => {
        assert(await page.evaluate(() => !!window.L && !!window.shp));
        assert(await page.locator("#calculate").isVisible());
        return {
          leaflet: await page.evaluate(() => L.version),
          title: await page.title(),
        };
      },
    );
    for (const city of cities) {
      const { data, p } = scene(city);
      await check(
        `${city[0]} / ${city[1]}: baseline routes and exports`,
        async () => {
          await load(data);
          const summary = await calc(2);
          const routes = JSON.parse(await download("routes"));
          assert.equal(routes.features.length, 2);
          assert(
            routes.features.every(
              (f) => f.properties.tempo_min > 8 && f.properties.tempo_min < 11,
            ),
          );
          assert(
            routes.features.every((f) =>
              f.geometry.coordinates.every(
                (q) =>
                  Math.abs(q[0] - city[2]) < 0.02 &&
                  Math.abs(q[1] - city[3]) < 0.02,
              ),
            ),
          );
          const csv = await download("csv");
          assert.match(csv, /"H1";"3";"nao"/);
          assert.match(csv, new RegExp(city[0]));
          return {
            summary,
            routeMinutes: routes.features.map((f) => f.properties.tempo_min),
            routeCount: routes.features.length,
            csvRows: csv.trim().split(/\r?\n/).length,
          };
        },
      );
      await check(
        `${city[0]}: shorter evacuation time invalidates and recomputes`,
        async () => {
          await page.locator("#minutes").fill("1");
          assert(await page.locator("#routes").isDisabled());
          const summary = await calc(0);
          await page.locator("#minutes").fill("20");
          await calc(2);
          return summary;
        },
      );
      await check(`${city[0]}: shelter capacity and occupancy`, async () => {
        const nums = page.locator("#destinationList input[type=number]");
        await nums.nth(0).fill("3");
        await nums.nth(0).blur();
        const partial = await calc(1);
        await nums.nth(0).fill("0");
        await nums.nth(0).blur();
        const zero = await calc(0);
        await nums.nth(0).fill("10");
        await nums.nth(1).fill("7");
        await nums.nth(1).blur();
        await calc(1);
        return { partial, zero, occupancy: 7, capacity: 10 };
      });
      await check(
        `${city[0]}: point obstruction disconnects route; clearing restores`,
        async () => {
          await load(data);
          await upload("blocks", fc([feature("Point", p(300))]));
          const blocked = await calc(0);
          await page.locator("#clearBlocks").click();
          await calc(2);
          return blocked;
        },
      );
      await check(
        `${city[0]}: flooded-road exclusion before/after water`,
        async () => {
          await load(data);
          await upload(
            "flood",
            fc([
              feature("Polygon", [
                [p(250, -50), p(350, -50), p(350, 50), p(250, 50), p(250, -50)],
              ]),
            ]),
          );
          await calc(2);
          await page.locator("#excludeFlood").check();
          const after = await calc(0);
          await page.locator("#excludeFlood").uncheck();
          await calc(2);
          return after;
        },
      );
      await check(
        `${city[0]}: save/reopen preserves layers, sources and results`,
        async () => {
          const saved = JSON.parse(await download("save"));
          await load(saved);
          const summary = await calc(2);
          const again = JSON.parse(await download("save"));
          assert.deepEqual(again.layers, saved.layers);
          assert.deepEqual(again.sources, saved.sources);
          for (const key of Object.keys(saved.options).filter(
            (k) => k !== "municipality",
          ))
            assert.deepEqual(again.options[key], saved.options[key], key);
          return { summary, layerKinds: Object.keys(saved.layers) };
        },
      );
    }
    const { data, p } = scene(cities[0]);
    await check(
      "Manaus: no configured destination produces explicit unserved households",
      async () => {
        const d = structuredClone(data);
        d.layers.destinations = fc([]);
        await load(d);
        const summary = await calc(0);
        const csv = await download("csv");
        assert.match(csv, /Sem destino alcançável/);
        return { summary, csv };
      },
    );
    await check(
      "Manaus: disconnected street components remain unreachable",
      async () => {
        const d = structuredClone(data);
        d.layers.roads = fc([
          feature("LineString", [p(0), p(100)], { highway: "residential" }),
          feature("LineString", [p(500), p(600)], { highway: "residential" }),
        ]);
        await load(d);
        return calc(0);
      },
    );
    await check(
      "Manaus: unknown capacity optional/required policy",
      async () => {
        const d = structuredClone(data);
        delete d.layers.destinations.features[0].properties.capacidade;
        await load(d);
        await calc(2);
        await page.locator("#enforceCapacity").check();
        return calc(0);
      },
    );
    await check(
      "Manaus: eligible polygons reject destination outside",
      async () => {
        const d = structuredClone(data);
        d.layers.eligible = fc([
          feature("Polygon", [
            [p(0, -30), p(100, -30), p(100, 30), p(0, 30), p(0, -30)],
          ]),
        ]);
        await load(d);
        return calc(0);
      },
    );
    await check(
      "Manaus: small AOI retains intersecting road segment",
      async () => {
        const d = structuredClone(data);
        d.layers.aoi = fc([
          feature("Polygon", [
            [p(150, -30), p(550, -30), p(550, 30), p(150, 30), p(150, -30)],
          ]),
        ]);
        d.layers.buildings = fc([
          feature("Point", p(200), { pessoas: 3 }),
          feature("Point", p(250), { pessoas: 3 }),
          feature("Point", p(0), { pessoas: 3 }),
        ]);
        d.layers.destinations.features[0].geometry.coordinates = p(500);
        await load(d);
        return calc(2);
      },
    );
    await check(
      "Manaus: street type predefinition excludes residential routes",
      async () => {
        await load(data);
        await page
          .locator("summary")
          .filter({ hasText: "Tipos de vias utilizados" })
          .click();
        await page.locator("#roadTypes").fill("primary");
        await page.locator("#calculate").click();
        await page.waitForFunction(
          () => !document.getElementById("calculate").disabled,
        );
        const status = await page.locator("#status").innerText();
        report.workerErrorDiagnostics = {
          visibleStatus: status,
          cases: await page.evaluate(async (base) => {
            const version = [...document.scripts]
              .filter((s) =>
                /\/cenario_(engine|terreno|municipal)\.js(?:\?|$)/.test(s.src),
              )
              .map((s) => new URL(s.src).searchParams.get("v") || "audit-v2")
              .join("-");
            const url = new URL(
              "assets/js/cenario_worker.js",
              document.baseURI,
            );
            url.searchParams.set("v", version || "audit-v2");
            const results = [];
            for (const kind of ["all-roads-filtered", "negative-capacity"]) {
              const d = structuredClone(base);
              if (kind === "all-roads-filtered")
                d.options.roadTypes = "primary";
              else d.layers.destinations.features[0].properties.capacidade = -1;
              const result = await new Promise((resolve) => {
                const w = new Worker(url);
                w.onmessage = (e) => {
                  resolve({ kind, message: e.data });
                  w.terminate();
                };
                w.onerror = (e) => {
                  e.preventDefault();
                  resolve({
                    kind,
                    error: e.message,
                    filename: e.filename,
                    line: e.lineno,
                    column: e.colno,
                  });
                  w.terminate();
                };
                w.postMessage({
                  id: 55,
                  type: "plan",
                  data: d.layers,
                  options: d.options,
                });
              });
              results.push(result);
            }
            return results;
          }, data),
        };
        assert.match(status, /Nenhuma via utilizável/);
        assert(await page.locator("#routes").isDisabled());
        return status;
      },
    );
    await check(
      "Worker regression: expected errors preserve request id without onerror",
      async () => {
        const cases = report.workerErrorDiagnostics.cases;
        assert.equal(cases.length, 2);
        for (const result of cases) {
          assert.equal(result.error, undefined);
          assert.equal(result.message.id, 55);
          assert.equal(result.message.result, undefined);
        }
        assert.match(cases[0].message.error, /Nenhuma via utilizável/);
        assert.match(cases[1].message.error, /Capacidade\/ocupação inválida/);
        return cases;
      },
    );
    await check("Recife: import three GeoJSON layers separately", async () => {
      const { data } = scene(cities[1]);
      await load(data);
      for (const kind of ["roads", "buildings", "destinations"])
        await upload(kind, data.layers[kind], `${kind}.geojson`);
      const result = await calc(2);
      const saved = JSON.parse(await download("save"));
      assert(
        Object.values(saved.sources).every(
          (s) => s === "TESTE SINTÉTICO - sem validade operacional",
        ),
      );
      return result;
    });
    await check(
      "Recife: actual SHP/SHX/DBF/PRJ ZIP import for streets, buildings and shelter",
      async () => {
        const { data } = scene(cities[1]);
        await load(data);
        for (const kind of ["roads", "buildings", "destinations"]) {
          await page.locator("#layerKind").selectOption(kind);
          await page
            .locator("#upload")
            .setInputFiles({
              name: `${kind}.zip`,
              mimeType: "application/zip",
              buffer: await shapeZip(data.layers[kind]),
            });
          await page.waitForFunction(() =>
            document
              .getElementById("status")
              .textContent.startsWith("Camada importada:"),
          );
        }
        const summary = await calc(2);
        const saved = JSON.parse(await download("save"));
        assert.equal(
          saved.layers.destinations.features[0].properties.capacidade,
          10,
        );
        assert.equal(saved.layers.buildings.features[0].properties.pessoas, 3);
        return {
          summary,
          filesPerZip: [".shp", ".shx", ".dbf", ".prj", ".cpg"],
        };
      },
    );
    for (const city of [cities[1], cities[4]])
      await check(
        `${city[0]} mobile: recompute, export and save/reopen`,
        async () => {
          await page.setViewportSize({ width: 390, height: 844 });
          const { data } = scene(city);
          await load(data);
          await calc(2);
          assert(
            await page.evaluate(
              () => document.documentElement.scrollWidth <= window.innerWidth,
            ),
          );
          const routes = JSON.parse(await download("routes"));
          assert.equal(routes.features.length, 2);
          const saved = JSON.parse(await download("save"));
          await load(saved);
          await calc(2);
          return {
            viewport: { width: 390, height: 844 },
            routeCount: routes.features.length,
            overflow: false,
          };
        },
      );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await check("No browser runtime errors", async () => {
      assert.deepEqual(report.pageErrors, []);
      return report.pageErrors;
    });
  } catch (e) {
    report.fatal = e.stack;
    console.log("FATAL", e.stack);
  }
  report.finishedAt = new Date().toISOString();
  report.passed = report.checks.filter((x) => x.pass).length;
  report.failed = report.checks.filter((x) => !x.pass).length;
  persist();
  await browser.close();
  if (server) await new Promise((resolve) => server.close(resolve));
  console.log(
    JSON.stringify({
      passed: report.passed,
      failed: report.failed,
      fatal: report.fatal,
      report: out,
    }),
  );
  process.exitCode = report.failed || report.fatal ? 1 : 0;
})();
