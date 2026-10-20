"""Vérification de la console des agents dans un vrai navigateur (Edge ou Chrome).

Prérequis :
  - pile démarrée avec TELEPHONIE_SIMULATION=true et SIP_ADRESSE_EXTERNE=127.0.0.1 ;
  - pip install playwright   (aucun navigateur à télécharger : Edge installé suffit).

Déroulé, avec un micro factice (son de test) :
  1. un agent se connecte, prend le poste 1 : le téléphone du navigateur s'enregistre ;
  2. un citoyen simulé demande un conseiller : l'agent décroche, la conversation est
     enregistrée (audio WebRTC réel), l'agent raccroche et qualifie l'appel ;
  3. l'agent se met en pause : un nouvel appel n'est pas présenté, le citoyen demande
     un rappel ; l'agent prend le rappel (numéro affiché) puis le clôture (numéro effacé) ;
  4. un superviseur qualité écoute l'enregistrement : l'écoute est journalisée.

Usage : python outils/verifier_console_agent.py   (variables du .env chargées)
"""

import os
import secrets
import subprocess
import sys
import time

import httpx
from playwright.sync_api import expect, sync_playwright

API = os.environ.get("API_URL", "http://localhost:8000")
DIRECTUS = os.environ.get("DIRECTUS_URL", "http://localhost:8055")
ECHECS: list[str] = []


def verifier(condition: bool, message: str) -> None:
    print(("  OK    " if condition else "  ÉCHEC ") + message, flush=True)
    if not condition:
        ECHECS.append(message)


def compose(*args: str) -> str:
    r = subprocess.run(["docker", "compose", *args], capture_output=True, text=True,
                       encoding="utf-8")
    return r.stdout + r.stderr


def sql(requete: str) -> str:
    return compose("exec", "-T", "postgres", "psql", "-U", "rgph_admin", "-d", "rgph",
                   "-tAc", requete).strip()


def appel_citoyen(numero: str) -> None:
    compose("exec", "-T", "asterisk", "asterisk", "-rx",
            f"channel originate Local/{numero}@test-entree extension s@test-robot-conseiller")


def admin() -> httpx.Client:
    r = httpx.post(f"{DIRECTUS}/auth/login", json={
        "email": os.environ["DIRECTUS_ADMIN_EMAIL"], "password": os.environ["DIRECTUS_ADMIN_MDP"]})
    r.raise_for_status()
    return httpx.Client(base_url=DIRECTUS, timeout=30,
                        headers={"Authorization": f"Bearer {r.json()['data']['access_token']}"})


def connecter(page, email: str, mdp: str) -> None:
    page.goto(f"{API}/tableau-de-bord/connexion")
    page.fill("#email", email)
    page.fill("#mdp", mdp)
    page.click("button[type=submit]")


