import json
from pathlib import Path

import pandas as pd

import aliases as alias_lib
from pixotada_dashboard import BASE_DIR, OUTPUT_DIR, PUBLIC_DIR, PLAYERS_FILE, load_data
from pixotada_scores import MODELS, RECENCY_WEIGHTS, last4_games, score_model


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


def load_players() -> pd.DataFrame:
    players = json.loads(PLAYERS_FILE.read_text(encoding="utf-8-sig"))
    players_df = pd.DataFrame(players)
    players_df["name_norm"] = players_df["name"].map(alias_lib.normalize_name)
    players_df["scout_name"] = players_df["name_norm"].map(alias_lib.ALIASES).fillna(players_df["name"])
    return players_df


def build_recent_form(df: pd.DataFrame, player_names: list[str]) -> pd.DataFrame:
    recent4 = (
        df[df["Jogadores"].isin(player_names)]
        .sort_values(["Jogadores", "Data"], ascending=[True, False])
        .assign(Recencia=lambda x: x.groupby("Jogadores").cumcount() + 1)
        .loc[lambda x: x["Recencia"] <= 4]
        .copy()
    )
    recent4["Peso_recencia"] = recent4["Recencia"].map(RECENCY_WEIGHTS)
    ranking, _ = score_model(recent4, "equilibrado", MODELS["equilibrado"])
    ranking["Top_recent"] = ranking["Posicao"] <= max(1, round(len(ranking) * 0.35))
    ranking["Bottom_recent"] = ranking["Posicao"] >= max(1, len(ranking) - round(len(ranking) * 0.35) + 1)
    return ranking


def build_pre_match_expected_results(history_df: pd.DataFrame, evaluation_df: pd.DataFrame) -> pd.DataFrame:
    model_config = MODELS["equilibrado"]
    evaluated_matches = []
    history_df = history_df.copy()
    evaluation_df = evaluation_df.copy()
    history_df.attrs = {}
    evaluation_df.attrs = {}

    for match_date in sorted(evaluation_df["Data"].drop_duplicates()):
        prior_df = history_df.loc[history_df["Data"] < match_date].copy()
        prior_df.attrs = {}
        if prior_df.empty:
            strength_map = {}
        else:
            ranking, _ = score_model(last4_games(prior_df), "equilibrado", model_config)
            strength_map = dict(zip(ranking["Jogadores"], ranking["Nota_final"]))

        match_rows = evaluation_df.loc[evaluation_df["Data"] == match_date].copy()
        match_rows.attrs = {}
        match_rows["forca_observada"] = match_rows["Jogadores"].map(strength_map).fillna(0)
        evaluated_matches.append(match_rows)

    data = pd.concat(evaluated_matches, ignore_index=True) if evaluated_matches else evaluation_df.iloc[0:0].copy()
    data["actual_points"] = data["classificacao_norm"].map(ACTUAL_POINTS)

    team_strength = (
        data.groupby(["Data", "Time"], as_index=False)
        .agg(
            team_strength=("forca_observada", "sum"),
            actual_points=("actual_points", "first"),
            classificacao=("classificacao_norm", "first"),
            gols_time=("gols_time", "first"),
            gols_sofridos=("gols_sofridos", "first"),
            jogos_sem_sofrer=("jogos_sem_sofrer", "first"),
        )
    )
    team_strength["expected_rank"] = team_strength.groupby("Data")["team_strength"].rank(method="dense", ascending=False)
    team_strength["expected_points"] = team_strength["expected_rank"].map(EXPECTED_POINTS_MAP).fillna(1)
    team_strength["delta_points"] = team_strength["actual_points"] - team_strength["expected_points"]
    expected_profile = (
        team_strength.groupby("expected_rank", as_index=False)
        .agg(
            expected_gols_time=("gols_time", "mean"),
            expected_gols_sofridos=("gols_sofridos", "mean"),
            expected_jogos_sem_sofrer=("jogos_sem_sofrer", "mean"),
        )
    )
    team_strength = team_strength.merge(expected_profile, on="expected_rank", how="left")
    team_strength["delta_gols_time"] = team_strength["gols_time"] - team_strength["expected_gols_time"]
    team_strength["delta_gols_sofridos"] = team_strength["expected_gols_sofridos"] - team_strength["gols_sofridos"]
    team_strength["delta_jogos_sem_sofrer"] = (
        team_strength["jogos_sem_sofrer"] - team_strength["expected_jogos_sem_sofrer"]
    )

    data = data.merge(
        team_strength[
            [
                "Data",
                "Time",
                "expected_points",
                "delta_points",
                "team_strength",
                "expected_gols_time",
                "expected_gols_sofridos",
                "expected_jogos_sem_sofrer",
                "delta_gols_time",
                "delta_gols_sofridos",
                "delta_jogos_sem_sofrer",
            ]
        ],
        on=["Data", "Time"],
        how="left",
    )
    return data


