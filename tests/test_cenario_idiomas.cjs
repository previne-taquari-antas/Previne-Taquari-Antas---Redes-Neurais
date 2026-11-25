// Traduções do fluxo principal do cenário municipal.
const test = require("node:test"),
  assert = require("node:assert/strict"),
  I = require("../assets/js/cenario_idiomas.js");

test("frases fixas e com números", () => {
  assert.equal(I.tr("Calcular", "en"), "Calculate");
  assert.equal(I.tr("Onde fica?", "es"), "¿Dónde queda?");
  assert.equal(
    I.tr("Área marcada: cerca de 2,2 km².", "en"),
    "Area marked: about 2,2 km².",
  );
  assert.equal(
    I.tr("Baixando do servidor oficial do OpenStreetMap: parte 3 de 9…", "es"),
    "Descargando del servidor oficial de OpenStreetMap: parte 3 de 9…",
  );
  assert.equal(
    I.tr("de 1,593 pessoas chegam a um ponto em até 20 min a pé", "en"),
    "of 1,593 people reach a point within 20 min on foot",
  );
});

test("aviso com várias frases é traduzido frase a frase", () => {
  const pt =
    "Mancha gerada pelo terreno, a partir dos rios mapeados. Confira no mapa e ajuste o nível acima do rio antes de calcular.";
  assert.equal(
    I.tr(pt, "en"),
    "Flood area generated from the terrain, starting from the mapped rivers. Check it on the map and adjust the level above the river before calculating.",
  );
});

test("português fica igual e o que não está na tabela não some", () => {
  assert.equal(I.tr("Calcular", "pt"), "Calcular");
  assert.equal(
    I.tr("Frase que não existe na tabela.", "en"),
    "Frase que não existe na tabela.",
  );
  assert.equal(
    I.tr("Perto de Rua Júlio de Castilhos", "en"),
    "Near Rua Júlio de Castilhos",
  );
});

test("motivos do cálculo", () => {
  assert.equal(
    I.tr("2 edificações: Sem destino alcançável no tempo escolhido", "en"),
    "2 building(s): no meeting point reachable in the chosen time",
  );
  assert.equal(
    I.tr(
      "Ponto não usado: Ginásio de Esportes — Fora dos critérios de elegibilidade, afastamento ou acesso à rede.",
      "es",
    ),
    "Punto no usado: Ginásio de Esportes — fuera de los criterios de elegibilidad, distancia o acceso a la red.",
  );
});
