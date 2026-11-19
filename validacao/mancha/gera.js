// Gera, na própria página, a mancha pelo terreno para cada lugar e nível; grava cada mancha em prep/<lugar>_<nível>.json
const { chromium } = require("playwright");
const fs = require("fs"),
  path = require("path");
const BASE = process.env.BASE || "http://localhost:8771/cenario_municipal.html";
const prep = path.join(__dirname, "prep"), saida = path.join(__dirname, process.env.SAIDA || "prep");
fs.mkdirSync(saida, { recursive: true });
const sites = JSON.parse(fs.readFileSync(path.join(__dirname, "sites.json"))).filter((s) => !process.env.SO || process.env.SO.split(",").includes(s.slug));
const NIVEIS = (process.env.NIVEIS || "2,4,6,8,10,12,16,20").split(",").map(Number);
(async () => {
  const b = await chromium.launch();
  for (const s of sites) {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
    const p = await ctx.newPage();
    const errs = [];
    p.on("pageerror", (e) => errs.push(e.message));
    const st = async () => (await p.textContent("#status")).trim().replace(/\s+/g, " ");
    const livre = async (ms = 600000) => {
      await p.waitForTimeout(500);
      await p.waitForFunction(
        () => ![...document.querySelectorAll("button")].some((x) => x.disabled && !["csv", "routes"].includes(x.id)),
        null,
        { timeout: ms },
      );
    };
    try {
      await p.goto(BASE);
      await p.waitForTimeout(1500);
      await p.evaluate(() => document.querySelectorAll("#avancado, #avancado details").forEach((d) => (d.open = true)));
      await p.setInputFiles("#areaUpload", path.join(prep, s.slug + "_area.geojson"));
      await p.waitForTimeout(800);
      const t0 = Date.now();
      if (process.env.DRAIN) await p.fill("#drainArea", process.env.DRAIN);
      for (const nivel of NIVEIS) {
        await p.fill("#handLevel", String(nivel));
        await p.click("#generateHand");
        await livre();
        const msg = await st();
        if (!/Mancha gerada/.test(msg)) throw Error("nível " + nivel + ": " + msg);
        const [d] = await Promise.all([p.waitForEvent("download"), p.click("#save")]);
        const flood = JSON.parse(fs.readFileSync(await d.path(), "utf8")).layers.flood;
        fs.writeFileSync(path.join(saida, `${s.slug}_${nivel}.json`), JSON.stringify(flood));
        if (nivel === NIVEIS[0]) console.log(s.slug, "|", msg.slice(0, 90), "|", (await p.textContent("#terrainInfo")).slice(0, 90));
      }
      console.log(s.slug, "ok", Math.round((Date.now() - t0) / 1000) + " s", errs.length ? errs : "");
    } catch (e) {
      console.log(s.slug, "FALHA", e.message.slice(0, 200));
    }
    await ctx.close();
  }
  await b.close();
})();
