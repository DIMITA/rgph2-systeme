"""Charte graphique du Gouvernement : toutes les interfaces montrées aux utilisateurs la portent."""

import re

import pytest

from coeur.config import parametres

NAVIGATEUR = {"Accept": "text/html,application/xhtml+xml"}


def marque(html: str) -> dict:
    """Armoiries (couleur ou blanc), Ligne d'État et intitulé, dans cet ordre."""
    bloc = re.search(r'<a class="marque[^"]*"[^>]*>(.*?)</a>', html, re.S)
    assert bloc, "bloc-marque absent"
    contenu = bloc.group(1)
    armoiries = re.search(r'src="/charte/(armoiries-(?:blanc-)?\d+)\.png"', contenu).group(1)
    assert contenu.index("<img") < contenu.index("ligne-etat") < contenu.index("intitule")
    assert "Institut national" in contenu and "Bureau central du recensement" in contenu
    return {"armoiries": armoiries, "bandeau_bleu": "bandeau bandeau-bleu" in html}


def test_portail_accueil_bandeau_blanc_armoiries_en_couleur(client, exemples):
    html = client.get("/fr").text
    assert '<link rel="stylesheet" href="/charte/charte.css">' in html
    assert marque(html) == {"armoiries": "armoiries-64", "bandeau_bleu": False}


@pytest.mark.parametrize("chemin", ["/fr/faq", "/fr/signaler", "/ln/faq"])
def test_portail_autres_pages_bandeau_bleu_armoiries_en_blanc(client, exemples, chemin):
    assert marque(client.get(chemin).text) == {"armoiries": "armoiries-blanc-54",
                                               "bandeau_bleu": True}


def test_pied_de_page_avec_liseré_tricolore(client, exemples):
    html = client.get("/fr").text
    pied = html[html.index('<footer class="pied">'):]
    assert '<div class="tricolore"' in pied
    assert marque(pied)["armoiries"] == "armoiries-blanc-54"


def test_espaces_connectes(client):
    html = client.get("/tableau-de-bord/connexion").text
    assert marque(html) == {"armoiries": "armoiries-blanc-54", "bandeau_bleu": True}
    assert 'href="/charte/favicon.png"' in html


def test_simulateur(client, monkeypatch):
    monkeypatch.setattr(parametres(), "simulateur_mobile", True)
    assert marque(client.get("/simulateur").text)["bandeau_bleu"]


def test_documentation_de_l_api(client):
    html = client.get("/docs").text
    assert marque(html) == {"armoiries": "armoiries-blanc-54", "bandeau_bleu": True}
    assert "/charte/favicon.png" in html
    assert client.get("/redoc").status_code == 404  # une seule documentation


def test_page_d_erreur_aux_couleurs_de_la_charte(client):
    r = client.get("/fr/nexiste-pas", headers=NAVIGATEUR)
    assert r.status_code == 404
    assert "Page introuvable" in r.text
    assert marque(r.text)["bandeau_bleu"]
    r = client.get("/xx", headers=NAVIGATEUR)  # langue inconnue
    assert r.status_code == 404 and "Page introuvable" in r.text


def test_l_api_garde_ses_erreurs_en_json(client):
    r = client.get("/v1/contenus/999", headers={**NAVIGATEUR, "X-Cle-API": "inconnue"})
    assert r.status_code == 401
    assert r.headers["content-type"] == "application/json"
    r = client.get("/fr/nexiste-pas")  # sans Accept HTML (programme) : JSON
    assert r.headers["content-type"] == "application/json"


def test_ressources_de_la_charte(client):
    for fichier in ("charte.css", "cooper-hewitt-medium.woff2", "cooper-hewitt-semibold.woff2",
                    "armoiries-64.png", "armoiries-blanc-54@2x.png", "favicon.png"):
        r = client.get(f"/charte/{fichier}")
        assert r.status_code == 200, fichier
        assert r.headers["cache-control"] == "public, max-age=2592000"
    css = client.get("/charte/charte.css").text
    for couleur in ("#0095c9", "#fff24b", "#db3832", "#17418a"):
        assert couleur in css
    # Ordre de la Ligne d'État : bleu, jaune, rouge, à parts égales (charte, p. 11).
    assert re.search(r"\.ligne-etat\{[^}]*var\(--etat-bleu\) 0 33\.34%,var\(--etat-jaune\) "
                     r"33\.34% 66\.67%,var\(--etat-rouge\) 66\.67%", css)


def test_police_legere(client):
    """Cooper Hewitt réduite aux caractères utiles : moins de 20 Ko par graisse (2G)."""
    for graisse in ("medium", "semibold"):
        assert len(client.get(f"/charte/cooper-hewitt-{graisse}.woff2").content) < 20_000
