// Keep imported computation modules aligned with the page's asset versions.
importScripts(
  "cenario_engine.js" + self.location.search,
  "cenario_terreno.js" + self.location.search,
);
self.onmessage = (e) => {
  const id = e.data?.id;
  try {
    const { type, data, options } = e.data;
    const result =
      type === "hand"
        ? CenarioTerreno.hand(...data)
        : CenarioEngine.plan(data, options);
    self.postMessage({ id, result });
  } catch (error) {
    self.postMessage({ id, error: error.message });
  }
};
