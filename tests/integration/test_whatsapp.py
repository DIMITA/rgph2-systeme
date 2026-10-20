"""Canal WhatsApp de bout en bout : notifications signées de Meta, réponses par la passerelle."""

import hashlib
import hmac
import itertools
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text, update

from coeur.calendrier.modeles import Passage
from coeur.centre_appels.modeles import Rappel
from coeur.connaissances.modeles import Traduction
from coeur.interactions.modeles import Interaction
from coeur.mobile.modeles import PreferenceLangue
from coeur.signalements.modeles import Signalement
from coeur.whatsapp.messages import Boutons, Liste, Texte
from coeur.whatsapp.modeles import Conversation, MessageWhatsapp
from coeur.whatsapp.passerelle import passerelle

SECRET = "secret-app-whatsapp-test"
NUMERO = "243812345678"
COMPTEUR = itertools.count()


def signer(corps: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()


def notification(messages: list[dict]) -> bytes:
    return json.dumps({"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [
        {"field": "messages", "value": {"messaging_product": "whatsapp", "messages": messages}}]}]}
    ).encode()


class Telephone:
    """Un citoyen sur WhatsApp : il écrit ou touche des boutons ; on lit les réponses."""

    def __init__(self, client, numero: str = NUMERO):
        self.client, self.numero = client, numero

    def envoyer(self, message: dict) -> list:
        avant = len(passerelle().derniers(self.numero))
        message = {"from": self.numero, "id": f"wamid.{next(COMPTEUR)}",
                   "timestamp": "1760000000", **message}
        corps = notification([message])
        r = self.client.post("/v1/whatsapp/webhook", content=corps,
                             headers={"X-Hub-Signature-256": signer(corps),
                                      "Content-Type": "application/json"})
        assert r.status_code == 200, r.text
        return passerelle().derniers(self.numero)[avant:]

    def ecrire(self, texte: str) -> list:
        return self.envoyer({"type": "text", "text": {"body": texte}})

    def toucher(self, identifiant: str, liste: bool = True) -> list:
        cle = "list_reply" if liste else "button_reply"
        return self.envoyer({"type": "interactive", "interactive": {
            "type": cle, cle: {"id": identifiant, "title": "x"}}})

    def choisir(self, reponses: list, libelle: str) -> list:
        """Touche la ligne ou le bouton portant ce libellé, en suivant « Suite de la liste »."""
        for _ in range(10):
            dernier = reponses[-1]
            options = ([(l.id, l.titre) for l in dernier.lignes] if isinstance(dernier, Liste)
                       else [(i, t) for i, t in dernier.boutons])
            for identifiant, titre in options:
                if titre == libelle:
                    return self.toucher(identifiant)
            suite = [i for i, t in options if t == "Suite de la liste"]
            assert suite, f"« {libelle} » absent de {options}"
            reponses = self.toucher(suite[0])
        raise AssertionError(libelle)


@pytest.fixture
def tel(client):
    """Citoyen dont la langue est déjà choisie (français)."""
    t = Telephone(client)
    t.ecrire("Bonjour")
    t.toucher("langue:fr")
    return t


def compter(session, modele, *conditions):
    return session.scalar(select(func.count()).select_from(modele).where(*conditions))


# --- Webhook -----------------------------------------------------------------------------------

def test_verification_de_l_abonnement(client):
    params = {"hub.mode": "subscribe", "hub.verify_token": "jeton-verification-test",
              "hub.challenge": "1158201444"}
    r = client.get("/v1/whatsapp/webhook", params=params)
    assert (r.status_code, r.text) == (200, "1158201444")
    r = client.get("/v1/whatsapp/webhook", params={**params, "hub.verify_token": "faux"})
    assert r.status_code == 403


def test_notification_non_signee_ou_mal_signee_refusee(client, session_admin):
    corps = notification([{"from": NUMERO, "id": "w1", "type": "text", "text": {"body": "Bonjour"}}])
    assert client.post("/v1/whatsapp/webhook", content=corps).status_code == 401
    r = client.post("/v1/whatsapp/webhook", content=corps,
                    headers={"X-Hub-Signature-256": signer(corps, "autre-secret")})
    assert r.status_code == 401
    r = client.post("/v1/whatsapp/webhook", content=corps + b" ",
                    headers={"X-Hub-Signature-256": signer(corps)})  # corps modifié
    assert r.status_code == 401
    assert passerelle().derniers(NUMERO) == []
    assert compter(session_admin, MessageWhatsapp) == 0


def test_accuses_de_lecture_ignores(client):
    corps = json.dumps({"entry": [{"changes": [{"value": {"statuses": [
        {"id": "w", "status": "read", "recipient_id": NUMERO}]}}]}]}).encode()
    r = client.post("/v1/whatsapp/webhook", content=corps,
                    headers={"X-Hub-Signature-256": signer(corps)})
    assert r.json() == {"traites": 0}


