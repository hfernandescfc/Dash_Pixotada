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


def build_participation_baseline(df: pd.DataFrame, players_df: pd.DataFrame) -> pd.DataFrame:
    player_ratings = players_df[["scout_name", "rating"]].rename(columns={"scout_name": "Jogadores"})
    rated_games = df.merge(player_ratings, on="Jogadores", how="left")

    player_summary = (
        rated_games.groupby(["Jogadores", "rating"], as_index=False)
        .agg(
            Jogos_ult6=("Data", "count"),
            Participacoes_ult6=("participacoes", "sum"),
        )
    )
    player_summary["Participacao_real_pg"] = (
        player_summary["Participacoes_ult6"] / player_summary["Jogos_ult6"].clip(lower=1)
    )

    global_mean = player_summary["Participacao_real_pg"].mean()
    rating_baseline = (
        player_summary.groupby("rating", as_index=False)
        .agg(
            Participacao_media_nota=("Participacao_real_pg", "mean"),
            Participacao_std_nota=("Participacao_real_pg", "std"),
            Jogadores_na_faixa=("Jogadores", "count"),
        )
    )
    rating_baseline["Participacao_std_nota"] = rating_baseline["Participacao_std_nota"].fillna(0)
    rating_baseline["Participacao_esperada_pg_nota"] = (
        rating_baseline["Participacao_media_nota"] * rating_baseline["Jogadores_na_faixa"] + global_mean * 2
    ) / (rating_baseline["Jogadores_na_faixa"] + 2)

    player_summary = player_summary.merge(rating_baseline, on="rating", how="left")
    player_summary["Delta_participacao_vs_nota"] = (
        player_summary["Participacao_real_pg"] - player_summary["Participacao_esperada_pg_nota"]
    )
    player_summary["Z_participacao_vs_nota"] = player_summary.apply(
        lambda row: 0
        if pd.isna(row["Participacao_std_nota"]) or row["Participacao_std_nota"] == 0
        else row["Delta_participacao_vs_nota"] / row["Participacao_std_nota"],
        axis=1,
    )
    return player_summary


