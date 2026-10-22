"""L'application de terrain dans un vrai navigateur (Chromium piloté par Playwright).

Le serveur est réellement arrêté au milieu du test : la page et le service worker
n'ont plus aucun réseau, comme un kiosque dans une zone non couverte.

Prérequis : pip install -e ".[e2e]" et un Chromium (`playwright install chromium`, ou
NAVIGATEUR_E2E=/chemin/vers/chrome). Sans eux, le test est ignoré.
"""

import os
import socket
import threading
import time

import pytest
from sqlalchemy import func, select

from coeur.interactions.modeles import Interaction
from coeur.mobile.modeles import Consultation
from coeur.signalements.modeles import Signalement
from coeur.terrain import service
from coeur.terrain.modeles import Appareil

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect


class Serveur:
    """L'application servie par uvicorn dans un fil, qu'on peut couper et relancer."""

    def __init__(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._serveur = None

    def demarrer(self):
        import uvicorn

        from coeur.main import app

        self._serveur = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port,
                                                      log_level="warning", lifespan="off"))
        fil = threading.Thread(target=self._serveur.run, daemon=True)
        fil.start()
        limite = time.monotonic() + 15
        while not self._serveur.started:
            assert time.monotonic() < limite, "le serveur ne démarre pas"
            time.sleep(0.05)
        self._fil = fil

    def arreter(self):
        self._serveur.should_exit = True
        self._fil.join(timeout=15)


@pytest.fixture
def navigateur():
    with sync_api.sync_playwright() as p:
        try:
            chromium = p.chromium.launch(executable_path=os.environ.get("NAVIGATEUR_E2E"))
        except Exception as erreur:  # navigateur absent ou incompatible
            pytest.skip(f"Chromium indisponible : {erreur}")
        yield chromium
        chromium.close()


def compter(session, modele, *conditions):
    session.expire_all()
    return session.scalar(select(func.count()).select_from(modele).where(*conditions))


