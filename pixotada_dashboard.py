from pathlib import Path
import json
import re
import unicodedata

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

import aliases as alias_lib


SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR
DESKTOP_DIR = SCRIPT_DIR.parent
DATA_DIR = SCRIPT_DIR / "data"
INPUT_FILE = DATA_DIR / "SCOUTS PIXOTADA 2026 - BASE.csv"
PLAYERS_FILE = DATA_DIR / "players.json"
CHAT_FILE = DESKTOP_DIR / "pixotada_2026_dashboard" / "Conversa do WhatsApp com Pelada - Pixotada FC.txt"
OUTPUT_DIR = DESKTOP_DIR / "pixotada_2026_dashboard"
PUBLIC_DIR = BASE_DIR

POSITION_ORDER = ["Lanterna", "Terceiro", "Segundo", "Campeao"]
POSITION_LABELS = {
    "Lanterna": "Lanterna",
    "Terceiro": "Terceiro",
    "Segundo": "Segundo",
    "Campeao": "Campe\u00e3o",
}
POSITION_COLORS = {
    "Lanterna": "#922b21",
    "Terceiro": "#d35400",
    "Segundo": "#2874a6",
    "Campeao": "#1e8449",
}
MIN_GAMES_DEFENSIVE_AVG = 3

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

MANUAL_PELADA_RESULTS = {
    "12/01/2026": {
        "team_map": {
            "guilherme": 1,
            "azul": 1,
            "serginho": 2,
            "vermelho": 2,
            "luquinhas": 3,
            "branco": 3,
            "perna": 4,
            "preto": 4,
        },
        "matches": [
            ("round_robin", "guilherme", 0, "serginho", 0),
            ("round_robin", "perna", 0, "luquinhas", 1),
            ("round_robin", "serginho", 1, "perna", 0),
            ("round_robin", "guilherme", 2, "luquinhas", 1),
            ("round_robin", "serginho", 2, "luquinhas", 0),
            ("round_robin", "guilherme", 2, "perna", 3),
            ("third", "luquinhas", 2, "perna", 1),
            ("final", "guilherme", 1, "serginho", 1),
        ],
    },
    "15/01/2026": {
        "team_map": {"azul": 1, "vermelho": 2, "branco": 3, "preto": 4},
        "matches": [
            ("round_robin", "vermelho", 0, "branco", 0),
            ("round_robin", "azul", 0, "preto", 1),
            ("round_robin", "vermelho", 0, "azul", 1),
            ("round_robin", "branco", 1, "preto", 1),
            ("round_robin", "branco", 3, "azul", 5),
            ("round_robin", "preto", 2, "vermelho", 0),
            ("third", "branco", 3, "vermelho", 3),
            ("final", "preto", 0, "azul", 1),
        ],
    },
    "22/01/2026": {
        "team_map": {"dudu": 1, "guilherme": 2, "ps": 3, "monteiro": 4},
        "matches": [
            ("round_robin", "monteiro", 1, "ps", 0),
            ("round_robin", "dudu", 0, "guilherme", 1),
            ("round_robin", "monteiro", 1, "dudu", 0),
            ("round_robin", "guilherme", 0, "ps", 0),
            ("round_robin", "dudu", 2, "ps", 1),
            ("round_robin", "monteiro", 0, "guilherme", 0),
            ("third", "dudu", 2, "ps", 0),
            ("final", "monteiro", 2, "guilherme", 1),
        ],
    },
    "26/01/2026": {
        "team_map": {"claudio": 1, "dudu": 2, "ps": 3, "guilherme": 4},
        "matches": [
            ("round_robin", "claudio", 0, "guilherme", 0),
            ("round_robin", "ps", 0, "dudu", 0),
            ("round_robin", "guilherme", 1, "ps", 0),
            ("round_robin", "claudio", 0, "dudu", 1),
            ("round_robin", "claudio", 1, "ps", 3),
            ("round_robin", "dudu", 0, "guilherme", 0),
            ("third", "claudio", 4, "ps", 2),
            ("final", "guilherme", 2, "dudu", 4),
        ],
    },
    "29/01/2026": {
        "team_map": {"claudio": 1, "dudu": 2, "ps": 3, "nego": 4},
        "matches": [
            ("round_robin", "dudu", 1, "claudio", 2),
            ("round_robin", "ps", 3, "nego", 1),
            ("round_robin", "dudu", 1, "nego", 0),
            ("round_robin", "ps", 0, "claudio", 0),
            ("round_robin", "claudio", 2, "nego", 0),
            ("round_robin", "dudu", 1, "ps", 2),
            ("third", "dudu", 2, "nego", 0),
            ("final", "ps", 1, "claudio", 0),
        ],
    },
    "16/03/2026": {
        "team_map": {"serginho": 1, "pa": 2, "junior": 3, "nego": 4},
        "matches": [
            ("round_robin", "serginho", 1, "pa", 0),
            ("round_robin", "junior", 0, "nego", 2),
            ("round_robin", "serginho", 0, "nego", 0),
            ("round_robin", "pa", 0, "junior", 2),
            ("round_robin", "serginho", 1, "junior", 1),
            ("round_robin", "pa", 1, "nego", 1),
            ("third", "junior", 1, "pa", 1),
            ("final", "nego", 1, "serginho", 0),
        ],
    },
}


def normalize_text(value: str) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text


def canonical_name(value: str) -> str:
    normalized = alias_lib.normalize_name(str(value))
    return alias_lib.ALIASES.get(normalized, str(value).strip())


def normalize_token(value: str) -> str:
    text = normalize_text(value).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_whatsapp_messages(chat_text: str) -> list[dict[str, str]]:
    message_start = re.compile(r"^(\d{2}/\d{2}/\d{4}) \d{2}:\d{2} - ([^:]+):\s?(.*)$")
    messages: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for raw_line in chat_text.splitlines():
        match = message_start.match(raw_line)
        if match:
            if current is not None:
                current["text"] = current["text"].strip()
                messages.append(current)
            current = {
                "date": match.group(1),
                "author": match.group(2).strip(),
                "text": match.group(3),
            }
            continue
        if current is not None:
            current["text"] += "\n" + raw_line

    if current is not None:
        current["text"] = current["text"].strip()
        messages.append(current)

    return messages


def extract_known_names(text: str, known_names: dict[str, str]) -> set[str]:
    normalized_text = f" {normalize_token(text)} "
    found: set[str] = set()
    for token, canonical in known_names.items():
        if token and f" {token} " in normalized_text:
            found.add(canonical)
    return found


def parse_score_line(line: str) -> dict[str, object] | None:
    cleaned = normalize_token(line)
    match = re.search(r"([a-z0-9 ]+?)\s*(\d+)\s*x\s*(\d+)\s*([a-z0-9 ]+)", cleaned)
    if not match:
        return None

    left = match.group(1).strip()
    right = match.group(4).strip()
    if not left or not right:
        return None
    if left.startswith("jogo ") or right.startswith("jogo "):
        return None

    return {
        "team_a": left,
        "goals_a": int(match.group(2)),
        "team_b": right,
        "goals_b": int(match.group(3)),
    }


def parse_message_matches(message_text: str, known_names: dict[str, str]) -> list[dict[str, object]]:
    lines = [line.strip() for line in message_text.splitlines()]
    matches: list[dict[str, object]] = []
    section = ""
    index = 0

    while index < len(lines):
        line = lines[index]
        line_norm = normalize_token(line)

        if "terceiro lugar" in line_norm:
            section = "third"
            index += 1
            continue
        if "grande final" in line_norm or line_norm == "final" or line_norm == "final " or line_norm.startswith("final"):
            section = "final"
            index += 1
            continue

        score = parse_score_line(line)
        if score is None:
            index += 1
            continue

        context_lines = [line]
        lookahead = index + 1
        while lookahead < len(lines):
            next_line = lines[lookahead].strip()
            next_norm = normalize_token(next_line)
            if not next_line:
                break
            if "terceiro lugar" in next_norm or "grande final" in next_norm or next_norm == "final" or next_norm.startswith("final"):
                break
            if parse_score_line(next_line) is not None:
                break
            context_lines.append(next_line)
            lookahead += 1

        participants = tuple(sorted([score["team_a"], score["team_b"]]))
        match_id = (section or "round_robin", participants)
        matches.append(
            {
                "match_id": match_id,
                "team_a": score["team_a"],
                "goals_a": score["goals_a"],
                "team_b": score["team_b"],
                "goals_b": score["goals_b"],
                "section": section or "round_robin",
                "mentioned_players": extract_known_names("\n".join(context_lines), known_names),
            }
        )
        if section in {"final", "third"}:
            section = ""
        index = lookahead

    return matches


