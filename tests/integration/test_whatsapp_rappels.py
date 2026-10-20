"""Rappels de passage par WhatsApp : abonnement, envoi J-3 et veille, STOP, expiration."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select, text

from coeur.calendrier.modeles import Passage
from coeur.centre_appels.service import dechiffrer_numero
from coeur.config import parametres
from coeur.whatsapp import abonnements
from coeur.whatsapp.messages import Modele
from coeur.whatsapp.modeles import Abonnement, MessageWhatsapp
from coeur.whatsapp.passerelle import passerelle
from tests.integration.test_whatsapp import NUMERO, Telephone

KINSHASA = ZoneInfo("Africa/Kinshasa")


def a(jour: date, heure: int = 10) -> datetime:
    return datetime.combine(jour, time(heure), KINSHASA)


@pytest.fixture
def tel(client):
    t = Telephone(client)
    t.ecrire("Bonjour")
    t.toucher("langue:fr")
    return t


@pytest.fixture
def passage_goma(session_admin) -> Passage:
    """Passage à Goma du 17 au 30 mai 2027 (publié)."""
    p = Passage(territoire_code="NKV-GOM", date_debut=date(2027, 5, 17),
                date_fin=date(2027, 5, 30), statut="publie")
    session_admin.add(p)
    session_admin.commit()
    return p


def abonner_goma(tel) -> list:
    territoires = tel.choisir(tel.toucher("passage"), "Nord-Kivu")
    [resultat] = tel.choisir(territoires, "Goma")
    assert resultat.boutons[0] == ("abonner:NKV-GOM", "Prévenez-moi")
    return tel.toucher("abonner:NKV-GOM", liste=False)


def rappels(session_admin, quand: datetime) -> list[Modele]:
    avant = len(passerelle().derniers(NUMERO))
    from coeur.base import nouvelle_session
    with nouvelle_session() as session:
        abonnements.envoyer_rappels(session, parametres(), quand)
    return passerelle().derniers(NUMERO)[avant:]


def test_abonnement_avec_consentement_et_numero_chiffre(tel, passage_goma, session_admin):
    [ok] = abonner_goma(tel)
    assert ok.corps.startswith("C'est noté : vous serez prévenu avant le passage des agents à Goma.")
    abonnement = session_admin.scalar(select(Abonnement))
    assert dechiffrer_numero(abonnement.numero_chiffre) == NUMERO
    contenu = session_admin.execute(
        text("SELECT string_agg(t::text, ' ') FROM coeur.abonnements_whatsapp t")).scalar()
    assert "812345678" not in contenu
    [deja] = tel.toucher("abonner:NKV-GOM", liste=False)
    assert deja.corps.startswith("Vous êtes déjà prévenu pour Goma")


def test_abonnement_possible_avant_la_publication_des_dates(tel, session_admin):
    [ok] = abonner_goma(tel)
    assert ok.corps.startswith("C'est noté")


def test_trois_territoires_au_plus(tel, session_admin):
    for code in ("KIN-V", "KCE-MAT", "NKV-BEN"):
        tel.toucher(f"abonner:{code}", liste=False)
    [refus] = tel.toucher("abonner:NKV-GOM", liste=False)
    assert refus.corps.startswith("Vous suivez déjà 3 territoires")
    assert session_admin.scalar(select(func.count()).select_from(Abonnement)) == 3


def test_rappel_trois_jours_avant_puis_la_veille(tel, passage_goma, session_admin):
    abonner_goma(tel)
    assert rappels(session_admin, a(date(2027, 5, 13))) == []           # J-4 : rien
    [j3] = rappels(session_admin, a(date(2027, 5, 14)))                  # J-3
    assert (j3.nom, j3.langue, j3.parametres) == ("rappel_passage", "fr",
                                                  ["Goma", "17/05/2027", "30/05/2027"])
    assert rappels(session_admin, a(date(2027, 5, 14), 15)) == []       # pas deux fois
    assert rappels(session_admin, a(date(2027, 5, 15))) == []           # J-2 : rien
    [veille] = rappels(session_admin, a(date(2027, 5, 16)))              # la veille
    assert veille.parametres[0] == "Goma"
    assert rappels(session_admin, a(date(2027, 5, 17))) == []           # passage commencé
    assert session_admin.scalar(select(func.count()).select_from(MessageWhatsapp).where(
        MessageWhatsapp.categorie == "modele")) == 2


def test_jamais_la_nuit(tel, passage_goma, session_admin):
    abonner_goma(tel)
    assert rappels(session_admin, a(date(2027, 5, 14), 6)) == []
    assert rappels(session_admin, a(date(2027, 5, 14), 21)) == []
    assert len(rappels(session_admin, a(date(2027, 5, 14), 8))) == 1


def test_abonnement_tardif_un_seul_rappel_par_jour(tel, passage_goma, session_admin):
    abonner_goma(tel)
    [rappel] = rappels(session_admin, a(date(2027, 5, 16)))  # abonné la veille seulement
    assert rappels(session_admin, a(date(2027, 5, 16), 17)) == []
    assert rappel.parametres[1] == "17/05/2027"


def test_langue_du_modele(client, passage_goma, session_admin):
    t = Telephone(client)
    t.ecrire("Bonjour")
    t.toucher("langue:ln")
    t.toucher("abonner:NKV-GOM", liste=False)
    [rappel] = rappels(session_admin, a(date(2027, 5, 14)))
    assert rappel.langue == "fr"  # Meta ne propose pas de modèle en lingala


def test_stop_efface_abonnements_et_numero(tel, passage_goma, session_admin):
    abonner_goma(tel)
    tel.toucher("abonner:KIN-V", liste=False)
    [ok] = tel.ecrire("STOP")
    assert ok.corps == "Vos rappels sont arrêtés et votre numéro est effacé de la liste."
    assert session_admin.scalar(select(func.count()).select_from(Abonnement)) == 0
    [rien] = tel.toucher("stop", liste=False)  # bouton « Arrêter » du modèle
    assert rien.corps == "Vous n'avez aucun rappel en cours."
    assert rappels(session_admin, a(date(2027, 5, 14))) == []


def test_expiration_apres_le_passage(tel, passage_goma, session_admin):
    abonner_goma(tel)
    from coeur.base import nouvelle_session
    with nouvelle_session() as session:
        assert abonnements.expirer(session, parametres(), date(2027, 6, 6)) == 0  # fin + 7 j
        assert abonnements.expirer(session, parametres(), date(2027, 6, 7)) == 1
    assert session_admin.scalar(select(func.count()).select_from(Abonnement)) == 0


def test_charge_utile_du_modele():
    from coeur.whatsapp.messages import charge_utile
    corps = charge_utile(NUMERO, Modele("rappel_passage", "fr", ["Goma", "17/05/2027", "30/05/2027"]))
    assert corps["type"] == "template"
    assert corps["template"]["name"] == "rappel_passage"
    assert corps["template"]["components"][0]["parameters"][0] == {"type": "text", "text": "Goma"}
    assert corps["template"]["components"][1]["parameters"] == [{"type": "payload", "payload": "stop"}]


def test_tableau_de_bord(client, tel, passage_goma, session_admin):
    from coeur.tableau_de_bord.auth import Utilisateur, authentificateur
    from coeur.main import app

    class Auth:
        def verifier(self, email, mdp):
            return Utilisateur(email=email, role="Administrator")

    app.dependency_overrides[authentificateur] = Auth
    try:
        client.post("/tableau-de-bord/connexion", data={"email": "a@b.cd", "mdp": "x"})
        html = client.get("/tableau-de-bord").text
    finally:
        app.dependency_overrides.pop(authentificateur, None)
    assert "<h2 class=\"section\">WhatsApp</h2>" in html
    assert "abonnés aux rappels" in html