def test_notification_repetee_traitee_une_seule_fois(client, session_admin):
    message = {"from": NUMERO, "id": "wamid.unique", "type": "text", "text": {"body": "Bonjour"}}
    corps = notification([message])
    for _ in range(2):
        client.post("/v1/whatsapp/webhook", content=corps,
                    headers={"X-Hub-Signature-256": signer(corps)})
    assert compter(session_admin, MessageWhatsapp, MessageWhatsapp.sens == "entrant") == 1


# --- Conversation ------------------------------------------------------------------------------

def test_premier_contact_puis_langue_retenue(client, session_admin):
    t = Telephone(client)
    [accueil] = t.ecrire("Bonjour")
    assert isinstance(accueil, Liste)
    assert accueil.corps.startswith("Bienvenue sur le service officiel du recensement")
    assert [l.id for l in accueil.lignes] == ["langue:fr", "langue:ln", "langue:sw", "langue:kg",
                                             "langue:lua"]
    [menu] = t.toucher("langue:ln")
    assert menu.bouton == "Menu" and menu.lignes[0].titre == "Mituna oyo batunaka mingi"
    assert session_admin.scalar(select(PreferenceLangue.langue)) == "ln"


def test_question_du_premier_message_traitee_apres_le_choix_de_la_langue(
        client, exemples, session_admin):
    t = Telephone(client)
    [accueil] = t.ecrire("Comment reconnaître un vrai agent recenseur ? Mon numéro : 0812345678")
    assert isinstance(accueil, Liste) and accueil.lignes[0].id == "langue:fr"
    # Gardée masquée le temps du choix de la langue.
    assert "0812345678" not in str(session_admin.scalar(select(Conversation.contexte)))
    texte, _menu = t.toucher("langue:fr")
    assert "badge officiel avec sa photo" in texte.corps
    assert session_admin.scalar(select(Interaction.resultat)) == "reponse"
    session_admin.expire_all()
    assert session_admin.scalar(select(Conversation.attente)) is None
    # Ensuite, un changement de langue ramène simplement au menu.
    [menu] = t.toucher("langue:ln")
    assert isinstance(menu, Liste) and menu.bouton == "Menu"


def test_langue_choisie_par_ussd_reprise_sur_whatsapp(client, session_admin):
    session_admin.add(PreferenceLangue(usager_empreinte=_empreinte(), langue="ln"))
    session_admin.commit()
    [menu] = Telephone(client).ecrire("Mbote")
    assert menu.corps.startswith("Boyei malamu")


def _empreinte() -> str:
    from coeur.confidentialite.service import empreinte_telephone
    from tests.conftest import PEPPER
    return empreinte_telephone(NUMERO, PEPPER)


def test_question_de_la_faq_avec_audio_et_video(tel, exemples, session_admin):
    session_admin.execute(update(Traduction).where(
        Traduction.contenu_id == exemples["exemple-confidentialite"]).values(
        audio_url="https://medias.rgph.cd/conf-fr.mp3", video_url="https://medias.rgph.cd/conf.mp4"))
    session_admin.commit()
    liste = tel.toucher("faq")
    reponses = tel.choisir(liste, "Mes réponses au recensement sont-elles confidentielles ?")
    texte, audio, video, menu = reponses
    assert isinstance(texte, Texte)
    assert texte.corps.startswith("*Mes réponses au recensement sont-elles confidentielles ?*")
    assert "Réponse officielle du Bureau central du recensement" in texte.corps
    assert "Oui. Vos réponses sont protégées par la loi" in texte.corps  # réponse complète
    assert (audio.type, audio.lien) == ("audio", "https://medias.rgph.cd/conf-fr.mp3")
    assert (video.type, video.lien) == ("video", "https://medias.rgph.cd/conf.mp4")
    assert isinstance(menu, Boutons) and menu.boutons == [("menu", "Menu")]
    interaction = session_admin.scalar(select(Interaction))
    assert (interaction.canal, interaction.contenu_id) == ("whatsapp", exemples["exemple-confidentialite"])


def test_question_libre(tel, exemples, session_admin):
    texte, _menu = tel.ecrire("Comment reconnaître un vrai agent recenseur ?")
    assert "badge officiel avec sa photo" in texte.corps
    [escalade] = tel.ecrire("Quel temps fera-t-il demain à Kisangani ?")
    assert escalade.corps.startswith("Pas de réponse validée à votre question. Appelez gratuitement")
    assert escalade.boutons[0] == ("rappel", "Être rappelé")
    assert sorted(session_admin.scalars(select(Interaction.resultat))) == ["escalade", "reponse"]


def test_mots_cles_comme_par_sms(tel, badges):
    [reponse] = tel.ecrire("AGENT AB1234")
    assert reponse.corps.startswith("Badge AB1234 VALIDE")


