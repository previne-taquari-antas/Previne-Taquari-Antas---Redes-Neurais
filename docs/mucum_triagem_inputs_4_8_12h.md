# Muçum — triagem de inputs para a previsão de 4 h, 8 h e 12 h

Pesquisa, sem efeito no robô ao vivo. Reproduzir com
`python scripts/screen_mucum_input_candidates.py`; resultado completo em
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

## Próximos passos sugeridos

1. Re-treinar 4 h e 8 h incluindo os dias de águas baixas, ou separar um modelo por
   regime. É o maior ganho e não depende de input novo.
2. Rodar em sombra um 4 h com Santa Tereza e um 12 h com chuva observada + Rio da
   Prata, com o mesmo contrato de auditoria do ao vivo.
3. Incluir Jararaca e Balsa do Prata na coleta de toda rodada e registrar latência.
4. Repetir esta triagem com as cheias históricas (2023–2024) quando houver acesso
   aos dados das novas estações.