def append_manual_day_results(
    date_str: str,
    day_df: pd.DataFrame,
    manual_config: dict[str, object],
    team_results: list[dict[str, object]],
    team_diagnostics: list[dict[str, object]],
) -> None:
    stats_by_team = {
        int(time_id): {"gols_time": 0, "gols_sofridos": 0, "jogos_sem_sofrer": 0}
        for time_id in sorted(day_df["Time"].unique())
    }

    for _, team_a_label, goals_a, team_b_label, goals_b in manual_config["matches"]:
        team_a = int(manual_config["team_map"][team_a_label])
        team_b = int(manual_config["team_map"][team_b_label])
        stats_by_team[team_a]["gols_time"] += goals_a
        stats_by_team[team_a]["gols_sofridos"] += goals_b
        stats_by_team[team_b]["gols_time"] += goals_b
        stats_by_team[team_b]["gols_sofridos"] += goals_a
        if goals_b == 0:
            stats_by_team[team_a]["jogos_sem_sofrer"] += 1
        if goals_a == 0:
            stats_by_team[team_b]["jogos_sem_sofrer"] += 1

    team_rows = (
        day_df.groupby(["Time", "classificacao_norm"], as_index=False)
        .agg(roster=("Jogadores", list))
        .sort_values("Time")
    )
    inverse_team_map: dict[int, list[str]] = {}
    for label, time_id in manual_config["team_map"].items():
        inverse_team_map.setdefault(int(time_id), []).append(label)

    for team in team_rows.to_dict("records"):
        time_id = int(team["Time"])
        stats = stats_by_team[time_id]
        labels = ", ".join(sorted(inverse_team_map.get(time_id, [])))
        team_results.append(
            {
                "Data": pd.to_datetime(date_str, dayfirst=True),
                "Time": time_id,
                "gols_sofridos": stats["gols_sofridos"],
                "gols_time": stats["gols_time"],
                "jogos_sem_sofrer": stats["jogos_sem_sofrer"],
            }
        )
        team_diagnostics.append(
            {
                "Data": pd.to_datetime(date_str, dayfirst=True),
                "Time": time_id,
                "classificacao": team["classificacao_norm"],
                "team_label": labels,
                "mapping_score": -1,
                "mapping_confidence": -1,
                "mentioned_players": "mapeamento manual",
            }
        )


