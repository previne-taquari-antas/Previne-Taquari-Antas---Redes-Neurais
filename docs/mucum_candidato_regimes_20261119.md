# Muçum — candidato linear com chuva e Santa Tereza contra a RNA ao vivo

Pesquisa, 19/11/2026. Não altera o robô ao vivo e não é alerta oficial.
Reproduzir: `python scripts/experimento_mucum_candidato_regimes.py` (pandas +
scikit-learn, ~5 s). Resultado: `assets/data/research_mucum_candidato_regimes_latest.json`.

## Pergunta

A triagem do PR #306 mostrou, só em horas de cheia, que a chuva média da bacia
e o nível de Santa Tereza reduzem a subestimação das subidas. A avaliação
prospectiva (`docs/avaliacao_prospectiva_ao_vivo_20261119.md`) mostrou outro
problema: as RNAs de 4h e 8h erram muito **com o rio parado**. As mesmas
entradas resolvem as duas coisas, em todas as horas?

## Método

- Dados: série horária contínua de 26/09 a 19/11/2026 (Muçum, Linha José
  Júlio, Santa Tereza, chuva média da bacia) e as cheias históricas do G040
  (2023, 2024, jul/2026), que ficam sempre no treino.
- Modelo: Ridge sobre a variação do nível, com as variáveis do #306.
- Validação: blocos de 7 dias; o bloco testado sai do treino com margem de
  48 h + horizonte de cada lado.
- **Comparação justa:** só as horas em que a RNA ao vivo tem registro
  conferido. Verdade e persistência vêm do próprio registro do robô; o
  candidato = nível do robô agora + variação prevista.
- **Alinhamento descoberto:** o rótulo `time_local` do CSV de pesquisa fica
  1 h à frente de `hora_modelo` do robô (diferença média 2,8 cm com o
  deslocamento, 10 cm sem). A chuva entra atrasada em mais 1 h por cautela.
  Os resultados de 4h e 8h se mantêm com deslocamento de 0, 1 ou 2 h.

## Resultado (MAE em cm, mesmas horas)

| Horizonte | Horas | Persistência | RNA ao vivo | M+LJJ | M+LJJ+chuva | M+LJJ+STZ+chuva |
|---|---|---|---|---|---|---|
| 2h | 1.015 | 9,2 | **8,0** | 14,3 | 14,0 | 18,4 |
| 4h | 1.011 | 33,5 | 35,6 | 24,0 | 22,3 | **21,0** |
| 8h | 837 | 57,4 | 78,6 | 38,7 | 34,0 | **30,8** |

Por regime (melhor candidato contra RNA ao vivo):

| | Rio estável | Subida ≥ 30 cm | Descida ≤ −30 cm |
|---|---|---|---|
| 4h | 16,7 vs 27,5 | 27,1 vs 53,0 | 25,5 vs 27,3 |
| 8h | 32,5 vs 87,1 | 36,1 vs 96,7 | 25,7 vs 59,3 |

Só o período depois da correção de contratos de 12/11 (#299), com poucas horas:
4h 18,1 vs 43,9 cm; 8h 24,0 vs 62,1 cm. A vantagem continua.

## Leitura

1. **Em 4h e 8h, até o modelo linear mais simples supera a RNA ao vivo** em
   todos os regimes. Chuva e Santa Tereza acrescentam ganho (8h: 38,7 → 30,8).
   O teste retrospectivo de #299 dava 31–34 cm para a 8h032. Ao vivo ela fica
   em 62–80 cm. A queda de desempenho entre teste e operação é o achado
   principal e precisa de explicação (entrada ao vivo diferente da de
   treino? escala? lacunas preenchidas?).
2. **Em 2h a RNA ao vivo é melhor.** O candidato perde com o rio parado
   (oscila ~11 cm, contra 4 da persistência). Para 2h o problema a atacar é só
   o viés nas subidas (−20 cm).
3. Com o rio parado, o candidato ainda erra mais que a persistência (4h: 16,7
   vs 4,5). Uma combinação com a persistência quando não há chuva nem
   tendência é o próximo teste natural.

## Limites

- Não é teste prospectivo: é validação em blocos sobre 8 semanas de 2026,
  enquanto a RNA foi avaliada de fato ao vivo. O candidato tem a vantagem de
  ver dados limpos (CSV de pesquisa, lacunas ≤ 2 h interpoladas).
- Poucas cheias grandes no período; Santa Tereza só existe em 2026 nas séries
  usadas.
- O CSV é média horária; o robô lê o último valor.

## Próximos passos

1. Rodar o melhor candidato **em sombra no robô** (mesmas entradas ao vivo, sem
   publicação), gravando no arquivo permanente, para ter prova prospectiva de
   verdade.
2. Investigar a diferença teste × ao vivo da 8h032 (reconstruir as entradas ao
   vivo de algumas horas e comparar com o que o treino teria usado).
3. Testar a combinação com persistência em regime estável.
