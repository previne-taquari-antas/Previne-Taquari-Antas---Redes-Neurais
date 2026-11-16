// Fluxo completo do cenário municipal em lugares de países diferentes, com os serviços reais:
// busca do lugar (Nominatim), ruas e edificações (Overpass), relevo (Terrain Tiles), mancha pelo
// terreno e cálculo. Não entra no teste de cada PR porque depende de serviços de fora:
// roda em .github/workflows/cenario-mundo-real.yml. MOCK_OVERPASS=1 simula só o Overpass.
const { chromium } = require("playwright"),
  fs = require("fs"),
  path = require("path"),
  http = require("http");
const root = path.resolve(__dirname, "../.."),
  out = process.env.REPORT_DIR || "/tmp/previne-cenario-mundo";
fs.mkdirSync(out, { recursive: true });
const LUGARES = [
  { q: "Centro, Lajeado, Rio Grande do Sul, Brasil", slug: "lajeado" },
  { q: "Alfafar, Valencia, España", slug: "alfafar" },
  { q: "Ahrweiler, Bad Neuenahr-Ahrweiler, Deutschland", slug: "ahrweiler" },
  { q: "Muçum, Rio Grande do Sul, Brasil", slug: "mucum", grande: true },
];
// LUGAR=lajeado roda só um lugar (um por máquina no CI: os servidores abertos limitam pedidos seguidos)
const ESCOLHIDOS = process.env.LUGAR
  ? LUGARES.filter((l) => l.slug === process.env.LUGAR)
  : LUGARES;