def evaluate_recommendation(row: pd.Series) -> dict:
    current = None if pd.isna(row.get("rating")) else int(row["rating"])
    impact = row.get("Impacto_ajustado")
    position = row.get("Posicao")
    jogos = row.get("Jogos_ult6", 0)
    top_recent = bool(row.get("Top_recent", False))
    bottom_recent = bool(row.get("Bottom_recent", False))
    participacao_real_pg = row.get("Participacao_real_pg")
    participacao_esperada = row.get("Participacao_esperada_pg_nota")
    delta_participacao = row.get("Delta_participacao_vs_nota")

    metrics = {
        "nota_atual": current,
        "impacto_ajustado": None if pd.isna(impact) else float(impact),
        "posicao_modelo_recente": None if pd.isna(position) else int(position),
        "jogos_ult6": None if pd.isna(jogos) else int(jogos),
        "top_recent": top_recent,
        "bottom_recent": bottom_recent,
        "participacao_real_pg": None if pd.isna(participacao_real_pg) else float(participacao_real_pg),
        "participacao_esperada_pg_nota": None if pd.isna(participacao_esperada) else float(participacao_esperada),
        "delta_participacao_vs_nota": None if pd.isna(delta_participacao) else float(delta_participacao),
    }

    if current is None or pd.isna(impact) or pd.isna(position) or jogos < 3:
        return {
            "metrics": metrics,
            "flags": {
                "amostra_minima_ok": False,
                "ataque_ok": None,
                "ataque_forte": None,
                "ataque_fraco": None,
                "ataque_muito_fraco": None,
                "strong_up": False,
                "moderate_up": False,
                "strong_down": False,
                "moderate_down": False,
            },
            "thresholds": {
                "subida_principal": "top_recent = True, impacto >= 0.20, ataque_ok = True, nota_atual < 7",
                "subida_secundaria": "posicao <= 10, impacto >= 0.35, ataque_forte = True, nota_atual < 7",
                "descida_principal": "bottom_recent = True, impacto <= -0.20, ataque_fraco = True, nota_atual > 1",
                "descida_secundaria": (
                    "(impacto <= -0.50, posicao >= 10, nota_atual >= 4, ataque_fraco = True) "
                    "ou (nota_atual >= 5, ataque_muito_fraco = True, impacto <= 0)"
                ),
            },
            "decision": {
                "nova_nota_sugerida": current,
                "sinal": "manter",
                "justificativa": "Sem amostra minima no recorte das ultimas 6 peladas.",
                "regra_acionada": "amostra_insuficiente",
            },
        }

    ataque_ok = pd.isna(delta_participacao) or delta_participacao > -0.3
    ataque_forte = not pd.isna(delta_participacao) and delta_participacao >= 0.35
    ataque_fraco = not pd.isna(delta_participacao) and delta_participacao <= -0.35
    ataque_muito_fraco = not pd.isna(delta_participacao) and delta_participacao <= -0.75

    strong_up = top_recent and impact >= 0.2 and ataque_ok and current < 7
    moderate_up = position <= 10 and impact >= 0.35 and ataque_forte and current < 7
    strong_down = bottom_recent and impact <= -0.2 and ataque_fraco and current > 1
    moderate_down = (impact <= -0.5 and position >= 10 and current >= 4 and ataque_fraco) or (
        current >= 5 and ataque_muito_fraco and impact <= 0
    )

    participacao_trecho = ""
    if not pd.isna(participacao_real_pg) and not pd.isna(participacao_esperada):
        participacao_trecho = (
            f" Produziu {participacao_real_pg:.2f} participacoes por jogo, contra {participacao_esperada:.2f} "
            f"esperadas para a faixa de nota {current}."
        )

    if strong_up or moderate_up:
        new_rating = min(7, current + 1)
        reason = (
            f"Classificacao recente como criterio principal: ficou na posicao {int(position)} e ajudou seus times a renderem "
            f"acima do esperado, com impacto ajustado de {impact:.2f} nas ultimas 6 peladas."
            f"{participacao_trecho}"
        )
        regra = "strong_up" if strong_up else "moderate_up"
        signal = "subir"
    elif strong_down or moderate_down:
        new_rating = max(1, current - 1)
        reason = (
            f"Classificacao recente como criterio principal: ficou na posicao {int(position)} e o impacto ajustado foi "
            f"{impact:.2f}, sinalizando rendimento abaixo do esperado no recorte recente."
            f"{participacao_trecho}"
        )
        regra = "strong_down" if strong_down else "moderate_down"
        signal = "descer"
    else:
        new_rating = current
        reason = (
            f"Classificacao recente segue compativel com a nota atual: posicao {int(position)} e impacto ajustado de {impact:.2f} "
            f"sem sinal forte para ajuste."
            f"{participacao_trecho}"
        )
        regra = "manter"
        signal = "manter"

    return {
        "metrics": metrics,
        "flags": {
            "amostra_minima_ok": True,
            "ataque_ok": ataque_ok,
            "ataque_forte": ataque_forte,
            "ataque_fraco": ataque_fraco,
            "ataque_muito_fraco": ataque_muito_fraco,
            "strong_up": strong_up,
            "moderate_up": moderate_up,
            "strong_down": strong_down,
            "moderate_down": moderate_down,
        },
        "thresholds": {
            "subida_principal": "top_recent = True, impacto >= 0.20, ataque_ok = True, nota_atual < 7",
            "subida_secundaria": "posicao <= 10, impacto >= 0.35, ataque_forte = True, nota_atual < 7",
            "descida_principal": "bottom_recent = True, impacto <= -0.20, ataque_fraco = True, nota_atual > 1",
            "descida_secundaria": (
                "(impacto <= -0.50, posicao >= 10, nota_atual >= 4, ataque_fraco = True) "
                "ou (nota_atual >= 5, ataque_muito_fraco = True, impacto <= 0)"
            ),
        },
        "decision": {
            "nova_nota_sugerida": new_rating,
            "sinal": signal,
            "justificativa": reason,
            "regra_acionada": regra,
        },
    }


