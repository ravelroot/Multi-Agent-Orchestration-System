# Agentes e ferramentas

Atualizado em 05/11/2026 14:24 (Brasília).

| Agente | Temperatura | Ferramentas | Tamanho do prompt |
|---|---|---|---|
| Supervisor | 0.1 | nenhuma | 132 palavras |
| Pesquisador | 0.2 | `buscar_web`, `consultar_wikipedia`, `ler_pagina`, `calcular`, `data_atual` | 115 palavras |
| Redator | 0.6 | nenhuma | 108 palavras |
| Revisor | 0.1 | `metricas_do_rascunho`, `verificar_citacoes`, `contar_palavras` | 78 palavras |

| Ferramenta | Descrição |
|---|---|
| `buscar_web` | Busca na web e devolve títulos, links e resumos, cada um com o número [n] da fonte. |
| `consultar_wikipedia` | Consulta a Wikipédia e devolve o resumo do verbete mais relevante, com o número [n] da fonte. |
| `ler_pagina` | Lê uma página pública (http ou https) e devolve o texto principal, com o número [n] da fonte. |
| `calcular` | Calcula uma expressão matemática com + - * / // % ** e parênteses. Use para qualquer conta. |
| `data_atual` | Informa a data e a hora atuais. Use para calcular idades, prazos ou intervalos. |
| `contar_palavras` | Conta palavras, frases e parágrafos de um texto e estima o tempo de leitura. |
| `metricas_do_rascunho` | Mede o rascunho atual: palavras, parágrafos, seções, legibilidade e distância do tamanho pedido. |
| `verificar_citacoes` | Confere as citações [n] do rascunho atual: números inválidos, fontes não citadas e parágrafos sem citação. |
