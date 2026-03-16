from pathlib import Path

import pandas as pd

from pixotada_dashboard import BASE_DIR, OUTPUT_DIR, PUBLIC_DIR, POSITION_LABELS, load_data


RECENCY_WEIGHTS = {1: 0.4, 2: 0.3, 3: 0.2, 4: 0.1}

MODELS = {
    "conservador": {
        "class_points": {"Campeao": 5, "Segundo": 3, "Terceiro": 1, "Lanterna": 0},
        "weights": {"classificacao": 0.75, "participacoes": 0.25},
        "participation_mode": "tier_3",
        "descricao": "Maior peso para o resultado coletivo.",
    },
    "equilibrado": {
        "class_points": {"Campeao": 5, "Segundo": 3, "Terceiro": 2, "Lanterna": 0},
        "weights": {"classificacao": 0.60, "participacoes": 0.40},
        "participation_mode": "cap_4",
        "descricao": "Equilibra classificacao e impacto ofensivo.",
    },
    "agressivo": {
        "class_points": {"Campeao": 4, "Segundo": 3, "Terceiro": 2, "Lanterna": 1},
        "weights": {"classificacao": 0.45, "participacoes": 0.55},
        "participation_mode": "cap_5",
        "descricao": "Maior peso para protagonismo ofensivo.",
    },
}


def last4_games(df: pd.DataFrame) -> pd.DataFrame:
    recent = (
        df.sort_values(["Jogadores", "Data"], ascending=[True, False])
        .assign(Recencia=lambda x: x.groupby("Jogadores").cumcount() + 1)
        .loc[lambda x: x["Recencia"] <= 4]
        .copy()
    )
    recent["Peso_recencia"] = recent["Recencia"].map(RECENCY_WEIGHTS)
    recent["Classificacao_label"] = recent["classificacao_norm"].map(POSITION_LABELS)
    recent["Data_fmt"] = recent["Data"].dt.strftime("%d/%m/%Y")
    return recent


def participation_points(value: int, mode: str) -> int:
    if mode == "tier_3":
        return min(int(value), 3)
    if mode == "cap_4":
        return min(int(value), 4)
    if mode == "cap_5":
        return min(int(value), 5)
    raise ValueError(f"Modo de participacao desconhecido: {mode}")


