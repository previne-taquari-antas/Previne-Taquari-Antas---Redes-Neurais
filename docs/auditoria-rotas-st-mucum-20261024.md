# PREVINE — auditoria automatizada de rotas até trechos elevados
**Data:** 24/10/2026. **Municípios:** Santa Tereza e Muçum, RS.
**Código auditado:** `pesquisas/gt-risco-vida.html` e `scripts/test_gt_page.js`.

## Finalidade e limite da análise
A avaliação é **computacional**, feita com a rede de vias OpenStreetMap e cotas de inundação/HAND vinculadas ao mapa PREVINE. Ela **não** constitui vistoria, certificação de segurança de ruas, verificação de pontes ou liberação de abrigo. Uma saída é apenas um **trecho elevado candidato** da rede, não necessariamente um refúgio, abrigo aberto ou acesso transitável. A elevação HAND não é a altitude absoluta, nem é profundidade hidráulica prevista.

## Bases e cenários
| Parâmetro | Santa Tereza | Muçum |
|---|---:|---:|
| HAND do cenário inicial | 13,4 m | 13,0 m |
| Régua aproximada correspondente (referência do painel) | 15,0 m | 18,0 m |
| Pontos de edificações OSM no grafo | 565 | 1.937 |
| Nós de rua OSM | 1.385 | 1.972 |
| Trechos de rua OSM | 1.425 | 2.099 |
| Trechos sem cota utilizável no arquivo | 765 | 1.135 |
| Trechos identificados como pontes no grafo | 54 | 73 |
| Edificações sem cota de inundação utilizável | 177 | 502 |
| Edificações a > 60 m do nó de rua associado | 117 | 672 |

**Atenção:** edificações OSM não representam necessariamente domicílios efetivamente habitados. Distância acima de 60 m é uma *regra conservadora de triagem*, não uma medida de impossibilidade real de acesso. As classes podem se sobrepor: não somar colunas de problemas como imóveis distintos.

## Teste automatizado com regras conservadoras
Após as correções, o algoritmo encontrou as seguintes situações **no cenário inicial de cada município**:

| Estado algorítmico | Santa Tereza | Muçum |
|---|---:|---:|
| Percurso computável com margem HAND mínima modelada de 1 m, cota disponível e nó de acesso até 60 m | 167 | 682 |
| Caminho topológico detectado, mas sem 1 m de margem no modelo — **traçado bloqueado** | 13 | 113 |
| Sem percurso desenhado pelos critérios conservadores / com dados insuficientes | 385 | 1.142 |
| **Total de edificações avaliadas** | **565** | **1.937** |

A classe “percurso computável” significa somente que o grafo encontra um caminho em cenário simulado, com cotas acima do limiar operacional computacional. **Todas** essas ligações continuam sem inspeção do acesso porta–rua, trafegabilidade das vias, correnteza, pontes, deslizamentos e destino real. Portanto **nenhuma das 167/682 rotas está validada para orientar evacuação**.

## Correções de 24/10/2026
1. A origem com cota de inundação ausente deixa de gerar percurso.
2. A origem alagada no cenário não recebe falsa rota seca na cota escolhida.
3. Ligação da edificação a nó viário acima de 60 m deixa de gerar percurso, mesmo que o roteamento do restante da rua seja possível.
4. Trechos sem cota utilizável ou identificados como ponte são excluídos da busca.
5. Um caminho sem margem HAND modelada de 1 m é sinalizado como pendência em vez de linha azul de saída.
6. Pontos de edificações e legenda seguem essas regras; o painel mostra as lacunas de ligação e de cota.
7. A página inicia com rota ilustrativa baseada em uma edificação de cadastro preliminar com margem no modelo e ligação de até 40 m; ela não representa a localização do usuário.
8. O teste de regressão inclui bloqueio de origem sem cota, acesso distante, caminho sem margem e checagem dos trechos efetivamente percorridos.

## Pendências que exigem conferência e impedem validação operacional
- **Edificação–rua:** geocodificar a entrada efetiva, não apenas o centroide; verificar muro, talude, passagem privada, rampa, cerca, escadaria e possível travessia de curso d'água. Confrontar OSM, ortofoto recente e cadastro municipal; registrar evidência e data.
- **Cotas das vias:** corrigir ausências de altitude/HAND e conferir a referência vertical do terreno, água e régua. Checar limites do recorte, pontes, aterros e viadutos; não extrapolar HAND como profundidade.
- **Pontes e passagens:** vistoriar cabeceiras, tabuleiro, danos, circulação efetiva e eventual interdição. Nenhuma ponte é declarada liberada automaticamente.
- **Destinos:** distinguir rua elevada de abrigo ou refúgio; verificar acessibilidade, espaço, capacidade, abertura e perigos locais, junto à Defesa Civil.
- **Cenários:** comparar com cotas e manchas de 2023/2024 e outros eventos, hidrodinâmica, velocidade, remanso (incluindo Arroio Marrecão), efeito de correnteza e bloqueios reais de rua.
- **Publicação:** validar construção do GitHub Pages e testar navegador/celular com mapa visível e popup para pontos em áreas secas, alagadas e sem dados; não divulgar como guia operacional antes de validação institucional e de campo.

## Regra de interpretação
**Verde = compatibilidade computacional preliminar**, nunca via liberada. **Azul = hipótese de trajeto pelas vias a trecho alto**, nunca rota certificada. **Cinza/amarelo = dado ou acesso insuficiente**, não prova de isolamento. **Vermelho = origem na mancha do cenário**, não indicação de nível observado em tempo real. A seleção do nível HAND é um exercício; mudanças hidrológicas reais podem invalidar qualquer resultado.

Fontes internas: dados embutidos em `pesquisas/gt-risco-vida.html`; `docs/gt-risco-vida-camadas-lacunas-20261024.md`; documentação do gerador `codigo_python/09_rota_fuga/README.md`. Fontes externas de referência: IBGE CNEFE 2022; OpenStreetMap (© contribuidores); Plano Municipal de Contingência; SGB (2025). 
