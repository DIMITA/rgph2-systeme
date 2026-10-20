"""Prépare le fichier .env à partir de .env.exemple, sans rien recopier à la main.

    python outils/preparer_env.py                  # questions dans le terminal
    python outils/preparer_env.py --non-interactif # valeurs par défaut (essais, CI)

Dans .env.exemple :
- « @genere » : secret tiré au hasard (« @genere:fernet » : clé Fernet ;
  « @genere:cles_api » : une clé par canal) ;
- « @demander » : valeur à saisir, vide si on ne l'a pas encore (« @demander=défaut »).

Une valeur déjà présente dans .env est toujours gardée : on peut relancer le script
sans risque (pour remplir une valeur obtenue entre-temps, la vider dans .env avant).
Les réglages d'un ancien .env qui se gardent désormais en base (pepper, WhatsApp…)
sont mis de côté dans .env.a-importer, à importer avec :

    docker compose run --rm -T migrations python -m coeur.reglages importer-env - < .env.a-importer

Ne dépend que de Python : se lance sur le serveur avant tout conteneur.
"""

import argparse
import base64
import getpass
import os
import re
import secrets
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
CANAUX = ("ussd", "sms", "whatsapp", "web", "kiosque", "ambassadeur")
LIGNE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def generer(type_: str) -> str:
    if type_ == "fernet":
        return base64.urlsafe_b64encode(os.urandom(32)).decode()
    if type_ == "cles_api":
        return ",".join(f"{canal}:{secrets.token_urlsafe(24)}" for canal in CANAUX)
    return secrets.token_urlsafe(32)


def lire_env(chemin: Path) -> dict[str, str]:
    if not chemin.is_file():
        return {}
    valeurs = {}
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        trouve = LIGNE.match(ligne.strip())
        if trouve:
            valeurs[trouve[1]] = trouve[2]
    return valeurs


def demander(cle: str, aide: list[str], defaut: str, interactif: bool) -> str:
    if not interactif:
        return defaut
    print()
    for ligne in aide:
        print(f"  {ligne}")
    invite = f"{cle}" + (f" [{defaut}]" if defaut else " (Entrée : laisser vide)") + " : "
    lire = getpass.getpass if re.search(r"MDP|SECRET|JETON", cle) else input
    return lire(invite).strip() or defaut


def preparer(modele: Path, cible: Path, a_importer: Path, interactif: bool) -> list[str]:
    """Écrit `cible` ; renvoie les clés de l'ancien .env mises de côté."""
    anciennes = lire_env(cible)
    sortie, aide, connues = [], [], set()
    for ligne in modele.read_text(encoding="utf-8").splitlines():
        trouve = LIGNE.match(ligne)
        if not trouve:
            sortie.append(ligne)
            aide = aide + [ligne.lstrip("# ")] if ligne.startswith("#") else []
            continue
        cle, valeur = trouve[1], trouve[2]
        connues.add(cle)
        if anciennes.get(cle) and not anciennes[cle].startswith("@"):
            valeur = anciennes[cle]
        elif valeur.startswith("@genere"):
            valeur = generer(valeur.partition(":")[2])
        elif valeur.startswith("@demander"):
            valeur = demander(cle, aide, valeur.partition("=")[2], interactif)
        sortie.append(f"{cle}={valeur}")
        aide = []
    cible.write_text("\n".join(sortie) + "\n", encoding="utf-8")
    cible.chmod(0o600)
    restes = {c: v for c, v in anciennes.items() if c not in connues and v}
    if restes:
        a_importer.write_text("".join(f"{c}={v}\n" for c, v in restes.items()), encoding="utf-8")
        a_importer.chmod(0o600)
    return sorted(restes)


def main() -> int:
    analyseur = argparse.ArgumentParser(prog="python outils/preparer_env.py")
    analyseur.add_argument("--non-interactif", action="store_true",
                           help="Ne rien demander : valeurs par défaut (essais, CI)")
    args = analyseur.parse_args()
    restes = preparer(RACINE / ".env.exemple", RACINE / ".env", RACINE / ".env.a-importer",
                      interactif=not args.non_interactif)
    print("\n.env prêt (lisible par son seul propriétaire).")
    print("Ranger CLE_MAITRE dans un coffre-fort, à part des sauvegardes de la base.")
    if restes:
        print(f"Réglages de l'ancien .env mis de côté dans .env.a-importer : {', '.join(restes)}.")
    print("\nÉtapes suivantes :\n"
          "  docker compose up -d postgres migrations\n"
          "  docker compose run --rm migrations python -m coeur.reglages initialiser\n"
          "  docker compose up -d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
