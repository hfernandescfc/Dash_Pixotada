from pathlib import Path

import pandas as pd

from pixotada_dashboard import BASE_DIR, OUTPUT_DIR, PUBLIC_DIR, POSITION_LABELS, load_data


RECENCY_WEIGHTS = {1: 0.4, 2: 0.3, 3: 0.2, 4: 0.1}

MODELS = {
    "conservador": {
        "class_points": {"Campeao": 5, "Segundo": 3, "Terceiro": 1, "Lanterna": 0},
        "weights": {
            "classificacao": 0.55,
            "participacoes": 0.20,
            "gols_time": 0.10,
            "gols_sofridos": 0.10,
            "clean_sheet": 0.05,
        },
        "participation_mode": "tier_3",
        "descricao": "Maior peso para classificacao e solidez coletiva.",
    },
    "equilibrado": {
        "class_points": {"Campeao": 5, "Segundo": 3, "Terceiro": 2, "Lanterna": 0},
        "weights": {
            "classificacao": 0.40,
            "participacoes": 0.25,
            "gols_time": 0.15,
            "gols_sofridos": 0.10,
            "clean_sheet": 0.10,
        },
        "participation_mode": "cap_4",
        "descricao": "Equilibra classificacao, producao ofensiva e consistencia defensiva.",
    },
    "agressivo": {
        "class_points": {"Campeao": 4, "Segundo": 3, "Terceiro": 2, "Lanterna": 1},
        "weights": {
            "classificacao": 0.25,
            "participacoes": 0.35,
            "gols_time": 0.20,
            "gols_sofridos": 0.10,
            "clean_sheet": 0.10,
        },
        "participation_mode": "cap_5",
        "descricao": "Maior peso para protagonismo e producao coletiva de gols.",
    },
}

GENERAL_RANKING_WEIGHTS = {
    "gols_pg": 0.25,
    "assist_pg": 0.20,
    "gols_time_pg": 0.15,
    "gols_sofridos_pg": 0.15,
    "sg_pg": 0.10,
    "delta_points_pg": 0.15,
}
GENERAL_RANKING_REVERSE_METRICS = {"gols_sofridos_pg"}
CURRENT_MONTH = "2026-03"
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
    recent.attrs = {}
    return recent


def participation_points(value: int, mode: str) -> int:
    if mode == "tier_3":
        return min(int(value), 3)
    if mode == "cap_4":
        return min(int(value), 4)
    if mode == "cap_5":
        return min(int(value), 5)
    raise ValueError(f"Modo de participacao desconhecido: {mode}")


def team_goals_points(value: int) -> int:
    return min(int(value), 5)


def goals_conceded_points(value: int) -> int:
    return max(0, 5 - int(value))


def clean_sheet_points(value: int) -> int:
    return 2 if int(value) > 0 else 0


def score_percentile(series: pd.Series, reverse: bool = False) -> pd.Series:
    base = -series if reverse else series
    return base.rank(pct=True, ascending=True) * 100


