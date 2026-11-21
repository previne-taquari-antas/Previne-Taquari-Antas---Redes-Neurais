# Validação da mancha gerada pelo terreno (cenario_municipal.html)

A página gera a mancha de inundação pelo relevo (HAND): baixa o relevo aberto (Terrain Tiles, base SRTM,
cerca de 30 m), acha os rios (do OpenStreetMap e da área que escoa) e marca tudo o que fica até "Rio sobe (m)"
acima do rio. Aqui ela é comparada com cheias reais.

## Como foi medido

- A mancha foi gerada **pela própria página publicada**, com a área de cada lugar importada e "Rio sobe" de
  2 a 28 m (`gera.js`).
- A comparação é **pelas casas** (`casas.py`): edificações do OpenStreetMap na zona, quais a cheia de verdade
  atingiu e quais a mancha marcou. O leito do rio não tem casas, então não pesa. Uma casa conta como atingida
  se estiver a até ~15 m da área atingida.
- "Pegou" = das casas atingidas, quantas a mancha marcou. "Acertou" = das casas que a mancha marcou, quantas
  foram atingidas. "Nota" = média harmônica das duas (F1).

## Referências

- **Mapa Único do Plano Rio Grande** (FEPAM): área diretamente atingida na cheia de maio de 2024. Santa Tereza
  e Muçum já estão em `assets/data/rota_fuga/`; as outras cidades foram recortadas por
  `.github/workflows/validacao-mancha-mup.yml` (`recorta_mup.py`) e estão aqui (`mup_*.geojson`).
- **Copernicus EMS** (satélite): EMSR720 (RS 2024), EMSR773 (Valência 2024), EMSR664 (Emília-Romanha 2023),
  EMSR696 (Derna 2023). Baixe os produtos em https://rapidmapping.emergency.copernicus.eu/ e descompacte em
  `z/<pasta de sites.json>`.

## Resultado (melhor nível de cada lugar)

Cheia de maio de 2024, vale do Taquari, contra o Mapa Único do RS. A página usa, desde esta validação, canal com
**10 km² ou mais** de área que drena para ele como rio (antes, 1 km²); a tabela compara os dois.

| Cidade | Casas atingidas / na zona | 10 km² (atual): rio sobe · pegou · acertou · nota | 1 km² (anterior): nota |
|---|---|---|---|
| Muçum | 3.593 / 5.507 | +24 m · 90% · 84% · 87 | 87 |
| Encantado | 3.976 / 9.443 | +20 m · 86% · 84% · 85 | 74 |
| Santa Tereza | 772 / 1.436 | +24 m · 98% · 73% · 84 | 83 |
| Arroio do Meio | 5.305 / 10.786 | +24 m · 90% · 77% · 83 | 72 |
| Roca Sales | 3.268 / 6.103 | +16 m · 80% · 84% · 82 | 78 |
| Colinas | 1.446 / 2.942 | +24 m · 77% · 82% · 80 | 74 |
| Cruzeiro do Sul | 5.913 / 13.246 | +16 m · 84% · 72% · 78 | 76 |
| Estrela | 5.604 / 15.273 | +16 m · 79% · 75% · 77 | 75 |
| Lajeado | 3.926 / 12.459 | +20 m · 67% · 76% · 71 | 74 |

Média da nota: 81 com 10 km², 77 com 1 km². Com 100 km² a página não acha drenagem em 7 das 9 cidades; quando
isso acontece com 10 km², ela tenta de novo com 1 km². Com 1 km², os arroios pequenos contam como rio e a mancha
marca os fundos de vale deles.

Na subida que melhor reproduziu 2024 em cada cidade (16 a 24 m), a mancha pegou de 67% a 98% das casas
atingidas (8 das 9 cidades acima de 77%), e das casas que ela marcou, de 72% a 84% foram mesmo atingidas.
Detalhe por nível em `resultado_casas_10km2.txt` e `resultado_casas_1km2.txt`.

Outros lugares, contra o satélite (Copernicus), medidos com o limite anterior de 1 km²:

- **Derna (Líbia, 2023, rompimento de barragem):** +12 m pegou 87% e acertou 87%.
- **Alfafar (Espanha, 2024):** +6 m pegou 76% e acertou 14%. Boa parte da água veio da chuva na planície.
- **Alzira (Espanha) e Forlì (Itália):** a inundação observada está espalhada na planície, longe do rio, e a
  mancha pelo relevo não a prevê (nota abaixo de 5).
- **Encantado, Roca Sales e Santa Tereza no satélite:** as imagens são de 4 e 5 de maio de 2024, depois do pico,
  e marcam pouquíssimas casas (5 de 737 em Santa Tereza). Não servem para julgar a mancha; por isso o Mapa
  Único é a referência no RS.

## Limites

- Uma referência boa existe só para o vale do Taquari; fora dele, só pelo satélite, que mostra uma cheia já
  baixando ou água de chuva.
- O "Rio sobe" que dá o melhor resultado varia de 16 a 24 m entre as cidades. Não foi conferido contra a régua de
  cada cidade em 2024.
- Relevo de 30 m de superfície (inclui parte de prédios e árvores).

## Como refazer

```
python3 prepara.py                 # zonas e referências em prep/
python3 agua.py                    # edificações do OpenStreetMap (osm/)
NODE_PATH=$(npm root -g) node gera.js   # manchas pela página (BASE= outra cópia; SO= lugares; DRAIN= km²; SAIDA= pasta)
python3 casas.py                   # comparação pelas casas
```
