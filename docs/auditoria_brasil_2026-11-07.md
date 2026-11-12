# Auditoria ampliada · outras regiões e situações · 7/11/2026

A nova rodada usou dois agentes independentes e uma bateria de integração com
recortes geográficos reais. Foram testadas as cinco regiões brasileiras e
coordenadas nos hemisférios norte e sul. As correções foram submetidas novamente
aos casos que falharam e às regressões anteriores.

Reexecução de confirmação em **12/11/2026**: 104 testes sintéticos, 54 casos
sobre os snapshots OSM e 49 verificações de navegador passaram novamente,
além das 37 regressões anteriores. Os snapshots geográficos continuam sendo os
coletados em 7/11; não representam uma atualização cartográfica em 12/11.

## Dados reais e o que foi simulado

As vias e os contornos das edificações da tabela vieram do OpenStreetMap via
Overpass. São recortes de bairros, não testes de cidades inteiras. O código usa
essas geometrias reais, mas os pontos de destino, as capacidades, a ocupação,
a população por edificação, os bloqueios e as manchas são hipóteses sintéticas
para exercitar a ferramenta. Não se validou um plano municipal de evacuação.

| Recorte real | Vias extraídas | Feições de edificações extraídas | Casos após correção |
| --- | ---: | ---: | ---: |
| Manaus (AM) | 83 | 862 | 9/9 |
| Recife (PE) | 161 | 233 | 9/9 |
| Brasília (DF) | 237 | 152 | 9/9 |
| São Paulo (SP) | 385 | 593 | 9/9 |
| Curitiba (PR) | 225 | 624 | 9/9 |
| Macapá (AP), ao norte do Equador | 46 | 98 | 9/9 |
| **Total** | **1.137** | **2.562** | **54/54** |

Amostras obtidas em 7/11/2026, com timestamps OSM entre 03:26:51 e 03:27:51 UTC.
Os snapshots, bboxes, consultas e atribuição ODbL estão em
`tests/fixtures/brasil_osm/`. O teste é reproduzível offline.

Cada recorte teve: seleção automática; destino manual com capacidade ampla;
capacidade zero; capacidade restante reduzida por ocupação; capacidade desconhecida
em modo estrito; toda a área bloqueada; prazo de um minuto; restrição de área
elegível; e mancha hipotética tornando vias indisponíveis. Foram conferidos também
o limite de tempo, os totais populacionais e a consistência entre distância da
rota e tempo calculado.

## Cenários sintéticos e navegador

- **104/104 testes sintéticos do motor:** Boa Vista, Manaus, Recife, Brasília,
  São Paulo e Curitiba. Usam redes construídas, posicionadas nas coordenadas
  dessas cidades. Cobrem rotas alternativas, múltiplos bloqueios, áreas com furos,
  ilhas desconectadas, pouca antecedência de caminhada, capacidade zero/desconhecida,
  ocupação, conexões entre níveis, GeoJSON inválido e limites de recorte.
- **49/49 verificações no navegador:** seis centros sintéticos, desktop e celular,
  importar GeoJSON e Shapefile ZIP, recalcular tempo/capacidade/água, exportar,
  salvar/reabrir e mensagens de erro do worker. ZIPs SHP/SHX/DBF/PRJ são construídos
  pelo teste; não dependem de arquivos externos.
- **37/37 regressões anteriores do motor:** mantidas após as mudanças.

A primeira rodada pública de navegador aprovou 47 de 48 verificações e expôs um
erro no tratamento de falhas do cálculo. A bateria sintética inicial aprovou
97 de 104 e expôs sete casos problemáticos. As verificações finais corrigidas
foram repetidas localmente; o comando abaixo permite repetir no site publicado.

## Falhas encontradas e corrigidas

1. **Níveis de vias:** extremos coincidentes eram unidos mesmo com `layer`
   explícito diferente. Agora o nível é preservado. Conexões de acessos entre
   níveis exigem IDs de nó compartilhados (`node_ids`/`osm_node_ids`) na mesma
   coordenada. Pontes sem nível explícito mantêm o comportamento dos acessos
   existentes. Bases sem topologia suficiente precisam de revisão municipal.
2. **Recorte e limite de nós:** vias externas podiam esgotar o limite de 30 mil
   nós. Seus segmentos externos são descartados antes de gerar nós. Uma área
   sem via retorna demanda não atendida, sem criar um caminho fictício.
3. **Furos de polígonos:** eram aceitos furos fora do anel externo, cruzando-o
   ou sobrepostos. A importação passa a rejeitá-los com uma mensagem específica.
4. **Modo automático:** um ponto manual no único lugar elegível suprimia o
   candidato automático antes de ser removido. Os pontos manuais agora são
   ignorados antes da geração de candidatos nesse modo.
5. **Erros do worker:** o `catch` usava `id` fora de escopo e transformava erros
   esperados em `ReferenceError`. O identificador agora é preservado, e o erro
   real de filtro sem vias ou capacidade inválida chega à interface.

## Executar

```sh
cd tests/frontend
npm ci
npx playwright install chromium
npm run test:municipal:brasil
# Chromium já instalado:
# CHROME_PATH=/usr/bin/chromium npm run test:municipal:brasil
```

`npm test` inclui também as suítes anteriores. Para a rodada de navegador pública,
com dependências remotas reais e TLS verificado:

```sh
BRASIL_ORIGIN=https://previne-taquari-antas.github.io/Previne-Taquari-Antas---Redes-Neurais \
  node tests/frontend/brasil_audit.cjs
```

## Alcance da conclusão

Os resultados confirmam o comportamento nos recortes e hipóteses descritos.
Não comprovam o comportamento de toda cidade brasileira, a integridade de
cadastros municipais ou a segurança operacional das rotas. HAND continua
experimental; não foram usados eventos de cheia observados dessas seis cidades
para validar o modelo hidrológico. A revisão cartográfica de Santa Tereza
permanece dependente de uma base validada.
