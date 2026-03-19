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
    evaluate_recommendation,
    suggest_row,
)


BASE_DIR = Path(r"c:\Users\compesa\Desktop")
EXPECTED_POINTS_MAP = {1.0: 4, 2.0: 3, 3.0: 2, 4.0: 1}
CLASS_LABELS = {"Campeao": "Campeão", "Segundo": "Segundo", "Terceiro": "Terceiro", "Lanterna": "Lanterna"}
CLASS_POINTS = {"Campeao": 4, "Segundo": 3, "Terceiro": 2, "Lanterna": 1}


def compute_base():
    scout_df = load_data()
    last6_dates = sorted(scout_df["Data"].drop_duplicates())[-6:]
    recent_df = scout_df[scout_df["Data"].isin(last6_dates)].copy()

    players_df = load_players()

    games_count = recent_df.groupby("Jogadores").size().rename("Jogos_ult6").reset_index()
    all_recent_names = sorted(recent_df["Jogadores"].drop_duplicates().tolist())

    recent_form = build_recent_form(recent_df, all_recent_names)
    adjusted = build_adjusted_impact(scout_df, recent_df)
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
    return scout_df, recent_df, players_df, result, last6_dates


def build_match_details(scout_df: pd.DataFrame, recent_df: pd.DataFrame) -> pd.DataFrame:
    merged = build_pre_match_expected_results(scout_df, recent_df).rename(columns={"forca_observada": "rating_base"})
    team_strength = (
        merged.groupby(["Data", "Time"], as_index=False)
        .agg(team_rating_mean=("rating_base", "mean"))
    )
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
                    "Forca_time": float(row.team_strength),
                    "Media_nota_time": float(row.team_rating_mean),
                    "Companheiros": [name for name in team_players if name != row.Jogadores],
                    "Adversarios": sorted(opponents["Jogadores"].tolist()),
                }
            )
    return pd.DataFrame(rows)


