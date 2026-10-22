"""Tâches périodiques du cœur (service « taches », toutes les heures).

    python -m coeur.taches                 # une fois
    python -m coeur.taches --boucle 3600   # indéfiniment, toutes les heures

- Centre d'appels : efface le numéro des demandes de rappel non traitées après
  CONSERVATION_RAPPELS_JOURS, supprime les enregistrements trop anciens.
- WhatsApp : envoie les rappels de passage dus (entre WHATSAPP_HEURE_DEBUT et
  WHATSAPP_HEURE_FIN), efface les abonnements dont le passage est fini, oublie les
  conversations restées en attente depuis plus d'un jour.
- Efface les compteurs de débit et la mémoire courte expirés (voir `coeur.limiteur`),
  et les identifiants des remontées de terrain après CONSERVATION_REMONTEES_JOURS.
"""

import argparse
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from coeur.base import nouvelle_session
from coeur.centre_appels.service import expirer_rappels, purger_enregistrements
from coeur.config import parametres
from coeur.limiteur import purger as purger_compteurs
from coeur.terrain.service import purger_remontees
from coeur.whatsapp import abonnements
from coeur.whatsapp.modeles import Conversation


def executer() -> dict[str, int]:
    reglages = parametres()
    with nouvelle_session() as session:
        resultat = {
            "rappels expirés": expirer_rappels(session, reglages.conservation_rappels_jours),
            "enregistrements supprimés": purger_enregistrements(
                session, reglages.conservation_enregistrements_jours),
            "rappels de passage envoyés": abonnements.envoyer_rappels(session, reglages),
            "abonnements expirés": abonnements.expirer(session, reglages),
        }
        hier = datetime.now(timezone.utc) - timedelta(days=1)
        resultat["conversations oubliées"] = session.execute(
            delete(Conversation).where(Conversation.maj_a < hier)).rowcount
        resultat["compteurs expirés"] = purger_compteurs(session)
        resultat["remontées oubliées"] = purger_remontees(session,
                                                          reglages.conservation_remontees_jours)
        session.commit()
    return resultat


def main() -> None:
    analyseur = argparse.ArgumentParser(prog="python -m coeur.taches")
    analyseur.add_argument("--boucle", type=int, metavar="SECONDES",
                           help="Recommencer indéfiniment à cet intervalle")
    args = analyseur.parse_args()
    while True:
        resultat = executer()
        detail = ", ".join(f"{n} {nom}" for nom, n in resultat.items())
        print(f"{datetime.now():%Y-%m-%d %H:%M} : {detail}.", flush=True)
        if not args.boucle:
            break
        time.sleep(args.boucle)


if __name__ == "__main__":
    main()
