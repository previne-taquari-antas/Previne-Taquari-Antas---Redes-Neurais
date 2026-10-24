# Porto Alegre — endereços CNEFE 2022 × edificações reais

**Área:** município de Porto Alegre (IBGE **4314902**). **Escopo:** todos os registros de **domicílio particular** do CNEFE 2022 (`COD_ESPECIE=1`), nunca contagens de população individual. Esta frente é independente dos recortes de Santa Tereza e Muçum.

## Como executar

1. Baixe os dados **oficiais completos** do IBGE em [CNEFE 2022 — municípios/RS](https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/43_RS/), arquivo `4314902_PORTO_ALEGRE.zip` (ou deixe o script baixá-lo). O arquivo tem logradouro, número, complemento, espécie, `NV_GEO_COORD`, latitude e longitude.
2. Exporte as **geometrias completas** das edificações do OSM para Porto Alegre em GeoJSON WGS 84, com tags `building`, `addr:street`, `addr:housenumber`, `amenity` e `landuse`, sempre que existirem. No QGIS/QuickOSM, use o filtro `building=*` e o limite do município; valide cobertura e data do extrato. Para uma grande cidade, prefira extrato PBF Geofabrik/OSM filtrado pelo limite municipal a uma única consulta Overpass sujeita a expirar. NÃO forneça apenas centroides dos edifícios: polígonos são necessários.
3. Execute:

```bash
python -m pip install shapely pyproj
python scripts/vincular_cnefe_edificacoes_porto_alegre.py \
  --osm caminho/edificacoes_porto_alegre.geojson \
  --saida saida_porto_alegre
```

Use `--cnefe caminho/4314902_PORTO_ALEGRE.zip` se o ZIP já estiver baixado. A primeira execução sem `--cnefe` tenta baixá-lo do endereço oficial.

O workflow [.github/workflows/porto-alegre-cnefe.yml](../.github/workflows/porto-alegre-cnefe.yml) automatiza o download completo e o processamento. O resultado integral fica no artefato do GitHub Actions, não é incorporado automaticamente ao mapa público. O extrato OSM é fixado em 22/10/2026 para reprodutibilidade. Caso uma etapa de download falhe, NÃO interprete o relatório incompleto como resultado censitário.

Para conferir qual construção corresponde ao número do CNEFE, abra **dois arquivos** no revisor: `revisao_street_view.csv` e `edificacoes_revisao.geojson` (polígonos OSM próximos dos candidatos). Clique primeiro no endereço IBGE e depois na edificação correta no mapa. O registro de decisão exige evidência e pode ser exportado para reprocessar com `--revisoes`. Nenhum ponto do arquivo de sugestões é apresentado como residência já validada.

Abra `pesquisas/porto-alegre-domicilios-revisao.html` no navegador e selecione `revisao_street_view.csv` para ver, sobre mapa de ruas ou imagem aérea, o ponto original (laranja) e a edificação candidata (azul). O mapa exige conferência humana, registra a evidência informada e exporta `revisoes_aprovadas_porto_alegre.csv` sem alterar o CNEFE. Para produzir as coordenadas corrigidas após revisão, passe esse arquivo em `--revisoes`.

## Saídas, regras e garantias

- `associacoes_auditoria.csv`: **um registro por finalidade domiciliar original** do IBGE, inclusive quando vários endereços ocupam a mesma coordenada. Guarda endereço/posição original, tipo de geocodificação, status, edificação candidata, distância e coordenada **proposta, não confirmada**. É o arquivo interno principal; não publique na Web sem avaliação de privacidade e necessidade.
- `revisao_street_view.csv`: fila priorizada para conferência visual, incluindo vínculo para abrir Street View. Street View pode estar indisponível, antigo ou não cobrir a rua. Complementar com imagem aérea datada, cadastro municipal e vistoria, quando necessário. É proibido presumir ocupação domiciliar a partir de telhado ou fachada isolados.
- `amostra_mapa.geojson`: amostra determinística de coordenadas originais para inspeção/cartografia; não é uma camada de casas corrigidas.
- `pontos_revisados.geojson`: **somente** locais associados após a aprovação manual documentada. Vazio até existirem decisões aprovadas.
- `resumo.json`: contagens originais, candidatos, edificações distintas, pontos compartilhados, aprovados, pendências. Essas variáveis **não são intercambiáveis**.

### Regra da esquina

`NV_GEO_COORD=3/4/5/6` indica coordenada estimada ou agregada (face, localidade, setor), mais propensa a associações geométricas erradas. Se vários domicílios estão no mesmo par de coordenadas, o script **não os distribui por acaso**. `NV_GEO_COORD=2` pode representar apartamentos no mesmo prédio; isso não autoriza distribuir unidades em construções vizinhas.

Tags `building=warehouse`, `industrial`, `commercial`, `school`, `hospital`, `church`, `shed`, `garage` e usos afins são excluídos de possíveis destinos. `building=yes` não prova moradia. Um candidato residencial com mesmo logradouro e número OSM fica **aguardando conferência visual**; a proximidade espacial (até 40 m na busca preliminar, configurável) é filtro, jamais validação.

Se um endereço foi aprovado em Street View / campo / cadastro municipal, registrar no CSV de aprovações as colunas:

```csv
id_cnefe,osm_id,tipo_confirmado,evidencia,uso_residencial_conferido
```

Exemplo de uma linha de decisão (IDs ilustrativos, não reais): `ID-EXEMPLO,way/123456,domicilio,fachada e número na imagem de 2025,sim`.

Rode novamente com `--revisoes aprovacoes.csv`. Só então o ponto vinculado é emitido em `pontos_revisados.geojson`. Se edificação cadastrada como não residencial só puder ser classificada após inspeção, `uso_residencial_conferido=sim` não ignora exclusões explícitas já filtradas, que devem ser corrigidas na fonte ou isoladas na investigação.

**Controles de qualidade:** conferir índice de coincidência número/logradouro, percentual por nível de geocodificação, falsos positivos de galpões, duplicação esperada em prédios, taxa de aprovação por bairro e amostra independente. Nenhum registro removido por falta de candidato. Não integrar às rotas nem à classificação de inundação como domicílio confirmado antes da revisão.

Fontes: IBGE/CNEFE 2022, notas metodológicas e dicionário; OpenStreetMap (© contribuidores), Street View quando visualizado manualmente, com registro da data da imagem e termos de uso. Não extrair nem redistribuir imagens do Street View sem licença.
