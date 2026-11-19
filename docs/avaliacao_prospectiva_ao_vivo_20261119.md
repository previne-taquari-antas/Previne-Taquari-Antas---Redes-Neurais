# Avaliação prospectiva das previsões ao vivo — 19/11/2026

Pesquisa. Não é alerta oficial.

## Por que existe

Os robôs guardam em `historico_previsoes_ao_vivo*.json` só os últimos 1.200
registros (cerca de 2 a 3 semanas). A agenda (`rna-multi-horizonte`) exige ganho
consistente **por evento** fora da amostra — e essa evidência estava sendo
apagada a cada ciclo.

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
   `assets/data/avaliacao_prospectiva_ao_vivo_latest.json`: MAE, P95, viés e
   skill contra a persistência, por regime do rio (subida ≥ +30 cm, estável
   < 10 cm, descida ≤ −30 cm) e disponibilidade (lacunas).

## Achados (modelos em produção hoje)

| Local | Horizonte | MAE rede | MAE persistência | Subida: rede / pers. | **Rio estável: rede / pers.** |
|---|---|---|---|---|---|
| Santa Tereza | 2h | 7,5 | 17,0 | 22 / 60 | 4,6 / 4,2 |
| Santa Tereza | 2h versão B | 7,3 | 16,4 | 19 / 59 | 5,0 / 4,2 |
| Santa Tereza | 4h V11 | 20,0 | 35,0 | 40 / 78 | 10,8 / 4,3 |
| Muçum | 2h | 7,6 | 8,9 | 34 / 46 (viés −21) | 5,3 / 3,8 |
| Muçum | 4h | 33,1 | 32,8 | 53 / 80 | **26,3 / 4,5** |
| Muçum | 8h | 67,7 | 62,1 | 90 / 121 | **66,4 / 4,4** |
| Muçum | 8h versão B | 67,2 | 62,4 | 88 / 122 | **63,0 / 4,4** (viés +36) |

(cm; períodos: STZ 2h desde 07/08, 4h V11 desde 08/10; Muçum 2h desde 27/08,
4h desde 28/09, 8h desde 28/08.)

1. **Santa Tereza 2h e 4h são robustos:** ganham da persistência em subida e
   descida e quase empatam com rio parado.
2. **Muçum 4h e 8h inventam movimento.** Com o rio parado, erram 26 cm (4h) e
   63–66 cm (8h), contra ~4 cm da persistência. No geral a 8h **perde** da
   persistência. O ganho nas subidas é real (≈ 26–34 %), mas vem junto de
   oscilações falsas — risco de alarme falso e de perder confiança.
3. **Muçum 2h subestima subidas** (viés −21 cm), o mesmo problema que a triagem
   do PR #306 encontrou em 4/8/12h.
4. **Disponibilidade cai na cheia.** A 8h de Muçum ficou 253 h sem previsão a
   partir de 21/09/2026 19h; a 4h de Santa Tereza teve lacuna de 62 h no mesmo
   evento. A previsão some justamente quando é mais necessária.

## Próximos passos sugeridos

- Muçum 4h/8h: testar um filtro/combinação com a persistência quando o rio está
  estável e sem chuva relevante, ou incluir as entradas da triagem (#306:
  chuva média da bacia, nível de Santa Tereza) e avaliar por regime.
- Investigar a causa das lacunas de 21–24/09 (fonte ANA, contrato de entrada).
- Repetir esta avaliação mensalmente: `python -B scripts/avaliar_arquivo_ao_vivo.py`.

Limites: poucas cheias grandes no período; regimes definidos pelo próprio
observado (não são conhecidos na hora da previsão); modelos trocaram ao longo do
tempo, então períodos diferentes têm hidrologia diferente.
