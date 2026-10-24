# GT Vulnerabilidades e Riscos — Relatório da rodada 24/10/2026

**Fonte:** GitHub Actions, workflow GT risco a vida, run 40107491502 (sucesso).  
**Método:** scripts/gt_risco_vida.py, gt_cnefe_residencias.py, gt_auditar_residencias.py, gt_destinos.py.  
**Validade:** pesquisa. Sem homologação de rotas, moradias e abrigos. Os resultados de rede usam o painel estático gerado em 09/10/2026 e edificações OSM como origens. Os pontos CNEFE não foram ainda reatribuídos individualmente ao grafo: o confronto é de proximidade.

## Síntese

| Indicador | Santa Tereza | Muçum |
|---|---:|---:|
| Edificações OSM no modelo publicado | 565 | 1.937 |
| Unidades de domicílios particulares no CNEFE 2022 | 890 | 2.270 |
| Pontos CNEFE residenciais distintos | 885 | 2.061 |
| Pontos residenciais CNEFE até 30 m de uma edificação OSM no painel | 318 | 1.452 |
| Pontos CNEFE sem OSM até 30 m | 567 | 609 |
| Edificações OSM com primeira perda de saída modelada antes da inundação | 327 | 638 |

O universo CNEFE é municipal, enquanto o painel OSM possui recorte urbano limitado. Divergência não implica edificação errada: os pontos sem OSM incluem residências fora do recorte e possíveis novas edificações, erros de mapeamento ou casos de coordenada distinta. Registros IBGE não certificam ocupação em 2026.

### Contagens da simulação (cenários de régua 15 m Santa Tereza / 18 m Muçum)

Santa Tereza: 18 edificações na mancha; 405 com acesso somente a ponto elevado candidato; 59 exigem arestas com cota desconhecida; 15 com conexão na rede cartografada; 52 sem nó de acesso; 16 sem conexão seca modelada. 177 origens possuem cota de inundação indeterminada (categoria sobreposta).

Muçum: 115 edificações na mancha; 145 dependem somente de ponto candidato; 577 exigem arestas de cota desconhecida; 1.079 com conexão no grafo cartografado; 1 sem nó de acesso; 20 sem conexão seca modelada. 502 origens possuem cota de inundação indeterminada (categoria sobreposta).

Classificações não são recomendações de evacuação; as origens não têm acesso porta–rua, ponte e abrigo inspecionados. Nem todas as edificações OSM são residências. A regra de 30 m identifica apenas proximidade espacial.

## Inventário de destinos

O Plano de Contingência de Muçum (julho/2026) contém **9 alojamentos e 2 pontos de encontro**. A atual camada de roteamento contém **6 desses 11**. Faltam: Centro Pastoral; EMEF Jardim Cidade Alta; EMEI Pingo de Gente; Estação Ferroviária; Salão Comunitário Brás Charléo (sem coordenada conhecida no cadastro). Antes de integrar, é necessário conferir geocodificação, estado operacional, capacidade, cotas de acesso e risco de ruptura de acesso.

O próprio plano tem capacidades divergentes: **446 / 506 / 533 pessoas** dependendo do quadro/anexo. Nenhuma dessas quantidades representa vagas em tempo real.

Santa Tereza possui um destino cadastrado no grafo, o Ginásio de Esportes; o centro histórico elevado deve ser investigado como possível proteção local sem equipará-lo a abrigo habilitado, e o caminho ao ginásio deve ser vistoriado.

## Testes e entregas

- 11 testes unitários passaram no GitHub Actions; processamento municipal, download CNEFE, confronto OSM e inventário de destinos concluídos.
- Arquivos gerados em artifact de pesquisa: GeoJSON de domicílios e faltantes, CSV por edificação, JSON de cortes por cenário, diagnósticos e abrigos. Fonte GitHub Actions: https://github.com/previne-taquari-antas/Previne-Taquari-Antas---Redes-Neurais/actions/runs/40107491502
- Implementação revisável no PR draft: https://github.com/previne-taquari-antas/Previne-Taquari-Antas---Redes-Neurais/pull/280

## Critérios antes de publicar como produto de gestão de risco

1. Conferência do cadastro CNEFE + OSM com ortofoto recente, recortes rurais e inspeção de amostra; resolver estrutura residencial e unidade domiciliar; sem atribuir condição individual.
2. Amarração vertical observada de régua, HAND, MDT e marcas de 2023/2024, com erros e envelopes espaciais.
3. Topologia de vias e passagens conferidas; água não atravessável, pontes com integridade e acesso físico, passagens não cartografadas e caminhos a pé/automóvel distintos.
4. Destinos verificados com autoridades, capacidade, acessibilidade, permanência de acesso, segurança de encosta e operação.
5. Validação cruzada por cheias e conferência em campo, incluindo cenários de velocidade de subida, preparação e grupos com necessidades de mobilidade.
6. Aplicar o método à malha intermunicipal da G040 e seus serviços antes de declarar mapa regional pronto.

## Referências

- IBGE. CNEFE, Censo 2022. https://www.ibge.gov.br/estatisticas/sociais/populacao/38734-cadastro-nacional-de-enderecos-para-finsestatisticos.html
- Mitropoulos, L.; Karolemeas, C.; Tsigdinos, S. (2025). Road network accessibility assessment during flood events by using infrastructure facility-based indices. International Journal of Disaster Risk Reduction, 122, 105475. https://doi.org/10.1016/j.ijdrr.2025.105475
- Altafini, D. et al. (2025). Formal Methods in Flood Disaster Response: The Case of Porto Alegre, Brazil. https://doi.org/10.1007/978-3-032-02782-5_28
