# Resultados manuais das peladas.
# Editado semanalmente após cada pelada.
#
# Formato de cada entrada:
#   "DD/MM/YYYY": {
#       "team_map": { "label": numero_do_time, ... },
#       "matches":  [ ("round_robin"|"third"|"final", label_A, gols_A, label_B, gols_B), ... ],
#   }
#
# Como encontrar o número do time:
#   Olhe a coluna "Time" no CSV para a data correspondente — cada jogador tem o número do seu time.
#   Use como label o nome do capitão/representante do time (em minúsculas, sem acentos).
#
# Ordem dos matches:
#   6 jogos "round_robin" (cada time joga contra os outros 3)
#   1 jogo "third"  (disputa do 3º lugar)
#   1 jogo "final"

MANUAL_PELADA_RESULTS: dict[str, dict] = {
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
    "24/03/2026": {
        "team_map": {"serginho": 1, "ps": 2, "guilherme": 3, "junior": 4},
        "matches": [
            ("round_robin", "serginho", 1, "ps", 0),
            ("round_robin", "junior", 2, "guilherme", 1),
            ("round_robin", "ps", 0, "junior", 0),
            ("round_robin", "guilherme", 1, "serginho", 1),
            ("round_robin", "junior", 1, "serginho", 1),
            ("round_robin", "guilherme", 1, "ps", 0),
            ("third", "guilherme", 3, "ps", 1),
            ("final", "junior", 1, "serginho", 0),
        ],
    },
    "07/04/2026": {
        "team_map": {"guilherme": 1, "ps": 2, "felipe": 3, "junior": 4},
        "matches": [
            ("round_robin", "ps", 0, "felipe", 0),
            ("round_robin", "junior", 1, "guilherme", 1),
            ("round_robin", "junior", 0, "felipe", 0),
            ("round_robin", "guilherme", 2, "ps", 2),
            ("round_robin", "guilherme", 0, "felipe", 1),
            ("round_robin", "ps", 3, "junior", 1),
            ("third", "guilherme", 2, "junior", 0),
            ("final", "ps", 0, "felipe", 1),
        ],
    },
}
