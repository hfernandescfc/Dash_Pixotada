# Alias Review

Este arquivo lista os aliases centralizados em [aliases.py](/Users/compesa/Desktop/Dash_Pixotada/aliases.py) e os casos que merecem revisao antes de consolidar os dados historicos.

## Aliases Atuais

| Origem no `players.json` | Destino nos scouts |
| --- | --- |
| Gabriel de Leon | Fuinha |
| Gabriel Lira | Gabriel |
| Guilherme Figueiredo | Guilherme |
| Guilherme Calafa | Calafa |
| Hugo | Hugão |
| Lucas Souza | Lucas |
| Paulo Freitas | Paulão |
| SHEIK / Sheik | Sheik |
| Girão | Diogo Girão |
| Junior | Júnior |
| Marcelo Torres | Marcelo |
| Claudio | Cláudio |
| Thiago cruz | Thiaguinho |
| Eduardo Jorge | JG |
| Davi | David Marques |

## Casos Com Maior Risco de Contagem Errada

| Caso | Situacao observada | Risco |
| --- | --- | --- |
| Gabriel de Leon -> Fuinha | `Fuinha` e `Gabriel de Leon` aparecem nos scouts | pode somar dois jogadores distintos ou duplicar historico |
| Lucas Souza -> Lucas | `Lucas` e `Lucas Souza` aparecem nos scouts | pode colapsar jogadores diferentes |
| Paulo Freitas -> Paulão | `Paulão` aparece nos scouts e `Paulo Freitas` existe no `players.json` | consolidacao depende de confirmar se sao a mesma pessoa |
| Hugo -> Hugão | scouts usam `Hugão`, cadastro usa `Hugo` | parece alias valido, mas deve ser mantido centralizado |
| Junior -> Júnior | scouts usam `Júnior`, cadastro usa `Junior` | parece alias valido, mas deve ser mantido centralizado |
| Girão -> Diogo Girão | cadastro abreviado, scout completo | parece alias valido, mas deve ser mantido centralizado |

## Casos Fora da Lista de Aliases Que Tambem Merecem Revisao

| Caso | Observacao |
| --- | --- |
| PA e Pedro Alonso | os dois nomes existem no ecossistema; hoje nao ha alias formal no codigo centralizado |
| David Marques e Davi | hoje existe alias `davi -> David Marques`; confirmar se sempre representam a mesma pessoa |
| Gabriel e Gabriel Lira | hoje existe alias `gabriel lira -> Gabriel`; confirmar se nao existe outro Gabriel no grupo |

## Recomendacao

Antes de corrigir os consolidados, revisar alias por alias e decidir:

1. quais pares devem ser unidos de fato
2. quais nomes devem permanecer separados
3. se o proprio CSV historico precisa de saneamento retroativo
