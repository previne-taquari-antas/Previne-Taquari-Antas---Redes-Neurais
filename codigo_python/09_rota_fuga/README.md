# Rotas de fuga / evacuação — Etapa 2 (roteamento por ruas)

Roteamento **real por ruas** (OpenStreetMap + caminho mínimo Dijkstra) de cada
casa até o ponto de encontro/abrigo mais próximo, **evitando a área que alaga**.
Cobre **Santa Tereza** e **Muçum** com um gerador único.

## Ordem de execução

```bash
# 1. Cota de alagamento por pixel (uma vez por MDT; ~1 min por cidade)
python codigo_python/09_rota_fuga/gerar_cota_alaga.py

# 2. Rotas (por cidade e fonte de nível)
python codigo_python/09_rota_fuga/gerar_rota_fuga_ruas.py --cidade mucum --fonte cenario
python codigo_python/09_rota_fuga/gerar_rota_fuga_ruas.py --cidade mucum --fonte live
python codigo_python/09_rota_fuga/gerar_rota_fuga_ruas.py --cidade santa_tereza --fonte cenario
python codigo_python/09_rota_fuga/gerar_rota_fuga_ruas.py --cidade santa_tereza --fonte live

# 3. Camadas derivadas (leem o JSON do cenário)
python codigo_python/09_rota_fuga/gerar_painel.py --cidade mucum
python codigo_python/09_rota_fuga/gerar_estudo_caso_slides.py
python codigo_python/09_rota_fuga/gerar_fila_cidade.py          # depois dos slides (lê fila_evacuacao_mucum.json)

# Só o template do painel mudou? Os JSON de rota e os insumos OSM/MDT não
# ficam no git; isto relê os dados do painel publicado e grava com o template atual
python codigo_python/09_rota_fuga/gerar_painel.py --cidade mucum --republicar
python codigo_python/09_rota_fuga/gerar_painel.py --cidade santa_tereza --republicar
```

`gerar_mapa_margem.py`, `gerar_mapa_impacto.py`, `gerar_estudo_caso_mucum.py` e
`gerar_comparacao_osm_ibge.py`, citados em versões anteriores deste README,
não estão no repositório.

Testes (sem OSM nem LiDAR): `python tests/test_rota_fuga_ao_vivo.py` e
`python tests/test_rota_fuga_painel.py` (workflow `testar-rota-fuga.yml`).

`--fonte`: `live` (pico entre atual/2h/4h da RNA, lido por `nivel_ao_vivo.py`:
hora sem fuso é de Brasília, nível atual ausente não gera rota e o previsto é o
último campo de cada passo; telemetria com mais de 3 h
é marcada como desatualizada no JSON e no mapa), `cenario` (cota oficial de
inundação: régua 18 m em Muçum, 15 m em Santa Tereza), `fixo` (`--nivel` em
HAND). `--tempo-max` (padrão 30 min): limite de caminhada do idoso.

Saídas: `assets/data/rota_fuga/rota_fuga_ruas_<cidade>*.json` +
`<cidade>_rota_fuga_ruas*.html` (toque numa casa → a rota dela).

## Método

### Área que alaga
`gerar_cota_alaga.py` grava `cota_alaga_<cidade>.tif`: para cada pixel do
mosaico 2 m, o menor nível HAND (0 a 25 m, passo 0,1 m) em que ele alaga
**ligado ao rio** — o mesmo critério de `contornos_mancha.json`, que para em
15 m (abaixo do recorde de 2024 em Santa Tereza, HAND ~21,8 m). Nas casas,
o raster concorda com os contornos (a 13 m, 77 casas em comum; os contornos
suavizados pegam algumas a mais).

Cada trecho de rua guarda o perfil desse raster a cada 4 m. No nível L, a
**fração** do trecho abaixo de L entra no custo: `tempo × (1 + 60 × fração)`.
Ponte e túnel não usam o perfil (o rio embaixo não alaga o tabuleiro): alagam
quando uma cabeceira alaga. Abrigo que alaga no nível sai do roteamento.

O mapa mostra os contornos do site até 15 m; acima disso, o próprio raster.

### Origem casa a casa
A origem é cada edificação do OpenStreetMap (`osm_casas_<cidade>.json`),
ligada pela perpendicular à via mais próxima (até 80 m). A rede inclui
calçadões, caminhos e escadarias, baixada num recorte 0,015° maior que o das
casas (`osm_vias_pe_ampla_<cidade>.json`). A cota de alagamento da casa é a
menor entre os vértices e o ponto interno da edificação.

Não entram como casa: tags não residenciais (indústria, galpão, comércio,
escola, igreja, estação…) e polígonos com menos de 20 m² ou mais de 1000 m²
(Curtume CBR, hospital e pavilhões em Muçum; aviários em Santa Tereza). Ponte
e túnel não recebem ligação de casa.

Situação de cada casa no nível de projeto:

