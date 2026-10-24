# Santa Tereza — prioridades de vistoria do risco de isolamento

Data da análise: 24/10/2026. Fonte: resultados computacionais [GitHub Actions run 40108600114](https://github.com/previne-taquari-antas/Previne-Taquari-Antas---Redes-Neurais/actions/runs/40108600114).

## Resultados calculados

- Refinamento por passo de 0,10 m HAND: **335 de 565** edificações OSM com primeira perda de conectividade modelada antes de inundar, entre aquelas com cotas disponíveis. Não equiparar a 335 domicílios ocupados.
- Simulação de retirada de uma aresta por vez: **1.103 pares (nível HAND, trecho)** para os quais o fechamento remove acesso adicional a destinos cadastrados. Não confundir pares de teste com ruas distintas.
- No cenário HAND 12,0 m (régua aproximada 13,6 m na conversão usada pelo painel), trechos 328–331 apresentam até **445 edificações OSM** adicionais desconectadas *em simulações separadas*. Não somar essas contagens: grande parte das mesmas origens aparece nos quatro cenários.
- Trecho 78 no mesmo nível resulta em até **406 edificações OSM** em fechamento individual.
- A contagem está condicionada a uma malha OSM, uma ligação casa-nó aproximada e destinos considerados habilitados no grafo sem validação de acesso, disponibilidade ou capacidade.

## Inspeção prioritária — P0

1. **Arestas 328–331 e 78**: verificar geometria OSM, continuidade das vias, bifurcações, possíveis passagens/falsas desconexões, restrições a pé, pontes e cabeceiras. O sinal de 445 origens repetidas sugere um corredor crítico ou um possível artefato de topologia que deve ser investigado.
2. **Acesso ao Ginásio de Esportes**: auditar a entrada, ruas de aproximação, rampa e coberturas por LiDAR/MDT; confirmar cota na régua observada em campo. A cota do prédio não substitui a cota de seu acesso.
3. **Centro histórico/igreja/prefeitura**: marcar como candidatos a refúgio temporário apenas para investigação; avaliar conexões reais, altura e estabilidade, disponibilidade de abrigo e exposição à correnteza e deslizamentos.
4. **Pontos CNEFE 2022 sem edificação OSM até 30 m**: 567 pontos no universo municipal, parte fora do recorte urbano. Não deduzir demolição nem ausência de moradia sem imagem e cadastro municipal.
5. **Origens sem nó de rede ou altura resolvida**: não classificar como seguras por ausência de resultado.

## Ficha mínima de verificação para cada via/destino

Identificador da aresta/ponto; coordenadas; tipo de via; passagem a pé/veículo; fotografia com data; evidência aérea; cota do pavimento com datum; cota das cabeceiras; ponte (sim/não e condição); rota alternativa confirmada; profundidade/velocidade de água tolerável (definida por protocolo técnico); cota da primeira interrupção; responsável pela inspeção; data; situação (pendente/verificado/incerto); referência da Defesa Civil.

## Delimitação técnica

As arestas que aparecem com cota de inundação alta ainda podem ter cabeceiras e acessos alagados antes; a simulação remove um segmento isolado e não as barreiras hidráulicas completas. A conversão de HAND para régua provém do painel, não constitui nova calibração de datum. Sem vistoria e validação histórica, qualquer rota deve ser denominada **hipótese de conectividade**, e nunca orientação pública de evacuação.

## Próximo marco técnico

Revisar as arestas 328–331 e 78 no OSM e ortofoto; comparar com o grafo/relevo e validar em campo; depois repetir os fechamentos com topologia reparada e gerar mapa de *primeira perda de acesso* com resolução residencial CNEFE. A integração operacional ao PREVINE dependerá dos critérios de qualidade documentados anteriormente.