def score_model(df: pd.DataFrame, model_name: str, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    scored = df.copy()
    scored["Pontos_classificacao"] = scored["classificacao_norm"].map(config["class_points"]).fillna(0)
    scored["Pontos_participacao"] = scored["participacoes"].map(lambda x: participation_points(x, config["participation_mode"]))
    scored["Nota_jogo"] = (
        scored["Pontos_classificacao"] * config["weights"]["classificacao"]
        + scored["Pontos_participacao"] * config["weights"]["participacoes"]
    )
    scored["Nota_ponderada"] = scored["Nota_jogo"] * scored["Peso_recencia"]
    scored["Modelo"] = model_name

    ranking = (
        scored.groupby("Jogadores", as_index=False)
        .agg(
            Nota_final=("Nota_ponderada", "sum"),
            Jogos_considerados=("Recencia", "count"),
            Participacoes_ult4=("participacoes", "sum"),
            Media_classificacao=("Pontos_classificacao", "mean"),
        )
        .sort_values(
            ["Nota_final", "Participacoes_ult4", "Media_classificacao", "Jogadores"],
            ascending=[False, False, False, True],
        )
        .reset_index(drop=True)
    )
    ranking["Posicao"] = ranking.index + 1
    ranking["Modelo"] = model_name
    ranking["Descricao_modelo"] = config["descricao"]
    ranking["Amostra_reduzida"] = ranking["Jogos_considerados"] < 4
    ranking = ranking[
        [
            "Modelo",
            "Posicao",
            "Jogadores",
            "Nota_final",
            "Jogos_considerados",
            "Participacoes_ult4",
            "Media_classificacao",
            "Amostra_reduzida",
            "Descricao_modelo",
        ]
    ]
    return ranking, scored


def build_comparison(rankings: dict[str, pd.DataFrame]) -> pd.DataFrame:
    comparison = None
    for model_name, ranking in rankings.items():
        subset = ranking[["Jogadores", "Posicao", "Nota_final"]].rename(
            columns={
                "Posicao": f"Posicao_{model_name}",
                "Nota_final": f"Nota_{model_name}",
            }
        )
        if comparison is None:
            comparison = subset
        else:
            comparison = comparison.merge(subset, on="Jogadores", how="outer")

    comparison = comparison.fillna(0)
    comparison["Media_notas"] = comparison[[col for col in comparison.columns if col.startswith("Nota_")]].mean(axis=1)
    comparison = comparison.sort_values(
        ["Posicao_equilibrado", "Posicao_conservador", "Posicao_agressivo", "Jogadores"],
        ascending=[True, True, True, True],
    )
    return comparison


def build_html(rankings: dict[str, pd.DataFrame], comparison: pd.DataFrame) -> str:
    sections = []
    for model_name, ranking in rankings.items():
        top10 = ranking.head(10).copy()
        top10["Nota_final"] = top10["Nota_final"].map(lambda x: f"{x:.2f}")
        top10["Media_classificacao"] = top10["Media_classificacao"].map(lambda x: f"{x:.2f}")
        sections.append(
            f"""
            <section class="card">
              <h2>Top 10: {model_name.title()}</h2>
              <p>{MODELS[model_name]["descricao"]}</p>
              {top10.to_html(index=False, classes="table", border=0)}
            </section>
            """
        )

    compare_top = comparison.head(15).copy()
    for column in [col for col in compare_top.columns if col.startswith("Nota_") or col == "Media_notas"]:
        compare_top[column] = compare_top[column].map(lambda x: f"{x:.2f}")

    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Ranking Pixotada 2026 - Modelos</title>
  <style>
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      background: #f6f1e8;
      color: #1f2933;
    }}
    .wrap {{
      width: min(1280px, calc(100% - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    .hero, .card {{
      background: #fffdf8;
      border: 1px solid #dccfb8;
      border-radius: 20px;
      padding: 20px;
      box-shadow: 0 10px 24px rgba(66, 52, 23, 0.06);
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 20px;
      margin-top: 20px;
    }}
    .table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    .table th, .table td {{
      border-bottom: 1px solid #eadfc9;
      padding: 10px 8px;
      text-align: left;
    }}
    .table th {{
      background: #f6efe2;
    }}
    .nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }}
    .nav a {{
      text-decoration: none;
      color: #1f2933;
      background: rgba(255,255,255,0.78);
      border: 1px solid #dccfb8;
      padding: 10px 14px;
      border-radius: 999px;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Comparativo de Modelos de Pontuação</h1>
      <p>Base: últimas 4 participações de cada jogador, com pesos de recência 40% / 30% / 20% / 10%.</p>
      <p>O modelo equilibrado foi usado como referência principal para ordenar a tabela comparativa.</p>
      <div class="nav">
        <a href="dashboard_pixotada_2026.html">Dashboard</a>
        <a href="ranking_modelos_ultimas4.html">Modelos de pontuação</a>
        <a href="efeito_jogadores.html">Efeito dos jogadores</a>
        <a href="sugestao_novas_notas.html">Sugestão de notas</a>
        <a href="detalhe_recomendacoes_notas.html">Detalhe das recomendações</a>
      </div>
    </section>
    <section class="card" style="margin-top:20px;">
      <h2>Comparativo geral</h2>
      {compare_top.to_html(index=False, classes="table", border=0)}
    </section>
    <section class="grid">
      {''.join(sections)}
    </section>
  </main>
</body>
</html>
"""


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    PUBLIC_DIR.mkdir(exist_ok=True)

    df = load_data()
    recent = last4_games(df)

    rankings = {}
    details = []
    for model_name, config in MODELS.items():
        ranking, scored = score_model(recent, model_name, config)
        rankings[model_name] = ranking
        details.append(scored)
        ranking.to_csv(OUTPUT_DIR / f"ranking_{model_name}_ultimas4.csv", index=False, encoding="utf-8-sig")

    detail_df = pd.concat(details, ignore_index=True)
    detail_df.to_csv(OUTPUT_DIR / "ranking_modelos_detalhado.csv", index=False, encoding="utf-8-sig")

    comparison = build_comparison(rankings)
    comparison.to_csv(OUTPUT_DIR / "comparativo_modelos_ultimas4.csv", index=False, encoding="utf-8-sig")

    html = build_html(rankings, comparison)
    html_path = OUTPUT_DIR / "ranking_modelos_ultimas4.html"
    html_path.write_text(html, encoding="utf-8")
    (BASE_DIR / "ranking_modelos_ultimas4.html").write_text(html, encoding="utf-8")
    (PUBLIC_DIR / "ranking_modelos_ultimas4.html").write_text(html, encoding="utf-8")

    print(f"Arquivos gerados em: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