| Situação | Critério |
|---|---|
| `ok` | rota até o abrigo dentro do tempo, ou casa seca com rota seca |
| `excede` | casa na água e rota acima de `--tempo-max` |
| `ilhada` | casa seca, mas a rota cruza área que alaga (qualquer trecho: 40 cm de água já derrubam um idoso) |
| `sem_rota` | sem via a 80 m, ou ligada a um trecho de rede sem caminho até abrigo oficial |

Trechos de rede desconectados da rede principal (50+ nós) ficam no grafo se
alguma casa depende deles — é o caso da outra margem em Santa Tereza (614
nós, 48 casas). Abrigos sempre se ligam à rede principal.

### Tempo de caminhada com declive
r.walk do GRASS (Naismith + Langmuir) com a cota do MDT 2 m em cada nó,
escalado para um **idoso a 0,9 m/s no plano**. Descida limitada a 1,1 m/s,
rampa a ±35 %, escadaria ×1,5; pontes interpolam a cota entre as cabeceiras.
Grafo direcionado: subir e descer a mesma rua têm tempos diferentes.

### Rotas por nível
Além do nível de projeto, o JSON traz em `niveis` as rotas recalculadas de
HAND 0 a 25 m (passo 1 m): próximo nó, abrigo e tempo por nó; nó, tempo e
água por casa. O painel usa o nível do slider (arredondado para cima).

### Pontos de encontro candidatos
Três tipos de casa pedem outro ponto de encontro: na água e acima de
`--tempo-max` (`tempo`), ligada a um trecho de rede sem caminho até abrigo
oficial (`sem_rota`) e ilhada. O local candidato é um nó que só alaga **2 m
acima** do nível de projeto, em rampa de até **15 %**.

A escolha é por **cobertura gulosa**: um local atende a casa se ela chega lá
em até `--tempo-max` (idoso) e se ele ganha do abrigo oficial no custo com
penalidade de água (senão o roteamento continuaria mandando a casa ao
oficial); para a ilhada, sem cruzar água. A cada passo entra
o local que atende mais casas na água ou sem rota (mínimo 3); depois, os que
atendem mais ilhadas (mínimo 5); até 8 locais.

O JSON traz por candidato os motivos, o pior tempo antes/depois, a cota em
que ele alaga, a rampa e a **demanda**, além da rota até ele (`rota_cand`) e,
por casa, `cand`, `tempo_cand_s` e `no_cand`. **Capacidade não é avaliada** —
são sugestões para a Defesa Civil, não abrigos oficiais.

### Locais altos sugeridos — Santa Tereza (`locais_altos.py`)
**Terreno alto = o que ficou fora da mancha da maior cheia registrada, visto no
MDT.** Em Santa Tereza a maior cheia é set/2023: régua 23,65 m na telemetria
(24,04 m nivelada pelo SGB); mai/2024 ficou em 22,42 m (SGB) e nov/2023 em
21,61 m. A validação de campo do HAND (05/09/2026, marcas de cheia e limites com
GNSS RTK; trabalho do SBSR 2027, `pesquisas/validacao-campo-hand-santa-tereza/`)
calibra o zero 1,60 m nesses pontos, o que põe set/2023 em **HAND 22,05 m**: a
mancha é o contorno HAND de 22,1 m (`contornos_mancha.json`), a linha tracejada
do painel.

No MDT (LiDAR de 10 m, o mesmo do HAND), dentro do recorte das ruas (± ~400 m),
com a mancha rasterizada **pelo centro do pixel** (5 subpixels por pixel: o PIL
pinta também o contorno do polígono, o que inflava a mancha em ~2% e a água na
borda em ~0,8 m):
1. **água na borda**: mediana, num raio de 300 m, do meio entre o pixel de
   dentro e os de fora da borda externa da mancha, levada a cada pixel pela
   borda mais próxima (o pixel de dentro sozinho fica ~1 m abaixo da água em
   barranco). Nas ruas, a mediana é 75,8 m (p10 72,7; p90 76,4), dentro da água
   medida com RTK em 2023 (74,1–76,5 m). As ilhas da mancha ficam fora da conta
   (a borda delas fica no leito);
2. **nível da água** = o maior entre a borda e a maior água medida em campo
   (76,47 m, limite H004). Na cidade a água de 2023 ficou plana e, em três
   limites, 1,4 a 1,8 m acima da borda do HAND; sozinha, a borda cai para
   72–73 m no sul;
3. fora da mancha, cada pixel é **alto** (terreno pelo menos **2 m** acima do
   nível da água), **sem folga** (menos de 2 m) ou **abaixo da água** (abaixo da
   água na borda sem estar na mancha: atrás de aterro ou barreira no modelo,
   pode ter alagado). "Sem folga" pode ficar abaixo de 76,47 m (a legenda diz
   isso). Nó de rua ou casa que o HAND alaga no nível da mancha (22,1 m) fica
   dentro dela mesmo que o pixel de 10 m na borda caia fora; e só é **alto** se
   o HAND também tiver a folga (≥ 24,05 m): MDT e HAND discordam em ±1–2 m, e 8
   casas com HAND de 23,2 a 24,1 m liam "não precisa sair".