def build_match_result_df(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not CHAT_FILE.exists():
        empty_results = pd.DataFrame(columns=["Data", "Time", "gols_sofridos", "gols_time", "jogos_sem_sofrer"])
        empty_diag = pd.DataFrame(columns=["Data", "Time", "classificacao", "team_label", "mapping_score", "mapping_confidence"])
        return empty_results, empty_diag

    chat_text = CHAT_FILE.read_text(encoding="utf-8-sig")
    messages = parse_whatsapp_messages(chat_text)
    scout_dates = {date.strftime("%d/%m/%Y") for date in df["Data"].drop_duplicates()}

    known_names = {normalize_token(name): canonical_name(name) for name in sorted(df["Jogadores"].unique())}
    team_results: list[dict[str, object]] = []
    team_diagnostics: list[dict[str, object]] = []

    grouped_messages: dict[str, list[dict[str, str]]] = {}
    for message in messages:
        if message["date"] in scout_dates:
            grouped_messages.setdefault(message["date"], []).append(message)

    for date_str, day_messages in grouped_messages.items():
        day_df = df.loc[df["Data"].dt.strftime("%d/%m/%Y") == date_str].copy()

        if date_str in MANUAL_PELADA_RESULTS:
            append_manual_day_results(date_str, day_df, MANUAL_PELADA_RESULTS[date_str], team_results, team_diagnostics)
            continue

        parsed_matches: dict[tuple[str, tuple[str, str]], dict[str, object]] = {}
        for message in day_messages:
            for parsed_match in parse_message_matches(message["text"], known_names):
                parsed_matches[parsed_match["match_id"]] = parsed_match

        if len(parsed_matches) < 6:
            continue

        team_rows = (
            day_df.groupby(["Time", "classificacao_norm"], as_index=False)
            .agg(roster=("Jogadores", list))
            .sort_values("Time")
        )

        labels = sorted({parsed_match["team_a"] for parsed_match in parsed_matches.values()}.union({parsed_match["team_b"] for parsed_match in parsed_matches.values()}))

        mentions_by_label = {label: set() for label in labels}
        for parsed_match in parsed_matches.values():
            mentions_by_label[parsed_match["team_a"]].update(parsed_match["mentioned_players"])
            mentions_by_label[parsed_match["team_b"]].update(parsed_match["mentioned_players"])

        team_candidates = team_rows.to_dict("records")
        score_matrix: dict[tuple[str, int], int] = {}
        label_mapping: dict[str, dict[str, int]] = {}
        for label in labels:
            label_norm = normalize_token(label)
            label_tokens = set(label_norm.split())
            ranked_candidates: list[tuple[int, int]] = []
            for team in team_candidates:
                roster_canonical = [canonical_name(player) for player in team["roster"]]
                roster_norm = [normalize_token(player) for player in roster_canonical]
                roster_tokens = [set(name.split()) for name in roster_norm]
                exact_match = any(label_norm == player_norm for player_norm in roster_norm)
                token_match = any(label_tokens and label_tokens <= player_tokens for player_tokens in roster_tokens)
                overlap = len(set(roster_canonical) & mentions_by_label[label])
                score = overlap * 10
                if token_match:
                    score += 35
                if exact_match:
                    score += 100
                score_matrix[(label, team["Time"])] = score
                ranked_candidates.append((score, team["Time"]))

            ranked_candidates.sort(reverse=True)
            best_score, best_team = ranked_candidates[0]
            second_score = ranked_candidates[1][0] if len(ranked_candidates) > 1 else 0
            label_mapping[label] = {
                "Time": best_team,
                "score": best_score,
                "confidence": best_score - second_score,
            }

        if len({mapping["Time"] for mapping in label_mapping.values()}) != len(team_rows):
            continue

        stats_by_team = {
            team["Time"]: {"gols_time": 0, "gols_sofridos": 0, "jogos_sem_sofrer": 0}
            for team in team_candidates
        }
        mapped_matches: dict[tuple[str, tuple[int, int]], dict[str, int]] = {}
        for parsed_match in parsed_matches.values():
            team_a = label_mapping[parsed_match["team_a"]]["Time"]
            team_b = label_mapping[parsed_match["team_b"]]["Time"]
            if team_a == team_b:
                continue
            match_key = (parsed_match["section"], tuple(sorted([team_a, team_b])))
            mapped_matches[match_key] = {
                "team_a": team_a,
                "goals_a": int(parsed_match["goals_a"]),
                "team_b": team_b,
                "goals_b": int(parsed_match["goals_b"]),
            }

        if len(mapped_matches) < 6:
            continue

        for mapped_match in mapped_matches.values():
            team_a = mapped_match["team_a"]
            team_b = mapped_match["team_b"]
            goals_a = int(mapped_match["goals_a"])
            goals_b = int(mapped_match["goals_b"])
            stats_by_team[team_a]["gols_time"] += goals_a
            stats_by_team[team_a]["gols_sofridos"] += goals_b
            stats_by_team[team_b]["gols_time"] += goals_b
            stats_by_team[team_b]["gols_sofridos"] += goals_a
            if goals_b == 0:
                stats_by_team[team_a]["jogos_sem_sofrer"] += 1
            if goals_a == 0:
                stats_by_team[team_b]["jogos_sem_sofrer"] += 1

        diagnostics_by_team: dict[int, list[dict[str, int | str]]] = {}
        for label, mapping in label_mapping.items():
            diagnostics_by_team.setdefault(mapping["Time"], []).append(
                {
                    "label": label,
                    "score": mapping["score"],
                    "confidence": mapping["confidence"],
                }
            )

        for team in team_candidates:
            time_id = team["Time"]
            stats = stats_by_team[time_id]
            candidates = sorted(diagnostics_by_team.get(time_id, []), key=lambda item: (item["score"], item["confidence"]), reverse=True)
            best_candidate = candidates[0] if candidates else {"label": "", "score": 0, "confidence": 0}
            team_results.append(
                {
                    "Data": pd.to_datetime(date_str, dayfirst=True),
                    "Time": time_id,
                    "gols_sofridos": stats["gols_sofridos"],
                    "gols_time": stats["gols_time"],
                    "jogos_sem_sofrer": stats["jogos_sem_sofrer"],
                }
            )
            team_diagnostics.append(
                {
                    "Data": pd.to_datetime(date_str, dayfirst=True),
                    "Time": time_id,
                    "classificacao": team["classificacao_norm"],
                    "team_label": best_candidate["label"],
                    "mapping_score": best_candidate["score"],
                    "mapping_confidence": best_candidate["confidence"],
                    "mentioned_players": ", ".join(sorted(set().union(*[mentions_by_label[item["label"]] for item in candidates]) if candidates else set())),
                }
            )

    result_df = pd.DataFrame(team_results).drop_duplicates(subset=["Data", "Time"], keep="last")
    diagnostic_df = pd.DataFrame(team_diagnostics).sort_values(["Data", "Time"]) if team_diagnostics else pd.DataFrame()
    return result_df, diagnostic_df


def load_players() -> pd.DataFrame:
    players = json.loads(PLAYERS_FILE.read_text(encoding="utf-8-sig"))
    players_df = pd.DataFrame(players)
    players_df["name_norm"] = players_df["name"].map(alias_lib.normalize_name)
    players_df["scout_name"] = players_df["name_norm"].map(alias_lib.ALIASES).fillna(players_df["name"])
    return players_df


def load_data() -> pd.DataFrame:
    df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig")
    df.columns = [col.strip() for col in df.columns]
    # The last column is the ranking label, but its header may arrive mangled.
    df = df.rename(columns={df.columns[-1]: "classificacao"})

    df["Jogadores"] = (
        df["Jogadores"]
        .astype(str)
        .str.strip()
        .map(lambda value: alias_lib.ALIASES.get(alias_lib.normalize_name(value), value))
    )
    df["Data"] = pd.to_datetime(df["Data"], dayfirst=True)
    df["mes"] = df["Data"].dt.strftime("%Y-%m")
    df["participacoes"] = df["Gol"] + df["Assist"]
    df["classificacao_norm"] = df["classificacao"].map(normalize_text)

    replace_map = {
        "Campeao": "Campeao",
        "Segundo": "Segundo",
        "Terceiro": "Terceiro",
        "Lanterna": "Lanterna",
    }
    df["classificacao_norm"] = df["classificacao_norm"].map(replace_map).fillna(df["classificacao_norm"])

    result_df, diagnostic_df = build_match_result_df(df)
    df = df.merge(result_df, on=["Data", "Time"], how="left")
    for column in ["gols_sofridos", "gols_time", "jogos_sem_sofrer"]:
        df[column] = df[column].fillna(0).astype(int)
    df["resultados_extraidos"] = df["gols_time"].gt(0) | df["gols_sofridos"].gt(0) | df["jogos_sem_sofrer"].gt(0)
    df.attrs["match_result_diagnostics"] = diagnostic_df
    return df


def build_summary_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    player_summary = (
        df.groupby("Jogadores", as_index=False)
        .agg(
            Gols=("Gol", "sum"),
            Assistencias=("Assist", "sum"),
            Participacoes=("participacoes", "sum"),
            Amarelos=("Amarelo", "sum"),
            Vermelhos=("Red", "sum"),
            Gols_sofridos=("gols_sofridos", "sum"),
            Gols_do_time=("gols_time", "sum"),
            Jogos_sem_sofrer=("jogos_sem_sofrer", "sum"),
            Jogos=("Data", "count"),
        )
        .sort_values(["Participacoes", "Gols", "Assistencias", "Jogadores"], ascending=[False, False, False, True])
    )

    classification_summary = (
        df.pivot_table(
            index="Jogadores",
            columns="classificacao_norm",
            values="Data",
            aggfunc="count",
            fill_value=0,
        )
        .reindex(columns=POSITION_ORDER, fill_value=0)
        .reset_index()
    )

    monthly_summary = (
        df.groupby(["mes", "Jogadores"], as_index=False)
        .agg(Participacoes=("participacoes", "sum"))
        .sort_values(["Jogadores", "mes"])
    )

    last4 = (
        df.sort_values(["Jogadores", "Data"], ascending=[True, False])
        .assign(Recencia=lambda x: x.groupby("Jogadores").cumcount() + 1)
        .loc[lambda x: x["Recencia"] <= 4]
        .copy()
    )
    last4["Data_fmt"] = last4["Data"].dt.strftime("%d/%m/%Y")
    last4 = last4.sort_values(["Jogadores", "Data"], ascending=[True, False])

    return {
        "resumo_jogadores": player_summary,
        "distribuicao_classificacao": classification_summary,
        "resumo_mensal": monthly_summary,
        "ultimas_4_datas": last4,
    }


def player_order(df: pd.DataFrame) -> list[str]:
    return (
        df.groupby("Jogadores")["participacoes"]
        .sum()
        .sort_values(ascending=False)
        .index
        .tolist()
    )


def player_scout_totals_switcher(df: pd.DataFrame) -> go.Figure:
    metric_configs = [
        {
            "column": "Participacoes",
            "label": "Participacoes",
            "title": "Total de participacoes em gol por jogador",
            "yaxis": "Participacoes",
            "color": "#16a085",
            "value_format": "{:.0f}",
        },
        {
            "column": "Gols",
            "label": "Gols",
            "title": "Numero de gols por jogador",
            "yaxis": "Gols",
            "color": "#c0392b",
            "value_format": "{:.0f}",
        },
        {
            "column": "Assistencias",
            "label": "Assistencias",
            "title": "Numero de assistencias por jogador",
            "yaxis": "Assistencias",
            "color": "#2980b9",
            "value_format": "{:.0f}",
        },
        {
            "column": "Gols_do_time",
            "label": "Gols do time",
            "title": "Total de gols marcados pelo time por jogador",
            "yaxis": "Gols do time",
            "color": "#8e44ad",
            "value_format": "{:.0f}",
        },
    ]

    fig = go.Figure()
    for index, config in enumerate(metric_configs):
        chart_df = df.sort_values([config["column"], "Jogadores"], ascending=[False, True])
        fig.add_trace(
            go.Bar(
                x=chart_df["Jogadores"],
                y=chart_df[config["column"]],
                marker_color=config["color"],
                text=chart_df[config["column"]].map(lambda value, fmt=config["value_format"]: fmt.format(value)),
                customdata=list(zip(chart_df["Jogos"],)),
                hovertemplate=(
                    "Jogador: %{x}<br>"
                    f"{config['label']}: %{{y}}<br>"
                    "Jogos: %{customdata[0]}<extra></extra>"
                ),
                visible=index == 0,
                name=config["label"],
            )
        )

    buttons = []
    for index, config in enumerate(metric_configs):
        visible = [False] * len(metric_configs)
        visible[index] = True
        buttons.append(
            dict(
                label=config["label"],
                method="update",
                args=[
                    {"visible": visible},
                    {"title": config["title"], "yaxis": {"title": config["yaxis"]}},
                ],
            )
        )

    fig.update_layout(
        template="plotly_white",
        height=560,
        margin=dict(l=40, r=20, t=110, b=140),
        xaxis_title="Jogador",
        yaxis_title=metric_configs[0]["yaxis"],
        xaxis_tickangle=-45,
        showlegend=False,
        title=metric_configs[0]["title"],
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                showactive=True,
                x=0,
                xanchor="left",
                y=1.18,
                yanchor="top",
                buttons=buttons,
            )
        ],
        annotations=[
            dict(
                text="Selecione o scout total",
                x=0,
                xref="paper",
                y=1.25,
                yref="paper",
                showarrow=False,
                align="left",
            )
        ],
    )
    return fig


