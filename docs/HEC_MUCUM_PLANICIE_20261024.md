# Muçum: planície quantificada por topografia e teste nativo HEC-HMS

Foi calculada uma curva cota–área–volume para a parte da planície coberta pelo MDT de drone existente, e ela foi inserida como tabela Storage-Outflow em um reservatório Modified Puls nativo do HEC-HMS 4.13, imediatamente antes do controle Muçum. Isso é uma hipótese de armazenamento concentrado, não uma nova barragem nem uma solução hidráulica 1D/2D validada.

## Resultado geométrico e domínio

O raster de origem é `mdt_mucum_drone_1m.tif`, com 2.333 km² válidos no recorte de análise. A grade foi reamostrada para 2 m em UTM 22S. O SGB publica o zero da régua 86510000 em 33,985 m, com referência MAPGEO2015 (Tabela 2 do trabalho de Marcuzzo, Silva e Mendes, 2025). A nota de marcas de 2024 usa 33,96 m; a diferença é 0,025 m e não autoriza tratar a altitude cadastral de 240 m como zero da régua.

A grade oficial MAPGEO2015 foi recuperada do instalador público do IBGE, sem executar o programa Windows. A interpolação no local da régua resulta em N=6.4694 m, coerente com os 6,47 m da nota de campo do SGB. O MDT bruto é tratado como altitude elipsoidal conforme o gerador original do projeto: H=h−N. O arquivo anterior `_ortho` usa hgeoHNOR2020 e não foi misturado silenciosamente com MAPGEO2015. A data do voo, a referência original e a acurácia vertical dos pontos de controle ainda precisam do relatório do levantamento. Não houve novo levantamento de campo.

Na cota de 22,975 m da série horária de novembro/2023, a superfície correspondente está em 56,960 m MAPGEO2015. No cenário central, a parte coberta pelo drone e atribuída a montante da régua soma 16.56 ha conectados, 0.793 milhão de m³ de volume fora da faixa adotada para o canal, e 0.454 milhão de m³ adicionais em relação à cota 18 m. Os 18 m são referência de início de danos do SGB, não levantamento da borda física do canal.

A meia largura excluída do canal foi testada em 50, 100 e 150 m, pois as linhas de margem medidas não foram recuperadas. Na cota do pico, o volume a montante varia aproximadamente de 0,125 a 2,451 milhões de m³. Há ainda teste de desnível água–terreno de ±0,5 e ±1 m no manifesto. Foram mantidos apenas pixels válidos, hidrologicamente conectados à faixa fluvial; depressões isoladas e NoData não viraram armazenamento. A repartição montante/jusante usa a projeção mais próxima ao longo do eixo BHO6, não limites administrativos.

O MDT local inclui áreas a jusante da régua. Todo o seu recorte soma cerca de 9.09 milhões de m³ no cenário central; esse total não foi usado como armazenamento a montante. O domínio mapeado não cobre o trecho completo de Linha José Júlio a Muçum. A capacidade da planície local não explica, sozinha, os 95.56 milhões de m³ máximos retidos na hipótese conceitual V3. Isso não prova a impossibilidade desse volume no vale inteiro: o restante do trecho não tem aqui a mesma cobertura de drone.

## Relógio e comparação na mesma base

O artigo original de Marcuzzo e Pinto relata o pico em 18/11/2023 às 23h45 locais, com 23,02 m no sensor e 23,20 m por leitura da Defesa Civil. A série horária arquivada tem seu máximo de 22,975 m entre 02h e 03h UTC de 19/11, intervalo que contém 02h45 UTC. A antiga correção de −105 min desloca esse intervalo para mais cedo e não é corroborada por esse registro independente para novembro/2023. Isso favorece o relógio bruto neste evento, sem provar todos os horários da série ou invalidar outros eventos. Os dados originais e a hipótese QA105 permanecem preservados.

Todos os modelos abaixo foram reavaliados com os horários brutos originais. Não se compara o NSE 0,9972 da V3 sob QA105 diretamente com um NSE calculado em outro relógio. O CSV fornece também o NSE sob QA105 para a mesma saída nativa, tornando a diferença auditável. A propagação Muskingum foi recalibrada apenas para Muçum/novembro de 2023; cada cidade e evento continuam com parâmetros próprios.

| Modelo | NSE, relógio bruto | Erro do pico contra Q disponível | Pico menos horário publicado pelo SGB | NSE até 15 m |
| --- | --- | --- | --- | --- |
| V3 · retenção conceitual | 0.9882 | -0.02% | -2.95 h | 0.9682 |
| Canal recalibrado · sem retenção externa | 0.9860 | +10.03% | +0.00 h | 0.9672 |
| Canal + planície local no HEC | 0.9859 | +10.03% | +0.05 h | 0.9670 |

