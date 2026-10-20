"""Contenus et calendrier de démonstration : python -m coeur.connaissances charger-exemples"""

import argparse
import sys

from coeur.base import nouvelle_session
from coeur.calendrier.service import charger_exemples as charger_calendrier
from coeur.config import parametres
from coeur.connaissances.exemples import charger_exemples


def main() -> None:
    analyseur = argparse.ArgumentParser(prog="python -m coeur.connaissances")
    sous = analyseur.add_subparsers(dest="commande", required=True)
    sous.add_parser("charger-exemples", help="Charger la FAQ de démonstration (hors production)")
    analyseur.parse_args()

    if parametres().environnement == "production":
        sys.exit("Refusé : les exemples ne sont pas validés par le BCR (ENVIRONNEMENT=production).")
    with nouvelle_session() as session:
        ids = charger_exemples(session)
        periodes = charger_calendrier(session)
    print(f"{len(ids)} contenus d'exemple et {periodes} dates de passage disponibles.")


if __name__ == "__main__":
    main()
