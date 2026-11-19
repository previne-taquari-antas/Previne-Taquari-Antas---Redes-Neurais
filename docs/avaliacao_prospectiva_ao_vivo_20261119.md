# Avaliação prospectiva das previsões ao vivo — 19/11/2026

Pesquisa. Não é alerta oficial. **O foco é a cheia**: só contam as horas em que
o nível na emissão ou na hora-alvo atinge a cota de transbordamento do robô
(`bankfull_cm`: Santa Tereza 1.500 cm, Muçum 500 cm). O erro com o rio baixo não
entra nas conclusões.

## Por que existe

Os robôs guardam em `historico_previsoes_ao_vivo*.json` só os últimos 1.200
registros (cerca de 2 a 3 semanas). A agenda (`rna-multi-horizonte`) exige ganho
consistente **por evento** fora da amostra — e essa evidência estava sendo
apagada a cada ciclo. Como as cheias são raras, perder um evento é perder boa
parte da prova.

## O que foi feito

1. `scripts/arquivar_historico_ao_vivo.py` copia cada registro para
   `assets/data/historico_ao_vivo_arquivo/<local>/AAAA-MM.json` (mês de
   `hora_modelo`). Nunca apaga; enquanto o registro está no histórico rolante,
   a versão do robô substitui a arquivada (inclui reconferências). Cada robô só
   escreve na própria pasta, sem conflito de rebase entre Santa Tereza e Muçum.
   Uma falha no arquivo gera aviso e não bloqueia a publicação da previsão.
2. **Recuperação:** o arquivo foi preenchido com a última versão de cada dia do
   histórico rolante no git (125 dias em Santa Tereza desde 18/07; 119 em Muçum
   desde 24/07). Como o robô gera ~70–100 registros/dia e o rolante guarda
   1.200, a amostragem diária não perde registros. Resultado: 9.966 registros
   de Santa Tereza e 10.027 de Muçum.
3. `scripts/avaliar_arquivo_ao_vivo.py` publica
   `assets/data/avaliacao_prospectiva_ao_vivo_latest.json` com MAE, P95, viés e
   skill contra a persistência **em cheia** e **na subida em cheia** (+50 cm ou
   mais no horizonte), além de disponibilidade (lacunas). Os recortes por
   regime em todas as horas ficam no JSON só como registro.

## Achados em cheia (Muçum ≥ 500 cm)

| Horizonte | Modelo | Horas | MAE RNA | MAE persistência | Subida em cheia: RNA / persistência |
|---|---|---|---|---|---|
| 2h | V001 (desde 27/08) | 433 | **6,9** | 11,5 | 51,5 / 73,1 (n=11, viés −36) |
| 4h | 015 (desde 28/09) | 249 | **23,0** | 46,5 | 49,8 / 112,5 (n=49) |
| 8h | 032 (desde 28/08) | 325 | **53,9** | 88,7 | 101,3 / 199,5 (n=96) |
| 8h B | 034 | 325 | 59,3 | 88,7 | 103,9 / 199,5 |

1. **Em cheia, as RNAs de Muçum ganham com folga da persistência** em todos os
   horizontes: cortam o erro pela metade na subida.
2. **A 2h ainda fica abaixo do real na subida rápida** (viés −36 cm em 11
   horas), o mesmo padrão da triagem do PR #306.
3. **Santa Tereza teve poucas horas acima de 1.500 cm** no período (11 na 2h
   atual; nenhuma desde a entrada da 4h V11 em 08/10). Ainda não dá para
   concluir; o arquivo permanente é o que vai permitir juntar essa prova.
4. **A previsão some na cheia.** A 8h de Muçum ficou 253 h sem previsão a partir
   de 21/09/2026 19h — a maior cheia do período (pico de 1.538 cm em 28/09)
   ficou sem nenhuma previsão de 8h. A 4h de Santa Tereza teve lacuna de 62 h no
   mesmo evento. É o problema mais grave encontrado: a previsão falta justamente
   quando é necessária.

## Próximos passos sugeridos

- Investigar a causa das lacunas de 21–24/09 (fonte ANA, contrato de entrada,
  guardrail) e garantir que a previsão não desligue em cheia.
- Muçum 2h: corrigir a subestimação da subida (ver
  `docs/mucum_candidato_regimes_20261119.md` e #306).
- Repetir esta avaliação a cada cheia: `python -B scripts/avaliar_arquivo_ao_vivo.py`.

Limites: poucas cheias no período (em Muçum, 28/09–02/10 com 1.538 cm, 03–05/10
com 641 cm, 04–07/11 com 953 cm e algumas pequenas perto de 500 cm); os modelos
trocaram ao longo do tempo, então períodos diferentes têm cheias diferentes.
