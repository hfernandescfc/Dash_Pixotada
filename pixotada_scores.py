from pathlib import Path
import json

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from pixotada_dashboard import BASE_DIR, OUTPUT_DIR, PUBLIC_DIR, POSITION_LABELS, load_data


RECENCY_WEIGHTS = {1: 0.325, 2: 0.275, 3: 0.225, 4: 0.175}

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
            "classificacao": 0.30,
            "participacoes": 0.25,
            "gols_time": 0.15,
            "gols_sofridos": 0.15,
            "clean_sheet": 0.15,
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
    historic_top = historic.copy()
    monthly_top = monthly.copy()
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
      width: min(1400px, calc(100% - 32px));
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
      <h1>Ranking geral</h1>
      <p>Ranking orientado por medias por pelada, sem duplicar participacoes com gols e assistencias.</p>
      <p>Pesos: 25% gols, 20% assistencias, 15% gols do time, 15% gols sofridos invertidos, 10% jogos sem sofrer gols e 15% classificacao final x esperada.</p>
      <div class="nav">
        <a href="dashboard_pixotada_2026.html">Dashboard</a>
        <a href="ranking_geral_jogadores.html">Ranking geral</a>
        <a href="premiacao_mensal.html">Premiacao mensal</a>
        <a href="raio_x_jogador.html">Raio X do jogador</a>
        <a href="ranking_modelos_ultimas4.html">Modelos de pontuacao</a>
        <a href="efeito_jogadores.html">Efeito dos jogadores</a>
        <a href="sugestao_novas_notas.html">Sugestao de notas</a>
        <a href="detalhe_recomendacoes_notas.html">Detalhe das recomendacoes</a>
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


def classify_confidence(games: int) -> str:
    if games >= 8:
        return "Alta"
    if games >= 5:
        return "Media"
    if games >= 3:
        return "Baixa"
    return "Muito baixa"


def build_monthly_awards_payload(appearance_df: pd.DataFrame) -> dict[str, list[dict[str, object]]]:
    monthly_summary = (
        appearance_df.assign(Mes=lambda x: x["Data"].dt.strftime("%Y-%m"))
        .groupby(["Mes", "Jogadores"], as_index=False)
        .agg(
            gols=("Gol", "sum"),
            assistencias=("Assist", "sum"),
            participacoes=("Participacoes", "sum"),
            gols_time=("Gols_time", "sum"),
            sg=("Jogos_sem_sofrer", "sum"),
            jogos=("Data", "count"),
        )
        .sort_values(["Mes", "participacoes", "gols", "assistencias", "Jogadores"], ascending=[True, False, False, False, True])
    )

    payload: dict[str, list[dict[str, object]]] = {}
    for month_key, month_df in monthly_summary.groupby("Mes"):
        payload[month_key] = [
            {
                "jogador": row.Jogadores,
                "gols": int(row.gols),
                "assistencias": int(row.assistencias),
                "participacoes": int(row.participacoes),
                "gols_time": int(row.gols_time),
                "sg": int(row.sg),
                "jogos": int(row.jogos),
            }
            for row in month_df.itertuples()
        ]
    return payload


