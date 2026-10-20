"""Import du référentiel : python -m coeur.territoires importer donnees/territoires.csv"""

import argparse
from pathlib import Path

from coeur.base import nouvelle_session
from coeur.territoires.service import importer_csv


def main() -> None:
    analyseur = argparse.ArgumentParser(prog="python -m coeur.territoires")
    sous = analyseur.add_subparsers(dest="commande", required=True)
    imp = sous.add_parser("importer", help="Importer un fichier CSV de territoires")
    imp.add_argument("chemin", type=Path)
    args = analyseur.parse_args()

    with nouvelle_session() as session:
        nb_provinces, nb_territoires = importer_csv(session, args.chemin)
    print(f"{nb_provinces} provinces et {nb_territoires} territoires importés.")


if __name__ == "__main__":
    main()
