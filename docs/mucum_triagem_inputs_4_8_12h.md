# Muçum — triagem de inputs para a previsão de 4 h, 8 h e 12 h

Pesquisa, sem efeito no robô ao vivo. O objetivo é acertar os **grandes eventos**;
a Parte 1 mede o erro só em cheia e é a que orienta as recomendações. A Parte 2
(todas as horas, incluindo a oscilação diária das usinas) fica como registro.

# Parte 1 — grandes eventos

Reproduzir com `python scripts/screen_mucum_flood_inputs.py`; resultado em
`assets/data/research_mucum_flood_input_screening_latest.json`.

## Como foi medido

- **Horas de cheia:** Muçum ≥ 500 cm na emissão ou no alvo.
- **Ramo de subida:** o rio sobe 50 cm ou mais dentro do horizonte.
- **Pico:** a previsão emitida h horas antes do pico de cada evento.
- **Eventos:** cheias de 2023–2024 e jul/2026 do arquivo histórico, mais quatro
  eventos de set–nov/2026. A validação deixa um evento inteiro de fora por vez.
- **Referência:** modelo só com Muçum + Linha José Júlio, nas mesmas horas.

## Resultado

Erro médio absoluto em cm, referência → com o input.

| Input somado | Horizonte | Eventos | Horas de cheia | Ramo de subida | Viés na subida | Pico |
|---|---|---|---|---|---|---|
| Chuva observada média da bacia | 4 h | 6 | 24,7 → 21,2 | 56,2 → 44,0 | −31 → −19 | 59 → 49 |
| | 8 h | 6 | 74,3 → 49,4 | 128,9 → 82,3 | −80 → −26 | 123 → 40 |
| | 12 h | 6 | 134,6 → 90,3 | 217,5 → 148,6 | −129 → −33 | 272 → 137 |
| Nível de Santa Tereza | 4 h | 4 | 23,0 → 20,6 | 40,9 → 32,8 | −28 → −18 | 24 → 25 |
| | 8 h | 4 | 67,1 → 54,0 | 92,3 → 76,5 | −64 → −49 | 53 → 47 |
| | 12 h | 4 | 118,9 → 88,3 | 133,2 → 113,3 | −100 → −77 | 171 → 116 |
| Santa Tereza + chuva | 4 h | 4 | 31,0 → 22,8 | 52,8 → 40,2 | −38 → −30 | 11 → 8 |
| | 8 h | 4 | 89,2 → 66,1 | 121,9 → 108,8 | −92 → −70 | 62 → 74 |
| | 12 h | 4 | 159,0 → 102,7 | 193,7 → 152,3 | −153 → −69 | 193 → 157 |

## O que isso diz

1. **O erro na cheia é subestimar a subida.** Só com réguas, o modelo fica em média
   31 cm abaixo em 4 h, 80 cm em 8 h e 129 cm em 12 h durante a subida. Na cheia de
   setembro de 2023 a previsão de 12 h para o pico ficou 12 m abaixo.
2. **Chuva já caída é o input que mais corrige isso**, e é o único testado em seis
   eventos, incluindo os dois de 2023. Reduz o erro em horas de cheia em 14% (4 h),
   34% (8 h) e 33% (12 h), e o viés na subida cai para um terço em 8 h e 12 h. As
   janelas usadas são acumulados de 3, 6, 12, 24 e 48 h.
3. **Média da bacia basta.** Separar a chuva em cinco sub-bacias deu o mesmo ganho
   em 8 h e 12 h e menos em 4 h.
4. **Santa Tereza ajuda em todos os horizontes** (10% a 26% nas horas de cheia), mas
   só pôde ser testada nos quatro eventos de 2026.
5. **Chuva prevista não acrescenta até 12 h.** Dando ao modelo a chuva futura
   observada (previsão perfeita), o erro não cai: 49,4 → 52,5 cm em 8 h e
   90,3 → 92,2 cm em 12 h. Nesse alcance o que manda é a água que já caiu.
