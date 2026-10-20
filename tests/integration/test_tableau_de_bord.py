"""Tableau de bord du Ministère : accès réservé, mêmes garde-fous statistiques."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update

from coeur.interactions.modeles import Interaction
from coeur.signalements.modeles import Signalement
from coeur.tableau_de_bord.auth import Utilisateur, authentificateur
from tests.integration.conftest import USSD, WEB

MDP = "bon-mot-de-passe"
COMPTES = {
    "validateur@bcr.cd": "Validateur BCR",
    "unfpa@exemple.org": "Tableau de bord",
    "redacteur@bcr.cd": "Rédacteur",
}


class AuthFactice:
    def verifier(self, email: str, mdp: str) -> Utilisateur | None:
        if email in COMPTES and mdp == MDP:
            return Utilisateur(email=email, role=COMPTES[email])
        return None


@pytest.fixture(autouse=True)
def auth_factice(client):
    from coeur.main import app
    from coeur.tableau_de_bord.routes import limiteur_connexion

    limiteur_connexion().reinitialiser()
    app.dependency_overrides[authentificateur] = AuthFactice
    yield
    app.dependency_overrides.pop(authentificateur, None)


def connecter(client, email="validateur@bcr.cd", mdp=MDP):
    return client.post("/tableau-de-bord/connexion", data={"email": email, "mdp": mdp},
                       follow_redirects=False)


@pytest.fixture
def connecte(client):
    assert connecter(client).status_code == 303
    return client


@pytest.fixture
def activite(client, exemples):
    for i in range(6):
        client.post("/v1/questions", headers=WEB, json={
            "texte": "Quand les agents recenseurs passeront-ils chez moi ?",
            "territoire_code": "NKV-GOM", "telephone": f"08100000{i:02d}"})
    for _ in range(3):
        client.post("/v1/questions", headers=USSD, json={"texte": "Combien coûte le pain ?"})
    client.post("/v1/questions", headers=WEB, json={"texte": "Où est le bureau de Goma ?"})
    for _ in range(2):
        client.post("/v1/signalements", headers=WEB, json={
            "type": "menage_non_visite", "territoire_code": "KCE-MAT", "localite": "Quartier Soyo"})


# --- Accès ---------------------------------------------------------------------------

@pytest.mark.parametrize("chemin", [
    "/tableau-de-bord", "/tableau-de-bord/escalades",
    "/tableau-de-bord/signalements", "/tableau-de-bord/export.csv",
])
def test_pages_reservees(client, chemin):
    r = client.get(chemin, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/tableau-de-bord/connexion"


def test_page_de_connexion(client):
    r = client.get("/tableau-de-bord/connexion")
    assert r.status_code == 200
    assert 'type="password"' in r.text


def test_mauvais_mot_de_passe(client):
    r = connecter(client, mdp="faux")
    assert r.status_code == 401
    assert client.get("/tableau-de-bord", follow_redirects=False).status_code == 303


def test_role_non_autorise(client):
    r = connecter(client, email="redacteur@bcr.cd")
    assert r.status_code == 403
    assert client.get("/tableau-de-bord", follow_redirects=False).status_code == 303


def test_connexion_puis_deconnexion(client):
    r = connecter(client, email="unfpa@exemple.org")
    assert r.status_code == 303
    assert r.headers["location"] == "/tableau-de-bord"
    cookie = r.headers["set-cookie"]
    assert "path=/tableau-de-bord" in cookie.lower()
    assert "httponly" in cookie.lower()
    assert "samesite=strict" in cookie.lower()
    assert client.get("/tableau-de-bord").status_code == 200
    client.post("/tableau-de-bord/deconnexion")
    assert client.get("/tableau-de-bord", follow_redirects=False).status_code == 303


def test_limite_des_tentatives_de_connexion(client):
    statuts = [connecter(client, mdp="faux").status_code for _ in range(11)]
    assert statuts[:10] == [401] * 10
    assert statuts[10] == 429


def test_le_portail_ne_pose_aucun_cookie(client, exemples):
    assert "set-cookie" not in client.get("/fr").headers
    assert "set-cookie" not in client.post("/fr/question", data={"texte": "bonjour"}).headers


def test_pages_non_mises_en_cache(connecte):
    assert connecte.get("/tableau-de-bord").headers["cache-control"] == "no-store"


# --- Synthèse ------------------------------------------------------------------------

def test_synthese(connecte, activite):
    html = connecte.get("/tableau-de-bord").text
    assert "10" in html                      # 10 interactions au total
    assert "Nord-Kivu" in html               # noms des unités, pas seulement les codes
    assert "&lt; 5" in html                  # petits effectifs masqués
    assert "Quartier Soyo" not in html       # jamais de localité dans les statistiques
    assert "<progress" in html               # barres sans style en ligne (CSP)


def test_synthese_par_territoire_et_periode(connecte, activite):
    html = connecte.get("/tableau-de-bord?niveau=territoire&depuis=2000-01-01&jusqu_a=").text
    assert "Goma" in html


def test_niveau_plus_fin_refuse(connecte):
    assert connecte.get("/tableau-de-bord?niveau=localite").status_code == 422


def test_export_csv(connecte, activite):
    r = connecte.get("/tableau-de-bord/export.csv?niveau=territoire")
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lignes = r.text.splitlines()
    assert lignes[0].startswith("﻿indicateur;axe;valeur")  # BOM : accents corrects dans Excel
    assert any(l.startswith("interactions;territoire;NKV-GOM;") for l in lignes)
    assert "Soyo" not in r.text


# --- Questions escaladées ------------------------------------------------------------

def test_questions_escaladees(connecte, activite):
    html = connecte.get("/tableau-de-bord/escalades").text
    assert "combien coûte le pain ?" in html  # regroupée, en minuscules, avec son nombre
    assert "Où est le bureau de Goma ?" in html
    assert "Quand les agents recenseurs" not in html  # réponses trouvées : absentes


def test_escalades_filtrees_par_langue(connecte, activite):
    html = connecte.get("/tableau-de-bord/escalades?langue=ln").text
    assert "Où est le bureau de Goma ?" not in html


# --- Signalements --------------------------------------------------------------------

def test_signalements_et_changement_de_statut(connecte, activite, session_admin):
    html = connecte.get("/tableau-de-bord/signalements").text
    assert "Quartier Soyo" in html  # utile aux équipes de terrain
    sid = session_admin.scalars(select(Signalement.id)).first()
    r = connecte.post(f"/tableau-de-bord/signalements/{sid}", data={"statut": "clos"},
                      follow_redirects=False)
    assert r.status_code == 303
    session_admin.expire_all()
    assert session_admin.get(Signalement, sid).statut == "clos"
    html = connecte.get("/tableau-de-bord/signalements?statut=clos").text
    assert html.count('class="signalement"') == 1


def test_statut_invalide_refuse(connecte, activite, session_admin):
    sid = session_admin.scalars(select(Signalement.id)).first()
    r = connecte.post(f"/tableau-de-bord/signalements/{sid}", data={"statut": "supprime"})
    assert r.status_code == 422


def test_heures_affichees_a_l_heure_de_kinshasa(connecte, activite, session_admin):
    session_admin.execute(
        update(Interaction).values(horodatage=datetime(2027, 5, 1, 8, 0, tzinfo=timezone.utc))
    )
    session_admin.execute(
        update(Signalement).values(horodatage=datetime(2027, 5, 1, 8, 0, tzinfo=timezone.utc))
    )
    session_admin.commit()
    assert "01/05/2027 09:00" in connecte.get("/tableau-de-bord/escalades").text
    assert "01/05/2027 09:00" in connecte.get("/tableau-de-bord/signalements").text


def test_filtre_de_dates_a_l_heure_locale(connecte, activite, session_admin):
    # 23:30 UTC le 30 avril = 00:30 le 1er mai à Kinshasa : compté le 1er mai.
    session_admin.execute(
        update(Interaction).values(horodatage=datetime(2027, 4, 30, 23, 30, tzinfo=timezone.utc))
    )
    session_admin.commit()
    r = connecte.get("/tableau-de-bord/export.csv?depuis=2027-05-01&jusqu_a=2027-05-01")
    assert "interactions;national;RDC;RDC;10;" in r.text
