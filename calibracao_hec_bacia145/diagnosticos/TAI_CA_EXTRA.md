# Diagnóstico lateral TAI–CA — 11/10/2026

Somente extração do titular pc-f8-c025, rota mc, com parâmetros inalterados e chuva v3b.
Não é recalibração, previsão atual nem aprovação operacional. Sem mudança ao sistema vivo.

## Correspondência espacial

Os três postos NÃO coincidem com as saídas do modelo. Extrair todos os componentes:

| Posto | Ramos de entrada | Lateral | Trecho / saída |
|---|---|---|---|
| 86118000 Cavalinhos I | J_217 + J_072 | SB_224 | R_224 / J_224 |
| 86220600 Palanquinho jus | J_226 + J_078 | SB_218 | R_218 / J_218 |
| 86298000 CA RS-122 | J_222 + J_089 | SB_211 | R_211 / J_211 |

Mapeamento revisado por Copernicus por conectividade, geometria e área acumulada.
O posto fica respectivamente a aproximadamente 13,85, 25,88 e 42,16 km da saída a jusante.
Essas distâncias são aproximadas na polilinha, não tempos de propagação medidos.
Fonte: a00_E27.basin, inventario_fluviometricas_86.json e trechos_taquari_antas_105.geojson.
Não subtrair hidrogramas deslocados nem converter diferença de nível em contribuição lateral.
Não apresentar Q na saída do trecho como Q no posto interior. SB é contribuição agregada: não separa a
área incremental antes/depois do posto. Barramento: pico de nível pode diferir de pico de vazão.

## Piloto e aceitação

Piloto nas janelas S2023_07 e S2023_11, com um único conjunto de parâmetros (titular).
Os arquivos observados de Palanquinho 86220600 nessas duas janelas contêm apenas cabeçalho.
Não pontuar timing observado desse posto no piloto. Há arquivos em 2026 a verificar em etapa
separada; isso não autoriza usar validação para escolher parâmetros.
Papéis dos eventos herdados do pedido pp-val; nenhum teste X20260918, X75 ou X76.
Parâmetros copiados exatamente de pp-val-c000 e conferidos contra o titular no sistema.
Não otimizar nem escolher candidatos nesta rodada. Métricas de validação não orientam ajustes.

1. HEC-HMS deve concluir todas as janelas.
2. Todos os componentes pedidos e controles devem ter série finita, sem duplicatas ou lacunas,
   passo de 10 min, do início até fim do controle, inclusive.
3. Os controles do titular devem reproduzir pp-val-c000; diferenças impedem interpretação causal.
4. SHA256 de parâmetros, bacia gerada, chuva JSON e CSV exportado acompanham cada janela.
5. Revisor de método e revisor de extração precisam concluir; falha de agente não é aprovação.

## Revisão de método recebida

Jason apontou em frente_observada.csv papéis antigos de E18/E22 e um máximo disponível em
CA/E18 antes de longa falha de registro, incorretamente chamado pico. Não reutilizar esses
rótulos nem essa medida como pico completo. Resolver papéis pelo catálogo + pedido congelado.
Proposta de QC antes de pontuar: mesma onda definida sem minimizar erro, cobertura ≥90% e
cobertura bilateral ±6h no pico, início/fim não censurados, platôs como intervalos e sem
preenchimento de lacunas. Tipo temporal e unidade DSS serão preservados em series_metadata.json.
Esses critérios ainda não foram aplicados aos postos intermediários; não são resultados.

Esta rodada é uma NOVA execução HEC-HMS na nuvem, com os parâmetros antigos mantidos.
As séries intermediárias não estavam nos CSVs arquivados. Não chamar esta execução de mera
leitura dos resultados existentes. As restrições de não executar HEC enviadas aos revisores
limitavam as tarefas dos revisores, não o pedido de continuidade da usuária ao executor principal.

Comparação temporal observada só depois de conferir cobertura e onda comum. Relatar platôs e censura,
sem interpolar lacunas. Nível e vazão são grandezas diferentes; timing de nível em barramento é proxy,
não observação da defluência. Se a malha impedir atribuir o erro, o resultado é inconclusivo e requer
inserção georreferenciada de controle interno, não ajuste artificial de horário.

## Resultado efetivamente executado e revisado — 11/10/2026

Run GitHub Actions 38147587943 (commit 2e7e31875b824b5f55da5b8e0212afa31d9ced92),
concluído com sucesso. Artefatos baixados em `_analise_lateral/run_38147587943`.
Pós-verificação: `_analise_lateral/posverificacao.json`.

| Janela | Elementos exportados | Pares nó × instante de controle | Maior diferença para pp-val-c000 |
|---|---:|---:|---:|
| S2023_07 | 24 | 23.050 | 0 m³/s |
| S2023_11 | 24 | 26.590 | 0 m³/s |

Os CSVs antigos continham 4.610 / 5.318 duplicatas idênticas; foram deduplicados
somente para comparação, preservando os originais. Os CSVs novos não têm duplicatas.
O catálogo tem CRLF no checkout Windows e LF no runner: o verificador registra
ambos os hashes e normaliza exclusivamente CRLF→LF na comparação. Não altera JSON,
chuva, parâmetros, séries ou o limite numérico de aceitação.