O cenário com planície mantém **todas as vazões observadas de montante intactas**. O gerador não aplica a retenção externa da V3. A área e a curva de armazenamento são fixadas pelo terreno; somente a propagação do canal e os parâmetros de perdas/transformação/recessão das áreas incrementais foram calibrados na busca. A curva de descarga foi tomada dos segmentos ANA arquivados com vigência 06/09–31/12/2023, em metros, sem ajustar seus coeficientes ao hidrograma alvo. Os rótulos derivados h0_cm/h0_m desse arquivo têm ambiguidade de unidade; foram usados os coeficientes brutos e a equação A(h−h0)^n. Trata-se de vazão extrema condicionada à curva-chave, não medição independente de cheia.

## Verificação nativa e abertura

Abra `g040_e1_hindcast.hms` em cada pasta e compute `Hindcast` no HEC-HMS 4.13. `HEC_PLANICIE_LOCAL_NATIVO` é o modelo com geometria; `CANAL_SEM_RETENCAO_EXTERNA` isola o efeito da planície; `REFERENCIA_V3_CONCEITUAL` conserva o ajuste anterior como comparação, incluindo sua entrada efetiva modificada.

O modelo geométrico foi copiado e computado novamente em pasta isolada, com 4.781 valores de 3 min em cada um dos seis controles e no reservatório. O DSS retorna armazenamento em `1000 M3`; a conversão foi conferida contra a curva geométrica em m³. O máximo nativo foi 0.880 milhão de m³, correspondente à cota simulada e não necessariamente à cota observada. O balanço nativo integrado apresentou resíduo de -3.8e-09 m³. A diferença máxima entre a entrada de montante do modelo geométrico e o observado original foi 0.0 m³/s. As métricas exportadas foram recalculadas com NumPy a partir das séries nativas. Não há preenchimento de Q ausente.

## Alcance e pendências concretas

O resultado entregue é uma geometria topográfica derivada do levantamento existente, associada a uma referência de régua medida pelo SGB. Não é uma nova planície levantada em campo nem validação hidráulica completa. Faltam o relatório de pontos de controle/data do voo, linhas de margem, batimetria numérica, estruturas e cobertura do vale a montante. A superfície horizontal local não resolve declive longitudinal, remanso do Guaporé ou tempos de troca com a planície. O terreno pode ser posterior às cheias de 2023/2024 e não estabelece a geometria histórica sem essa verificação. O pico residual e os compromissos das métricas constam da tabela: não foram escondidos por nova alteração do hidrograma observado.

## Fontes e reprodução

- Marcuzzo, F. F. N.; Silva, E. D.; Mendes, D. V. Levantamento dos zeros ortométricos das estações fluviométricas da hidrologia do SGB no RS e SC. 2025. Tabela 2 e métodos: https://rigeo.sgb.gov.br/bitstream/doc/25518/1/marcuzzo_silva_Mendes_zero%20ortometrico_artigo.pdf
- Marcuzzo, F. F. N.; Pinto, E. J. A. Inundações históricas de 2023 na bacia do rio Taquari-Antas no município de Muçum/RS e os seus tempos de retorno. 2024. p. 4–5: https://rigeo.sgb.gov.br/bitstreams/98db393c-19a5-4a87-9d29-46b3a2985e74/download
- SGB. Nota técnica de levantamento dos níveis das marcas da grande cheia de maio/2024, versão 2, Tabela 2: https://rigeo.sgb.gov.br/bitstream/doc/24939.5/1/nota_tecnica_levantamento_cheias_2024_rs_versao%202.pdf
- IBGE. MAPGEO2015, grade SIRGAS2000 do instalador oficial: https://geoftp.ibge.gov.br/modelos_digitais_de_superficie/modelo_de_ondulacao_geoidal/aplicativo_desktop_MAPGEO2015/setup_mapgeo2015_v1.exe
- USACE. Outflow Curve Routing, HEC-HMS 4.13: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.13/reservoir-elements/outflow-curve-routing

Os scripts `build_mucum_floodplain_storage.py`, `refine_mucum_native_rawclock.py`, `test_mucum_terrain_storage_native.py`, `verify_mucum_terrain_storage.py` e `export_mucum_floodplain_research.py` estão no repositório PREVINE, PR 278. A grade geoidal local em JSON acompanha o pacote e pode substituir a grade completa na reprodução da geometria. O MDT bruto e o eixo BHO6 permanecem no repositório; o raster derivado, curvas, polígonos, auditorias e projetos portáveis acompanham este pacote.
