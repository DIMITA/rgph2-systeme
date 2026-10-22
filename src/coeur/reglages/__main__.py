"""Assistant d'initialisation et gestion des réglages chiffrés.

À lancer avec le rôle propriétaire de la base (service « migrations ») et CLE_MAITRE :

    docker compose run --rm migrations python -m coeur.reglages initialiser
    docker compose run --rm migrations python -m coeur.reglages lister
    docker compose run --rm migrations python -m coeur.reglages afficher whatsapp_jeton_verification
    docker compose run --rm migrations python -m coeur.reglages definir numero_vert "0800 000 000"
    docker compose run --rm migrations python -m coeur.reglages definir whatsapp_jeton   # saisie masquée
    docker compose run --rm -T migrations python -m coeur.reglages importer-env - < .env.a-importer
    docker compose run --rm -e CLE_MAITRE_NOUVELLE=… migrations python -m coeur.reglages changer-cle-maitre

Toute modification est prise en compte au redémarrage de l'API et des tâches :
    docker compose restart api taches
"""

import argparse
import getpass
import os
import sys

from dotenv import dotenv_values
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from coeur.reglages import service
from coeur.reglages.catalogue import QUESTIONS
from coeur.reglages.source import cle_maitre


def _demander(question, actuelle: str | None) -> str | None:
    """Nouvelle valeur, ou None pour garder l'actuelle (Entrée)."""
    print(f"\n{question.libelle}")
    if question.aide:
        print(f"  {question.aide}")
    if question.choix:
        print(f"  Choix : {', '.join(question.choix)}")
    if actuelle is not None:
        print(f"  Actuel : {service.masquer(question.champ, actuelle) or '(vide)'}  "
              "— Entrée pour le garder")
    while True:
        saisie = (getpass.getpass("  > ") if question.secret else input("  > ")).strip()
        if not saisie and actuelle is not None:
            return None
        if question.choix and saisie not in question.choix:
            print(f"  Répondre par : {', '.join(question.choix)}")
            continue
        try:
            service.valider(question.champ, saisie)
        except ValueError as erreur:
            print(f"  {erreur}")
            continue
        return saisie


def initialiser(session: Session, cle: str, interactif: bool) -> None:
    actuelles = service.lire(session, cle)
    nouvelles: dict[str, str] = {}
    for question in QUESTIONS:
        connues = {**actuelles, **nouvelles}
        if question.si and not question.si(connues):
            continue
        if question.generer:
            if question.champ not in actuelles:
                nouvelles[question.champ] = question.generer()
                print(f"Généré : {question.libelle}")
            continue
        if interactif:
            valeur = _demander(question, actuelles.get(question.champ))
            if valeur is not None:
                nouvelles[question.champ] = valeur
        elif question.champ not in actuelles and question.choix:
            nouvelles[question.champ] = question.choix[0]
    service.ecrire(session, cle, nouvelles)
    print(f"\n{len(nouvelles)} réglage(s) enregistré(s), chiffrés.")


def verifier() -> int:
    """Les réglages (environnement + base) suffisent-ils pour démarrer l'API ?"""
    from coeur.config import Parametres

    try:
        Parametres()
    except ValidationError as erreur:
        manquants = ", ".join(str(e["loc"][0]) for e in erreur.errors())
        print(f"Réglages incomplets ou invalides : {manquants}")
        return 1
    print("Réglages complets : l'API et les tâches peuvent démarrer "
          "(docker compose up -d, ou docker compose restart api taches).")
    return 0


def main(arguments: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(prog="python -m coeur.reglages")
    commandes = analyseur.add_subparsers(dest="commande", required=True)
    init = commandes.add_parser("initialiser", help="Assistant de mise en service")
    init.add_argument("--non-interactif", action="store_true",
                      help="Seulement générer les secrets manquants (automatisation)")
    commandes.add_parser("lister", help="Réglages en base (secrets masqués)")
    afficher = commandes.add_parser("afficher", help="Un réglage en clair (à recopier ailleurs)")
    afficher.add_argument("champ")
    definir = commandes.add_parser("definir", help="Enregistrer un réglage")
    definir.add_argument("champ")
    definir.add_argument("valeur", nargs="?", help="Omis : saisie masquée")
    effacer = commandes.add_parser("effacer", help="Retirer un réglage de la base")
    effacer.add_argument("champ")
    importer = commandes.add_parser("importer-env", help="Copier en base les réglages d'un "
                                                         "ancien .env")
    importer.add_argument("fichier", nargs="?",
                          help="« - » : lignes CLE=valeur lues sur l'entrée standard "
                               "(.env.a-importer) ; absent : variables d'environnement")
    commandes.add_parser("changer-cle-maitre", help="Rechiffrer avec CLE_MAITRE_NOUVELLE")
    commandes.add_parser("verifier", help="Les réglages suffisent-ils à démarrer ?")
    args = analyseur.parse_args(arguments)

    cle = cle_maitre()
    if not cle:
        print("CLE_MAITRE manquante (voir outils/preparer_env.py).", file=sys.stderr)
        return 1
    with Session(create_engine(os.environ["DATABASE_URL"])) as session:
        if args.commande == "initialiser":
            initialiser(session, cle, interactif=not args.non_interactif)
            return verifier()
        if args.commande == "lister":
            for champ, valeur in sorted(service.lire(session, cle).items()):
                print(f"{champ:32} {service.masquer(champ, valeur)}")
            return 0
        if args.commande == "afficher":
            valeur = service.lire(session, cle).get(args.champ)
            if valeur is None:
                print(f"{args.champ} : absent de la base.", file=sys.stderr)
                return 1
            print(valeur)
            return 0
        if args.commande == "definir":
            valeur = args.valeur
            if valeur is None:
                valeur = getpass.getpass(f"{args.champ} : ").strip()
            try:
                service.ecrire(session, cle, {args.champ: valeur})
            except ValueError as erreur:
                print(erreur, file=sys.stderr)
                return 1
            print(f"{args.champ} enregistré. Prise en compte : docker compose restart api taches")
            return 0
        if args.commande == "effacer":
            print("Effacé." if service.effacer(session, args.champ) else "Absent.")
            return 0
        if args.commande == "importer-env":
            source = (dotenv_values(stream=sys.stdin) if args.fichier == "-"
                      else dotenv_values(args.fichier) if args.fichier else os.environ)
            valeurs = {c: source[c.upper()] for c in service.eligibles() if source.get(c.upper())}
            service.ecrire(session, cle, valeurs)
            print(f"{len(valeurs)} réglage(s) copié(s) en base : "
                  f"{', '.join(sorted(valeurs)) or 'aucun'}. Les retirer ensuite du .env.")
            return 0
        if args.commande == "changer-cle-maitre":
            nouvelle = os.environ.get("CLE_MAITRE_NOUVELLE")
            if not nouvelle:
                print("CLE_MAITRE_NOUVELLE manquante.", file=sys.stderr)
                return 1
            n = service.changer_cle_maitre(session, cle, nouvelle)
            print(f"{n} réglage(s) rechiffré(s). Remplacer CLE_MAITRE dans .env et le coffre-fort, "
                  "puis : docker compose up -d")
            return 0
        return verifier()


if __name__ == "__main__":
    sys.exit(main())
