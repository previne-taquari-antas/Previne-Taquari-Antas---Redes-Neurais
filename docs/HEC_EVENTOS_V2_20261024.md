# Revisão V2: biblioteca de membros por cidade e evento

Referência histórica. A [revisão V3](HEC_EVENTOS_V3_20261024.md) refina separadamente subida, recessão e domínio de vazão menos incerto, comparando a saída nativa V2 efetivamente entregue.

O objetivo é calibrar conjuntos próprios para cada cheia. A transferência de um mesmo conjunto a outros eventos não é condição para inclusão na biblioteca. Esta revisão trata de novembro/2023 em Muçum e Estrela.

## Problema e resultado

A V1 tinha NSE 0,976 em Muçum apenas até 15 m, enquanto o pico completo simulado superava a vazão da telemetria em 18,45%. Em Estrela, a crista simulada estava 2,15 h atrasada. A V2 compara toda a telemetria disponível na mesma base antes/depois e mantém o diagnóstico de Muçum até 15 m separado.

| Cidade | Erro do pico V1 → V2, contra telemetria | Erro relativo na subida V1 → V2 | NSE completo V1 → V2 |
|---|---:|---:|---:|
| Muçum | +18,45% → −1,08% | 9,21% → 2,91% | 0,9734 → 0,9961 |
| Estrela | +1,14% → +0,25% | 9,99% → 5,43% | 0,9678 → 0,9866 |

O horário da crista V2 difere da maior cota disponível em −0,10 h em Muçum e +0,25 h em Estrela. As observações são horárias; isso não significa precisão de campo de 6 ou 15 minutos. Em Muçum, o NSE até 15 m passa de 0,9759 a 0,9697: a principal melhoria está na crista e na subida, sem alegar melhoria em todos os indicadores.

## Configurações comparadas

- SCS e hidrograma unitário SCS com recessão, mantendo a versão anterior como referência.
- Perdas Initial+Constant e transformação Clark nativas do HEC-HMS, com parâmetros em horas para Clark.
- Propagação Muskingum com número de subtrechos calibrável, selecionando sempre coeficientes estáveis e não negativos. O padrão anterior permanece igual quando a opção não é fornecida.
- Armazenamento lateral conceitual, causal e conservativo, com vários limiares, frações e tempos de liberação. O observado original não é sobrescrito.

Muçum selecionou SCS + recessão + armazenamento lateral conceitual antes da propagação HEC. Estrela selecionou Initial+Constant/Clark + recessão e propagação HEC. A biblioteca indexa cidade, evento e conjunto de parâmetros; não há parâmetro universal entre cidades ou cheias.

## Execução e verificação

```bash
python3 scripts/calibrate_event_members_v2.py /path/to/hec-hms.sh
python3 scripts/targeted_event_storage_v2.py /path/to/hec-hms.sh
python3 scripts/refine_balanced_event_member_v2.py /path/to/hec-hms.sh
python3 scripts/finalize_event_members_v2.py /path/to/hec-hms.sh
python3 scripts/isolate_verify_event_members_v2.py /path/to/hec-hms.sh
python3 scripts/export_event_members_v2.py /path/to/deliverables
```

O árbitro final exige pico até 5%, viés nos pares até 5%, diferença de crista até 1,5 h, NSE completo ≥0,975, NSE do domínio estrito ≥0,965, erro relativo da subida até 8% e a restrição por nível de Estrela. São critérios de trabalho para este ajuste histórico, não certificação geral.

Os casos finais foram abertos em pastas isoladas, executados novamente em série e conferidos com 4.781 valores em cada um dos seis controles. A exportação recalcula NSE, KGE, viés, RMSE, erro do pico e erro da subida independentemente. Saída nativa incompleta é rejeitada; os CSVs e os metadados são gravados por substituição atômica para não expor arquivos parciais.

## Limites mantidos

A comparação de grandes vazões de Muçum é condicionada à curva da telemetria; não substitui medições de descarga de cheia. O diagnóstico até 15 m, com a correção de relógio documentada de −105 min, continua separado. Estrela tem 142/240 horas de Q e restrição adicional por nível em 32 horas sem Q. A chuva possui mediana de 3 postos/h. O armazenamento lateral não tem geometria/curva de descarga medida e não é um reservatório hidráulico validado.

São simulações históricas com chuva e vazão de montante conhecidas. O domínio permanece E1 BHO6 por ramos, não o projeto integral de 145 sub-bacias. Nenhum resultado foi promovido às previsões públicas.

## Referências

USACE HEC. *Model Calibration*. https://www.hec.usace.army.mil/confluence/hmsdocs/hmsrd/model-calibration-355276362.html

USACE HEC. *Applying the Muskingum Routing Method*. https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/applying-reach-routing-methods-within-hec-hms/applying-the-muskingum-routing-method
