from itertools import combinations
from pathlib import Path

import pandas as pd

from pixotada_dashboard import OUTPUT_DIR, PUBLIC_DIR, load_data
from pixotada_scores import last4_games, score_model, MODELS


BASE_DIR = Path(r"c:\Users\compesa\Desktop")

CLASS_POINTS = {
    "Campeao": 4,
    "Segundo": 3,
    "Terceiro": 2,
    "Lanterna": 1,
}

CLASS_RANK = {
    "Campeao": 1,
    "Segundo": 2,
    "Terceiro": 3,
    "Lanterna": 4,
}


def build_player_strength(df: pd.DataFrame) -> pd.DataFrame:
    recent = last4_games(df)
    ranking, _ = score_model(recent, "equilibrado", MODELS["equilibrado"])
    strength = ranking[["Jogadores", "Nota_final", "Jogos_considerados"]].rename(
        columns={"Nota_final": "forca_recente", "Jogos_considerados": "jogos_ult4"}
    )
    return strength


def build_team_context(df: pd.DataFrame, strength: pd.DataFrame) -> pd.DataFrame:
    data = df.merge(strength, on="Jogadores", how="left")
    data["forca_recente"] = data["forca_recente"].fillna(0)
    data["class_points"] = data["classificacao_norm"].map(CLASS_POINTS)
    data["class_rank"] = data["classificacao_norm"].map(CLASS_RANK)

    team_strength = (
        data.groupby(["Data", "Time"], as_index=False)
        .agg(
            team_strength=("forca_recente", "sum"),
            team_avg_strength=("forca_recente", "mean"),
            team_actual_points=("class_points", "first"),
            team_actual_rank=("class_rank", "first"),
            team_players=("Jogadores", "count"),
        )
    )
    team_strength["expected_rank"] = team_strength.groupby("Data")["team_strength"].rank(method="dense", ascending=False)
    expected_points_map = {1.0: 4, 2.0: 3, 3.0: 2, 4.0: 1}
    team_strength["expected_points"] = team_strength["expected_rank"].map(expected_points_map).fillna(1)
    team_strength["team_delta_points"] = team_strength["team_actual_points"] - team_strength["expected_points"]
    team_strength["team_delta_rank"] = team_strength["expected_rank"] - team_strength["team_actual_rank"]

    data = data.merge(
        team_strength[
            [
                "Data",
                "Time",
                "team_strength",
                "team_avg_strength",
                "expected_rank",
                "expected_points",
                "team_delta_points",
                "team_delta_rank",
            ]
        ],
        on=["Data", "Time"],
        how="left",
    )

    appearance_rows = []
    for (match_date, team), team_df in data.groupby(["Data", "Time"]):
        same_date = data[data["Data"] == match_date]
        opponents_df = same_date[same_date["Time"] != team]
        team_players = team_df["Jogadores"].tolist()
        for row in team_df.itertuples():
            teammate_strengths = team_df.loc[team_df["Jogadores"] != row.Jogadores, "forca_recente"]
            appearance_rows.append(
                {
                    "Data": row.Data,
                    "Data_fmt": row.Data.strftime("%d/%m/%Y"),
                    "Time": row.Time,
                    "Jogadores": row.Jogadores,
                    "Gol": row.Gol,
                    "Assist": row.Assist,
                    "Participacoes": row.participacoes,
                    "Classificacao": row.classificacao_norm,
                    "Class_points": row.class_points,
                    "Class_rank": row.class_rank,
                    "Forca_jogador": row.forca_recente,
                    "Forca_time_total": row.team_strength,
                    "Forca_time_sem_jogador": row.team_strength - row.forca_recente,
                    "Forca_media_companheiros": teammate_strengths.mean() if not teammate_strengths.empty else 0,
                    "Forca_media_adversarios": opponents_df["forca_recente"].mean() if not opponents_df.empty else 0,
                    "Forca_total_adversarios": opponents_df["forca_recente"].sum(),
                    "Expected_rank": row.expected_rank,
                    "Expected_points": row.expected_points,
                    "Delta_points": row.team_delta_points,
                    "Delta_rank": row.team_delta_rank,
                    "Companheiros": ", ".join(player for player in team_players if player != row.Jogadores),
                }
            )

    return pd.DataFrame(appearance_rows)


def classify_confidence(games: int) -> str:
    if games >= 8:
        return "Alta"
    if games >= 5:
        return "Media"
    if games >= 3:
        return "Baixa"
    return "Muito baixa"


def build_player_impact(appearance_df: pd.DataFrame) -> pd.DataFrame:
    impact = (
        appearance_df.groupby("Jogadores", as_index=False)
        .agg(
            Jogos=("Data", "count"),
            Forca_recente=("Forca_jogador", "max"),
            Classificacao_media=("Class_points", "mean"),
            Expected_points_medios=("Expected_points", "mean"),
            Impacto_bruto=("Class_points", "mean"),
            Impacto_ajustado=("Delta_points", "mean"),
            Impacto_rank_ajustado=("Delta_rank", "mean"),
            Participacoes_media=("Participacoes", "mean"),
            Forca_media_companheiros=("Forca_media_companheiros", "mean"),
            Forca_media_adversarios=("Forca_media_adversarios", "mean"),
        )
        .sort_values(["Impacto_ajustado", "Impacto_bruto", "Jogadores"], ascending=[False, False, True])
        .reset_index(drop=True)
    )
    impact["Confianca"] = impact["Jogos"].map(classify_confidence)
    impact["Leitura"] = impact["Impacto_ajustado"].map(
        lambda x: "Impacto positivo provavel"
        if x >= 0.35
        else "Impacto negativo provavel"
        if x <= -0.35
        else "Neutro ou inconclusivo"
    )
    return impact


