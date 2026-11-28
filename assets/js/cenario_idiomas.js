/* Idiomas do fluxo principal do cenário municipal (os três passos, os avisos e o resultado).
   A página é escrita em português; aqui cada frase tem a versão em inglês e em espanhol.
   As opções avançadas ficam em português. tests/test_cenario_idiomas.cjs. */
(function (raiz) {
  "use strict";
  const IDIOMAS = ["pt", "en", "es"];
  // [frase em português (expressão regular, frase inteira), inglês, espanhol]; $1, $2… repetem os números
  const N = "([\\d.,]+)";
  const FRASES = [
    // cabeçalho e passos
    [
      "PREVINE · APOIO À DECISÃO",
      "PREVINE · DECISION SUPPORT",
      "PREVINE · APOYO A LA DECISIÓN",
    ],
    [
      "Planejamento municipal de evacuação",
      "Municipal evacuation planning",
      "Planificación municipal de evacuación",
    ],
    [
      "Ver o estudo pronto de Santa Tereza",
      "See the finished Santa Tereza study",
      "Ver el estudio de Santa Tereza",
    ],
    ["Calcule em 3 passos", "Calculate in 3 steps", "Calcule en 3 pasos"],
    [
      "Para qualquer cidade do mundo. A página baixa o mapa das ruas e das casas, o relevo e os rios, e mostra quantas pessoas chegam a pé a um lugar seguro no tempo escolhido.",
      "For any city in the world. The page downloads the map of streets and houses, the terrain and the rivers, and shows how many people reach a safe place on foot within the chosen time.",
      "Para cualquier ciudad del mundo. La página descarga el mapa de calles y casas, el relieve y los ríos, y muestra cuántas personas llegan a pie a un lugar seguro en el tiempo elegido.",
    ],
    ["Onde fica\\?", "Where is it?", "¿Dónde queda?"],
    ["Procurar", "Search", "Buscar"],
    [
      "Qual parte da cidade\\?",
      "Which part of the city?",
      "¿Qué parte de la ciudad?",
    ],
    [
      "Aproxime o mapa até ver só a parte que inunda \\(o centro, um bairro perto do rio\\) e toque em “Usar esta parte do mapa”.",
      "Zoom the map until you see only the part that floods (downtown, a neighborhood by the river) and tap “Use this part of the map”.",
      "Acerque el mapa hasta ver solo la parte que se inunda (el centro, un barrio junto al río) y toque “Usar esta parte del mapa”.",
    ],
    [
      "Usar esta parte do mapa",
      "Use this part of the map",
      "Usar esta parte del mapa",
    ],
    [
      "Quanto o rio sobe e quanto tempo a pé\\?",
      "How much does the river rise, and how long on foot?",
      "¿Cuánto sube el río y cuánto tiempo a pie?",
    ],
    ["Rio sobe \\(m\\)", "River rises (m)", "El río sube (m)"],
    ["Tempo a pé \\(min\\)", "Time on foot (min)", "Tiempo a pie (min)"],
    [
      "O quanto o rio sobe vem da régua ou de uma cheia conhecida: a ferramenta não prevê a cheia.",
      "How much the river rises comes from the river gauge or a known flood: the tool does not forecast floods.",
      "Cuánto sube el río viene de la regla limnimétrica o de una crecida conocida: la herramienta no pronostica la crecida.",
    ],
    ["Calcular", "Calculate", "Calcular"],
    [
      "Comece pelo passo 1: escreva o nome da cidade e toque em Procurar.",
      "Start with step 1: type the city name and tap Search.",
      "Empiece por el paso 1: escriba el nombre de la ciudad y toque Buscar.",
    ],
    [
      "Ou veja um exemplo pronto:",
      "Or see a ready example:",
      "O vea un ejemplo listo:",
    ],
    [
      "Estudo técnico para planejar e comparar cenários, com bases abertas que podem ter falhas. Não é instrução de evacuação à população.",
      "Technical study to plan and compare scenarios, using open data that may have gaps. It is not an evacuation instruction for the public.",
      "Estudio técnico para planificar y comparar escenarios, con datos abiertos que pueden tener fallas. No es una instrucción de evacuación a la población.",
    ],
    ["Opções avançadas", "Advanced options", "Opciones avanzadas"],
    [
      "importar arquivos do município, relevo, bloqueios, pontos de encontro e capacidade, salvar e relatórios",
      "import municipal files, terrain, blockages, meeting points and capacity, save and reports (in Portuguese)",
      "importar archivos del municipio, relieve, bloqueos, puntos de encuentro y capacidad, guardar e informes (en portugués)",
    ],
    [
      "Nome da cidade, bairro ou endereço",
      "City, neighborhood or address",
      "Ciudad, barrio o dirección",
    ],
    [
      "Ex\\.: Lajeado, Brasil",
      "E.g.: Valencia, Spain",
      "Ej.: Valencia, España",
    ],
    // legenda do mapa
    ["inundação", "flooding", "inundación"],
    ["edificação", "building", "edificación"],
    [
      "chega a um ponto no tempo",
      "reaches a point in time",
      "llega a un punto a tiempo",
    ],
    ["não chega no tempo", "does not reach in time", "no llega a tiempo"],
    [
      "chega, mas a rota passa pela mancha",
      "reaches, but the route crosses the flood",
      "llega, pero la ruta cruza la mancha",
    ],
    ["ponto de encontro", "meeting point", "punto de encuentro"],
    ["bloqueio", "blockage", "bloqueo"],
    ["caminho", "route", "camino"],
    // busca e área
    [
      "Escreva o nome do lugar.",
      "Type the name of the place.",
      "Escriba el nombre del lugar.",
    ],
    ["Procurando “(.+)”…", "Searching for “$1”…", "Buscando “$1”…"],
    [
      "Lugar encontrado. Agora aproxime o mapa da parte que inunda e toque em “Usar esta parte do mapa”.",
      "Place found. Now zoom the map to the part that floods and tap “Use this part of the map”.",
      "Lugar encontrado. Ahora acerque el mapa a la parte que se inunda y toque “Usar esta parte del mapa”.",
    ],
    [
      "Nenhum lugar encontrado com esse nome. Tente incluir o estado ou o país.",
      "No place found with that name. Try adding the state or country.",
      "No se encontró ningún lugar con ese nombre. Pruebe agregando la provincia o el país.",
    ],
    [
      "A busca de lugares não respondeu. Tente de novo em instantes ou aproxime o mapa e desenhe a área.",
      "The place search did not respond. Try again in a moment.",
      "La búsqueda de lugares no respondió. Intente de nuevo en un momento.",
    ],
    ["Ver no mapa", "Show on map", "Ver en el mapa"],
    [
      "Usar o limite como área",
      "Use its boundary as the area",
      "Usar su límite como área",
    ],
    [
      "Primeiro escreva o nome da cidade no passo 1 e toque em Procurar.",
      "First type the city name in step 1 and tap Search.",
      "Primero escriba el nombre de la ciudad en el paso 1 y toque Buscar.",
    ],
    [
      "Área marcada: cerca de " + N + " km².",
      "Area marked: about $1 km².",
      "Área marcada: unos $1 km².",
    ],
    [
      "Área marcada \\(cerca de " +
        N +
        " km²\\). Agora informe quanto o rio sobe e toque em Calcular.",
      "Area marked (about $1 km²). Now enter how much the river rises and tap Calculate.",
      "Área marcada (unos $1 km²). Ahora indique cuánto sube el río y toque Calcular.",
    ],
    [
      "A área na tela é grande demais.",
      "The area on screen is too large.",
      "El área en pantalla es demasiado grande.",
    ],
    [
      "A área na tela tem cerca de " + N + " km².",
      "The area on screen is about $1 km².",
      "El área en pantalla tiene unos $1 km².",
    ],
    [
      "Aproxime o mapa até a parte que inunda \\(até " +
        N +
        " km²\\) e toque de novo.",
      "Zoom the map to the part that floods (up to $1 km²) and tap again.",
      "Acerque el mapa a la parte que se inunda (hasta $1 km²) y toque de nuevo.",
    ],
    [
      "Essa parte do mapa cruza a linha de data \\(longitude 180°\\). Arraste o mapa para um lado só dela e toque de novo.",
      "This part of the map crosses the date line (longitude 180°). Drag the map to one side of it and tap again.",
      "Esta parte del mapa cruza la línea de cambio de fecha (longitud 180°). Arrastre el mapa a un solo lado y toque de nuevo.",
    ],
    [
      "Informe quanto o rio sobe, em metros.",
      "Enter how much the river rises, in meters.",
      "Indique cuánto sube el río, en metros.",
    ],
    // download, relevo, rios
    [
      "Baixando ruas e edificações do OpenStreetMap…",
      "Downloading streets and buildings from OpenStreetMap…",
      "Descargando calles y edificaciones de OpenStreetMap…",
    ],
    [
      "Os servidores de consulta estão lentos. Baixando também do servidor oficial do OpenStreetMap…",
      "The query servers are slow. Also downloading from the official OpenStreetMap server…",
      "Los servidores de consulta están lentos. Descargando también del servidor oficial de OpenStreetMap…",
    ],
    [
      "Baixando do servidor oficial do OpenStreetMap: parte " +
        N +
        " de " +
        N +
        "…",
      "Downloading from the official OpenStreetMap server: part $1 of $2…",
      "Descargando del servidor oficial de OpenStreetMap: parte $1 de $2…",
    ],
    [
      "O mapa das ruas e das casas não chegou em 2 minutos. Tente uma área menor \\(aproxime mais o mapa\\) ou tente de novo em alguns minutos.",
      "The map of streets and houses did not arrive within 2 minutes. Try a smaller area (zoom in more) or try again in a few minutes.",
      "El mapa de calles y casas no llegó en 2 minutos. Pruebe un área más pequeña (acerque más el mapa) o intente de nuevo en unos minutos.",
    ],
    [
      "Baixado do OpenStreetMap: " + N + " ruas e " + N + " edificações.",
      "Downloaded from OpenStreetMap: $1 streets and $2 buildings.",
      "Descargado de OpenStreetMap: $1 calles y $2 edificaciones.",
    ],
    [
      "Falta a mancha de inundação \\(etapa 5\\).",
      "The flood area is still missing.",
      "Falta la mancha de inundación.",
    ],
    [
      "Essa área tem (ruas|edificações) demais para o cálculo \\((.+)\\). Aproxime o mapa da parte que inunda, toque em “Usar esta parte do mapa” e baixe de novo.",
      "This area has too many $1 for the calculation ($2). Zoom to the part that floods and tap “Use this part of the map” again.",
      "Esta área tiene demasiadas $1 para el cálculo ($2). Acerque el mapa a la parte que se inunda y toque “Usar esta parte del mapa” de nuevo.",
    ],
    [
      "Buscando o relevo da área…",
      "Fetching the terrain of the area…",
      "Buscando el relieve del área…",
    ],
    [
      "Buscando os rios mapeados da área…",
      "Fetching the mapped rivers of the area…",
      "Buscando los ríos mapeados del área…",
    ],
    [
      "Buscando os rios no servidor oficial do OpenStreetMap…",
      "Fetching rivers from the official OpenStreetMap server…",
      "Buscando los ríos en el servidor oficial de OpenStreetMap…",
    ],
    [
      "Buscando os rios no servidor oficial do OpenStreetMap: parte " +
        N +
        " de " +
        N +
        "…",
      "Fetching rivers from the official OpenStreetMap server: part $1 of $2…",
      "Buscando los ríos en el servidor oficial de OpenStreetMap: parte $1 de $2…",
    ],
    [
      "Condicionando terreno e calculando HAND experimental…",
      "Preparing the terrain and computing the flood area…",
      "Preparando el relieve y calculando la mancha…",
    ],
    [
      "Mancha gerada pelo terreno, a partir dos rios mapeados.",
      "Flood area generated from the terrain, starting from the mapped rivers.",
      "Mancha generada por el relieve, a partir de los ríos mapeados.",
    ],
    [
      "Mancha gerada pelo terreno. Não foi possível ler os rios do OpenStreetMap: a drenagem saiu só do relevo dentro da área e pode falhar para rio que vem de fora.",
      "Flood area generated from the terrain. The OpenStreetMap rivers could not be read: drainage came only from the terrain inside the area and may miss a river coming from outside.",
      "Mancha generada por el relieve. No se pudieron leer los ríos de OpenStreetMap: el drenaje salió solo del relieve dentro del área y puede fallar para un río que viene de afuera.",
    ],
    [
      "Confira no mapa e ajuste o nível acima do rio antes de calcular.",
      "Check it on the map and adjust the level above the river before calculating.",
      "Revísela en el mapa y ajuste el nivel sobre el río antes de calcular.",
    ],
    [
      "Construindo a rede, aplicando bloqueios e calculando destinos…",
      "Building the street network and calculating meeting points…",
      "Construyendo la red de calles y calculando puntos de encuentro…",
    ],
    [
      "Ainda calculando… Áreas com muitas ruas e edificações podem levar alguns minutos. Uma área menor calcula mais rápido.",
      "Still calculating… Areas with many streets and buildings can take a few minutes. A smaller area is faster.",
      "Todavía calculando… Áreas con muchas calles y edificaciones pueden tardar unos minutos. Un área más pequeña es más rápida.",
    ],
    [
      "Cenário calculado. Toque numa edificação no mapa para ver o caminho dela.",
      "Scenario calculated. Tap a building on the map to see its route.",
      "Escenario calculado. Toque una edificación en el mapa para ver su camino.",
    ],
    [
      "O OpenStreetMap não respondeu agora. Tente de novo em alguns minutos ou importe os arquivos do município.",
      "OpenStreetMap did not respond now. Try again in a few minutes.",
      "OpenStreetMap no respondió ahora. Intente de nuevo en unos minutos.",
    ],
    [
      "Exemplo carregado: Santa Tereza, com uma mancha de inundação simulada \\(não é a cheia observada\\). Agora toque em Calcular.",
      "Example loaded: Santa Tereza, with a simulated flood area (not the observed flood). Now tap Calculate.",
      "Ejemplo cargado: Santa Tereza, con una mancha de inundación simulada (no es la crecida observada). Ahora toque Calcular.",
    ],
    // resultado
    ["Resultado · (.+)", "Result · $1", "Resultado · $1"],
    ["pontos de encontro", "meeting points", "puntos de encuentro"],
    [
      "de " + N + " pessoas chegam a um ponto em até " + N + " min a pé",
      "of $1 people reach a point within $2 min on foot",
      "de $1 personas llegan a un punto en hasta $2 min a pie",
    ],
    [
      N + " de " + N + " edificações atendidas.",
      "$1 of $2 buildings reach a point.",
      "$1 de $2 edificaciones llegan a un punto.",
    ],
    [
      N +
        " (edificação não chega|edificações não chegam) a nenhum ponto no tempo escolhido \\(em vermelho no mapa\\). Aumente o tempo, cadastre outro ponto ou preveja transporte.",
      "$1 building(s) do not reach any point in the chosen time (red on the map). Increase the time, add another point or plan transport.",
      "$1 edificación(es) no llegan a ningún punto en el tiempo elegido (en rojo en el mapa). Aumente el tiempo, agregue otro punto o prevea transporte.",
    ],
    [
      N +
        " (edificação tem|edificações têm) a rota passando por dentro da mancha depois de estar fora dela, por exemplo numa ponte \\(em amarelo no mapa\\)\\. Confira se essa passagem estará aberta durante a retirada\\.",
      "$1 building(s) have a route that goes back into the flood after leaving it, for example over a bridge (yellow on the map). Check that this crossing will be open during the evacuation.",
      "$1 edificación(es) tienen la ruta pasando por dentro de la mancha después de haber salido, por ejemplo por un puente (en amarillo en el mapa). Verifique que ese paso esté abierto durante la evacuación.",
    ],
    [
      "Só " +
        N +
        " (edificação|edificações) na área que precisa de ponto de encontro. Confira no mapa se marcou a parte certa da cidade \\(a que inunda, com casas\\) e se a mancha azul encosta nela.",
      "Only $1 building(s) in the area need a meeting point. Check on the map that you marked the right part of the city (the part that floods, with houses) and that the blue area touches it.",
      "Solo $1 edificación(es) en el área necesitan un punto de encuentro. Revise en el mapa si marcó la parte correcta de la ciudad (la que se inunda, con casas) y si la mancha azul la toca.",
    ],
    [
      "População estimada em " + N + " edificações \\(sem cadastro\\).",
      "Population estimated for $1 buildings (no census data).",
      "Población estimada en $1 edificaciones (sin catastro).",
    ],
    [
      "Há pontos sem capacidade informada: o resultado não garante que há espaço para todos.",
      "Some points have no stated capacity: the result does not guarantee room for everyone.",
      "Hay puntos sin capacidad informada: el resultado no garantiza espacio para todos.",
    ],
    [
      "As capacidades cadastradas foram respeitadas.",
      "The registered capacities were respected.",
      "Se respetaron las capacidades registradas.",
    ],
    [
      "A escolha dos pontos é aproximada; pode existir uma solução melhor.",
      "The choice of points is approximate; a better solution may exist.",
      "La elección de los puntos es aproximada; puede existir una solución mejor.",
    ],
    [
      "Toque numa linha para ver o ponto no mapa; toque numa edificação para ver o caminho dela.",
      "Tap a row to see the point on the map; tap a building to see its route.",
      "Toque una fila para ver el punto en el mapa; toque una edificación para ver su camino.",
    ],
    ["Nº", "No.", "N.º"],
    ["Ponto de encontro", "Meeting point", "Punto de encuentro"],
    ["Pessoas", "People", "Personas"],
    ["Capacidade", "Capacity", "Capacidad"],
    ["Não informada", "Not stated", "No informada"],
    [
      "Sugerido pelo cálculo",
      "Suggested by the calculation",
      "Sugerido por el cálculo",
    ],
    ["Perto de (.+)", "Near $1", "Cerca de $1"],
    [
      "Nenhuma edificação da área fica na mancha nem a menos de " +
        N +
        " m dela: com o rio subindo " +
        N +
        " m, ninguém aqui precisa sair\\. Para outra cheia, mude quanto o rio sobe e calcule de novo\\.",
      "No building in the area is in the flood area or less than $1 m from it: with the river rising $2 m, nobody here needs to leave. For another flood, change how much the river rises and calculate again.",
      "Ninguna edificación del área queda en la mancha ni a menos de $1 m de ella: con el río subiendo $2 m, nadie aquí necesita salir. Para otra crecida, cambie cuánto sube el río y calcule de nuevo.",
    ],
    [
      "A área tinha casas e ruas demais para o cálculo e foi reduzida para cerca de " +
        N +
        " km² em volta do centro\\.",
      "The area had too many houses and streets for the calculation and was reduced to about $1 km² around its center.",
      "El área tenía demasiadas casas y calles para el cálculo y se redujo a unos $1 km² alrededor del centro.",
    ],
    [
      "Nenhum lugar seguro dentro da área marcada: ela fica toda na mancha ou a menos de " +
        N +
        " m dela\\. Marque uma área maior, que inclua terreno mais alto, ou confira quanto o rio sobe\\.",
      "No safe place inside the marked area: all of it is in the flood area or less than $1 m from it. Mark a larger area that includes higher ground, or check how much the river rises.",
      "Ningún lugar seguro dentro del área marcada: toda queda en la mancha o a menos de $1 m de ella. Marque un área más grande, que incluya terreno más alto, o revise cuánto sube el río.",
    ],
    [
      "Quanto dá para confiar na mancha\\?",
      "How far can the flood area be trusted?",
      "¿Cuánto se puede confiar en la mancha?",
    ],
    [
      "Testada na cheia de maio de 2024 em 9 cidades do vale do Taquari, contra a área atingida do Mapa Único do RS: com o rio subindo de 16 a 24 m, a mancha pegou de 67% a 98% das casas atingidas \\(8 das 9 cidades acima de 77%\\).",
      "Tested on the May 2024 flood in 9 towns of the Taquari valley (Brazil), against the state's mapped affected area: with the river rising 16 to 24 m, the flood area caught 67% to 98% of the affected houses (above 77% in 8 of the 9 towns).",
      "Probada en la crecida de mayo de 2024 en 9 ciudades del valle del Taquari (Brasil), contra el área afectada mapeada por el estado: con el río subiendo de 16 a 24 m, la mancha detectó del 67% al 98% de las casas afectadas (más del 77% en 8 de las 9 ciudades).",
    ],
    [
      "Das casas que ela marca, de 72% a 84% foram mesmo atingidas.",
      "Of the houses it marks, 72% to 84% were really affected.",
      "De las casas que marca, del 72% al 84% fueron realmente afectadas.",
    ],
    [
      "Não prevê a água que vem da chuva longe do rio, de diques que rompem ou de enxurradas, e é menos precisa em planícies. Um modelo de terreno do município \\(MDT\\) melhora o resultado.",
      "It does not predict water from rain far from the river, levee breaches or flash floods, and is less precise on flat plains. A municipal terrain model (DTM) improves the result.",
      "No predice el agua de lluvia lejos del río, de diques que se rompen o de riadas, y es menos precisa en llanuras. Un modelo de terreno del municipio (MDT) mejora el resultado.",
    ],
    [
      "Baixar planilha por edificação",
      "Download spreadsheet by building",
      "Descargar planilla por edificación",
    ],
    [
      "Baixar rotas \\(GeoJSON\\)",
      "Download routes (GeoJSON)",
      "Descargar rutas (GeoJSON)",
    ],
    [
      "Copiar link deste cenário",
      "Copy link to this scenario",
      "Copiar enlace de este escenario",
    ],
    ["Link copiado", "Link copied", "Enlace copiado"],
    ["Copie o link abaixo", "Copy the link below", "Copie el enlace de abajo"],
    [
      "O link refaz o cálculo com o mesmo lugar, a mesma área, o mesmo nível do rio e o mesmo tempo, com os dados do mapa do dia em que for aberto.",
      "The link redoes the calculation with the same place, area, river level and time, using the map data of the day it is opened.",
      "El enlace rehace el cálculo con el mismo lugar, la misma área, el mismo nivel del río y el mismo tiempo, con los datos del mapa del día en que se abra.",
    ],
    [
      "Cenário aberto pelo link. Calculando…",
      "Scenario opened from the link. Calculating…",
      "Escenario abierto desde el enlace. Calculando…",
    ],
    [
      "O link tem uma área inválida ou grande demais. Comece pelo passo 1.",
      "The link has an invalid or too large area. Start with step 1.",
      "El enlace tiene un área inválida o demasiado grande. Empiece por el paso 1.",
    ],
    [
      "inundação simulada \\(rio \\+" + N + " m\\)",
      "simulated flooding (river +$1 m)",
      "inundación simulada (río +$1 m)",
    ],
    [
      N + " edificaç(?:ão|ões): Sem destino alcançável no tempo escolhido",
      "$1 building(s): no meeting point reachable in the chosen time",
      "$1 edificación(es): sin destino alcanzable en el tiempo elegido",
    ],
    [
      N + " edificaç(?:ão|ões): Sem acesso à rede após os bloqueios",
      "$1 building(s): no street access after the blockages",
      "$1 edificación(es): sin acceso a la red tras los bloqueos",
    ],
    [
      N + " edificaç(?:ão|ões): Sem capacidade disponível ou informada",
      "$1 building(s): no available or stated capacity",
      "$1 edificación(es): sin capacidad disponible o informada",
    ],
    [
      "Ponto não usado: (.+) — Fora dos critérios de elegibilidade, afastamento ou acesso à rede\\.",
      "Point not used: $1 — outside the eligibility, distance or street-access criteria.",
      "Punto no usado: $1 — fuera de los criterios de elegibilidad, distancia o acceso a la red.",
    ],
  ].map(([pt, en, es]) => [new RegExp("^" + pt + "$"), en, es]);

  // abre em português; muda pelo endereço (?lang=en) ou pela escolha da pessoa, que fica guardada
  function idioma() {
    try {
      const q = new URLSearchParams(location.search).get("lang");
      if (IDIOMAS.includes(q)) return q;
      const salvo = localStorage.getItem("previne-idioma");
      if (IDIOMAS.includes(salvo)) return salvo;
    } catch (e) {}
    return "pt";
  }
  let atual = "pt";
  // traduz frase por frase; o que não estiver na tabela fica em português
  function tr(texto, lang = atual) {
    if (lang === "pt" || texto == null) return texto;
    const k = lang === "en" ? 1 : 2,
      um = (f) => {
        const limpo = f.replace(/\s+/g, " ").trim();
        for (const linha of FRASES)
          if (linha[0].test(limpo)) return limpo.replace(linha[0], linha[k]);
        return f;
      },
      inteiro = um(String(texto));
    if (inteiro !== String(texto)) return inteiro;
    return String(texto)
      .split(/(?<=[.…])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])/)
      .map(um)
      .join(" ");
  }
  const original = new WeakMap();
  // troca os textos fixos dentro dos elementos indicados (guarda o português para voltar)
  function aplica(raizes, lang = atual) {
    atual = lang;
    for (const r of raizes) {
      if (!r) continue;
      const w = document.createTreeWalker(r, NodeFilter.SHOW_TEXT);
      for (let n = w.nextNode(); n; n = w.nextNode()) {
        if (!n.nodeValue.trim()) continue;
        if (!original.has(n)) original.set(n, n.nodeValue);
        const pt = original.get(n),
          novo = tr(pt, lang);
        n.nodeValue = novo === pt ? pt : " " + novo + " ";
      }
      for (const el of r.querySelectorAll("[placeholder],[aria-label]"))
        for (const a of ["placeholder", "aria-label"])
          if (el.hasAttribute(a)) {
            const chave = "data-pt-" + a;
            if (!el.hasAttribute(chave))
              el.setAttribute(chave, el.getAttribute(a));
            el.setAttribute(a, tr(el.getAttribute(chave), lang));
          }
    }
    document.documentElement.lang = lang === "pt" ? "pt-BR" : lang;
  }
  const api = {
    IDIOMAS,
    idioma,
    tr,
    aplica,
    get atual() {
      return atual;
    },
    set atual(v) {
      atual = v;
    },
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else raiz.CenarioIdioma = api;
})(typeof self !== "undefined" ? self : this);