A folga de 2 m cobre o erro do terreno de 10 m: LiDAR 10 m − RTK nos 19 vértices
tem NMAD 0,71 m e máximo +1,46 m (H003, um limite de set/2023: a água chegou lá e
o LiDAR o põe 1,23 m acima do nível de 76,47 m; com folga de 1 m ele seria
"alto"). As métricas do artigo (MAE 0,64 m, erro perigoso máximo 1,84 m em H004)
são do HAND **krigado** de 1 m; o painel usa o HAND D8 de 5 m dos contornos, que
nos 19 vértices RTK válidos tem viés +0,69 m, MAE 1,02 m e erro perigoso máximo
de **1,25 m** (H007: o HAND põe a água 1,25 m abaixo da medida; V001, com o RTK a
conferir, dá 1,75 m). `meta.cheia` guarda as duas (`hand_krigado_artigo`,
`hand_painel`).

**Ilhas**: `ilha_m` é o nível (HAND) em que um ponto perde a última ligação seca
com as saídas da cidade: pontas de rua em terreno alto na borda da rede e pontas
de via principal do OSM (primary/secondary/tertiary) que seguem para fora dela —
a rede corta a **Estrada do Vinho** a 600 m da borda, e sem ela o ponto na
própria estrada "virava ilha". Os pontos 1 e 8 (centro: ESF, igreja, escolas)
viram ilha com o rio em 18,4 m; 7 em 19,2 m; 4 em 11,5 m; 5, na outra margem, não
tem rua mapeada até o resto da cidade; 2, 3, 6 e 9 não viram. 86 casas no alto
ficam ilhadas antes de uma cheia como a de 2023: o cartão pede água, comida e
remédios e dá o nível para quem depende de remédio, oxigênio ou diálise sair,
descontada a caminhada até passar o gargalo (`ilha_tempo_s`, mediana ~8 min); em
Quem sai elas contam como "ilhada (precisa de apoio)". Quando o ponto mais perto
vira ilha, o cartão sugere um que não vira, se custar no máximo 15 min a mais
(até 30 min no total), com o traçado (roxo tracejado) e o nível de saída dele.

**Quando sair**: o cartão mostra o nível da régua para sair, não o nível em que a
água corta o caminho: `corte − 1,5 m de erro do modelo − (preparo + caminhada) ×
subida`, com o preparo e a subida dos seletores do painel (padrão 30 min e
90 cm/h) e, à parte, os níveis para 1 h (noite) e 2 h (acamado ou cadeirante).
Os 1,5 m cobrem o erro perigoso máximo do HAND do painel (1,25 m), não só o MAE.
Margem e Quem sai descontam a mesma margem (antes, no nível em que o cartão
mandava sair, a casa aparecia "confortável"). O corte inclui o **acesso da casa
até a rua** (`acesso_cota`: o menor contorno que cobre o caminho da casa ao pé da
perpendicular e dali ao nó, em `gerar_painel.cota_acesso`); antes ele ficava de
fora e 43 casas recebiam o nível até 2,7 m alto. Casa fora da mancha mas abaixo
da maior água medida conta com água no nível da mancha (22,1 m), mesmo que o HAND
diga mais. Com a leitura do rio recente (até 1 h), o cartão diz **agora** só
enquanto o caminho ainda está seco; com o rio acima do corte ou da casa, manda
não entrar na água, subir e ligar 193/199.

Cada casa que não fica no alto vai pelo caminho mais rápido (idoso, com subidas
no LiDAR; `caminhada.py`) entre os que continuam secos **pelo menos até a água
chegar na casa** (cota HAND de cada trecho); quando nenhum continua, pelo que
fica seco até o nível mais alto possível, e a casa precisa sair antes dele
(`corte_m`). Casa sem caminho até o abrigo oficial (outra margem; o gerador grava
`no = -1`) parte do nó mais perto do pé da perpendicular; sem ponto possível ao
alcance, vai ao terreno alto mais perto. Os **pontos altos** são nós de rua em
terreno alto com 1 m a mais (3 m acima da água) também no pixel mais baixo do
entorno de 3×3 (30 m: a grade de 10 m é o vizinho mais próximo do LiDAR de 1 m e
erra ±1–2 m em declive) e a mais de 100 m das cicatrizes de deslizamento do
inventário de 2024 (`assets/data/landslides_poly.geojson`; o antigo ponto 5
ficava a 2 m de uma), escolhidos um a um pelo que mais poupa caminhada
(casa·min, teto de 60 min) até o ganho cair abaixo de 150 casa·min ou chegar a
10. O popup avisa encosta ou barranco de 30° ou mais a menos de 100 m (pontos 1,
2, 4 e 7), e o cartão, trecho com mais de 8,33% em 40 m (limite da NBR 9050 para
cadeira de rodas; 229 de 366 rotas). Nome: rua com nome a até 25 m e lugares a até
150 m (`osm_nomes_santa_tereza.json`, de `baixar_nomes_osm.py`; escolas e UBS de
`assets/data/servicos`), cada lugar com a situação em 2023 (a EMEI Descobrindo
Caminhos, perto do ponto 1, alagou). O OSM de Santa Tereza tem poucos nomes de
rua.