def suggest_row(row: pd.Series) -> tuple[int, str, str]:
    evaluation = evaluate_recommendation(row)
    decision = evaluation["decision"]
    return decision["nova_nota_sugerida"], decision["sinal"], decision["justificativa"]


def build_html(df: pd.DataFrame) -> str:
    table = df.copy()
    table["tem_mudanca"] = (
        table["sinal"].fillna("manter").ne("manter")
        | table["nova_nota_sugerida"].fillna(table["nota_atual"]).ne(table["nota_atual"])
    )
    numeric_cols = [
        "Impacto_ajustado",
        "participacao_real_pg",
        "participacao_esperada_pg_nota",
        "delta_participacao_vs_nota",
    ]
    for col in numeric_cols:
        table[col] = table[col].map(lambda x: "" if pd.isna(x) else f"{x:.2f}")
    rows_html = []
    columns = table.columns.tolist()
    display_columns = [col for col in columns if col != "tem_mudanca"]

    for _, row in table.iterrows():
        row_class = "has-change" if bool(row["tem_mudanca"]) else "no-change"
        cells = "".join(f"<td>{row[col]}</td>" for col in display_columns)
        rows_html.append(f'<tr class="{row_class}">{cells}</tr>')

    header_html = "".join(f"<th>{col}</th>" for col in display_columns)
    body_html = "\n".join(rows_html)
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
    .controls {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
      margin-bottom: 14px;
    }}
    .toggle {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-weight: 600;
      cursor: pointer;
    }}
    .toggle input {{
      width: 16px;
      height: 16px;
      accent-color: #1e8449;
    }}
    .helper {{
      color: #5b6673;
      font-size: 14px;
    }}
    body.only-changes .table tbody tr.no-change {{
      display: none;
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
      <div class="controls">
        <label class="toggle" for="onlyChanges">
          <input id="onlyChanges" type="checkbox">
          Mostrar apenas jogadores com sugestão de mudança
        </label>
        <span class="helper">O filtro esconde recomendações de manter nota.</span>
      </div>
      <table class="table">
        <thead>
          <tr>{header_html}</tr>
        </thead>
        <tbody>
          {body_html}
        </tbody>
      </table>
    </section>
  </main>
  <script>
    const onlyChanges = document.getElementById("onlyChanges");
    onlyChanges.addEventListener("change", () => {{
      document.body.classList.toggle("only-changes", onlyChanges.checked);
    }});
  </script>
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
    participation_baseline = build_participation_baseline(recent_df, players_df)

    result = players_df.merge(
        recent_form[
            [
                "Jogadores",
                "Posicao",
                "Nota_final",
                "Participacoes_ult4",
                "Media_classificacao",
                "Jogos_considerados",
                "Top_recent",
                "Bottom_recent",
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
    ).merge(
        participation_baseline[
            [
                "Jogadores",
                "Participacao_real_pg",
                "Participacao_esperada_pg_nota",
                "Delta_participacao_vs_nota",
                "Z_participacao_vs_nota",
                "Jogadores_na_faixa",
            ]
        ],
        left_on="scout_name",
        right_on="Jogadores",
        how="left",
        suffixes=("", "_baseline"),
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
            "Participacao_real_pg",
            "Participacao_esperada_pg_nota",
            "Delta_participacao_vs_nota",
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
            "Participacao_real_pg": "participacao_real_pg",
            "Participacao_esperada_pg_nota": "participacao_esperada_pg_nota",
            "Delta_participacao_vs_nota": "delta_participacao_vs_nota",
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
