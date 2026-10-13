# RS-122: resultado numérico e extensão — 13/10/2026

## Resultado do primeiro lote

Run GitHub `38284983152`, commit HEC `84401448f203ae6f29ff6e3f66a9c0120e4c742d`.
18 execuções concluídas; 6 artefatos preservados localmente em
`_analise_lateral/run_38284983152`. O pós-verificador compara as grades nativas,
metadados, limites exatos e nós exigidos externamente, com identidade e hashes
do lote e piloto fixados. Não usa métricas contra observado.

- A10 reproduziu exatamente o piloto `38147587943` nas duas janelas e 12 nós:
  máximo desvio 0 m³/s.
- Os filhos conservaram a geração da SB211 em todas as 12 verificações
  (duas janelas × três passos × janela/evento): máximo desvio aproximadamente
  10⁻⁶ m³/s. As outras 144 chuvas permaneceram idênticas.
- Em 164 comparações 5→1, pico e volume passaram nos limites de 1%:
  maiores diferenças absolutas 0,3773% e 0,2466%. Houve 50 reprovações pelo
  horário do máximo e zero estados temporalmente indeterminados por empate exato
  ou borda. As 50 reprovações incluem repetições entre braços e recortes.
- Em Muçum/J201, B1−B0 a 1 min alterou o pico −0,123775 m³/s em E4 e
  −0,125731 m³/s em E12, sem mudar o instante. O efeito não supera a variação
  examinada entre 5 e 1 min.
- Em J_RS122, a retirada da contribuição DOWN de montante reduz o pico
  B1−B0 em 5,72%/4,93% em E4/E12. Esse efeito de magnitude/volume supera a
  variação examinada entre grades; não demonstra aceleração da calha.

Estado: `diagnostico_inconclusivo_gate_falhou`. Reprodução e conservação estão
confirmadas; convergência temporal não foi demonstrada. Não houve calibração,
validação observacional, promoção do titular ou previsão de nível nesta etapa.

## Por que o horário pode mudar tanto

Em A/J211/E4 a 1 min há dois máximos locais: 13/07/2023 08:05,
2.101,930398 m³/s, e 10:52, 2.102,378640 m³/s. A diferença de amplitude é
0,02132%. A série de 5 min tem o máximo global às 08:05. A troca do máximo
global explica a diferença reportada de 167 min, sem provar que toda a onda
se deslocou esse tempo. Esse diagnóstico não muda o gate pré-registrado.

Os 18 `Rodada.log` registram término de cálculo e nenhum ERROR/FATAL. Há avisos
de difusividade e baixa declividade. O HEC eleva Tc ao passo em 17 SB a 10 min,
5 a 5 min, nenhuma a 1 min. As cinco afetadas a 5 min não alimentam R211,
conforme revisão independente. R199/R224 ainda têm avisos de difusividade a
1 min em julho e alimentam R211; são caminhos a investigar, não causas provadas.
Os stderr contêm aviso de anotação de mapa e `SystemExit: 1`; o script gerado
termina deliberadamente com `Exit(1)`. A conclusão foi conferida pelo log de
cálculo, CSV, metadados e hashes, e não pelo código de retorno da JVM.

Fontes completas: `comparacao_rs122_v1.json` no workspace desta conversa;
figura e máximos locais em `_analise_lateral/figura_rs122_v2`. A figura compara
somente simulações históricas e não representa uma previsão atual.

## Extensão pré-registrada antes do novo lote

Contrato separado `experimentos/rs122/extensao_2min.json`: seis execuções
A/B0/B1 × S2023_07/S2023_11 a 2 min, comparadas às saídas já congeladas de 1 min.
O menor Tc escrito é 3,3456 min. Manter Tc, R, hidráulica, chuva, perdas, estados,
bordas e parâmetros da mãe; alterar somente o passo e Muskingum Steps conforme
a regra já auditada. Exigir todos os Tc escritos >2 min e ausência de WARNING
42403 nos novos logs. Preservar DX/DT efetivos e avisos de difusividade.

Usar os mesmos limites: pico/volume ≤1%, instante ≤10 min; temporal indeterminado
quando empate exato ou borda. Avaliar janela completa e E4/E12; conservar a soma
dos filhos. A comparação 2→1 não apaga ou substitui o resultado 5→1. Mesmo se
passar, não certifica toda a forma do hidrograma nem isola só Muskingum-Cunge.

O runner exige `--extensao-2min`; o contrato original e snapshot de 27 fontes
permanecem intactos. Novo workflow opt-in `[rs122-e2]`, sem executar o lote
genérico nem repetir as 18 simulações originais. Não há seleção de parâmetros.

69 testes passaram; preflights JUL/NOV V2 prepararam os seis basins. V1 foi
bloqueado pela guarda antiga do adaptador, que não admitia 2 min; V2 inclui 2 min
e teste do dt explícito, sem mudar a regra física ou apagar a tentativa. A cópia
leve de artefatos exclui DSS para permitir conferência rápida; o artefato completo
continua preservando DSS. Copernicus e Jason aprovaram o escopo pré-execução.
Jason apontou diferenças Windows/Linux de CRLF nos hashes brutos e arredondamento
de até 6,94×10⁻¹⁸ no dicionário de inicialização dos preflights. Os basins efetivos
coincidem exceto Steps. O comparador exigirá pareamento dos manifestos cloud antes
de interpretar resultados; não foram relaxadas tolerâncias hidrológicas.

## Pareceres recebidos sobre o primeiro lote

- Copernicus: reprodução, conservação e diagnóstico úteis; convergência temporal
  não demonstrada; recomenda extensão 2→1, abaixo de todos os Tc escritos.
- Jason: conferiu 27 fontes, somas, volumes, metadados, seis manifestos e logs;
  conservação/rastreabilidade aprovadas no escopo; convergência temporal reprovada.
- Euler: reproduziu integralmente o JSON em memória, com resultado idêntico;
  software/conservação aprovados e convergência temporal reprovada. Revisão do
  delta da extensão ainda pendente.

As restrições hidrométricas de RS122, documentadas em `TAI_CA_EXTRA.md` e na
auditoria de origem, continuam válidas. Nenhuma aprovação desta etapa equivale
à aprovação da calibração ou operação.