Resultado (out/2026, terceira revisão): no recorte, 2.237 ha de terreno alto,
43 ha sem folga e 5 ha abaixo da água fora da mancha. 759 de 1385 nós de rua
ficam no alto; das 565 casas, 196 já estão no alto, 366 têm caminho até terreno
alto (362 até um dos **9 pontos altos**) e 3 não têm via mapeada. Caminhada do
idoso: mediana 6,5 min, p90 16,2 min, máximo 33,5 min; em 178 casas a água corta
o caminho antes de chegar na casa. O Ginásio (HAND 21,3 m, terreno 75,0 m) fica dentro da água de set/2023. O
ponto 8 fica junto à ESF Santa Tereza, a 83 m do campanário da igreja.

No painel (`gerar_painel.py`, `CFG["santa_tereza"]["locais_altos"]`): na aba
Rotas, o terreno em três cores (imagem do recorte), a linha tracejada da mancha,
triângulos numerados e, ao tocar numa casa, o caminho roxo e um cartão em ordem
de decisão (**Sua casa · Para onde ir · Quando sair · Evite**); o abrigo oficial e
os números técnicos ficam em "detalhes". Em Margem e Quem sai, vale a melhor
saída entre o abrigo oficial e o ponto alto (casa ou rua no alto = segura).
Célula IBGE sem casa mapeada fica "sem avaliação", fora da contagem de risco, a
não ser que o centro alague ou que a célula seja inteira alta (dentro do recorte,
todo pixel alto; fora, fora da mancha HAND de 24,1 m com todo o LiDAR acima de
78,47 m). Na cheia de set/2023, "precisam sair ou de apoio" fica em 468 pessoas
(antes: 971, com ~610 moradores rurais contados pelo acesso ao Ginásio; depois
366, sem os ilhados no alto). Na aba Rotas, com os pontos altos, o mapa mostra a
cheia de referência (tracejado) e não mais a mancha azul do cenário de 15 m, que
não tinha legenda à vista. Enquanto
`contornos_mancha.json` não trouxer `river_reference_method =
eixo_dominante_taquari_D8` (auditoria do Marrecão), o painel mostra o aviso de
estudo em validação (`meta.aviso_estudo`). Os locais candidatos do gerador
(calculados para a régua 15 m; 1 de 5 alagava em set/2023 e outros 2 ficavam
dentro da folga) saem do painel de Santa Tereza. **São sugestões técnicas**:
espaço, acesso, capacidade e uso dependem da Defesa Civil.

`santa_tereza_rotas_altas_set2023.html` (rotas no pico de 2023 até qualquer
trecho alto) usa os mesmos dados: `--republicar` grava
`assets/data/rota_fuga/santa_tereza_rotas_altas_set2023.json`
(`locais_altos.pagina_rotas_altas`), com os nós altos, a mancha e o terreno do
painel. Antes, a página usava "HAND acima de 24,05 m" e tratava trecho sem cota
como desconhecido, deixando de fora justamente os pontos mais altos.

A **simulação da cheia** (`santa_tereza_painel_evacuacao.html`) lê o mesmo JSON
(com a altitude LiDAR dos nós, `z_nos`, e `margem_corte_m`) e, ao tocar perto de
uma rua, traça a **rota de fuga até o terreno alto pelo MDT**, não mais até o
Ginásio (que fica dentro da água de set/2023 e virou só referência): entre os
caminhos que ficam secos por mais tempo (até o ponto alagar ou o melhor caminho até
algum nó alto ser cortado, o `gargalo`), o ponto alto (▲) mais perto no passo do
idoso subindo e descendo; sem ▲ ao alcance, o nó alto mais perto. É a mesma conta
de `locais_altos.caminhos` e bate com `margem_nos` do painel casa a casa em todos os
nós com ▲ ao alcance (teste em node). O nível simulado só diz se o caminho ainda
está seco; "saia até" desconta `margem_corte_m` (1,5 m) e o que o rio sobe na
caminhada. Ponto que vira ilha antes de set/2023 mostra, tracejada, a alternativa
que não vira (até 15 min a mais e 30 no total). A aba "Tempo para sair" usa a
mesma rota.

```
python codigo_python/09_rota_fuga/locais_altos.py          # resumo do painel publicado, sem gravar
python codigo_python/09_rota_fuga/gerar_painel.py --cidade santa_tereza --republicar
python codigo_python/09_rota_fuga/baixar_nomes_osm.py santa_tereza   # precisa de internet
```

