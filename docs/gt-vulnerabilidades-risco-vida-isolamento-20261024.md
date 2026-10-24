# GT Vulnerabilidades e Riscos — risco à vida, isolamento e rotas de fuga
**Plano metodológico e auditoria preliminar — 24/10/2026**  
**Municípios-piloto:** Santa Tereza e Muçum (RS). **Escala futura:** bacia Taquari–Antas.  
**Status:** pesquisa; não constitui validação de rota, abrigo, ponte ou ordem de evacuação. Alterações de operação pública só após validação independente e pactuação com Defesa Civil.

## 1. Pergunta e objetivo
**Pergunta:** Em que nível e momento da cheia cada domicílio perde a possibilidade de chegar, por caminho transitável, a uma alternativa de proteção compatível com seu perfil? O destino mais próximo nem sempre é alcançável. Um centro urbano pode permanecer seco, mas ficar isolado; um abrigo pode continuar seco quando seu acesso já foi inundado.

**Objetivo:** desenvolver e validar um método de avaliação espaço-temporal do risco à vida que cruza inundação, acessibilidade da malha viária, edificações residenciais, oferta real de abrigos e alternativas elevadas locais; iniciar na escala de endereço em Santa Tereza/Muçum e agregar à escala municipal e regional.

**Unidades analíticas distintas:** (a) unidade residencial; (b) trecho transitável e travessia; (c) destino validado; (d) componente isolada do grafo; (e) município e conexões regionais. Cada resultado deve carregar cota da régua, nível HAND, tempo, cenário, fonte e incerteza.

## 2. Auditoria preliminar do PREVINE (não é validação de campo)
### Há implementação prévia
- codigo_python/09_rota_fuga/README.md descreve o roteiro OSM + Dijkstra, edificações OSM, HAND/MDT, abrigos, candidatos, perfis de vias e painéis por cidade. NÃO começar do zero; refatorar, auditar, validar.
- codigo_python/09_rota_fuga/gerar_rota_fuga_ruas.py tem fator PENAL_AGUA = 60 e classifica risco por presença de água nos trechos; **penalização não prova que toda travessia alagada foi proibida**. Auditar semântica da busca para nunca publicar trajeto pedonal que cruza água, salvo cenário de travessia especializado, autorizado e validado por equipe habilitada.
- A regra atual de ponte desconsidera perfil de água sob o tabuleiro e marca comprometimento a partir de cabeceiras. Não se pode inferir transitabilidade nem resistência estrutural daí. Acrescentar cotas do tabuleiro, cabeceiras, inspeções, status de operação e incerteza.
- Os arquivos auxiliares OSM e MDT para reprocessar rotas podem não estar versionados no Git; o README informa ausência desses caches. Guardar manifesto reprodutível com hashes, data de aquisição e fonte antes de recalcular ou comparar quantitativamente.
- assets/data/servicos/abrigos.geojson inclui 1 destino de Santa Tereza (Ginásio de Esportes) e 6 destinos de Muçum. O próprio dado de Santa Tereza aponta possibilidade de inundação em cheia extrema e incerteza: **não classificar como seguro sem verificação**. O cadastro de Muçum não inclui todos os locais do Plano de Contingência de julho/2026.
- assets/data/mucum_contingencia_202607.json traz 9 alojamentos do Quadro 13, dados conflitantes de capacidade e alguns pontos geocodificados ainda não confirmados em campo. Os estados operacionais constam como desconhecidos.
- No README, resultados de pesquisa para cenário de 18 m na régua de Muçum / 15 m na de Santa Tereza são: edificações OSM 1.937 / 565; casas secas ilhadas 194→62 / 425→27 ao adicionar destinos candidatos; 4 / 5 candidatos. São **contagens declaradas na documentação**, não medidas independentes validadas nesta revisão.
- No próprio README, o deslocamento do zero da régua em Muçum em ±1 m muda a contagem de casas atingidas de 62 a 330: sensibilidade impeditiva para declarar rotas seguras sem calibração. Outro limite: o recorte urbano deixa domicílios de fora.