def player_scout_averages_switcher(df: pd.DataFrame) -> go.Figure:
    chart_df = (
        df.groupby("Jogadores", as_index=False)
        .agg(
            Jogos=("Data", "count"),
            Participacoes_media=("participacoes", "mean"),
            Gols_media=("Gol", "mean"),
            Assistencias_media=("Assist", "mean"),
            Gols_do_time_media=("gols_time", "mean"),
        )
        .copy()
    )

    metric_configs = [
        {
            "column": "Participacoes_media",
            "label": "Media de participacoes",
            "title": "Media de participacoes em gol por jogador",
            "yaxis": "Participacoes por pelada",
            "color": "#16a085",
            "value_format": "{:.2f}",
        },
        {
            "column": "Gols_media",
            "label": "Media de gols",
            "title": "Media de gols por jogador",
            "yaxis": "Gols por pelada",
            "color": "#c0392b",
            "value_format": "{:.2f}",
        },
        {
            "column": "Assistencias_media",
            "label": "Media de assistencias",
            "title": "Media de assistencias por jogador",
            "yaxis": "Assistencias por pelada",
            "color": "#2980b9",
            "value_format": "{:.2f}",
        },
        {
            "column": "Gols_do_time_media",
            "label": "Media de gols do time",
            "title": "Media de gols marcados pelo time por jogador",
            "yaxis": "Gols do time por pelada",
            "color": "#8e44ad",
            "value_format": "{:.2f}",
        },
    ]

    fig = go.Figure()
    for index, config in enumerate(metric_configs):
        metric_df = chart_df.sort_values([config["column"], "Jogadores"], ascending=[False, True])
        fig.add_trace(
            go.Bar(
                x=metric_df["Jogadores"],
                y=metric_df[config["column"]],
                marker_color=config["color"],
                text=metric_df[config["column"]].map(lambda value, fmt=config["value_format"]: fmt.format(value)),
                customdata=list(zip(metric_df["Jogos"],)),
                hovertemplate=(
                    "Jogador: %{x}<br>"
                    f"{config['label']}: %{{y:.2f}}<br>"
                    "Jogos: %{customdata[0]}<extra></extra>"
                ),
                visible=index == 0,
                name=config["label"],
            )
        )

    buttons = []
    for index, config in enumerate(metric_configs):
        visible = [False] * len(metric_configs)
        visible[index] = True
        buttons.append(
            dict(
                label=config["label"],
                method="update",
                args=[
                    {"visible": visible},
                    {"title": config["title"], "yaxis": {"title": config["yaxis"]}},
                ],
            )
        )

    fig.update_layout(
        template="plotly_white",
        height=560,
        margin=dict(l=40, r=20, t=110, b=140),
        xaxis_title="Jogador",
        yaxis_title=metric_configs[0]["yaxis"],
        xaxis_tickangle=-45,
        showlegend=False,
        title=metric_configs[0]["title"],
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                showactive=True,
                x=0,
                xanchor="left",
                y=1.18,
                yanchor="top",
                buttons=buttons,
            )
        ],
        annotations=[
            dict(
                text="Selecione o scout medio",
                x=0,
                xref="paper",
                y=1.25,
                yref="paper",
                showarrow=False,
                align="left",
            )
        ],
    )
    return fig


def top10_bar(df: pd.DataFrame, value_col: str, title: str, color: str, axis_label: str) -> go.Figure:
    chart_df = (
        df.loc[df[value_col] > 0, ["Jogadores", value_col]]
        .sort_values([value_col, "Jogadores"], ascending=[False, True])
        .head(10)
        .sort_values(value_col, ascending=True)
    )
    fig = px.bar(
        chart_df,
        x=value_col,
        y="Jogadores",
        orientation="h",
        text_auto=True,
        color_discrete_sequence=[color],
        title=title,
    )
    fig.update_layout(
        template="plotly_white",
        height=460,
        margin=dict(l=40, r=20, t=70, b=40),
        xaxis_title=axis_label,
        yaxis_title="Jogador",
        showlegend=False,
    )
    return fig


def top10_switcher(df: pd.DataFrame) -> go.Figure:
    metric_configs = [
        {
            "column": "Gols",
            "label": "Gols",
            "title": "Top 10 de gols",
            "xaxis": "Gols",
            "color": "#c0392b",
        },
        {
            "column": "Assistencias",
            "label": "Assistencias",
            "title": "Top 10 de assistencias",
            "xaxis": "Assistencias",
            "color": "#2980b9",
        },
        {
            "column": "Participacoes",
            "label": "Participacoes",
            "title": "Top 10 de participacoes em gol",
            "xaxis": "Participacoes",
            "color": "#16a085",
        },
        {
            "column": "Amarelos",
            "label": "Amarelos",
            "title": "Top 10 de cartoes amarelos",
            "xaxis": "Amarelos",
            "color": "#f1c40f",
        },
        {
            "column": "Vermelhos",
            "label": "Vermelhos",
            "title": "Top 10 de cartoes vermelhos",
            "xaxis": "Vermelhos",
            "color": "#7f1d1d",
        },
    ]

    fig = go.Figure()
    for index, config in enumerate(metric_configs):
        chart_df = (
            df.loc[df[config["column"]] > 0, ["Jogadores", config["column"]]]
            .sort_values([config["column"], "Jogadores"], ascending=[False, True])
            .head(10)
            .sort_values(config["column"], ascending=True)
        )
        fig.add_trace(
            go.Bar(
                x=chart_df[config["column"]],
                y=chart_df["Jogadores"],
                orientation="h",
                marker_color=config["color"],
                text=chart_df[config["column"]],
                hovertemplate=(
                    "Jogador: %{y}<br>"
                    f"{config['label']}: %{{x}}<extra></extra>"
                ),
                visible=index == 0,
                name=config["label"],
            )
        )

    buttons = []
    for index, config in enumerate(metric_configs):
        visible = [False] * len(metric_configs)
        visible[index] = True
        buttons.append(
            dict(
                label=config["label"],
                method="update",
                args=[
                    {"visible": visible},
                    {"title": config["title"], "xaxis": {"title": config["xaxis"]}},
                ],
            )
        )

    fig.update_layout(
        template="plotly_white",
        height=460,
        margin=dict(l=40, r=20, t=110, b=40),
        xaxis_title=metric_configs[0]["xaxis"],
        yaxis_title="Jogador",
        showlegend=False,
        title=metric_configs[0]["title"],
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                showactive=True,
                x=0,
                xanchor="left",
                y=1.18,
                yanchor="top",
                buttons=buttons,
            )
        ],
        annotations=[
            dict(
                text="Selecione o Top 10",
                x=0,
                xref="paper",
                y=1.25,
                yref="paper",
                showarrow=False,
                align="left",
            )
        ],
    )
    return fig


def classification_chart(df: pd.DataFrame) -> go.Figure:
    order = player_order(df)
    chart_df = (
        df.pivot_table(
            index="Jogadores",
            columns="classificacao_norm",
            values="Data",
            aggfunc="count",
            fill_value=0,
        )
        .reindex(index=order, columns=POSITION_ORDER, fill_value=0)
        .reset_index()
        .melt(id_vars="Jogadores", var_name="classificacao_norm", value_name="Quantidade")
    )
    chart_df["Classificacao"] = chart_df["classificacao_norm"].map(POSITION_LABELS)

    fig = px.bar(
        chart_df,
        x="Jogadores",
        y="Quantidade",
        color="Classificacao",
        category_orders={
            "Jogadores": order,
            "Classificacao": [POSITION_LABELS[key] for key in POSITION_ORDER],
        },
        color_discrete_map={POSITION_LABELS[key]: value for key, value in POSITION_COLORS.items()},
        title="Distribui\u00e7\u00e3o de posi\u00e7\u00e3o por jogador",
    )
    fig.update_layout(
        template="plotly_white",
        barmode="stack",
        height=620,
        margin=dict(l=40, r=20, t=70, b=160),
        xaxis_title="Jogador",
        yaxis_title="Quantidade de vezes",
        xaxis_tickangle=-45,
        legend_title="Posi\u00e7\u00e3o",
    )
    return fig


def classification_participation_adjusted_chart(df: pd.DataFrame) -> go.Figure:
    order = player_order(df)
    chart_df = (
        df.groupby(["Jogadores", "classificacao_norm"], as_index=False)
        .agg(
            Participacoes_ajustadas=("participacoes", "sum"),
            Jogos=("Data", "count"),
            Media_participacoes=("participacoes", "mean"),
        )
        .assign(
            Classificacao=lambda x: x["classificacao_norm"].map(POSITION_LABELS),
            Hover_media=lambda x: x["Media_participacoes"].map(lambda value: f"{value:.2f}"),
        )
    )

    fig = px.bar(
        chart_df,
        x="Jogadores",
        y="Participacoes_ajustadas",
        color="Classificacao",
        category_orders={
            "Jogadores": order,
            "Classificacao": [POSITION_LABELS[key] for key in POSITION_ORDER],
        },
        color_discrete_map={POSITION_LABELS[key]: value for key, value in POSITION_COLORS.items()},
        custom_data=["Jogos", "Hover_media"],
        title="Distribuição de posição por jogador ajustada por participações",
    )
    fig.update_traces(
        hovertemplate=(
            "Jogador: %{x}<br>"
            "Posição: %{fullData.name}<br>"
            "Participações acumuladas: %{y}<br>"
            "Jogos nessa posição: %{customdata[0]}<br>"
            "Média de participações/jogo: %{customdata[1]}<extra></extra>"
        )
    )
    fig.update_layout(
        template="plotly_white",
        barmode="stack",
        height=620,
        margin=dict(l=40, r=20, t=70, b=160),
        xaxis_title="Jogador",
        yaxis_title="Participações em jogos daquela posição",
        xaxis_tickangle=-45,
        legend_title="Posição",
    )
    return fig


