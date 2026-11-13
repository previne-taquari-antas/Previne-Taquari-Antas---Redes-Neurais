/* Motor municipal independente de Leaflet. Coordenadas GeoJSON WGS84. */
(function (root) {
  "use strict";
  const R = 6371000,
    rad = Math.PI / 180;
  function distance(a, b) {
    const x =
      Math.sin(((b[1] - a[1]) * rad) / 2) ** 2 +
      Math.cos(a[1] * rad) *
        Math.cos(b[1] * rad) *
        Math.sin(((b[0] - a[0]) * rad) / 2) ** 2;
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(x)));
  }
  const lerp = (a, b, t) => [
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
  ];
  function project(p, a, b) {
    const c = Math.cos(p[1] * rad),
      dx = (b[0] - a[0]) * c,
      dy = b[1] - a[1],
      den = dx * dx + dy * dy,
      t = den
        ? Math.max(
            0,
            Math.min(1, ((p[0] - a[0]) * c * dx + (p[1] - a[1]) * dy) / den),
          )
        : 0;
    const q = lerp(a, b, t);
    return { q, t, d: distance(p, q) };
  }
  function ring(p, r) {
    let yes = false;
    for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
      const a = r[i],
        b = r[j];
      if (project(p, a, b).d < 0.01) return true;
      if (
        a[1] > p[1] !== b[1] > p[1] &&
        p[0] < ((b[0] - a[0]) * (p[1] - a[1])) / (b[1] - a[1]) + a[0]
      )
        yes = !yes;
    }
    return yes;
  }
  function polygons(g) {
    return g.type === "Polygon"
      ? [g.coordinates]
      : g.type === "MultiPolygon"
        ? g.coordinates
        : [];
  }
  function inside(p, g) {
    return polygons(g).some(
      (poly) => ring(p, poly[0]) && !poly.slice(1).some((r) => ring(p, r)),
    );
  }
  function intersects(a, b, c, d) {
    const ux = b[0] - a[0],
      uy = b[1] - a[1],
      vx = d[0] - c[0],
      vy = d[1] - c[1],
      z = ux * vy - uy * vx;
    if (Math.abs(z) < 1e-15) return null;
    const t = ((c[0] - a[0]) * vy - (c[1] - a[1]) * vx) / z,
      u = ((c[0] - a[0]) * uy - (c[1] - a[1]) * ux) / z;
    return t >= -1e-9 && t <= 1 + 1e-9 && u >= -1e-9 && u <= 1 + 1e-9
      ? { t: Math.max(0, Math.min(1, t)), u: Math.max(0, Math.min(1, u)) }
      : null;
  }
  function lines(g) {
    if (g.type === "LineString") return [g.coordinates];
    if (g.type === "MultiLineString") return g.coordinates;
    return polygons(g).flat();
  }
  function near(p, features, margin) {
    return features.some(
      (f) =>
        (f.geometry.type === "Point" &&
          distance(p, f.geometry.coordinates) <= margin) ||
        inside(p, f.geometry) ||
        lines(f.geometry).some((l) =>
          l.some((q, i) => i && project(p, l[i - 1], q).d < margin),
        ),
    );
  }
  function hit(a, b, features, pointRadius = 15) {
    return features.some((f) => {
      const g = f.geometry;
      if (g.type === "Point")
        return project(g.coordinates, a, b).d <= pointRadius;
      if (inside(a, g) || inside(b, g) || inside(lerp(a, b, 0.5), g))
        return true;
      return lines(g).some((l) =>
        l.some(
          (q, i) =>
            i &&
            (intersects(a, b, l[i - 1], q) ||
              project(a, l[i - 1], q).d < 0.01 ||
              project(b, l[i - 1], q).d < 0.01 ||
              project(l[i - 1], a, b).d < 0.01 ||
              project(q, a, b).d < 0.01),
        ),
      );
    });
  }
  function validate(input, kind, { allowEmpty = false } = {}) {
    if (!input || typeof input !== "object") throw Error("GeoJSON inválido.");
    const fs =
      input.type === "FeatureCollection"
        ? input.features
        : input.type === "Feature"
          ? [input]
          : [{ type: "Feature", properties: {}, geometry: input }];
    if (!Array.isArray(fs) || (!fs.length && !allowEmpty))
      throw Error("Camada vazia.");
    const allowed = {
      roads: ["LineString", "MultiLineString"],
      buildings: ["Point", "Polygon", "MultiPolygon"],
      flood: ["Polygon", "MultiPolygon"],
      eligible: ["Polygon", "MultiPolygon"],
      aoi: ["Polygon", "MultiPolygon"],
      destinations: ["Point", "Polygon", "MultiPolygon"],
      blocks: [
        "Point",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
      ],
    }[kind];
    let count = 0,
      work = 0;
    function position(c) {
      if (
        !Array.isArray(c) ||
        c.length < 2 ||
        !c.every(Number.isFinite) ||
        Math.abs(c[0]) > 180 ||
        Math.abs(c[1]) > 90
      )
        throw Error(
          "Use coordenadas WGS84 (longitude, latitude) com a estrutura GeoJSON correta.",
        );
      if (++count > 500000)
        throw Error("Limite: 500 mil coordenadas por camada.");
      return c.slice(0, 2);
    }
    function line(c, min = 2) {
      if (!Array.isArray(c) || c.length < min)
        throw Error("Linha ou anel incompleto.");
      return c.map(position);
    }
    function simpleRing(r) {
      if (r[0][0] !== r.at(-1)[0] || r[0][1] !== r.at(-1)[1])
        throw Error("Polígono deve ter anéis fechados.");
      const seen = new Set(),
        segs = [],
        grid = new Map();
      let area = 0;
      const xs = r.map((p) => p[0]),
        ys = r.map((p) => p[1]),
        west = xs.reduce((a, b) => Math.min(a, b), Infinity),
        south = ys.reduce((a, b) => Math.min(a, b), Infinity),
        span = Math.max(
          xs.reduce((a, b) => Math.max(a, b), -Infinity) - west,
          ys.reduce((a, b) => Math.max(a, b), -Infinity) - south,
        ),
        cell = span / Math.max(1, Math.ceil(Math.sqrt(r.length)));
      if (!cell) throw Error("Anel sem área.");
      for (let i = 0; i < r.length - 1; i++) {
        const a = r[i],
          b = r[i + 1],
          key = a.join(",");
        if (seen.has(key) || distance(a, b) < 0.001)
          throw Error("Anel com vértices repetidos ou segmentos nulos.");
        seen.add(key);
        area +=
          (a[0] - r[0][0]) * (b[1] - r[0][1]) -
          (b[0] - r[0][0]) * (a[1] - r[0][1]);
        const candidates = new Set(),
          cells = [];
        for (
          let x = Math.floor((Math.min(a[0], b[0]) - west) / cell);
          x <= Math.floor((Math.max(a[0], b[0]) - west) / cell);
          x++
        )
          for (
            let y = Math.floor((Math.min(a[1], b[1]) - south) / cell);
            y <= Math.floor((Math.max(a[1], b[1]) - south) / cell);
            y++
          ) {
            if (++work > 3000000)
              throw Error(
                "Polígono muito complexo. Simplifique e valide a camada antes de importar.",
              );
            const k = x + "," + y;
            cells.push(k);
            for (const j of grid.get(k) || []) candidates.add(j);
          }
        for (const j of candidates) {
          if (j === i - 1 || (j === 0 && i === r.length - 2)) continue;
          const [c, d] = segs[j];
          if (
            intersects(a, b, c, d) ||
            project(a, c, d).d < 0.001 ||
            project(b, c, d).d < 0.001 ||
            project(c, a, b).d < 0.001 ||
            project(d, a, b).d < 0.001
          )
            throw Error(
              "Polígono com auto-interseção. Corrija a geometria antes de importar.",
            );
        }
        segs.push([a, b]);
        for (const k of cells) {
          if (!grid.has(k)) grid.set(k, []);
          grid.get(k).push(i);
        }
      }
      if (Math.abs(area) < 1e-16)
        throw Error("Anel sem área ou com auto-interseção.");
      return r;
    }
    function polygon(c) {
      if (!Array.isArray(c) || !c.length) throw Error("Polígono vazio.");
      const rings = c.map((r) => simpleRing(line(r, 4)));
      // A hole may touch its shell at one isolated point (valid OGC geometry).
      function relation(a, b) {
        let invalid = false;
        const contacts = new Set();
        for (let i = 1; i < a.length; i++)
          for (let j = 1; j < b.length; j++) {
            if (++work > 3000000)
              throw Error("Polígono muito complexo. Simplifique a camada.");
            const p = a[i - 1],
              q = a[i],
              r = b[j - 1],
              t = b[j];
            if (
              Math.max(p[0], q[0]) < Math.min(r[0], t[0]) ||
              Math.max(r[0], t[0]) < Math.min(p[0], q[0]) ||
              Math.max(p[1], q[1]) < Math.min(r[1], t[1]) ||
              Math.max(r[1], t[1]) < Math.min(p[1], q[1])
            )
              continue;
            const cross = intersects(p, q, r, t);
            if (cross) {
              if (
                cross.t > 1e-9 &&
                cross.t < 1 - 1e-9 &&
                cross.u > 1e-9 &&
                cross.u < 1 - 1e-9
              )
                invalid = true;
              contacts.add(
                lerp(p, q, cross.t)
                  .map((x) => x.toFixed(9))
                  .join(","),
              );
            } else if (
              project(r, p, q).d < 0.001 &&
              project(t, p, q).d < 0.001
            ) {
              const dx = q[0] - p[0],
                dy = q[1] - p[1],
                den = dx * dx + dy * dy;
              const u = ((r[0] - p[0]) * dx + (r[1] - p[1]) * dy) / den,
                v = ((t[0] - p[0]) * dx + (t[1] - p[1]) * dy) / den;
              const lo = Math.max(0, Math.min(u, v)),
                hi = Math.min(1, Math.max(u, v));
              if (hi > lo && distance(lerp(p, q, lo), lerp(p, q, hi)) > 0.001)
                invalid = true;
              if (hi >= lo)
                contacts.add(
                  lerp(p, q, lo)
                    .map((x) => x.toFixed(9))
                    .join(","),
                );
            }
          }
        return invalid || contacts.size > 1;
      }
      function samples(a, b) {
        const out = a.slice(0, -1);
        for (let i = 1; i < a.length; i++) {
          const ts = [0, 1];
          for (let j = 1; j < b.length; j++) {
            if (++work > 3000000)
              throw Error("Polígono muito complexo. Simplifique a camada.");
            const cross = intersects(a[i - 1], a[i], b[j - 1], b[j]);
            if (cross) ts.push(cross.t);
          }
          ts.sort((x, y) => x - y);
          for (let j = 1; j < ts.length; j++)
            if (ts[j] > ts[j - 1])
              out.push(lerp(a[i - 1], a[i], (ts[j] + ts[j - 1]) / 2));
        }
        return out;
      }
      const strictlyInside = (p, r) =>
        ring(p, r) && !r.some((q, i) => i && project(p, r[i - 1], q).d < 0.001);
      for (let i = 1; i < rings.length; i++) {
        if (
          relation(rings[i], rings[0]) ||
          samples(rings[i], rings[0]).some((p) => !ring(p, rings[0]))
        )
          throw Error("Furo fora do anel exterior ou cruzando seu limite.");
        for (let j = 1; j < i; j++)
          if (
            relation(rings[i], rings[j]) ||
            samples(rings[i], rings[j]).some((p) =>
              strictlyInside(p, rings[j]),
            ) ||
            samples(rings[j], rings[i]).some((p) => strictlyInside(p, rings[i]))
          )
            throw Error("Furos sobrepostos ou aninhados no polígono.");
      }
      return rings;
    }
    for (const f of fs) {
      if (
        !f ||
        f.type !== "Feature" ||
        !f.geometry ||
        !allowed?.includes(f.geometry.type)
      )
        throw Error("Geometria incompatível com " + kind + ".");
      if (
        f.properties != null &&
        (typeof f.properties !== "object" || Array.isArray(f.properties))
      )
        throw Error("Atributos GeoJSON inválidos.");
      const g = f.geometry,
        c = g.coordinates;
      if (g.type === "Point") g.coordinates = position(c);
      else if (g.type === "LineString") g.coordinates = line(c);
      else if (g.type === "Polygon") g.coordinates = polygon(c);
      else {
        if (!Array.isArray(c) || !c.length) throw Error("Geometria vazia.");
        g.coordinates = c.map(
          g.type === "MultiLineString" ? (x) => line(x) : polygon,
        );
      }
      f.properties = f.properties || {};
    }
    return { type: "FeatureCollection", features: fs };
  }
  function representative(g) {
    if (g.type === "Point") return g.coordinates;
    const r = polygons(g)[0][0];
    let sx = 0,
      sy = 0,
      ar = 0;
    for (let i = 1; i < r.length; i++) {
      const a = r[i - 1],
        b = r[i],
        z = a[0] * b[1] - b[0] * a[1];
      ar += z;
      sx += (a[0] + b[0]) * z;
      sy += (a[1] + b[1]) * z;
    }
    const p = ar ? [sx / (3 * ar), sy / (3 * ar)] : r[0];
    if (inside(p, g)) return p;
    return r[0];
  }
  function graph(features, options) {
    let segments = [];
    const terminals = new Set(),
      sourceJunctions = new Map(),
      gradeGroups = new Map();
    const coordKey = (p) => p.map((v) => v.toFixed(7)).join(",");
    for (const f of features) {
      const p = f.properties || {},
        type = p.highway || "sem_classificacao";
      if (options.roadTypes?.length && !options.roadTypes.includes(type))
        continue;
      if (p.foot === "no" || p.access === "no") continue;
      const geometryLines = lines(f.geometry),
        rawIds = p.node_ids ?? p.osm_node_ids;
      const nodeLists =
        rawIds == null
          ? null
          : f.geometry.type === "MultiLineString"
            ? rawIds
            : [rawIds];
      if (
        nodeLists &&
        (!Array.isArray(nodeLists) || nodeLists.length !== geometryLines.length)
      )
        throw Error("node_ids deve acompanhar as coordenadas das vias.");
      const layer = Number.isFinite(Number(p.layer ?? 0))
        ? String(Number(p.layer ?? 0))
        : String(p.layer);
      for (const [lineIndex, l] of geometryLines.entries()) {
        const nodeIds = nodeLists?.[lineIndex];
        if (nodeIds && (!Array.isArray(nodeIds) || nodeIds.length !== l.length))
          throw Error("node_ids deve ter um identificador por coordenada.");
        if (nodeIds)
          l.forEach((position, i) => {
            const id = nodeIds[i];
            if (id == null) return;
            if (
              (typeof id !== "string" && typeof id !== "number") ||
              String(id).trim() === "" ||
              (typeof id === "number" && !Number.isSafeInteger(id))
            )
              throw Error("Identificador de nó inválido.");
            const key = coordKey(position);
            if (!sourceJunctions.has(key)) sourceJunctions.set(key, new Map());
            const byId = sourceJunctions.get(key),
              nodeId = String(id);
            if (!byId.has(nodeId)) byId.set(nodeId, new Set());
            byId.get(nodeId).add(layer);
          });
        terminals.add(l[0].map((v) => v.toFixed(7)).join(","));
        terminals.add(l[l.length - 1].map((v) => v.toFixed(7)).join(","));
        for (let i = 1; i < l.length; i++) {
          const a = l[i - 1],
            b = l[i];
          if (distance(a, b) < 0.05) continue;
          segments.push({
            a,
            b,
            ts: [0, 1],
            layer,
            level:
              layer +
              "|" +
              String(p.bridge || "no") +
              "|" +
              String(p.tunnel || "no"),
          });
        }
      }
    }
    // Only source node IDs can establish a junction between explicit levels.
    for (const [coord, byId] of sourceJunctions) {
      const groups = new Map();
      const find = (x) => {
        if (!groups.has(x)) groups.set(x, x);
        const p = groups.get(x);
        if (p !== x) groups.set(x, find(p));
        return groups.get(x);
      };
      let shared = false;
      for (const layers of byId.values())
        if (layers.size > 1) {
          shared = true;
          const list = [...layers];
          for (const layer of list.slice(1))
            groups.set(find(layer), find(list[0]));
        }
      if (shared) {
        for (const layer of groups.keys()) find(layer);
        gradeGroups.set(coord, groups);
        terminals.add(coord);
      }
    }
    for (const segment of segments)
      for (const area of options.clipAreas || [])
        for (const boundary of lines(area.geometry))
          for (let i = 1; i < boundary.length; i++) {
            const cross = intersects(
              segment.a,
              segment.b,
              boundary[i - 1],
              boundary[i],
            );
            if (cross) segment.ts.push(cross.t);
          }
    if (segments.length > 15000)
      throw Error("Recorte as vias para até 15 mil segmentos.");
    // Grade espacial para dividir cruzamentos no mesmo nível; pontes não viram cruzamentos em nível.
    const grid = new Map(),
      cell = 0.002;
    function cells(s) {
      const out = [];
      for (
        let x = Math.floor(Math.min(s.a[0], s.b[0]) / cell);
        x <= Math.floor(Math.max(s.a[0], s.b[0]) / cell);
        x++
      )
        for (
          let y = Math.floor(Math.min(s.a[1], s.b[1]) / cell);
          y <= Math.floor(Math.max(s.a[1], s.b[1]) / cell);
          y++
        ) {
          out.push(x + "," + y);
          if (out.length > 10000)
            throw Error("Segmento muito extenso; recorte a área.");
        }
      return out;
    }
    segments.forEach((s, i) => {
      const seen = new Set();
      for (const k of cells(s)) {
        for (const j of grid.get(k) || []) {
          if (seen.has(j)) continue;
          seen.add(j);
          const o = segments[j];
          if (o.level !== s.level) continue;
          const q = intersects(s.a, s.b, o.a, o.b);
          if (q) {
            s.ts.push(q.t);
            o.ts.push(q.u);
          } else {
            for (const p of [s.a, s.b]) {
              const x = project(p, o.a, o.b);
              if (x.d < 0.02) o.ts.push(x.t);
            }
            for (const p of [o.a, o.b]) {
              const x = project(p, s.a, s.b);
              if (x.d < 0.02) s.ts.push(x.t);
            }
          }
        }
        if (!grid.has(k)) grid.set(k, []);
        grid.get(k).push(i);
      }
    });
    const nodes = [],
      edges = [],
      ids = new Map();
    const node = (p, level, layer) => {
      const coord = coordKey(p),
        grade = gradeGroups.get(coord)?.get(layer) ?? layer,
        k = coord + "|" + (terminals.has(coord) ? "endpoint:" + grade : level);
      if (!ids.has(k)) {
        ids.set(k, nodes.length);
        nodes.push(p);
      }
      return ids.get(k);
    };
    for (const s of segments) {
      const ts = [...new Set(s.ts)].sort((a, b) => a - b);
      for (let i = 1; i < ts.length; i++) {
        const a = lerp(s.a, s.b, ts[i - 1]),
          b = lerp(s.a, s.b, ts[i]),
          n = Math.max(1, Math.ceil(distance(a, b) / 80));
        if (
          options.clipAreas?.length &&
          !options.clipAreas.some((area) =>
            inside(lerp(a, b, 0.5), area.geometry),
          )
        )
          continue;
        if (n > 30000 || nodes.length + n > 30000)
          throw Error("Recorte a rede para até 30 mil nós.");
        for (let j = 0; j < n; j++) {
          const p = lerp(a, b, j / n),
            q = lerp(a, b, (j + 1) / n);
          if (distance(p, q) > 0.05)
            edges.push([
              node(p, s.level, s.layer),
              node(q, s.level, s.layer),
              distance(p, q),
            ]);
        }
      }
    }
    if (!edges.length && (!options.clipAreas?.length || !segments.length))
      throw Error("Nenhuma via utilizável com os filtros escolhidos.");
    if (nodes.length > 30000)
      throw Error("Rede muito grande. Reduza a área de interesse.");
    return { nodes, edges };
  }
  class Heap {
    constructor() {
      this.h = [];
    }
    push(v) {
      let i = this.h.length;
      this.h.push(v);
      while (i) {
        const p = (i - 1) >> 1;
        if (this.h[p][0] <= v[0]) break;
        this.h[i] = this.h[p];
        i = p;
      }
      this.h[i] = v;
    }
    pop() {
      const top = this.h[0],
        v = this.h.pop();
      if (this.h.length) {
        let i = 0;
        while (i * 2 + 1 < this.h.length) {
          let j = i * 2 + 1;
          if (j + 1 < this.h.length && this.h[j + 1][0] < this.h[j][0]) j++;
          if (this.h[j][0] >= v[0]) break;
          this.h[i] = this.h[j];
          i = j;
        }
        this.h[i] = v;
      }
      return top;
    }
  }
  function shortest(adj, start) {
    const t = Array(adj.length).fill(Infinity),
      next = Array(adj.length).fill(-1),
      h = new Heap();
    t[start] = 0;
    h.push([0, start]);
    while (h.h.length) {
      const [v, u] = h.pop();
      if (v !== t[u]) continue;
      for (const [n, w] of adj[u])
        if (v + w < t[n]) {
          t[n] = v + w;
          next[n] = u;
          h.push([t[n], n]);
        }
    }
    return { t, next };
  }
  function plan(data, o) {
    for (const [kind, layer] of Object.entries(data))
      validate(layer, kind, {
        allowEmpty: !["roads", "buildings"].includes(kind),
      });
    const flood = data.flood?.features || [],
      blocks = data.blocks?.features || [],
      aoi = data.aoi?.features || [],
      elig = data.eligible?.features || [];
    if (!data.roads || !data.buildings)
      throw Error("Importe vias e edificações antes de calcular.");
    if (!flood.length && !o.allBuildings)
      throw Error("Selecione uma mancha ou marque todas as edificações.");
    const speed = Number(o.speed),
      limit = Number(o.minutes) * 60,
      margin = Number(o.margin);
    if (
      ![speed, limit, margin].every(Number.isFinite) ||
      !(speed > 0 && limit > 0 && margin >= 0)
    )
      throw Error("Tempo, velocidade e afastamento inválidos.");
    const inArea = (p) => !aoi.length || aoi.some((f) => inside(p, f.geometry));
    function withinArea(p, q) {
      if (!aoi.length) return true;
      if (!inArea(p) || !inArea(q)) return false;
      const ts = [0, 1];
      for (const f of aoi)
        for (const l of lines(f.geometry))
          for (let i = 1; i < l.length; i++) {
            const cross = intersects(p, q, l[i - 1], l[i]);
            if (cross) ts.push(cross.t);
          }
      ts.sort((a, b) => a - b);
      return ts.every((t, i) => !i || inArea(lerp(p, q, (t + ts[i - 1]) / 2)));
    }
    const g = graph(data.roads.features, {
        ...o,
        clipAreas: aoi,
        roadTypes:
          typeof o.roadTypes === "string"
            ? o.roadTypes
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
            : o.roadTypes,
      }),
      adj = g.nodes.map(() => []),
      available = [];
    let removed = 0;
    for (const [a, b, d] of g.edges) {
      const p = g.nodes[a],
        q = g.nodes[b];
      if (
        !withinArea(p, q) ||
        hit(p, q, blocks) ||
        (o.excludeFlood && hit(p, q, flood))
      ) {
        removed++;
        continue;
      }
      adj[a].push([b, d / speed]);
      adj[b].push([a, d / speed]);
      available.push([a, b]);
    }
    function snap(p) {
      let best = { node: -1, d: Infinity };
      g.nodes.forEach((q, node) => {
        if (!adj[node].length) return;
        const d = distance(p, q);
        if (
          d < best.d &&
          withinArea(p, q) &&
          !hit(p, q, blocks) &&
          (!o.excludeFlood || !hit(p, q, flood))
        )
          best = { node, d };
      });
      return best.d <= Number(o.snapMax || 150)
        ? best
        : { node: -1, d: Infinity };
    }
    const buildings = data.buildings.features.map((f, i) => {
      const p = representative(f.geometry),
        props = f.properties || {},
        raw = props.pessoas ?? props.population ?? props.ocupantes,
        n = raw == null ? Number(o.peoplePerBuilding) : Number(raw);
      if (!Number.isFinite(n) || n <= 0)
        throw Error("População inválida na edificação " + (i + 1));
      return {
        id: String(f.id ?? props.id ?? i + 1),
        p,
        people: Math.ceil(n),
        estimated: raw == null,
        required: inArea(p) && (o.allBuildings || near(p, flood, margin)),
        ...snap(p),
      };
    });
    const safe = (p) =>
      inArea(p) &&
      !near(p, flood, Math.max(0.01, margin)) &&
      !near(p, blocks, 15) &&
      (!elig.length || elig.some((f) => inside(p, f.geometry)));
    const destinations = [],
      rejected = [];
    for (const f of o.mode === "automatico"
      ? []
      : data.destinations?.features || []) {
      const p = representative(f.geometry),
        props = f.properties || {},
        s = snap(p),
        raw = props.capacidade ?? props.capacity,
        cap = raw == null || raw === "" ? null : Number(raw),
        occ = Number(props.ocupacao ?? props.occupancy ?? 0),
        name = String(
          props.nome || props.name || "Destino " + (destinations.length + 1),
        );
      if (
        (cap !== null && (!Number.isInteger(cap) || cap < 0)) ||
        !Number.isInteger(occ) ||
        occ < 0 ||
        (cap !== null && occ > cap)
      )
        throw Error("Capacidade/ocupação inválida: " + name);
      if (!safe(p) || s.node < 0) {
        rejected.push({
          name,
          reason:
            "Fora dos critérios de elegibilidade, afastamento ou acesso à rede.",
        });
        continue;
      }
      destinations.push({
        p,
        ...s,
        name,
        kind: props.tipo || "ponto_de_encontro",
        capacity: cap,
        remaining: cap === null ? Infinity : cap - occ,
        occupancy: occ,
        origin: "usuario",
      });
    }
    if (o.mode !== "manual") {
      const nodes = g.nodes
        .map((p, node) => ({ p, node }))
        .filter((x) => adj[x.node].length && safe(x.p));
      const stride = Math.max(1, Math.ceil(nodes.length / 200));
      for (let i = 0; i < nodes.length; i += stride) {
        const c = nodes[i];
        if (destinations.some((d) => d.node === c.node)) continue;
        destinations.push({
          ...c,
          d: 0,
          name: "Ponto sugerido " + (i + 1),
          kind: "ponto_de_encontro",
          capacity: null,
          remaining: Infinity,
          occupancy: 0,
          origin: "algoritmo",
        });
      }
    }
    if (destinations.length > 300)
      throw Error("Use até 300 destinos por cenário.");
    for (const d of destinations) {
      d.route = shortest(adj, d.node);
      d.assigned = [];
      d.used = 0;
    }
    const pending = new Set(
        buildings.map((b, i) => (b.required ? i : -1)).filter((i) => i >= 0),
      ),
      selected = [];
    function feasible(d, b) {
      const t =
        b.node < 0 ? Infinity : b.d / speed + d.route.t[b.node] + d.d / speed;
      return t <= limit &&
        (!o.enforceCapacity || d.capacity !== null) &&
        b.people <= d.remaining
        ? t
        : Infinity;
    }
    function assign(d) {
      selected.push(d);
      const order = [...pending]
        .map((i) => [i, feasible(d, buildings[i])])
        .filter((x) => Number.isFinite(x[1]))
        .sort((a, b) => a[1] - b[1]);
      for (const [i, t] of order) {
        const b = buildings[i];
        if (!Number.isFinite(feasible(d, b))) continue;
        d.assigned.push(i);
        d.used += b.people;
        if (d.capacity !== null) d.remaining -= b.people;
        b.destination = selected.length - 1;
        b.seconds = t;
        pending.delete(i);
      }
    }
    for (const d of destinations.filter((d) => d.origin === "usuario"))
      assign(d);
    while (o.mode !== "manual" && pending.size) {
      let best = null,
        score = 0;
      for (const d of destinations) {
        if (selected.includes(d)) continue;
        const s = [...pending].reduce(
          (n, i) =>
            n +
            (Number.isFinite(feasible(d, buildings[i]))
              ? buildings[i].people
              : 0),
          0,
        );
        if (s > score) {
          best = d;
          score = s;
        }
      }
      if (!best) break;
      assign(best);
    }
    for (const i of pending) {
      const b = buildings[i];
      b.reason =
        b.node < 0
          ? "Sem acesso à rede após os bloqueios"
          : destinations.some(
                (d) => b.d / speed + d.route.t[b.node] + d.d / speed <= limit,
              )
            ? "Sem capacidade disponível ou informada"
            : "Sem destino alcançável no tempo escolhido";
    }
    const required = buildings.filter((b) => b.required),
      assigned = required.filter((b) => b.destination != null);
    return {
      graph: g,
      available,
      removed,
      buildings,
      destinations: selected,
      rejected,
      summary: {
        required: required.length,
        assigned: assigned.length,
        unassigned: pending.size,
        people: required.reduce((s, b) => s + b.people, 0),
        served: assigned.reduce((s, b) => s + b.people, 0),
        estimated: required.filter((b) => b.estimated).length,
        capacityVerified: !!o.enforceCapacity,
      },
      options: o,
    };
  }
  function route(result, i) {
    const b = result.buildings[i];
    if (b.destination == null) return [];
    const d = result.destinations[b.destination],
      out = [b.p];
    let n = b.node,
      guard = 0;
    while (n >= 0 && guard++ < result.graph.nodes.length) {
      out.push(result.graph.nodes[n]);
      n = d.route.next[n];
    }
    out.push(d.p);
    return out;
  }
  const api = {
    distance,
    inside,
    hit,
    validate,
    representative,
    graph,
    plan,
    route,
    near,
  };
  if (typeof module !== "undefined") module.exports = api;
  else root.CenarioEngine = api;
})(typeof self !== "undefined" ? self : this);