### Pontos de encontro pelo mapa único — versão 1 (`pontos_encontro.py`)
Critério da equipe (out/2026), provisório até o perigo hidrológico do projeto ficar pronto:
área insegura = mancha do **Mapa Único do Plano Rio Grande** (MUP RS, Área Diretamente
Atingida das cheias de abril e maio de 2024, SPGG/DEE); área segura = fora dela, a mais de
**100 m**; ponto de encontro = **trecho de via** do OpenStreetMap (a rede dos painéis casa a
casa) inteiro fora dessa faixa, para não sugerir lugar no meio do mato. As "áreas edificadas"
da SEMA não entram. Santa Tereza e Muçum.

Os pontos são escolhidos como os locais altos: um a um, o que mais poupa caminhada do idoso
(casa·min, teto de 60 min), até 10 pontos ou ganho abaixo de 150 casa·min; caminhada do
r.walk, com subida do LiDAR em Santa Tereza e no plano em Muçum (sem grade). Casas na mancha
ou na faixa vão ao ponto mais perto pelas ruas; casa fora da faixa não precisa ir.

A mancha entra por `preparar_mancha.py` (shapefile, GeoPackage, KML ou GeoJSON em qualquer
sistema de coordenadas → GeoJSON WGS84 recortado por cidade em
`assets/data/rota_fuga/mup_rs_ada_<cidade>.geojson`); a página é `pontos_encontro.html?cidade=`.

```
pip install pyogrio pyproj      # só para converter a mancha
python codigo_python/09_rota_fuga/preparar_mancha.py <arquivo do MUP RS>
python codigo_python/09_rota_fuga/pontos_encontro.py santa_tereza --gravar
python codigo_python/09_rota_fuga/pontos_encontro.py mucum --gravar
```

A mancha publicada vem da FEPAM: "área diretamente atingida 2024"
(`area_diretamente_atingida_2024.shp`, 482 polígonos por município, SIRGAS 2000, versão de
03/09/2024; zip `03100958-area-dietamente-atingida-2024.zip`, sha256 `f8934c43…`). O site do
estado não responde fora do Brasil; o workflow manual `.github/workflows/mancha-mup-rs.yml`
(`baixar_mancha_mup.py`, com cópia do Internet Archive como reserva) baixa, recorta e recalcula.

Resultado (out/2026), 100 m de afastamento:

| | casas | na mancha | na faixa | fora | pontos | caminhada até o ponto (mediana · p90 · máx.) |
|---|---|---|---|---|---|---|
| Santa Tereza | 565 | 372 | 144 | 45 | 6 | 15,0 · 22,2 · 38,0 min |
| Muçum | 1.937 | 1.690 | 99 | 147 | 6 | 24,5 · 36,1 · 56,7 min |

Em Muçum a mancha cobre quase toda a área urbana (o polígono do município inclui as áreas
autodeclaradas pela Defesa Civil), então os pontos ficam na borda, a até 1,8 km do centro;
quatro dos seis locais do Plano de Contingência ficam dentro dela (Hospital, Igreja Matriz,
Salão José Marcolin e CTG) e o Posto Sander fica fora, a 164 m. O Ginásio de Santa Tereza fica
fora da mancha de 2024, a 11 m da borda. É o motivo de trocar o mapa único pelo perigo
hidrológico do projeto na próxima versão.

**Versão com o modelo do projeto** (`--versao hand`, página `&mancha=hand`): enquanto o perigo
hidrológico não chega, a área insegura é a mancha do modelo HAND do projeto na maior cheia
registrada, a mesma dos painéis (`mancha_hand.py`, que lê `contornos_mancha.json` e grava
`hand_maior_cheia_<cidade>.geojson`): Santa Tereza set/2023, régua 23,65 m → HAND 22,1 m (LiDAR,
contornos em revisão no Marrecão); Muçum mai/2024, régua 25,51 m → HAND 20,6 m (mosaico 2 m,
régua 5 m = HAND 0). Mesmo afastamento de 100 m e mesma escolha de pontos.

| modelo HAND | casas | na mancha | na faixa | fora | pontos | caminhada até o ponto (mediana · máx.) |
|---|---|---|---|---|---|---|
| Santa Tereza (set/2023) | 565 | 264 | 264 | 34 | 5 | 14,1 · 43,8 min |
| Muçum (mai/2024) | 1.937 | 1.221 | 403 | 312 | 9 | 9,3 · 41,5 min |

Em Muçum o modelo deixa fora da mancha a parte alta do centro, que o mapa único inclui: a
caminhada mediana até o ponto cai de 24,5 min (mapa único) para 9,3 min. A página alterna as
duas manchas.

Para trocar pelo perigo hidrológico do projeto: `preparar_mancha.py <arquivo> --saida-prefixo
perigo_hidrologico` e `pontos_encontro.py <cidade> --mancha <geojson> --fonte "<descrição>"`.