def classification_chart_switcher(df: pd.DataFrame) -> go.Figure:
    order = player_order(df)
    count_df = (
        df.pivot_table(
            index="Jogadores",
            columns="classificacao_norm",
            values="Data",
            aggfunc="count",
            fill_value=0,
        )
        .reindex(index=order, columns=POSITION_ORDER, fill_value=0)
        .reset_index()
    )
    adjusted_df = (
        df.pivot_table(
            index="Jogadores",
            columns="classificacao_norm",
            values="participacoes",
            aggfunc="sum",
            fill_value=0,
        )
        .reindex(index=order, columns=POSITION_ORDER, fill_value=0)
        .reset_index()
    )

    media_df = adjusted_df.copy()
    for position in POSITION_ORDER:
        jogos = count_df[position].astype(float)
        media_df[position] = (adjusted_df[position] / jogos.where(jogos > 0)).fillna(0.0)

    fig = go.Figure()
    for position in POSITION_ORDER:
        label = POSITION_LABELS[position]
        fig.add_trace(
            go.Bar(
                x=order,
                y=count_df[position],
                name=label,
                marker_color=POSITION_COLORS[position],
                visible=True,
                customdata=list(zip(count_df[position], media_df[position])),
                hovertemplate=(
                    "Jogador: %{x}<br>"
                    f"Posição: {label}<br>"
                    "Quantidade de vezes: %{y}<br>"
                    "Média de participações/jogo: %{customdata[1]:.2f}<extra></extra>"
                ),
            )
        )

    for position in POSITION_ORDER:
        label = POSITION_LABELS[position]
        fig.add_trace(
            go.Bar(
                x=order,
                y=adjusted_df[position],
                name=label,
                marker_color=POSITION_COLORS[position],
                visible=False,
                customdata=list(zip(count_df[position], media_df[position])),
                hovertemplate=(
                    "Jogador: %{x}<br>"
                    f"Posição: {label}<br>"
                    "Participações acumuladas: %{y}<br>"
                    "Jogos nessa posição: %{customdata[0]}<br>"
                    "Média de participações/jogo: %{customdata[1]:.2f}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        template="plotly_white",
        barmode="stack",
        height=620,
        margin=dict(l=40, r=20, t=110, b=160),
        xaxis_title="Jogador",
        yaxis_title="Quantidade de vezes",
        xaxis_tickangle=-45,
        legend_title="Posição",
        title="Distribuição de posição por jogador",
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                showactive=True,
                x=0,
                xanchor="left",
                y=1.18,
                yanchor="top",
                buttons=[
                    dict(
                        label="Contagem de posições",
                        method="update",
                        args=[
                            {"visible": [True] * len(POSITION_ORDER) + [False] * len(POSITION_ORDER)},
                            {"title": "Distribuição de posição por jogador", "yaxis": {"title": "Quantidade de vezes"}},
                        ],
                    ),
                    dict(
                        label="Ajustado por participações",
                        method="update",
                        args=[
                            {"visible": [False] * len(POSITION_ORDER) + [True] * len(POSITION_ORDER)},
                            {
                                "title": "Distribuição de posição por jogador ajustada por participações",
                                "yaxis": {"title": "Participações em jogos daquela posição"},
                            },
                        ],
                    ),
                ],
            )
        ],
        annotations=[
            dict(
                text="Selecione a versão do gráfico",
                x=0,
                xref="paper",
                y=1.25,
                yref="paper",
                showarrow=False,
                align="left",
            )
        ],
    )
    return fig


def classification_games_adjusted_chart(df: pd.DataFrame) -> go.Figure:
    order = player_order(df)
    count_df = (
        df.pivot_table(
            index="Jogadores",
            columns="classificacao_norm",
            values="Data",
            aggfunc="count",
            fill_value=0,
        )
        .reindex(index=order, columns=POSITION_ORDER, fill_value=0)
        .reset_index()
    )
    expected_df = count_df.copy()
    total_games = count_df[POSITION_ORDER].sum(axis=1).astype(float)

    for position in POSITION_ORDER:
        expected_df[position] = (count_df[position].astype(float) / total_games.where(total_games > 0)).fillna(0.0)

    fig = go.Figure()
    for position in POSITION_ORDER:
        label = POSITION_LABELS[position]
        fig.add_trace(
            go.Bar(
                x=order,
                y=count_df[position],
                name=label,
                marker_color=POSITION_COLORS[position],
                visible=True,
                customdata=list(zip(total_games, expected_df[position])),
                hovertemplate=(
                    "Jogador: %{x}<br>"
                    f"Posicao: {label}<br>"
                    "Quantidade de vezes: %{y}<br>"
                    "Jogos do jogador: %{customdata[0]}<br>"
                    "Percentual historico nessa posicao: %{customdata[1]:.1%}<extra></extra>"
                ),
            )
        )

    for position in POSITION_ORDER:
        label = POSITION_LABELS[position]
        fig.add_trace(
            go.Bar(
                x=order,
                y=expected_df[position],
                name=label,
                marker_color=POSITION_COLORS[position],
                visible=False,
                customdata=list(zip(count_df[position], total_games)),
                hovertemplate=(
                    "Jogador: %{x}<br>"
                    f"Posicao: {label}<br>"
                    "Classificacao esperada historica: %{y:.1%}<br>"
                    "Jogos nessa posicao: %{customdata[0]}<br>"
                    "Jogos do jogador: %{customdata[1]}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        template="plotly_white",
        barmode="stack",
        height=620,
        margin=dict(l=40, r=20, t=110, b=160),
        xaxis_title="Jogador",
        yaxis_title="Quantidade de vezes",
        xaxis_tickangle=-45,
        legend_title="Posicao",
        title="Distribuicao de posicao por jogador",
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                showactive=True,
                x=0,
                xanchor="left",
                y=1.18,
                yanchor="top",
                buttons=[
                    dict(
                        label="Contagem de posicoes",
                        method="update",
                        args=[
                            {"visible": [True] * len(POSITION_ORDER) + [False] * len(POSITION_ORDER)},
                            {
                                "title": "Distribuicao de posicao por jogador",
                                "yaxis": {"title": "Quantidade de vezes", "tickformat": ""},
                            },
                        ],
                    ),
                    dict(
                        label="Ajustado por jogos",
                        method="update",
                        args=[
                            {"visible": [False] * len(POSITION_ORDER) + [True] * len(POSITION_ORDER)},
                            {
                                "title": "Classificacao esperada historica por jogador",
                                "yaxis": {"title": "Percentual dos jogos do jogador", "tickformat": ".0%"},
                            },
                        ],
                    ),
                ],
            )
        ],
        annotations=[
            dict(
                text="Selecione a versao do grafico",
                x=0,
                xref="paper",
                y=1.25,
                yref="paper",
                showarrow=False,
                align="left",
            )
        ],
    )
    return fig


