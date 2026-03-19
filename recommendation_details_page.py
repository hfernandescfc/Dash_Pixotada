from pathlib import Path
import json

import pandas as pd

from pixotada_dashboard import load_data
from rating_recommendations import (
    OUTPUT_DIR,
    PUBLIC_DIR,
    load_players,
    build_recent_form,
    build_adjusted_impact,
    build_pre_match_expected_results,
    build_participation_baseline,
    build_collective_baseline,
    evaluate_recommendation,
    suggest_row,
)


BASE_DIR = Path(__file__).resolve().parent
CLASS_LABELS = {"Campeao": "Campeão", "Segundo": "Segundo", "Terceiro": "Terceiro", "Lanterna": "Lanterna"}


def compute_base():
    scout_df = load_data()
    last6_dates = sorted(scout_df["Data"].drop_duplicates())[-6:]
    recent_df = scout_df[scout_df["Data"].isin(last6_dates)].copy()

    players_df = load_players()
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
    return scout_df, recent_df, players_df, result, last6_dates


def build_match_details(scout_df: pd.DataFrame, recent_df: pd.DataFrame) -> pd.DataFrame:
    merged = build_pre_match_expected_results(scout_df, recent_df).rename(columns={"forca_observada": "rating_base"})
    team_strength = merged.groupby(["Data", "Time"], as_index=False).agg(team_rating_mean=("rating_base", "mean"))
    merged = merged.merge(team_strength, on=["Data", "Time"], how="left")

    rows = []
    for (match_date, team), team_df in merged.groupby(["Data", "Time"]):
        team_players = team_df["Jogadores"].tolist()
        same_date = merged[merged["Data"] == match_date]
        opponents = same_date[same_date["Time"] != team]
        for row in team_df.itertuples():
            rows.append(
                {
                    "Jogadores": row.Jogadores,
                    "Data_fmt": row.Data.strftime("%d/%m/%Y"),
                    "Time": int(row.Time),
                    "Gols": int(row.Gol),
                    "Assistencias": int(row.Assist),
                    "Participacoes": int(row.participacoes),
                    "Classificacao": CLASS_LABELS.get(row.classificacao_norm, row.classificacao_norm),
                    "Pontos_reais": int(row.actual_points),
                    "Pontos_esperados": int(row.expected_points),
                    "Delta": float(row.delta_points),
                    "Gols_time": float(row.gols_time),
                    "Gols_sofridos": float(row.gols_sofridos),
                    "Jogos_sem_sofrer": float(row.jogos_sem_sofrer),
                    "Expected_gols_time": float(row.expected_gols_time),
                    "Expected_gols_sofridos": float(row.expected_gols_sofridos),
                    "Expected_jogos_sem_sofrer": float(row.expected_jogos_sem_sofrer),
                    "Delta_gols_time": float(row.delta_gols_time),
                    "Delta_gols_sofridos": float(row.delta_gols_sofridos),
                    "Delta_jogos_sem_sofrer": float(row.delta_jogos_sem_sofrer),
                    "Forca_time": float(row.team_strength),
                    "Media_nota_time": float(row.team_rating_mean),
                    "Companheiros": [name for name in team_players if name != row.Jogadores],
                    "Adversarios": sorted(opponents["Jogadores"].tolist()),
                }
            )
    return pd.DataFrame(rows)


