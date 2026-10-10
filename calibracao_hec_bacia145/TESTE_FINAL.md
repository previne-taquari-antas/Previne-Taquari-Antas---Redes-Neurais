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
