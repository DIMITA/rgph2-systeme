"""Tâches de conservation du centre d'appels seulement.

Le service « taches » utilise désormais `python -m coeur.taches`, qui les regroupe
avec celles des autres canaux.

    python -m coeur.centre_appels taches             # une fois
    python -m coeur.centre_appels taches --boucle 3600  # toutes les heures (service « taches »)

Efface le numéro des demandes de rappel non traitées après CONSERVATION_RAPPELS_JOURS
et supprime les enregistrements de plus de CONSERVATION_ENREGISTREMENTS_JOURS.
"""

import argparse
import time
from datetime import datetime

from coeur.base import nouvelle_session
from coeur.centre_appels.service import expirer_rappels, purger_enregistrements
from coeur.config import parametres


def executer() -> None:
    reglages = parametres()
    with nouvelle_session() as session:
        rappels = expirer_rappels(session, reglages.conservation_rappels_jours)
        enregistrements = purger_enregistrements(
            session, reglages.conservation_enregistrements_jours
        )
    print(f"{datetime.now():%Y-%m-%d %H:%M} : {rappels} rappel(s) expiré(s), "
          f"{enregistrements} enregistrement(s) supprimé(s).", flush=True)


def main() -> None:
    analyseur = argparse.ArgumentParser(prog="python -m coeur.centre_appels")
    sous = analyseur.add_subparsers(dest="commande", required=True)
    taches = sous.add_parser("taches", help="Expirer les rappels, purger les enregistrements")
    taches.add_argument("--boucle", type=int, metavar="SECONDES",
                        help="Recommencer indéfiniment à cet intervalle")
    args = analyseur.parse_args()
    while True:
        executer()
        if not args.boucle:
            break
        time.sleep(args.boucle)


if __name__ == "__main__":
    main()
