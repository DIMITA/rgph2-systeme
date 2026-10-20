"""Vérification de bout en bout de l'USSD et des SMS, sans opérateur.

Prérequis : pile démarrée avec SMS_SIMULATION=true (jamais en production).
Prépare les données d'exemple (FAQ, calendrier, badges fictifs EX0001…), puis :
  1. USSD : une session complète envoyée à l'API comme le ferait l'agrégateur
     (choix de la langue, date de passage, vérification d'un badge) ;
  2. SMS : des messages envoyés par l'opérateur simulé de Kannel (fakesmsc), qui
     traversent Kannel, le cœur, puis reviennent par Kannel jusqu'au téléphone ;
  3. contrôle : aucun numéro en clair dans la base ni dans les journaux.

Usage : python outils/verifier_mobile.py   (depuis la racine du dépôt)
"""

import random
import re
import subprocess
import sys
import uuid
from urllib.parse import unquote_plus

import httpx

API = "http://localhost:8000"
ECHECS: list[str] = []


def verifier(condition: bool, message: str) -> None:
    print(("  OK    " if condition else "  ÉCHEC ") + message, flush=True)
    if not condition:
        ECHECS.append(message)


def compose(*args: str) -> str:
    resultat = subprocess.run(["docker", "compose", *args], capture_output=True, text=True,
                              encoding="utf-8")
    return resultat.stdout + resultat.stderr


def sql(requete: str) -> str:
    return compose("exec", "-T", "postgres", "psql", "-U", "rgph_admin", "-d", "rgph",
                   "-tAc", requete).strip()


def cle_du_canal(canal: str) -> str:
    cles = compose("exec", "-T", "api", "printenv", "CLES_API").strip()
    return dict(p.strip().split(":", 1) for p in cles.split(",") if ":" in p)[canal]


class SessionUssd:
    def __init__(self, cle: str, numero: str):
        self.cle, self.numero = cle, numero
        self.id, self.saisies = "verif-" + uuid.uuid4().hex[:8], []

    def envoyer(self, saisie: str | None = None) -> str:
        if saisie is not None:
            self.saisies.append(saisie)
        r = httpx.post(f"{API}/v1/ussd", headers={"X-Cle-API": self.cle}, data={
            "sessionId": self.id, "phoneNumber": self.numero, "serviceCode": "*000#",
            "text": "*".join(self.saisies)})
        r.raise_for_status()
        return r.text

    def choisir(self, ecran: str, libelle: str) -> str:
        while True:
            trouve = re.search(rf"^(\d+) {re.escape(libelle)}", ecran, re.MULTILINE)
            if trouve:
                return self.envoyer(trouve.group(1))
            if "\n98 " not in ecran:
                raise AssertionError(f"« {libelle} » absent de :\n{ecran}")
            ecran = self.envoyer("98")


def sms(numero: str, texte: str, attendu: str) -> str:
    """Envoie un SMS par l'opérateur simulé ; renvoie la réponse reçue contenant `attendu`."""
    sortie = compose("exec", "-T", "sms", "timeout", "15", "fakesmsc", "-H", "127.0.0.1",
                     "-r", "13010", "-i", "1", "-m", "1", f"{numero} 1234 text {texte}")
    recus, parties = [], []
    for ligne in sortie.splitlines():
        if simple := re.search(r"Got message \d+: <\S+ \+?\d+ text (.*)>", ligne):
            recus.append(simple.group(1))
        # SMS long : plusieurs parties (en-tête UDH), texte encodé, à recoller.
        elif partie := re.search(r"Got message \d+: <\S+ \+?\d+ udh %05%00%03%\w\w%(\w\w)%(\w\w) "
                                 r"data (\S*)>", ligne):
            parties.append(unquote_plus(partie.group(3)))
            if partie.group(1) == partie.group(2):  # dernière partie
                recus.append("".join(parties))
                parties = []
    return next((r for r in recus if attendu in r), " | ".join(recus) or "(aucune réponse)")


def main() -> None:
    suffixe = f"{random.randint(0, 999999):06d}"
    numero_ussd, numero_sms = "0861" + suffixe, "243862" + suffixe

    print("0. Préparation")
    compose("run", "--rm", "migrations", "python", "-m", "coeur.connaissances", "charger-exemples")
    sortie = compose("run", "--rm", "migrations", "python", "-m", "coeur.badges", "importer",
                     "donnees/badges-exemple.csv")
    verifier("3 badges actifs et 1 badges retirés" in sortie, "badges fictifs importés")
    verifier("Passerelle SMS en SIMULATION" in compose("logs", "sms"),
             "Kannel en simulation (SMS_SIMULATION=true)")
    if ECHECS:
        sys.exit(1)

    print("1. USSD")
    cle = cle_du_canal("ussd")
    session = SessionUssd(cle, numero_ussd)
    ecran = session.envoyer()
    verifier(ecran.startswith("CON RGPH-2 Recensement. Choisissez votre langue"),
             "premier contact : choix de la langue")
    ecran = session.choisir(ecran, "Francais")
    ecran = session.choisir(ecran, "Date de passage des agents")
    ecran = session.choisir(ecran, "Kinshasa")
    ecran = session.choisir(ecran, "Ville de Kinshasa")
    verifier(ecran == "END Passage des agents à Ville de Kinshasa : du 10/05/2027 au 20/06/2027.",
             f"date de passage ({ecran})")
    session = SessionUssd(cle, numero_ussd)
    ecran = session.envoyer()
    verifier(ecran.startswith("CON RGPH-2 Recensement\n1 Questions"),
             "nouvelle session : la langue n'est plus demandée")
    session.choisir(ecran, "Vérifier un agent")
    ecran = session.envoyer("EX0001")
    verifier(ecran.startswith("END Badge EX0001 VALIDE"), f"badge vérifié ({ecran[:40]}…)")

    print("2. SMS par Kannel (opérateur simulé)")
    reponse = sms(numero_sms, "AGENT EX0099", "RETIRÉ")
    verifier("Badge EX0099 RETIRÉ" in reponse, f"badge retiré ({reponse[:50]}…)")
    reponse = sms(numero_sms, "Comment reconnaitre un vrai agent recenseur ?", "badge officiel")
    verifier("badge officiel" in reponse, "question libre : réponse validée de la FAQ")
    reponse = sms(numero_sms, "NONVISITE Goma verification", "Signalement")
    verifier(reponse.startswith("Merci. Signalement"), "ménage non recensé signalé")
    verifier(sql("SELECT canal || '|' || territoire_code FROM coeur.signalements "
                 "WHERE localite = 'verification' ORDER BY id DESC LIMIT 1") == "sms|NKV-GOM",
             "signalement enregistré (canal sms, Goma)")
    verifier(int(sql("SELECT count(*) FROM coeur.sms WHERE horodatage > now() - interval '5 min' "
                     "AND sens = 'sortant' AND statut = 'envoye'")) >= 3,
             "réponses comptées dans le journal des SMS")

    print("3. Aucun numéro en clair")
    for table in ("interactions", "signalements", "consultations", "sms", "preferences_langue",
                  "rappels"):
        contenu = sql(f"SELECT coalesce(string_agg(t::text, ' '), '') FROM coeur.{table} t")
        verifier(suffixe not in contenu, f"table coeur.{table}")
    for service in ("api", "sms"):
        verifier(suffixe not in compose("logs", service), f"journaux du service {service}")

    print(f"\n{'Vérification réussie.' if not ECHECS else f'{len(ECHECS)} échec(s).'}")
    sys.exit(1 if ECHECS else 0)


if __name__ == "__main__":
    main()
