# HEC-HMS — revisão V3, Muçum e Estrela

Atualização de Muçum: [geometria da planície e teste nativo](HEC_MUCUM_PLANICIE_20261024.md). A referência de zero da régua foi recuperada no SGB; a retenção V3 não foi validada como armazenamento da planície local. O registro independente do pico de novembro/2023 também favorece os horários brutos, questionando a correção de −105 min neste evento. Os resultados abaixo permanecem como histórico de calibração sob a hipótese QA105, não como confirmação hidráulica ou de relógio.

Dois modelos independentes, calibrados para novembro/2023 (E24 q62 / E12 Muçum 2h). Não se exige que um conjunto de parâmetros funcione em outra cheia ou cidade.

## Comparação com a V2 realmente entregue

| Cidade | NSE completo | Erro relativo na subida | Erro relativo após a crista | Erro do pico V3 |
| --- | --- | --- | --- | --- |
| Muçum | 0.9961 → 0.9972 | 2.91% → 2.49% | 4.06% → 3.53% | -0.02% |
| Estrela | 0.9866 → 0.9919 | 5.43% → 4.19% | 8.40% → 5.61% | +0.06% |

Os erros relativos por trecho são soma dos erros absolutos dividida pela soma das vazões observadas nos pares disponíveis. Subida: 24h antes da crista de nível; recessão: todos os pares depois da crista. Não são média dos erros percentuais horários. O NSE e o viés usam somente os pares disponíveis. O pico usa o máximo da série simulada completa e o máximo da telemetria disponível, na mesma base da V2.

`comparacao_V2_V3.csv` inclui os valores exatos, NSE restrito, viés e erro de horário. A comparação é recalculada com NumPy, independentemente do cálculo de seleção, contra uma cópia da saída nativa efetivamente entregue na V2. Não se exige melhora em todos os indicadores: NSE completo e MAE relativo completo, da subida e da recessão não podem piorar; em Muçum também não podem regredir NSE e MAE até 15m. Pico deve ficar até 2%, horário até 0,75h e viés até 2%; Estrela deve cumprir a restrição por nível.

A busca gera candidatos minimizando resíduos quadráticos normalizados, com pesos explícitos no manifesto. A seleção para entrega prioriza equilíbrio entre trechos: entre candidatos aprovados, minimiza a maior razão MAE_V3/MAE_V2 dos trechos (completo, subida, recessão e, em Muçum, até 15m). Empates usam média das razões e depois o objetivo quadrático. Isso impede que um grande ganho em um trecho esconda um ganho pequeno nos demais. É uma seleção com o evento de calibração inteiro; não é avaliação independente.

## Abrir e executar

HEC-HMS 4.13: abra `g040_e1_hindcast.hms` dentro de cada pasta e compute `Hindcast`. Cada projeto leva seus DSS de entrada e referências relativas. Os dois projetos foram copiados para pastas isoladas e computados novamente, em série. Todos os seis controles devem ter 4.781 valores a cada 3min e métricas iguais às da seleção. Os parâmetros exatos e resultados nativos estão no JSON da respectiva cidade. Arquivos temporários e scripts com caminhos absolutos foram removidos do pacote.

Muçum usa SCS, recessão, Muskingum e armazenamento lateral conceitual causal aplicado à entrada de montante. A série efetiva acompanha o DSS. O CSV `montante_original_e_entrada_modelo.csv` conserva a distinção entre observado original e entrada efetiva; não se reclassifica a entrada modificada como medição. Para regenerar essa entrada a partir dos dados originais, use o gerador de projetos e os parâmetros no PR associado. Estrela usa perdas Initial+Constant, Clark, recessão e Muskingum; CN/lag legados em seus argumentos são ignorados por Initial+Constant/Clark.

## Limites da interpretação

Domínio E1 BHO6 por ramos de Linha José Júlio a Porto Mariante, diferente do projeto original completo de 145 sub-bacias. Chuva e vazão de montante de todo o evento são conhecidas: é ajuste retrospectivo, sem comprovação de previsão em tempo real. A chuva tem mediana de três postos por hora e pode produzir compensação entre parâmetros. Não há promoção operacional.

Muçum: correção de relógio de −105min somente na observação para comparação, seguindo o QA fornecido e dentro da vigência documentada; observados e entradas originais não foram sobrescritos. NSE até 15m permanece separado. As vazões de cotas maiores dependem da curva-chave da telemetria; bom ajuste não confirma independentemente a vazão extrema. Armazenamento lateral é hipótese conceitual, sem geometria hidráulica medida. A auditoria de componentes é uma checagem numérica e de escala, não validação física da planície ou aquífero.

Estrela: 142/240h de Q disponíveis, com lacuna de 63h. Nenhuma Q ausente foi inventada; em 32h de nível baixo sem Q, usa-se apenas o limite superior decorrente da monotonicidade da mesma relação nível/vazão, com tolerância de 10%. Observações são horárias; diferenças de minutos na saída de 3min não representam precisão de campo.

Os parâmetros foram escolhidos usando este mesmo evento completo. Os ganhos informados são de calibração; não são resultados de validação independente. Cada evento futuro deve ser identificado por seu próprio membro e por sua evidência.
