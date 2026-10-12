# Experimento RS-122 — pré-registro 12/10/2026

Pesquisa numérica, sem otimização ou aprovação operacional. Titular pc-f8-c025,
família lrdcf8, rota mc, chuva v3b, papéis congelados. Sem testes abertos.

## Por que este passo

Os perfis nos mesmos vértices mostram que a queda dos 374,56 m de montante muda
de sinal: −0,8924 m no MDT de contexto e +0,2981 m no MDT dos atributos. Os
perfis de superfície não justificam escolher uma declividade hidráulica local.
O perfil inteiro no segundo raster reproduz os extremos originais do CSV.
Fonte local: `_analise_lateral/geo/perfis_rs122_v2.json`; código `perfil_rs122.py`.
Não usa valor absoluto nem suaviza para forçar queda. Copernicus reproduziu os
rasters, percentis, hashes e quatro testes, aprovando somente o diagnóstico.

## Configurações (mesma chuva e resposta hidrológica)

- A: 145 SB/105 R original, sem alteração no texto parametrizado.
- B0: 145 SB/106 R, divide R211, introduz J_RS122; SB211 inteira continua
  entrando antes do primeiro trecho. **J_RS122 de B0 não representa a área real
  do posto**. A×B0 mede segmentação/discretização.
- B1: 146 SB/106 R, divide também SB211; UP entra no trecho UP e DOWN no trecho
  DOWN, depois de J_RS122. B0×B1 mede reposicionamento lateral sob resposta
  herdada. Não é chuva espacial independente nem recalibração de Tc/R.

Manter explicitamente os valores finais de Tc/R, perdas, reservatórios, estados
específicos e ET da mãe nos filhos; chuva em mm idêntica. As áreas não multiplicam
a lâmina. Não usar RS-122 para inicialização. Não recalcular S_REF com 146 SB.
Manter as 12 ligações de borda para não misturar a correção da rede neste ensaio.

Hidráulica: mesmos slope 0,002064, seção trapezoidal, Manning e índice de vazão
efetivamente gravados no pai. Comprimentos seguem a regra vigente /1,10:
340,5 e 38.281,4 m. Isso é transferência experimental, não levantamento físico.
Áreas geográficas 4,8168 + 408,9510 = 413,7678 km². A mãe HEC tem 413,768;
o resíduo numérico 0,0002 vai para DOWN no arquivo HEC, sem modificar polígonos.

## Execuções e verificações previstas antes dos resultados

Duas janelas completas (S2023_07/S2023_11), cada uma com passos 10, 5 e 1 min;
três configurações em cada par janela/passo: 18 execuções. Não há seleção.
Cada execução usa pasta nova, DSS novo por braço, preservando DSS, logs, parâmetros,
metadados e hashes. A função padrão `rodar_lote` não é usada porque limpa caches.
O adaptador não muda guardas 145/105 de `hec.py` ou `estrutura_v3.py`.

Verificar:

1. A em 10 min contra `dl-piloto` nos controles, mesma inicialização/forçamento.
2. Mesmas séries de chuva das outras 144 SB e fechamento horário de volume
   usando as áreas escritas no basin. Filho não pode coexistir com mãe no DSS.
3. SB_UP + SB_DOWN contra SB211 de A: pico, volume e máximo desvio ponto a ponto
   na grade comum; tolerância prévia abs 0,001 m³/s + rel 0,01% por instante,
   volume relativo ≤0,01%; não presumir identidade da implementação HEC.
4. A/B0/B1: volume integrado, pico e instante nos controles e nós internos;
   diferenças numéricas não são erro contra observado.
5. Convergência 10→5→1 min, comparações na janela completa e recortes E4/E12.
   Critério diagnóstico prévio 5→1: variação ≤1% em pico e volume, horário ≤10 min.
   É tolerância numérica de triagem, não aprovação científica do modelo.
6. Conferir logs Muskingum-Cunge, metadados DSS, ausência de valores inválidos,
   duplicatas e lacunas. Não extrapolar saída ou preencher falhas.

O gerador original é sempre chamado em 10 min para congelar K, pisos e parâmetros.
Nos passos menores, o adaptador altera somente Muskingum Steps e fornece dt_h
explicitamente (a função original captura 10 min no argumento padrão). Mantém
limite do HEC de 100 passos; bloqueia em vez de trocar K/x se inadmissível.

Correções do preflight preservadas em pastas distintas: V1 identificou a junção
terminal J157 sem Downstream; guardas aceitam somente esse terminal cadastrado.
Nov1/V1 identificou mistura entre piso de K com passo novo e argumento padrão
antigo. Nov1/V2 passou após a separação descrita acima. Nenhuma dessas tentativas
preliminares executou HEC. Perdas/base intensivas foram conferidas nos arquivos
reais; não há duplicação de vazão inicial absoluta. V3 julho verificou conservação
horária da chuva após serialização e identidade dos blocos de resposta dos filhos.

Somente depois comparar J_RS122 de B1 à Q publicada ANA, preservando as
restrições da curva-chave e lacunas. Nenhuma conversão vazão→nível autorizada
por este experimento. Sem seleção na validação e sem promoção do titular.

## Revisões

Copernicus propôs e apoiou o desenho A/B0/B1, com transferência explícita da
hidráulica e resposta da mãe. Jason mapeou as fontes/IDW para um B2 posterior
(recalcular nos centroides e controlar volume) e depois aprovou o protocolo
A/B0/B1 com 6 testes, condicionado à conservação efetiva das saídas. Euler
aprovou componentes, apontou a cobertura raster e o dt padrão capturado, ambos
tratados; revisão final do runner pendente. A contagem de centros de pixels foi
separada da verificação de limites/NoData com all_touched. V2 preserva os perfis.
Execução experimental não equivale à aprovação das saídas ou da calibração.

Atualização antes do despacho: Copernicus favorável à execução isolada; Jason
favorável ao desenho. Foram congeladas 27 fontes em `experimentos/rs122/fontes.json`,
incluindo parâmetros/papéis, basin, MDTs tabulares, catálogo, chuva e observados.
O snapshot geométrico foi conferido localmente; os rasters não serão distribuídos
à nuvem, e isso é declarado no manifesto. Hash da partição corrigido para 64 dígitos.
O runner exige chuva horária contínua/ordenada com extremos exatos da janela;
prepara os três braços antes da primeira JVM; valida gages/met/ET e metadados
DSS de saída. CI opt-in exclusivo `[rs122]`, sem cancelar lote145 na mesma branch.
Todos os seis preflights V4 (janelas × passos) passaram, totalizando 18 basins.
36 testes RS122 e 21 testes anteriores passaram. Euler concluiu a revisão final:
27/27 hashes conferidos; grade temporal/transferência/MET/ET/gages e contratos
aprovados para executar o experimento, sem P0/P1 remanescente identificado.
Executou 36 testes e verificou escritor meteorológico em memória, sem HEC.
O workflow inclui `teste_contrato_runner_rs122`. Nenhum parecer aprova resultados,
convergência, calibração ou uso operacional. Pós-verificador `comparar_rs122.py`
deve ser revisado separadamente antes de interpretar os resultados.

Referência USACE: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/channel-flow/muskingum-cunge-model
O método depende da geometria e discretização; o ajuste automático de DX/DT
não substitui o ensaio de convergência aqui proposto.
