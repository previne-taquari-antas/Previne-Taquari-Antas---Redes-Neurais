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
  await page
    .getByRole("button", { name: "Carregar exemplo: Santa Tereza" })
    .click();
  await page.waitForFunction(() =>
    document.getElementById("status").textContent.includes("Exemplo carregado"),
  );
  await page.getByRole("button", { name: "Calcular cenário e rotas" }).click();
  await page.waitForFunction(
    () => !document.getElementById("calculate").disabled,
    { timeout: 120000 },
  );
  console.log(
    "example",
    await page.locator("#status").innerText(),
    await page.locator("#results").innerText(),
  );
  assert.match(
    await page.locator("#status").innerText(),
    /Cenário calculado/,
    "reference example must calculate successfully",
  );
  const f = (type, coordinates, properties = {}) => ({
      type: "Feature",
      geometry: { type, coordinates },
      properties,
    }),
    fc = (features) => ({ type: "FeatureCollection", features });
  const scene = {
    schema: "previne-municipal-v1",
    options: {
      municipality: "Município teste",
      allBuildings: true,
      mode: "manual",
      margin: 0,
      roadTypes: "residential",
      minutes: 20,
      speed: 0.9,
      peoplePerBuilding: 3,
      enforceCapacity: false,
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
      buildings: fc([f("Point", [0, 0]), f("Point", [0.001, 0])]),
      destinations: fc([
        f("Point", [0.004, 0], {
          nome: "Abrigo municipal",
          tipo: "abrigo",
          capacidade: 3,
        }),
      ]),
    },
  };
  await page.locator("#load").setInputFiles({
    name: "municipio.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(scene)),
  });
  await page.waitForFunction(() =>
    document
      .getElementById("status")
      .textContent.includes("Predefinições reabertas"),
  );
  await page.locator("#calculate").click();
  await page.waitForFunction(
    () => !document.getElementById("calculate").disabled,
  );
  assert.match(
    await page.locator("#results").innerText(),
    /1 de 2 edificações atendidas/,
  );
  const dlPromise = page.waitForEvent("download");
  await page.locator("#save").click();
  const dl = await dlPromise;
  const saved = JSON.parse(fs.readFileSync(await dl.path(), "utf8"));
  assert.equal(saved.options.municipality, "Município teste");
  assert.equal(saved.layers.destinations.features[0].properties.capacidade, 3);
  await page.locator("#minutes").fill("1");
  await page.locator("#minutes").blur();
  assert(await page.locator("#csv").isDisabled());
  assert.match(await page.locator("#results").innerText(), /Calcule novamente/);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    false,
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .getByText("Modelo de elevação e geração HAND", { exact: true })
    .click();
  const T = require("../../assets/js/cenario_terreno.js");
  const terrain = T.writeGeoTIFF({
    width: 9,
    height: 9,
    bbox: [0, 0, 0.01, 0.01],
    values: Array.from(
      { length: 81 },
      (_, i) => Math.abs((i % 9) - 4) * 3 + (8 - Math.floor(i / 9)) + 0.25,
    ),
  });
  await page
    .locator("#terrainFile")
    .setInputFiles({
      name: "terreno.tif",
      mimeType: "image/tiff",
      buffer: Buffer.from(terrain),
    });
  await page.waitForFunction(() =>
    document.getElementById("terrainInfo").textContent.includes("9 × 9"),
  );
  await page.locator("#drainArea").fill("0.01");
  await page.locator("#generateHand").click();
  await page.waitForFunction(
    () => !document.getElementById("generateHand").disabled,
  );
  assert.match(await page.locator("#status").innerText(), /HAND gerado/);
  const terrainDownload = page.waitForEvent("download");
  await page.locator("#downloadTerrain").click();
  const terrainFile = await terrainDownload;
  const { fromArrayBuffer } = await import("geotiff");
  const bytes = fs.readFileSync(await terrainFile.path());
  const tif = await fromArrayBuffer(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
  );
  const image = await tif.getImage();
  const raster = await image.readRasters();
  assert.equal(raster[0][0], 20.25);
  assert.equal(image.getGeoKeys().GeographicTypeGeoKey, 4326);
  assert.deepEqual(errors, []);
  console.log(
    "UI: example, custom municipality, capacity, save, invalidation, mobile passed",
  );
  await browser.close();
  server.close();
})().catch((e) => {
  console.error(e);
  server.close();
  process.exit(1);
});
