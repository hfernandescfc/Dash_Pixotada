# Dash Pixotada

Dashboard e analises da Pixotada 2026.

## Publicacao

O projeto pode ser publicado como site estatico no Netlify sem etapa de build.

Fluxo mais simples:

1. Atualize os HTMLs rodando os scripts Python localmente.
2. Suba este repositorio no Netlify.
3. Use a raiz do repositorio como publish directory.

Os scripts publicam os HTMLs diretamente na raiz do repositorio.
Os CSVs e arquivos auxiliares continuam sendo exportados em `C:\Users\compesa\Desktop\pixotada_2026_dashboard`.

O arquivo `netlify.toml` configura:

- `publish = "."`
- atalhos para `/dashboard`, `/ranking`, `/efeito`, `/sugestao-notas` e `/detalhe-notas`

Tambem da para fazer deploy manual por drag-and-drop da pasta do projeto, desde que os HTMLs ja estejam atualizados.

## Conteudo

- `index.html`: dashboard principal
- `dashboard_pixotada_2026.html`: dashboard principal em rota explicita
- `ranking_modelos_ultimas4.html`: comparacao dos modelos de pontuacao
- `efeito_jogadores.html`: analise de efeito ajustado dos jogadores
- `sugestao_novas_notas.html`: sugestao de novas notas a partir do `players.json`
- `detalhe_recomendacoes_notas.html`: detalhamento partida a partida das recomendacoes

## Dados usados

- `data/SCOUTS PIXOTADA 2026 - BASE.csv`
- `data/players.json`

## Scripts

- `pixotada_dashboard.py`
- `pixotada_scores.py`
- `pixotada_effect_analysis.py`
- `rating_recommendations.py`
- `recommendation_details_page.py`

## Observacao

Os HTMLs ja estao gerados e podem ser abertos diretamente no navegador.