def build_monthly_awards_scores(appearance_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    payload: dict[str, dict[str, float]] = {}
    for month_key, month_df in appearance_df.groupby(appearance_df["Data"].dt.strftime("%Y-%m")):
        ranking = build_general_ranking(month_df.copy(), f"Mes {month_key}", min_games=1)
        payload[month_key] = {
            row.Jogadores: round(float(row.Score_geral), 2)
            for row in ranking.itertuples()
        }
    return payload


def build_monthly_awards_html(appearance_df: pd.DataFrame) -> str:
    monthly_payload = build_monthly_awards_payload(appearance_df)
    monthly_scores = build_monthly_awards_scores(appearance_df)
    monthly_payload_json = json.dumps(monthly_payload, ensure_ascii=False)
    monthly_scores_json = json.dumps(monthly_scores, ensure_ascii=False)

    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Premiação Mensal | Pixotada 2026</title>
  <style>
    :root {{
      --bg: #f3efe6;
      --panel: #fffdfa;
      --ink: #1f2937;
      --muted: #6b7280;
      --line: #e5dccb;
      --gold: #d97706;
      --teal: #0f766e;
      --blue: #2563eb;
      --wine: #be123c;
      --olive: #4d7c0f;
      --slate: #334155;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #fff6dc 0%, rgba(255, 246, 220, 0.1) 28%, transparent 50%),
        linear-gradient(180deg, #ede5d5 0%, var(--bg) 34%, #faf7f1 100%);
    }}
    .wrap {{
      width: min(1380px, calc(100% - 32px));
      margin: 0 auto;
      padding: 24px 0 48px;
    }}
    .hero, .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: 0 14px 32px rgba(71, 55, 26, 0.08);
    }}
    .hero {{
      padding: 28px;
      background:
        linear-gradient(135deg, rgba(217, 119, 6, 0.1), rgba(15, 118, 110, 0.08)),
        var(--panel);
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(217, 119, 6, 0.12);
      color: #92400e;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 16px 0 8px;
      font-size: clamp(30px, 4vw, 48px);
      line-height: 1.05;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }}
    .nav, .hero-top, .hero-actions, .hero-summary, .leader-grid, .tables-grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .hero-top, .hero-actions {{
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }}
    .nav {{
      margin-top: 22px;
    }}
    .nav a {{
      text-decoration: none;
      color: var(--ink);
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.7);
      font-size: 14px;
    }}
    .hero-actions label {{
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    select {{
      min-width: 220px;
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      font-size: 15px;
    }}
    .hero-summary {{
      margin-top: 20px;
    }}
    .summary-pill {{
      padding: 12px 14px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.78);
      min-width: 180px;
    }}
    .summary-pill strong {{
      display: block;
      font-size: 18px;
      margin-top: 4px;
      color: var(--ink);
    }}
    .section-title {{
      margin: 26px 0 12px;
      font-size: 24px;
    }}
    .leader-grid, .tables-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
    }}
    .card {{
      padding: 18px;
    }}
    .award-name {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .award-stat {{
      margin: 14px 0 4px;
      font-size: 42px;
      line-height: 1;
      font-weight: 800;
    }}
    .award-leader {{
      font-size: 22px;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .award-meta {{
      font-size: 14px;
      color: var(--muted);
    }}
    .award-gold .award-name, .award-gold .award-stat {{ color: var(--wine); }}
    .award-teal .award-name, .award-teal .award-stat {{ color: var(--blue); }}
    .award-blue .award-name, .award-blue .award-stat {{ color: var(--teal); }}
    .award-olive .award-name, .award-olive .award-stat {{ color: var(--olive); }}
    .award-slate .award-name, .award-slate .award-stat {{ color: var(--slate); }}
    .table-wrap {{
      overflow-x: auto;
      margin-top: 14px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      padding: 12px 10px;
      border-bottom: 1px solid #efe6d7;
      text-align: left;
      white-space: nowrap;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    tbody tr:first-child td {{
      font-weight: 700;
    }}
    @media (max-width: 720px) {{
      .hero-top, .hero-actions {{
        align-items: stretch;
      }}
      select {{
        width: 100%;
      }}
      .award-stat {{
        font-size: 36px;
      }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div class="hero-top">
        <div>
          <span class="eyebrow">Pixotada FC 2026</span>
          <h1>Premiação Mensal</h1>
          <p>Disputa mensal pelos líderes dos scouts ofensivos, coletivos e defensivos. O recorte usa os registros consolidados de cada mês.</p>
        </div>
        <div class="hero-actions">
          <div>
            <label for="month-select">Selecione o mês</label>
            <select id="month-select"></select>
          </div>
        </div>
      </div>
      <div class="hero-summary" id="hero-summary"></div>
      <div class="nav">
        <a href="dashboard_pixotada_2026.html">Dashboard</a>
        <a href="ranking_modelos_ultimas4.html">Modelos de pontuação</a>
        <a href="ranking_geral_jogadores.html">Ranking geral</a>
        <a href="premiacao_mensal.html">Premiação mensal</a>
        <a href="raio_x_jogador.html">Raio X do jogador</a>
        <a href="efeito_jogadores.html">Efeito dos jogadores</a>
        <a href="sugestao_novas_notas.html">Sugestão de notas</a>
        <a href="detalhe_recomendacoes_notas.html">Detalhe das recomendações</a>
      </div>
    </section>

    <h2 class="section-title">Líderes do mês</h2>
    <section class="leader-grid" id="leader-grid"></section>

    <h2 class="section-title">Perseguição por scout</h2>
    <section class="tables-grid" id="tables-grid"></section>
  </main>

  <script>
    const monthlyPayload = {monthly_payload_json};
    const awards = [
      {{ key: "score", title: "Jogador mais valioso", subtitle: "maior score do mês", tone: "award-olive" }},
      {{ key: "gols", title: "Artilheiro", subtitle: "+ gols", tone: "award-gold" }},
      {{ key: "assistencias", title: "Garçom", subtitle: "+ assistências", tone: "award-teal" }},
      {{ key: "participacoes", title: "Maestro", subtitle: "+ participações", tone: "award-blue" }},
      {{ key: "sg", title: "Xerife", subtitle: "+ jogos sem sofrer gols", tone: "award-slate" }}
    ];
    const craqueScores = {monthly_scores_json};

    const monthSelect = document.getElementById("month-select");
    const heroSummary = document.getElementById("hero-summary");
    const leaderGrid = document.getElementById("leader-grid");
    const tablesGrid = document.getElementById("tables-grid");
    const months = Object.keys(monthlyPayload).sort();

    function formatMonth(monthKey) {{
      const [year, month] = monthKey.split("-").map(Number);
      return new Date(year, month - 1, 1).toLocaleDateString("pt-BR", {{
        month: "long",
        year: "numeric"
      }});
    }}

    function rankBy(items, statKey) {{
      return [...items].sort((a, b) =>
        (Number.isFinite(b[statKey]) ? b[statKey] : -Infinity) - (Number.isFinite(a[statKey]) ? a[statKey] : -Infinity) ||
        b.jogos - a.jogos ||
        a.jogador.localeCompare(b.jogador, "pt-BR")
      );
    }}

    function getAvailableAwards(items) {{
      return awards.filter(award => items.some(item => Number.isFinite(item[award.key])));
    }}

    function formatValue(value) {{
      return Number(value).toLocaleString("pt-BR", {{
        minimumFractionDigits: 0,
        maximumFractionDigits: 2
      }});
    }}

    function buildSummary(items, monthKey) {{
      const totalJogadores = items.length;
      const totalJogos = items.reduce((sum, item) => sum + item.jogos, 0);
      const totalParticipacoes = items.reduce((sum, item) => sum + item.participacoes, 0);
      heroSummary.innerHTML = `
        <div class="summary-pill">
          <span>Mês em foco</span>
          <strong>${{formatMonth(monthKey)}}</strong>
        </div>
        <div class="summary-pill">
          <span>Jogadores com scout</span>
          <strong>${{totalJogadores}}</strong>
        </div>
        <div class="summary-pill">
          <span>Aparições somadas</span>
          <strong>${{totalJogos}}</strong>
        </div>
        <div class="summary-pill">
          <span>Participações em gol</span>
          <strong>${{totalParticipacoes}}</strong>
        </div>
      `;
    }}

    function buildLeaderCards(items) {{
      leaderGrid.innerHTML = getAvailableAwards(items).map(award => {{
        const ranking = rankBy(items, award.key);
        const bestValue = ranking[0][award.key];
        const leaders = ranking.filter(item => item[award.key] === bestValue);
        const runnerUp = ranking.find(item => item[award.key] < bestValue);
        const chase = runnerUp ? `${{formatValue(bestValue - runnerUp[award.key])}} de vantagem para ${{runnerUp.jogador}}` : "Sem perseguidor direto";
        return `
          <article class="card ${{award.tone}}">
            <div class="award-name">${{award.title}}</div>
            <div class="award-stat">${{formatValue(bestValue)}}</div>
            <div class="award-leader">${{leaders.map(item => item.jogador).join(", ")}}</div>
            <p class="award-meta">${{award.subtitle}}. ${{chase}}.</p>
          </article>
        `;
      }}).join("");
    }}

    function buildTables(items) {{
      tablesGrid.innerHTML = getAvailableAwards(items).map(award => {{
        const ranking = rankBy(items, award.key).slice(0, 5);
        const rows = ranking.map((item, index) => `
          <tr>
            <td>${{index + 1}}</td>
            <td>${{item.jogador}}</td>
            <td>${{formatValue(item[award.key])}}</td>
            <td>${{item.jogos}}</td>
          </tr>
        `).join("");

        return `
          <article class="card">
            <div class="award-name">${{award.title}}</div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Jogador</th>
                    <th>Scout</th>
                    <th>Jogos</th>
                  </tr>
                </thead>
                <tbody>${{rows}}</tbody>
              </table>
            </div>
          </article>
        `;
      }}).join("");
    }}

    function renderMonth(monthKey) {{
      const scores = craqueScores[monthKey] || {{}};
      const items = (monthlyPayload[monthKey] || []).map(item => ({{
        ...item,
        score: Number.isFinite(scores[item.jogador]) ? scores[item.jogador] : undefined
      }}));
      buildSummary(items, monthKey);
      buildLeaderCards(items);
      buildTables(items);
    }}

    months.forEach(month => {{
      const option = document.createElement("option");
      option.value = month;
      option.textContent = formatMonth(month);
      monthSelect.appendChild(option);
    }});

    monthSelect.value = months[months.length - 1];
    renderMonth(monthSelect.value);
    monthSelect.addEventListener("change", event => renderMonth(event.target.value));
  </script>
</body>
</html>
"""


def build_player_xray_history(appearance_df: pd.DataFrame) -> pd.DataFrame:
    history_frames = []
    for match_date in sorted(appearance_df["Data"].drop_duplicates()):
        cumulative = appearance_df.loc[appearance_df["Data"] <= match_date].copy()
        ranking = build_general_ranking(cumulative, match_date.strftime("%Y-%m-%d"), min_games=1)
        if ranking.empty:
            continue
        ranking["Data"] = match_date
        ranking["Data_fmt"] = match_date.strftime("%d/%m/%Y")
        ranking["Mes"] = match_date.strftime("%Y-%m")
        ranking["Confianca"] = ranking["Jogos"].map(classify_confidence)
        history_frames.append(ranking)

    if not history_frames:
        return pd.DataFrame()

    history_df = pd.concat(history_frames, ignore_index=True)
    detail_columns = [
        "Data",
        "Jogadores",
        "Time",
        "Gol",
        "Assist",
        "Participacoes",
        "Classificacao",
        "Expected_points",
        "Delta_points",
        "Gols_time",
        "Gols_sofridos",
        "Jogos_sem_sofrer",
        "Companheiros",
    ]
    history_df = history_df.merge(
        appearance_df[detail_columns],
        on=["Data", "Jogadores"],
        how="left",
    )
    history_df = history_df.loc[history_df["Time"].notna()].copy()
    history_df["Time"] = history_df["Time"].astype(int)
    return history_df.sort_values(["Jogadores", "Data"]).reset_index(drop=True)


def build_player_xray_summary(
    appearance_df: pd.DataFrame,
    history_df: pd.DataFrame,
    general_historic: pd.DataFrame,
    general_month: pd.DataFrame,
) -> pd.DataFrame:
    latest_positions = (
        history_df.sort_values(["Jogadores", "Data"])
        .groupby("Jogadores", as_index=False)
        .tail(1)[["Jogadores", "Posicao", "Score_geral", "Data", "Data_fmt"]]
        .rename(
            columns={
                "Posicao": "PosicaoAtualHistoricoBruto",
                "Score_geral": "ScoreAtualHistoricoBruto",
                "Data": "UltimaData",
                "Data_fmt": "UltimaDataFmt",
            }
        )
    )

    trend_rows = []
    for player, player_df in history_df.groupby("Jogadores"):
        last_positions = player_df.sort_values("Data")["Posicao"].tail(3).tolist()
        if len(last_positions) < 2:
            trend = "Sem tendencia"
        elif last_positions[-1] < last_positions[0]:
            trend = "Subindo"
        elif last_positions[-1] > last_positions[0]:
            trend = "Caindo"
        else:
            trend = "Estavel"
        trend_rows.append({"Jogadores": player, "Tendencia": trend})
    trend_df = pd.DataFrame(trend_rows)

    distribution_rows = []
    for player, player_df in appearance_df.groupby("Jogadores"):
        counts = player_df["Classificacao"].value_counts().to_dict()
        distribution_rows.append(
            {
                "Jogadores": player,
                "Titulos": int(counts.get("Campeao", 0)),
                "Segundos": int(counts.get("Segundo", 0)),
                "Terceiros": int(counts.get("Terceiro", 0)),
                "Lanternas": int(counts.get("Lanterna", 0)),
            }
        )
    distribution_df = pd.DataFrame(distribution_rows)

    summary = (
        appearance_df.groupby("Jogadores", as_index=False)
        .agg(
            Jogos=("Data", "count"),
            Gols_pg=("Gol", "mean"),
            Assist_pg=("Assist", "mean"),
            Participacoes_pg=("Participacoes", "mean"),
            GolsTime_pg=("Gols_time", "mean"),
            GolsSofridos_pg=("Gols_sofridos", "mean"),
            JogosSemSofrer_pg=("Jogos_sem_sofrer", "mean"),
            Delta_points_pg=("Delta_points", "mean"),
        )
        .merge(latest_positions, on="Jogadores", how="left")
        .merge(trend_df, on="Jogadores", how="left")
        .merge(distribution_df, on="Jogadores", how="left")
        .merge(
            general_historic[["Jogadores", "Posicao", "Score_geral"]].rename(
                columns={"Posicao": "PosicaoRankingGeral", "Score_geral": "ScoreRankingGeral"}
            ),
            on="Jogadores",
            how="left",
        )
        .merge(
            general_month[["Jogadores", "Posicao", "Score_geral"]].rename(
                columns={"Posicao": "PosicaoRankingMes", "Score_geral": "ScoreRankingMes"}
            ),
            on="Jogadores",
            how="left",
        )
    )
    return summary.sort_values("Jogadores").reset_index(drop=True)


def build_player_xray_html(history_df: pd.DataFrame, summary_df: pd.DataFrame) -> str:
    if history_df.empty or summary_df.empty:
        return """
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"><title>Raio X do jogador</title></head>
<body><p>Sem dados suficientes para gerar o Raio X do jogador.</p></body>
</html>
"""

    players = sorted(summary_df["Jogadores"].tolist())
    first_player = players[0]
    payload = {}

    for player in players:
        player_summary = summary_df.loc[summary_df["Jogadores"] == player].iloc[0]
        player_history = history_df.loc[history_df["Jogadores"] == player].sort_values("Data").copy()
        best_row = player_history.sort_values(["Posicao", "Delta_points", "Data"], ascending=[True, False, True]).iloc[0]
        worst_row = player_history.sort_values(["Posicao", "Delta_points", "Data"], ascending=[False, True, False]).iloc[0]
        payload[player] = {
            "summary": {
                "jogos": int(player_summary["Jogos"]),
                "posicao_ranking_geral": None
                if pd.isna(player_summary["PosicaoRankingGeral"])
                else int(player_summary["PosicaoRankingGeral"]),
                "score_ranking_geral": None
                if pd.isna(player_summary["ScoreRankingGeral"])
                else round(float(player_summary["ScoreRankingGeral"]), 2),
                "posicao_ranking_mes": None
                if pd.isna(player_summary["PosicaoRankingMes"])
                else int(player_summary["PosicaoRankingMes"]),
                "score_ranking_mes": None
                if pd.isna(player_summary["ScoreRankingMes"])
                else round(float(player_summary["ScoreRankingMes"]), 2),
                "gols_pg": round(float(player_summary["Gols_pg"]), 2),
                "assist_pg": round(float(player_summary["Assist_pg"]), 2),
                "participacoes_pg": round(float(player_summary["Participacoes_pg"]), 2),
                "gols_time_pg": round(float(player_summary["GolsTime_pg"]), 2),
                "gols_sofridos_pg": round(float(player_summary["GolsSofridos_pg"]), 2),
                "sg_pg": round(float(player_summary["JogosSemSofrer_pg"]), 2),
                "delta_points_pg": round(float(player_summary["Delta_points_pg"]), 2),
                "tendencia": player_summary["Tendencia"],
                "titulos": int(player_summary["Titulos"]),
                "segundos": int(player_summary["Segundos"]),
                "terceiros": int(player_summary["Terceiros"]),
                "lanternas": int(player_summary["Lanternas"]),
                "ultima_data": player_summary["UltimaDataFmt"],
                "melhor_data": best_row["Data_fmt"],
                "melhor_posicao": int(best_row["Posicao"]),
                "pior_data": worst_row["Data_fmt"],
                "pior_posicao": int(worst_row["Posicao"]),
            },
            "history": [
                {
                    "data": row.Data.strftime("%Y-%m-%d"),
                    "data_fmt": row.Data_fmt,
                    "mes": row.Mes,
                    "posicao": int(row.Posicao),
                    "score": round(float(row.Score_geral), 2),
                    "jogos": int(row.Jogos),
                    "confianca": row.Confianca,
                    "time": int(row.Time),
                    "classificacao": POSITION_LABELS.get(row.Classificacao, row.Classificacao),
                    "gols": int(row.Gol),
                    "assistencias": int(row.Assist),
                    "participacoes": int(row.Participacoes),
                    "gols_time": int(row.Gols_time),
                    "gols_sofridos": int(row.Gols_sofridos),
                    "sg": int(row.Jogos_sem_sofrer),
                    "expected_points": round(float(row.Expected_points), 2),
                    "delta_points": round(float(row.Delta_points), 2),
                    "companheiros": row.Companheiros,
                }
                for row in player_history.itertuples()
            ],
        }

    first_dates = ["geral"] + [item["data"] for item in payload[first_player]["history"]]
    plotly_js = get_plotlyjs()

    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Raio X do jogador</title>
  <script>{plotly_js}</script>
  <style>
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      background: #f6f1e8;
      color: #1f2933;
    }}
    .wrap {{
      width: min(1400px, calc(100% - 32px));
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
    .selectors {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 280px));
      gap: 14px;
      margin-top: 18px;
    }}
    .selectors label {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      font-weight: 600;
    }}
    .selectors select {{
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid #dccfb8;
      background: #fff;
      font-size: 15px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 20px;
      margin-top: 20px;
    }}
    .summary-grid, .detail-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 16px;
    }}
    .mini-card {{
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px solid #eadfc9;
      background: #fffaf1;
    }}
    .mini-card span {{
      display: block;
      font-size: 12px;
      color: #6b7280;
      margin-bottom: 6px;
    }}
    .mini-card strong {{
      font-size: 24px;
    }}
    .detail-grid .mini-card strong {{
      font-size: 20px;
    }}
    .detail-note {{
      margin-top: 14px;
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px solid #eadfc9;
      background: #fffaf1;
      line-height: 1.5;
    }}
    .hidden {{
      display: none;
    }}
    #ranking-history-chart {{
      width: 100%;
      height: 420px;
    }}
    @media (max-width: 720px) {{
      .selectors {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Raio X do jogador</h1>
      <p>Visao individual com evolucao no ranking ao longo do tempo e detalhamento por data.</p>
      <div class="nav">
        <a href="dashboard_pixotada_2026.html">Dashboard</a>
        <a href="ranking_geral_jogadores.html">Ranking geral</a>
        <a href="premiacao_mensal.html">Premiacao mensal</a>
        <a href="raio_x_jogador.html">Raio X do jogador</a>
        <a href="ranking_modelos_ultimas4.html">Modelos de pontuacao</a>
        <a href="efeito_jogadores.html">Efeito dos jogadores</a>
        <a href="sugestao_novas_notas.html">Sugestao de notas</a>
        <a href="detalhe_recomendacoes_notas.html">Detalhe das recomendacoes</a>
      </div>
      <div class="selectors">
        <label for="player-select">Selecione o jogador
          <select id="player-select"></select>
        </label>
        <label for="date-select">Selecione a data
          <select id="date-select"></select>
        </label>
      </div>
    </section>
    <section class="card" style="margin-top:20px;">
      <h2>Evolucao no ranking</h2>
      <div id="ranking-history-chart"></div>
    </section>
    <section class="grid">
      <section class="card">
        <h2>Resumo geral</h2>
        <div id="summary-grid" class="summary-grid"></div>
        <div id="general-detail" class="detail-note"></div>
      </section>
      <section id="date-card" class="card hidden">
        <h2 id="date-title">Detalhe da data</h2>
        <div id="date-detail-grid" class="detail-grid"></div>
        <div id="date-detail-note" class="detail-note"></div>
      </section>
    </section>
  </main>
  <script>
    const playerPayload = {json.dumps(payload, ensure_ascii=False)};
    const playerSelect = document.getElementById("player-select");
    const dateSelect = document.getElementById("date-select");
    const summaryGrid = document.getElementById("summary-grid");
    const generalDetail = document.getElementById("general-detail");
    const dateCard = document.getElementById("date-card");
    const dateTitle = document.getElementById("date-title");
    const dateDetailGrid = document.getElementById("date-detail-grid");
    const dateDetailNote = document.getElementById("date-detail-note");

    function metric(label, value) {{
      return `<div class="mini-card"><span>${{label}}</span><strong>${{value}}</strong></div>`;
    }}

    function formatNumber(value, digits = 2) {{
      if (value === null || value === undefined || Number.isNaN(value)) return "-";
      return Number(value).toFixed(digits);
    }}

    function formatSigned(value, digits = 2) {{
      if (value === null || value === undefined || Number.isNaN(value)) return "-";
      const formatted = Number(value).toFixed(digits);
      return value > 0 ? `+${{formatted}}` : formatted;
    }}

    function renderDateOptions(player, selectedDate = "geral") {{
      const history = playerPayload[player].history;
      dateSelect.innerHTML = "";
      const overallOption = document.createElement("option");
      overallOption.value = "geral";
      overallOption.textContent = "Visao geral";
      dateSelect.appendChild(overallOption);
      history.forEach(item => {{
        const option = document.createElement("option");
        option.value = item.data;
        option.textContent = item.data_fmt;
        dateSelect.appendChild(option);
      }});
      dateSelect.value = selectedDate;
    }}

    function renderSummary(player) {{
      const summary = playerPayload[player].summary;
      summaryGrid.innerHTML = [
        metric("Posicao no ranking geral", summary.posicao_ranking_geral ?? "-"),
        metric("Posicao no mes", summary.posicao_ranking_mes ?? "-"),
        metric("Jogos", summary.jogos),
        metric("Gols/pelada", formatNumber(summary.gols_pg)),
        metric("Assist/pelada", formatNumber(summary.assist_pg)),
        metric("Participacoes/pelada", formatNumber(summary.participacoes_pg)),
        metric("Gols do time/pelada", formatNumber(summary.gols_time_pg)),
        metric("Gols sofridos/pelada", formatNumber(summary.gols_sofridos_pg)),
        metric("SG/pelada", formatNumber(summary.sg_pg)),
        metric("Delta pontos/pelada", formatSigned(summary.delta_points_pg)),
        metric("Tendencia", summary.tendencia),
        metric("Ultima pelada", summary.ultima_data),
      ].join("");
      generalDetail.innerHTML = `
        <strong>Distribuicao de classificacoes</strong><br>
        Campeao: ${{summary.titulos}} | Segundo: ${{summary.segundos}} | Terceiro: ${{summary.terceiros}} | Lanterna: ${{summary.lanternas}}<br><br>
        <strong>Melhor momento</strong><br>
        ${{summary.melhor_data}} (posicao ${{summary.melhor_posicao}})<br><br>
        <strong>Pior momento</strong><br>
        ${{summary.pior_data}} (posicao ${{summary.pior_posicao}})
      `;
    }}

    function renderDateDetail(player, selectedDate) {{
      if (selectedDate === "geral") {{
        dateCard.classList.add("hidden");
        return;
      }}
      const item = playerPayload[player].history.find(entry => entry.data === selectedDate);
      if (!item) {{
        dateCard.classList.add("hidden");
        return;
      }}
      dateCard.classList.remove("hidden");
      dateTitle.textContent = `Detalhe da pelada: ${{item.data_fmt}}`;
      dateDetailGrid.innerHTML = [
        metric("Posicao no ranking", item.posicao),
        metric("Score", formatNumber(item.score)),
        metric("Jogos acumulados", item.jogos),
        metric("Confianca", item.confianca),
        metric("Time", item.time),
        metric("Classificacao", item.classificacao),
        metric("Gols", item.gols),
        metric("Assistencias", item.assistencias),
        metric("Participacoes", item.participacoes),
        metric("Gols do time", item.gols_time),
        metric("Gols sofridos", item.gols_sofridos),
        metric("Jogo sem sofrer gols", item.sg ? "Sim" : "Nao"),
        metric("Pontos esperados", formatNumber(item.expected_points)),
        metric("Delta pontos", formatSigned(item.delta_points)),
      ].join("");
      dateDetailNote.innerHTML = `
        <strong>Companheiros</strong><br>
        ${{item.companheiros || "-"}}
      `;
    }}

    function renderChart(player) {{
      const history = playerPayload[player].history;
      const trace = {{
        x: history.map(item => item.data_fmt),
        y: history.map(item => item.posicao),
        customdata: history.map(item => [
          item.score,
          item.classificacao,
          item.delta_points,
          item.time,
          item.gols,
          item.assistencias,
        ]),
        mode: "lines+markers",
        line: {{ color: "#0f766e", width: 3 }},
        marker: {{ size: 9, color: "#b45309" }},
        hovertemplate:
          "<b>%{{x}}</b><br>" +
          "Posicao: %{{y}}<br>" +
          "Score: %{{customdata[0]:.2f}}<br>" +
          "Classificacao: %{{customdata[1]}}<br>" +
          "Delta pontos: %{{customdata[2]:+.2f}}<br>" +
          "Time: %{{customdata[3]}}<br>" +
          "Gols/Assist: %{{customdata[4]}} / %{{customdata[5]}}<extra></extra>",
      }};
      const maxRank = Math.max(...history.map(item => item.posicao)) + 1;
      Plotly.newPlot("ranking-history-chart", [trace], {{
        margin: {{ l: 60, r: 20, t: 20, b: 50 }},
        paper_bgcolor: "#fffdf8",
        plot_bgcolor: "#fff",
        xaxis: {{ title: "Data" }},
        yaxis: {{ title: "Posicao", autorange: "reversed", range: [maxRank, 1] }},
      }}, {{ responsive: true, displayModeBar: false }});

      const chart = document.getElementById("ranking-history-chart");
      chart.on("plotly_click", event => {{
        const point = event.points && event.points[0];
        if (!point) return;
        const selected = history[point.pointIndex];
        dateSelect.value = selected.data;
        renderDateDetail(player, selected.data);
      }});
    }}

    function renderPlayer(player, selectedDate = "geral") {{
      renderDateOptions(player, selectedDate);
      renderSummary(player);
      renderDateDetail(player, dateSelect.value);
      renderChart(player);
    }}

    Object.keys(playerPayload).forEach(player => {{
      const option = document.createElement("option");
      option.value = player;
      option.textContent = player;
      playerSelect.appendChild(option);
    }});

    playerSelect.value = {json.dumps(first_player, ensure_ascii=False)};
    renderPlayer(playerSelect.value, "geral");

    playerSelect.addEventListener("change", event => renderPlayer(event.target.value, "geral"));
    dateSelect.addEventListener("change", event => renderDateDetail(playerSelect.value, event.target.value));
  </script>
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
  <title>Modelos de pontuacao</title>
  <style>
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      background: #f6f1e8;
      color: #1f2933;
    }}
    .wrap {{
      width: min(1400px, calc(100% - 32px));
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
        <a href="ranking_geral_jogadores.html">Ranking geral</a>
        <a href="premiacao_mensal.html">Premiação mensal</a>
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

    monthly_awards_html = build_monthly_awards_html(appearance_df)
    (OUTPUT_DIR / "premiacao_mensal.html").write_text(monthly_awards_html, encoding="utf-8")
    (BASE_DIR / "premiacao_mensal.html").write_text(monthly_awards_html, encoding="utf-8")
    (PUBLIC_DIR / "premiacao_mensal.html").write_text(monthly_awards_html, encoding="utf-8")

    xray_history = build_player_xray_history(appearance_df)
    xray_summary = build_player_xray_summary(appearance_df, xray_history, general_historic, general_month)
    xray_history.to_csv(OUTPUT_DIR / "raio_x_jogador_historico.csv", index=False, encoding="utf-8-sig")
    xray_summary.to_csv(OUTPUT_DIR / "raio_x_jogador_resumo.csv", index=False, encoding="utf-8-sig")

    xray_html = build_player_xray_html(xray_history, xray_summary)
    (OUTPUT_DIR / "raio_x_jogador.html").write_text(xray_html, encoding="utf-8")
    (BASE_DIR / "raio_x_jogador.html").write_text(xray_html, encoding="utf-8")
    (PUBLIC_DIR / "raio_x_jogador.html").write_text(xray_html, encoding="utf-8")

    print(f"Arquivos gerados em: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