const tipos = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".json": "application/json",
  ".css": "text/css",
};
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
    tipos[path.extname(file)] || "application/octet-stream",
  );
  res.end(fs.readFileSync(file));
});
const simulado = (caixa) => {
  // grade de ruas e casas dentro da caixa pedida
  const [s, w, n, e] = caixa,
    els = [];
  let id = 1;
  const g = (pts) => pts.map(([lon, lat]) => ({ lat, lon })),
    dx = (e - w) / 7,
    dy = (n - s) / 7;
  for (let i = 1; i < 7; i++) {
    els.push({
      type: "way",
      id: id++,
      nodes: [1, 2, 3, 4, 5, 6].map((j) => i * 10 + j),
      tags: { highway: "residential" },
      geometry: g([1, 2, 3, 4, 5, 6].map((j) => [w + j * dx, s + i * dy])),
    });
    els.push({
      type: "way",
      id: id++,
      nodes: [1, 2, 3, 4, 5, 6].map((j) => j * 10 + i),
      tags: { highway: "residential" },
      geometry: g([1, 2, 3, 4, 5, 6].map((j) => [w + i * dx, s + j * dy])),
    });
  }
  for (let i = 1; i < 6; i++)
    for (let j = 1; j < 6; j++) {
      const x = w + (i + 0.4) * dx,
        y = s + (j + 0.2) * dy,
        d = 0.0001;
      els.push({
        type: "way",
        id: id++,
        tags: { building: "yes" },
        geometry: g([
          [x, y],
          [x + d, y],
          [x + d, y + d],
          [x, y + d],
          [x, y],
        ]),
      });
    }
  return { osm3s: { timestamp_osm_base: "simulado" }, elements: els };
};
(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const base = `http://127.0.0.1:${server.address().port}/cenario_municipal.html`,
    browser = await chromium.launch(),
    relatorio = [];
  let falhas = 0;
  for (const lugar of ESCOLHIDOS) {
    // os servidores abertos limitam pedidos seguidos da mesma máquina
    if (relatorio.length && !process.env.MOCK_OVERPASS)
      await new Promise((r) => setTimeout(r, 45000));
    const reg = { lugar: lugar.q, passos: [], erros: [] },
      ctx = await browser.newContext({
        viewport: { width: 1280, height: 800 },
      });
    if (process.env.MOCK_OVERPASS)
      await ctx.route(/\/api\/interpreter/, (r) => {
        const q = decodeURIComponent(r.request().postData()),
          c = q
            .match(/\(([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)\)/)
            .slice(1, 5)
            .map(Number);
        if (/waterway/.test(q) && !/highway/.test(q)) {
          const [s0, w0, n0, e0] = c;
          return r.fulfill({
            json: {
              elements: [
                {
                  type: "way",
                  id: 1,
                  tags: { waterway: "river" },
                  geometry: [
                    { lat: s0, lon: w0 },
                    { lat: (s0 + n0) / 2, lon: (w0 + e0) / 2 },
                    { lat: n0, lon: e0 },
                  ],
                },
              ],
            },
          });
        }
        r.fulfill({ json: simulado(c) });
      });
    const p = await ctx.newPage();
    p.on("pageerror", (e) => reg.erros.push(e.message));
    reg.avisos = [];
    p.on("console", (m) => {
      if (m.type() === "warning" && /interpreter/.test(m.text()))
        reg.avisos.push(m.text().slice(0, 160));
    });
    const estado = async (ms = 120000) => {
        // espera o botão em uso terminar
        await p.waitForFunction(
          () =>
            ![...document.querySelectorAll("button")].some(
              (b) => b.disabled && !["csv", "routes"].includes(b.id),
            ),
          null,
          { timeout: ms },
        );
        return {
          texto: (await p.textContent("#status")).trim(),
          erro: await p.evaluate(() =>
            document.getElementById("status").classList.contains("error"),
          ),
        };
      },
      passo = async (nome, fn, ms) => {
        await fn();
        await p.waitForTimeout(400);
        const r = await estado(ms);
        reg.passos.push({ nome, ...r });
        return r;
      };
    try {
      await p.goto(base);
      await p.waitForTimeout(1500);
      await p.fill("#placeQuery", lugar.q);
      let r = await passo("procurar", () => p.click("#placeSearch"), 60000);
      if (r.erro) throw Error("busca: " + r.texto);
      const usar = p.locator("#placeResults li:first-child button", {
        hasText: "Usar o limite",
      });
      if (lugar.grande) {
        r = await passo("limite grande", () => usar.click());
        if (!/Usar a área visível/.test(r.texto))
          throw Error("devia orientar a usar a área visível: " + r.texto);
        await p
          .locator("#placeResults li:first-child button", {
            hasText: "Ver no mapa",
          })
          .click();
        // aproxima até a área na tela caber no limite
        for (let i = 0; i < 6; i++) {
          r = await passo("área visível", () => p.click("#viewArea"));
          if (!r.erro) break;
          await p.click(".leaflet-control-zoom-in");
          await p.waitForTimeout(600);
        }
      } else r = await passo("usar limite", () => usar.click());
      if (r.erro) throw Error("área: " + r.texto);
      r = await passo(
        "ruas e edificações",
        () => p.click("#osmDownload"),
        300000,
      );
      // cidade densa: a página pede uma área menor; aproxima e tenta de novo, como ela orienta
      for (let i = 0; i < 4 && r.erro && /ruas demais/.test(r.texto); i++) {
        await p.click(".leaflet-control-zoom-in");
        await p.waitForTimeout(700);
        r = await passo("área visível (menor)", () => p.click("#viewArea"));
        if (r.erro) continue;
        r = await passo(
          "ruas e edificações",
          () => p.click("#osmDownload"),
          300000,
        );
      }
      if (r.erro && !/Nenhuma edificação/.test(r.texto))
        throw Error("OpenStreetMap: " + r.texto);
      reg.camadas = (await p.innerText("#layers")).replace(
        /\s*Remover\s*/g,
        " | ",
      );
      // a mancha pelo terreno busca sozinha o relevo e os rios
      await p.evaluate(
        () =>
          (document.querySelector("#generateHand").closest("details").open =
            true),
      );
      await p.fill("#handLevel", "4");
      r = await passo(
        "mancha pelo terreno",
        () => p.click("#generateHand"),
        300000,
      );
      reg.terreno = (await p.textContent("#terrainInfo")).trim().slice(0, 160);
      const mancha = !r.erro && /Inundação/.test(await p.innerText("#layers"));
      if (!mancha) throw Error("mancha pelo terreno: " + r.texto);
      if (!process.env.MOCK_OVERPASS && !/rios mapeados/.test(r.texto))
        throw Error("a mancha saiu sem os rios do mapa: " + r.texto);
      reg.mancha = mancha;
      await p.selectOption("#mode", "automatico");
      r = await passo("calcular", () => p.click("#calculate"), 300000);
      reg.resultado = (await p.innerText("#results"))
        .split("\n")
        .filter(Boolean)
        .slice(0, 8)
        .join(" / ");
      if (r.erro) throw Error("cálculo: " + r.texto);
      if (reg.erros.length) throw Error("erro de script: " + reg.erros[0]);
      reg.ok = true;
    } catch (e) {
      reg.ok = false;
      reg.falha = e.message;
      falhas++;
    }
    await p
      .screenshot({ path: path.join(out, lugar.slug + ".png") })
      .catch(() => {});
    relatorio.push(reg);
    await ctx.close();
  }
  await browser.close();
  server.close();
  fs.writeFileSync(
    path.join(out, "relatorio.json"),
    JSON.stringify(relatorio, null, 1),
  );
  console.log(JSON.stringify(relatorio, null, 1));
  if (falhas) process.exit(1);
})();