def build_payload(result: pd.DataFrame, match_df: pd.DataFrame) -> dict:
    payload = {}
    known_players = set(match_df["Jogadores"].unique())

    for row in result.itertuples():
        player = row.scout_name
        player_matches = match_df[match_df["Jogadores"] == player].copy()
        player_matches = player_matches.sort_values("Data_fmt", ascending=False)
        evaluation = evaluate_recommendation(pd.Series(row._asdict()))
        payload[row.name] = {
            "jogador_json": row.name,
            "jogador_scout": player,
            "nota_atual": None if pd.isna(row.rating) else int(row.rating),
            "nova_nota_sugerida": None if pd.isna(row.nova_nota_sugerida) else int(row.nova_nota_sugerida),
            "sinal": row.sinal,
            "jogos_ult6": None if pd.isna(row.Jogos_ult6) else int(row.Jogos_ult6),
            "posicao_modelo_recente": None if pd.isna(row.Posicao) else int(row.Posicao),
            "participacoes_ult6": None if pd.isna(row.Participacoes_ult6) else int(row.Participacoes_ult6),
            "impacto_ajustado": None if pd.isna(row.Impacto_ajustado) else round(float(row.Impacto_ajustado), 2),
            "impacto_gols_time": None if pd.isna(row.Impacto_gols_time) else round(float(row.Impacto_gols_time), 2),
            "impacto_gols_sofridos": None
            if pd.isna(row.Impacto_gols_sofridos)
            else round(float(row.Impacto_gols_sofridos), 2),
            "impacto_jogos_sem_sofrer": None
            if pd.isna(row.Impacto_jogos_sem_sofrer)
            else round(float(row.Impacto_jogos_sem_sofrer), 2),
            "participacao_real_pg": None if pd.isna(row.Participacao_real_pg) else round(float(row.Participacao_real_pg), 2),
            "participacao_esperada_pg_nota": None
            if pd.isna(row.Participacao_esperada_pg_nota)
            else round(float(row.Participacao_esperada_pg_nota), 2),
            "delta_participacao_vs_nota": None
            if pd.isna(row.Delta_participacao_vs_nota)
            else round(float(row.Delta_participacao_vs_nota), 2),
            "gols_time_pg": None if pd.isna(row.Gols_time_pg) else round(float(row.Gols_time_pg), 2),
            "gols_time_esperados_pg_nota": None
            if pd.isna(row.Gols_time_esperados_pg_nota)
            else round(float(row.Gols_time_esperados_pg_nota), 2),
            "delta_gols_time_vs_nota": None
            if pd.isna(row.Delta_gols_time_vs_nota)
            else round(float(row.Delta_gols_time_vs_nota), 2),
            "gols_sofridos_pg": None if pd.isna(row.Gols_sofridos_pg) else round(float(row.Gols_sofridos_pg), 2),
            "gols_sofridos_esperados_pg_nota": None
            if pd.isna(row.Gols_sofridos_esperados_pg_nota)
            else round(float(row.Gols_sofridos_esperados_pg_nota), 2),
            "delta_gols_sofridos_vs_nota": None
            if pd.isna(row.Delta_gols_sofridos_vs_nota)
            else round(float(row.Delta_gols_sofridos_vs_nota), 2),
            "jogos_sem_sofrer_pg": None
            if pd.isna(row.Jogos_sem_sofrer_pg)
            else round(float(row.Jogos_sem_sofrer_pg), 2),
            "jogos_sem_sofrer_esperados_pg_nota": None
            if pd.isna(row.Jogos_sem_sofrer_esperados_pg_nota)
            else round(float(row.Jogos_sem_sofrer_esperados_pg_nota), 2),
            "delta_jogos_sem_sofrer_vs_nota": None
            if pd.isna(row.Delta_jogos_sem_sofrer_vs_nota)
            else round(float(row.Delta_jogos_sem_sofrer_vs_nota), 2),
            "justificativa": row.justificativa,
            "memoria_calculo": evaluation,
            "tem_correspondencia": player in known_players,
            "partidas": player_matches[
                [
                    "Data_fmt",
                    "Time",
                    "Gols",
                    "Assistencias",
                    "Participacoes",
                    "Classificacao",
                    "Pontos_reais",
                    "Pontos_esperados",
                    "Delta",
                    "Gols_time",
                    "Gols_sofridos",
                    "Jogos_sem_sofrer",
                    "Expected_gols_time",
                    "Expected_gols_sofridos",
                    "Expected_jogos_sem_sofrer",
                    "Delta_gols_time",
                    "Delta_gols_sofridos",
                    "Delta_jogos_sem_sofrer",
                    "Forca_time",
                    "Media_nota_time",
                    "Companheiros",
                    "Adversarios",
                ]
            ].to_dict(orient="records"),
        }
    return payload


