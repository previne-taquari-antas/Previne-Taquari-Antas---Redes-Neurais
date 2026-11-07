const { chromium } = require("playwright"),
  fs = require("fs"),
  path = require("path"),
  http = require("http"),
  assert = require("assert/strict");
const root = path.resolve(__dirname, "../..");
const server = http.createServer((req, res) => {
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
(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const origin = "http://127.0.0.1:" + server.address().port;
  const browser = await chromium.launch({
    ...(process.env.CHROME_PATH
      ? { executablePath: process.env.CHROME_PATH }
      : {}),
    headless: true,
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    }),
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("https://cdn.jsdelivr.net/npm/**", async (route) => {
    const path = route
      .request()
      .url()
      .replace("https://cdn.jsdelivr.net/npm/", "")
      .replace(/@[^/]+/, "");
    try {
      await route.fulfill({ path: require.resolve(path) });
    } catch (e) {
      await route.continue();
    }
  });
  await page.route("https://tile.openstreetmap.org/**", (r) => r.abort());
  await page.goto(origin + "/cenario_municipal.html");

  const f = (type, coordinates, properties = {}) => ({
      type: "Feature",
      geometry: { type, coordinates },
      properties,
    }),
    fc = (features) => ({ type: "FeatureCollection", features });
  const scene = {
    schema: "previne-municipal-v1",
    options: {
      municipality: "Auditoria de regressões",
      allBuildings: true,
      mode: "manual",
      margin: 0,
      roadTypes: "residential",
      minutes: 20,
      speed: 0.9,
      peoplePerBuilding: 3,
      enforceCapacity: false,
      excludeFlood: false,
    },
    layers: {
      roads: fc([
        f(
          "LineString",
          [
            [0, 0],
            [0.004, 0],
          ],
          { highway: "residential" },
        ),
      ]),
      buildings: fc([
        f("Point", [0, 0], { pessoas: 3 }),
        f("Point", [0.001, 0], { pessoas: 3 }),
      ]),
      destinations: fc([
        f("Point", [0.004, 0], {
          nome: "Abrigo teste",
          tipo: "abrigo",
          capacidade: 10,
          ocupacao: 0,
        }),
      ]),
    },
  };
  const load = async (data) => {
    await page
      .locator("#load")
      .setInputFiles({
        name: "scene.json",
        mimeType: "application/json",
        buffer: Buffer.from(JSON.stringify(data)),
      });
    await page.waitForFunction(() =>
      document
        .getElementById("status")
        .textContent.includes("Predefinições reabertas"),
    );
  };
  const calc = async () => {
    await page.locator("#calculate").click();
    await page.waitForFunction(
      () => !document.getElementById("calculate").disabled,
    );
    return page.locator("#results").innerText();
  };
  const save = async () => {
    const d = page.waitForEvent("download");
    await page.locator("#save").click();
    return JSON.parse(fs.readFileSync(await (await d).path(), "utf8"));
  };
  await load(scene);
  assert.match(await calc(), /2 de 2/);
  const capacity = page.locator("#destinationList input[type=number]").first();
  await capacity.fill("-1");
  await capacity.blur();
  assert(await page.locator("#csv").isDisabled());
  let downloaded = false;
  const listener = () => {
    downloaded = true;
  };
  page.on("download", listener);
  await page.locator("#save").click();
  await page.waitForTimeout(100);
  page.off("download", listener);
  assert.equal(downloaded, false);
  await page.locator("#calculate").click();
  assert.match(await page.locator("#status").innerText(), /inválido/);
  await capacity.fill("10");
  await capacity.blur();
  assert.equal(
    (await save()).layers.destinations.features[0].properties.capacidade,
    10,
  );
  await page.locator("#destinationList button").click();
  const empty = await save();
  assert.equal(empty.layers.destinations.features.length, 0);
  await load(empty);
  const withEmpty = structuredClone(scene);
  withEmpty.layers.blocks = fc([]);
  withEmpty.layers.flood = fc([]);
  withEmpty.layers.eligible = fc([]);
  withEmpty.layers.aoi = fc([]);
  await load(withEmpty);
  assert.match(await calc(), /2 de 2/);
  await page.locator("#layerKind").selectOption("buildings");
  await page
    .locator("#upload")
    .setInputFiles({
      name: "bad.geojson",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(fc([f("Point", [[0, 0]])]))),
    });
  await page.waitForFunction(() =>
    document.getElementById("status").textContent.includes("WGS84"),
  );
  assert.equal((await save()).layers.buildings.features.length, 2);
  await load(scene);
  await page.locator("#drawKind").selectOption("blockPoint");
  await page.locator("#draw").click();
  const b = await page.locator("#map").boundingBox();
  await page.mouse.click(b.x + b.width * 0.5, b.y + b.height * 0.5);
  await page.locator(".leaflet-draw-edit-edit").click();
  const marker = page.locator(".leaflet-marker-draggable").last(),
    mb = await marker.boundingBox();
  await page.mouse.move(mb.x + mb.width / 2, mb.y + mb.height / 2);
  await page.mouse.down();
  await page.mouse.move(mb.x + mb.width / 2 + 45, mb.y + mb.height / 2 + 25, {
    steps: 8,
  });
  await page.mouse.up();
  await page
    .locator(".leaflet-draw-actions a")
    .filter({ hasText: "Save" })
    .click();
  await page.waitForTimeout(100);
  assert.deepEqual(errors, []);
  assert.equal((await save()).layers.blocks.features.length, 1);
  await page.locator(".leaflet-draw-edit-remove").click();
  await page
    .locator(".leaflet-overlay-pane path")
    .last()
    .click({ force: true });
  await page
    .locator(".leaflet-draw-actions a")
    .filter({ hasText: "Save" })
    .click();
  const deleted = await save();
  assert.equal(deleted.layers.blocks.features.length, 0);
  await load(deleted);
  assert.deepEqual(errors, []);
  console.log(
    "PASS municipal audit: invalid input, save guard, empty layers, malformed GeoJSON, edit/delete toolbar, roundtrip",
  );
  await browser.close();
  server.close();
})().catch((e) => {
  console.error(e);
  server.close();
  process.exit(1);
});