### Componentes simulados, somente calibração

`codigo/diagnostico_componentes_lateral.py` gera `_analise_lateral/componentes.json`.
Reproduz catálogo + papéis congelados, confere hashes, topologia, grade e R=J.
Não lê dados observados nem calcula lag observado. E3, de validação, não é analisado.

| Evento | Trecho | SB local / entrada no máximo combinado | Diferença entre horários dos máximos saída − entrada |
|---|---|---:|---:|
| E4 | R_224 | 4,57% | +1h00 |
| E4 | R_218 | 4,96% | +1h30 |
| E4 | R_211 | 6,01% | +2h30 |
| E12 | R_224 | 3,27% | +50min |
| E12 | R_218 | 4,40% | +1h20 |
| E12 | R_211 | 5,04% | +1h50 |

As três entradas de cada trecho (dois J e uma SB) são somadas ANTES de R.
R e seu J de saída coincidem exatamente. São 787 instantes por trecho em E4 e
1.795 em E12. Fração local NÃO é fração de toda a geração lateral TAI→CA; parte
dela já chega pelos J. Os horários dos máximos não são tempos observados de viagem
nem demonstram pareamento de ondas. Estes números não autorizam escolher parâmetros.

### Restrição dos observados intermediários

Revisão independente de Jason sobre os CSVs de `hec_calibracao_20261005/dados_ana/csv`:
horários mantidos como registrados, grade esperada horária, limites inclusivos,
sem conversão, preenchimento ou exclusão de linhas. Cobertura numérica não é qualidade física.

| Posto / evento | H presente | Q presente | Uso permitido neste diagnóstico |
|---|---:|---:|---|
| Cavalinhos I / E4 | 132/132 | 0/132 | Cronologia descritiva de H; não vazão |
| Cavalinhos I / E12 | 297/300 | 0/300 | Não usar máximo/recessão até esclarecer anomalia |
| Palanquinho / E4 | 0/132 | 0/132 | Indisponível no pacote |
| Palanquinho / E12 | 0/300 | 0/300 | Indisponível no pacote |
| CA RS-122 / E4 | 123/132 | 123/132 | Falha dentro de +6 h do máximo; timing não aprovado |
| CA RS-122 / E12 | 295/300 | 295/300 | Candidata; exige ondas, origem de Q e controle espacial correto |

Nenhuma duplicata de carimbo nos quatro arquivos com registros. Palanquinho contém
somente cabeçalho. Isso não prova ausência em outras fontes.

Anomalia Cavalinhos/E12 (86118000_S2023_11.csv, coluna nivel_cm; verificada também pelo executor):
- 18/11 14h: 48.399 cm; 15h: 47.278 cm → variação −1.121 cm em 1 h;
- 18/11 19h a 19/11 09h: 15 leituras consecutivas iguais a 47.070 cm;
- 19/11 10h: 48.208 cm → variação +1.138 cm em 1 h.

São valores do registrador, NÃO profundidade d'água. Causa não estabelecida:
sensor, referência, transmissão ou operação precisam de verificação. Não corrigir
por interpolação nem chamar o máximo imediatamente anterior de pico validado.
Esta restrição é específica do diagnóstico intermediário; não exclui E12 inteiro
dos outros controles e não modifica dados nem objetivos existentes.

Lacunas preservadas (2023):
- Cavalinhos/E12: 20/11 01h; 21/11 16h e 17h.
- CA RS-122/E4: 12/07 16h; 13/07 09h; 14/07 11h; 16/07 12h,13h,16h,17h,20h,23h.
- CA RS-122/E12: 15/11 14h; 17/11 17h,18h,19h; 22/11 14h.
- Palanquinho: ambas as janelas integralmente ausentes.

### Pareceres e continuação

- Euler: software, patch CRLF e reprodução independente dos componentes aprovados;
  seis testes novos passaram, além dos quinze testes do contrato de extração.
- Copernicus: topologia e decomposição descritiva aprovadas; rejeita atribuição
  do atraso total às três SB ou comparação direta posto interior versus outlet.
- Jason: QC concluído; restrições acima impedem aprovação quantitativa indiscriminada.

Nenhum parecer aprova recalibração ou operação. Não houve promoção, mudança do
titular nem atualização do site. O diagnóstico confirmou a execução, NÃO redução de erro.

Próximo experimento deve distinguir geração da região inteira e calha, com controles
espacialmente compatíveis e observações qualificadas; documentar critérios antes de
examinar candidatos, manter orçamento igual e escolher só por calibração. Não
ajustar o modelo para reproduzir o salto suspeito de Cavalinhos. Inserir controle
no posto RS-122 exige divisão georreferenciada de trecho e área incremental; não
substituir isso por uma fração do hidrograma de jusante ou deslocamento manual.

Referência metodológica consultada: USACE, Muskingum-Cunge Model,
https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/channel-flow/muskingum-cunge-model.
Documenta coeficientes dependentes da geometria e profundidade; não prova a causa
do erro deste projeto nem dispensa o experimento pareado.
