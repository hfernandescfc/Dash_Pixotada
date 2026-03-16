from pathlib import Path
import json
import unicodedata

import pandas as pd

from pixotada_dashboard import load_data
from pixotada_scores import MODELS, score_model


BASE_DIR = Path(r"c:\Users\compesa\Desktop")
PLAYERS_FILE = BASE_DIR / "Peladapp" / "players.json"
OUTPUT_DIR = BASE_DIR / "pixotada_2026_dashboard"
PUBLIC_DIR = BASE_DIR / "pixotada_public_site"

ACTUAL_POINTS = {"Campeao": 4, "Segundo": 3, "Terceiro": 2, "Lanterna": 1}
EXPECTED_POINTS_MAP = {1.0: 4, 2.0: 3, 3.0: 2, 4.0: 1}

ALIASES = {
    "gabriel de leon": "Fuinha",
    "gabriel lira": "Gabriel",
    "guilherme figueiredo": "Guilherme",
    "guilherme calafa": "Calafa",
    "hugo": "Hugão",
    "lucas souza": "Lucas",
    "paulo freitas": "Paulão",
    "sheik": "Sheik",
    "girao": "Diogo Girão",
    "junior": "Júnior",
    "marcelo torres": "Marcelo",
    "claudio": "Cláudio",
    "thiago cruz": "Thiaguinho",
    "eduardo jorge": "JG",
    "davi": "David Marques",
}


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(char for char in text if not unicodedata.combining(char))


def load_players() -> pd.DataFrame:
    players = json.loads(PLAYERS_FILE.read_text(encoding="utf-8-sig"))
    players_df = pd.DataFrame(players)
    players_df["name_norm"] = players_df["name"].map(normalize_name)
    players_df["scout_name"] = players_df["name_norm"].map(ALIASES).fillna(players_df["name"])
    return players_df


def build_recent_form(df: pd.DataFrame, player_names: list[str]) -> pd.DataFrame:
    recent4 = (
        df[df["Jogadores"].isin(player_names)]
        .sort_values(["Jogadores", "Data"], ascending=[True, False])
        .assign(Recencia=lambda x: x.groupby("Jogadores").cumcount() + 1)
        .loc[lambda x: x["Recencia"] <= 4]
        .copy()
    )
    recent4["Peso_recencia"] = recent4["Recencia"].map({1: 0.4, 2: 0.3, 3: 0.2, 4: 0.1})
    ranking, _ = score_model(recent4, "equilibrado", MODELS["equilibrado"])
    ranking["Top_recent"] = ranking["Posicao"] <= max(1, round(len(ranking) * 0.35))
    ranking["Bottom_recent"] = ranking["Posicao"] >= max(1, len(ranking) - round(len(ranking) * 0.35) + 1)
    return ranking


def build_adjusted_impact(df: pd.DataFrame, strength_map: dict[str, float]) -> pd.DataFrame:
    data = df.copy()
    # Expected team strength is based on observed recent form, not current stars.
    data["forca_observada"] = data["Jogadores"].map(strength_map).fillna(0)
    data["actual_points"] = data["classificacao_norm"].map(ACTUAL_POINTS)

    team_strength = (
        data.groupby(["Data", "Time"], as_index=False)
        .agg(
            team_strength=("forca_observada", "sum"),
            actual_points=("actual_points", "first"),
            classificacao=("classificacao_norm", "first"),
        )
    )
    team_strength["expected_rank"] = team_strength.groupby("Data")["team_strength"].rank(method="dense", ascending=False)
    team_strength["expected_points"] = team_strength["expected_rank"].map(EXPECTED_POINTS_MAP).fillna(1)
    team_strength["delta_points"] = team_strength["actual_points"] - team_strength["expected_points"]

    data = data.merge(
        team_strength[["Data", "Time", "expected_points", "delta_points", "team_strength"]],
        on=["Data", "Time"],
        how="left",
    )
    summary = (
        data.groupby("Jogadores", as_index=False)
        .agg(
            Jogos_ult6=("Data", "count"),
            Participacoes_ult6=("participacoes", "sum"),
            Media_participacoes=("participacoes", "mean"),
            Impacto_ajustado=("delta_points", "mean"),
            Impacto_bruto=("actual_points", "mean"),
            Expected_points_medios=("expected_points", "mean"),
        )
    )
    return summary


