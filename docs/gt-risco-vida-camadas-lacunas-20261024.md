# GT Vulnerabilidades e Riscos — rastreabilidade das oito camadas

Auditoria de integração em 24/10/2026; a página em `pesquisas/gt-risco-vida.html` é exploratória, não um sistema de orientação de evacuação.

| Frente | O que há no mapa | O que impede validação operacional |
|---|---|---|
| MDT Santa Tereza | Visualização LiDAR georreferenciada, ~10 m, controle de transparência | Não substitui pontos altimétricos de campo, seção hidráulica nem raster original de 1 m |
| MDT Muçum | PNG georreferenciado ~10 m derivado de mosaico de 2 m; referência `assets/data/mucum_inundacao/mdt/altitude_terreno_10m.json` | Não equivale a LiDAR; requer verificação horizontal/vertical do mosaico |
| HAND/profundidade | Cenário HAND e classes por cota, notas metodológicas | HAND não é profundidade; faltam superfície de água 1D/2D, velocidade e remanso do Marrecão validado |
| Cota de isolamento | Cenários computacionais por nível e fichas de origem OSM | Entrada real dos imóveis, cotas das pontes e datum da régua; a 'ruptura legada' é apenas indício |
| Ruas/pontes | Grafo OSM com trechos projetados, classes e centralidade; testes por aresta na pesquisa | Inspeção de passagens, pontes, cabeceiras, danos e desconexões espúrias |
| CNEFE | Confronto 2022 × OSM e filtro preliminar de distância | Auditoria dentro de footprints e imagens atuais não concluída; ainda não há correspondência residencial verificada |
| Abrigos | Locais cadastrados e candidatos distintos; contagem por município | Disponibilidade, capacidade, acessibilidade e validação pela Defesa Civil; plano de Muçum tem capacidades 446/506/533 divergentes |
| 2023/2024 | Referências de cota históricas selecionáveis (em metros de régua) | Apenas cenários ilustrativos; NÃO constitui replay validado sem registros de abertura/fechamento de vias, inundação observada e ajuste vertical |

## Critérios para autorizar a palavra validado

- Domicílios: conferência entre endereço municipal CNEFE, footprint, uso e imagem aérea com data, amostra de inspeção e taxa de erro por classe.
- Hidráulica: comparação de cota de água, extensão, profundidade e comportamento de remanso com marcas de 2023/2024, com métricas e tolerâncias explicitadas.
- Rede: teste de circulação real por modo, avaliação de pontes e retorno por vias alternativas.
- Destinos: liberação por Defesa Civil, verificação de lotação e acessibilidade, cota do local e da rota.
- No painel: cada informação exibe fonte, data, resolução, confiança, estado de verificação e incerteza. Não divulgar rotas como seguras antes disso.

## Fontes efetivamente usadas

- MDT LiDAR ST: `assets/data/santa_tereza_inundacao/mdt/altitude_terreno_lidar_10m.json`.
- MDT mosaico Muçum: `assets/data/mucum_inundacao/mdt/altitude_terreno_10m.json`.
- Edificações e malha viária OSM: dados embutidos nos painéis gerados em 09/10/2026.
- CNEFE 2022: arquivos municipais IBGE, workflow de pesquisa, sujeito a comparação com ortofotos.
- Cheias de 2023 e 2024: eventos referenciados no campo `meta.cheias_ref` dos painéis, sem validação independente nesta etapa.
