# Teste final — abertura única dos eventos de teste (X20260918, X75, X76)

**Pesquisa. Nada aqui é alerta, previsão operacional ou orientação de evacuação.**

Branch `cursor/hec-bacia145-teste-final`, criada de `cursor/hec-bacia145-sistema` em `532369075`. Abertura autorizada
pela usuária em 10/10/2026. Depois desta rodada a janela X20260918 e os eventos X75/X76 deixam de ser teste
independente.

## Pré-registro (gravado e enviado ANTES de qualquer leitura ou simulação da janela de teste)

**Regra de leitura: nenhuma opção, parâmetro, limiar, grade de emissões, métrica ou regra de decisão será ajustada
depois de ver o resultado. O resultado só informa. O padrão do sistema (`pc-f8-c025` + `d_piv` `so_curva`) não muda
por causa deste teste.**

O que já era público antes deste registro (catálogo `dados/catalogo_ampliado.json`): janela X20260918 de
18/09/2026 06:00 a 04/10/2026 11:00; X75 pico 1871 cm em 22/09 04:00; X76 pico 1538 cm em 29/09 23:00. Os dois são
"grandes" (≥ 13 m) e os dois têm o pico de Muçum acima do limite da curva-chave (15 m). Nenhuma série (chuva, nível,
vazão) da janela foi lida até este commit.

### Lista fechada de opções

Arquivos em `calibracao_hec_bacia145/operacional/parametros/` neste commit. `sha256_p` = 16 primeiros hex do sha256 de
`json.dumps(p, sort_keys=True)` (conferido agora contra o `p` de cada arquivo); `sha256 arq` = 16 primeiros hex do
sha256 do arquivo.

| # | opção | modelo base (HEC) | pós-processamento publicado | arquivos | sha256_p | sha256 arq |
|---|---|---|---|---|---|---|
| 1 | antigo (rollback) | `md-val2-c002` (lrdc, rota mc) | aditiva τ(h) do próprio arquivo (`correcao.tau_h`) | `md-val2-c002.json` | `ebb1c61757d60bdb` | `93babdfab59e5cb2` |
| 2a | c008 + d_piv so_curva | `vo-val-c008` (lrdcr) | `d_piv` variante `so_curva` | `vo-val-c008.json`, `hibrido_vo-val-c008.json` | `0eb97094239cbf67` | `abb5dc32936e4520`, `79f65157423936ec` |
| 2b | c008 + d_piv todos_picos | `vo-val-c008` | `d_piv` variante `todos_picos` | idem | idem | idem |
| 3 | **TITULAR** | `pc-f8-c025` (lrdcr, xdmax = xperc = 1) | `d_piv` `so_curva` | `pc-f8-c025.json`, `hibrido_pc-f8-c025.json` | `343ac885f77e5467` | `47f42099ba8a451f`, `83d0c8ecf1cbd932` |
| 4 | sombra todos_picos | `pc-f8-c025` | `d_piv` `todos_picos` | idem | idem | idem |
| 5 | sombra regra por porte | S ≥ 83,4 mm → `po-r4-c008`; senão o titular | S ≥ limiar: `d_piv` do `porte_po-r4-c008.json`; senão `d_piv` `so_curva` do titular | `porte_po-r4-c008.json` (+ arquivos do titular) | `c28b514c3e11fd0f` | `464f0d503cf99a97` |
| 6 | chuva alta (regime ×1,45) | `pc-f8-c025` com ECMWF × (1 + 0,45·w(F72)) | `d_piv` `so_curva` | titular | `343ac885f77e5467` | — |
| 7 | mais chuvosa ECMWF/GFS | `pc-f8-c025` com a fonte de maior F72 | `d_piv` `so_curva` | titular | `343ac885f77e5467` | — |
| R | referência sem previsão | HEC com chuva perfeita (observada) para 1, 2a/2b, 3/4 | o pós de cada opção | — | — | — |

Parâmetros do pós-processamento (copiados dos arquivos, sem mudança):