### Conclusão da auditoria inicial
Há protótipo relevante já desenvolvido, mas permanecem quatro bloqueios científicos para decisão sobre risco à vida: referência vertical e mancha; inventário residencial verificado; conexões e travessias reais; adequação dos destinos/capacidade. Um teste que apenas abre a página não resolve esses bloqueios.

## 3. Dados e procedimentos
| Camada | Base inicial | Tratamento/controle |
|---|---|---|
| Endereços | IBGE CNEFE 2022, espécie de uso e tipo de edificação | Filtrar finalidade domiciliar; manter endereço com múltiplas espécies quando possui residência; deduplicar corretamente unidades; preservar incerteza de ocupação atual; não publicar vulnerabilidade individual |
| Edificações | OSM building e ortofotos/drone existentes, imagens datadas | Intersectar CNEFE com footprints; marcar divergências, edificações destruídas e posteriores a 2022; ortofoto atual e revisão humana para casos duvidosos; não presumir que building=yes é residência |
| Terreno e água | MDT/LiDAR existentes; HAND; marcas de 2023/2024; nível das estações; contornos | Conferir datum horizontal e vertical, resolução e erro; superfície de água espacialmente variável quando necessário; conectividade hidráulica, incerteza e gradiente; não tratar HAND como hidráulica 2D |
| Ruas e travessias | OSM, arruamento municipal, pontes, escadarias e acessos locais | Grafo topologicamente conectado; transições casa→via verificadas; amostrar os trechos e incluir tabuleiros; classificar condições a pé, mobilidade reduzida e veículos separadamente |
| Destinos | Plano municipal, cadastro de abrigos, prédios elevados candidatos | Classificar como abrigo operacional, ponto de encontro validado, refúgio temporário ou candidato de pesquisa; conferir abertura, acessibilidade, capacidade, encosta, saúde/água, acesso, risco de isolamento |
| Exposição e demandas | IBGE 2022 agregado, registros municipais sob governança restrita | Estimar demanda com intervalos de confiança; não supor pessoas por edificação sem evidência; integrar cadastro local sem publicação de identidades e condições de saúde |

O cadastro CNEFE distingue domicílios de escolas, UBS, templos e outros estabelecimentos. O robô recomendado deve funcionar em níveis de confiança, não por decisão silenciosa: correspondência CNEFE + footprint e imagem recente; discrepâncias para revisão humana; conferência fotográfica de rua apenas quando disponível, datada e juridicamente permitida. OSM não é sinônimo de Street View.

## 4. Modelo de acessibilidade
Construir grafo espacial **G=(V,E)** por modo de deslocamento, com arestas tipadas (ruas, pontes, escadas, caminhos, acessos domiciliares). Para cada cenário de cheia c e instante t:
1. Calcular inundação, profundidade e incerteza por ponto/segmento e momento de perda de transitabilidade. Para caminhada no protótipo, qualquer trecho previsto como alagado ou sem estado verificável é bloqueado; regras adicionais de segurança para fluxo, correnteza, detritos, encostas e pontes. Não equivaler posição elevada a destino seguro.
2. Remover do grafo os trechos bloqueados; não apenas atribuir custo alto. Marcar como **desconhecida** a conectividade que depende de ponte sem verificação e produzir cenários conservadores de ponte aberta/fechada para comparação, sem declarar a opção desconhecida transitável.
3. Gerar rotas com custo tempo de deslocamento, inclinação, barreiras, acessibilidade e risco; selecionar destino entre os **alcançáveis**, não o mais próximo em linha reta.
4. Em modelo dinâmico, a rota só é viável se a chegada a **cada aresta** for anterior ao momento de bloqueio, descontando preparo, variação de subida e margem de segurança. Se faltar tempo para sair, não sugerir saída a pé por via alagada.
5. Otimizar a atribuição domicílio→destino sob restrições de capacidade e demanda; opção de proteção temporária somente se local seco e estruturalmente compatível, com plano de sustentação/comunicação e validação da autoridade. Calcular ocupação prevista, não presumir disponibilidade.
6. Reter alternativa primária, secundária, motivo do bloqueio, trecho crítico, cota do primeiro bloqueio, antecedência estimada, custo, robustez e incerteza.

