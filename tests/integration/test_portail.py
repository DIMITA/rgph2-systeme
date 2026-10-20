"""Portail web citoyen : léger, sans ressource externe, ne sert que des contenus validés."""

import json
import re

import pytest
from sqlalchemy import select

from coeur.connaissances.modeles import Contenu, Traduction
from coeur.interactions.modeles import Interaction
from coeur.portail.textes import DOSSIER
from coeur.signalements.modeles import Signalement

QUESTION = "Quand les agents recenseurs passeront-ils chez moi ?"


@pytest.fixture(autouse=True)
def limites_remises_a_zero():
    from coeur.portail.routes import limiteurs

    for limiteur in limiteurs():
        limiteur.reinitialiser()


def test_racine_redirige_vers_le_francais(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/fr"


def test_accueil(client, exemples):
    r = client.get("/fr")
    assert r.status_code == 200
    assert '<html lang="fr">' in r.text
    assert 'action="/fr/question"' in r.text
    for code in ("fr", "ln", "sw", "kg", "lua"):
        assert f'href="/{code}"' in r.text


def test_langue_inconnue_ou_inactive(client):
    assert client.get("/zz").status_code == 404


def test_aucune_ressource_externe(client, exemples):
    html = client.get("/fr").text + client.get("/fr/faq").text + client.get("/fr/signaler").text
    externes = re.findall(r'(?:src|href|action)="(https?:)?//', html)
    assert externes == []


def test_page_legere_pour_la_2g(client, exemples):
    poids = sum(
        len(client.get(chemin).content)
        for chemin in ("/fr", "/statique/portail.css", "/statique/portail.js")
    )
    assert poids < 30_000, f"{poids} octets"


def test_en_tetes_de_securite(client):
    r = client.get("/fr")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    # La documentation de l'API (Swagger) n'est pas bridée par la politique du portail.
    assert "content-security-policy" not in client.get("/docs").headers


def test_question_sans_javascript(client, exemples, session_admin):
    r = client.post("/fr/question", data={"texte": QUESTION})
    assert r.status_code == 200
    assert "Les agents recenseurs passent dans tous les ménages" in r.text
    interaction = session_admin.scalars(select(Interaction)).one()
    assert interaction.canal == "web"
    assert interaction.resultat == "reponse"


def test_escalade_affiche_le_numero_vert(client, exemples):
    r = client.post("/fr/question", data={"texte": "Quel est le prix du riz ?"})
    assert r.status_code == 200
    assert "0800 000 000" in r.text


def test_sans_numero_vert_aucun_numero_affiche(client, exemples, monkeypatch):
    from coeur.config import parametres

    monkeypatch.setattr(parametres(), "numero_vert", "")
    r = client.post("/fr/question", data={"texte": "Quel est le prix du riz ?"})
    assert "pas encore de réponse validée" in r.text
    assert "numéro vert" not in r.text.lower()
    accueil = client.get("/fr").text
    assert "numéro vert" not in accueil.lower()
    assert "{numero}" not in accueil


def test_repli_en_francais_signale(client, exemples):
    r = client.post("/ln/question", data={"texte": QUESTION})
    assert 'class="repli"' in r.text


def test_question_vide_refusee(client, exemples):
    r = client.post("/fr/question", data={"texte": "   "})
    assert r.status_code == 422


def test_texte_echappe(client, exemples):
    r = client.post("/fr/question", data={"texte": "<script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text


def test_api_json_du_portail(client, exemples, session_admin):
    r = client.post("/api/portail/question", json={"texte": QUESTION, "langue": "fr"})
    assert r.status_code == 200
    assert r.json()["contenu"]["cle"] == "exemple-calendrier-passage"
    assert session_admin.scalars(select(Interaction.canal)).one() == "web"


def test_api_json_refuse_les_champs_non_prevus(client):
    r = client.post("/api/portail/question", json={"texte": QUESTION, "nom": "Ilunga"})
    assert r.status_code == 422


def test_limite_de_debit(client, exemples):
    statuts = [
        client.post("/api/portail/question", json={"texte": "bonjour"}).status_code
        for _ in range(21)
    ]
    assert statuts[:20] == [200] * 20
    assert statuts[20] == 429
    assert client.post("/fr/question", data={"texte": "bonjour"}).status_code == 429


def test_faq_ne_montre_que_le_publie(client, exemples, session_admin):
    contenu = Contenu(cle="secret", statut="brouillon")
    session_admin.add(contenu)
    session_admin.flush()
    session_admin.add(Traduction(contenu_id=contenu.id, langue_code="fr", statut="publie",
                                 question="Question pas encore validée ?", reponse="..."))
    session_admin.commit()
    r = client.get("/fr/faq")
    assert "Comment reconnaître un vrai agent recenseur ?" in r.text
    assert "Question pas encore validée" not in r.text


def test_formulaire_de_signalement(client):
    r = client.get("/fr/signaler")
    assert r.status_code == 200
    assert '<optgroup label="Nord-Kivu">' in r.text
    assert 'value="NKV-GOM"' in r.text
    assert 'name="telephone"' not in r.text


def test_envoi_d_un_signalement(client, session_admin):
    r = client.post("/fr/signaler", data={
        "type": "menage_non_visite", "territoire_code": "NKV-GOM",
        "localite": "Himbi", "description": "Personne n'est passé",
    })
    assert r.status_code == 200
    signalement = session_admin.scalars(select(Signalement)).one()
    assert (signalement.canal, signalement.territoire_code) == ("web", "NKV-GOM")
    assert signalement.usager_empreinte is None


def test_signalement_invalide_reaffiche_le_formulaire(client, session_admin):
    r = client.post("/fr/signaler", data={"type": "menage_non_visite", "territoire_code": "XXX"})
    assert r.status_code == 422
    assert 'name="territoire_code"' in r.text
    assert session_admin.scalars(select(Signalement)).all() == []


@pytest.mark.parametrize("fichier", sorted(p.name for p in DOSSIER.glob("*.json")))
def test_chaque_traduction_a_exactement_les_cles_du_francais(fichier):
    reference = json.loads((DOSSIER / "fr.json").read_text(encoding="utf-8"))
    traduction = json.loads((DOSSIER / fichier).read_text(encoding="utf-8"))
    assert set(traduction) == set(reference)
    for cle, texte in reference.items():
        assert ("{numero}" in texte) == ("{numero}" in traduction[cle]), cle


def test_interface_en_lingala(client, exemples):
    r = client.get("/ln")
    assert '<html lang="ln">' in r.text
    assert "Motuna na yo" in r.text
    assert "Tinda" in r.text
    r = client.post("/ln/question", data={"texte": "Quel est le prix du riz ?"})
    assert "benga ofele na nimero 0800 000 000" in r.text


def test_interface_traduite_avec_repli_sur_le_francais(client, exemples):
    from coeur.portail.textes import textes

    assert textes("fr")["envoyer"]
    # Toute clé absente d'une langue est reprise du français.
    assert set(textes("ln")) == set(textes("fr"))