def test_kiosque_hors_ligne_de_bout_en_bout(navigateur, session_admin, exemples):
    from coeur.calendrier.service import charger_exemples

    charger_exemples(session_admin)
    _, code = service.creer(session_admin, type_="kiosque", code="KIO-NKV-GOM-01",
                            territoire_code="NKV-GOM", langues=["ln"], lieu="École Himbi",
                            jours_activation=7)
    serveur = Serveur()
    serveur.demarrer()
    try:
        page = navigateur.new_context().new_page()
        accueil = page.get_by_role("navigation").get_by_role("button", name="Accueil")
        page.goto(f"{serveur.url}/terrain/")

        # 1. Activation, téléchargement du paquet.
        page.get_by_label("Code d'activation").fill(code.lower())
        page.get_by_role("button", name="Activer").click()
        expect(page.get_by_role("heading", name="Choisissez votre langue")).to_be_visible()
        expect(page.get_by_role("button", name="Lingala")).to_be_visible()
        page.evaluate("navigator.serviceWorker.ready.then(() => true)")

        # 2. Plus de réseau du tout : page et service worker sont coupés du serveur.
        serveur.arreter()
        page.reload()
        page.get_by_role("button", name="Français").click()
        expect(page.locator("#etat-reseau")).to_have_text("Hors ligne")

        # FAQ hors ligne, recherche sans accents.
        page.get_by_role("button", name="Questions fréquentes").click()
        page.get_by_label("Rechercher une question").fill("confidentielles")
        questions = page.locator("details.question")
        expect(questions).to_have_count(1)
        questions.first.locator("summary").click()
        expect(questions.first.get_by_text("Réponse officielle")).to_be_visible()

        # Date de passage : le territoire du kiosque est déjà choisi.
        accueil.click()
        page.get_by_role("button", name="Date de passage des agents").click()
        page.get_by_role("button", name="Voir").click()
        expect(page.locator("#resultat-passage")).to_contain_text("17 mai 2027")

        # Ménage non recensé, puis question absente de la FAQ : mis en attente.
        accueil.click()
        page.get_by_role("button", name="Mon ménage n'a pas été recensé").click()
        page.get_by_label("Quartier ou village (facultatif)").fill("Himbi")
        page.get_by_role("button", name="Envoyer").click()
        expect(page.locator("#texte-merci")).to_have_text(
            "Ce sera transmis dès que l'appareil aura du réseau.")
        accueil.click()
        page.get_by_role("button", name="Ma question n'est pas dans la liste").click()
        page.get_by_label("La question").fill("Faut-il présenter une pièce d'identité ?")
        page.get_by_role("button", name="Envoyer").click()
        expect(page.locator("#etat-attente")).to_have_text("4 envoi(s) en attente")
        assert compter(session_admin, Signalement) == 0

        # Le badge, lui, demande du réseau.
        accueil.click()
        page.get_by_role("button", name="Vérifier un badge d'agent").click()
        page.get_by_label("Numéro du badge").fill("AB1234")
        page.get_by_role("button", name="Vérifier").click()
        expect(page.locator("#resultat-badge")).to_contain_text("demande du réseau")

        # 3. Le réseau revient : tout part, une seule fois.
        serveur.demarrer()
        page.get_by_role("button", name="Synchroniser").click()
        expect(page.locator("#etat-attente")).to_have_text("")
        expect(page.locator("#etat-reseau")).to_have_text("En ligne")
        assert compter(session_admin, Signalement, Signalement.canal == "kiosque",
                       Signalement.localite == "Himbi") == 1
        assert compter(session_admin, Interaction, Interaction.motif_escalade == "remontee_terrain") == 1
        assert compter(session_admin, Interaction, Interaction.resultat == "reponse") == 1
        assert compter(session_admin, Consultation, Consultation.service == "passage") == 1

        # 4. Tablette volée : révoquée, elle redemande un code.
        service.revoquer(session_admin, session_admin.scalar(select(Appareil)))
        page.get_by_role("button", name="Synchroniser").click()
        expect(page.get_by_role("heading", name="Activer cet appareil")).to_be_visible()
    finally:
        if serveur._serveur and not serveur._serveur.should_exit:
            serveur.arreter()


def test_ambassadeur_remonte_une_rumeur_en_ligne(navigateur, session_admin, exemples):
    _, code = service.creer(session_admin, type_="ambassadeur", code="AMB-KCE-MAT-07",
                            territoire_code="KCE-MAT", langues=[], lieu=None, jours_activation=7)
    serveur = Serveur()
    serveur.demarrer()
    try:
        page = navigateur.new_context(viewport={"width": 390, "height": 800}).new_page()
        page.goto(f"{serveur.url}/terrain/")
        page.get_by_label("Code d'activation").fill(code)
        page.get_by_role("button", name="Activer").click()
        # Une seule langue embarquée : directement l'accueil, sans choix de langue.
        expect(page.get_by_text("Espace Ambassadeur")).to_be_visible()
        page.get_by_role("button", name="Remonter une rumeur").click()
        page.get_by_role("button", name="Envoyer").click()
        expect(page.locator("#erreur-remontee")).to_have_text("Ce champ est obligatoire.")
        page.get_by_label("Ce qui se dit").fill("Le recensement servirait à recruter des soldats")
        page.get_by_role("button", name="Envoyer").click()
        expect(page.locator("#texte-merci")).to_have_text(
            "C'est déjà transmis au Bureau central du recensement.")
        session_admin.expire_all()
        rumeur = session_admin.scalar(select(Signalement))
        assert (rumeur.canal, rumeur.type, rumeur.territoire_code) == ("ambassadeur", "rumeur",
                                                                       "KCE-MAT")
        assert rumeur.description == "Le recensement servirait à recruter des soldats"
    finally:
        serveur.arreter()
