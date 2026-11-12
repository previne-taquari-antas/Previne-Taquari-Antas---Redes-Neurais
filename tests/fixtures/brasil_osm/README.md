# Recortes OSM para testes municipais

Seis snapshots de vias (`way[highway]`) e edificações (`way[building]`) do OpenStreetMap,
obtidos via Overpass em 2026-11-07. Os arquivos JSON gzip incluem município, bbox,
consulta exata, endpoint, data de coleta e timestamp da base OSM.

© OpenStreetMap contributors. Dados sob ODbL 1.0:
https://www.openstreetmap.org/copyright
https://opendatacommons.org/licenses/odbl/1-0/

São amostras de feições do tipo way, incluindo segmentos que intersectam o bbox;
não representam um cadastro completo de cada cidade e não incluem todas as
relações multipoligonais. Capacidade, população, destinos, bloqueios e inundação
usados nos testes são sintéticos. Nenhum destino é apresentado como abrigo oficial.

`node tests/test_cenario_osm_brasil.cjs` executa os casos offline sobre os snapshots.
O relatório é gravado em `$BRASIL_OSM_REPORT` ou no diretório temporário do sistema.
Para inspecionar um arquivo: `gzip -dc tests/fixtures/brasil_osm/manaus.json.gz`.
