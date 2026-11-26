# Histórico de forçantes da bacia Taquari-Antas

Robô de pesquisa para o estudo **"o que as grandes cheias têm em comum / vai inundar ou não"**.
Ele traz os dados que hoje faltam no repositório (auditoria de 26/11/2026):

| Lacuna encontrada | O que o robô baixa | Fonte |
|---|---|---|
| Chuva só de 3 pluviômetros do vale, desde dez/2022 | Chuva **diária** dos ~149 postos ANA da bacia, desde 1980 | ANA HidroSerieHistorica |
| Nível só em janelas de evento (antes de set/2026) | **Cota e vazão diárias** contínuas de 15 estações-chave | ANA HidroSerieHistorica |
| Sem chuva horária das cabeceiras fora de set/2023 | Chuva/nível/vazão **horários** de 20 estações telemétricas, desde 2014 | ANA telemetria |
| Sem umidade do solo nem reanálise | Chuva e **umidade do solo** (0–7, 7–28, 28–100 cm) por sub-bacia, desde 1990 | ERA5-Land (Open-Meteo Archive) |

Saída em `assets/data/historico_bacia/` (CSV gzip) e `manifesto_latest.json` (cobertura e erros por série).

## Como rodar

GitHub → **Actions** → *Historico de forcantes da bacia* → **Run workflow**.
A primeira carga completa leva algumas rodadas: cada rodada para depois do orçamento de tempo,
publica o que já baixou e a próxima continua de onde parou. Depois disso, roda sozinho aos domingos.

## Regras

- Ausência é ausência: nada é interpolado e lacuna nunca vira zero.
- Nada é sobrescrito com vazio; ANA consistido (2) prevalece sobre bruto (1).
- Chuva telemétrica: soma das leituras distintas na hora (rótulo = hora de início, horário local),
  mesma convenção de `chuvas_horarias.csv`.
- ERA5-Land no centroide da sub-bacia é **contexto de grande escala**: subestima chuva convectiva extrema;
  conferir com MERGE/IMERG (próxima etapa, exige download via FTP/credencial).
- Pesquisa apenas — não é dado oficial e não gera alerta.

## Próximos passos (depois da carga)

1. Catálogo objetivo de cheias 1980–2026 a partir da cota diária (Santa Tereza, Muçum, Encantado, Estrela).
2. Casos negativos: todo episódio com chuva de 72 h ≥ 80 mm na bacia que não virou cheia.
3. Testes: curva chuva do evento × umidade antecedente, logística com 3–5 variáveis, validação
   deixando um evento de fora e divisão temporal (até 2022 × 2023–2026).
