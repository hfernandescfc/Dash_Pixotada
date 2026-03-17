import unicodedata


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
