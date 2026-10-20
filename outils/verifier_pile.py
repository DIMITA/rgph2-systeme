"""Vérification de bout en bout d'une pile démarrée (docker compose up).

Déroule le circuit réel de validation et vérifie que l'API le respecte :
  1. un Rédacteur crée un contenu en brouillon       → l'API escalade ;
  2. le Rédacteur tente de le publier                 → Directus refuse ;
  3. un Validateur BCR le publie                      → l'API le sert ;
  4. le Rédacteur tente de modifier le contenu publié → Directus refuse.
Les utilisateurs et le contenu de test sont supprimés à la fin.

Variables : DIRECTUS_URL, API_URL, DIRECTUS_ADMIN_EMAIL, DIRECTUS_ADMIN_MDP, CLES_API
Usage :    python outils/verifier_pile.py
"""

import os
import secrets
import sys
import time

import httpx

DIRECTUS = os.environ.get("DIRECTUS_URL", "http://localhost:8055")
API = os.environ.get("API_URL", "http://localhost:8000")
# Question sans rapport avec la FAQ, rendue unique par un mot aléatoire (voir main).
QUESTION_MODELE = "Procédure technique de contrôle {}"
ECHECS: list[str] = []


def verifier(condition: bool, message: str) -> None:
    print(("  OK    " if condition else "  ÉCHEC ") + message)
    if not condition:
        ECHECS.append(message)


def connexion(email: str, mdp: str) -> httpx.Client:
    r = httpx.post(f"{DIRECTUS}/auth/login", json={"email": email, "password": mdp})
    r.raise_for_status()
    jeton = r.json()["data"]["access_token"]
    return httpx.Client(base_url=DIRECTUS, headers={"Authorization": f"Bearer {jeton}"}, timeout=30)


def cle_api_web() -> str:
    for paire in os.environ["CLES_API"].split(","):
        canal, _, cle = paire.strip().partition(":")
        if canal == "web":
            return cle
    sys.exit("CLES_API ne contient pas de clé pour le canal web.")


def demander(cle: str, question: str) -> dict:
    r = httpx.post(f"{API}/v1/questions", json={"texte": question}, headers={"X-Cle-API": cle})
    r.raise_for_status()
    return r.json()


def main() -> None:
    admin = connexion(os.environ["DIRECTUS_ADMIN_EMAIL"], os.environ["DIRECTUS_ADMIN_MDP"])
    roles = {r["name"]: r["id"] for r in admin.get("/roles").json()["data"]}
    suffixe = secrets.token_hex(4)
    question = QUESTION_MODELE.format("zq" + suffixe)
    mdp = secrets.token_urlsafe(16)
    utilisateurs = {}
    for nom in ("Rédacteur", "Validateur BCR"):
        email = f"verif-{suffixe}-{len(utilisateurs)}@exemple.cd"
        r = admin.post("/users", json={"email": email, "password": mdp, "role": roles[nom]})
        r.raise_for_status()
        utilisateurs[nom] = (r.json()["data"]["id"], connexion(email, mdp))
    redacteur, validateur = utilisateurs["Rédacteur"][1], utilisateurs["Validateur BCR"][1]
    cle = cle_api_web()
    contenu_id = None
    try:
        print("1. Rédaction d'un brouillon")
        r = redacteur.post("/items/contenus", json={"cle": f"verif-{suffixe}", "statut": "brouillon"})
        verifier(r.status_code == 200, "le Rédacteur crée un contenu en brouillon")
        contenu_id = r.json()["data"]["id"]
        r = redacteur.post("/items/contenus_traductions", json={
            "contenu_id": contenu_id, "langue_code": "fr", "question": question,
            "reponse": "Réponse de vérification technique.", "statut": "brouillon",
        })
        verifier(r.status_code == 200, "le Rédacteur ajoute la traduction française")
        traduction_id = r.json()["data"]["id"]
        verifier(demander(cle, question)["type"] == "escalade", "l'API ne sert pas le brouillon")

        print("2. Tentative de publication par le Rédacteur")
        r = redacteur.patch(f"/items/contenus/{contenu_id}", json={"statut": "publie"})
        verifier(r.status_code in (400, 403), f"Directus refuse la publication (HTTP {r.status_code})")

        print("3. Publication par le Validateur BCR")
        r1 = validateur.patch(f"/items/contenus/{contenu_id}", json={"statut": "publie"})
        r2 = validateur.patch(f"/items/contenus_traductions/{traduction_id}", json={"statut": "publie"})
        verifier(r1.status_code == r2.status_code == 200, "le Validateur BCR publie")
        servi = False
        for _ in range(40):  # l'API garde les contenus en cache jusqu'à 60 s
            reponse = demander(cle, question)
            if reponse["type"] == "reponse":
                servi = reponse["contenu"]["contenu_id"] == contenu_id
                break
            time.sleep(2)
        verifier(servi, "l'API sert le contenu publié")

        print("4. Modification d'un contenu publié par le Rédacteur")
        r = redacteur.patch(f"/items/contenus_traductions/{traduction_id}",
                            json={"reponse": "Texte modifié sans validation"})
        verifier(r.status_code in (400, 403), f"Directus refuse la modification (HTTP {r.status_code})")
    finally:
        if contenu_id:
            admin.delete(f"/items/contenus/{contenu_id}")
        for uid, _ in utilisateurs.values():
            admin.delete(f"/users/{uid}")

    print(f"\n{'Vérification réussie.' if not ECHECS else f'{len(ECHECS)} échec(s).'}")
    sys.exit(1 if ECHECS else 0)


if __name__ == "__main__":
    main()