def offensive_participation_blob_chart(df: pd.DataFrame, players_df: pd.DataFrame) -> go.Figure:
    ratings_df = players_df[["scout_name", "rating"]].rename(columns={"scout_name": "Jogadores", "rating": "Nivel"})
    chart_df = (
        df.merge(ratings_df, on="Jogadores", how="inner")
        .groupby(["Jogadores", "Nivel"], as_index=False)
        .agg(
            Participacoes_media=("participacoes", "mean"),
            Jogos=("Data", "count"),
            Participacoes_totais=("participacoes", "sum"),
            SG_media=("jogos_sem_sofrer", "mean"),
            SG_total=("jogos_sem_sofrer", "sum"),
            Gols_do_time_media=("gols_time", "mean"),
            Gols_do_time_total=("gols_time", "sum"),
            Gols_sofridos_media=("gols_sofridos", "mean"),
            Gols_sofridos_total=("gols_sofridos", "sum"),
        )
    )
    chart_df["Nivel"] = chart_df["Nivel"].astype(int).astype(str)
    level_order = [str(level) for level in sorted(chart_df["Nivel"].unique(), key=int)]

    fig = go.Figure()
    for level in level_order:
        level_df = chart_df.loc[chart_df["Nivel"] == level]
        fig.add_trace(
            go.Violin(
                x=level_df["Nivel"],
                y=level_df["Participacoes_media"],
                name=level,
                legendgroup=level,
                scalegroup=level,
                box_visible=True,
                meanline_visible=True,
                points="all",
                pointpos=0,
                jitter=0.16,
                marker=dict(size=6, opacity=0.5),
                visible=True,
                customdata=list(zip(level_df["Jogadores"], level_df["Jogos"], level_df["Participacoes_totais"])),
                hovertemplate=(
                    "Nivel: %{x}<br>"
                    "Participacoes medias/jogo: %{y:.2f}<br>"
                    "Jogador: %{customdata[0]}<br>"
                    "Jogos: %{customdata[1]}<br>"
                    "Participacoes totais: %{customdata[2]}<extra></extra>"
                ),
            )
        )
    for level in level_order:
        level_df = chart_df.loc[chart_df["Nivel"] == level]
        fig.add_trace(
            go.Violin(
                x=level_df["Nivel"],
                y=level_df["SG_media"],
                name=level,
                legendgroup=level,
                scalegroup=f"sg-{level}",
                box_visible=True,
                meanline_visible=True,
                points="all",
                pointpos=0,
                jitter=0.16,
                marker=dict(size=6, opacity=0.5),
                visible=False,
                customdata=list(zip(level_df["Jogadores"], level_df["Jogos"], level_df["SG_total"])),
                hovertemplate=(
                    "Nivel: %{x}<br>"
                    "SG medios/jogo: %{y:.2f}<br>"
                    "Jogador: %{customdata[0]}<br>"
                    "Jogos: %{customdata[1]}<br>"
                    "Jogos com SG: %{customdata[2]}<extra></extra>"
                ),
            )
        )
    for level in level_order:
        level_df = chart_df.loc[chart_df["Nivel"] == level]
        fig.add_trace(
            go.Violin(
                x=level_df["Nivel"],
                y=level_df["Gols_do_time_media"],
                name=level,
                legendgroup=level,
                scalegroup=f"gols-time-{level}",
                box_visible=True,
                meanline_visible=True,
                points="all",
                pointpos=0,
                jitter=0.16,
                marker=dict(size=6, opacity=0.5),
                visible=False,
                customdata=list(zip(level_df["Jogadores"], level_df["Jogos"], level_df["Gols_do_time_total"])),
                hovertemplate=(
                    "Nivel: %{x}<br>"
                    "Gols do time medios/jogo: %{y:.2f}<br>"
                    "Jogador: %{customdata[0]}<br>"
                    "Jogos: %{customdata[1]}<br>"
                    "Gols do time totais: %{customdata[2]}<extra></extra>"
                ),
            )
        )
    for level in level_order:
        level_df = chart_df.loc[chart_df["Nivel"] == level]
        fig.add_trace(
            go.Violin(
                x=level_df["Nivel"],
                y=level_df["Gols_sofridos_media"],
                name=level,
                legendgroup=level,
                scalegroup=f"gols-sofridos-{level}",
                box_visible=True,
                meanline_visible=True,
                points="all",
                pointpos=0,
                jitter=0.16,
                marker=dict(size=6, opacity=0.5),
                visible=False,
                customdata=list(zip(level_df["Jogadores"], level_df["Jogos"], level_df["Gols_sofridos_total"])),
                hovertemplate=(
                    "Nivel: %{x}<br>"
                    "Gols sofridos medios/jogo: %{y:.2f}<br>"
                    "Jogador: %{customdata[0]}<br>"
                    "Jogos: %{customdata[1]}<br>"
                    "Gols sofridos totais: %{customdata[2]}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        template="plotly_white",
        height=620,
        margin=dict(l=40, r=20, t=110, b=40),
        xaxis_title="Nivel do jogador",
        yaxis_title="Participacoes ofensivas medias por jogo",
        legend_title="Nivel",
        title="Distribuicao de participacoes ofensivas medias por nivel do jogador",
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                showactive=True,
                x=0,
                xanchor="left",
                y=1.18,
                yanchor="top",
                buttons=[
                    dict(
                        label="Participacoes por nivel",
                        method="update",
                        args=[
                            {
                                "visible": [True] * len(level_order)
                                + [False] * len(level_order)
                                + [False] * len(level_order)
                                + [False] * len(level_order)
                            },
                            {
                                "title": "Distribuicao de participacoes ofensivas medias por nivel do jogador",
                                "yaxis": {"title": "Participacoes ofensivas medias por jogo"},
                            },
                        ],
                    ),
                    dict(
                        label="SG por nivel",
                        method="update",
                        args=[
                            {
                                "visible": [False] * len(level_order)
                                + [True] * len(level_order)
                                + [False] * len(level_order)
                                + [False] * len(level_order)
                            },
                            {
                                "title": "Distribuicao de jogos sem sofrer gols por nivel do jogador",
                                "yaxis": {"title": "Jogos com SG por jogo"},
                            },
                        ],
                    ),
                    dict(
                        label="Gols do time por nivel",
                        method="update",
                        args=[
                            {
                                "visible": [False] * len(level_order)
                                + [False] * len(level_order)
                                + [True] * len(level_order)
                                + [False] * len(level_order)
                            },
                            {
                                "title": "Distribuicao de gols marcados pelo time por nivel do jogador",
                                "yaxis": {"title": "Gols do time por jogo"},
                            },
                        ],
                    ),
                    dict(
                        label="Gols sofridos por nivel",
                        method="update",
                        args=[
                            {
                                "visible": [False] * len(level_order)
                                + [False] * len(level_order)
                                + [False] * len(level_order)
                                + [True] * len(level_order)
                            },
                            {
                                "title": "Distribuicao de gols sofridos por nivel do jogador",
                                "yaxis": {"title": "Gols sofridos por jogo"},
                            },
                        ],
                    ),
                ],
            )
        ],
        annotations=[
            dict(
                text="Selecione a versao do grafico",
                x=0,
                xref="paper",
                y=1.25,
                yref="paper",
                showarrow=False,
                align="left",
            )
        ],
    )
    return fig


def defensive_average_chart_switcher(df: pd.DataFrame, min_games: int = MIN_GAMES_DEFENSIVE_AVG) -> go.Figure:
    chart_df = (
        df.groupby("Jogadores", as_index=False)
        .agg(
            Jogos=("Data", "count"),
            Gols_sofridos_media=("gols_sofridos", "mean"),
            SG_media=("jogos_sem_sofrer", "mean"),
            Gols_sofridos_total=("gols_sofridos", "sum"),
            SG_total=("jogos_sem_sofrer", "sum"),
        )
        .loc[lambda x: x["Jogos"] >= min_games]
        .copy()
    )

    if chart_df.empty:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_white",
            height=520,
            title=f"Medias defensivas por jogador (minimo de {min_games} jogos)",
            annotations=[
                dict(
                    text="Nao ha jogadores suficientes para o filtro atual.",
                    x=0.5,
                    y=0.5,
                    xref="paper",
                    yref="paper",
                    showarrow=False,
                )
            ],
        )
        return fig

    conceded_df = chart_df.sort_values(["Gols_sofridos_media", "Jogadores"], ascending=[False, True])
    sg_df = chart_df.sort_values(["SG_media", "Jogadores"], ascending=[False, True])

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=conceded_df["Jogadores"],
            y=conceded_df["Gols_sofridos_media"],
            marker_color="#c0392b",
            text=conceded_df["Gols_sofridos_media"].map(lambda value: f"{value:.2f}"),
            customdata=list(zip(conceded_df["Jogos"], conceded_df["Gols_sofridos_total"])),
            hovertemplate=(
                "Jogador: %{x}<br>"
                "Media de gols sofridos/pelada: %{y:.2f}<br>"
                "Jogos: %{customdata[0]}<br>"
                "Gols sofridos totais: %{customdata[1]}<extra></extra>"
            ),
            visible=True,
            name="Gols sofridos",
        )
    )
    fig.add_trace(
        go.Bar(
            x=sg_df["Jogadores"],
            y=sg_df["SG_media"],
            marker_color="#1e8449",
            text=sg_df["SG_media"].map(lambda value: f"{value:.2f}"),
            customdata=list(zip(sg_df["Jogos"], sg_df["SG_total"])),
            hovertemplate=(
                "Jogador: %{x}<br>"
                "Media de jogos com SG/pelada: %{y:.2f}<br>"
                "Jogos: %{customdata[0]}<br>"
                "Jogos com SG: %{customdata[1]}<extra></extra>"
            ),
            visible=False,
            name="Jogos com SG",
        )
    )
    fig.update_layout(
        template="plotly_white",
        height=560,
        margin=dict(l=40, r=20, t=110, b=140),
        xaxis_title="Jogador",
        yaxis_title="Media de gols sofridos por pelada",
        xaxis_tickangle=-45,
        showlegend=False,
        title=f"Medias defensivas por jogador (minimo de {min_games} jogos)",
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                showactive=True,
                x=0,
                xanchor="left",
                y=1.18,
                yanchor="top",
                buttons=[
                    dict(
                        label="Media de gols sofridos",
                        method="update",
                        args=[
                            {"visible": [True, False]},
                            {
                                "yaxis": {"title": "Media de gols sofridos por pelada"},
                                "title": f"Media de gols sofridos por jogador (minimo de {min_games} jogos)",
                            },
                        ],
                    ),
                    dict(
                        label="Media de jogos com SG",
                        method="update",
                        args=[
                            {"visible": [False, True]},
                            {
                                "yaxis": {"title": "Media de jogos com SG por pelada"},
                                "title": f"Media de jogos com SG por jogador (minimo de {min_games} jogos)",
                            },
                        ],
                    ),
                ],
            )
        ],
        annotations=[
            dict(
                text=f"Filtro minimo: {min_games} jogos",
                x=0,
                xref="paper",
                y=1.25,
                yref="paper",
                showarrow=False,
                align="left",
            )
        ],
    )
    return fig