def build_pair_synergy(appearance_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (match_date, team), team_df in appearance_df.groupby(["Data", "Time"]):
        players = sorted(team_df["Jogadores"].tolist())
        delta_points = team_df["Delta_points"].iloc[0]
        class_points = team_df["Class_points"].iloc[0]
        for player_a, player_b in combinations(players, 2):
            rows.append(
                {
                    "Jogador_A": player_a,
                    "Jogador_B": player_b,
                    "Data": match_date,
                    "Delta_points": delta_points,
                    "Class_points": class_points,
                }
            )
    pair_df = pd.DataFrame(rows)
    if pair_df.empty:
        return pair_df

    pair_summary = (
        pair_df.groupby(["Jogador_A", "Jogador_B"], as_index=False)
        .agg(
            Jogos_juntos=("Data", "count"),
            Sinergia_media=("Delta_points", "mean"),
            Classificacao_media=("Class_points", "mean"),
        )
        .sort_values(["Sinergia_media", "Jogos_juntos"], ascending=[False, False])
    )
    return pair_summary


def build_html(impact_df: pd.DataFrame, pair_df: pd.DataFrame) -> str:
    filtered_impact = impact_df.loc[impact_df["Jogos"] >= 4].copy()
    top_positive = filtered_impact.head(15).copy()
    top_negative = filtered_impact.sort_values(["Impacto_ajustado", "Jogadores"], ascending=[True, True]).head(15).copy()
    pair_positive = pair_df.loc[pair_df["Jogos_juntos"] >= 2].head(15).copy()
    pair_negative = (
        pair_df.loc[pair_df["Jogos_juntos"] >= 2]
        .sort_values(["Sinergia_media", "Jogos_juntos"], ascending=[True, False])
        .head(15)
        .copy()
    )

    for table in [top_positive, top_negative, pair_positive, pair_negative]:
        for column in table.columns:
            if table[column].dtype.kind in {"f"}:
                table[column] = table[column].map(lambda x: f"{x:.2f}")

    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Analise de Efeito por Jogador</title>
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
      <h1>Analise de Efeito dos Jogadores</h1>
      <p>Impacto bruto = classificacao media das equipes com o jogador.</p>
      <p>Impacto ajustado = resultado real menos resultado esperado a partir da forca recente do elenco do time em cada data.</p>
      <p>Esta versao destaca apenas jogadores com pelo menos 4 jogos.</p>
      <div class="nav">
        <a href="dashboard_pixotada_2026.html">Dashboard</a>
        <a href="ranking_modelos_ultimas4.html">Modelos de pontuação</a>
        <a href="efeito_jogadores.html">Efeito dos jogadores</a>
        <a href="sugestao_novas_notas.html">Sugestão de notas</a>
        <a href="detalhe_recomendacoes_notas.html">Detalhe das recomendações</a>
      </div>
    </section>
    <section class="grid">
      <section class="card">
        <h2>Top 15 impacto ajustado positivo</h2>
        {top_positive.to_html(index=False, classes="table", border=0)}
      </section>
      <section class="card">
        <h2>Top 15 impacto ajustado negativo</h2>
        {top_negative.to_html(index=False, classes="table", border=0)}
      </section>
      <section class="card">
        <h2>Duplas com sinergia positiva</h2>
        {pair_positive.to_html(index=False, classes="table", border=0)}
      </section>
      <section class="card">
        <h2>Duplas com sinergia negativa</h2>
        {pair_negative.to_html(index=False, classes="table", border=0)}
      </section>
    </section>
  </main>
</body>
</html>
"""


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    PUBLIC_DIR.mkdir(exist_ok=True)

    df = load_data()
    strength = build_player_strength(df)
    appearance_df = build_team_context(df, strength)
    impact_df = build_player_impact(appearance_df)
    impact_df_min4 = impact_df.loc[impact_df["Jogos"] >= 4].copy()
    pair_df = build_pair_synergy(appearance_df)

    appearance_df.to_csv(OUTPUT_DIR / "efeito_jogador_aparicoes.csv", index=False, encoding="utf-8-sig")
    impact_df.to_csv(OUTPUT_DIR / "efeito_jogador_resumo.csv", index=False, encoding="utf-8-sig")
    impact_df_min4.to_csv(OUTPUT_DIR / "efeito_jogador_resumo_min4.csv", index=False, encoding="utf-8-sig")
    pair_df.to_csv(OUTPUT_DIR / "efeito_duplas_sinergia.csv", index=False, encoding="utf-8-sig")

    html = build_html(impact_df, pair_df)
    (OUTPUT_DIR / "efeito_jogadores.html").write_text(html, encoding="utf-8")
    (BASE_DIR / "efeito_jogadores.html").write_text(html, encoding="utf-8")
    (PUBLIC_DIR / "efeito_jogadores.html").write_text(html, encoding="utf-8")

    print(f"Arquivos gerados em: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