def build_payload(result: pd.DataFrame, match_df: pd.DataFrame) -> dict:
    payload = {}
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
            "participacao_real_pg": None if pd.isna(row.Participacao_real_pg) else round(float(row.Participacao_real_pg), 2),
            "participacao_esperada_pg_nota": None
            if pd.isna(row.Participacao_esperada_pg_nota)
            else round(float(row.Participacao_esperada_pg_nota), 2),
            "delta_participacao_vs_nota": None
            if pd.isna(row.Delta_participacao_vs_nota)
            else round(float(row.Delta_participacao_vs_nota), 2),
            "justificativa": row.justificativa,
            "memoria_calculo": evaluation,
            "tem_correspondencia": player in set(match_df["Jogadores"].unique()),
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
  <title>Detalhamento das Recomendações de Nota</title>
  <style>
    :root {{
      --bg: #f6f1e8;
      --panel: #fffdf8;
      --ink: #1f2933;
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
      background: linear-gradient(180deg, #efe4cf 0%, var(--bg) 40%, #f8f5ef 100%);
      color: var(--ink);
    }}
    .wrap {{
      width: min(1380px, calc(100% - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    .hero, .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 22px;
      box-shadow: 0 12px 30px rgba(88, 71, 35, 0.08);
    }}
    .hero p {{
      margin: 6px 0;
      line-height: 1.5;
    }}
    .selector {{
      margin-top: 18px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .selector select {{
      max-width: 320px;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fff;
      font-size: 15px;
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
    .grid {{
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 20px;
      margin-top: 20px;
      align-items: start;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 16px;
    }}
    .metric {{
      padding: 14px;
      border: 1px solid #eadfc9;
      border-radius: 16px;
      background: #fff;
    }}
    .metric span {{
      display: block;
      color: #6b7280;
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .metric strong {{
      font-size: 22px;
    }}
    .tag {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      color: white;
      font-weight: 600;
      margin-top: 8px;
    }}
    .tag.subir {{ background: var(--up); }}
    .tag.descer {{ background: var(--down); }}
    .tag.manter {{ background: var(--keep); }}
    .match-list {{
      display: grid;
      gap: 14px;
    }}
    .match {{
      border: 1px solid #eadfc9;
      border-radius: 18px;
      padding: 16px;
      background: linear-gradient(180deg, #fffefb 0%, #f8f1e5 100%);
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
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }}
    .mini {{
      padding: 10px;
      border-radius: 14px;
      background: rgba(255,255,255,0.78);
      border: 1px solid #efe4cf;
    }}
    .mini span {{
      display: block;
      font-size: 12px;
      color: #6b7280;
      margin-bottom: 4px;
    }}
    .mini strong {{
      font-size: 18px;
    }}
    .people {{
      font-size: 14px;
      line-height: 1.45;
    }}
    .people strong {{
      display: block;
      margin-bottom: 2px;
    }}
    .calc-box {{
      margin-top: 18px;
      border: 1px solid #eadfc9;
      border-radius: 18px;
      padding: 16px;
      background: linear-gradient(180deg, #fffefb 0%, #f7efe2 100%);
    }}
    .calc-box h3 {{
      margin: 0 0 12px;
      font-size: 18px;
    }}
    .calc-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }}
    .calc-item {{
      border: 1px solid #eadfc9;
      border-radius: 14px;
      padding: 12px;
      background: rgba(255,255,255,0.9);
    }}
    .calc-item strong {{
      display: block;
      margin-bottom: 4px;
    }}
    .rule-list {{
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }}
    .rule {{
      border-left: 4px solid var(--line);
      padding: 10px 12px;
      background: rgba(255,255,255,0.82);
      border-radius: 10px;
    }}
    .rule.hit {{
      border-left-color: var(--accent);
    }}
    @media (max-width: 980px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
      .summary-grid, .match-grid, .calc-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Detalhamento das Recomendações de Nota</h1>
      <p>Esta página mostra, jogador por jogador, como a recomendação foi construída a partir das últimas 6 peladas.</p>
      <p>Janela analisada: {last6_str}.</p>
      <p>A classificação recente segue como critério principal; participações ofensivas entram como moderador em relação à nota atual.</p>
      <div class="nav">
        <a href="dashboard_pixotada_2026.html">Dashboard</a>
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
        <h2 id="player-name"></h2>
        <div id="player-tag" class="tag manter"></div>
        <p id="player-reason"></p>
        <div id="summary-grid" class="summary-grid"></div>
        <div id="calc-box" class="calc-box"></div>
      </section>
      <section class="card">
        <h2>Partida por partida</h2>
        <div id="match-list" class="match-list"></div>
      </section>
    </section>
  </main>
  <script>
    const payload = {json.dumps(payload, ensure_ascii=False)};
    const select = document.getElementById('player-select');
    const playerName = document.getElementById('player-name');
    const playerTag = document.getElementById('player-tag');
    const playerReason = document.getElementById('player-reason');
    const summaryGrid = document.getElementById('summary-grid');
    const calcBox = document.getElementById('calc-box');
    const matchList = document.getElementById('match-list');

    function metric(label, value) {{
      return `<div class="metric"><span>${{label}}</span><strong>${{value}}</strong></div>`;
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

    function formatNumber(value) {{
      if (value === null || value === undefined) return '-';
      return typeof value === 'number' ? value.toFixed(2) : value;
    }}

    function renderPlayer(key) {{
      const item = payload[key];
      const calc = item.memoria_calculo;
      const metrics = calc.metrics;
      const flags = calc.flags;
      const decision = calc.decision;
      playerName.textContent = `${{item.jogador_json}}${{item.jogador_json !== item.jogador_scout ? ' (' + item.jogador_scout + ')' : ''}}`;
      playerTag.className = `tag ${{item.sinal}}`;
      playerTag.textContent = `${{formatSignal(item.sinal)}}: ${{item.nota_atual ?? '-'}} → ${{item.nova_nota_sugerida ?? '-'}}`;
      playerReason.textContent = item.justificativa;

      summaryGrid.innerHTML = [
        metric('Nota atual', item.nota_atual ?? '-'),
        metric('Nova nota sugerida', item.nova_nota_sugerida ?? '-'),
        metric('Jogos nas últimas 6', item.jogos_ult6 ?? '-'),
        metric('Posição no modelo recente', item.posicao_modelo_recente ?? '-'),
        metric('Participações nas últimas 6', item.participacoes_ult6 ?? '-'),
        metric('Impacto ajustado', item.impacto_ajustado ?? '-'),
        metric('Participações por jogo', item.participacao_real_pg ?? '-'),
        metric('Esperado p/ a nota', item.participacao_esperada_pg_nota ?? '-'),
        metric('Delta participação vs nota', item.delta_participacao_vs_nota ?? '-'),
        metric('Correspondência no scout', item.tem_correspondencia ? 'Sim' : 'Não'),
        metric('Sinal', formatSignal(item.sinal)),
      ].join('');

      calcBox.innerHTML = `
        <h3>Memória de cálculo</h3>
        <div class="calc-grid">
          <div class="calc-item"><strong>Amostra mínima ok</strong>${{formatBool(flags.amostra_minima_ok)}}</div>
          <div class="calc-item"><strong>Regra acionada</strong>${{decision.regra_acionada}}</div>
          <div class="calc-item"><strong>Top recente</strong>${{formatBool(metrics.top_recent)}}</div>
          <div class="calc-item"><strong>Bottom recente</strong>${{formatBool(metrics.bottom_recent)}}</div>
          <div class="calc-item"><strong>Ataque ok</strong>${{formatBool(flags.ataque_ok)}}</div>
          <div class="calc-item"><strong>Ataque forte</strong>${{formatBool(flags.ataque_forte)}}</div>
          <div class="calc-item"><strong>Ataque fraco</strong>${{formatBool(flags.ataque_fraco)}}</div>
          <div class="calc-item"><strong>Ataque muito fraco</strong>${{formatBool(flags.ataque_muito_fraco)}}</div>
        </div>
        <div class="rule-list">
          <div class="rule ${{flags.strong_up ? 'hit' : ''}}">
            <strong>Subida principal</strong>
            <div>${{calc.thresholds.subida_principal}}</div>
            <div>Resultado: ${{formatBool(flags.strong_up)}}</div>
          </div>
          <div class="rule ${{flags.moderate_up ? 'hit' : ''}}">
            <strong>Subida secundária</strong>
            <div>${{calc.thresholds.subida_secundaria}}</div>
            <div>Resultado: ${{formatBool(flags.moderate_up)}}</div>
          </div>
          <div class="rule ${{flags.strong_down ? 'hit' : ''}}">
            <strong>Descida principal</strong>
            <div>${{calc.thresholds.descida_principal}}</div>
            <div>Resultado: ${{formatBool(flags.strong_down)}}</div>
          </div>
          <div class="rule ${{flags.moderate_down ? 'hit' : ''}}">
            <strong>Descida secundária</strong>
            <div>${{calc.thresholds.descida_secundaria}}</div>
            <div>Resultado: ${{formatBool(flags.moderate_down)}}</div>
          </div>
          <div class="rule hit">
            <strong>Valores usados na decisão</strong>
            <div>Posição recente: ${{metrics.posicao_modelo_recente ?? '-'}} | Impacto ajustado: ${{formatNumber(metrics.impacto_ajustado)}} | Jogos: ${{metrics.jogos_ult6 ?? '-'}}</div>
            <div>Participação real/jogo: ${{formatNumber(metrics.participacao_real_pg)}} | Esperado p/ nota: ${{formatNumber(metrics.participacao_esperada_pg_nota)}} | Delta: ${{formatNumber(metrics.delta_participacao_vs_nota)}}</div>
          </div>
        </div>
      `;

      if (!item.partidas.length) {{
        matchList.innerHTML = '<p>Sem partidas detalhadas nesse recorte.</p>';
        return;
      }}

      matchList.innerHTML = item.partidas.map(match => `
        <article class="match">
          <div class="match-head">
            <div class="match-title">${{match.Data_fmt}} | Time ${{match.Time}} | ${{match.Classificacao}}</div>
            <div class="delta ${{deltaClass(match.Delta)}}">Delta: ${{match.Delta > 0 ? '+' : ''}}${{match.Delta.toFixed(2)}}</div>
          </div>
          <div class="match-grid">
            <div class="mini"><span>Gols</span><strong>${{match.Gols}}</strong></div>
            <div class="mini"><span>Assistências</span><strong>${{match.Assistencias}}</strong></div>
            <div class="mini"><span>Participações</span><strong>${{match.Participacoes}}</strong></div>
            <div class="mini"><span>Pontos reais / esperados</span><strong>${{match.Pontos_reais}} / ${{match.Pontos_esperados}}</strong></div>
            <div class="mini"><span>Força do time</span><strong>${{match.Forca_time.toFixed(2)}}</strong></div>
            <div class="mini"><span>Média de força observada</span><strong>${{match.Media_nota_time.toFixed(2)}}</strong></div>
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