def build_general_ranking(frame: pd.DataFrame, label: str, min_games: int) -> pd.DataFrame:
    ranking = (
        frame.groupby("Jogadores", as_index=False)
        .agg(
            Jogos=("Data", "count"),
            Gols_pg=("Gol", "mean"),
            Assist_pg=("Assist", "mean"),
            GolsTime_pg=("Gols_time", "mean"),
            GolsSofridos_pg=("Gols_sofridos", "mean"),
            JogosSemSofrer_pg=("Jogos_sem_sofrer", "mean"),
            Delta_points_pg=("Delta_points", "mean"),
        )
        .loc[lambda x: x["Jogos"] >= min_games]
        .copy()
    )
    if ranking.empty:
        return ranking

    metric_specs = [
        ("Gols_pg", "gols_pg"),
        ("Assist_pg", "assist_pg"),
        ("GolsTime_pg", "gols_time_pg"),
        ("GolsSofridos_pg", "gols_sofridos_pg"),
        ("JogosSemSofrer_pg", "sg_pg"),
        ("Delta_points_pg", "delta_points_pg"),
    ]

    for source_col, weight_key in metric_specs:
        reverse = weight_key in GENERAL_RANKING_REVERSE_METRICS
        ranking[f"Score_{weight_key}"] = score_percentile(ranking[source_col], reverse=reverse)
        ranking[f"Peso_{weight_key}"] = GENERAL_RANKING_WEIGHTS[weight_key]
        ranking[f"Contrib_{weight_key}"] = ranking[f"Score_{weight_key}"] * GENERAL_RANKING_WEIGHTS[weight_key]

    contrib_cols = [f"Contrib_{weight_key}" for _, weight_key in metric_specs]
    ranking["Score_geral"] = ranking[contrib_cols].sum(axis=1)
    ranking["Recorte"] = label
    ranking["Amostra_minima"] = min_games
    ranking = ranking.sort_values(
        ["Score_geral", "Gols_pg", "Assist_pg", "Delta_points_pg", "Jogadores"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)
    ranking["Posicao"] = ranking.index + 1
    return ranking[
        [
            "Recorte",
            "Posicao",
            "Jogadores",
            "Score_geral",
            "Jogos",
            "Gols_pg",
            "Assist_pg",
            "GolsTime_pg",
            "GolsSofridos_pg",
            "JogosSemSofrer_pg",
            "Delta_points_pg",
            "Score_gols_pg",
            "Score_assist_pg",
            "Score_gols_time_pg",
            "Score_gols_sofridos_pg",
            "Score_sg_pg",
            "Score_delta_points_pg",
            "Amostra_minima",
        ]
    ]


def build_general_ranking_context(df: pd.DataFrame) -> pd.DataFrame:
    from rating_recommendations import build_pre_match_expected_results

    data = build_pre_match_expected_results(df, df).rename(columns={"forca_observada": "forca_recente"})
    data["class_points"] = data["classificacao_norm"].map(CLASS_POINTS)
    data["class_rank"] = data["classificacao_norm"].map(CLASS_RANK)
    data["team_delta_points"] = data["delta_points"]

    appearance_rows = []
    for (match_date, team), team_df in data.groupby(["Data", "Time"]):
        team_players = team_df["Jogadores"].tolist()
        for row in team_df.itertuples():
            appearance_rows.append(
                {
                    "Data": row.Data,
                    "Time": row.Time,
                    "Jogadores": row.Jogadores,
                    "Gol": row.Gol,
                    "Assist": row.Assist,
                    "Participacoes": row.participacoes,
                    "Classificacao": row.classificacao_norm,
                    "Class_points": row.class_points,
                    "Class_rank": row.class_rank,
                    "Expected_points": row.expected_points,
                    "Delta_points": row.team_delta_points,
                    "Gols_time": row.gols_time,
                    "Gols_sofridos": row.gols_sofridos,
                    "Jogos_sem_sofrer": row.jogos_sem_sofrer,
                    "Companheiros": ", ".join(player for player in team_players if player != row.Jogadores),
                }
            )

    return pd.DataFrame(appearance_rows)


def build_general_ranking_html(historic: pd.DataFrame, monthly: pd.DataFrame) -> str:
    historic_top = historic.head(20).copy()
    monthly_top = monthly.head(20).copy()
    for table in [historic_top, monthly_top]:
        for column in table.columns:
            if table[column].dtype.kind in {"f"}:
                table[column] = table[column].map(lambda value: f"{value:.2f}")
    historic_html = historic_top.to_html(index=False, classes="table sortable-table", border=0)
    monthly_html = monthly_top.to_html(index=False, classes="table sortable-table", border=0)

    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Ranking Geral Pixotada 2026</title>
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
      <h1>Ranking Geral dos Jogadores</h1>
      <p>Ranking orientado por medias por pelada, sem duplicar participacoes com gols e assistencias.</p>
      <p>Pesos: 25% gols, 20% assistencias, 15% gols do time, 15% gols sofridos invertidos, 10% jogos sem sofrer gols e 15% classificacao final x esperada.</p>
      <div class="nav">
        <a href="dashboard_pixotada_2026.html">Dashboard</a>
        <a href="ranking_modelos_ultimas4.html">Modelos de pontuacao</a>
        <a href="ranking_geral_jogadores.html">Ranking geral</a>
        <a href="efeito_jogadores.html">Efeito dos jogadores</a>
        <a href="sugestao_novas_notas.html">Sugestao de notas</a>
      </div>
    </section>
    <section class="grid">
      <section class="card">
        <h2>Historico geral</h2>
        <p>Filtro minimo: 4 jogos.</p>
        <div class="table-wrap">{historic_html}</div>
      </section>
      <section class="card">
        <h2>Mes corrente</h2>
        <p>Recorte: {CURRENT_MONTH}. Filtro minimo: 2 jogos.</p>
        <div class="table-wrap">{monthly_html}</div>
      </section>
    </section>
  </main>
{TABLE_UI_SCRIPT}
</body>
</html>
"""


def score_model(df: pd.DataFrame, model_name: str, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    scored = df.copy()
    scored.attrs = {}
    scored["Pontos_classificacao"] = scored["classificacao_norm"].map(config["class_points"]).fillna(0)
    scored["Pontos_participacao"] = scored["participacoes"].map(lambda x: participation_points(x, config["participation_mode"]))
    scored["Pontos_gols_time"] = scored["gols_time"].map(team_goals_points)
    scored["Pontos_gols_sofridos"] = scored["gols_sofridos"].map(goals_conceded_points)
    scored["Pontos_clean_sheet"] = scored["jogos_sem_sofrer"].map(clean_sheet_points)
    scored["Nota_jogo"] = (
        scored["Pontos_classificacao"] * config["weights"]["classificacao"]
        + scored["Pontos_participacao"] * config["weights"]["participacoes"]
        + scored["Pontos_gols_time"] * config["weights"]["gols_time"]
        + scored["Pontos_gols_sofridos"] * config["weights"]["gols_sofridos"]
        + scored["Pontos_clean_sheet"] * config["weights"]["clean_sheet"]
    )
    scored["Nota_ponderada"] = scored["Nota_jogo"] * scored["Peso_recencia"]
    scored["Modelo"] = model_name

    ranking = (
        scored.groupby("Jogadores", as_index=False)
        .agg(
            Nota_final=("Nota_ponderada", "sum"),
            Jogos_considerados=("Recencia", "count"),
            Participacoes_ult4=("participacoes", "sum"),
            Gols_time_ult4=("gols_time", "sum"),
            Gols_sofridos_ult4=("gols_sofridos", "sum"),
            Clean_sheets_ult4=("jogos_sem_sofrer", "sum"),
            Media_classificacao=("Pontos_classificacao", "mean"),
        )
        .sort_values(
            ["Nota_final", "Participacoes_ult4", "Gols_time_ult4", "Media_classificacao", "Jogadores"],
            ascending=[False, False, False, False, True],
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
            "Gols_time_ult4",
            "Gols_sofridos_ult4",
            "Clean_sheets_ult4",
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
        top10_html = top10.to_html(index=False, classes="table sortable-table", border=0)
        sections.append(
            f"""
            <section class="card">
              <h2>Top 10: {model_name.title()}</h2>
              <p>{MODELS[model_name]["descricao"]}</p>
              <div class="table-wrap">{top10_html}</div>
            </section>
            """
        )

    compare_top = comparison.head(15).copy()
    for column in [col for col in compare_top.columns if col.startswith("Nota_") or col == "Media_notas"]:
        compare_top[column] = compare_top[column].map(lambda x: f"{x:.2f}")
    compare_html = compare_top.to_html(index=False, classes="table sortable-table", border=0)

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
      <div class="table-wrap">{compare_html}</div>
    </section>
    <section class="grid">
      {''.join(sections)}
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
    recent = last4_games(df)

    rankings = {}
    details = []
    for model_name, config in MODELS.items():
        ranking, scored = score_model(recent, model_name, config)
        rankings[model_name] = ranking
        ranking.attrs = {}
        scored.attrs = {}
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

    appearance_df = build_general_ranking_context(df)
    general_historic = build_general_ranking(appearance_df, "Historico", min_games=4)
    general_month = build_general_ranking(
        appearance_df.loc[appearance_df["Data"].dt.strftime("%Y-%m") == CURRENT_MONTH].copy(),
        f"Mes {CURRENT_MONTH}",
        min_games=2,
    )
    general_historic.to_csv(OUTPUT_DIR / "ranking_geral_historico.csv", index=False, encoding="utf-8-sig")
    general_month.to_csv(OUTPUT_DIR / "ranking_geral_mes_corrente.csv", index=False, encoding="utf-8-sig")

    general_html = build_general_ranking_html(general_historic, general_month)
    (OUTPUT_DIR / "ranking_geral_jogadores.html").write_text(general_html, encoding="utf-8")
    (BASE_DIR / "ranking_geral_jogadores.html").write_text(general_html, encoding="utf-8")
    (PUBLIC_DIR / "ranking_geral_jogadores.html").write_text(general_html, encoding="utf-8")

    print(f"Arquivos gerados em: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
