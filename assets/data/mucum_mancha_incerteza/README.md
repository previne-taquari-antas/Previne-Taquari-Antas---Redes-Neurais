# Muçum — mancha prevista com incerteza (SOMBRA)

Pesquisa em sombra. **Não é alerta oficial** e não aparece na página de previsão.

## O que o robô faz
`codigo_python/01_previsao_ao_vivo/gerar_mancha_incerteza_mucum_sombra.py`, chamado pelo
workflow `mancha-incerteza-mucum-sombra.yml` depois de cada ciclo da previsão ao vivo de Muçum:

1. Para cada horizonte principal disponível em `previsao_ao_vivo_mucum.json`, monta a faixa
   do nível (P10/P50/P90) somando à previsão os erros fora da amostra do mesmo grupo
   (situação do rio × faixa de nível) — `tabela_incerteza.json`.
2. Converte para HAND (nível − 500 cm) somando a incerteza da conversão (σ = 1,5 m) e
   devolve três níveis HAND: contornos com 90 %, 50 % e 10 % de chance de alagar.
   Use esses níveis em `assets/data/mucum_inundacao/contornos_extravasamento.json`.
   `null` = água dentro da calha.
3. Conta endereços e pessoas em cada contorno e o número esperado (`expostos_por_hand.json`).
4. Confere as previsões antigas quando a hora-alvo passa (`historico_sombra.jsonl`) e
   resume a cobertura real em `sombra_atual.json → verificacao`.

## Página de pesquisa (fora do menu)
`mucum_mancha_incerteza_sombra.html` desenha as três áreas (90 / 50 / 10 %) sobre o mapa,
reaproveitando os contornos HAND publicados, e mostra pessoas, idosos, crianças, domicílios,
escolas e saúde em cada uma. Lê `sombra_atual.json` do GitHub Raw (a cópia publicada do site
fica para trás até o próximo deploy) e tem um exemplo fixo, `exemplo_cheia_set2026.json`
(cheia de 22/09/2026, recalculada pelo próprio robô; abrir com `?ver=exemplo`).
`noindex`, sem link no menu, com aviso de "não é alerta oficial".

## De onde vêm as tabelas
- `tabela_incerteza.json`: 99 quantis do erro (cm) da validação cruzada por evento do
  controle LJJ de Muçum (58 eventos, 2018–2026). **Não** são erros do modelo publicado:
  a sombra existe para medir se a faixa funciona com ele. O 2 h usa a tabela de 4 h.
- `expostos_por_hand.json`: contagens acumuladas por decímetro de HAND, a partir do
  CNEFE 2022 (IBGE) e da população por setor do Censo 2022 (mapa de risco à vida).
  Só agregados — nenhum endereço individual.

## Validação feita antes (cheias de teste: jul/2026, 21/09, 29/09, 10/10, 05/11/2026)
Pico real dentro dos contornos de 90 %–10 % em 14 de 15 previsões (4/8/12 h).
No teste, a faixa do nível cobre ~70 % (meta 80 %): tratar como "faixa provável".
Mancha observada de maio/2024 e Sentinel-1 (2020, 2024, 2026) confirmam a regra de 500 cm.
