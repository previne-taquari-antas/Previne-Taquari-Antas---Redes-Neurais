importScripts("cenario_engine.js", "cenario_terreno.js");
self.onmessage = (e) => {
  try {
    const { type, id, data, options } = e.data;
    const result =
      type === "hand"
        ? CenarioTerreno.hand(...data)
        : CenarioEngine.plan(data, options);
    self.postMessage({ id, result });
  } catch (error) {
    self.postMessage({ id, error: error.message });
  }
};
