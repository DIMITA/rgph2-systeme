"""Tests de charge du cœur : un profil d'usager par canal, au mélange attendu au pic.

Chaque usager simulé suit le parcours réel de son canal, avec un numéro différent (les
limiteurs et les sessions sont par numéro), et les vraies clés d'API de la pile :

    CLES_API                 « ussd:…,sms:…,web:… » (comme dans .env)
    CLE_API_CENTRE_ECOUTE    clé du serveur téléphonique
    WHATSAPP_SECRET_APP      secret de l'application Meta (signature des notifications)

    locust -f charge/locustfile.py --host http://localhost:8000 --headless \\
        -u 200 -r 10 -t 5m --csv rapport

Les poids (`weight`) donnent le mélange : USSD et SMS d'abord (téléphones basiques),
puis WhatsApp, le web, le badge des agents et le serveur vocal. À ajuster quand le
pilote donnera les vraies proportions (tableau de bord, par canal).

À lancer contre une pile d'essai, jamais en production : les échanges sont journalisés
comme de vraies interactions, et les SMS ou messages WhatsApp partent vers la passerelle
configurée (simulateur dans la pile d'essai).
"""

import hashlib
import hmac
import itertools
import json
import os
import random
import uuid

from locust import HttpUser, between, task

CLES = dict(p.split(":", 1) for p in os.environ.get("CLES_API", "").split(",") if ":" in p)
CLE_CENTRE = os.environ.get("CLE_API_CENTRE_ECOUTE", "")
SECRET_WHATSAPP = os.environ.get("WHATSAPP_SECRET_APP", "")

# Questions courantes, telles qu'un citoyen les écrit (sans accents, abrégées…).
QUESTIONS = [
    "quand les agents passent chez moi",
    "comment reconnaitre un vrai agent recenseur",
    "mes informations restent confidentielles ?",
    "personne n'est venu chez nous",
    "pourquoi faire le recensement",
    "est ce que je dois payer l'agent",
    "on a oublie mon menage",
    "je veux parler a un conseiller",
]
# Numéros de 0810000000 à 0899999999, un par usager simulé.
_NUMEROS = itertools.count(random.randrange(10_000_000, 80_000_000))


def nouveau_numero() -> str:
    return f"08{next(_NUMEROS) % 100_000_000:08d}"


class CitoyenUSSD(HttpUser):
    """Session USSD : la passerelle renvoie la saisie cumulée à chaque écran. L'opérateur
    coupe la session si la réponse tarde (souvent 2 à 3 s) : c'est la latence à tenir."""

    weight = 35
    wait_time = between(2, 6)

    def on_start(self):
        self.numero = nouveau_numero()

    @task
    def session(self):
        session_id = uuid.uuid4().hex
        saisies = ["", "1", "1*1", f"1*1*{random.randint(1, 4)}"]
        for texte in saisies:
            with self.client.post(f"/v1/ussd?cle={CLES.get('ussd', '')}", name="USSD écran",
                                  data={"sessionId": session_id, "phoneNumber": self.numero,
                                        "text": texte, "serviceCode": "*123#"},
                                  catch_response=True) as r:
                if r.status_code != 200 or not r.text.startswith(("CON ", "END ")):
                    r.failure(f"réponse USSD inattendue : {r.status_code}")
                    return
                if r.text.startswith("END "):
                    return


class CitoyenSMS(HttpUser):
    """SMS entrant transmis par Kannel ; la réponse repart par la passerelle SMS."""

    weight = 25
    wait_time = between(5, 15)

    def on_start(self):
        self.numero = nouveau_numero()

    @task
    def question(self):
        self.client.get("/v1/sms/entrant", name="SMS entrant", params={
            "cle": CLES.get("sms", ""), "de": self.numero, "texte": random.choice(QUESTIONS)})


class CitoyenWhatsApp(HttpUser):
    """Notification signée de Meta : un message texte, comme un citoyen qui écrit."""

    weight = 15
    wait_time = between(3, 10)

    def on_start(self):
        self.numero = "243" + nouveau_numero()[1:]

    def _notifier(self, message: dict) -> None:
        corps = json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{
            "field": "messages", "value": {"messages": [{
                "from": self.numero, "id": "wamid.charge." + uuid.uuid4().hex,
                "timestamp": "1760000000", **message}]}}]}]}).encode()
        signature = "sha256=" + hmac.new(SECRET_WHATSAPP.encode(), corps,
                                         hashlib.sha256).hexdigest()
        self.client.post("/v1/whatsapp/webhook", name="WhatsApp notification", data=corps,
                         headers={"X-Hub-Signature-256": signature,
                                  "Content-Type": "application/json"})

    @task
    def ecrire(self):
        self._notifier({"type": "text", "text": {"body": random.choice(QUESTIONS)}})


class CitoyenWeb(HttpUser):
    """Portail et chatbot : la FAQ, puis une question."""

    weight = 10
    wait_time = between(3, 10)

    @task(3)
    def question(self):
        self.client.post("/v1/questions", name="Web question",
                         headers={"X-Cle-API": CLES.get("web", "")},
                         json={"texte": random.choice(QUESTIONS), "langue": "fr"})

    @task(1)
    def faq(self):
        self.client.get("/v1/faq", name="Web FAQ", params={"langue": "fr"},
                        headers={"X-Cle-API": CLES.get("web", "")})


class VerificationBadge(HttpUser):
    """Un ménage vérifie le badge de l'agent à sa porte (pic pendant le dénombrement)."""

    weight = 10
    wait_time = between(2, 8)

    @task
    def verifier(self):
        with self.client.post("/v1/badges/verification", name="Badge vérification",
                              headers={"X-Cle-API": CLES.get("web", "")},
                              json={"numero": f"RGPH-{random.randint(1, 99999):05d}",
                                    "telephone": nouveau_numero()},
                              catch_response=True) as r:
            # Badge inconnu ou trop d'essais : réponses normales, pas des pannes.
            if r.status_code in (200, 404, 429):
                r.success()


class AppelSVI(HttpUser):
    """Appel au numéro vert vu du cœur : les événements qu'Asterisk envoie."""

    weight = 5
    wait_time = between(5, 15)

    def _evenement(self, nom: str, **champs) -> None:
        self.client.post("/v1/appels/evenements", name=f"SVI {nom}",
                         headers={"X-Cle-API": CLE_CENTRE}, data=champs)

    @task
    def appel(self):
        appel = f"charge-{uuid.uuid4().hex[:16]}"
        self._evenement("début", type="debut", appel=appel, numero=nouveau_numero())
        self._evenement("langue", type="langue", appel=appel, langue="fr")
        self._evenement("réponse écoutée", type="svi_ecoute", appel=appel,
                        contenu_id=random.randint(1, 5))
        self._evenement("fin", type="fin", appel=appel)
