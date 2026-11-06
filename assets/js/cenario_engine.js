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
  function validate(input, kind) {
    const fs =
      input.type === "FeatureCollection"
        ? input.features
        : input.type === "Feature"
          ? [input]
          : [{ type: "Feature", properties: {}, geometry: input }];
    if (!Array.isArray(fs) || !fs.length) throw Error("Camada vazia.");
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
    let count = 0;
    for (const f of fs) {
      if (!f.geometry || !allowed?.includes(f.geometry.type))
        throw Error("Geometria incompatível com " + kind + ".");
      const g = f.geometry;
      function walk(c) {
        if (!Array.isArray(c) || !c.length) throw Error("Coordenadas vazias.");
        if (typeof c[0] === "number") {
          if (
            c.length < 2 ||
            !Number.isFinite(c[0]) ||
            !Number.isFinite(c[1]) ||
            Math.abs(c[0]) > 180 ||
            Math.abs(c[1]) > 90
          )
            throw Error("Use coordenadas WGS84 (longitude, latitude).");
          if (++count > 500000)
            throw Error("Limite: 500 mil coordenadas por camada.");
        } else c.forEach(walk);
      }
      walk(g.coordinates);
      for (const l of lines(g)) {
        if (l.length < 2) throw Error("Linha incompleta.");
      }
      for (const p of polygons(g))
        for (const r of p) {
          if (
            r.length < 4 ||
            r[0][0] !== r[r.length - 1][0] ||
            r[0][1] !== r[r.length - 1][1]
          )
            throw Error(
              "Polígono deve ter anéis fechados e ao menos quatro coordenadas.",
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
    const terminals = new Set();
    for (const f of features) {
      const p = f.properties || {},
        type = p.highway || "sem_classificacao";
      if (options.roadTypes?.length && !options.roadTypes.includes(type))
        continue;
      if (p.foot === "no" || p.access === "no") continue;
      for (const l of lines(f.geometry)) {
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
            level:
              String(p.layer || 0) +
              "|" +
              String(p.bridge || "no") +
              "|" +
              String(p.tunnel || "no"),
          });
        }
      }
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
    const node = (p, level) => {
      const coord = p.map((v) => v.toFixed(7)).join(","),
        k = coord + "|" + (terminals.has(coord) ? "endpoint" : level);
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
        if (n > 30000 || nodes.length + n > 30000)
          throw Error("Recorte a rede para até 30 mil nós.");
        for (let j = 0; j < n; j++) {
          const p = lerp(a, b, j / n),
            q = lerp(a, b, (j + 1) / n);
          if (distance(p, q) > 0.05)
            edges.push([node(p, s.level), node(q, s.level), distance(p, q)]);
        }
      }
    }
    if (!edges.length)
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
    if (!(speed > 0 && limit > 0 && margin >= 0))
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
    for (const f of data.destinations?.features || []) {
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
    if (o.mode === "automatico")
      destinations.splice(
        0,
        destinations.findIndex((d) => d.origin === "algoritmo") < 0
          ? destinations.length
          : destinations.findIndex((d) => d.origin === "algoritmo"),
      );
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
