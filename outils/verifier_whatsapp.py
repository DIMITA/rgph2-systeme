"""Vérification de bout en bout du canal WhatsApp, sans compte Meta.

Prérequis : pile démarrée avec WHATSAPP_PASSERELLE=simulation et SIMULATEUR_MOBILE=true
(jamais en production), et la FAQ d'exemple chargée.

Envoie au webhook de l'API des notifications **signées comme celles de Meta**, puis lit
les réponses du bot (au format exact de l'API Graph) :
  1. notification non signée refusée ; abonnement du webhook vérifié ;
  2. premier contact (choix de la langue), menu, question de la FAQ, question libre ;
  3. vérification d'un badge, demande de rappel ;
  4. abonnement aux rappels de passage, envoi du rappel (modèle), STOP ;
  5. aucun numéro en clair dans la base ni dans les journaux.

Usage : python outils/verifier_whatsapp.py   (depuis la racine du dépôt)
"""

import hashlib
import hmac
import json
import random
import subprocess
import sys
import uuid

import httpx

API = "http://localhost:8000"
ECHECS: list[str] = []


def verifier(condition: bool, message: str) -> None:
    print(("  OK    " if condition else "  ÉCHEC ") + message, flush=True)
    if not condition:
        ECHECS.append(message)


def compose(*args: str) -> str:
    r = subprocess.run(["docker", "compose", *args], capture_output=True, text=True, encoding="utf-8")
    return r.stdout + r.stderr


def sql(requete: str) -> str:
    return compose("exec", "-T", "postgres", "psql", "-U", "rgph_admin", "-d", "rgph",
                   "-tAc", requete).strip()


def env_api(nom: str) -> str:
    """Réglage effectif de l'API (environnement ou réglages chiffrés en base)."""
    return compose("exec", "-T", "api", "python", "-c",
                   f"from coeur.config import parametres; print(parametres().{nom.lower()})").strip()


