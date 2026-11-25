# Testes de interação

Execute `npm ci` e `npx playwright install chromium` nesta pasta; depois `npm test`.
O teste usa Leaflet real e snapshots reduzidos de previsão, intercepta rede externa e simula falha/recuperação. Cobre quatro mapas em 390 e 1440 px, navegação de cidades, atualização das réguas e controles móveis de evacuação. A geometria sintética de evacuação é explicitamente uma prévia não validada. Não valida modelos hidrológicos nem atualidade de previsões.

`SITE_ROOT` permite testar o diretório de publicação otimizado. `CHROME_PATH` e `LEAFLET_DIR` permitem usar instalações locais. `readyMs` inclui recuperação deliberada de falha de rede; não é uma medida de carregamento inicial.

Para o módulo configurável para qualquer município, execute `npm run test:municipal`.
Esse teste cobre exemplo de Santa Tereza, importação de cenário municipal, capacidade,
persistência, invalidação, layout móvel, importação GeoTIFF, HAND em worker e
exportação de alturas Float32. As bibliotecas externas são interceptadas e servidas
pelas dependências locais; não depende dos CDNs nem da rede de mapas.

`npm run test:municipal:audit` executa os casos adversos encontrados na auditoria:
recorte da área de interesse, GeoJSON malformado, entrada inválida de capacidade,
edição e exclusão pelo mapa e reabertura de camadas opcionais vazias. Inclui também
os testes do motor. `npm test` executa as três suítes de navegador em sequência.
