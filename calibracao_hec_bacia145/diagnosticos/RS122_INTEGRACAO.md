# RS-122: preparação do controle interno — 11/10/2026

Estado: **geometria candidata calculada, ainda não integrada ao HEC e não calibrada**.
Nada foi alterado no titular, nas séries originais, no sistema ao vivo ou no site.

## Resultado geográfico

Código: `codigo/preparar_controle_rs122.py`.
Saídas locais: `_analise_lateral/geo/rs122_v3/manifesto.json` e `particao.geojson`.
V1/V2 preservadas. V2 acrescentou sensibilidade espacial e dependências; V3
corrige o segmento final de 30 m apontado pelo revisor Copernicus.

Usa o MDT SRTM da reconstrução original, EPSG:31982, 30 m, e seus rasters
Whitebox D8 (não ESRI), links e sub-bacias no limiar de 150.000 células.
Não usa o LiDAR das seções como substituto do raster de drenagem.
Posto 86298000: coordenadas do inventário ANA/CERAN (-51,1892; -28,9414).
O cadastro local não declara datum: EPSG:4326 é hipótese explícita de trabalho,
não metadado confirmado. Snap não equivale à localização levantada da seção.
Snap à célula mais próxima do link 211, distância 32,8466 m; não foi escolhido
para aproximar a área publicada ou melhorar qualquer hidrograma.

| Medida | Resultado |
|---|---:|
| SB_211 original por pixels | 413,7678 km² |
| Área incremental da SB_211 antes do posto | 4,8168 km² |
| Área incremental da SB_211 depois do posto | 408,9510 km² |
| Comprimento de R_211 antes do posto | 374,56 m |
| Comprimento de R_211 depois do posto | 42.109,53 m |
| Acumulação D8 no ponto escolhido | 7.301,6631 km² |
| Área de drenagem publicada no inventário | 7.370 km² |

A separação da área é feita por conectividade D8 reversa restrita à SB_211, não
por proporção do comprimento nem pela diferença entre áreas do inventário.
Todos os pixels da SB_211 drenam ao seu outlet. Partes disjuntas, união igual ao
original e grades idênticas. A diferença simétrica raster/vetor original é
0,0000305 m² (arredondamento de reprojeção), abaixo do limite de um pixel (900 m²).
O segmento final chega ao centro da primeira célula do link 205, preservando
o R_211 original. Soma dos comprimentos: 42.484,0866 m; erro de fechamento
3,64×10⁻⁹ m e distância de Hausdorff 1,88×10⁻⁹ m. O código exige ambos ≤0,01 m.
Essa precisão numérica de fechamento não é acurácia física de um MDT de 30 m.
A recomposição é planimétrica (XY). O original contém Z e a candidata não:
comprimento e Hausdorff não validam cotas, declividades nem geometria hidráulica.

Sensibilidade de snap, duas células antes/depois na mesma linha: área incremental
4,8024–4,8582 km². É sensibilidade geométrica, não intervalo de confiança.

**Não confundir as bases de área:** o basin HEC soma 6.924,493 + 400,434 =
7.324,927 km² nos dois J de entrada. Com a parcela nova, resulta 7.329,7438 km²,
28,0807 km² acima da acumulação D8. O inventário dá outro valor. A origem dessa
diferença foi rastreada abaixo. Não foi feito ajuste de área.

### Rastreio da diferença de área (sem alteração da rede)

Código: `codigo/auditar_conectividade_rs122.py`.
Resultado: `_analise_lateral/geo/conectividade_rs122_v3.json` (V2 preservada).
V3 calcula a área do pixel pelo determinante da transformação e exige CRS
EPSG:31982 e grade de 30 m norte-acima, sem rotação; não fixa a área por literal.
Para 144 unidades, traçou o caminho D8 do pixel de maior acumulação; SB_211
entra com sua parcela de 4,8168 km². Além disso, contou todos os rótulos no
raster completo de contexto. É teste de conectividade de exutórios e fechamento
agregado, não classificação independente de cada pixel da área recortada.

Foram identificadas 12 divergências HEC versus D8: SB_051, SB_059, SB_064,
SB_079, SB_085, SB_088, SB_102, SB_105, SB_112, SB_116, SB_128 e SB_129.
Todas têm `link_id` original nulo. O construtor original
`gerar_bacia_hec_hms_taquari_antas_145.py` associa essas unidades de borda ao
trecho mais próximo do centroide, com método `nearest_in_basin_reach_for_edge_unit`.
No HEC elas drenam antes do posto; seus exutórios D8 não passam pela célula do posto.
Somam **50,278 km² nas áreas arredondadas do basin**.
Os 12 caminhos terminam em ponteiro D8 zero. Isso descreve o raster disponível,
não estabelece sozinho o destino hidrológico real dessas áreas.

| Componente do fechamento | Área km² |
|---|---:|
| Área HEC montante + parcela local | 7.329,743800 |
| Remover, somente na conta, 12 ligações de borda divergentes | −50,278000 |
| Restaurar arredondamento das áreas HEC versus polígonos | +0,003741 |
| Área dos polígonos que drenam por D8 + parcela local | 7.279,469541 |
| Diferença pixels do recorte versus polígonos | +0,692559 |
| Pixels dos mesmos rótulos fora do recorte da auditoria original | +21,501000 |
| Área calculada pelos rótulos no raster completo | **7.301,663100** |
| Acumulação D8 na célula do posto | **7.301,663100** |