def build_adjusted_impact(history_df: pd.DataFrame, evaluation_df: pd.DataFrame) -> pd.DataFrame:
    data = build_pre_match_expected_results(history_df, evaluation_df)
    summary = (
        data.groupby("Jogadores", as_index=False)
        .agg(
            Jogos_ult6=("Data", "count"),
            Participacoes_ult6=("participacoes", "sum"),
            Media_participacoes=("participacoes", "mean"),
            Impacto_ajustado=("delta_points", "mean"),
            Impacto_bruto=("actual_points", "mean"),
            Expected_points_medios=("expected_points", "mean"),
            Gols_time_pg=("gols_time", "mean"),
            Gols_sofridos_pg=("gols_sofridos", "mean"),
            Jogos_sem_sofrer_pg=("jogos_sem_sofrer", "mean"),
            Impacto_gols_time=("delta_gols_time", "mean"),
            Impacto_gols_sofridos=("delta_gols_sofridos", "mean"),
            Impacto_jogos_sem_sofrer=("delta_jogos_sem_sofrer", "mean"),
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


def build_collective_baseline(df: pd.DataFrame, players_df: pd.DataFrame) -> pd.DataFrame:
    player_ratings = players_df[["scout_name", "rating"]].rename(columns={"scout_name": "Jogadores"})
    rated_games = df.merge(player_ratings, on="Jogadores", how="left")

    player_summary = (
        rated_games.groupby(["Jogadores", "rating"], as_index=False)
        .agg(
            Jogos_ult6=("Data", "count"),
            Gols_time_pg=("gols_time", "mean"),
            Gols_sofridos_pg=("gols_sofridos", "mean"),
            Jogos_sem_sofrer_pg=("jogos_sem_sofrer", "mean"),
        )
    )

    global_profile = {
        "Gols_time_pg": player_summary["Gols_time_pg"].mean(),
        "Gols_sofridos_pg": player_summary["Gols_sofridos_pg"].mean(),
        "Jogos_sem_sofrer_pg": player_summary["Jogos_sem_sofrer_pg"].mean(),
    }

    baseline = (
        player_summary.groupby("rating", as_index=False)
        .agg(
            Gols_time_medio_nota=("Gols_time_pg", "mean"),
            Gols_sofridos_medio_nota=("Gols_sofridos_pg", "mean"),
            Jogos_sem_sofrer_medio_nota=("Jogos_sem_sofrer_pg", "mean"),
            Jogadores_na_faixa=("Jogadores", "count"),
        )
    )
    shrink = baseline["Jogadores_na_faixa"] + 2
    baseline["Gols_time_esperados_pg_nota"] = (
        baseline["Gols_time_medio_nota"] * baseline["Jogadores_na_faixa"] + global_profile["Gols_time_pg"] * 2
    ) / shrink
    baseline["Gols_sofridos_esperados_pg_nota"] = (
        baseline["Gols_sofridos_medio_nota"] * baseline["Jogadores_na_faixa"] + global_profile["Gols_sofridos_pg"] * 2
    ) / shrink
    baseline["Jogos_sem_sofrer_esperados_pg_nota"] = (
        baseline["Jogos_sem_sofrer_medio_nota"] * baseline["Jogadores_na_faixa"]
        + global_profile["Jogos_sem_sofrer_pg"] * 2
    ) / shrink

    player_summary = player_summary.merge(baseline, on="rating", how="left", suffixes=("", "_baseline"))
    player_summary["Delta_gols_time_vs_nota"] = (
        player_summary["Gols_time_pg"] - player_summary["Gols_time_esperados_pg_nota"]
    )
    player_summary["Delta_gols_sofridos_vs_nota"] = (
        player_summary["Gols_sofridos_pg"] - player_summary["Gols_sofridos_esperados_pg_nota"]
    )
    player_summary["Delta_jogos_sem_sofrer_vs_nota"] = (
        player_summary["Jogos_sem_sofrer_pg"] - player_summary["Jogos_sem_sofrer_esperados_pg_nota"]
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
    gols_time_pg = row.get("Gols_time_pg")
    gols_time_esperados = row.get("Gols_time_esperados_pg_nota")
    delta_gols_time = row.get("Delta_gols_time_vs_nota")
    gols_sofridos_pg = row.get("Gols_sofridos_pg")
    gols_sofridos_esperados = row.get("Gols_sofridos_esperados_pg_nota")
    delta_gols_sofridos = row.get("Delta_gols_sofridos_vs_nota")
    jogos_sem_sofrer_pg = row.get("Jogos_sem_sofrer_pg")
    jogos_sem_sofrer_esperados = row.get("Jogos_sem_sofrer_esperados_pg_nota")
    delta_clean_sheet = row.get("Delta_jogos_sem_sofrer_vs_nota")
    impacto_gols_time = row.get("Impacto_gols_time")
    impacto_gols_sofridos = row.get("Impacto_gols_sofridos")
    impacto_clean_sheet = row.get("Impacto_jogos_sem_sofrer")

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
        "gols_time_pg": None if pd.isna(gols_time_pg) else float(gols_time_pg),
        "gols_time_esperados_pg_nota": None if pd.isna(gols_time_esperados) else float(gols_time_esperados),
        "delta_gols_time_vs_nota": None if pd.isna(delta_gols_time) else float(delta_gols_time),
        "gols_sofridos_pg": None if pd.isna(gols_sofridos_pg) else float(gols_sofridos_pg),
        "gols_sofridos_esperados_pg_nota": None
        if pd.isna(gols_sofridos_esperados)
        else float(gols_sofridos_esperados),
        "delta_gols_sofridos_vs_nota": None if pd.isna(delta_gols_sofridos) else float(delta_gols_sofridos),
        "jogos_sem_sofrer_pg": None if pd.isna(jogos_sem_sofrer_pg) else float(jogos_sem_sofrer_pg),
        "jogos_sem_sofrer_esperados_pg_nota": None
        if pd.isna(jogos_sem_sofrer_esperados)
        else float(jogos_sem_sofrer_esperados),
        "delta_jogos_sem_sofrer_vs_nota": None if pd.isna(delta_clean_sheet) else float(delta_clean_sheet),
        "impacto_gols_time": None if pd.isna(impacto_gols_time) else float(impacto_gols_time),
        "impacto_gols_sofridos": None if pd.isna(impacto_gols_sofridos) else float(impacto_gols_sofridos),
        "impacto_jogos_sem_sofrer": None if pd.isna(impacto_clean_sheet) else float(impacto_clean_sheet),
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
                "coletivo_ok": None,
                "coletivo_forte": None,
                "coletivo_fraco": None,
                "strong_up": False,
                "moderate_up": False,
                "strong_down": False,
                "moderate_down": False,
            },
            "thresholds": {
                "subida_principal": (
                    "top_recent = True, impacto >= 0.20, ataque_ok = True, coletivo_ok = True, nota_atual < 7"
                ),
                "subida_secundaria": (
                    "posicao <= 10, impacto >= 0.35, ataque_forte = True, coletivo_forte = True, nota_atual < 7"
                ),
                "descida_principal": (
                    "bottom_recent = True, impacto <= -0.20, ataque_fraco = True, coletivo_fraco = True, nota_atual > 1"
                ),
                "descida_secundaria": (
                    "(impacto <= -0.50, posicao >= 10, nota_atual >= 4, ataque_fraco = True, coletivo_fraco = True) "
                    "ou (nota_atual >= 5, ataque_muito_fraco = True, impacto <= 0, coletivo_ok = False)"
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
    gols_time_ok = pd.isna(delta_gols_time) or delta_gols_time >= -0.2
    gols_time_forte = not pd.isna(delta_gols_time) and delta_gols_time >= 0.35
    gols_sofridos_ok = pd.isna(delta_gols_sofridos) or delta_gols_sofridos <= 0.2
    gols_sofridos_ruim = not pd.isna(delta_gols_sofridos) and delta_gols_sofridos >= 0.35
    clean_sheet_ok = pd.isna(delta_clean_sheet) or delta_clean_sheet >= -0.08
    clean_sheet_forte = not pd.isna(delta_clean_sheet) and delta_clean_sheet >= 0.12

    coletivo_ok = gols_time_ok and (gols_sofridos_ok or clean_sheet_ok)
    coletivo_forte = gols_time_forte and (not gols_sofridos_ruim or clean_sheet_forte)
    coletivo_fraco = (not gols_time_ok) and (gols_sofridos_ruim or not clean_sheet_ok)

    strong_up = top_recent and impact >= 0.2 and ataque_ok and coletivo_ok and current < 7
    moderate_up = position <= 10 and impact >= 0.35 and ataque_forte and coletivo_forte and current < 7
    strong_down = bottom_recent and impact <= -0.2 and ataque_fraco and coletivo_fraco and current > 1
    moderate_down = (impact <= -0.5 and position >= 10 and current >= 4 and ataque_fraco and coletivo_fraco) or (
        current >= 5 and ataque_muito_fraco and impact <= 0 and not coletivo_ok
    )

    participacao_trecho = ""
    if not pd.isna(participacao_real_pg) and not pd.isna(participacao_esperada):
        participacao_trecho = (
            f" Produziu {participacao_real_pg:.2f} participacoes por jogo, contra {participacao_esperada:.2f} "
            f"esperadas para a faixa de nota {current}."
        )
    coletivo_trecho = ""
    if not pd.isna(gols_time_pg) and not pd.isna(gols_sofridos_pg) and not pd.isna(jogos_sem_sofrer_pg):
        coletivo_trecho = (
            f" Seus times tiveram media de {gols_time_pg:.2f} gols marcados, {gols_sofridos_pg:.2f} sofridos "
            f"e {jogos_sem_sofrer_pg:.2f} jogos sem sofrer gols por aparicao."
        )

    if strong_up or moderate_up:
        new_rating = min(7, current + 1)
        reason = (
            f"Classificacao recente como criterio principal: ficou na posicao {int(position)} e ajudou seus times a renderem "
            f"acima do esperado, com impacto ajustado de {impact:.2f} nas ultimas 6 peladas."
            f"{participacao_trecho}"
            f"{coletivo_trecho}"
        )
        regra = "strong_up" if strong_up else "moderate_up"
        signal = "subir"
    elif strong_down or moderate_down:
        new_rating = max(1, current - 1)
        reason = (
            f"Classificacao recente como criterio principal: ficou na posicao {int(position)} e o impacto ajustado foi "
            f"{impact:.2f}, sinalizando rendimento abaixo do esperado no recorte recente."
            f"{participacao_trecho}"
            f"{coletivo_trecho}"
        )
        regra = "strong_down" if strong_down else "moderate_down"
        signal = "descer"
    else:
        new_rating = current
        reason = (
            f"Classificacao recente segue compativel com a nota atual: posicao {int(position)} e impacto ajustado de {impact:.2f} "
            f"sem sinal forte para ajuste."
            f"{participacao_trecho}"
            f"{coletivo_trecho}"
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
            "coletivo_ok": coletivo_ok,
            "coletivo_forte": coletivo_forte,
            "coletivo_fraco": coletivo_fraco,
            "strong_up": strong_up,
            "moderate_up": moderate_up,
            "strong_down": strong_down,
            "moderate_down": moderate_down,
        },
        "thresholds": {
            "subida_principal": (
                "top_recent = True, impacto >= 0.20, ataque_ok = True, coletivo_ok = True, nota_atual < 7"
            ),
            "subida_secundaria": (
                "posicao <= 10, impacto >= 0.35, ataque_forte = True, coletivo_forte = True, nota_atual < 7"
            ),
            "descida_principal": (
                "bottom_recent = True, impacto <= -0.20, ataque_fraco = True, coletivo_fraco = True, nota_atual > 1"
            ),
            "descida_secundaria": (
                "(impacto <= -0.50, posicao >= 10, nota_atual >= 4, ataque_fraco = True, coletivo_fraco = True) "
                "ou (nota_atual >= 5, ataque_muito_fraco = True, impacto <= 0, coletivo_ok = False)"
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
    table["tem_amostra"] = table["jogos_ult6"].fillna(0).ge(3)

    def leitura_label(value: float | None) -> str:
        if pd.isna(value):
            return "Sem partidas suficientes"
        if value >= 1:
            return "Muito acima do esperado"
        if value >= 0.35:
            return "Acima do esperado"
        if value <= -1:
            return "Muito abaixo do esperado"
        if value <= -0.35:
            return "Abaixo do esperado"
        return "Dentro do esperado"

    def resumo_texto(row: pd.Series) -> str:
        if not bool(row["tem_amostra"]):
            return "Ainda nao ha partidas suficientes no recorte recente para recomendar mudanca."
        gols_time = row["gols_time_pg"]
        gols_sofridos = row["gols_sofridos_pg"]
        if row["sinal"] == "subir":
            return (
                f"Tem jogado acima do esperado. Seus times fizeram {gols_time:.2f} gols por jogo "
                f"e sofreram {gols_sofridos:.2f} com ele em campo."
            )
        if row["sinal"] == "descer":
            return (
                f"O recorte recente ficou abaixo do esperado. Seus times fizeram {gols_time:.2f} gols por jogo "
                f"e sofreram {gols_sofridos:.2f} com ele em campo."
            )
        return (
            f"Nao ha evidencia forte para mudar a nota. Seus times fizeram {gols_time:.2f} gols por jogo "
            f"e sofreram {gols_sofridos:.2f} no recorte recente."
        )

    table["Jogador"] = table["jogador_scout"].fillna(table["jogador_json"])
    table["Nota atual"] = table["nota_atual"].map(lambda value: "" if pd.isna(value) else int(value))
    table["Sugestao"] = table["nova_nota_sugerida"].map(lambda value: "" if pd.isna(value) else int(value))
    table["Mudanca"] = table["sinal"].map({"subir": "Subir", "descer": "Descer", "manter": "Manter"}).fillna("Manter")
    table["Jogos recentes"] = table["jogos_ult6"].map(lambda value: "" if pd.isna(value) else int(value))
    table["Desempenho recente"] = table["Impacto_ajustado"].map(leitura_label)
    table["Resumo"] = table.apply(resumo_texto, axis=1)
    table["Detalhe"] = '<a href="detalhe_recomendacoes_notas.html">Abrir</a>'

    display_table = table.loc[table["tem_amostra"]].copy()
    display_table = display_table.sort_values(
        ["tem_mudanca", "Mudanca", "Jogos recentes", "Jogador"],
        ascending=[False, True, False, True],
    )

    change_counts = display_table["Mudanca"].value_counts().to_dict()
    without_sample = int((~table["tem_amostra"]).sum())
    rows_html = []
    display_columns = [
        "Jogador",
        "Nota atual",
        "Sugestao",
        "Mudanca",
        "Jogos recentes",
        "Desempenho recente",
        "Resumo",
        "Detalhe",
    ]

    for _, row in display_table.iterrows():
        row_class = "has-change" if bool(row["tem_mudanca"]) else "no-change"
        change_class = str(row["Mudanca"]).lower()
        cells = []
        for column in display_columns:
            value = row[column]
            if column == "Mudanca":
                value = f'<span class="badge {change_class}">{value}</span>'
            elif column == "Desempenho recente":
                value = f'<span class="badge neutral">{value}</span>'
            cells.append(f"<td>{value}</td>")
        rows_html.append(f'<tr class="{row_class}">{"".join(cells)}</tr>')

    header_html = "".join(f"<th>{col}</th>" for col in display_columns)
    body_html = "\n".join(rows_html)
    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Sugestao de notas</title>
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
    .table-wrap {{
      max-height: 720px;
      overflow: auto;
      border: 1px solid #eadfc9;
      border-radius: 16px;
      background: #fff;
    }}
    .table th, .table td {{
      border-bottom: 1px solid #eadfc9;
      padding: 10px 8px;
      text-align: left;
      vertical-align: top;
    }}
    .table th {{
      background: #f6efe2;
      position: sticky;
      top: 0;
      z-index: 2;
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
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 20px;
    }}
    .summary-card {{
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px solid #eadfc9;
      background: #fffaf1;
    }}
    .summary-card strong {{
      display: block;
      font-size: 28px;
      margin-top: 4px;
    }}
    .badge {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      font-weight: 700;
      font-size: 13px;
      white-space: nowrap;
    }}
    .badge.subir {{
      background: #e8f6f3;
      color: #117864;
    }}
    .badge.descer {{
      background: #fdecea;
      color: #922b21;
    }}
    .badge.manter, .badge.neutral {{
      background: #f6efe2;
      color: #6b5b45;
    }}
    body.only-changes .table tbody tr.no-change {{
      display: none;
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Sugestao de notas</h1>
      <p>Esta pagina resume a decisao principal sobre nota: subir, manter ou descer.</p>
      <p>So aparecem na tabela principal os jogadores com pelo menos 3 jogos nas ultimas 6 peladas.</p>
      <div class="nav">
        <a href="dashboard_pixotada_2026.html">Dashboard</a>
        <a href="ranking_geral_jogadores.html">Ranking geral</a>
        <a href="ranking_modelos_ultimas4.html">Modelos de pontuação</a>
        <a href="premiacao_mensal.html">Premiação mensal</a>
        <a href="efeito_jogadores.html">Efeito dos jogadores</a>
        <a href="sugestao_novas_notas.html">Sugestão de notas</a>
        <a href="detalhe_recomendacoes_notas.html">Detalhe das recomendações</a>
      </div>
      <div class="summary-grid">
        <div class="summary-card">
          <span>Subir nota</span>
          <strong>{change_counts.get("Subir", 0)}</strong>
        </div>
        <div class="summary-card">
          <span>Descer nota</span>
          <strong>{change_counts.get("Descer", 0)}</strong>
        </div>
        <div class="summary-card">
          <span>Manter nota</span>
          <strong>{change_counts.get("Manter", 0)}</strong>
        </div>
        <div class="summary-card">
          <span>Sem partidas suficientes</span>
          <strong>{without_sample}</strong>
        </div>
      </div>
    </section>
    <section class="card" style="margin-top:20px;">
      <div class="controls">
        <label class="toggle" for="onlyChanges">
          <input id="onlyChanges" type="checkbox" checked>
          Mostrar apenas jogadores com mudanca de nota
        </label>
        <span class="helper">Use a pagina de detalhe para ver a memoria completa de calculo.</span>
      </div>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>{header_html}</tr>
          </thead>
          <tbody>
            {body_html}
          </tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    const onlyChanges = document.getElementById("onlyChanges");
    document.body.classList.toggle("only-changes", onlyChanges.checked);
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
    adjusted = build_adjusted_impact(scout_df, recent_df)
    participation_baseline = build_participation_baseline(recent_df, players_df)
    collective_baseline = build_collective_baseline(recent_df, players_df)

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
    ).merge(
        collective_baseline[
            [
                "Jogadores",
                "Gols_time_pg",
                "Gols_sofridos_pg",
                "Jogos_sem_sofrer_pg",
                "Gols_time_esperados_pg_nota",
                "Gols_sofridos_esperados_pg_nota",
                "Jogos_sem_sofrer_esperados_pg_nota",
                "Delta_gols_time_vs_nota",
                "Delta_gols_sofridos_vs_nota",
                "Delta_jogos_sem_sofrer_vs_nota",
            ]
        ],
        left_on="scout_name",
        right_on="Jogadores",
        how="left",
        suffixes=("", "_collective"),
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
            "Impacto_gols_time",
            "Impacto_gols_sofridos",
            "Impacto_jogos_sem_sofrer",
            "Participacao_real_pg",
            "Participacao_esperada_pg_nota",
            "Delta_participacao_vs_nota",
            "Gols_time_pg",
            "Gols_time_esperados_pg_nota",
            "Delta_gols_time_vs_nota",
            "Gols_sofridos_pg",
            "Gols_sofridos_esperados_pg_nota",
            "Delta_gols_sofridos_vs_nota",
            "Jogos_sem_sofrer_pg",
            "Jogos_sem_sofrer_esperados_pg_nota",
            "Delta_jogos_sem_sofrer_vs_nota",
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
            "Gols_time_pg": "gols_time_pg",
            "Gols_time_esperados_pg_nota": "gols_time_esperados_pg_nota",
            "Delta_gols_time_vs_nota": "delta_gols_time_vs_nota",
            "Gols_sofridos_pg": "gols_sofridos_pg",
            "Gols_sofridos_esperados_pg_nota": "gols_sofridos_esperados_pg_nota",
            "Delta_gols_sofridos_vs_nota": "delta_gols_sofridos_vs_nota",
            "Jogos_sem_sofrer_pg": "jogos_sem_sofrer_pg",
            "Jogos_sem_sofrer_esperados_pg_nota": "jogos_sem_sofrer_esperados_pg_nota",
            "Delta_jogos_sem_sofrer_vs_nota": "delta_jogos_sem_sofrer_vs_nota",
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