def suggest_row(row: pd.Series) -> tuple[int, str, str]:
    current = int(row["rating"])
    impact = row.get("Impacto_ajustado")
    participacoes = row.get("Participacoes_ult6")
    position = row.get("Posicao")
    jogos = row.get("Jogos_ult6", 0)

    if pd.isna(impact) or pd.isna(position) or jogos < 3:
        return current, "manter", "Sem amostra minima no recorte das ultimas 6 peladas."

    strong_up = impact >= 0.5 and position >= 10
    moderate_up = impact >= 0.25 and position >= 14
    # If the player is underperforming versus expectation, allow a downgrade
    # either because he is still ranking high individually or because the
    # observed collective signal is strongly negative.
    strong_down = impact <= -0.75 or (impact <= -0.5 and position <= 10)
    moderate_down = impact <= -0.5 and current >= 4

    if strong_up or moderate_up:
        new_rating = min(7, current + 1)
        reason = (
            f"Jogou {int(jogos)} vezes nas ultimas 6, somou {int(participacoes)} participacoes, "
            f"mas ainda assim ficou apenas na posicao {int(position)} do desempenho recente. "
            f"O impacto ajustado de {impact:.2f} sugere que seus times renderam acima do esperado pela forca recente observada."
        )
        return new_rating, "subir", reason

    if strong_down or moderate_down:
        new_rating = max(1, current - 1)
        reason = (
            f"Jogou {int(jogos)} vezes nas ultimas 6, ficou na posicao {int(position)} do desempenho recente, "
            f"mas o impacto ajustado foi {impact:.2f}, indicando que seus times renderam abaixo do esperado pela forca recente observada."
        )
        return new_rating, "descer", reason

    reason = (
        f"Jogou {int(jogos)} vezes nas ultimas 6, impacto ajustado de {impact:.2f} e desempenho recente sem sinal claro "
        f"de incompatibilidade com a nota atual."
    )
    return current, "manter", reason


def build_html(df: pd.DataFrame) -> str:
    table = df.copy()
    numeric_cols = ["Impacto_ajustado"]
    for col in numeric_cols:
        table[col] = table[col].map(lambda x: "" if pd.isna(x) else f"{x:.2f}")
    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Sugestao de Notas dos Jogadores</title>
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
    .table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    .table th, .table td {{
      border-bottom: 1px solid #eadfc9;
      padding: 10px 8px;
      text-align: left;
      vertical-align: top;
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
      <h1>Sugestao de Novas Notas</h1>
      <p>Expectativa refinada usando scouts e classificacao recente para estimar a forca observada dos times nas ultimas 6 peladas.</p>
      <p>So entram como evidência de ajuste os jogadores com pelo menos 3 jogos nesse recorte.</p>
      <div class="nav">
        <a href="dashboard_pixotada_2026.html">Dashboard</a>
        <a href="ranking_modelos_ultimas4.html">Modelos de pontuação</a>
        <a href="efeito_jogadores.html">Efeito dos jogadores</a>
        <a href="sugestao_novas_notas.html">Sugestão de notas</a>
        <a href="detalhe_recomendacoes_notas.html">Detalhe das recomendações</a>
      </div>
    </section>
    <section class="card" style="margin-top:20px;">
      {table.to_html(index=False, classes="table", border=0)}
    </section>
  </main>
</body>
</html>
"""


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    PUBLIC_DIR.mkdir(exist_ok=True)

    scout_df = load_data()
    last6_dates = sorted(scout_df["Data"].drop_duplicates())[-6:]
    recent_df = scout_df[scout_df["Data"].isin(last6_dates)].copy()

    players_df = load_players()
    games_count = recent_df.groupby("Jogadores").size().rename("Jogos_ult6").reset_index()
    eligible_names = games_count.loc[games_count["Jogos_ult6"] >= 3, "Jogadores"].tolist()
    all_recent_names = sorted(recent_df["Jogadores"].drop_duplicates().tolist())

    recent_form = build_recent_form(recent_df, all_recent_names)
    adjusted = build_adjusted_impact(recent_df, dict(zip(recent_form["Jogadores"], recent_form["Nota_final"])))

    result = players_df.merge(
        recent_form[
            [
                "Jogadores",
                "Posicao",
                "Nota_final",
                "Participacoes_ult4",
                "Media_classificacao",
                "Jogos_considerados",
            ]
        ],
        left_on="scout_name",
        right_on="Jogadores",
        how="left",
    ).merge(
        adjusted,
        left_on="scout_name",
        right_on="Jogadores",
        how="left",
        suffixes=("", "_impact"),
    )

    suggestions = result.apply(suggest_row, axis=1, result_type="expand")
    suggestions.columns = ["nova_nota_sugerida", "sinal", "justificativa"]
    result = pd.concat([result, suggestions], axis=1)

    final_df = result[
        [
            "name",
            "scout_name",
            "rating",
            "nova_nota_sugerida",
            "sinal",
            "Jogos_ult6",
            "Posicao",
            "Participacoes_ult6",
            "Impacto_ajustado",
            "justificativa",
        ]
    ].rename(
        columns={
            "name": "jogador_json",
            "scout_name": "jogador_scout",
            "rating": "nota_atual",
            "Jogos_ult6": "jogos_ult6",
            "Posicao": "posicao_modelo_recente",
            "Participacoes_ult6": "participacoes_ult6",
        }
    )

    final_df = final_df.sort_values(["sinal", "nova_nota_sugerida", "jogador_json"], ascending=[True, False, True])
    final_df.to_csv(OUTPUT_DIR / "sugestao_novas_notas.csv", index=False, encoding="utf-8-sig")

    html = build_html(final_df)
    (OUTPUT_DIR / "sugestao_novas_notas.html").write_text(html, encoding="utf-8")
    (BASE_DIR / "sugestao_novas_notas.html").write_text(html, encoding="utf-8")
    (PUBLIC_DIR / "sugestao_novas_notas.html").write_text(html, encoding="utf-8")

    print(f"Arquivos gerados em: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
