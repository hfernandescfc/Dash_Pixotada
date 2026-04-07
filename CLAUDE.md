# CLAUDE.md — Dash Pixotada

## Contexto do projeto

Acompanhamento semanal de uma pelada de futebol entre amigos. Os scouts são registrados manualmente no CSV após cada pelada. Os scripts Python são executados localmente para regenerar os HTMLs, que são então publicados via git push.

## Fluxo semanal

### Passo 1 — Scouts (CSV)
Adicionar as linhas da pelada em `data/SCOUTS PIXOTADA 2026 - BASE.csv` com gols, assists, cartões e classificação de cada jogador.

### Passo 2 — Resultados dos jogos
Abrir `pelada_results.py` e adicionar uma entrada no final do dicionário `MANUAL_PELADA_RESULTS`:

```python
"DD/MM/YYYY": {
    "team_map": {"label_time1": 1, "label_time2": 2, "label_time3": 3, "label_time4": 4},
    "matches": [
        ("round_robin", "A", gols_A, "B", gols_B),
        # ... 6 jogos de round robin (cada time joga contra os outros 3) ...
        ("third",       "A", gols_A, "B", gols_B),
        ("final",       "A", gols_A, "B", gols_B),
    ],
},
```

> Os números de time (1–4) estão na coluna `Time` do CSV para aquela data.
> O `label` é o nome do capitão/representante do time, em minúsculas e sem acentos.

### Passo 3 — Regenerar todas as páginas
```bash
python atualizar.py
```

### Passo 4 — Deploy
```bash
git add data/ pelada_results.py *.html
git commit -m "Add pelada DD/MM/YYYY"
git push
```

**Não há etapa de build no servidor.** Os HTMLs já são gerados localmente antes do push.

## Dados

| Arquivo | Descrição |
|---|---|
| `data/SCOUTS PIXOTADA 2026 - BASE.csv` | Scouts por partida: gols, assistências, cartões, classificação dos times |
| `data/players.json` | Cadastro de jogadores com nota (1–6), intensidade e status de mensalista |
| `pelada_results.py` | Resultados dos jogos (gols por partida) — editado semanalmente |

Colunas do CSV: `Data, Time, Jogadores, Gol, Assist, Amarelo, Red, Pontos, Pixotada, Desarme, Classificação`

## Scripts Python

| Script | Função | Gera |
|---|---|---|
| `atualizar.py` | **Ponto de entrada semanal** — executa todos os scripts abaixo na ordem correta | todos os HTMLs |
| `pixotada_dashboard.py` | Dashboard principal com gráficos interativos | `index.html`, `dashboard_pixotada_2026.html` |
| `pixotada_scores.py` | Rankings por 3 modelos de pontuação + Raio X individual + Premiação mensal | `ranking_geral_jogadores.html`, `ranking_modelos_ultimas4.html`, `raio_x_jogador.html`, `premiacao_mensal.html` |
| `pixotada_effect_analysis.py` | Efeito ajustado por jogador e sinergias entre duplas | `efeito_jogadores.html` |
| `rating_recommendations.py` | Sugestão de ajuste de notas com base na forma recente | `sugestao_novas_notas.html` |
| `recommendation_details_page.py` | Detalhamento partida a partida das recomendações | `detalhe_recomendacoes_notas.html` |

**Arquivos auxiliares:**
- `aliases.py` — mapeia variações de nome dos jogadores entre o CSV e o `players.json`.
- `pelada_results.py` — resultados manuais dos jogos; importado por `pixotada_dashboard.py`.

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
- `pelada_results.py` é o único arquivo a editar para registrar resultados de jogos — não editar `pixotada_dashboard.py` para isso.
- Os CSVs auxiliares de saída são exportados para `output/` (gitignored).