**Categorias propostas** (não reduzir a um semáforo único):
- A — residência seca + rota e destino validados/alcançáveis;
- B — residência seca, acesso externo perdido, mas refúgio local validado e suprimentos/assistência avaliados;
- C — residência seca e isolada, sem refúgio validado;
- D — residência prevista dentro da mancha, com saída antecipada necessária;
- E — condição indeterminada, dados insuficientes ou travessia crítica não vistoriada.
A classificação é dependente do cenário e do horário; estado operacional separado do resultado científico.

Para cada origem i, cenário c, registrar:
- L_casa(i): nível da régua no qual a edificação é atingida;
- L_corte(i): **primeiro** nível no qual desaparece a rota de saída sem atravessar trechos bloqueados;
- DeltaL(i) = L_casa(i) − L_corte(i): potencial de ficar isolado antes de inundar;
- T_saida_limite(i): último horário possível para concluir o trajeto, dadas subida prevista e capacidade de marcha, com margem de incerteza;
- abrigo(i,c), alternativa(i,c), demanda(i), confiança(i).

## 5. Pilotos e hipóteses de campo
**Santa Tereza:** tratar o centro/igreja/prefeitura como **candidato a área elevada de refúgio local**, e não como abrigo certificado por altitude ou por testemunho isolado. Comparar (a) caminho ao ginásio, (b) acesso a essa área, (c) conexões com exterior e (d) perdas de ponte/rua. Quantificar residências ainda secas quando o acesso ao ginásio se perde. Verificar se o nível de corte da rota é inferior ao nível que alaga o ginásio e se o centro mantém infraestrutura durante isolamento. Investigar margens separadas e acessos rurais, que o recorte OSM não cobre integralmente.

**Muçum:** reconciliar os 9 alojamentos, 2 pontos de encontro e 6 rotas do Plano de Contingência de julho/2026 com o inventário do PREVINE; testar múltiplos destinos e capacidade por cheia. Identificar candidatos em Cidade Alta e demais pontos elevados **sem declarar segurança antes da inspeção**. Comparar rota mínima por distância versus rota com água e barreiras bloqueadas; verificar acessos às pontes. Cruzar também com as 23 áreas de risco mapeadas pelo SGB em 2025, incluindo processos não fluviais.

**Regional:** depois dos pilotos, processar intermunicipalmente a rede, pontes, corredores prioritários e destinos aptos; usar agregação por comunidade, município e bacia sem perder a origem pontual do estudo. Distinguir evacuação municipal de deslocamento regional.

## 6. Produto cartográfico
Painel por município com:
- pontos domiciliares filtrados e **indicador de qualidade cadastral**, sem expor dados pessoais;
- malha de vias em estado trafegável / bloqueado por água / ponte a confirmar / fora de cobertura;
- destinos separados: abrigo validado, ponto de encontro, refúgio temporário, candidato;
- nível do rio por régua local com tradução HAND explicitamente marcada como calibrada ou provisória, slider e cenários históricos;
- clique na casa → destino alcançável, trajeto, tempo, rota alternativa, cota e motivo da perda de saída, confiança e estado de validação;
- mapa específico de **isolamento anterior à inundação da residência** e lista de trechos críticos;
- duas visualizações: pesquisa técnica e informação pública revisada com autoridades competentes.
Nenhuma recomendação individual automatizada de evacuação deve depender de modelo experimental não validado.

