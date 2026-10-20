"""Format des messages envoyés à l'API de Meta, et adaptateur Graph."""

import httpx

from coeur.whatsapp.messages import Boutons, Ligne, Liste, Media, Texte, charge_utile
from coeur.whatsapp.passerelle import PasserelleMeta
from coeur.whatsapp.service import lire_entree, signature_valide

NUMERO = "243812345678"


def test_texte():
    assert charge_utile(NUMERO, Texte("Bonjour")) == {
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": NUMERO,
        "type": "text", "text": {"body": "Bonjour", "preview_url": False}}


def test_liste_dans_les_limites_de_meta():
    lignes = [Ligne(f"q:{i}", "Une question beaucoup trop longue pour un titre", "d" * 100)
              for i in range(12)]
    corps = charge_utile(NUMERO, Liste("x" * 2000, "Un bouton au libellé trop long", lignes))
    interactif = corps["interactive"]
    assert interactif["type"] == "list"
    assert len(interactif["body"]["text"]) == 1024
    assert len(interactif["action"]["button"]) <= 20
    rangees = interactif["action"]["sections"][0]["rows"]
    assert len(rangees) == 10
    assert all(len(r["title"]) <= 24 and len(r["description"]) <= 72 for r in rangees)
    assert rangees[0]["title"] == "Une question beaucoup..."


def test_boutons():
    corps = charge_utile(NUMERO, Boutons("Confirmer ?", [("a", "Oui"), ("b", "Non"), ("c", "Menu"),
                                                         ("d", "En trop")]))
    boutons = corps["interactive"]["action"]["buttons"]
    assert [b["reply"]["id"] for b in boutons] == ["a", "b", "c"]


def test_medias():
    assert charge_utile(NUMERO, Media("audio", "https://x/a.mp3"))["audio"] == {"link": "https://x/a.mp3"}
    assert charge_utile(NUMERO, Media("video", "https://x/v.mp4", "Titre"))["video"] == {
        "link": "https://x/v.mp4", "caption": "Titre"}


def test_lire_entree():
    assert lire_entree({"type": "text", "text": {"body": "Bonjour"}}).valeur == "Bonjour"
    assert lire_entree({"type": "interactive", "interactive": {
        "type": "list_reply", "list_reply": {"id": "faq"}}}).valeur == "faq"
    assert lire_entree({"type": "interactive", "interactive": {
        "type": "button_reply", "button_reply": {"id": "menu"}}}).type == "choix"
    assert lire_entree({"type": "image"}).type == "autre"


def test_signature():
    import hashlib
    import hmac
    corps = b'{"a":1}'
    bonne = "sha256=" + hmac.new(b"s", corps, hashlib.sha256).hexdigest()
    assert signature_valide(corps, bonne, "s")
    assert not signature_valide(corps, bonne, "")  # secret non configuré : tout est refusé
    assert not signature_valide(corps, None, "s")
    assert not signature_valide(corps, bonne.replace("sha256=", "sha1="), "s")


def test_passerelle_meta():
    requetes = []

    def repondre(requete):
        requetes.append(requete)
        return httpx.Response(200, json={"messages": [{"id": "wamid.x"}]})

    p = PasserelleMeta("https://graph.facebook.com/v21.0", "123456", "jeton")
    p.http = httpx.Client(transport=httpx.MockTransport(repondre),
                          headers={"Authorization": "Bearer jeton"})
    assert p.envoyer(NUMERO, Texte("Bonjour"))
    assert str(requetes[0].url) == "https://graph.facebook.com/v21.0/123456/messages"
    assert requetes[0].headers["Authorization"] == "Bearer jeton"
    p.http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(400, json={"error": {"code": 131047}})))
    assert not p.envoyer(NUMERO, Texte("Bonjour"))
