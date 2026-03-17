from pathlib import Path
import json
import unicodedata

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

import aliases as alias_lib


BASE_DIR = Path(r"c:\Users\compesa\Desktop")
INPUT_FILE = BASE_DIR / "SCOUTS PIXOTADA 2026 - BASE.csv"
PLAYERS_FILE = BASE_DIR / "Peladapp" / "players.json"
OUTPUT_DIR = BASE_DIR / "pixotada_2026_dashboard"
PUBLIC_DIR = BASE_DIR / "pixotada_public_site"

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


def normalize_text(value: str) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text


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


def overall_bar(df: pd.DataFrame, value_col: str, title: str, color: str, axis_label: str) -> go.Figure:
    chart_df = df.sort_values([value_col, "Jogadores"], ascending=[False, True])
    fig = px.bar(
        chart_df,
        x="Jogadores",
        y=value_col,
        text_auto=True,
        color_discrete_sequence=[color],
        title=title,
    )
    fig.update_layout(
        template="plotly_white",
        height=560,
        margin=dict(l=40, r=20, t=70, b=140),
        xaxis_title="Jogador",
        yaxis_title=axis_label,
        xaxis_tickangle=-45,
        showlegend=False,
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
        )
    )
    chart_df["Nivel"] = chart_df["Nivel"].astype(int).astype(str)
    level_order = [str(level) for level in sorted(chart_df["Nivel"].unique(), key=int)]

    fig = px.violin(
        chart_df,
        x="Nivel",
        y="Participacoes_media",
        color="Nivel",
        category_orders={"Nivel": level_order},
        box=True,
        points="all",
        hover_data={
            "Jogadores": True,
            "Jogos": True,
            "Participacoes_totais": True,
            "Participacoes_media": ":.2f",
            "Nivel": False,
        },
        title="Mancha de participacoes ofensivas medias por nivel do jogador",
    )
    fig.update_traces(
        meanline_visible=True,
        marker=dict(size=6, opacity=0.5),
        pointpos=0,
        jitter=0.16,
        hovertemplate=(
            "Nivel: %{x}<br>"
            "Participacoes medias/jogo: %{y:.2f}<br>"
            "Jogador: %{customdata[0]}<br>"
            "Jogos: %{customdata[1]}<br>"
            "Participacoes totais: %{customdata[2]}<extra></extra>"
        ),
    )
    fig.update_layout(
        template="plotly_white",
        height=620,
        margin=dict(l=40, r=20, t=70, b=40),
        xaxis_title="Nivel do jogador",
        yaxis_title="Participacoes ofensivas medias por jogo",
        legend_title="Nivel",
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


def build_dashboard(df: pd.DataFrame, summaries: dict[str, pd.DataFrame]) -> str:
    summary_df = summaries["resumo_jogadores"]
    eligible_players = summary_df.loc[summary_df["Jogos"] >= 4, "Jogadores"]
    chart_summary_df = summary_df.loc[summary_df["Jogadores"].isin(eligible_players)].copy()
    chart_df = df.loc[df["Jogadores"].isin(eligible_players)].copy()
    players_df = load_players()
    last4_cards = build_last4_cards(summaries["ultimas_4_datas"])

    figures = [
        overall_bar(chart_summary_df, "Gols", "N\u00famero de gols por jogador", "#c0392b", "Gols"),
        overall_bar(chart_summary_df, "Assistencias", "N\u00famero de assist\u00eancias por jogador", "#2980b9", "Assist\u00eancias"),
        overall_bar(chart_summary_df, "Participacoes", "Total de participa\u00e7\u00f5es em gol por jogador", "#16a085", "Participa\u00e7\u00f5es"),
        offensive_participation_blob_chart(chart_df, players_df),
        classification_games_adjusted_chart(chart_df),
        monthly_player_bar(chart_df),
        top10_bar(chart_summary_df, "Gols", "Top 10 de gols", "#c0392b", "Gols"),
        top10_bar(chart_summary_df, "Assistencias", "Top 10 de assist\u00eancias", "#2980b9", "Assist\u00eancias"),
        top10_bar(chart_summary_df, "Participacoes", "Top 10 de participa\u00e7\u00f5es em gol", "#16a085", "Participa\u00e7\u00f5es"),
        top10_bar(chart_summary_df, "Amarelos", "Top 10 de cart\u00f5es amarelos", "#f1c40f", "Amarelos"),
        top10_bar(chart_summary_df, "Vermelhos", "Top 10 de cart\u00f5es vermelhos", "#7f1d1d", "Vermelhos"),
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
    ).to_html(index=False, classes="table", border=0)

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
        <a href="efeito_jogadores.html">Efeito dos jogadores</a>
        <a href="sugestao_novas_notas.html">Sugestão de notas</a>
        <a href="detalhe_recomendacoes_notas.html">Detalhe das recomendações</a>
      </div>
    </section>
    <section class="card">
      <h2>Top 10 geral em participa\u00e7\u00f5es</h2>
      {top10_table}
    </section>
    <section class="grid">
      {''.join(cards)}
      {last4_cards}
    </section>
  </main>
</body>
</html>
"""


def write_outputs(df: pd.DataFrame, summaries: dict[str, pd.DataFrame]) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    PUBLIC_DIR.mkdir(exist_ok=True)

    csv_exports = {
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
