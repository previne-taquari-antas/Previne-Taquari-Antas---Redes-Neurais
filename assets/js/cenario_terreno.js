/* HAND experimental: condicionamento por priority-flood, fluxo D8 e drenagem por área contribuinte. */
(function (root) {
  "use strict";
  function hand(values, width, height, cellArea, threshold, level, bbox) {
    if (values.length !== width * height || width < 3 || height < 3)
      throw Error("Raster inválido.");
    if (
      !Number.isFinite(level) ||
      level < 0 ||
      !Number.isFinite(threshold) ||
      threshold <= 0
    )
      throw Error("Nível e área de drenagem inválidos.");
    const n = values.length,
      z = Float64Array.from(values),
      parent = new Int32Array(n).fill(-1),
      seen = new Uint8Array(n),
      order = [],
      heap = [];
    function push(v, i) {
      let k = heap.length;
      heap.push([v, i]);
      while (k) {
        const p = (k - 1) >> 1;
        if (heap[p][0] <= v) break;
        heap[k] = heap[p];
        k = p;
      }
      heap[k] = [v, i];
    }
    function pop() {
      const top = heap[0],
        v = heap.pop();
      if (heap.length) {
        let i = 0;
        while (i * 2 + 1 < heap.length) {
          let j = i * 2 + 1;
          if (j + 1 < heap.length && heap[j + 1][0] < heap[j][0]) j++;
          if (heap[j][0] >= v[0]) break;
          heap[i] = heap[j];
          i = j;
        }
        heap[i] = v;
      }
      return top;
    }
    for (let i = 0; i < n; i++)
      if (!Number.isFinite(z[i]))
        throw Error(
          "Recorte com lacunas/nodata. Selecione uma área coberta pelo raster.",
        );
    for (let y = 0; y < height; y++)
      for (let x = 0; x < width; x++)
        if (!x || !y || x === width - 1 || y === height - 1) {
          const i = y * width + x;
          seen[i] = 1;
          push(z[i], i);
        }
    while (heap.length) {
      const [, i] = pop();
      order.push(i);
      const x = i % width,
        y = Math.floor(i / width);
      for (let dy = -1; dy <= 1; dy++)
        for (let dx = -1; dx <= 1; dx++) {
          if (!dx && !dy) continue;
          const xx = x + dx,
            yy = y + dy;
          if (xx < 0 || yy < 0 || xx >= width || yy >= height) continue;
          const j = yy * width + xx;
          if (seen[j]) continue;
          seen[j] = 1;
          z[j] = Math.max(z[j], z[i]);
          parent[j] = i;
          push(z[j], j);
        }
    }
    const acc = new Float64Array(n).fill(cellArea),
      drain = new Float64Array(n);
    for (let k = order.length - 1; k >= 0; k--) {
      const i = order[k];
      if (parent[i] >= 0) acc[parent[i]] += acc[i];
    }
    const wet = new Uint8Array(n);
    let streams = 0;
    for (const i of order) {
      const stream = acc[i] >= threshold;
      if (stream) streams++;
      drain[i] = stream ? z[i] : parent[i] >= 0 ? drain[parent[i]] : NaN;
      const h = z[i] - drain[i];
      if (Number.isFinite(h) && h <= level) wet[i] = 1;
    }
    if (!streams)
      throw Error(
        "Nenhuma drenagem encontrada. Amplie a área ou reduza a área contribuinte.",
      );
    const [west, south, east, north] = bbox,
      dx = (east - west) / width,
      dy = (north - south) / height,
      features = [];
    for (let y = 0; y < height; y++) {
      let start = -1;
      for (let x = 0; x <= width; x++) {
        const w = x < width && wet[y * width + x];
        if (w && start < 0) start = x;
        if (!w && start >= 0) {
          const a = west + start * dx,
            b = west + x * dx,
            c = north - (y + 1) * dy,
            d = north - y * dy;
          features.push({
            type: "Feature",
            properties: { modelo: "HAND experimental", nivel_m: level },
            geometry: {
              type: "Polygon",
              coordinates: [
                [
                  [a, c],
                  [b, c],
                  [b, d],
                  [a, d],
                  [a, c],
                ],
              ],
            },
          });
          start = -1;
        }
      }
    }
    return { type: "FeatureCollection", features };
  }
  function writeGeoTIFF(t) {
    const { width, height, bbox, values } = t;
    if (values.length !== width * height)
      throw Error("Dimensões do terreno inválidas.");
    const count = 14,
      ifdEnd = 8 + 2 + count * 12 + 4,
      scaleOffset = (ifdEnd + 7) & ~7,
      tieOffset = scaleOffset + 24,
      keysOffset = tieOffset + 48,
      pixelsOffset = keysOffset + 32;
    const buffer = new ArrayBuffer(pixelsOffset + values.length * 4),
      v = new DataView(buffer);
    v.setUint16(0, 0x4949, true);
    v.setUint16(2, 42, true);
    v.setUint32(4, 8, true);
    v.setUint16(8, count, true);
    const tags = [
      [256, 4, 1, width],
      [257, 4, 1, height],
      [258, 3, 1, 32],
      [259, 3, 1, 1],
      [262, 3, 1, 1],
      [273, 4, 1, pixelsOffset],
      [277, 3, 1, 1],
      [278, 4, 1, height],
      [279, 4, 1, values.length * 4],
      [284, 3, 1, 1],
      [339, 3, 1, 3],
      [33550, 12, 3, scaleOffset],
      [33922, 12, 6, tieOffset],
      [34735, 3, 16, keysOffset],
    ];
    tags.forEach(([tag, type, n, value], i) => {
      const o = 10 + i * 12;
      v.setUint16(o, tag, true);
      v.setUint16(o + 2, type, true);
      v.setUint32(o + 4, n, true);
      if (type === 3 && n === 1) v.setUint16(o + 8, value, true);
      else v.setUint32(o + 8, value, true);
    });
    const [w, s, e, n] = bbox;
    [(e - w) / width, (n - s) / height, 0].forEach((x, i) =>
      v.setFloat64(scaleOffset + i * 8, x, true),
    );
    [0, 0, 0, w, n, 0].forEach((x, i) =>
      v.setFloat64(tieOffset + i * 8, x, true),
    );
    [1, 1, 0, 3, 1024, 0, 1, 2, 1025, 0, 1, 1, 2048, 0, 1, 4326].forEach(
      (x, i) => v.setUint16(keysOffset + i * 2, x, true),
    );
    values.forEach((x, i) => v.setFloat32(pixelsOffset + i * 4, x, true));
    return buffer;
  }
  const api = { hand, writeGeoTIFF };
  if (typeof module !== "undefined") module.exports = api;
  else root.CenarioTerreno = api;
})(typeof self !== "undefined" ? self : this);