### Demanda por destino
Cada casa recebe `pessoas`: a população da grade IBGE 2022 (domicílios
ocupados) dividida entre as casas OSM da célula. Casa fora das células com
moradores fica `null` (não residencial ou posterior ao Censo — 214 em Muçum,
65 em Santa Tereza) e conta 0. Por abrigo e candidato, `demanda` soma as
casas na água que vão até ele e, nos candidatos, as ilhadas e sem rota.

### Cenários oficiais (outubro/2026)

| | Muçum 18 m | Santa Tereza 15 m |
|---|---|---|
| Casas (OSM) | 1937 | 565 |
| HAND do cenário | 13,0 m | 13,4 m |
| Na área que alaga | 115 | 18 |
| Na água acima de 30 min | 47 → **0** | 14 → **0** |
| Sem caminho até abrigo oficial (outra margem) | 0 | 46 → **0** |
| Casas secas ilhadas | 194 → **62** | 425 → **27** |
| Locais candidatos | 4 | 5 |

(antes → com candidatos; ilhada = a rota até o abrigo oficial cruza qualquer
trecho que alaga. As que restam não têm caminho seco até nenhum local alto
fora da água: abrigar-se no próprio local ou sair antes.)

Santa Tereza usa o HAND LiDAR do `main` (`contornos_mancha.json`, 0–25 m) com
a calibração de campo régua 1,60 m = HAND 0; a cota de alagamento é
rasterizada desses contornos (`gerar_cota_alaga.py`, `cota_de_contornos`). O
Ginásio (único abrigo) só alaga em HAND 21,3 m (régua 22,9 m), mas a via até
ele alaga a partir de HAND 13,0 m perto de (−29,1726, −51,7237): ~35 m de
rua com ~40 cm de água no cenário deixam 361 casas ilhadas, todas atendidas
por um candidato do lado seco. A outra margem é ligada ao centro só por uma
lacuna de ~190 m perto de (−29,1794, −51,7344) que cruza o canal do rio
(ponte ou balsa), não rua faltando; o candidato de lá atende as 46 casas.

Muçum: o Salão José Marcolin alaga a partir de HAND 18 m (régua 23 m) e o
CTG Sentinela a partir de 20,6 m.

## Camadas derivadas
- `gerar_painel.py` — **painel casa a casa** (`<cidade>_painel_casas.html`) com abas
  Rotas · Margem · Quem sai; em Quem sai cada casa é um ponto colorido pela situação.
  Em Santa Tereza, com os locais altos (`locais_altos.py`).
  Não substitui o `<cidade>_painel_evacuacao.html` (grade IBGE, robô de 30 m).
- `gerar_estudo_caso_slides.py` — vídeo/slides de Muçum, recalculando as rotas por nível.
- `gerar_fila_cidade.py` — fila por célula IBGE (`fila_cidade_<cidade>.json`):
  cota da casa mais baixa da célula e p90 do tempo a pé.

Todas leem o JSON do **cenário oficial** de cada cidade.

**Margem de fuga** (painel): quanto tempo a pessoa ainda pode esperar para
sair. É o mínimo, ao longo da rota até o abrigo no nível do slider, de
`tempo até a água chegar no ponto − tempo do idoso para chegar nele − tempo de
preparo` (seletor 0/30/60/120 min; padrão 30). Se a rota já cruza água no nível,
a casa é "ilhada". A subida padrão é **90 cm/h**, a média de set/2023 e de
22/07/2026 (o antigo 40 cm/h dava margem 2 a 5 vezes maior); o slider vai a
2 m/h, ritmo dos trechos mais rápidos de set/2023. A margem supõe que o rio
continua subindo nesse ritmo a partir do nível escolhido.

**Cheias registradas** (`CFG[...]["cheias_ref"]` em `gerar_painel.py`): botões
que levam o slider à cota oficial e aos picos das réguas (Santa Tereza: jul/2026
17,46 m, nov/2023 21,61 m, mai/2024 22,42 m nivelada pelo SGB — a telemetria
parou em 22,32 m —, set/2023 23,65 m, a maior; os 25,82 m de "referência" para
mai/2024 que estavam aqui não tinham fonte primária;
Muçum: jul/2020 22,11 m, nov/2023 22,99 m, mai/2024 25,51 m — set/2023 fica de
fora porque a série termina subindo em 21,18 m). Cada abrigo e candidato diz até
onde fica seco e se alagaria em cada cheia; a aba Rotas avisa o que alagaria na
maior delas. Em Muçum, o popup traz a capacidade planejada do Plano de
Contingência de jul/2026 (`mucum_contingencia_202607.json`; faixa quando o plano
diverge) e avisa quando a demanda do cenário passa dela.

