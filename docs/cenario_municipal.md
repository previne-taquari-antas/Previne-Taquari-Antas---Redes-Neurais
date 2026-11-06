# Planejamento municipal de evacuação

Entrada: `cenario_municipal.html`, também acessível pelo botão no topo de `pontos_encontro.html`.
O módulo independe da lista de municípios do estudo legado. Santa Tereza é apenas um exemplo carregável.

## Executar

```sh
python scripts/servir_cenario.py --port 8000
```

Abra http://localhost:8000/cenario_municipal.html. Python 3.9+; o serviço não exige bibliotecas adicionais. Ele serve os arquivos e encaminha somente tiles Copernicus com identificadores válidos, preservando requisições de intervalo de bytes. Não recebe URLs arbitrárias ou dados municipais. Por padrão escuta apenas localhost.

Também funciona em hospedagem estática (incluindo GitHub Pages). Caso a fonte Copernicus impeça leitura pelo navegador por CORS, a interface apresenta links para download e importação. O recorte é aplicado ao importar o arquivo com a área de interesse definida. Para obtenção automática sem esse impedimento, use o serviço incluído. Mapas e leitores de formatos dependem de conexão aos CDNs indicados no HTML.

## Fluxo municipal

1. Identifique o município e importe/desenhe a área de interesse. Importe vias e edificações.
2. Defina tempo máximo de deslocamento, velocidade e estimativa populacional para edificações sem cadastro.
3. Desenhe ou importe bloqueios por ponto (15 m), linha ou polígono. É possível editar e excluir desenhos pelo mapa.
4. Importe uma mancha, desenhe-a ou gere HAND a partir do terreno. Informe natureza, fonte e referência do cenário. Selecione se as vias inundadas já estão indisponíveis.
5. Importe/desenhe destinos e áreas elegíveis. Cadastre nome, tipo (ponto de encontro/abrigo), capacidade e ocupação atual.
6. Calcule, examine as rotas clicando nas edificações e exporte CSV ou GeoJSON. Salve as predefinições em JSON para reabrir depois.

Alterações invalidam o resultado e as exportações até novo cálculo. Resultados de cálculos iniciados antes de uma alteração são descartados. O serviço não armazena os cadastros; arquivos e relatórios permanecem no dispositivo. Tiles Copernicus são solicitados ao provedor público; o mapa-base usa OpenStreetMap e os leitores são obtidos por CDN.

## Contrato dos dados

GeoJSON WGS84 (longitude, latitude) ou ZIP com um Shapefile completo (.shp, .shx, .dbf, .prj). Cada importação substitui somente a camada selecionada. Multipartes são aceitas. O desenho/editor do Leaflet suporta apenas geometrias simples; multipartes podem ser substituídas por importação.

| Camada | Geometria | Atributos |
| --- | --- | --- |
| Área / elegibilidade / inundação | Polygon, MultiPolygon | Fonte e referência registradas na interface |
| Vias | LineString, MultiLineString | highway, access, foot, layer, bridge, tunnel (opcionais) |
| Edificações | Point, Polygon, MultiPolygon | id; pessoas ou population ou ocupantes |
| Destinos | Point, Polygon, MultiPolygon | nome/name, tipo, capacidade/capacity, ocupacao/occupancy |
| Bloqueios | Point, linhas, polígonos | Geometria define a obstrução |

Edificações e destinos poligonais recebem um ponto representativo. Valide acessos reais; a ligação à rede é uma aproximação de até 150 m. Cruzamentos de vias no mesmo nível são divididos para construir a rede. Pontes/túneis não conectam em cruzamentos de níveis distintos; extremos compartilhados conectam acessos. `foot=no` e `access=no` são excluídos; as demais vias são filtradas pelas classes informadas. Edificações fora da área não entram na demanda. Trechos e ligações de acesso não atravessam bloqueios ou saem da área de interesse.

Capacidades conhecidas sempre são respeitadas, descontando ocupação atual. A opção de exigir capacidade informada exclui destinos sem capacidade — incluindo sugestões automáticas ainda não cadastradas. Sem essa exigência, esses destinos recebem pessoas, mas o resultado explicita que não há confirmação de espaço. Grupos de uma edificação não são divididos. A seleção e distribuição são heurísticas: podem deixar demanda sem atendimento mesmo quando outra distribuição seria possível; não há garantia de ótimo global. Não se calcula uma segunda etapa de transporte entre pontos de encontro e abrigos: o destino cadastrado é o destino direto da rota.

## Terreno e HAND

GeoTIFF EPSG:4326, alturas em metros, uma banda, até 100 MB. Projeções distintas devem ser convertidas antes da importação. O recorte é retangular; a área de interesse limita posteriormente o planejamento. O download pode compor até quatro tiles Copernicus GLO-30 e exporta GeoTIFF Float32 georreferenciado, preservando alturas fracionárias e negativas.

O modelo experimental usa preenchimento de depressões por priority-flood, encaminhamento D8, acumulação por área contribuinte e altura sobre a drenagem derivada. O nível informado é relativo à drenagem, não uma cota de régua. O raster é reduzido para até 320 × 320 células. Amplie o domínio para incluir a bacia contribuinte; bordas do recorte afetam o resultado. Nodata interrompe a geração. Copernicus é DSM (~30 m), não automaticamente um MDT adequado ao planejamento urbano. Não representa hidrodinâmica, remanso, propagação ou chegada da água. Exige validação e calibração locais.

O tempo de rota usa velocidade constante, inclusive nas subidas. Não é a janela até a água chegar. Sem excluir vias inundadas, a hipótese é evacuação antes da cheia; com a opção marcada, elas são removidas da rede. Destinos devem ficar fora da mancha, do afastamento, dos bloqueios e dentro das áreas elegíveis quando cadastradas. Não há validação de deslizamentos ou condições locais sem uma camada de bloqueios apropriada.

## Santa Tereza

O exemplo preserva a mancha modelada do projeto para set/2023 e identifica a revisão pendente no Arroio Marrecão. Não foi inventada uma geometria corretiva, nem se apresentou essa simulação como mancha observada ou máximo histórico validado. A cidade pode substituí-la pela camada revisada. O ginásio cadastrado é rejeitado quando não satisfaz os critérios do cenário.

## Limites e verificação

Até 25 MB por importação vetorial, 500 mil coordenadas por camada, 15 mil segmentos de entrada, 30 mil nós de rede e 300 destinos. Candidatos automáticos são amostrados em até aproximadamente 200 nós elegíveis. Para bases extensas, recorte antes de importar.

```sh
node --test tests/test_cenario_engine.cjs
cd tests/frontend
npm ci
npx playwright install chromium
npm run test:municipal
# Ou CHROME_PATH=/usr/bin/chromium npm run test:municipal
```

Testes cobrem capacidade/ocupação, conectividade, bloqueios, pontes, política de inundação, áreas elegíveis, rotas, validação de dados e HAND sintético; o navegador cobre exemplo, município próprio, persistência, atualização obrigatória e layout móvel. Não constituem validação hidrológica ou cartográfica. A obtenção real de um recorte Copernicus foi verificada com o serviço incluído.
