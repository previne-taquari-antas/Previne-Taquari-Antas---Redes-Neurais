# Correção das entradas das RNAs — 12/11/2026

O robô deve enviar à rede os mesmos sinais usados no treinamento. A conferência das planilhas arquivadas com os arrays físicos `Ptot` dos MAT demonstrou dois contratos diferentes de aceleração.

## Alterações

- Santa Tereza 2h A/B: a entrada15, chamada A-20h de Linha José Júlio, usa offsets `(0,1,19,20)`. A fórmula `DADOS_FORM!U100=(P100-P99)-(P81-P80)` e as 2.677 linhas das entradas das redes confirmam o deslocamento. Corrigidos montador, auditoria, diagnóstico de ausências e montagem exata da cascata 4h.
- Muçum4h015 e 8h032/034: as acelerações usam `N(t)-2*N(t-h)+N(t-2h)`. O montador usava mudança da variação de uma hora. A correção é específica dessas três receitas e foi confrontada com as planilhas e os respectivos Ptot.
- Muçum2hV001: mantém `[N(t)-N(t-1)]-[N(t-h)-N(t-h-1)]`, conforme a planilha original. Não generalizar a fórmula das redes4h/8h a esse modelo.
- As saídas e o histórico recebem uma versão de fórmula. Previsões calculadas pela fórmula antiga não são reutilizadas na contingência nem entram nos indicadores da fórmula nova. O histórico anterior permanece rastreável; previsões históricas não são reescritas como se fossem prospectivas.
- Muçum4h/8h continuam em acompanhamento sem publicação durante os primeiros seis pares prospectivos da fórmula corrigida; depois continuam sujeitos aos limites existentes de MAE24h30cm e erro máximo100cm. Corrigir a fórmula não valida automaticamente o desempenho.

## Verificação

`python -m unittest scripts.test_live_input_training_contracts scripts.test_previsao_ao_vivo_schema scripts.test_previsao_ao_vivo_mucum_schema scripts.test_stz_8h_excel_mother_contract`

61 testes passaram. A regressão usa dados reais dos workbooks e MAT, verifica as entradas reproduzíveis dentro do mesmo evento, a cascata2h→4h, a falta de leituras em t−2h, a preservação da fórmula2h de Muçum e a separação do histórico entre versões. Os dois workflows passam a executar essa regressão antes da consulta ANA.

## Oito e doze horas

Santa Tereza8h V001/V002 continuam suspensas. O diagnóstico observado de 12/11 às13:59 UTC−3 não tinha uma base completa: faltava nível de Santa Tereza naquela consulta e Nova Roma estava defasada; A894 não tinha chuva. Ausência no endpoint não prova sensor inativo. Não foi demonstrado nesta correção que essas redes possam ser reativadas.

Nenhum robô possui12h no cadastro operacional atual. Existem artefatos de pesquisa, entre eles STZ C0065 de12entradas, Muçum STC027 de15entradas e Muçum039 de28entradas com chuva18/24/48h. Eles não foram ativados por esta mudança. O candidato039 também contém a convenção de segunda diferença de passo h nos seus dados exportados.

Uma reprodução retrospectiva parcial de Muçum, usando somente linhas com todos os atrasos dentro de cada evento e mantendo a chuva observada exportada, reproduziu as previsões arquivadas com diferença máxima abaixo de5e−13cm. No subconjunto de teste:

| Rede | N | MAE com regra antiga (cm) | MAE com regra do treinamento (cm) |
|---|---:|---:|---:|
| 4h015 |118|20,18|23,59|
| 8h032 |201|31,38|34,39|
| 8h034 |201|36,69|39,37|
| 12h039, pesquisa |201|53,99|54,75|

Essa amostra não mede melhoria prospectiva e não equivale a reavaliar todos os eventos. Mostra que a fidelidade ao treinamento e a qualidade preditiva são questões diferentes: não há evidência de ganho automático de MAE com a correção. Para melhorar8h/12h, reavaliar chuva por sub-bacia e por atraso, cobertura temporal, propagação entre estações e validação por eventos inteiros, preservando eventos de teste fora da escolha dos modelos. MDT pode apoiar delimitação, declividade e tempos de percurso, após confirmação de cobertura, referência espacial/vertical e resolução. A topografia fixa de uma mesma bacia precisa entrar por atributos hidrológicos ou por um modelo de propagação, não apenas como mais uma constante na RNA.
