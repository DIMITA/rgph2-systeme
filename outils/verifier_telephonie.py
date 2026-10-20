"""Vérification de bout en bout du centre d'appels, sans opérateur ni téléphone.

Prérequis : pile démarrée avec TELEPHONIE_SIMULATION=true (jamais en production)
et au moins un contenu publié placé dans le SVI (champ « ordre_svi » dans Directus).

Trois appels simulés (un « robot » tape les touches comme un citoyen) :
  A. écoute d'une réponse du SVI          → interaction « réponse » du canal centre_ecoute ;
  B. demande de conseiller sans agent     → proposition de rappel acceptée → rappel chiffré ;
  C. demande de conseiller, agent simulé  → décroché, conversation enregistrée.
Puis contrôle : aucun numéro en clair dans la base ni dans les journaux d'Asterisk.

Usage : python outils/verifier_telephonie.py   (depuis la racine du dépôt)
"""

import subprocess
import sys
import time
from datetime import datetime, timezone

ECHECS: list[str] = []
NUMEROS = {"A": "0811000001", "B": "0822000002", "C": "0833000003"}


def verifier(condition: bool, message: str) -> None:
    print(("  OK    " if condition else "  ÉCHEC ") + message, flush=True)
    if not condition:
        ECHECS.append(message)


def compose(*args: str) -> str:
    resultat = subprocess.run(["docker", "compose", *args], capture_output=True, text=True,
                              encoding="utf-8")
    return resultat.stdout + resultat.stderr


def asterisk(commande: str) -> str:
    return compose("exec", "-T", "asterisk", "asterisk", "-rx", commande)


def sql(requete: str) -> str:
    return compose("exec", "-T", "postgres", "psql", "-U", "rgph_admin", "-d", "rgph",
                   "-tAc", requete).strip()


def appeler(numero: str, robot: str) -> None:
    asterisk(f"channel originate Local/{numero}@test-entree extension s@{robot}")


def main() -> None:
    debut = datetime.now(timezone.utc).isoformat()

    print("0. Préparation")
    verifier("test-entree" in asterisk("dialplan show test-entree"),
             "appels simulés activés (TELEPHONIE_SIMULATION=true)")
    compose("exec", "-T", "asterisk", "python3", "/opt/rgph/synchro/synchroniser_svi.py")
    verifier("svi_ecoute" in asterisk("dialplan show svi-fr"),
             "le SVI français propose au moins une réponse")
    if ECHECS:
        sys.exit(1)

    print("1. Appels A (réponse du SVI) et B (rappel), en parallèle — environ 1 min 30")
    appeler(NUMEROS["A"], "test-robot-faq")
    appeler(NUMEROS["B"], "test-robot-conseiller")
    time.sleep(85)

    print("2. Appel C (agent simulé) — environ 1 min")
    asterisk("queue add member Local/s@test-agent/n to rgph")
    appeler(NUMEROS["C"], "test-robot-conseiller")
    time.sleep(60)
    asterisk("queue remove member Local/s@test-agent/n from rgph")

    print("3. Contrôles")
    depuis = f"'{debut}'"
    reponses = int(sql(f"SELECT count(*) FROM coeur.interactions WHERE canal = 'centre_ecoute' "
                       f"AND resultat = 'reponse' AND horodatage > {depuis}"))
    verifier(reponses >= 1, f"A : réponse du SVI comptée ({reponses})")
    appels = int(sql(f"SELECT count(*) FROM coeur.appels WHERE debut > {depuis} "
                     "AND fin_a IS NOT NULL AND usager_empreinte IS NOT NULL"))
    verifier(appels == 3, f"3 appels suivis de bout en bout, numéros en empreinte ({appels})")
    rappels = sql(f"SELECT numero_chiffre FROM coeur.rappels WHERE cree_a > {depuis}")
    verifier(len(rappels.splitlines()) == 1 and rappels.startswith("gAAAA"),
             "B : une demande de rappel, numéro chiffré")
    decroches = int(sql(f"SELECT count(*) FROM coeur.appels WHERE debut > {depuis} "
                        "AND decroche_a IS NOT NULL"))
    verifier(decroches == 1, f"C : appel décroché par l'agent ({decroches})")
    fichier = sql(f"SELECT fichier FROM coeur.enregistrements WHERE cree_a > {depuis}")
    taille = compose("exec", "-T", "asterisk", "stat", "-c", "%s",
                     f"/var/spool/asterisk/enregistrements/{fichier}").strip() if fichier else ""
    verifier(bool(fichier) and taille.isdigit() and int(taille) > 1000,
             f"C : conversation enregistrée ({fichier or 'aucun fichier'}, {taille} octets)")

    print("4. Données personnelles")
    tables = sql("SELECT string_agg(t::text, ' ') FROM (SELECT a FROM coeur.appels a UNION ALL "
                 "SELECT r FROM coeur.rappels r UNION ALL SELECT i FROM coeur.interactions i) t")
    journaux = compose("logs", "--since", debut, "asterisk")
    for nom, numero in NUMEROS.items():
        chiffres = numero[1:]
        verifier(chiffres not in tables, f"{nom} : numéro absent en clair de la base")
        verifier(chiffres not in journaux, f"{nom} : numéro absent des journaux d'Asterisk")

    print(f"\n{'Vérification réussie.' if not ECHECS else f'{len(ECHECS)} échec(s).'}")
    sys.exit(1 if ECHECS else 0)


if __name__ == "__main__":
    main()
