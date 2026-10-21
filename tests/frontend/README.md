# Testes de interação

Execute `npm ci` e `npx playwright install chromium` nesta pasta; depois `npm test`.
O teste usa Leaflet real e snapshots reduzidos de previsão, intercepta rede externa e simula falha/recuperação. Cobre quatro mapas em 390 e 1440 px, navegação de cidades, atualização das réguas e controles móveis de evacuação. A geometria sintética de evacuação é explicitamente uma prévia não validada. Não valida modelos hidrológicos nem atualidade de previsões.

`SITE_ROOT` permite testar o diretório de publicação otimizado. `CHROME_PATH` e `LEAFLET_DIR` permitem usar instalações locais. `readyMs` inclui recuperação deliberada de falha de rede; não é uma medida de carregamento inicial.
