"""
Executa todos os scripts de geração do dashboard na ordem correta.
Uso: python atualizar.py
"""

import subprocess
import sys
from pathlib import Path

SCRIPTS = [
    "pixotada_dashboard.py",
    "pixotada_scores.py",
    "pixotada_effect_analysis.py",
    "rating_recommendations.py",
    "recommendation_details_page.py",
]

BASE_DIR = Path(__file__).parent


def run(script: str) -> bool:
    print(f"\n{'='*60}")
    print(f"  {script}")
    print(f"{'='*60}")
    result = subprocess.run(
        [sys.executable, BASE_DIR / script],
        cwd=BASE_DIR,
    )
    if result.returncode != 0:
        print(f"\nERRO: {script} falhou com código {result.returncode}.")
        return False
    return True


def main() -> None:
    for script in SCRIPTS:
        if not run(script):
            print("\nAtualização interrompida.")
            sys.exit(1)
    print("\nTodas as páginas foram atualizadas com sucesso.")


if __name__ == "__main__":
    main()