def monthly_player_bar(df: pd.DataFrame) -> go.Figure:
    monthly = (
        df.groupby(["Jogadores", "mes"], as_index=False)
        .agg(Participacoes=("participacoes", "sum"))
        .sort_values(["Jogadores", "mes"])
    )
    players = sorted(monthly["Jogadores"].unique())
    months = sorted(monthly["mes"].unique())

    fig = go.Figure()
    for index, player in enumerate(players):
        player_df = (
            monthly.loc[monthly["Jogadores"] == player, ["mes", "Participacoes"]]
            .set_index("mes")
            .reindex(months, fill_value=0)
            .reset_index()
        )
        fig.add_trace(
            go.Bar(
                x=player_df["mes"],
                y=player_df["Participacoes"],
                name=player,
                visible=index == 0,
                marker_color="#0f766e",
                text=player_df["Participacoes"],
                textposition="outside",
                hovertemplate=f"Jogador: {player}<br>M\u00eas: %{{x}}<br>Participa\u00e7\u00f5es: %{{y}}<extra></extra>",
            )
        )

    buttons = []
    for index, player in enumerate(players):
        visible = [False] * len(players)
        visible[index] = True
        buttons.append(
            dict(
                label=player,
                method="update",
                args=[{"visible": visible}, {"title": f"Participa\u00e7\u00f5es por m\u00eas: {player}"}],
            )
        )

    fig.update_layout(
        template="plotly_white",
        height=520,
        margin=dict(l=40, r=20, t=110, b=40),
        title=f"Participa\u00e7\u00f5es por m\u00eas: {players[0]}",
        xaxis_title="M\u00eas",
        yaxis_title="Participa\u00e7\u00f5es",
        showlegend=False,
        updatemenus=[
            dict(
                buttons=buttons,
                direction="down",
                showactive=True,
                x=0,
                xanchor="left",
                y=1.18,
                yanchor="top",
            )
        ],
        annotations=[
            dict(
                text="Selecione o jogador",
                x=0,
                xref="paper",
                y=1.24,
                yref="paper",
                showarrow=False,
                align="left",
            )
        ],
    )
    return fig


def build_last4_cards(last4: pd.DataFrame) -> str:
    players = sorted(last4["Jogadores"].unique())
    payload = {}
    for player in players:
        rows = []
        player_df = last4.loc[last4["Jogadores"] == player].sort_values("Data", ascending=False)
        for row in player_df.itertuples():
            rows.append(
                {
                    "data": row.Data_fmt,
                    "time": int(row.Time),
                    "gols": int(row.Gol),
                    "assistencias": int(row.Assist),
                    "participacoes": int(row.participacoes),
                    "amarelos": int(row.Amarelo),
                    "vermelhos": int(row.Red),
                    "classificacao": POSITION_LABELS.get(row.classificacao_norm, row.classificacao),
                }
            )
        payload[player] = rows

    first_player = players[0]
    cards_html = """
    <section class="card">
      <h2>\u00daltimas 4 datas</h2>
      <div class="selector-row">
        <label for="last4-player">Selecione o jogador</label>
        <select id="last4-player"></select>
      </div>
      <div id="last4-cards" class="last4-grid"></div>
    </section>
    <script>
      const last4Payload = """ + json.dumps(payload, ensure_ascii=False) + """;
      const last4Select = document.getElementById("last4-player");
      const last4Container = document.getElementById("last4-cards");
      const last4Players = Object.keys(last4Payload);

      function renderLast4(player) {
        const items = last4Payload[player] || [];
        last4Container.innerHTML = items.map(item => `
          <article class="match-card">
            <div class="match-head">
              <strong>${item.data}</strong>
              <span>Time ${item.time}</span>
            </div>
            <div class="match-tag">${item.classificacao}</div>
            <div class="match-stats">
              <div><span>Gols</span><strong>${item.gols}</strong></div>
              <div><span>Assist.</span><strong>${item.assistencias}</strong></div>
              <div><span>Part.</span><strong>${item.participacoes}</strong></div>
              <div><span>Amar.</span><strong>${item.amarelos}</strong></div>
              <div><span>Verm.</span><strong>${item.vermelhos}</strong></div>
            </div>
          </article>
        `).join("");
      }

      last4Players.forEach(player => {
        const option = document.createElement("option");
        option.value = player;
        option.textContent = player;
        last4Select.appendChild(option);
      });
      last4Select.value = """ + json.dumps(first_player, ensure_ascii=False) + """;
      renderLast4(last4Select.value);
      last4Select.addEventListener("change", event => renderLast4(event.target.value));
    </script>
    """
    return cards_html


def build_general_ranking_spotlight() -> str:
    historic_path = OUTPUT_DIR / "ranking_geral_historico.csv"
    current_path = OUTPUT_DIR / "ranking_geral_mes_corrente.csv"
    if not historic_path.exists() or not current_path.exists():
        return """
    <section class="card">
      <h2>Ranking geral dos jogadores</h2>
      <p>Os arquivos do ranking geral ainda nao foram gerados. Rode <code>python Dash_Pixotada\\pixotada_scores.py</code> para atualizar esta visao.</p>
    </section>
    """

    historic = pd.read_csv(historic_path, encoding="utf-8-sig").head(15).copy()
    current = pd.read_csv(current_path, encoding="utf-8-sig").head(15).copy()
    display_columns = [
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
    ]
    column_labels = {
        "Posicao": "Posicao",
        "Jogadores": "Jogador",
        "Score_geral": "Score",
        "Jogos": "Jogos",
        "Gols_pg": "Gols/pelada",
        "Assist_pg": "Assist/pelada",
        "GolsTime_pg": "Gols time/pelada",
        "GolsSofridos_pg": "Gols sofridos/pelada",
        "JogosSemSofrer_pg": "SG/pelada",
        "Delta_points_pg": "Delta pontos/pelada",
    }

    def format_table(frame: pd.DataFrame) -> str:
        table_df = frame[display_columns].rename(columns=column_labels).copy()
        for column in table_df.columns:
            if table_df[column].dtype.kind in {"f"}:
                table_df[column] = table_df[column].map(lambda value: f"{value:.2f}")
        return table_df.to_html(index=False, classes="table sortable-table", border=0)

    historic_table = format_table(historic)
    current_table = format_table(current)
    return f"""
    <section class="card">
      <h2>Ranking geral dos jogadores</h2>
      <p>Visao principal orientada por medias por pelada, com pesos para gols, assistencias, desempenho coletivo, solidez defensiva e classificacao final x esperada.</p>
      <div class="selector-row">
        <label for="ranking-geral-select">Selecione o recorte</label>
        <select id="ranking-geral-select">
          <option value="historico">Historico geral</option>
          <option value="mes">Mes corrente</option>
        </select>
      </div>
      <div id="ranking-geral-historico" class="table-wrap">{historic_table}</div>
      <div id="ranking-geral-mes" class="table-wrap" style="display:none;">{current_table}</div>
      <p><a href="ranking_geral_jogadores.html">Abrir pagina completa do ranking geral</a></p>
    </section>
    <script>
      const rankingSelect = document.getElementById("ranking-geral-select");
      const rankingHistorico = document.getElementById("ranking-geral-historico");
      const rankingMes = document.getElementById("ranking-geral-mes");
      if (rankingSelect && rankingHistorico && rankingMes) {{
        rankingSelect.addEventListener("change", event => {{
          const showHistorico = event.target.value === "historico";
          rankingHistorico.style.display = showHistorico ? "block" : "none";
          rankingMes.style.display = showHistorico ? "none" : "block";
        }});
      }}
    </script>
    """


