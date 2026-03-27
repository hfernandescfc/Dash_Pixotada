# CLAUDE.md — Dash Pixotada

## Contexto do projeto

Acompanhamento semanal de uma pelada de futebol entre amigos. Os scouts são extraídos manualmente a partir de conversas do WhatsApp e arquivos históricos em CSV. Após cada evento semanal, os scripts Python são executados localmente para regenerar os HTMLs e a página é publicada.

## Fluxo de trabalho

```
CSV de scouts + players.json
        ↓
  Scripts Python (localmente)
        ↓
  HTMLs gerados na raiz do repo
        ↓
  git push → deploy automático (GitHub Pages ou Netlify)
```

**Não há etapa de build no servidor.** Os HTMLs já são gerados localmente antes do push.

## Dados

| Arquivo | Descrição |
|---|---|
| `data/SCOUTS PIXOTADA 2026 - BASE.csv` | Scouts por partida: gols, assistências, cartões, classificação dos times |
| `data/players.json` | Cadastro de jogadores com nota (1–6), intensidade e status de mensalista |

Colunas do CSV: `Data, Time, Jogadores, Gol, Assist, Amarelo, Red, Pontos, Pixotada, Desarme, Classificação`

## Scripts Python

Execute na ordem abaixo após atualizar o CSV de scouts:

| Script | Função | Gera |
|---|---|---|
| `pixotada_dashboard.py` | Dashboard principal com gráficos interativos | `index.html`, `dashboard_pixotada_2026.html` |
| `pixotada_scores.py` | Rankings por 3 modelos de pontuação (conservador, equilibrado, agressivo) + Raio X individual + Premiação mensal | `ranking_geral_jogadores.html`, `ranking_modelos_ultimas4.html`, `raio_x_jogador.html`, `premiacao_mensal.html` |
| `pixotada_effect_analysis.py` | Efeito ajustado por jogador e sinergias entre duplas | `efeito_jogadores.html` |
| `rating_recommendations.py` | Sugestão de ajuste de notas com base na forma recente | `sugestao_novas_notas.html` |
| `recommendation_details_page.py` | Detalhamento partida a partida das recomendações | `detalhe_recomendacoes_notas.html` |

**Arquivo auxiliar:** `aliases.py` — mapeia variações de nome dos jogadores entre o CSV e o `players.json`.

## Páginas publicadas

| URL (Netlify) | Arquivo |
|---|---|
| `/` ou `/dashboard` | `index.html` / `dashboard_pixotada_2026.html` |
| `/ranking` | `ranking_modelos_ultimas4.html` |
| `/efeito` | `efeito_jogadores.html` |
| `/sugestao-notas` | `sugestao_novas_notas.html` |
| `/detalhe-notas` | `detalhe_recomendacoes_notas.html` |
| `/raio-x` | `raio_x_jogador.html` |
| `/ranking-geral` | `ranking_geral_jogadores.html` |

## Deploy

- **GitHub Pages**: automático via `.github/workflows/pages.yml` ao fazer push na branch `main`
- **Netlify**: configurado em `netlify.toml` com `publish = "."` (raiz do repositório)
- Ambos os destinos servem os HTMLs pré-gerados diretamente, sem build

## Dependências Python

- `pandas`
- `plotly`
- `json`, `re`, `unicodedata` (stdlib)

Instale com `pip install -r requirements.txt`.

## Pontos de atenção

- `aliases.py` é crítico: sem ele, jogadores com nomes variantes aparecem duplicados nas análises.
- Os CSVs auxiliares de saída são exportados para `output/` (gitignored). O arquivo de entrada do WhatsApp (`CHAT_FILE`) ainda é lido de `C:\Users\compesa\Desktop\pixotada_2026_dashboard`.