class Citoyen:
    def __init__(self, numero: str, secret: str):
        self.numero, self.secret = numero, secret

    def _poster(self, message: dict) -> list[dict]:
        avant = len(self.recus())
        corps = json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{
            "field": "messages", "value": {"messages": [{
                "from": self.numero, "id": "wamid.verif." + uuid.uuid4().hex,
                "timestamp": "1760000000", **message}]}}]}]}).encode()
        signature = "sha256=" + hmac.new(self.secret.encode(), corps, hashlib.sha256).hexdigest()
        r = httpx.post(f"{API}/v1/whatsapp/webhook", content=corps,
                       headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"})
        r.raise_for_status()
        return self.recus()[avant:]

    def recus(self) -> list[dict]:
        r = httpx.get(f"{API}/simulateur/whatsapp/messages", params={"numero": self.numero})
        r.raise_for_status()
        return r.json()

    def ecrire(self, texte: str) -> list[dict]:
        return self._poster({"type": "text", "text": {"body": texte}})

    def toucher(self, identifiant: str) -> list[dict]:
        return self._poster({"type": "interactive", "interactive": {
            "type": "button_reply", "button_reply": {"id": identifiant, "title": "x"}}})


def corps(message: dict) -> str:
    if message["type"] == "text":
        return message["text"]["body"]
    if message["type"] == "interactive":
        return message["interactive"]["body"]["text"]
    return ""


def main() -> None:
    suffixe = f"{random.randint(0, 999999):06d}"
    numero = "243863" + suffixe
    secret = env_api("WHATSAPP_SECRET_APP")

    print("0. Préparation")
    verifier(env_api("WHATSAPP_PASSERELLE") in ("", "simulation"), "passerelle WhatsApp en simulation")
    verifier(httpx.get(f"{API}/simulateur").status_code == 200, "simulateur actif (SIMULATEUR_MOBILE=true)")
    verifier(bool(secret), "secret de l'application configuré (WHATSAPP_SECRET_APP)")
    compose("run", "--rm", "migrations", "python", "-m", "coeur.connaissances", "charger-exemples")
    compose("run", "--rm", "migrations", "python", "-m", "coeur.badges", "importer",
            "donnees/badges-exemple.csv")
    if ECHECS:
        sys.exit(1)

    print("1. Webhook")
    r = httpx.post(f"{API}/v1/whatsapp/webhook", content=b'{"entry":[]}')
    verifier(r.status_code == 401, "notification non signée refusée")
    jeton = env_api("WHATSAPP_JETON_VERIFICATION")
    r = httpx.get(f"{API}/v1/whatsapp/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": jeton, "hub.challenge": "42"})
    verifier(r.text == "42", "abonnement du webhook vérifié (défi renvoyé)")

    print("2. Conversation")
    c = Citoyen(numero, secret)
    reponses = c.ecrire("Bonjour")
    verifier(len(reponses) == 1 and reponses[0]["interactive"]["type"] == "list"
             and "Bienvenue" in corps(reponses[0]), "premier contact : accueil et liste des langues")
    menu = c.toucher("langue:fr")
    lignes = [l["id"] for l in menu[0]["interactive"]["action"]["sections"][0]["rows"]]
    verifier(lignes == ["faq", "passage", "badge", "nonvisite", "conseiller", "langues"],
             "menu principal en liste")
    liste = c.toucher("faq")[0]["interactive"]["action"]["sections"][0]["rows"]
    reponse = c.toucher(liste[0]["id"])
    verifier("Réponse officielle du Bureau central du recensement" in corps(reponse[0]),
             "question de la FAQ : réponse officielle complète")
    reponse = c.ecrire("Comment reconnaitre un vrai agent recenseur ?")
    verifier("badge officiel" in corps(reponse[0]), "question libre : réponse validée")

    print("3. Services")
    c.toucher("badge")
    reponse = c.ecrire("EX0002")
    verifier(corps(reponse[0]).startswith("Badge EX0002 VALIDE"), "badge vérifié")
    c.toucher("conseiller")
    reponse = c.toucher("rappel")
    verifier(corps(reponse[0]).startswith(("Demande enregistrée", "Votre demande de rappel")),
             "demande de rappel enregistrée")
    verifier(sql("SELECT count(*) FROM coeur.rappels WHERE origine = 'whatsapp' "
                 "AND numero_chiffre IS NOT NULL") != "0", "rappel visible pour les agents (origine WhatsApp)")

    print("4. Rappels de passage")
    sql("INSERT INTO calendrier_passages (territoire_code, date_debut, date_fin, statut) "
        "SELECT 'TAN-KAL', current_date + 3, current_date + 20, 'publie' WHERE NOT EXISTS "
        "(SELECT 1 FROM calendrier_passages WHERE territoire_code = 'TAN-KAL')")
    debut = sql("SELECT to_char(date_debut, 'DD/MM/YYYY') FROM calendrier_passages "
                "WHERE territoire_code = 'TAN-KAL' ORDER BY id LIMIT 1")
    reponse = c.toucher("terr:passage:TAN-KAL")
    verifier(any(b["reply"]["id"] == "abonner:TAN-KAL" for b in
                 reponse[0]["interactive"]["action"]["buttons"]), "« Prévenez-moi » proposé")
    reponse = c.toucher("abonner:TAN-KAL")
    verifier(corps(reponse[0]).startswith("C'est noté"), "abonnement enregistré")
    verifier(sql("SELECT count(*) FROM coeur.abonnements_whatsapp WHERE territoire_code = 'TAN-KAL' "
                 "AND numero_chiffre IS NOT NULL") != "0", "numéro conservé chiffré")
    avant = len(c.recus())
    httpx.post(f"{API}/simulateur/whatsapp/rappels").raise_for_status()
    modeles = [m for m in c.recus()[avant:] if m["type"] == "template"]
    verifier(len(modeles) == 1 and modeles[0]["template"]["name"] == "rappel_passage"
             and [p["text"] for p in modeles[0]["template"]["components"][0]["parameters"]][:2]
             == ["Kalemie", debut], f"rappel envoyé par modèle (Kalemie, {debut})")
    reponse = c.ecrire("STOP")
    verifier(corps(reponse[0]).startswith("Vos rappels sont arrêtés"), "STOP : rappels arrêtés")
    verifier(sql("SELECT count(*) FROM coeur.abonnements_whatsapp WHERE territoire_code = 'TAN-KAL'")
             == "0", "STOP : abonnement et numéro effacés")
    sortie = compose("exec", "-T", "taches", "python", "-m", "coeur.taches")
    verifier("rappels de passage envoyés" in sortie, "le service « taches » exécute les rappels")

    print("5. Aucun numéro en clair")
    for table in ("whatsapp_messages", "conversations_whatsapp", "abonnements_whatsapp",
                  "interactions", "consultations", "preferences_langue", "rappels"):
        contenu = sql(f"SELECT coalesce(string_agg(t::text, ' '), '') FROM coeur.{table} t")
        verifier(suffixe not in contenu, f"table coeur.{table}")
    verifier(suffixe not in compose("logs", "api"), "journaux de l'API")

    print(f"\n{'Vérification réussie.' if not ECHECS else f'{len(ECHECS)} échec(s).'}")
    sys.exit(1 if ECHECS else 0)


if __name__ == "__main__":
    main()