| arquivo / variante | Muçum q0 / b / qmax / τd | Encantado | LJJ |
|---|---|---|---|
| `hibrido_pc-f8-c025` `so_curva` (titular, 6, 7, 5 abaixo do limiar) | 2601,2 / 0,99 / 4728,0 / 24 | 3041,7 / 1,31 / 5463,3 / 24 | 1944,2 / 1,37 / 3699,8 / 12 |
| `hibrido_pc-f8-c025` `todos_picos` (4) | 2715,9 / 1,17 / 9389,8 / 24 | 3226,9 / 1,39 / 10849,9 / 36 | 2005,6 / 1,41 / 8270,5 / 12 |
| `hibrido_vo-val-c008` `so_curva` (2a) | 2588,8 / 1,04 / 4560,5 / 24 | 3053,2 / 1,35 / 5327,2 / 24 | 1936,5 / 1,47 / 3498,9 / 12 |
| `hibrido_vo-val-c008` `todos_picos` (2b) | 2685,8 / 1,20 / 9175,3 / 24 | 3223,1 / 1,41 / 10681,7 / 36 | 2002,9 / 1,47 / 7862,4 / 12 |
| `porte_po-r4-c008` `d_piv` (5, S ≥ limiar) | 2685,8 / 1,15 / 9627,0 / 24 | 3223,1 / 1,36 / 11151,2 / 36 | 2002,9 / 1,40 / 8293,4 / 12 |

rmax = 3 em todos. Aplicação = `operacional/posproc.py` deste commit (sha256 arq `6fcd669736a543db`): `d_piv` =
`posproc.d_piv`; aditiva = a mesma conta de `posproc.ponto` (τ(h) por horizonte h = t − t0, decaimento em t − tv);
tv = último observado válido (vazão > 0, nível ≤ limite da curva) até 72 h antes de t0. Índice S da opção 5 =
`operacional/porte.py` (`indice_s`, sha256 arq `48e8a2c722554ea1`): chuva das 24 h até t0 + 48 h da ECMWF (GFS se a
ECMWF faltar), média de área nas 87 sub-bacias da lista do arquivo; a decisão vale para os dois cenários de chuva.
Regime da opção 6 (`_analise_chuvaprev/gerar_cp.py`, `ajuste_cp.json`): F72 = total da ECMWF nas 72 h após t0, média de
área na bacia de Muçum (topologia do `.basin`); w = 0 abaixo de 40 mm, 1 acima de 60 mm, linear entre; k = 1,45;
emissão com w = 0 usa a vazão da ECMWF crua (não roda de novo). Opção 7 (`avaliar_cp.py`): GFS se a soma das 72 h da GFS
na bacia de Muçum (mesmos pesos) for maior que a da ECMWF; senão ECMWF; a série é a do HEC já rodado com a fonte escolhida.

### Dados

- Chuva observada: `dados/forcamento_v3b/X20260918.json.gz` (blob `72853c4f53c69111715d7cb21135116677462aad`, igual
  em todas as branches de frente; é cópia byte a byte do v3 porque o INMET termina em 25/11/2025 — `_analise_inmet`).
  Mesma rede/QC/IDW das demais janelas v3b. Não será refeita.
- Observados: `dados/observados/<posto>_X20260918.csv.gz` (telemetria ANA, relógio corrigido na leitura).
- Chuva prevista (ECMWF IFS open data e GFS 0,25°): baixada agora com os scripts da frente de chuva prevista
  (`repo_hec_calib/_analise_bacia145/chuva_prevista/`: `baixar_aws.py`, `grade.py`, `gerar_forcamento.py`), copiados para
  `_analise_teste/` (fora do git) com uma única mudança: a lista de eventos passa a ser X75/X76. Mesmos atrasos (GFS
  5 h, ECMWF 7 h), "rodada mais recente publicada até t0", 72 h a partir de t0+1 h, média na área da sub-bacia →
  `dados/forcamento_prevista/X20260918__{ecmwf,gfs,ecmwfrg}.json.gz`. Emissão sem rodada disponível (mesmo recuando 2
  ciclos, como no script) fica fora e é relatada.
- Grade de emissões (`_analise_hibrido/base.py: grade_emissoes`, igual à hb-r1/hb-f8/cp-r1): t0 = pico do nível de
  Muçum no evento − 6k h, de 24 h antes do início da subida (mínimo do nível nas 96 h antes do pico) até pico + 12 h,
  fora das primeiras 24 h da janela e com t0 ≤ fim − 6 h. Janelas derivadas `X20260918__<t0>__<fonte>` (estado
  inicial e observados da mãe; chuva observada até t0 e a prevista depois; horizonte avaliado 48 h).

### Rodada na nuvem (uma só)

