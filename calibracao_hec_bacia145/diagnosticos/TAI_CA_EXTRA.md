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
