#!/usr/bin/env python3
"""AGI du SVI : envoie la question dite (touche 9) au cœur, puis l'efface.

    same => n,AGI(/opt/rgph/synchro/question_vocale.py,${FICHIER})

Lit les variables API, CLE_API, APPEL et LANGUE du canal ; écrit QV_ISSUE
(« proposition » ou « conseiller ») et QV_CONTENU (contenu à faire confirmer). Le
fichier est supprimé dans tous les cas : la voix ne reste pas sur le disque.

Un sujet n'est proposé que si sa question et sa réponse lues existent dans la langue
de l'appel (préparées par synchroniser_svi.py) ; sinon, passage à un conseiller.
"""

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from audio import dossier_rgph

DELAI_SECONDES = 30
# Seul dossier d'où un enregistrement peut être lu (puis effacé) : en mémoire (tmpfs).
DOSSIER = Path("/dev/shm/rgph-questions")


class Agi:
    """Protocole AGI minimal sur l'entrée et la sortie standard."""

    def __init__(self, entree=sys.stdin, sortie=sys.stdout):
        self.entree, self.sortie = entree, sortie
        self.env = {}
        for ligne in iter(self.entree.readline, ""):
            if not ligne.strip():
                break
            cle, _, valeur = ligne.partition(":")
            self.env[cle.strip()] = valeur.strip()

    def commande(self, texte: str) -> str:
        self.sortie.write(texte + "\n")
        self.sortie.flush()
        return self.entree.readline().strip()

    def lire(self, nom: str) -> str:
        """« 200 result=1 (valeur) » → valeur ; « 200 result=0 » (non définie) → ""."""
        reponse = self.commande(f"GET VARIABLE {nom}")
        debut, fin = reponse.find("("), reponse.rfind(")")
        return reponse[debut + 1:fin] if reponse.startswith("200 result=1") and debut > 0 else ""

    def ecrire(self, nom: str, valeur: str) -> None:
        self.commande(f'SET VARIABLE {nom} "{valeur}"')


def demander(api: str, cle: str, appel: str, langue: str, audio: bytes) -> dict:
    url = f"{api}/v1/appels/question-vocale?" + urllib.parse.urlencode(
        {"appel": appel, "langue": langue})
    requete = urllib.request.Request(url, data=audio, method="POST", headers={
        "X-Cle-API": cle, "Content-Type": "audio/wav"})
    with urllib.request.urlopen(requete, timeout=DELAI_SECONDES) as reponse:
        return json.load(reponse)


def audios_prets(langue: str, contenu_id: int) -> bool:
    dossier = dossier_rgph(langue) / "svi"
    return all((dossier / f"{n}-{contenu_id}.wav").is_file() for n in ("q", "r"))


def traiter(agi: Agi, fichier: Path) -> tuple[str, str]:
    langue = agi.lire("LANGUE")
    if fichier.resolve().parent != DOSSIER:
        return "conseiller", ""
    try:
        audio = fichier.read_bytes()
    except OSError:  # rien d'enregistré (raccroché, silence)
        return "conseiller", ""
    finally:
        fichier.unlink(missing_ok=True)
    try:
        resultat = demander(agi.lire("API"), agi.lire("CLE_API"), agi.lire("APPEL"), langue,
                            audio)
    except Exception as erreur:  # cœur injoignable ou réponse illisible
        agi.commande(f'VERBOSE "question vocale : {type(erreur).__name__}" 1')
        return "conseiller", ""
    contenu = resultat.get("contenu_id")
    if resultat.get("issue") == "proposition" and isinstance(contenu, int) \
            and audios_prets(langue, contenu):
        return "proposition", str(contenu)
    return "conseiller", ""


def main(agi: Agi | None = None) -> int:
    agi = agi or Agi()
    issue, contenu = traiter(agi, Path(sys.argv[1]))
    agi.ecrire("QV_ISSUE", issue)
    agi.ecrire("QV_CONTENU", contenu)
    return 0


if __name__ == "__main__":
    sys.exit(main())