def build_html(payload: dict, last6_dates: list[pd.Timestamp]) -> str:
    first_key = next(iter(payload))
    last6_str = ", ".join(date.strftime("%d/%m/%Y") for date in last6_dates)
    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Detalhe das recomendacoes</title>
  <style>
    :root {{
      --bg: #f6f1e8;
      --panel: #fffdf8;
      --ink: #1f2933;
      --muted: #6b7280;
      --line: #dccfb8;
      --accent: #0f766e;
      --up: #1e8449;
      --down: #922b21;
      --keep: #7f8c8d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    .wrap {{
      width: min(1400px, calc(100% - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    .hero, .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 20px;
      box-shadow: 0 10px 24px rgba(66, 52, 23, 0.06);
    }}
    .hero p {{
      margin: 6px 0;
      line-height: 1.5;
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
    .selector {{
      margin-top: 18px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-width: 340px;
    }}
    .selector select {{
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fff;
      font-size: 15px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.05fr 0.95fr;
      gap: 20px;
      margin-top: 20px;
      align-items: start;
    }}
    .headline {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 14px;
      align-items: start;
    }}
    .headline h2 {{
      margin: 0;
      font-size: 28px;
    }}
    .headline p {{
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.45;
    }}
    .tag {{
      display: inline-block;
      padding: 8px 12px;
      border-radius: 999px;
      font-weight: 700;
      white-space: nowrap;
      font-size: 13px;
    }}
    .tag.subir {{
      background: #e8f6f3;
      color: #117864;
    }}
    .tag.descer {{
      background: #fdecea;
      color: #922b21;
    }}
    .tag.manter {{
      background: #f6efe2;
      color: #6b5b45;
    }}
    .explanation {{
      margin-top: 16px;
      padding: 16px 18px;
      border-radius: 16px;
      border: 1px solid #eadfc9;
      background: #fffaf1;
    }}
    .explanation h3 {{
      margin: 0 0 8px;
      font-size: 18px;
    }}
    .explanation p {{
      margin: 0;
      line-height: 1.6;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 16px;
    }}
    .metric {{
      padding: 14px;
      border: 1px solid #eadfc9;
      border-radius: 16px;
      background: #fffaf1;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .metric strong {{
      display: block;
      font-size: 22px;
    }}
    .metric small {{
      display: block;
      margin-top: 6px;
      color: var(--muted);
      line-height: 1.4;
    }}
    details {{
      margin-top: 16px;
      border: 1px solid #eadfc9;
      border-radius: 16px;
      background: #fffaf1;
      overflow: hidden;
    }}
    summary {{
      cursor: pointer;
      list-style: none;
      padding: 16px 18px;
      font-weight: 700;
    }}
    summary::-webkit-details-marker {{
      display: none;
    }}
    .details-body {{
      border-top: 1px solid #efe4cf;
      padding: 0 18px 18px;
    }}
    .calc-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 14px;
    }}
    .calc-item {{
      border: 1px solid #eadfc9;
      border-radius: 14px;
      padding: 12px;
      background: #fff;
    }}
    .calc-item strong {{
      display: block;
      margin-bottom: 4px;
    }}
    .rule-list {{
      display: grid;
      gap: 8px;
      margin-top: 14px;
    }}
    .rule {{
      border-left: 4px solid var(--line);
      padding: 10px 12px;
      background: #fff;
      border-radius: 10px;
    }}
    .rule.hit {{
      border-left-color: var(--accent);
    }}
    .match-list {{
      display: grid;
      gap: 14px;
    }}
    .match {{
      border: 1px solid #eadfc9;
      border-radius: 16px;
      padding: 16px;
      background: #fffaf1;
    }}
    .match-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
      align-items: center;
    }}
    .match-title {{
      font-weight: 700;
      font-size: 17px;
    }}
    .delta {{
      font-weight: 700;
    }}
    .delta.pos {{ color: var(--up); }}
    .delta.neg {{ color: var(--down); }}
    .delta.neu {{ color: var(--keep); }}
    .match-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }}
    .mini {{
      padding: 10px;
      border-radius: 14px;
      background: #fff;
      border: 1px solid #efe4cf;
    }}
    .mini span {{
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
    }}
    .mini strong {{
      font-size: 18px;
    }}
    .people {{
      font-size: 14px;
      line-height: 1.45;
      color: #374151;
    }}
    .people strong {{
      display: block;
      margin-bottom: 2px;
      color: var(--ink);
    }}
    @media (max-width: 980px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
      .summary-grid, .match-grid, .calc-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 640px) {{
      .wrap {{
        width: min(100%, calc(100% - 20px));
      }}
      .summary-grid, .match-grid, .calc-grid {{
        grid-template-columns: 1fr;
      }}
      .headline h2 {{
        font-size: 24px;
      }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Detalhe das recomendacoes</h1>
      <p>Leitura simplificada por jogador, com foco na decisão final e no contexto recente.</p>
      <p>Janela analisada: {last6_str}.</p>
      <div class="nav">
        <a href="dashboard_pixotada_2026.html">Dashboard</a>
        <a href="ranking_geral_jogadores.html">Ranking geral</a>
        <a href="ranking_modelos_ultimas4.html">Modelos de pontuação</a>
        <a href="efeito_jogadores.html">Efeito dos jogadores</a>
        <a href="sugestao_novas_notas.html">Sugestão de notas</a>
        <a href="detalhe_recomendacoes_notas.html">Detalhe das recomendações</a>
      </div>
      <div class="selector">
        <label for="player-select">Selecione o jogador</label>
        <select id="player-select"></select>
      </div>
    </section>
    <section class="grid">
      <section class="card">
        <div class="headline">
          <div>
            <h2 id="player-name"></h2>
            <p id="player-subtitle"></p>
          </div>
          <div id="player-tag" class="tag manter"></div>
        </div>
        <div class="explanation">
          <h3>Resumo da recomendação</h3>
          <p id="player-reason"></p>
        </div>
        <div id="summary-grid" class="summary-grid"></div>
        <div id="calc-box"></div>
      </section>
      <section class="card">
        <h2>Partida por partida</h2>
        <p style="margin-top: 4px; color: var(--muted);">Cada cartão resume produção individual, resultado do time e contexto do jogo.</p>
        <div id="match-list" class="match-list"></div>
      </section>
    </section>
  </main>
  <script>
    const payload = {json.dumps(payload, ensure_ascii=False)};
    const select = document.getElementById('player-select');
    const playerName = document.getElementById('player-name');
    const playerSubtitle = document.getElementById('player-subtitle');
    const playerTag = document.getElementById('player-tag');
    const playerReason = document.getElementById('player-reason');
    const summaryGrid = document.getElementById('summary-grid');
    const calcBox = document.getElementById('calc-box');
    const matchList = document.getElementById('match-list');

    function metric(label, value, note = '') {{
      return `<div class="metric"><span>${{label}}</span><strong>${{value}}</strong>${{note ? `<small>${{note}}</small>` : ''}}</div>`;
    }}

    function formatSignal(signal) {{
      if (signal === 'subir') return 'Subir';
      if (signal === 'descer') return 'Descer';
      return 'Manter';
    }}

    function deltaClass(delta) {{
      if (delta > 0) return 'pos';
      if (delta < 0) return 'neg';
      return 'neu';
    }}

    function formatBool(value) {{
      if (value === null || value === undefined) return '-';
      return value ? 'Sim' : 'Não';
    }}

    function formatNumber(value, digits = 2) {{
      if (value === null || value === undefined || Number.isNaN(value)) return '-';
      return typeof value === 'number' ? value.toFixed(digits) : value;
    }}

    function formatSigned(value, digits = 2) {{
      if (value === null || value === undefined || Number.isNaN(value)) return '-';
      const formatted = Number(value).toFixed(digits);
      return value > 0 ? `+${{formatted}}` : formatted;
    }}

    function performanceLabel(value) {{
      if (value === null || value === undefined || Number.isNaN(value)) return 'Sem base suficiente';
      if (value >= 1.5) return 'Muito acima do esperado';
      if (value >= 0.5) return 'Acima do esperado';
      if (value <= -1.5) return 'Muito abaixo do esperado';
      if (value <= -0.5) return 'Abaixo do esperado';
      return 'Dentro do esperado';
    }}

    function buildRules(calc) {{
      const flags = calc.flags;
      return `
        <details>
          <summary>Critérios usados na decisão</summary>
          <div class="details-body">
            <div class="calc-grid">
              <div class="calc-item"><strong>Amostra mínima</strong>${{formatBool(flags.amostra_minima_ok)}}</div>
              <div class="calc-item"><strong>Regra acionada</strong>${{calc.decision.regra_acionada}}</div>
              <div class="calc-item"><strong>Jogador entre os melhores</strong>${{formatBool(calc.metrics.top_recent)}}</div>
              <div class="calc-item"><strong>Jogador entre os piores</strong>${{formatBool(calc.metrics.bottom_recent)}}</div>
              <div class="calc-item"><strong>Ataque acima da nota atual</strong>${{formatBool(flags.ataque_ok)}}</div>
              <div class="calc-item"><strong>Impacto coletivo forte</strong>${{formatBool(flags.coletivo_forte)}}</div>
            </div>
            <div class="rule-list">
              <div class="rule ${{flags.strong_up ? 'hit' : ''}}">
                <strong>Critério de subida principal</strong>
                <div>${{calc.thresholds.subida_principal}}</div>
                <div>Resultado: ${{formatBool(flags.strong_up)}}</div>
              </div>
              <div class="rule ${{flags.moderate_up ? 'hit' : ''}}">
                <strong>Critério de subida secundário</strong>
                <div>${{calc.thresholds.subida_secundaria}}</div>
                <div>Resultado: ${{formatBool(flags.moderate_up)}}</div>
              </div>
              <div class="rule ${{flags.strong_down ? 'hit' : ''}}">
                <strong>Critério de descida principal</strong>
                <div>${{calc.thresholds.descida_principal}}</div>
                <div>Resultado: ${{formatBool(flags.strong_down)}}</div>
              </div>
              <div class="rule ${{flags.moderate_down ? 'hit' : ''}}">
                <strong>Critério de descida secundário</strong>
                <div>${{calc.thresholds.descida_secundaria}}</div>
                <div>Resultado: ${{formatBool(flags.moderate_down)}}</div>
              </div>
            </div>
          </div>
        </details>
        <details>
          <summary>Base numérica usada no cálculo</summary>
          <div class="details-body">
            <div class="calc-grid">
              <div class="calc-item"><strong>Posição no modelo recente</strong>${{calc.metrics.posicao_modelo_recente ?? '-'}}</div>
              <div class="calc-item"><strong>Impacto recente do time</strong>${{formatNumber(calc.metrics.impacto_ajustado)}}</div>
              <div class="calc-item"><strong>Participações por jogo</strong>${{formatNumber(calc.metrics.participacao_real_pg)}}</div>
              <div class="calc-item"><strong>Participações esperadas para a nota</strong>${{formatNumber(calc.metrics.participacao_esperada_pg_nota)}}</div>
              <div class="calc-item"><strong>Gols do time por jogo</strong>${{formatNumber(calc.metrics.gols_time_pg)}}</div>
              <div class="calc-item"><strong>Gols do time esperados</strong>${{formatNumber(calc.metrics.gols_time_esperados_pg_nota)}}</div>
              <div class="calc-item"><strong>Gols sofridos por jogo</strong>${{formatNumber(calc.metrics.gols_sofridos_pg)}}</div>
              <div class="calc-item"><strong>Gols sofridos esperados</strong>${{formatNumber(calc.metrics.gols_sofridos_esperados_pg_nota)}}</div>
              <div class="calc-item"><strong>Jogos sem sofrer gols por jogo</strong>${{formatNumber(calc.metrics.jogos_sem_sofrer_pg)}}</div>
              <div class="calc-item"><strong>Jogos sem sofrer gols esperados</strong>${{formatNumber(calc.metrics.jogos_sem_sofrer_esperados_pg_nota)}}</div>
            </div>
          </div>
        </details>
      `;
    }}

    function renderPlayer(key) {{
      const item = payload[key];
      const calc = item.memoria_calculo;
      playerName.textContent = item.jogador_json;
      playerSubtitle.textContent = item.jogador_json !== item.jogador_scout ? `Nome no scout: ${{item.jogador_scout}}` : 'Nome já conciliado com a base de scouts';
      playerTag.className = `tag ${{item.sinal}}`;
      playerTag.textContent = `${{formatSignal(item.sinal)}}: ${{item.nota_atual ?? '-'}} → ${{item.nova_nota_sugerida ?? '-'}}`;
      playerReason.textContent = item.justificativa;

      summaryGrid.innerHTML = [
        metric('Nota atual', item.nota_atual ?? '-'),
        metric('Sugestão', item.nova_nota_sugerida ?? '-', formatSignal(item.sinal)),
        metric('Jogos recentes', item.jogos_ult6 ?? '-'),
        metric('Desempenho recente', performanceLabel(item.impacto_ajustado), `Impacto do time: ${{formatNumber(item.impacto_ajustado)}}`),
        metric('Posição no modelo recente', item.posicao_modelo_recente ?? '-'),
        metric('Participações nas últimas 6', item.participacoes_ult6 ?? '-'),
        metric('Gols do time por jogo', formatNumber(item.gols_time_pg), `Esperado para a nota: ${{formatNumber(item.gols_time_esperados_pg_nota)}}`),
        metric('Gols sofridos por jogo', formatNumber(item.gols_sofridos_pg), `Esperado para a nota: ${{formatNumber(item.gols_sofridos_esperados_pg_nota)}}`),
        metric('Jogos sem sofrer gols por jogo', formatNumber(item.jogos_sem_sofrer_pg), `Esperado para a nota: ${{formatNumber(item.jogos_sem_sofrer_esperados_pg_nota)}}`),
      ].join('');

      calcBox.innerHTML = buildRules(calc);

      if (!item.partidas.length) {{
        matchList.innerHTML = '<p>Sem partidas detalhadas nesse recorte.</p>';
        return;
      }}

      matchList.innerHTML = item.partidas.map(match => `
        <article class="match">
          <div class="match-head">
            <div class="match-title">${{match.Data_fmt}} | Time ${{match.Time}} | ${{match.Classificacao}}</div>
            <div class="delta ${{deltaClass(match.Delta)}}">Resultado do time vs esperado: ${{formatSigned(match.Delta)}}</div>
          </div>
          <div class="match-grid">
            <div class="mini"><span>Produção individual</span><strong>${{match.Gols}} G | ${{match.Assistencias}} A | ${{match.Participacoes}} P</strong></div>
            <div class="mini"><span>Pontos do time</span><strong>${{match.Pontos_reais}} reais | ${{match.Pontos_esperados}} esperados</strong></div>
            <div class="mini"><span>Força média do time</span><strong>${{formatNumber(match.Media_nota_time)}}</strong></div>
            <div class="mini"><span>Gols do time</span><strong>${{formatNumber(match.Gols_time, 1)}}</strong></div>
            <div class="mini"><span>Gols sofridos</span><strong>${{formatNumber(match.Gols_sofridos, 1)}}</strong></div>
            <div class="mini"><span>Jogo sem sofrer gols</span><strong>${{match.Jogos_sem_sofrer ? 'Sim' : 'Não'}}</strong></div>
            <div class="mini"><span>Comparação com o esperado</span><strong>Ataque ${{formatSigned(match.Delta_gols_time)}} | Defesa ${{formatSigned(match.Delta_gols_sofridos)}} | SG ${{formatSigned(match.Delta_jogos_sem_sofrer)}}</strong></div>
            <div class="mini"><span>Gols do time esperados</span><strong>${{formatNumber(match.Expected_gols_time)}}</strong></div>
            <div class="mini"><span>Gols sofridos esperados</span><strong>${{formatNumber(match.Expected_gols_sofridos)}}</strong></div>
          </div>
          <div class="people"><strong>Companheiros</strong>${{match.Companheiros.join(', ') || '—'}}</div>
          <div class="people" style="margin-top:8px;"><strong>Adversários</strong>${{match.Adversarios.join(', ') || '—'}}</div>
        </article>
      `).join('');
    }}

    Object.keys(payload).sort((a, b) => a.localeCompare(b, 'pt-BR')).forEach(key => {{
      const option = document.createElement('option');
      option.value = key;
      option.textContent = key;
      select.appendChild(option);
    }});

    select.value = {json.dumps(first_key, ensure_ascii=False)};
    renderPlayer(select.value);
    select.addEventListener('change', event => renderPlayer(event.target.value));
  </script>
</body>
</html>
"""


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    PUBLIC_DIR.mkdir(exist_ok=True)

    scout_df, recent_df, _players_df, result, last6_dates = compute_base()
    match_df = build_match_details(scout_df, recent_df)
    payload = build_payload(result, match_df)

    html = build_html(payload, last6_dates)
    (OUTPUT_DIR / "detalhe_recomendacoes_notas.html").write_text(html, encoding="utf-8")
    (BASE_DIR / "detalhe_recomendacoes_notas.html").write_text(html, encoding="utf-8")
    (PUBLIC_DIR / "detalhe_recomendacoes_notas.html").write_text(html, encoding="utf-8")

    print(f"Arquivos gerados em: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
