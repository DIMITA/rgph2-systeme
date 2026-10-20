"""Vérification de bout en bout de la question dite au serveur vocal (touche 9).

Prérequis : ceux de verifier_telephonie.py (TELEPHONIE_SIMULATION=true, un contenu
publié placé dans le SVI). Le vrai service de transcription est remplacé, le temps du
test, par un faux branché sous le même nom sur le réseau de la pile : il vérifie que
l'enregistrement de l'appel est bien arrivé (un WAV d'au moins une seconde) et renvoie
la question du calendrier de passage. Les réglages de transcription sont rétablis à la fin.

Parcours vérifié : SVI → 9 → enregistrement → AGI → cœur → transcription → sujet proposé
→ « 1 » → réponse ; interaction « voix » journalisée, enregistrement effacé du tmpfs.

Usage : python outils/verifier_question_vocale.py   (depuis la racine du dépôt)
"""

import subprocess
import sys
import time
from datetime import datetime, timezone

from verifier_telephonie import ECHECS, appeler, asterisk, compose, sql, verifier

FAUX = "rgph-transcription-factice"
NUMERO = "0844000004"
QUESTION = "Quand les agents recenseurs passeront-ils chez moi ?"
SERVEUR = f'''
import http.server, json, sys
class G(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        corps = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        recu = corps[:4] == b"RIFF" and len(corps) > 16000
        print("recu", len(corps), "octets", flush=True)
        r = json.dumps({{"texte": {QUESTION!r} if recu else ""}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(r)
    def log_message(self, *a):
        pass
http.server.HTTPServer(("", 9000), G).serve_forever()
'''


def reglages(*args: str) -> str:
    return compose("run", "--rm", "-T", "migrations", "python", "-m", "coeur.reglages", *args)


def lire_reglage(nom: str) -> str | None:
    sortie = reglages("afficher", nom).strip().splitlines()[-1]
    return None if "absent de la base" in sortie else sortie


def ecrire_reglage(nom: str, valeur: str | None) -> None:
    reglages("definir", nom, valeur) if valeur is not None else reglages("effacer", nom)


def redemarrer_coeur() -> None:
    compose("restart", "api", "taches")
    time.sleep(8)


def main() -> None:
    debut = datetime.now(timezone.utc).isoformat()
    image, reseau = subprocess.run(
        ["docker", "inspect", compose("ps", "-q", "api").strip(), "--format",
         "{{.Config.Image}} {{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}"],
        capture_output=True, text=True).stdout.split()
    avant = {nom: lire_reglage(nom) for nom in ("transcription", "transcription_langues")}

    print("0. Préparation : faux service de transcription, français ouvert à la voix")
    subprocess.run(["docker", "rm", "-f", FAUX], capture_output=True)
    subprocess.run(["docker", "run", "-d", "--rm", "--name", FAUX, "--network", reseau,
                    "--network-alias", "transcription", "--entrypoint", "python", image,
                    "-c", SERVEUR], capture_output=True, check=True)
    try:
        ecrire_reglage("transcription", "service")
        ecrire_reglage("transcription_langues", "fr")
        redemarrer_coeur()
        compose("exec", "-T", "asterisk", "python3", "/opt/rgph/synchro/synchroniser_svi.py")
        verifier("question-vocale" in asterisk("dialplan show svi-fr"),
                 "le SVI français propose la question dite (touche 9)")
        if ECHECS:
            sys.exit(1)

        print("1. Appel D : question dite puis confirmée — environ 1 min 30")
        appeler(NUMERO, "test-robot-question")
        time.sleep(90)

        print("2. Contrôles")
        journal = subprocess.run(["docker", "logs", FAUX], capture_output=True,
                                 text=True).stdout
        verifier("recu" in journal, f"enregistrement reçu par la transcription ({journal.strip()})")
        ligne = sql("SELECT entree || ' ' || resultat || ' ' || coalesce(contenu_id::text, '') "
                    f"FROM coeur.interactions WHERE canal = 'centre_ecoute' AND entree = 'voix' "
                    f"AND horodatage > '{debut}'")
        attendu = sql("SELECT id FROM public.contenus WHERE cle = 'exemple-calendrier-passage'")
        verifier(ligne == f"voix reponse {attendu}",
                 f"question dite, confirmée, réponse journalisée ({ligne or 'rien'})")
        attente = sql("SELECT count(*) FROM coeur.appels WHERE question_texte IS NOT NULL "
                      "OR question_contenu_id IS NOT NULL")
        verifier(attente == "0", "aucune question en attente gardée après l'appel")
        restes = compose("exec", "-T", "asterisk", "ls", "-A", "/dev/shm/rgph-questions").strip()
        verifier(restes == "", f"enregistrement effacé du tmpfs ({restes or 'vide'})")
        verifier(NUMERO[1:] not in compose("logs", "--since", debut, "asterisk"),
                 "numéro absent des journaux d'Asterisk")
    finally:
        print("3. Remise en état des réglages")
        for nom, valeur in avant.items():
            ecrire_reglage(nom, valeur)
        subprocess.run(["docker", "rm", "-f", FAUX], capture_output=True)
        redemarrer_coeur()

    print(f"\n{'Vérification réussie.' if not ECHECS else f'{len(ECHECS)} échec(s).'}")
    sys.exit(1 if ECHECS else 0)


if __name__ == "__main__":
    main()