`rodadas/PEDIDO.json` com `"abrir_teste": true`, `"forcamento": "forcamento_v3b"`, papéis congelados
(`E18`, `E22` em validação), candidatos `md-val2-c002`, `vo-val-c008`, `pc-f8-c025`, `po-r4-c008` com os `p` dos
arquivos acima. Janelas: X20260918 (mãe = chuva perfeita), as derivadas ECMWF/GFS de todas as emissões, as derivadas
`ecmwfrg` com chuva alterada, e X20260827 (validação, só conferência de reprodução contra vo-valb/pc-valx/po-valr; não
entra em nenhum resultado). O lote é cartesiano (todos os candidatos em todas as janelas); só as combinações da tabela
acima são relatadas. O fluxo `hec-bacia145-lote.yml` recebe só a escolha da pasta de forçamento pelo PEDIDO (as mesmas
linhas das branches de frente, commit `be8b13dfe`); o código do HEC (`codigo/`) é o do `-sistema`.

### Métricas (definidas agora; código = `_analise_hibrido/avaliar.py` e `comparar_f8.py`, sem mudança de regra)

(a) **Janela X20260918, chuva perfeita, modelos base c002, c008, f8** (e `po-r4-c008` só como informação): por evento
(X75, X76) e controle (Tainhas, Castro Alves, Monte Claro, LJJ, Muçum, Encantado): volume, erro de pico, NSE, atraso
(`bacia_inteira.avaliar_sim`, a mesma conta da calibração/validação); J_evento = `bacia_inteira.J_evento`; J = média
nos 2 eventos; J_pico = `metricas.J_ponderado` com `metricas.pesos_por_pico` nos 2 eventos.

(b) **Emissões ao vivo simuladas (X75, X76), fontes perfeita / ECMWF / GFS (+ regime e mx nas opções 6/7)**, controles
Muçum, Encantado, LJJ (pós de cada opção) e Tainhas, Castro Alves, Monte Claro (HEC bruto, sem pós):
- Erro de pico por antecedência X = pico observado − t0, faixas 1–6, 7–12, 13–24, 25–47 h: pico previsto = máximo em
  t0+1..t0+48; pico observado = horário pelo nível (Muçum/Encantado/LJJ) ou pela vazão, vazão da telemetria nesse
  horário; mediana das emissões do evento, depois mediana entre eventos (com 2 eventos = média). Observado "com" =
  toda a telemetria (inclusive acima do limite da curva); "sem" = só eventos com pico dentro da curva (Muçum ≤ 1500 cm,
  LJJ ≤ 1800 cm, Encantado ≤ 1920 cm) e só horas com nível ≤ limite.
- MAE (m³/s) em +6/+12/+24/+48 h: média de |Q − O| nas emissões com observado no horizonte ("com" e "sem").
- Alarmes de Muçum, 10 m e 15 m, janela de 24 h: aviso se a previsão de t0+1..t0+24 passa da vazão da cota (curva da
  telemetria `correcao_horaria.Curva` da janela X20260918, pares da janela + agregado das janelas de cal/val);
  acerto se o nível medido cruza a cota nessas 24 h; emissões com o nível em t0 já acima da cota ficam fora.
  Acertos / falsos / perdidos e eventos avisados / que cruzam.
- Hidrogramas (observado × opções), Muçum e Encantado, ECMWF, escolhidos agora: X75 em t0 = pico − 24 h, X75 em
  t0 = pico − 12 h e X76 em t0 = pico − 12 h.

### Regra de leitura (fixada agora)

Métrica principal: |erro de pico| médio de Muçum e Encantado, ECMWF, observado "com", nas faixas 1–6, 7–12 e 13–24 h
(média das 6 células). Secundárias: MAE +24 h (Muçum, Encantado), alarmes de 15 m e 10 m em Muçum.
- **O titular se confirma** se (i) a métrica principal dele não for pior que a do antigo (opção 1) em mais de 5 p.p. e
  (ii) no alarme de 15 m ele tiver acertos ≥ os do antigo e falsos ≤ os do antigo + 1.
- **Uma sombra (2a, 2b, 4, 5, 6, 7) "teria sido melhor"** se a métrica principal dela for ≥ 5 p.p. menor que a do
  titular, sem mais falsos de 10 m ou 15 m e com MAE +24 h no máximo 10 % pior.
