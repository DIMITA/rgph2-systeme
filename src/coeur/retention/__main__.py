"""Purge : python -m coeur.retention purger --avant AAAA-MM-JJ

Règle (architecture.md) : tout supprimer au plus tard six mois après la
publication des résultats du RGPH-2. Pour tout effacer, donner la date du lendemain.
"""

import argparse
from datetime import date, datetime, time, timezone

from coeur.base import nouvelle_session
from coeur.retention.service import purger


def main() -> None:
    analyseur = argparse.ArgumentParser(prog="python -m coeur.retention")
    sous = analyseur.add_subparsers(dest="commande", required=True)
    cmd = sous.add_parser("purger", help="Supprimer les données enregistrées avant une date")
    cmd.add_argument("--avant", type=date.fromisoformat, required=True, help="AAAA-MM-JJ (exclue)")
    args = analyseur.parse_args()

    limite = datetime.combine(args.avant, time.min, timezone.utc)
    with nouvelle_session() as session:
        supprimes = purger(session, limite)
    detail = ", ".join(f"{nombre} {nom}" for nom, nombre in supprimes.items())
    print(f"Avant le {args.avant.isoformat()}, supprimés : {detail}.")


if __name__ == "__main__":
    main()
