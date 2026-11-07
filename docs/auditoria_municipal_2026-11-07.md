# Auditoria funcional · 7 de novembro de 2026

Foram usados dois agentes independentes: um para interface e fluxos publicados,
outro para geometria, rede, capacidades e terreno. A integração foi conferida
separadamente. Os casos de falha foram reproduzidos, corrigidos e incorporados
a testes de regressão.

## Cobertura e resultados

- **10 páginas públicas e 45 scripts/estilos:** HTTP 200, sem assets ausentes ou IDs duplicados. Inclui início, módulo municipal, pontos de encontro, painéis de edificações, previsão e evacuação de Santa Tereza e Muçum.
- **27 combinações nas páginas existentes:** três bases de cidade/mancha × três modos × tempos de 5, 20 e 60 minutos. Resultados e contagens consistentes, sem erros JavaScript; execução no site publicado com os CDNs reais e TLS verificado.
- **37 testes de motor:** capacidade, ocupação, destinos desconhecidos, bloqueios pontuais e poligonais, ligações à rede, cruzamentos em níveis distintos, vias sobrepostas, restrições de acesso, áreas com furos, recorte da rede, estrutura GeoJSON, alturas negativas/fracionárias, GeoTIFF georreferenciado e monotonicidade do HAND. Incluem 50 variações de capacidade com conferência de totais populacionais.
- **Navegador, desktop e celular:** carregar exemplo, importar cenário, calcular, selecionar rotas, exportar, salvar/reabrir, redefinir município e desenhar área de interesse. Sem transbordamento horizontal nos tamanhos verificados de 1440 e 390 px.
- **Shapefile real:** ZIPs com SHP/SHX/DBF/PRJ de vias, edificações e abrigo importados no site publicado; alias `capacity` convertido; duas edificações e seis pessoas atendidas sem superar a capacidade de dez pessoas.
- **Regressões de interface locais:** entrada negativa invalida resultados e exportações; cálculo e salvamento bloqueados com campo inválido; última feição pode ser excluída e o cenário reaberto; arquivo malformado não substitui a base válida; salvar edição e exclusão na barra do mapa não gera erro JavaScript.

Os testes públicos usaram o código anterior à correção; as regressões foram
repetidas na versão corrigida local antes da publicação. Os testes de regressão
locais usam bibliotecas reais instaladas e interceptam o CDN; isso evita
confundir indisponibilidade de rede com defeito de produto. Uma tentativa com
proxy para localhost falhou no próprio harness (não encontrou a página); ela
foi substituída pelo servidor local em porta aleatória e não foi contabilizada
como falha do produto.

## Defeitos corrigidos

| Problema reproduzido | Correção |
| --- | --- |
| Uma via atravessando uma área pequena desaparecia quando não havia nó interno a cada 80 m | Divisão das vias nos limites da área antes de filtrar os trechos |
| Point e LineString com profundidade de coordenadas incorreta passavam pela importação | Validação por tipo geométrico antes de atualizar a camada; validação também no motor |
| Anéis auto-intersectantes e parâmetros não finitos eram aceitos | Rejeição explícita; alturas de coordenadas vetoriais são normalizadas para processamento 2D |
| Salvar uma edição do mapa gerava erro ao desmontar os controles de edição | Reconstrução visual adiada até a conclusão do evento do Leaflet Draw |
| Excluir a última feição impedia reabrir o cenário: “Camada vazia” | Coleções vazias permitidas nas camadas opcionais de predefinições; vias e edificações continuam obrigatórias no cálculo |
| Capacidade negativa deixava resultados e CSV anteriores ativos e salvava o valor antigo | Invalidação na entrada, validade explícita do campo e bloqueio de cálculo/salvamento |

A validação de formulário também passou a detectar um passo numérico incompatível
com o valor padrão da área de drenagem; o passo foi ajustado para 0,001 km².

## Reproduzir

```sh
cd tests/frontend
npm ci
npx playwright install chromium
npm test
# Em ambiente com Chromium instalado:
# CHROME_PATH=/usr/bin/chromium npm test
```

As suítes municipais podem ser executadas separadamente:

```sh
npm run test:municipal
npm run test:municipal:audit
```

## Limites da conclusão

Esta auditoria confirma os fluxos e casos descritos, não uma verificação exaustiva
de toda a plataforma ou validação hidrológica/cartográfica. HAND continua
experimental, capacidades e populações dependem dos cadastros e a revisão dos
contornos de Santa Tereza depende de base validada. A distribuição de destinos
é heurística; os testes não transformam suas sugestões em orientação oficial.

## Atualização do motor no navegador

O worker e seus módulos recebem a versão dos scripts da página na URL. Isso
evita reutilizar um motor anterior do cache depois da publicação de correções.
A suíte de interface verifica que essas requisições têm versão explícita.