def test_date_de_passage_par_les_listes(tel, session_admin):
    session_admin.add(Passage(territoire_code="NKV-GOM", date_debut="2027-05-17",
                              date_fin="2027-06-06", statut="publie"))
    session_admin.commit()
    provinces = tel.toucher("passage")
    assert len(provinces[0].lignes) == 10 and provinces[0].lignes[-1].titre == "Suite de la liste"
    territoires = tel.choisir(provinces, "Nord-Kivu")
    [resultat] = tel.choisir(territoires, "Goma")
    assert resultat.corps == "Passage des agents à Goma : du 17/05/2027 au 06/06/2027."


def test_verifier_un_badge_puis_signaler_un_faux_agent(tel, badges, session_admin):
    [consigne] = tel.toucher("badge")
    assert consigne.corps.startswith("Tapez le numéro inscrit sur le badge")
    [erreur] = tel.ecrire("A!")
    assert erreur.corps.startswith("Numéro de badge non valide")
    [inconnu] = tel.ecrire("zz-0000")
    assert inconnu.corps.startswith("Badge ZZ0000 INCONNU")
    provinces = tel.toucher("faux:ZZ0000", liste=False)
    territoires = tel.choisir(provinces, "Nord-Kivu")
    [confirmation] = tel.choisir(territoires, "Goma")
    assert confirmation.corps == "Signaler un faux agent à Goma ?"
    [merci] = tel.toucher("confirmer", liste=False)
    assert merci.corps.startswith("Merci. Signalement 1 enregistré")
    s = session_admin.scalar(select(Signalement))
    assert (s.type, s.canal, s.territoire_code, s.description) == (
        "agent_douteux", "whatsapp", "NKV-GOM", "Badge présenté : ZZ0000")


def test_menage_non_recense_avec_quartier(tel, session_admin):
    territoires = tel.choisir(tel.toucher("nonvisite"), "Kinshasa")
    [consigne] = tel.choisir(territoires, "Ville de Kinshasa")
    assert consigne.boutons == [("passer", "Passer")]
    [confirmation] = tel.ecrire("Limete, 7e rue")
    assert confirmation.corps == "Signaler un ménage non recensé à Ville de Kinshasa, Limete, 7e rue ?"
    tel.toucher("confirmer", liste=False)
    s = session_admin.scalar(select(Signalement))
    assert (s.type, s.localite) == ("menage_non_visite", "Limete, 7e rue")
    assert session_admin.scalar(select(Conversation.attente)) is None


def test_menage_non_recense_sans_quartier(tel, session_admin):
    territoires = tel.choisir(tel.toucher("nonvisite"), "Kinshasa")
    tel.choisir(territoires, "Ville de Kinshasa")
    [confirmation] = tel.toucher("passer", liste=False)
    assert confirmation.corps == "Signaler un ménage non recensé à Ville de Kinshasa ?"
    tel.toucher("confirmer", liste=False)
    assert session_admin.scalar(select(Signalement.localite)) is None


def test_confirmation_trop_tardive(tel, session_admin):
    territoires = tel.choisir(tel.toucher("nonvisite"), "Kinshasa")
    tel.choisir(territoires, "Ville de Kinshasa")
    tel.toucher("passer", liste=False)
    session_admin.execute(update(Conversation).values(
        maj_a=datetime.now(timezone.utc) - timedelta(hours=2)))
    session_admin.commit()
    [menu] = tel.toucher("confirmer", liste=False)
    assert menu.corps.startswith("Votre précédente demande a expiré")
    assert compter(session_admin, Signalement) == 0


def test_demande_de_rappel(tel, session_admin):
    [conseiller] = tel.toucher("conseiller")
    assert conseiller.corps.startswith("Appelez gratuitement le 0800 000 000")
    [ok] = tel.toucher("rappel", liste=False)
    assert ok.corps.startswith("Demande enregistrée")
    assert session_admin.scalar(select(Rappel.origine)) == "whatsapp"


def test_message_vocal_ou_image(tel):
    [menu] = tel.envoyer({"type": "audio", "audio": {"id": "123", "mime_type": "audio/ogg"}})
    assert menu.corps.startswith("Je ne lis que les messages écrits")


def test_journal_sans_texte_ni_numero(tel, exemples, session_admin):
    tel.ecrire("Comment reconnaître un vrai agent recenseur ?")
    for table in ("coeur.whatsapp_messages", "coeur.conversations_whatsapp", "coeur.interactions",
                  "coeur.preferences_langue"):
        contenu = session_admin.execute(
            text(f"SELECT coalesce(string_agg(t::text, ' '), '') FROM {table} t")).scalar()
        assert "812345678" not in contenu, table
    assert compter(session_admin, MessageWhatsapp, MessageWhatsapp.sens == "entrant") == 3
    assert compter(session_admin, MessageWhatsapp, MessageWhatsapp.sens == "sortant",
                   MessageWhatsapp.categorie == "service") >= 4