Fechamento agregado: **0 km² de diferença**. Não apareceram rótulos novos a
montante fora da lista de 145; os 21,501 km² correspondem à extensão de rótulos
existentes no raster completo, além do recorte original. Não confundir
`area_pixel_km2` do GeoJSON antigo com contagem do raster de contexto completo.

O achado prova uma aproximação estrutural na conectividade e reconcilia os
números de área. **Não prova que essa aproximação explique o erro dos picos**.
Ainda é necessário um experimento HEC pareado; não excluir automaticamente as
12 unidades nem adicionar terreno externo sem reavaliar o divisor hidrográfico.

## Origem da vazão

Código: `codigo/auditar_origem_rs122.py`; saída `_analise_lateral/origem_rs122.json`.
Leitura do XML arquivado de `DadosHidrometeorologicos` da ANA, sem nova coleta.

- Julho/2023: 440 registros XML/CSV iguais, todos com campo `Vazao` preenchido.
- Novembro/2023: 491 registros iguais, todos com `Vazao` preenchido.
- Zero duplicatas, conflitos de carimbo ou divergências, incluindo nível/chuva.
- O coletor `hec_calibracao_20261005/baixar_ana.py` copia o campo `Vazao`; não
  calcula Q a partir de H nesta conversão.
- Isso NÃO comprova medição direta independente: origem física da Q, curva-chave,
  faixa válida e referência vertical não vêm nesse XML. Não foi localizada curva
  desse posto na busca direcionada dos arquivos `dados_ana`.
- Permanecem as lacunas e restrições de ondas/qualidade de `TAI_CA_EXTRA.md`.

## Integração ainda necessária

1. Rastreio concluído acima. Preparar variante que trate explicitamente o divisor
   e as ligações de borda, preservando a bacia original como controle. Não alterar
   as áreas para forçar coincidência com o inventário.
2. Criar variante explícita com 146 SB/106 R e junção no posto. O padrão 145/105
   permanece intocado. `hec.py`, `bacia_inteira.py` e `estrutura_v3.py` têm guardas
   145/105: não removê-las globalmente para permitir uma variante.
3. Recalcular atributos de terreno, geometria hidráulica e transformação dos
   filhos. Manter a distinção entre superfície do MDT e leito submerso.
4. Recalcular a espacialização da chuva para as áreas novas, auditando intervalo,
   estação, pesos, cobertura e volume. Não rotular uma cópia da chuva da SB-mãe
   como espacialização independente dos filhos.
5. Construir DSS/met/pares e diretórios novos; cache da bacia antiga não pode
   passar por execução da nova. Conferir convergência temporal: o trecho de
   375 m exige avaliação numérica antes de manter saída em passo de 10 min.
6. Executar piloto com mesma chuva e parâmetros de referência, identificar o
   efeito da subdivisão antes de otimizar. Seleção posterior só em calibração;
   validação congelada e sem uso dos testes abertos para escolha.

## Verificação

Oito testes geográficos, cinco de transcrição e oito de conectividade passaram;
os quinze testes de extração e seis de decomposição anteriores também passaram
(42 no total, em cinco suítes).
Os arquivos brutos e as tentativas anteriores foram preservados. Dependências
geográficas estão em ambiente isolado `_analise_lateral/geo/.venv`, sem alteração
do ambiente do modelo operacional. Manifesto registra versões e hashes.

Os três especialistas concluíram revisões independentes, após tentativas que
retornaram limite de uso:

- Jason (`01a12b55-972a-7cb1-a92a-d9e2248bf833`): transcrição confirmada por
  comparação independente dos 931 registros e hashes. Não aprovou método de
  medição, independência de Q ou validade hidrométrica dos picos.
- Copernicus (`01a12b55-96bb-7212-bf6b-1d7822f99ec7`): identificou o segmento
  final omitido de 30 m; após correção, aprovou geometria V3 em XY e auditoria de
  outlets V2. Conferiu 144 caminhos, 277 rótulos, 12 divergências e fechamento.
  Executou os 14 testes geográficos/conectividade então existentes.
- Euler (`01a12b55-9798-7a12-a63f-9b8507a6558c`): reproduziu integralmente a
  auditoria V2 em memória, confirmou as 12 associações por distância aos trechos
  e aprovou geometria candidata V3 e diagnóstico. Executou os 19 testes então
  existentes. Recomendou calcular a área pelo determinante e exigir CRS/grade;
  proteção incorporada na auditoria V3 com dois testes adicionais. Reavaliou e
  aprovou essa alteração, executando ambos os testes novos. Não reavaliou o
  arquivo de saída V3; o executor o comparou integralmente com V2, excluindo
  somente `codigo_sha256`: resultado idêntico, fechamento ainda zero.

Nenhum parecer aprova correção da rede, integração no HEC ou calibração. O
fechamento é registrado, não um gate automático de aceitação; qualquer integração
futura exige tolerância explícita e testes de falha. Não reutilizar aprovação do
piloto anterior como aprovação da nova geometria, integração ou calibração.

## Referências do método

- USACE: divisão geográfica de sub-bacias/trechos e controles:
  https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/gis-tools-and-terrain-data/creating-a-georeferenced-model-using-hec-hms-gis-tools/using-merge-and-split-tools-to-customize-subbasin-and-reach-delineation
- Whitebox: convenção D8 e delineação por direção de drenagem:
  https://jblindsay.github.io/wbt_book/available_tools/hydrological_analysis.html

Essas referências sustentam o método, não certificam os dados nem os parâmetros
específicos desta bacia. Não há nova previsão de nível ou ganho de calibração aqui.