**Quem sai**: a população de cada célula IBGE é dividida entre as casas OSM
dentro dela, cada casa com sua situação; célula sem casa mapeada usa o nó de
via mais próximo do centroide. **Isolada** = tinha rota até abrigo seco com o
rio baixo e perdeu pela água (conta como risco: antes essas casas sumiam da
contagem quando o abrigo alagava); **sem rota** = nunca teve via mapeada até
um abrigo (não conta). Em Santa Tereza, o caminho até o local alto também é
saída (vale a melhor das duas; ver Locais altos).

O slider mostra o nível em **régua** (HAND entre parênteses). A paleta separa
urgente (escuro) de folgado (claro); o par de classes mais próximo fica a
distância de cor ≥ 17 (Lab) também em deuteranopia, protanopia e tritanopia
(simulação de Machado et al. 2009).

**Toque e leitura do rio** (painel): com o mapa longe (zoom < 17 no toque, < 16
no mouse), o primeiro toque só aproxima — 1 px passava de 8 m e o dedo pegava a
casa do vizinho; o cartão lembra de conferir o círculo verde. "Usar minha
localização" escolhe a casa só com GPS de até 60 m. No teclado, o painel vem
antes do mapa, as abas seguem o padrão WAI-ARIA (setas) e Enter no mapa escolhe a
casa sob a mira do centro. "Rio agora" usa `assets/js/live_feed.js` (Raw,
jsDelivr e API do GitHub), relê a cada 5 min e ao voltar à página, mostra há
quanto tempo é a leitura (com a data se não for de hoje), recusa hora no futuro e
avisa quando a busca falha; o cartão aberto é refeito quando a leitura muda.
Nomes do OSM e de cadastros entram escapados no HTML, e o JSON embutido não tem
"</" (um nome com `</script>` fecharia o script). No Pages, o CSS dos logos
(`institutional_logos.css`) punha o painel com 100% da altura: no celular a
folha cobria o mapa; o template vence essa regra.

**Abertura e celular** (painel): Santa Tereza abre na aba Rotas, com o cartão
da casa clicada no alto (sua casa, para onde ir, quando sair, evite) e as
outras camadas recolhidas em "Mais camadas"; os contornos HAND só são baixados
na primeira vez que se abre Quem sai. Muçum continua abrindo em Quem sai. Até
700 px o painel vira folha inferior, começa recolhido ("Ver instruções ▲") e
abre no cartão quando se toca numa casa; o zoom fica no canto superior direito.
Se o Leaflet não carregar (unpkg, com reserva no jsDelivr), aparece um aviso e
fica a "Lista dos pontos altos", que é sempre gerada em texto. "Rio agora" lê
`previsao_ao_vivo*.json` do main pelo raw.githubusercontent (o Pages não
publica esse JSON); leitura com mais de 3 h aparece como atrasada e não entra
no "quando sair", que diz "agora" quando o rio já passou da régua de saída.
Os painéis por grade (`*_painel_evacuacao.html`) também abrem em 90 cm/h.

## Cobertura OSM × IBGE
Contagem, por célula da grade estatística, das edificações OSM usadas como casa
comparadas com os domicílios (`dom`). O script que a fez
(`gerar_comparacao_osm_ibge.py`) não está no repositório.

| | Muçum | Santa Tereza |
|---|---|---|
| Domicílios IBGE no município | 1782 | 630 |
| Dentro do recorte das casas | 1441 | 267 |
| Edificações OSM nesse recorte / domicílios | 1,19 | 1,85 |
| Fora ou parcialmente fora do recorte | 341 | 363 |
| … em células que tocam a mancha | 112 | 73 |
| … ponderando pela área alagada da célula | ~32 | ~19 |

Dentro do recorte, nenhuma célula com 5+ domicílios tem menos da metade das
edificações esperadas. Em Muçum, o excesso de edificações bate com galpões e
anexos (menos de 30 m² ou mais de 300 m²); em Santa Tereza, não — quase tudo é
só `building=yes` e o filtro residencial não separa nada. Fora do recorte
ficam domicílios ribeirinhos e rurais que o modelo ainda não enxerga.

## Pendências conhecidas
- **Locais altos de Santa Tereza**: vistoriar os 9 pontos com a Defesa Civil
  (espaço, acesso, muro, escada, encosta) e decidir quais viram pontos de
  encontro; o Ginásio fica dentro da água de set/2023. A grade de 10 m deveria
  ser o mínimo (ou p10) do LiDAR de 1 m, não o vizinho mais próximo (precisa dos
  rasters originais). Faltam a lista imprimível por ponto e por nível da régua
  para a Defesa Civil e o "quando sair" em Muçum. Mai/2024 (SGB) entra no painel
  com o zero da telemetria (1,60 m), o que é conservador (o zero do SGB é ~2,0 m).
  `contornos_mancha.json` (45 MB) sai inteiro na primeira ida a Quem sai: falta
  um arquivo por nível. O bloco `risco_em_cheia_referencia`
  do Ginásio em `abrigos.geojson` ainda usa os 25,82 m e o zero antigo (4 m).
