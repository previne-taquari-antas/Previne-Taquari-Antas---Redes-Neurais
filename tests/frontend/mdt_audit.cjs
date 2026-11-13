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
  const origin = process.env.MDT_ORIGIN || "http://127.0.0.1:" + server.address().port;
  const browser = await chromium.launch({
    ...(process.env.CHROME_PATH
      ? { executablePath: process.env.CHROME_PATH }
      : {}),
    headless: true,
    ...(process.env.MDT_ORIGIN && process.env.HTTPS_PROXY ? {proxy:{server:process.env.HTTPS_PROXY}} : {}),
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    }),
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const workerRequests = [];
  page.on("request", (request) => {
    if (/cenario_(worker|engine|terreno)\.js\?v=/.test(request.url()))
      workerRequests.push(request.url());
  });
  if(!process.env.MDT_ORIGIN) await page.route("https://cdn.jsdelivr.net/npm/**", async (route) => {
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
  if(!process.env.MDT_ORIGIN) await page.route("https://tile.openstreetmap.org/**", (r) => r.abort());
  await page.goto(origin + "/cenario_municipal.html?verify=mdt-20261113");

  const os = require("os"),
    T = require("../../assets/js/cenario_terreno.js");
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "previne-mdt-"));
  await page.evaluate(() => {
    window.terrainReads = [];
    const read = FileReader.prototype.readAsArrayBuffer;
    FileReader.prototype.readAsArrayBuffer = function (blob) {
      window.terrainReads.push(blob.size);
      return read.call(this, blob);
    };
    const full = File.prototype.arrayBuffer;
    File.prototype.arrayBuffer = function () {
      if (/\.tiff?$/i.test(this.name))
        throw Error("Full TIFF read is forbidden in this regression test");
      return full.call(this);
    };
  });
  const first = page.locator("aside > fieldset").first();
  assert.equal(await first.locator("#terrainFile").count(), 1);
  assert.equal(await first.locator("#copernicus").count(), 1);
  assert.equal(await first.locator("#areaUpload").count(), 1);
  assert(await page.locator("#terrainFile").isVisible());
  await page.locator("#copernicus").click();
  await page.waitForFunction(
    () => !document.getElementById("copernicus").disabled,
  );
  assert.match(
    await page.locator("#status").innerText(),
    /área de interesse primeiro/,
  );
  // Small TIFF can be selected immediately, without municipality or area prerequisites.
  const small = T.writeGeoTIFF({
    width: 9,
    height: 9,
    bbox: [0, 0, 0.01, 0.01],
    values: Array(81).fill(42.25),
  });
  await page
    .locator("#terrainFile")
    .setInputFiles({
      name: "mdt_sem_municipio.tif",
      mimeType: "image/tiff",
      buffer: Buffer.from(small),
    });
  await page.waitForFunction(() =>
    document
      .getElementById("terrainInfo")
      .textContent.includes("mdt_sem_municipio.tif"),
  );
  const aoi = {
    type: "Polygon",
    coordinates: [
      [
        [0.499, 0.499],
        [0.501, 0.499],
        [0.501, 0.501],
        [0.499, 0.501],
        [0.499, 0.499],
      ],
    ],
  };
  await page
    .locator("#areaUpload")
    .setInputFiles({
      name: "area.geojson",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(aoi)),
    });
  await page.waitForFunction(() =>
    document.getElementById("status").textContent.includes("Camada importada"),
  );
  // A genuine 4096 × 8192 Float32 raster (128 MiB of pixel data), stored in row strips.
  const width = 4096,
    height = 8192,
    rowBytes = width * 4,
    offsets = 304,
    counts = offsets + height * 4,
    pixelBase = Math.ceil((counts + height * 4) / 4096) * 4096;
  const header = Buffer.alloc(pixelBase),
    tags = [
      [256, 4, 1, width],
      [257, 4, 1, height],
      [258, 3, 1, 32],
      [259, 3, 1, 1],
      [262, 3, 1, 1],
      [273, 4, height, offsets],
      [277, 3, 1, 1],
      [278, 4, 1, 1],
      [279, 4, height, counts],
      [284, 3, 1, 1],
      [339, 3, 1, 3],
      [33550, 12, 3, 192],
      [33922, 12, 6, 216],
      [34735, 3, 16, 264],
    ];
  header.write("II");
  header.writeUInt16LE(42, 2);
  header.writeUInt32LE(8, 4);
  header.writeUInt16LE(tags.length, 8);
  tags.forEach(([tag, type, n, val], i) => {
    const at = 10 + i * 12;
    header.writeUInt16LE(tag, at);
    header.writeUInt16LE(type, at + 2);
    header.writeUInt32LE(n, at + 4);
    if (type === 3 && n === 1) header.writeUInt16LE(val, at + 8);
    else header.writeUInt32LE(val, at + 8);
  });
  [1 / width, 1 / height, 0].forEach((x, i) =>
    header.writeDoubleLE(x, 192 + i * 8),
  );
  [0, 0, 0, 0, 1, 0].forEach((x, i) => header.writeDoubleLE(x, 216 + i * 8));
  [1, 1, 0, 3, 1024, 0, 1, 2, 1025, 0, 1, 1, 2048, 0, 1, 4326].forEach((x, i) =>
    header.writeUInt16LE(x, 264 + i * 2),
  );
  for (let y = 0; y < height; y++) {
    header.writeUInt32LE(pixelBase + y * rowBytes, offsets + y * 4);
    header.writeUInt32LE(rowBytes, counts + y * 4);
  }
  const filename = path.join(tmp, "mdt_128_mib.tif"),
    fd = fs.openSync(filename, "w");
  fs.ftruncateSync(fd, pixelBase + rowBytes * height);
  fs.writeSync(fd, header);
  const row = Buffer.alloc(rowBytes);
  for (let x = 0; x < width; x++) row.writeFloatLE(123.25, x * 4);
  for (let y = 4000; y < 4200; y++)
    fs.writeSync(fd, row, 0, rowBytes, pixelBase + y * rowBytes);
  fs.closeSync(fd);
  await page.evaluate(() => {
    window.terrainReads = [];
  });
  await page.locator("#terrainFile").setInputFiles(filename);
  await page.waitForFunction(() =>
    document
      .getElementById("terrainInfo")
      .textContent.includes("mdt_128_mib.tif"),
  );
  const readBytes = await page.evaluate(() =>
      window.terrainReads.reduce((a, b) => a + b, 0),
    ),
    fileBytes = fs.statSync(filename).size;
  assert(fileBytes > 100 * 1024 * 1024);
  assert(
    readBytes > 0 && readBytes < 4 * 1024 * 1024,
    "large raster must be read in small slices for the selected area",
  );
  const downloaded = page.waitForEvent("download");
  await page.locator("#downloadTerrain").click();
  const file = await downloaded,
    bytes = fs.readFileSync(await file.path()),
    { fromArrayBuffer } = await import("geotiff"),
    tif = await fromArrayBuffer(
      bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
    ),
    image = await tif.getImage(),
    raster = await image.readRasters();
  assert(image.getWidth() < 320 && image.getHeight() < 320);
  assert(Array.from(raster[0]).every((x) => x === 123.25));
  assert.equal(image.getGeoKeys().GeographicTypeGeoKey, 4326);
  await page
    .getByText("Modelo de elevação e geração HAND", { exact: true })
    .click();
  await page.locator("#drainArea").fill("0.001");
  await page.locator("#generateHand").click();
  await page.waitForFunction(
    () => !document.getElementById("generateHand").disabled,
  );
  assert.match(await page.locator("#status").innerText(), /HAND gerado/);
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.locator("#terrainFile").isVisible());
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    false,
  );
  assert.deepEqual(errors, []);
  console.log(
    JSON.stringify({
      pass: true,
      fileBytes,
      readBytes,
      croppedWidth: image.getWidth(),
      croppedHeight: image.getHeight(),
      firstStepTerrain: true,
      smallFileWithoutMunicipality: true,
      hand: true,
      mobile: true,
    }),
  );
  fs.rmSync(tmp, { recursive: true, force: true });
  await browser.close();
  server.close();
})().catch((e) => {
  console.error(e);
  server.close();
  process.exit(1);
});
