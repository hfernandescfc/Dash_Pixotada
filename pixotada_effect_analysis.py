from itertools import combinations
from pathlib import Path

import pandas as pd

from pixotada_dashboard import OUTPUT_DIR, PUBLIC_DIR, load_data
from rating_recommendations import build_pre_match_expected_results


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

TABLE_UI_CSS = """
    .table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    .table-wrap {
      max-height: 520px;
      overflow: auto;
      border: 1px solid #eadfc9;
      border-radius: 16px;
      background: #fff;
    }
    .table th, .table td {
      border-bottom: 1px solid #eadfc9;
      padding: 10px 8px;
      text-align: left;
    }
    .table th {
      background: #f6efe2;
      position: sticky;
      top: 0;
      z-index: 2;
    }
    .sortable-table th {
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
    }
    .sortable-table th::after {
      content: "  ↕";
      color: #8a7d66;
      font-size: 12px;
    }
"""

TABLE_UI_SCRIPT = """
  <script>
    function parseSortableValue(rawValue) {
      const value = String(rawValue ?? "").trim();
      const normalized = value.replace(/\\./g, "").replace(",", ".");
      const numeric = Number(normalized);
      if (!Number.isNaN(numeric) && normalized !== "") {
        return numeric;
      }
      return value.toLocaleLowerCase("pt-BR");
    }

    function sortTableByColumn(table, columnIndex, direction) {
      const tbody = table.tBodies[0];
      if (!tbody) return;
      const rows = Array.from(tbody.rows);
      rows.sort((rowA, rowB) => {
        const valueA = parseSortableValue(rowA.cells[columnIndex]?.innerText);
        const valueB = parseSortableValue(rowB.cells[columnIndex]?.innerText);
        if (typeof valueA === "number" && typeof valueB === "number") {
          return direction === "asc" ? valueA - valueB : valueB - valueA;
        }
        return direction === "asc"
          ? String(valueA).localeCompare(String(valueB), "pt-BR")
          : String(valueB).localeCompare(String(valueA), "pt-BR");
      });
      rows.forEach(row => tbody.appendChild(row));
    }

    document.querySelectorAll(".sortable-table").forEach(table => {
      const headers = table.tHead ? Array.from(table.tHead.rows[0].cells) : [];
      headers.forEach((header, columnIndex) => {
        header.dataset.sortDirection = "desc";
        header.addEventListener("click", () => {
          const currentDirection = header.dataset.sortDirection === "asc" ? "desc" : "asc";
          headers.forEach(cell => cell.dataset.sortDirection = "");
          header.dataset.sortDirection = currentDirection;
          sortTableByColumn(table, columnIndex, currentDirection);
        });
      });
    });
  </script>
"""

def build_team_context(df: pd.DataFrame) -> pd.DataFrame:
    data = build_pre_match_expected_results(df, df).rename(columns={"forca_observada": "forca_recente"})
    data["class_points"] = data["classificacao_norm"].map(CLASS_POINTS)
    data["class_rank"] = data["classificacao_norm"].map(CLASS_RANK)
    data["team_delta_points"] = data["delta_points"]
    data["team_actual_rank"] = data["class_rank"]
    data["team_avg_strength"] = data.groupby(["Data", "Time"])["forca_recente"].transform("mean")
    data["team_delta_rank"] = data["expected_points"].map({4: 1, 3: 2, 2: 3, 1: 4}) - data["team_actual_rank"]

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
                    "Expected_rank": {4: 1, 3: 2, 2: 3, 1: 4}.get(row.expected_points, 4),
                    "Expected_points": row.expected_points,
                    "Delta_points": row.team_delta_points,
                    "Gols_time": row.gols_time,
                    "Gols_sofridos": row.gols_sofridos,
                    "Jogos_sem_sofrer": row.jogos_sem_sofrer,
                    "Expected_gols_time": row.expected_gols_time,
                    "Expected_gols_sofridos": row.expected_gols_sofridos,
                    "Expected_jogos_sem_sofrer": row.expected_jogos_sem_sofrer,
                    "Delta_gols_time": row.delta_gols_time,
                    "Delta_gols_sofridos": row.delta_gols_sofridos,
                    "Delta_jogos_sem_sofrer": row.delta_jogos_sem_sofrer,
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
            Gols_time_medio=("Gols_time", "mean"),
            Gols_sofridos_medio=("Gols_sofridos", "mean"),
            Jogos_sem_sofrer_medio=("Jogos_sem_sofrer", "mean"),
            Impacto_gols_time=("Delta_gols_time", "mean"),
            Impacto_gols_sofridos=("Delta_gols_sofridos", "mean"),
            Impacto_clean_sheet=("Delta_jogos_sem_sofrer", "mean"),
            Forca_media_companheiros=("Forca_media_companheiros", "mean"),
            Forca_media_adversarios=("Forca_media_adversarios", "mean"),
        )
        .sort_values(["Impacto_ajustado", "Impacto_gols_time", "Impacto_gols_sofridos", "Jogadores"], ascending=[False, False, False, True])
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
                    "Gols_time": team_df["Gols_time"].iloc[0],
                    "Gols_sofridos": team_df["Gols_sofridos"].iloc[0],
                    "Jogos_sem_sofrer": team_df["Jogos_sem_sofrer"].iloc[0],
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
            Gols_time_juntos=("Gols_time", "mean"),
            Gols_sofridos_juntos=("Gols_sofridos", "mean"),
            Clean_sheet_juntos=("Jogos_sem_sofrer", "mean"),
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
    top_positive_html = top_positive.to_html(index=False, classes="table sortable-table", border=0)
    top_negative_html = top_negative.to_html(index=False, classes="table sortable-table", border=0)
    pair_positive_html = pair_positive.to_html(index=False, classes="table sortable-table", border=0)
    pair_negative_html = pair_negative.to_html(index=False, classes="table sortable-table", border=0)

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
{TABLE_UI_CSS}
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
        <div class="table-wrap">{top_positive_html}</div>
      </section>
      <section class="card">
        <h2>Top 15 impacto ajustado negativo</h2>
        <div class="table-wrap">{top_negative_html}</div>
      </section>
      <section class="card">
        <h2>Duplas com sinergia positiva</h2>
        <div class="table-wrap">{pair_positive_html}</div>
      </section>
      <section class="card">
        <h2>Duplas com sinergia negativa</h2>
        <div class="table-wrap">{pair_negative_html}</div>
      </section>
    </section>
  </main>
{TABLE_UI_SCRIPT}
</body>
</html>
"""


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    PUBLIC_DIR.mkdir(exist_ok=True)

    df = load_data()
    appearance_df = build_team_context(df)
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