def main() -> None:
    directus = admin()
    roles = {r["name"]: r["id"] for r in directus.get("/roles").json()["data"]}
    suffixe, mdp = secrets.token_hex(3), secrets.token_urlsafe(16)
    comptes = {}
    for role in ("Agent centre d'appels", "Superviseur qualité"):
        email = f"verif-{suffixe}-{len(comptes)}@exemple.cd"
        r = directus.post("/users", json={"email": email, "password": mdp, "role": roles[role]})
        r.raise_for_status()
        comptes[role] = (r.json()["data"]["id"], email)
    debut = sql("SELECT now()")
    try:
        with sync_playwright() as p:
            navigateur = p.chromium.launch(channel="msedge", args=[
                "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                "--disable-features=WebRtcHideLocalIpsWithMdns",
            ])
            agent = navigateur.new_context(permissions=["microphone"]).new_page()

            print("1. Connexion de l'agent et du téléphone")
            connecter(agent, comptes["Agent centre d'appels"][1], mdp)
            verifier(agent.url.endswith("/tableau-de-bord/agent"), "l'agent arrive sur sa console")
            agent.select_option("#poste", "poste1")
            agent.click("text=Prendre ce poste")
            etat = agent.locator("#etat")
            expect(etat).to_have_attribute("data-etat", "disponible", timeout=15000)
            verifier(True, "téléphone du navigateur enregistré (poste 1 disponible)")

            print("2. Appel d'un citoyen, décroché par l'agent")
            appel_citoyen("0844000001")
            expect(etat).to_have_attribute("data-etat", "sonnerie", timeout=60000)
            verifier(True, "l'appel sonne dans le navigateur")
            agent.click("#decrocher")
            expect(etat).to_have_attribute("data-etat", "communication", timeout=10000)
            expect(agent.locator("#appel-info")).to_contain_text("Français", timeout=10000)
            verifier(True, "en communication ; la langue choisie s'affiche (Français)")
            verifier(agent.locator("#decrocher").is_hidden()
                     and agent.locator("#raccrocher").is_visible()
                     and agent.locator("#reprendre").is_hidden(),
                     "boutons cohérents : « Raccrocher » visible, « Décrocher » et « Reprendre » masqués")
            time.sleep(8)  # le micro factice « parle »
            agent.click("#raccrocher")
            expect(etat).to_have_attribute("data-etat", "qualification", timeout=10000)
            agent.check("input[value=renseigne]")
            agent.click("#qualification button[type=submit]")
            expect(etat).to_have_attribute("data-etat", "disponible", timeout=10000)
            ligne = sql(f"SELECT poste || '|' || coalesce(qualification, '') FROM coeur.appels "
                        f"WHERE debut > '{debut}' AND decroche_a IS NOT NULL")
            verifier(ligne == "poste1|renseigne", f"appel décroché au poste 1 et qualifié ({ligne})")
            fichier = sql(f"SELECT fichier FROM coeur.enregistrements WHERE cree_a > '{debut}'")
            taille = compose("exec", "-T", "asterisk", "stat", "-c", "%s",
                             f"/var/spool/asterisk/enregistrements/{fichier}").strip()
            verifier(taille.isdigit() and int(taille) > 20000,
                     f"conversation WebRTC enregistrée avec du son ({taille} octets)")

            print("3. Pause, puis rappel")
            agent.click("#pause")
            expect(etat).to_have_attribute("data-etat", "pause", timeout=10000)
            verifier(agent.locator("#pause").is_hidden() and agent.locator("#reprendre").is_visible(),
                     "en pause : seul « Reprendre les appels » est proposé")
            appel_citoyen("0855000002")
            time.sleep(55)
            verifier(agent.locator("#etat").get_attribute("data-etat") == "pause",
                     "en pause, aucun appel n'est présenté")
            agent.click("#actualiser-rappels")
            # La liste va du plus ancien au plus récent : ce rappel est le dernier.
            ligne_rappel = agent.locator("#rappels tr").last
            ligne_rappel.locator("button:has-text('Prendre')").click()
            expect(ligne_rappel.locator("strong")).to_contain_text("243855000002", timeout=5000)
            verifier(True, "rappel pris : le numéro s'affiche pour l'agent seulement")
            ligne_rappel.locator("button:has-text('Rappelé')").click()
            time.sleep(2)
            restant = sql(f"SELECT count(*) FROM coeur.rappels WHERE cree_a > '{debut}' "
                          "AND numero_chiffre IS NOT NULL")
            verifier(restant == "0", "rappel clôturé : numéro effacé de la base")
            agent.click("#reprendre")
            expect(etat).to_have_attribute("data-etat", "disponible", timeout=10000)

            print("4. Écoute qualité")
            qualite = navigateur.new_context().new_page()
            connecter(qualite, comptes["Superviseur qualité"][1], mdp)
            verifier(qualite.url.endswith("/tableau-de-bord/qualite"),
                     "le superviseur arrive sur l'écoute qualité")
            source = qualite.locator("td audio").first.get_attribute("src")
            reponse = qualite.request.get(f"{API}{source}")
            verifier(reponse.status == 200 and reponse.headers["content-type"] == "audio/wav",
                     "l'enregistrement s'écoute")
            qualite.reload()
            verifier(comptes["Superviseur qualité"][1] in qualite.locator("main").inner_text(),
                     "l'écoute figure au journal")
            navigateur.close()
    finally:
        for _, (uid, _) in comptes.items():
            directus.delete(f"/users/{uid}")

    print(f"\n{'Vérification réussie.' if not ECHECS else f'{len(ECHECS)} échec(s).'}")
    sys.exit(1 if ECHECS else 0)


if __name__ == "__main__":
    main()