def build_dashboard(df: pd.DataFrame, summaries: dict[str, pd.DataFrame]) -> str:
    summary_df = summaries["resumo_jogadores"]
    eligible_players = summary_df.loc[summary_df["Jogos"] >= 4, "Jogadores"]
    chart_summary_df = summary_df.loc[summary_df["Jogadores"].isin(eligible_players)].copy()
    chart_df = df.loc[df["Jogadores"].isin(eligible_players)].copy()
    players_df = load_players()
    last4_cards = build_last4_cards(summaries["ultimas_4_datas"])
    general_ranking_spotlight = build_general_ranking_spotlight()

    figures = [
        player_scout_totals_switcher(chart_summary_df),
        player_scout_averages_switcher(chart_df),
        offensive_participation_blob_chart(chart_df, players_df),
        defensive_average_chart_switcher(chart_df),
        classification_games_adjusted_chart(chart_df),
        monthly_player_bar(chart_df),
        top10_switcher(chart_summary_df),
    ]

    cards = []
    for fig in figures:
        cards.append(
            f"""
            <section class="card">
              {fig.to_html(full_html=False, include_plotlyjs=False)}
            </section>
            """
        )

    top10_table = summary_df.head(10).rename(
        columns={
            "Assistencias": "Assist\u00eancias",
            "Participacoes": "Participa\u00e7\u00f5es",
        }
    ).to_html(index=False, classes="table sortable-table", border=0)

    plotly_js = get_plotlyjs()
    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Dashboard Pixotada 2026</title>
  <script>{plotly_js}</script>
  <style>
    :root {{
      --bg: #f6f1e8;
      --panel: #fffdf8;
      --ink: #1f2933;
      --line: #dccfb8;
      --accent: #0f766e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      background: linear-gradient(180deg, #efe4cf 0%, var(--bg) 40%, #f8f5ef 100%);
      color: var(--ink);
    }}
    .wrap {{
      width: min(1480px, calc(100% - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    .hero {{
      background: radial-gradient(circle at top left, #fff4dc 0%, #f7e7c6 38%, #ecd6ab 100%);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 28px;
      box-shadow: 0 12px 30px rgba(88, 71, 35, 0.08);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(28px, 4vw, 42px);
    }}
    p {{
      margin: 6px 0;
      line-height: 1.5;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 20px;
      margin-top: 20px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 18px;
      box-shadow: 0 10px 24px rgba(66, 52, 23, 0.06);
    }}
    .table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    .table-wrap {{
      max-height: 520px;
      overflow: auto;
      border: 1px solid #eadfc9;
      border-radius: 16px;
      background: #fff;
    }}
    .table th, .table td {{
      border-bottom: 1px solid #eadfc9;
      padding: 10px 8px;
      text-align: left;
    }}
    .table th {{
      background: #f6efe2;
      position: sticky;
      top: 0;
      z-index: 2;
    }}
    .sortable-table th {{
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
    }}
    .sortable-table th::after {{
      content: "  ↕";
      color: #8a7d66;
      font-size: 12px;
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
    .selector-row {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-bottom: 16px;
    }}
    .selector-row select {{
      max-width: 280px;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fff;
      font-size: 15px;
    }}
    .last4-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }}
    .match-card {{
      border: 1px solid #e6dcc8;
      border-radius: 18px;
      padding: 16px;
      background: linear-gradient(180deg, #fffefb 0%, #f8f1e5 100%);
    }}
    .match-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      gap: 8px;
    }}
    .match-head span {{
      font-size: 13px;
      color: #536471;
    }}
    .match-tag {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      background: #e8f6f3;
      color: var(--accent);
      font-size: 13px;
      margin-bottom: 14px;
    }}
    .match-stats {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }}
    .match-stats div {{
      padding: 10px;
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.7);
      border: 1px solid #efe4cf;
    }}
    .match-stats span {{
      display: block;
      font-size: 12px;
      color: #6b7280;
      margin-bottom: 4px;
    }}
    .match-stats strong {{
      font-size: 20px;
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Dashboard Scouts Pixotada 2026</h1>
      <p>Base analisada: {len(df)} registros, {df["Jogadores"].nunique()} jogadores, {df["Data"].nunique()} datas entre {df["Data"].min():%d/%m/%Y} e {df["Data"].max():%d/%m/%Y}.</p>
      <p>As classifica\u00e7\u00f5es foram normalizadas para evitar perda de contagem por diferen\u00e7a de acentua\u00e7\u00e3o.</p>
      <div class="nav">
        <a href="dashboard_pixotada_2026.html">Dashboard</a>
        <a href="ranking_modelos_ultimas4.html">Modelos de pontuação</a>
        <a href="ranking_geral_jogadores.html">Ranking geral</a>
        <a href="efeito_jogadores.html">Efeito dos jogadores</a>
        <a href="sugestao_novas_notas.html">Sugestão de notas</a>
        <a href="detalhe_recomendacoes_notas.html">Detalhe das recomendações</a>
      </div>
    </section>
    {general_ranking_spotlight}
    <section class="card">
      <h2>Top 10 geral em participa\u00e7\u00f5es</h2>
      <div class="table-wrap">
        {top10_table}
      </div>
    </section>
    <section class="grid">
      {''.join(cards)}
      {last4_cards}
    </section>
  </main>
  <script>
    function parseSortableValue(rawValue) {{
      const value = String(rawValue ?? "").trim();
      const normalized = value.replace(/\\./g, "").replace(",", ".");
      const numeric = Number(normalized);
      if (!Number.isNaN(numeric) && normalized !== "") {{
        return numeric;
      }}
      return value.toLocaleLowerCase("pt-BR");
    }}

    function sortTableByColumn(table, columnIndex, direction) {{
      const tbody = table.tBodies[0];
      if (!tbody) return;
      const rows = Array.from(tbody.rows);
      rows.sort((rowA, rowB) => {{
        const valueA = parseSortableValue(rowA.cells[columnIndex]?.innerText);
        const valueB = parseSortableValue(rowB.cells[columnIndex]?.innerText);
        if (typeof valueA === "number" && typeof valueB === "number") {{
          return direction === "asc" ? valueA - valueB : valueB - valueA;
        }}
        return direction === "asc"
          ? String(valueA).localeCompare(String(valueB), "pt-BR")
          : String(valueB).localeCompare(String(valueA), "pt-BR");
      }});
      rows.forEach(row => tbody.appendChild(row));
    }}

    document.querySelectorAll(".sortable-table").forEach(table => {{
      const headers = table.tHead ? Array.from(table.tHead.rows[0].cells) : [];
      headers.forEach((header, columnIndex) => {{
        header.dataset.sortDirection = "desc";
        header.addEventListener("click", () => {{
          const currentDirection = header.dataset.sortDirection === "asc" ? "desc" : "asc";
          headers.forEach(cell => cell.dataset.sortDirection = "");
          header.dataset.sortDirection = currentDirection;
          sortTableByColumn(table, columnIndex, currentDirection);
        }});
      }});
    }});
  </script>
</body>
</html>
"""


def write_outputs(df: pd.DataFrame, summaries: dict[str, pd.DataFrame]) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    PUBLIC_DIR.mkdir(exist_ok=True)
    diagnostics_df = df.attrs.get("match_result_diagnostics", pd.DataFrame())

    csv_exports = {
        "base_scouts_enriquecida": df.rename(
            columns={
                "classificacao": "Classificacao",
                "participacoes": "Participacoes",
                "gols_sofridos": "GolsSofridos",
                "gols_time": "GolsTime",
                "jogos_sem_sofrer": "JogosSemSofrer",
                "resultados_extraidos": "ResultadosExtraidos",
            }
        ).drop(columns=["classificacao_norm", "mes"]),
        "resumo_jogadores": summaries["resumo_jogadores"].rename(
            columns={"Assistencias": "Assistencias", "Participacoes": "Participacoes"}
        ),
        "distribuicao_classificacao": summaries["distribuicao_classificacao"].rename(columns=POSITION_LABELS),
        "resumo_mensal": summaries["resumo_mensal"].rename(columns={"Participacoes": "Participacoes"}),
        "ultimas_4_datas": summaries["ultimas_4_datas"].drop(columns=["classificacao_norm"]).rename(
            columns={"participacoes": "Participacoes", "classificacao": "Classificacao", "Recencia": "Recencia"}
        ),
    }

    for name, summary in csv_exports.items():
        summary.to_csv(OUTPUT_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")

    if not diagnostics_df.empty:
        diagnostics_df.to_csv(OUTPUT_DIR / "diagnostico_resultados_peladas.csv", index=False, encoding="utf-8-sig")

    html = build_dashboard(df, summaries)
    (OUTPUT_DIR / "dashboard_pixotada_2026.html").write_text(html, encoding="utf-8")
    (BASE_DIR / "dashboard_pixotada_2026.html").write_text(html, encoding="utf-8")
    (PUBLIC_DIR / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    df = load_data()
    summaries = build_summary_tables(df)
    write_outputs(df, summaries)
    print(f"Arquivos atualizados em: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
