# Santa Tereza - camadas de inundacao

Atualizado em: 2026-10-01.

## Auditoria de remanso no Marrecão — 12/10/2026

**Situação: reprocessamento espacial PENDENTE.** Os contornos publicados
antes desta auditoria foram criados com `FLOWACC >= 50.000.000` células
(~50 km²), critério que também permite selecionar afluentes como o Marrecão,
cuja área contribuinte supera 50 km². O contorno antigo **não foi corrigido
pelo simples commit do código**. A classificação de edificações baseada nele
é suspensa pelo painel até que um produto novo identifique explicitamente
`metadata.river_reference_method = "eixo_dominante_taquari_D8"`.

O gerador atualizado usa o algoritmo
`codigo_python/02_mdt_hand_mancha/eixo_principal_taquari.py`, que sobe
pela rede D8 escolhendo o ramo de maior acumulação em cada confluência,
evitando incluir o Marrecão como eixo de referência. A extração tem trava
geográfica em relação à estação 86472600 e recusa eixos curtos ou distantes.

**Remanso não é subida local de 25 metros:** os 0–25 m publicados são o
domínio vertical HAND, não uma medição de elevação do Marrecão. O efeito de
remanso requer nível de contorno na foz, cotas altimétricas reconciliadas,
topobatimetria, obstáculos e verificação com eventos históricos. Corrigir
somente o eixo do canal reduz a confusão entre rios, mas **não constitui**
simulação 1D/2D validada de remanso nem comprova alcance nas casas.

Para ativar novamente a classificação individual:
1. Executar o gerador com os rasters LiDAR originais
   `CLIP_MOSAICO_LIDAR_RS.tif`, `FILL_CLIP_MOSAICO_LIDAR_RS.tif`,
   `FLOWDIR_CLIP_MOSAICO_LIDAR_RS.tif` e `FLOWACC_CLIP_MOSAICO_LIDAR_RS.tif`
   no diretório configurado (originalmente `D:\\PREVINE\\hand\\santa tereza`).
2. Confirmar o teste `tests/test_eixo_principal_taquari.py`, as coordenadas
   e o percurso do eixo, principalmente a confluência Taquari–Marrecão.
3. Auditar cota e extensão contra pontos observados e modelagem de remanso.
   A nova mancha traz a procedência do eixo em `contornos_mancha.json`.
4. Publicar o contorno e verificar as páginas pública e de pesquisa.

Até completar as etapas de recomputação/validação, manter o status pendente:
**o código está corrigido; a mancha hidráulica NÃO foi validada**.

## Produção atual (site)

A página ao vivo `santa_tereza_previsao_inundacao.html` usa o **HAND 5 m**
gerado a partir dos rasters de campo em `D:\\PREVINE\\hand\\santa tereza`.
O gerador original considerava `FLOWACC >= 50.000.000` células finas,
sem separar tributários. O código corrigido extrai o eixo dominante do Taquari
pela rede `FLOWDIR`/`FLOWACC`; a publicação da mancha nova está pendente. A calibração vertical
permanece separada: **1,60 m na régua = HAND 0**.

O gerador `codigo_python/02_mdt_hand_mancha/gerar_hand_lidar_santa_tereza.py`
também produz uma grade de altitude absoluta a ~10 m a partir do **LiDAR bruto**
`CLIP_MOSAICO_LIDAR_RS.tif`. O `FILL_CLIP_MOSAICO_LIDAR_RS.tif` é usado apenas
no roteamento. A página só aceita essa grade quando o
metadado declara `same_source_as_hand: true`, e posiciona a imagem usando os
bounds do próprio MDT.

**Estado atual:** o produto publicado usa o LiDAR bruto como terreno, com
FILL/FLOWDIR/FLOWACC restritos ao roteamento. A referência vertical é única:
**régua 1,60 m = HAND 0**, e os contornos publicados de Santa Tereza cobrem
**HAND 0–25 m**. O MDT web de apoio também vem da mesma fonte LiDAR
(`altitude_terreno_lidar_10m.json`).

A cadeia autoritativa é:

`LiDAR bruto 1 m → roteamento D8 → HAND hidráulico ~5 m → contornos LiDAR → mapas/impacto/rotas/replay`.

O deploy executa `scripts/validate_santa_tereza_lidar_contract.py` e falha se
as páginas voltarem a usar ANADEM, mosaico drone+ANADEM, MDT refinado legado,
HAND acima de 25 m para Santa Tereza, ou se a página ao vivo e a histórica
divergirem no payload HAND.

### MDT refinado antigo — legado, não usar na página ao vivo

Os arquivos abaixo pertencem ao mosaico anterior drone + ANADEM e foram
retirados da página ao vivo em 21/09/2026 porque não são espacialmente
compatíveis com o HAND 5 m atual:

- `mdt_refinamento_santa_tereza.json`;
- `mdt/altitude_terreno_10m_refinado.json`;
- `mdt/mdt_santa_tereza_10m_refinado_visual.png`;
- `codigo_python/02_mdt_hand_mancha/refinar_mdt_santa_tereza.py` (bloqueado por padrão; somente auditoria histórica explícita com `--legacy-audit-only`).

Eles permanecem apenas para rastreabilidade histórica. Não devem ser usados
para consulta de altitude, sobreposição visual ou cálculo junto com o HAND
atual.

## Camadas preliminares legadas

Esta pasta tambem contem duas camadas antigas do prototipo espacial:

1. `mancha_preliminar_santa_tereza.png` e `.geojson`
   - Recorte de `D:/PREVINE/inundacoes/profundidade_inund_v02.tif`.
   - Uso: mancha local preliminar para visualizacao no site.
   - Area positiva aproximada: 1369.67 ha.

2. `cenario_dem_na9765_santa_tereza.png` e `.geojson`
   - Cenario derivado do Copernicus DEM GLO-30 recortado.
   - Limiar: `NA 97,65 m`, extraido do anteprojeto publico da Ponte Santa Barbara.
   - Mascara filtrada por conectividade a partir dos pontos do rio/ponte/estacao.
   - Area aproximada: 1374.87 ha.

Arquivo de controle:

- `mancha_preliminar_santa_tereza.json`: metadados consumidos pela pagina do site.
- `protocolo_leave_one_event_out_estrangulamento.json`: proposta de teste RNA deixando fora um evento critico.

Pagina:

- `/santa_tereza_inundacao.html`

Fontes publicas principais:

- Compras RS Edital 0028/2024: https://www.compras.rs.gov.br/editais/0028_2024/318164
- SELT/DAER Ponte Santa Barbara: https://transportes.rs.gov.br/obras-da-ponte-santa-barbara-avancam-na-ers-431
- SGB/SACE: https://www.sgb.gov.br/sace/
- Zenodo cheias RH Guaiba 2024: https://zenodo.org/records/13227745
- Copernicus DEM: https://registry.opendata.aws/copernicus-dem/

Limitacao tecnica:

Estas camadas sao prova de conceito. A camada `NA 97,65` ainda depende da
compatibilizacao entre datum da ponte, datum do DEM e zero da regua da estacao
86472600 para uso operacional.