## 7. Validação
1. Auditar valores de nível e datum, cobertura do MDT, cena base e séries de cheias. Confrontar limites e profundidades com marcas, imagens e informações observadas de 2023/2024.
2. Conferir em campo amostra estratificada de endereços OSM/CNEFE: falsos positivos (galpões, UBS, igrejas) e falsos negativos (casas sem footprint, áreas rurais, casas novas/destruídas).
3. Conferir in loco pontes, escadas, rampas, passagens, pontos de água, encostas e abrigos, com registro de data e fotos.
4. Exercitar rotas com Defesa Civil e representantes comunitários, inclusive idosos e pessoas com mobilidade reduzida, em **simulação sem deslocamento arriscado durante cheia**.
5. Testes de sensibilidade de cota vertical, profundidade, taxa de subida, chuva lateral, tempo de preparo, capacidade, interrupção de pontes, incerteza do OSM e destino fechado.
6. Avaliar completude da cobertura (% endereços CNEFE com rota ou motivo explícito), precisão do inventário residencial, acerto dos cortes de via observados, taxa de falsas rotas disponíveis, margem temporal conservadora e demanda versus capacidade.
7. Versionar cenários, dados e método; manter log do que foi testado e do que ainda não foi validado.

## 8. Plano de execução, com critérios de aceite
- **P0 — inventário do existente:** produzir quadro rastreável de scripts, arquivos realmente presentes, SHA, fontes, extensão geográfica e status de uso. Não reutilizar saída sem registrar a origem.
- **P0 — nenhuma rota insegura publicada:** teste automático que falhe se uma rota pedonal dita 'segura' incluir segmento alagado, ponte sem verificação ou destino inacessível; travessias incertas entram como **não verificadas**. Não confundir penalização de água com bloqueio.
- **P0 — referência vertical:** auditoria independente dos zeros de régua de ambas as cidades e envelopes de incerteza. Só calcular níveis de corte quando a transformação estiver justificada para o trecho.
- **P1 — base de domicílios:** importar CNEFE 2022, filtrar espécie domiciliar e conferir divergência OSM/ortofoto; produzir tabela de precisão e faltantes, abrangendo os setores fora do recorte urbano.
- **P1 — destinos:** revalidar Santa Tereza e conciliar todos os alojamentos de Muçum, incluindo capacidade e condição de uso. Sem classificação de 'seguro' automática.
- **P1 — grafo dinâmico:** gerar por residência L_casa, L_corte, caminho, alternativa, isolamento e margem temporal por cenário, sem trajetos em água.
- **P2 — estudos de caso:** produzir mapas, matriz de confusão, ensaios 2023/2024 e parecer interdisciplinar/Defesa Civil.
- **P3 — regional:** generalizar método e harmonizar critérios da bacia inteira, com geração controlada de painéis municipais e produto regional.

### Decisão de publicação
Esta branch contém **apenas plano de pesquisa e auditoria**; nenhuma rota de evacuação foi recalculada ou certificada neste commit. Não alterar automaticamente o painel público até conclusão dos bloqueios P0 e inspeções necessárias.

## Referências e documentação
- IBGE (2024). CNEFE Censo 2022, microdados e classificação de espécie. https://www.ibge.gov.br/estatisticas/sociais/populacao/38734-cadastro-nacional-de-enderecos-para-finsestatisticos.html
- SGB (2025). Cartografia de risco geológico: Muçum, RS. https://rigeo.sgb.gov.br/handle/doc/25608
- FEMA (2021). Identifying At-Risk Roadways and Evacuation Routes. https://www.fema.gov/sites/default/files/documents/fema_Identifying-at-risk-roadways-evacuation-routes_region-three_06-2021.pdf
- Prefeitura de Muçum (2026). Plano de Contingência, julho/2026 (referenciado em assets/data/mucum_contingencia_202607.json).
- PREVINE, docs e código de rotas consultados em 24/10/2026: codigo_python/09_rota_fuga/README.md; gerar_rota_fuga_ruas.py; gerar_painel.py; assets/data/servicos/abrigos.geojson; assets/data/mucum_contingencia_202607.json; docs/hec-hms-calibration-plan.md.