6. **O modelo precisa extrapolar.** Com gradient boosting, a chuva não ajudou em
   cheia (8 h: 74,2 → 82,4 cm), porque árvores não preveem subida maior do que as
   que viram no treino. O modelo linear, que extrapola, aproveitou o input.

## Inconclusivo ou sem ganho em cheia

- **Rio da Prata (Balsa do Prata 86447000):** sozinho fica entre −9% e +4%. Com
  chuva o ganho em 8 h e 12 h é grande (45% e 62%), mas em menos de 200 horas e com
  cobertura irregular nas cheias históricas. Vale coletar; não dá para afirmar.
- **Rio Carreiro (Passo Carreiro 86500000):** piora de 15% a 28% em cheia.
- **Usinas (Monte Claro, 14 de Julho) e hora do dia:** só importam em águas baixas.

## Recomendação para grandes eventos

1. **4 h:** somar chuva observada (acumulados de 3 a 48 h) e Santa Tereza. Hoje o
   modelo de 4 h não tem nenhum dos dois.
2. **8 h:** trocar o acumulado único de 24 h por várias janelas de chuva areal da
   bacia e somar Santa Tereza.
3. **12 h:** mesmo conjunto; a chuva é indispensável nesse horizonte.
4. Treinar com arquitetura que extrapole e avaliar pelos critérios acima (horas de
   cheia, subida, pico), não pelo erro médio de todas as horas.
5. Garantir coleta contínua de Balsa do Prata para decidir sobre o Rio da Prata na
   próxima cheia.

## Limites

- Chuva: 6 eventos. Santa Tereza e Passo Carreiro: só os 4 de 2026, dos quais dois
  são pequenos (picos de 532 e 640 cm).
- O erro de pico é uma previsão por evento; leitura qualitativa.
- Não foi possível baixar histórico da ANA neste ambiente para estender Santa
  Tereza às cheias de 2023–2024.

# Parte 2 — todas as horas (inclui a oscilação das usinas)

Reproduzir com `python scripts/screen_mucum_input_candidates.py`; resultado em
`assets/data/research_mucum_input_screening_latest.json`.

## Resumo

1. **A maior parte do erro do ao vivo está em águas baixas, não na cheia.** Abaixo
   de 400 cm, Muçum sobe e desce ~145 cm por dia (mediana; 25 de 28 dias acima de
   80 cm) por causa da operação das usinas a montante. Os modelos ao vivo foram
   treinados em cheias e não conhecem esse regime.
2. **Só re-treinar com os mesmos inputs já corta o erro pela metade.** Nos mesmos
   instantes do histórico conferido:

   | Horizonte | Regime | Ao vivo | Mesmos inputs, re-treinado | Conjunto proposto |
   |---|---|---|---|---|
   | 4 h | todos (307) | 35,4 cm | 14,8 cm | 10,5 cm |
   | 4 h | águas baixas (218) | 42,1 cm | 13,3 cm | 9,2 cm |
   | 4 h | cheia (89) | 18,9 cm | 18,4 cm | 13,6 cm |
   | 8 h | todos (241) | 57,7 cm | 41,2 cm | 34,7 cm |
   | 8 h | águas baixas (155) | 67,6 cm | 32,0 cm | 30,2 cm |
   | 8 h | cheia (86) | 40,0 cm | 57,8 cm | 42,8 cm |

   Na cheia de 8 h o ao vivo atual segue melhor (40,0 contra 42,8 cm): ele foi
   treinado com mais cheias do que os 51 dias desta base.
3. **Inputs novos que somam ganho** (erro médio absoluto, validação por blocos):

   | Horizonte | Baseline (Muçum + L. José Júlio) | Com os novos inputs | Redução |
   |---|---|---|---|
   | 4 h | 16,2 cm | 11,5 cm | 29% |
   | 8 h | 36,6 cm | 30,8 cm | 16% |
   | 12 h | 58,2 cm | 43,4 cm | 25% |

## Inputs recomendados por horizonte