- **Mancha de Santa Tereza**: refazer `contornos_mancha.json` com o eixo dominante
  do Taquari (precisa dos rasters LiDAR originais) e rodar `--republicar`; o aviso
  de estudo some sozinho.
- **Rotas × água plana**: o corte das rotas usa o HAND por trecho; com a água
  plana medida em campo, ~41 rotas cortariam antes da casa (revisão de out/2026).
  Falta uma cota de alagamento pelo plano para nós e trechos na área dos pontos
  RTK. Faltam também cenários acima de 2023 (+1 e +2 m) e marcas de cheia no norte,
  no sul e a montante no vale do afluente.
- **Referência do HAND**: o talvegue do mosaico tem poços e degraus; trocar
  pela linha central do rio e um perfil de linha d'água suavizado muda muito a
  contagem de casas atingidas. Exige refazer `02_mdt_hand_mancha`.
- **Zero da régua**: ±1 m no zero leva as casas na água de Muçum de 62 a 330.
  Calibrar com as manchas e marcas das cheias de 2023/2024.
- Capacidade: Muçum já compara demanda × capacidade planejada no painel; faltam
  Santa Tereza (sem plano no repositório) e os candidatos. Os 5 alojamentos do
  Plano de Muçum de jul/2026 que não estão em `abrigos.geojson` (Centro Pastoral,
  EMEF Jardim Cidade Alta, EMEI Pingo de Gente, Estação Ferroviária, Brás
  Charléo) dependem de conferir o PDF do plano.
- A fila (`fila_cidade_*.json` + `assets/previsao_fila.js`) ainda não está nas
  páginas de previsão ao vivo: primeiro validar o painel de evacuação. Ao
  ligar, `gerar_pagina_previsao_mucum.py` (que copia a página de Santa Tereza)
  precisa trocar também o bloco da fila para Muçum (JSON, replayKey, links).

## Abrigos / pontos de encontro
`assets/data/servicos/abrigos.geojson` (filtrado por `municipio`):
- **Santa Tereza**: Ginásio de Esportes (geocodificado do link da Defesa Civil).
- **Muçum**: 6 pontos de encontro oficiais do **Plano de Contingência de Muçum 2025**
  (seção 8.3): Hospital NSa Aparecida, Igreja Matriz da Purificação, Salão Cidade
  Alta, Salão José Marcolin, Posto Sander, CTG Sentinela — com coordenadas oficiais,
  iguais às do plano de jul/2026 (`mucum_contingencia_202607.json`). Até out/2026
  eles não estavam no arquivo e `--cidade mucum` abortava com "Nenhum abrigo".

## Calibração régua ↔ HAND — Muçum

O `zero_regua_m` de Muçum é **5,0 m** (500 cm na régua **86510000**): o mesmo
bankfull operacional já usado na mancha (`gerar_mancha_mucum.py`), na RNA ao
vivo (`gerar_previsao_ao_vivo_mucum.py`) e em `mucum_inundacao.html`. Coincide
com a **cota de atenção** do Plano de Contingência.

Conversão: `HAND = régua_m − 5`.

| Alarme oficial (régua) | HAND |
|---|---|
| Atenção **5 m** | 0 m (sai da calha) |
| Alerta **10 m** | 5 m |
| Inundação **18 m** | 13 m |

O cenário (`--fonte cenario`) ancora na cota de **inundação 18 m**. O ao vivo
(`--fonte live`) lê `previsao_ao_vivo_mucum.json`; rio abaixo de 5 m → sem mancha.

Valor **operacional**, não o RN nivelado do SGB/ANA. Definitivo: amarrar a cota
oficial do zero da régua ao mesmo datum do mosaico 2 m
(`codigo_python/04_zero_regua/consulta_estacao_ana.py 86510000`).

Santa Tereza usa a calibração de campo **régua 1,60 m = HAND 0** no rio
principal (régua_m − 1,6 = HAND), válida só sobre o HAND LiDAR de
`gerar_hand_lidar_santa_tereza.py`. O cenário usa a inundação oficial de 15 m
(HAND 13,4 m). Antes: bankfull 4 m sobre o mosaico 2 m (HAND 11 m).

## Fontes
- Plano de Contingência do Município de Muçum 2025 (Defesa Civil / Prefeitura) —
  abrigos, pontos de encontro, cotas oficiais, rotas de fuga oficiais (seção 8.4).
- Franco, G. G. — notebook de roteamento de evacuação, Zenodo,
  [doi:10.5281/zenodo.20402230](https://doi.org/10.5281/zenodo.20402230) (CC-BY 4.0):
  origem casa a casa ligada à rua por perpendicular, tempo de caminhada pelo
  r.walk e ponto de encontro calculado a partir das casas, fora da mancha
  (aqui adaptado como candidatos por cobertura gulosa, ao lado dos abrigos oficiais).
- © OpenStreetMap contributors (ODbL) — vias e edificações; IBGE — grade estatística.