- **Confiança na validação:** os erros de pico do titular no teste são comparados com os da validação (ECMWF,
  médias+grandes, Muçum −5/−7/−17 %, Encantado −1/−7/−14 % em 1–6/7–12/13–24 h); diferença ≤ 15 p.p. em cada célula =
  "coerente com a validação".
- Com 2 eventos, ambos grandes e com Muçum acima de 15 m (vazão de pico extrapolada), nenhum resultado é
  estatisticamente conclusivo; o texto dirá isso. Seja qual for o resultado, nada é ajustado e o padrão não muda.

## Resultado

(preenchido depois da rodada, sem alterar nada acima)

### Execução

- Pré-registro: commit `655bc699a` (enviado antes de qualquer leitura da janela). Pedido da rodada: commit `5e3613327`.
- Rodada `tf-r1`: [run 38075082265](https://github.com/previne-taquari-antas/Previne-Taquari-Antas---Redes-Neurais/actions/runs/38075082265)
  — 75 janelas × 4 candidatos = 300 simulações, 0 falhas.
- Reprodução em X20260827: c008, f8 e po-r4-c008 da `tf-r1` iguais aos lotes locais `vo-valb-c008`, `pc-valx-c000` e
  `po-valr-c002` (máx |dif| = 0,0000 m³/s). O código `-sistema` com `forcamento_v3b` reproduz as frentes.
- Emissões: X75 14 (19/09 10h … 22/09 16h), X76 16 (26/09 17h … 30/09 11h). As 60 rodadas ECMWF/GFS foram achadas sem
  recuo de ciclo; nenhuma emissão ficou fora. `ecmwfrg` mudou a chuva em 13 das 30 emissões. A regra por porte
  (S ≥ 83,4 mm) disparou em 8 emissões (X75 21/09 16h–22/09 04h; X76 28/09 11h–29/09 11h).
- Picos observados: X75 Muçum 1871 cm / 8664 m³/s (acima de 15 m: vazão extrapolada), Encantado 1643 cm / 10995 m³/s,
  LJJ 2015 cm (acima de 18 m); X76 Muçum 1538 cm / 6310 m³/s (acima), Encantado 1352 cm / 8033 m³/s, LJJ 1588 cm.
  Curva da janela de teste em Muçum: 10 m = 3246 m³/s, 15 m = 6064 m³/s.
- A chuva prevista ficou muito abaixo da observada antes dos dois picos. Total de 72 h na bacia de Muçum:
  - X75, de 20/09 04h a 21/09 04h: observado 98–99 mm, ECMWF 36–42 mm, GFS 24–36 mm;
  - X76, de 26/09 17h a 27/09 23h: observado 113–131 mm, ECMWF 42–46 mm, GFS 59–75 mm.

### (a) Janela X20260918 com chuva perfeita (modelo base, sem pós)

| modelo | J X75 | J X76 | J | J_pico (pesos 1,17/0,83) |
|---|---|---|---|---|
| c002 (md-val2) | 7,64 | 7,02 | 7,33 | 7,38 |
| c008 (vo-val) | 8,09 | 5,20 | 6,65 | 6,89 |
| f8 (pc-f8-c025, titular) | 8,47 | 4,92 | 6,69 | 7,00 |
| po-r4-c008 (só informação) | 7,81 | 4,47 | 6,14 | 6,43 |

Volume / erro de pico / NSE / atraso do f8 (os outros estão em `_analise_teste/resultado.md`, fora do git). Erro de
pico de Muçum e LJJ em X75, e de Muçum em X76, não é calculado, porque o pico está acima da curva:

| evento | Tainhas | Castro Alves | Monte Claro | LJJ | Muçum | Encantado |
|---|---|---|---|---|---|---|
| X75 | −42 % / −58 % / 0,27 / +3 h | −27 % / −62 % / 0,34 / +7 h | −32 % / −58 % / 0,33 / +6 h | +7 % / — / 0,43 / +6 h | +15 % / — / 0,39 / +6 h | −12 % / −36 % / 0,61 / +5 h |
| X76 | +30 % / +14 % / 0,59 / +0 h | −4 % / −29 % / 0,84 / +5 h | −17 % / −36 % / 0,76 / +9 h | −9 % / −29 % / 0,82 / +7 h | −4 % / — / 0,93 / +5 h | −6 % / −26 % / 0,90 / +3 h |

### (b) Emissões X75/X76 — regra de leitura (ECMWF, observado "com")

A métrica principal é o |erro de pico| médio de Muçum e Encantado, nas faixas 1–6, 7–12 e 13–24 h. As colunas de alarme
mostram acertos/falsos/perdidos.

| opção | principal ECMWF | principal GFS | principal chuva perfeita | MAE +24 h Muçum / Encantado (m³/s) | alarme 15 m | alarme 10 m |
|---|---|---|---|---|---|---|
| 1 antigo (c002 + aditiva) | 16,7 % | 18,0 % | 13,7 % | 1567 / 1896 | 1/0/7 | 3/0/5 |
| 2a c008 + d_piv so_curva | 13,5 % | 15,7 % | 10,3 % | 1483 / 1806 | 1/0/7 | 3/0/5 |
| 2b c008 + d_piv todos_picos | 11,2 % | 13,3 % | 6,2 % | 1513 / 1837 | 2/0/6 | 3/0/5 |
| **3 TITULAR** f8 + so_curva | **14,8 %** | 16,9 % | 11,9 % | 1484 / 1814 | 1/0/7 | 3/0/5 |
| 4 f8 + todos_picos | 10,5 % | 12,9 % | 6,3 % | 1516 / 1850 | 2/0/6 | 3/0/5 |
| 5 porte | 10,1 % | 12,4 % | — | 1518 / 1851 | 1/0/7 | 3/0/5 |
| 6 ECMWF × regime | 14,2 % | — | — | 1492 / 1832 | 1/0/7 | 3/0/5 |
| 7 mx (mais chuvosa) | 14,6 % | — | — | 1454 / 1775 | 1/0/7 | 3/0/5 |
| HEC f8 bruto (ref.) | 29,5 % | 31,5 % | 26,5 % | 1385 / 1627 | 1/0/7 | 3/0/5 |

Erro de pico por antecedência. Cada célula é a mediana por evento e depois a média dos 2 eventos; chuva ECMWF,
observado "com":

| opção | Muçum 1–6 | 7–12 | 13–24 | 25–47 | Encantado 1–6 | 7–12 | 13–24 | 25–47 | LJJ 1–6 | 7–12 | 13–24 | 25–47 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 antigo | −1 % | −12 % | −44 % | −59 % | +3 % | −6 % | −33 % | −60 % | −1 % | −23 % | −55 % | −69 % |
| 2a | −4 % | −9 % | −42 % | −56 % | +2 % | −5 % | −19 % | −53 % | +3 % | −7 % | −45 % | −64 % |
| 2b | +4 % | +3 % | −38 % | −54 % | +6 % | +4 % | −12 % | −53 % | +11 % | +6 % | −45 % | −65 % |
| **3 titular** | −7 % | −11 % | −42 % | −55 % | +3 % | −7 % | −20 % | −52 % | +1 % | −7 % | −44 % | −64 % |
| 4 | +2 % | +1 % | −38 % | −52 % | +9 % | +1 % | −13 % | −52 % | +10 % | +5 % | −44 % | −64 % |
| 5 porte | +0 % | +2 % | −40 % | −52 % | +4 % | +1 % | −14 % | −52 % | +9 % | +6 % | −44 % | −63 % |
| 6 regime | −7 % | −11 % | −40 % | −54 % | +3 % | −7 % | −18 % | −51 % | +1 % | −7 % | −42 % | −60 % |
| 7 mx | −7 % | −11 % | −41 % | −54 % | +3 % | −7 % | −19 % | −51 % | +1 % | −7 % | −44 % | −60 % |
| titular, chuva perfeita | −7 % | −17 % | −21 % | −23 % | +3 % | −7 % | −17 % | −17 % | +1 % | −12 % | −17 % | −17 % |

O titular varia bastante entre os eventos: X75 Muçum −5/−5/−59/−78 % e X76 Muçum −8/−16/−25/−32 %; X75 Encantado
+7/−2/−24/−80 % e X76 Encantado −2/−12/−16/−25 %.

Observado "sem":
- Muçum não tem nenhum evento, porque os dois picos estão acima de 15 m.
- Em Encantado, "sem" é igual a "com", porque os dois picos estão dentro da curva.
- LJJ tem só X76; titular ECMWF +2/−9/−26/−44 %.

Os controles de montante (HEC bruto do titular, ECMWF) subestimam muito o pico. Erro nas faixas 1–6/7–12/13–24/25–47 h:

| controle | 1–6 h | 7–12 h | 13–24 h | 25–47 h |
|---|---|---|---|---|
| Tainhas | −29 % | −38 % | −52 % | −64 % |
| Castro Alves | −44 % | −50 % | −65 % | −71 % |
| Monte Claro | −44 % | −57 % | −69 % | −79 % |

MAE do titular em Muçum, chuva ECMWF, observado "com" (m³/s; HEC bruto entre parênteses):

| horizonte | +6 h | +12 h | +24 h | +48 h |
|---|---|---|---|---|
| titular (HEC bruto) | 572 (719) | 887 (825) | 1484 (1385) | 1990 (1947) |

Alarmes de Muçum com chuva ECMWF:
- 15 m: todas as opções avisaram X75 na emissão de 21/09 16h, 12 h antes do pico. Nenhuma avisou antes do cruzamento
  nas emissões de 18 h antes do pico ou mais. Em X76, só 2b e 4 avisaram (29/09 17h, 6 h antes do pico).
- 10 m: todas as opções acertaram as mesmas 3 emissões.
- Não houve falso alarme em nenhuma opção. Com 2 cheias grandes, quase não havia chance de falso alarme.

### Leitura (pela regra pré-registrada; nada foi ajustado)

1. **O titular se confirma.** Na métrica principal ele tem 14,8 %, contra 16,7 % do antigo; o critério exigia não ser
   pior que o antigo mais 5 p.p. No alarme de 15 m, titular e antigo empatam em 1/0/7. A vantagem sobre o antigo é
   pequena (1,9 p.p.). Ela vem de Encantado em 13–24 h (−20 % contra −33 %), não de Muçum.
2. **Nenhuma sombra "teria sido melhor" pelo critério de ≥ 5 p.p.** Mas as variantes que puxam o pico para cima
   chegaram perto:
   - porte: 10,1 % (−4,7 p.p.);
   - f8 + todos_picos: 10,5 % (−4,3 p.p.);
   - c008 + todos_picos: 11,2 % (−3,6 p.p.).

   As três passam nos critérios de falsos e de MAE. As duas `todos_picos` avisaram 15 m em X76, e o titular não. O
   GFS e a chuva perfeita mostram o mesmo sentido: com chuva perfeita, todos_picos fica em 6 % e o titular em 12 %. É
   o resultado esperado para dois eventos acima de 15 m, o regime para o qual `todos_picos` foi ajustado. O
   pré-registro já dizia que, com 2 eventos, isso não é base para trocar o padrão.
3. **As correções de chuva (6 regime, 7 mx) quase não mudaram o erro de pico** (−0,6 e −0,2 p.p.). O erro de 13–24 h
   é dominado pela chuva prevista: ECMWF e GFS previram de 25 % a 55 % da chuva das 72 h. Com chuva perfeita, o
   titular de Muçum em 13–24 h cai de −42 % para −21 %. O mx teve o menor MAE em +24 h e +48 h (Muçum 1454 e 1736,
   contra 1484 e 1990 do titular).
4. **Confiança nos números da validação.**
   - Em 1–6 h e 7–12 h, os números se mantêm: o titular dá −7/−11 % em Muçum (validação −5/−7 %) e +3/−7 % em Encantado
     (validação −1/−7 %). Todos ficam dentro de 15 p.p. da validação.
   - Em 13–24 h, Encantado é coerente (−20 % contra −14 %), mas Muçum fica **fora** (−42 % contra −17 %), puxado por
     X75 (−59 %), em que a chuva prevista falhou.
   - O número de 13–24 h da validação deve ser lido como otimista quando a previsão de chuva erra muito.
   - O pós-processamento com d_piv acerta o pico a 1–12 h, mas piora o MAE a partir de +12 h. Em +24 h, o HEC bruto
     tem MAE de 1385 m³/s em Muçum, contra 1484 do titular. Os hidrogramas mostram por quê: a recessão simulada é mais
     lenta que a observada.
   - Os controles de montante subestimam o pico em 58–62 % em X75 mesmo com chuva perfeita, o que limita qualquer
     pós-processamento a jusante.
5. Tudo isto vem de **2 eventos, ambos grandes e com a vazão de pico de Muçum extrapolada acima de 15 m**. Nada é
   estatisticamente conclusivo. O padrão do sistema (pc-f8-c025 + d_piv so_curva) **não muda**. Depois deste commit, a
   janela X20260918 e os eventos X75/X76 deixam de ser teste independente.
