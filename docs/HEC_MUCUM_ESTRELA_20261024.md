# HEC-HMS: referência V1 de Muçum e Estrela em novembro de 2023

Revisão atual: [V3 por cidade e evento](HEC_EVENTOS_V3_20261024.md), com comparação independente contra a V2.

Esta versão foi substituída pela [revisão V2](HEC_EVENTOS_V2_20261024.md), que melhora o pico e a subida e compara toda a telemetria disponível na mesma base antes/depois. O conteúdo abaixo preserva o diagnóstico e os resultados históricos da V1.

O E1 por ramos não representava a vazão de base das áreas incrementais. Em Estrela, a seleção apenas por NSE também admitia um pico secundário incompatível com o nível baixo observado em horas sem Q. Esta versão acrescenta recessão nativa opcional, calibração por cidade e uma restrição verificável a partir desses níveis.

Foram concluídas 138 avaliações cidade × parâmetros, correspondentes a 132 execuções nativas distintas do HEC-HMS 4.13, com intervalo interno de 3 minutos.

| Cidade | NSE | KGE | Viés nos pares | Horário do pico modelado menos o pico de nível | Pares de Q |
|---|---:|---:|---:|---:|---:|
| Muçum | 0,975874 | 0,896647 | +0,575% | −0,20 h | 194 |
| Estrela | 0,967773 | 0,894768 | −2,249% | +2,15 h | 142 |

Muçum foi avaliada em Q somente até 15 m, com a correção de relógio documentada de −105 minutos. O pico de nível, corrigido no mesmo relógio, controla o horário da onda. A amplitude de vazão acima de 15 m não entra na calibração.

Estrela tem apenas 142/240 horas de Q e uma lacuna de 63 h. Em outras 32 horas sem Q, existe nível abaixo do menor par nível–Q disponível: 13,9875 m e 2.186,6 m³/s. A monotonicidade dessa mesma relação fornece um limite superior de Q, sem preencher a vazão ausente. A seleção final respeita esse limite com tolerância de 10%; a máxima vazão simulada nessas horas caiu para 2.375,67 m³/s.

Os parâmetros globais CN baixos são efetivos desta configuração e deste evento; não são valores mapeados de solo e uso da terra. Podem compensar a chuva esparsa: novembro possui mediana de somente 3 pluviômetros/h. Isso limita a interpretação física e a transferência dos parâmetros.

## Reprodução

Instalar NumPy, SciPy e Matplotlib. Com HEC-HMS 4.13 e ambiente gráfico disponível:

```bash
python3 scripts/calibrate_mucum_estrela_event_library.py /path/to/hec-hms.sh --workers 3
python3 scripts/refine_mucum_estrela_stage_consistency.py /path/to/hec-hms.sh
python3 scripts/audit_hec_incremental_water_budget.py /path/to/hec-hms.sh
python3 scripts/export_mucum_estrela_event_calibration.py /path/to/deliverables
```

O primeiro comando retoma etapas concluídas e recusa reutilizar o cache se entradas ou configuração mudarem. A revisão acrescenta erro relativo e a restrição pelo nível. A exportação recusa Estrela se a restrição falhar e recalcula NSE, KGE, viés e RMSE independentemente, a partir do CSV nativo.

Os projetos entregues usam referências relativas e incluem `input.dss`. O script gerado com caminhos absolutos não é necessário para abrir e executar o projeto na interface do HEC-HMS.

## Validação e alcance

- Testes de estabilidade, contrato E1, proteção da validação de 2024 e QA específico da estação.
- Verificação nativa de `FLOW = FLOW-DIRECT + FLOW-BASE`, não negatividade e escala do volume de base frente às perdas de precipitação nas nove sub-bacias incrementais.
- Observações originais e condições de montante preservadas; alterações de relógio e censura de Q existem apenas no pacote de pontuação.
- A linha José Júlio observada e a chuva de todo o evento são entradas retrospectivas. Estes resultados são calibração histórica, não comprovação de previsão operacional.
- O domínio é o E1 BHO6 por ramos de Linha José Júlio a Porto Mariante, não o projeto original completo de 145 sub-bacias.
- Sementes anteriores foram ajustadas em setembro e novembro de 2023. O novo refinamento usa novembro; setembro não é teste independente. Maio/junho de 2024 continuam reservados nesta busca.
- Nenhuma alteração foi promovida às previsões públicas.

## Referências

USACE HEC. *Model Calibration*. https://www.hec.usace.army.mil/confluence/hmsdocs/hmsrd/model-calibration-355276362.html

USACE HEC. *Recession Model*. https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/baseflow/recession-model