Em ordem de entrada na seleção; todos se somam ao baseline.

- **4 h** — nível de Santa Tereza (86472600): sozinho leva 16,2 → 13,0 cm e melhora
  nos 6 blocos. Depois: chuva observada média da bacia (3/6/12/24 h), Balsa do
  Prata (86447000) e vazão de Linha José Júlio.
- **8 h** — Rio da Prata pela PCH Jararaca (86125500): 36,6 → 32,4 cm. Depois:
  chuva média da bacia, Santa Tereza e chuva por sub-bacia (5 zonas).
- **12 h** — chuva observada média da bacia: 58,2 → 46,1 cm. Depois: Balsa do
  Prata, PCH Jararaca e Santa Tereza.

## Por que esses inputs — dinâmica da bacia

Defasagem até Muçum (correlação máxima entre variações de 2 h):

| Estação | Águas baixas | Cheia |
|---|---|---|
| Santa Tereza 86472600 | 3 h | 2 h |
| Linha José Júlio 86472000 | 6 h | 3 h |
| UHE 14 de Julho alça 86470900 | 8 h | 3 h |
| UHE Monte Claro Jusante 2 86450500 | 9 h | 4 h |
| UHE Monte Claro Jusante 1 86450000 | 12 h | 6 h |
| Balsa do Prata 86447000 | 8 h | 6 h |
| PCH Jararaca 86125500 | 7 h | 6 h |
| Passo Carreiro 86500000 | 4 h | 5 h |

- **A onda anda duas vezes mais rápido na cheia.** Linha José Júlio antecipa Muçum
  em 6 h em águas baixas e só 3 h na cheia. Por isso ela sozinha não sustenta 8 h
  nem 12 h em cheia: é preciso sinal mais a montante e chuva.
- **Santa Tereza é o sinal mais limpo para 4 h** (2–3 h de antecedência, correlação
  0,89–0,95) e hoje não entra no modelo de 4 h.
- **O Rio da Prata (3.776 km²) entra no Antas em Monte Claro** e chega a Muçum em
  6–8 h. É a peça que faltava para 8 h e 12 h; o ao vivo só olha o eixo do Antas.
- **Para 12 h a água ainda não está em nenhuma régua**: o que antecipa é a chuva já
  caída. O ganho isolado fica entre 18% e 24% em qualquer zona de chuva, então a média da
  bacia basta como primeiro passo.

## O que não ajudou

- UHE Castro Alves RS-122 (86298000), hoje no modelo de 8 h: −1,6% em 8 h (base
  com só 47% de cobertura, então o teste é fraco).
- Hora do dia e "mesma janela de ontem": entre −5% e +2%. O ciclo das usinas é
  melhor capturado pelas réguas do que pelo relógio.
- Monte Claro Jusante 1 e 2: ajudam 12 h em águas baixas (+13%) e pioram em cheia
  (−14%). Só fazem sentido em um modelo separado por regime.
- Rio Carreiro (vazão de Passo Carreiro): ganho pequeno, mas consistente em 8 h
  (+5%, 6 de 6 blocos). Candidato de segunda linha.

## Limites desta triagem

- 51 dias (26/09 a 16/11/2026) e duas cheias. Não foi possível baixar histórico da
  ANA neste ambiente; os ganhos precisam ser confirmados em cheias anteriores.
- A seleção combinada usa a mesma validação que reporta, então as reduções da
  tabela são levemente otimistas. Os ganhos de candidato isolado não têm esse viés.
- PCHs e UHEs têm ~45% de lacunas nesta base (coleta rotativa). Antes de usar
  Jararaca ou Balsa do Prata ao vivo, medir a latência real de cada uma.
- Chuva prevista (ECMWF) não foi testada: não há arquivo histórico de previsões
  alinhado a esta base.

## Observação

As recomendações valem as da Parte 1. Re-treinar para a oscilação das usinas reduz
o erro médio do painel, mas não é o objetivo e não melhora a previsão de cheia.
