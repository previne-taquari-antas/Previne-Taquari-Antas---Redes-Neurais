# Manutenção do PREVINE — revisão de 21/10/2026

## Alterações e verificação

1. **Fontes e robôs:** monitor automático `site-feed-health.yml`, a cada 30 minutos, verifica oito arquivos e separa idade da consulta da idade da observação. Falhas das fontes ao vivo reprovam o monitor; fontes experimentais antigas geram avisos. O gerador binário deixa de emitir decisão atual com fonte ausente, futura ou com mais de 36 horas, preservando a decisão anterior em campo histórico.
2. **Mapas móveis:** réguas compartilham atualização imediata e desenho limitado a um por quadro, com atualização final garantida; área mínima de toque de 44 px. Testes de interação incluem cidades, réguas, recuperação da conexão e evacuação.
3. **Código compartilhado:** `SiteRuntime.bindRange` substitui manipuladores repetidos nos quatro mapas. Os testes verificam coalescência e atualização final.
4. **Desempenho:** `site-performance.json` registra a aplicação do otimizador existente em 22 páginas: HTML de 12.625.828 para 700.741 bytes, com 9.168.554 bytes de scripts extraídos. Isso melhora reutilização por cache; NÃO representa redução equivalente do primeiro download.
5. **Regressão:** CI executa testes de frontend, fontes e decisões binárias, além de Chromium móvel/desktop. Fixtures não substituem validação hidrológica.
6. **Inventário:** `site-inventory.json` relaciona 112 páginas públicas, dependências, scripts/workflows e arquivos iguais. Ausência de referência HTML direta não prova desuso; nenhum arquivo científico foi excluído com esse critério. Testes e documentação ficam fora do pacote de publicação.

## Fontes e consumidores

| Produção | Arquivo | Consumidores |
| --- | --- | --- |
| Robôs de previsão ao vivo / `gerar_previsao_ao_vivo.py` | `previsao_ao_vivo.json`, `previsao_ao_vivo_mucum.json` | Mapas de previsão das duas cidades |
| Atualização meteorológica de pesquisa | `research_weather_*_latest.json` | Painéis de pesquisa e padrões visuais |
| Exportação de probabilidade experimental | `research_probability_*_latest.json` | Gerador binário e padrões visuais |
| `build_binary_research_decision.py` | `research_binary_decision_*_latest.json` | Decisões de pesquisa |
| `build_visual_research_patterns.py` | `research_visual_patterns_*_latest.json` | Padrões visuais de pesquisa |

## Pendências concretas

A auditoria registrada em `site-feed-health.json` encontrou probabilidade experimental de Santa Tereza datada de 27/08 e Muçum de 25/08. A cadeia produtora dessas probabilidades não foi restabelecida nesta revisão. Não há autorização técnica para fabricar novos valores a partir dos antigos. O monitor identifica o problema e o gerador binário impede decisões atuais com essas fontes. Outros consumidores devem continuar sendo auditados individualmente; um arquivo derivado recém-gerado não torna sua fonte atual.

Uma execução de previsão da bacia recusou uma rodada com apenas 247/530 estações; preservar o snapshot anterior foi comportamento de proteção. Não foi reduzido o requisito de cobertura.

## Comandos

```sh
python scripts/validate_site_frontend.py
python -m unittest scripts.test_binary_research_decision scripts.test_site_feeds
node scripts/test_range_controls.js
cd tests/frontend && npm ci && npx playwright install chromium && npm test
```

Os JSONs desta pasta documentam uma fotografia da revisão, não são monitores ao vivo. O relatório de interação fica no artefato de CI por 14 dias.
