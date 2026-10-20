"""Console des agents et écoute qualité : espaces réservés par rôle, rappels, journal des écoutes."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from coeur.centre_appels.modeles import Appel, Ecoute, Enregistrement, Rappel
from coeur.centre_appels.postes import mot_de_passe_poste
from coeur.interactions.modeles import Interaction
from coeur.signalements.modeles import Signalement
from coeur.tableau_de_bord.auth import Utilisateur, authentificateur
from tests.conftest import CLE_CENTRE

MDP = "bon-mot-de-passe"
COMPTES = {
    "agent1@bcr.cd": "Agent centre d'appels",
    "agent2@bcr.cd": "Agent centre d'appels",
    "qualite@bcr.cd": "Superviseur qualité",
    "unfpa@exemple.org": "Tableau de bord",
    "admin@bcr.cd": "Administrator",
}
CENTRE = {"X-Cle-API": CLE_CENTRE}


class AuthFactice:
    def verifier(self, email: str, mdp: str) -> Utilisateur | None:
        return Utilisateur(email, COMPTES[email]) if email in COMPTES and mdp == MDP else None


@pytest.fixture(autouse=True)
def auth_factice(client, tmp_path, monkeypatch):
    from coeur.config import parametres
    from coeur.main import app
    from coeur.tableau_de_bord.routes import limiteur_connexion

    limiteur_connexion().reinitialiser()
    monkeypatch.setattr(parametres(), "dossier_enregistrements", str(tmp_path))
    app.dependency_overrides[authentificateur] = AuthFactice
    yield
    app.dependency_overrides.pop(authentificateur, None)


def connecter(client, email):
    r = client.post("/tableau-de-bord/connexion", data={"email": email, "mdp": MDP},
                    follow_redirects=False)
    assert r.status_code == 303
    return r.headers["location"]


@pytest.fixture
def agent(client):
    connecter(client, "agent1@bcr.cd")
    client.post("/tableau-de-bord/agent/poste", data={"poste": "poste2"})
    return client


def evenement(client, **donnees):
    return client.post("/v1/appels/evenements", data=donnees, headers=CENTRE)


def compter(session, modele, *conditions):
    return session.scalar(select(func.count()).select_from(modele).where(*conditions))


# --- Espaces et rôles ------------------------------------------------------------------

@pytest.mark.parametrize("email, accueil", [
    ("agent1@bcr.cd", "/tableau-de-bord/agent"),
    ("qualite@bcr.cd", "/tableau-de-bord/qualite"),
    ("unfpa@exemple.org", "/tableau-de-bord"),
    ("admin@bcr.cd", "/tableau-de-bord"),
])
def test_accueil_selon_le_role(client, email, accueil):
    assert connecter(client, email) == accueil


@pytest.mark.parametrize("email, interdit, renvoi", [
    ("agent1@bcr.cd", "/tableau-de-bord", "/tableau-de-bord/agent"),
    ("agent1@bcr.cd", "/tableau-de-bord/qualite", "/tableau-de-bord/agent"),
    ("qualite@bcr.cd", "/tableau-de-bord/agent", "/tableau-de-bord/qualite"),
    ("unfpa@exemple.org", "/tableau-de-bord/agent", "/tableau-de-bord"),
    ("unfpa@exemple.org", "/tableau-de-bord/qualite", "/tableau-de-bord"),
])
def test_chaque_role_reste_dans_son_espace(client, email, interdit, renvoi):
    connecter(client, email)
    r = client.get(interdit, follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, renvoi)


def test_l_administrateur_voit_tout(client):
    connecter(client, "admin@bcr.cd")
    for chemin in ("/tableau-de-bord", "/tableau-de-bord/agent", "/tableau-de-bord/qualite"):
        assert client.get(chemin).status_code == 200


# --- Poste et téléphone ----------------------------------------------------------------

def test_choix_du_poste(client):
    connecter(client, "agent1@bcr.cd")
    html = client.get("/tableau-de-bord/agent").text
    assert all(f'value="poste{n}"' in html for n in range(1, 7))
    assert client.post("/tableau-de-bord/agent/poste", data={"poste": "poste9"}).status_code == 422


def test_configuration_du_telephone(agent):
    from coeur.config import parametres

    r = agent.get("/tableau-de-bord/agent")
    assert 'data-sip-uri="sip:poste2@rgph2.local"' in r.text
    secret = parametres().secret_postes
    assert f'data-mot-de-passe="{mot_de_passe_poste(secret, "poste2")}"' in r.text
    assert 'src="/tableau-de-bord/statique/jssip.min.js"' in r.text
    # La page autorise la connexion WebSocket vers Asterisk, et rien d'autre à l'extérieur.
    csp = r.headers["content-security-policy"]
    assert "connect-src 'self' ws://localhost:8088/ws" in csp
    assert r.headers["cache-control"] == "no-store"


def test_liberer_le_poste(agent):
    agent.post("/tableau-de-bord/agent/liberer")
    assert "data-sip-uri" not in agent.get("/tableau-de-bord/agent").text


def test_appel_en_cours_sur_le_poste(agent, session_admin):
    assert agent.get("/tableau-de-bord/agent/appel-courant").json() == {"appel": None}
    evenement(agent, type="debut", appel="a1", numero="0812345678")
    evenement(agent, type="langue", appel="a1", langue="ln")
    evenement(agent, type="decroche", appel="a1", poste="poste2", fichier="a1.wav")
    appel = agent.get("/tableau-de-bord/agent/appel-courant").json()["appel"]
    assert (appel["reference"], appel["langue"], appel["langue_nom"]) == ("a1", "ln", "Lingala")
    assert "numero" not in appel and "usager_empreinte" not in appel


# --- Outils de l'agent -----------------------------------------------------------------

def test_recherche_dans_la_faq_sans_journaliser(agent, exemples, session_admin):
    resultats = agent.get("/tableau-de-bord/agent/recherche",
                          params={"q": "quand passent les agents", "langue": "fr"}).json()
    assert resultats[0]["cle"] == "exemple-calendrier-passage"
    assert resultats[0]["reponse"]
    assert compter(session_admin, Interaction) == 0


def test_signalement_pris_au_telephone(agent, session_admin):
    r = agent.post("/tableau-de-bord/agent/signalement",
                   data={"type": "menage_non_visite", "territoire_code": "NKV-GOM",
                         "localite": "Himbi"})
    assert r.status_code == 201
    assert session_admin.scalars(select(Signalement.canal)).one() == "centre_ecoute"
    r = agent.post("/tableau-de-bord/agent/signalement",
                   data={"type": "menage_non_visite", "territoire_code": "XXX"})
    assert r.status_code == 422


def test_qualification_de_l_appel(agent, session_admin):
    evenement(agent, type="debut", appel="a1")
    r = agent.post("/tableau-de-bord/agent/qualification",
                   data={"appel": "a1", "qualification": "renseigne"})
    assert r.status_code == 200
    assert session_admin.scalars(select(Appel.qualification)).one() == "renseigne"
    assert agent.post("/tableau-de-bord/agent/qualification",
                      data={"appel": "a1", "qualification": "texte libre"}).status_code == 422
    assert agent.post("/tableau-de-bord/agent/qualification",
                      data={"appel": "inconnu", "qualification": "renseigne"}).status_code == 404


# --- Rappels ---------------------------------------------------------------------------

def test_liste_des_rappels_sans_numero(agent):
    evenement(agent, type="rappel", appel="a1", numero="0812345678", langue="ln")
    [rappel] = agent.get("/tableau-de-bord/agent/rappels").json()
    assert rappel["langue_nom"] == "Lingala" and rappel["statut"] == "a_rappeler"
    assert "812345678" not in str(rappel)


def test_prendre_et_cloturer_un_rappel(agent, session_admin):
    from coeur.main import app

    evenement(agent, type="rappel", appel="a1", numero="0812345678")
    [rappel] = agent.get("/tableau-de-bord/agent/rappels").json()
    r = agent.post(f"/tableau-de-bord/agent/rappels/{rappel['id']}/prendre")
    assert r.json() == {"numero": "243812345678"}

    with TestClient(app) as autre:  # un second agent ne peut pas prendre le même rappel
        connecter(autre, "agent2@bcr.cd")
        assert autre.post(f"/tableau-de-bord/agent/rappels/{rappel['id']}/prendre").status_code == 409

    r = agent.post(f"/tableau-de-bord/agent/rappels/{rappel['id']}/cloturer",
                   data={"statut": "rappele"})
    assert r.status_code == 200
    ligne = session_admin.get(Rappel, rappel["id"])
    session_admin.refresh(ligne)
    assert (ligne.statut, ligne.numero_chiffre, ligne.traite_par) == (
        "rappele", None, "agent1@bcr.cd")
    assert agent.get("/tableau-de-bord/agent/rappels").json() == []


def test_cloture_invalide(agent):
    evenement(agent, type="rappel", appel="a1", numero="0812345678")
    [rappel] = agent.get("/tableau-de-bord/agent/rappels").json()
    r = agent.post(f"/tableau-de-bord/agent/rappels/{rappel['id']}/cloturer",
                   data={"statut": "expire"})
    assert r.status_code == 422


# --- Écoute qualité --------------------------------------------------------------------

@pytest.fixture
def enregistrement(client, tmp_path):
    (tmp_path / "a1.wav").write_bytes(b"RIFF" + b"\0" * 16_040)
    evenement(client, type="debut", appel="a1")
    evenement(client, type="langue", appel="a1", langue="sw")
    evenement(client, type="decroche", appel="a1", poste="poste3", fichier="a1.wav")


def test_liste_des_enregistrements(client, enregistrement):
    connecter(client, "qualite@bcr.cd")
    html = client.get("/tableau-de-bord/qualite").text
    assert "Kiswahili" in html and "poste3" in html
    assert 'src="/tableau-de-bord/qualite/ecouter/1"' in html


def test_ecoute_journalisee(client, enregistrement, session_admin):
    connecter(client, "qualite@bcr.cd")
    r = client.get("/tableau-de-bord/qualite/ecouter/1")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.headers["cache-control"] == "no-store"
    # Le navigateur redemande des morceaux du fichier : une seule écoute est comptée.
    client.get("/tableau-de-bord/qualite/ecouter/1", headers={"Range": "bytes=8000-"})
    ecoute = session_admin.scalars(select(Ecoute)).one()
    assert (ecoute.utilisateur, ecoute.fichier) == ("qualite@bcr.cd", "a1.wav")
    assert "qualite@bcr.cd" in client.get("/tableau-de-bord/qualite").text


def test_un_agent_ne_peut_pas_ecouter(client, enregistrement):
    connecter(client, "agent1@bcr.cd")
    r = client.get("/tableau-de-bord/qualite/ecouter/1", follow_redirects=False)
    assert r.status_code == 303


def test_fichier_absent(client, enregistrement, tmp_path):
    (tmp_path / "a1.wav").unlink()
    connecter(client, "qualite@bcr.cd")
    assert client.get("/tableau-de-bord/qualite/ecouter/1").status_code == 404


def test_journal_des_ecoutes_conserve_apres_suppression(client, enregistrement, session_admin):
    from coeur.centre_appels.service import purger_enregistrements

    connecter(client, "qualite@bcr.cd")
    client.get("/tableau-de-bord/qualite/ecouter/1")
    purger_enregistrements(session_admin, jours=-1)
    assert compter(session_admin, Enregistrement) == 0
    ecoute = session_admin.scalars(select(Ecoute)).one()
    session_admin.refresh(ecoute)
    assert (ecoute.enregistrement_id, ecoute.fichier) == (None, "a1.wav")


# --- Statistiques d'appels -------------------------------------------------------------

def test_statistiques_d_appels_dans_la_synthese(client, session_admin):
    for n in range(6):
        evenement(client, type="debut", appel=f"a{n}")
        evenement(client, type="file_entree", appel=f"a{n}")
        if n < 5:
            evenement(client, type="decroche", appel=f"a{n}", poste="poste1")
        evenement(client, type="fin", appel=f"a{n}")
    connecter(client, "admin@bcr.cd")
    html = client.get("/tableau-de-bord").text
    assert "Centre d'appels" in html
    assert "appels reçus" in html
