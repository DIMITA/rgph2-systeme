"""Import de la liste des badges : python -m coeur.badges importer badges.csv

Le fichier remplace toute la liste précédente. Colonnes : numero, territoire_code, actif
(1 = badge en service, 0 = retiré). Supprimer le fichier après l'import.
"""

import argparse
import sys
from pathlib import Path

from coeur.badges.service import importer_csv
from coeur.base import nouvelle_session
from coeur.config import parametres


def main() -> None:
    analyseur = argparse.ArgumentParser(prog="python -m coeur.badges")
    sous = analyseur.add_subparsers(dest="commande", required=True)
    imp = sous.add_parser("importer", help="Remplacer la liste des badges par un fichier CSV")
    imp.add_argument("chemin", type=Path)
    args = analyseur.parse_args()

    with nouvelle_session() as session:
        try:
            actifs, retires = importer_csv(session, args.chemin, parametres().pepper_telephone)
        except ValueError as erreur:
            sys.exit(str(erreur))
    print(f"{actifs} badges actifs et {retires} badges retirés importés.")


if __name__ == "__main__":
    main()
