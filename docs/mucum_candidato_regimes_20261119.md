# Muçum — candidato linear com chuva contra a RNA ao vivo, em cheia

Pesquisa, 19/11/2026. Não altera o robô ao vivo e não é alerta oficial.
Reproduzir: `python scripts/experimento_mucum_candidato_regimes.py` (pandas +
scikit-learn, ~5 s). Resultado: `assets/data/research_mucum_candidato_regimes_latest.json`.

**Foco: só cheia.** Contam as horas com Muçum ≥ 500 cm (`bankfull_cm` do robô)
na emissão ou na hora-alvo, como no #306. O erro com o rio baixo não entra nas
conclusões; os recortes de todas as horas ficam no JSON só como registro.

## Pergunta

A triagem do PR #306 mostrou, em horas de cheia, que a chuva média da bacia e o
nível de Santa Tereza reduzem a subestimação das subidas. Isso se confirma
contra a RNA **ao vivo**, nas mesmas horas?

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
  deslocamento, 10 cm sem). O CSV é média da hora, que vai até ~45 min além da
  leitura usada pelo robô: o candidato pode ter uma pequena vantagem aqui. A
  chuva entra atrasada em mais 1 h por cautela. Os resultados de 4h e 8h se
  mantêm com deslocamento de 0, 1 ou 2 h.

## Resultado em cheia (MAE em cm, mesmas horas)

| Horizonte | Horas | Persistência | RNA ao vivo | M+LJJ+chuva | M+LJJ+STZ+chuva |
|---|---|---|---|---|---|
| 2h | 202 | 12,8 | **6,8** | 16,4 | 29,9 |
| 4h | 212 | 50,9 | 29,1 | **15,1** | 28,5 |
| 8h | 128 | 88,7 | 64,9 | **34,3** | 35,4 |

Subida em cheia (+50 cm ou mais): 4h 22,3 (candidato) vs 49,1 (RNA) vs 116,3
(persistência), n=46; 8h 45,3 vs 93,2 vs 156,8, n=43.

Erro na hora do pico, por evento (cm, candidato / RNA):

| Evento | Pico | 2h | 4h | 8h |
|---|---|---|---|---|
| 28/09–02/10 | 1.538 cm | −12 / +1 | −11 / +59 | sem RNA (lacuna de 253 h) |
| 03–05/10 | 641 cm | −1 / +7 | 0 / +42 | −21 / −16 |
| 04–07/11 | 953 cm | −23 / +5 | +13 / +68 | −16 / −33 |
| 6, 9 e 10/10 (pequenos, ~500–530 cm) | | | +4 a +20 / −5 a +44 | −37 a +34 / **−205 a +244** |

## Leitura

1. **2h: a RNA ao vivo é a melhor** (6,8 cm em cheia, erro no pico ≤ 7 cm nas
   cheias grandes). O candidato não serve para 2h.
2. **4h: o candidato erra metade da RNA em cheia** (15 vs 29 cm) e no pico não
   passa de 13 cm, enquanto a RNA **superestimou os picos** em +42 a +68 cm
   nas três cheias maiores.
3. **8h: vantagem menos clara.** A diferença média (34 vs 65 cm) vem quase toda
   das cheias pequenas de outubro, em que a RNA errou ±200 cm. Na cheia de
   novembro (953 cm) os dois ficam próximos (MAE 38 vs 40 cm). A maior cheia do
   período ficou sem previsão de 8h.
4. A variante com Santa Tereza **piora em cheia** (2h 29,9; 4h 28,5), porque
   Santa Tereza não existe nas cheias históricas do treino. Fica fora da sombra.

## Contexto da RNA de 8h

- O erro oficial de teste da 8h032 é **49,4 cm**, medido nos eventos de cheia
  31, 33, 34, 35 e 37 (workbook de auditoria); os 31–34 cm do #299 eram de um
  subconjunto. Ao vivo, em cheia, ela fica em 54 cm no arquivo completo desde
  28/08 (`avaliacao_prospectiva_ao_vivo_latest.json`), perto do teste.
- O treino da 8h032 é de cheia (99,7 % das linhas com Muçum > 300 cm), o que é
  coerente com o objetivo do sistema. Os erros grandes fora da cheia não são
  relevantes para esta pesquisa.

## Limites

- Não é teste prospectivo: é validação em blocos sobre 8 semanas de 2026,
  enquanto a RNA foi avaliada de fato ao vivo. O candidato vê dados mais limpos
  (CSV de pesquisa, lacunas ≤ 2 h interpoladas).
- **Poucas cheias:** três relevantes (1.538, 641 e 953 cm) e algumas pequenas
  perto de 500 cm. Diferenças em um único evento são leitura qualitativa.

## Sombra (a partir de 19/11/2026)

Para ter prova prospectiva de verdade, o candidato **M + LJJ + chuva** foi
congelado para 4h e 8h e roda em sombra:

- Treino: `python scripts/treinar_candidato_mucum_sombra.py` →
  `config/mucum_candidato_ridge_v1.json` (coeficientes, padronização, hash,
  `congelado_ate` = 19/11 14:00).
- Variáveis: `scripts/mucum_candidato_features.py`, o mesmo código no treino e
  na operação (só biblioteca padrão).
- Operação: `.github/workflows/candidato-mucum-sombra.yml` roda depois de cada
  atualização dos CSVs pelo robô HEC (e de hora em hora, de reserva). Emite em
  todas as horas, porque a subida de uma cheia começa abaixo de 500 cm; usa só
  a hora completa mais recente (até 3 h de atraso), nunca reescreve uma
  previsão emitida e confere quando a hora-alvo aparece. Saída em
  `assets/data/mucum_candidato_sombra/`.
- **Avaliação:** só registros com `posterior_ao_congelamento = true` e só em
  cheia (nível na emissão ou no alvo ≥ 500 cm), comparando com a RNA nas
  mesmas `hora_modelo`, por evento e no pico.
- Não toca RNA, robô principal nem páginas. Não é alerta oficial.
