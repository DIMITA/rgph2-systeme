"""Canal USSD de bout en bout : la passerelle envoie la saisie cumulée, le cœur répond un écran."""

import re

import pytest
from sqlalchemy import func, select, text

from coeur.calendrier.modeles import Passage
from coeur.centre_appels.modeles import Rappel
from coeur.centre_appels.service import dechiffrer_numero
from coeur.interactions.modeles import Interaction
from coeur.mobile.gsm import en_gsm
from coeur.mobile.modeles import Consultation, PreferenceLangue
from coeur.signalements.modeles import Signalement
from coeur.sms.passerelle import passerelle
from tests.integration.conftest import USSD, WEB

NUMERO = "0812345678"
INTERNATIONAL = "243812345678"


def compter(session, modele, *conditions):
    return session.scalar(select(func.count()).select_from(modele).where(*conditions))


class Telephone:
    """Un téléphone qui compose le code USSD et tape des réponses, comme un citoyen."""

    def __init__(self, client, numero=NUMERO, session="s1"):
        self.client, self.numero, self.session = client, numero, session
        self.saisies: list[str] = []
        self.ecran = ""

    def envoyer(self, texte: str) -> str:
        r = self.client.post("/v1/ussd", headers=USSD, data={
            "sessionId": self.session, "phoneNumber": self.numero, "text": texte,
            "serviceCode": "*123#"})
        assert r.status_code == 200, r.text
        assert r.text.startswith(("CON ", "END "))
        assert len(r.text) - 4 <= 182
        return r.text

    def composer(self) -> str:
        """Chaque composition du code ouvre une nouvelle session USSD."""
        self.nb_sessions = getattr(self, "nb_sessions", 0) + 1
        self.session = f"{self.session.split('#')[0]}#{self.nb_sessions}"
        self.saisies, self.ecran = [], self.envoyer("")
        return self.ecran

    def taper(self, saisie: str) -> str:
        self.saisies.append(saisie)
        self.ecran = self.envoyer("*".join(self.saisies))
        return self.ecran

    def choisir(self, libelle: str) -> str:
        """Tape le numéro de l'option portant ce libellé, en tournant les pages (98)."""
        libelle = en_gsm(libelle)  # « Français » s'affiche « Francais » (alphabet GSM)
        for _ in range(10):
            trouve = re.search(rf"^(\d+) {re.escape(libelle)}", self.ecran[4:], re.MULTILINE)
            if trouve:
                return self.taper(trouve.group(1))
            assert "\n98 " in self.ecran, f"« {libelle} » introuvable dans :\n{self.ecran}"
            self.taper("98")
        raise AssertionError(libelle)


@pytest.fixture
def tel(client):
    return Telephone(client)


@pytest.fixture
def francais(tel):
    """Téléphone dont la langue est déjà choisie (français)."""
    tel.composer()
    tel.choisir("Français")
    return tel


@pytest.fixture
def calendrier(session_admin):
    session_admin.add_all([
        Passage(territoire_code="NKV-GOM", date_debut="2027-05-17", date_fin="2027-06-06",
                statut="publie"),
        Passage(territoire_code="NKV-BEN", date_debut="2027-05-17", date_fin="2027-06-06",
                statut="brouillon"),
    ])
    session_admin.commit()


def test_reserve_a_la_passerelle_ussd(client):
    donnees = {"sessionId": "s", "phoneNumber": NUMERO, "text": ""}
    assert client.post("/v1/ussd", data=donnees).status_code == 401
    assert client.post("/v1/ussd", data=donnees, headers=WEB).status_code == 403
    # Clé dans l'adresse, pour les passerelles qui ne savent pas ajouter d'en-tête.
    assert client.post(f"/v1/ussd?cle={USSD['X-Cle-API']}", data=donnees).status_code == 200


def test_premier_contact_choix_de_la_langue_puis_memorisee(client, tel, session_admin):
    ecran = tel.composer()
    assert ecran.startswith("CON RGPH-2 Recensement. Choisissez votre langue :\n1 Fran")
    assert "2 Lingala" in ecran
    ecran = tel.choisir("Lingala")
    assert ecran.startswith("CON RGPH-2 Botangi bato\n1 Mituna")
    assert session_admin.scalar(select(PreferenceLangue.langue)) == "ln"

    # Nouvelle session : la langue n'est plus demandée.
    autre = Telephone(client, session="s2")
    assert autre.composer().startswith("CON RGPH-2 Botangi bato")
    autre.choisir("Bongola lokota")
    assert autre.choisir("Français").startswith("CON RGPH-2 Recensement\n1 Questions")


def test_changer_de_langue_en_cours_de_session(francais, session_admin):
    francais.choisir("Changer de langue")
    assert francais.choisir("Lingala").startswith("CON RGPH-2 Botangi bato")
    # Les saisies suivantes rejouent le parcours : le changement doit y être retrouvé.
    assert "Koma nimero" in francais.choisir("Tala soki mosali azali ya solo")
    assert "Bongola lokota" in francais.taper("0")
    assert session_admin.scalar(select(PreferenceLangue.langue)) == "ln"


def test_choix_invalide_et_retour(francais):
    ecran = francais.taper("7")
    assert ecran.startswith("CON Choix invalide.\nRGPH-2 Recensement")
    francais.choisir("Vérifier un agent")
    ecran = francais.taper("0")
    assert ecran.startswith("CON RGPH-2 Recensement\n1 Questions")


def test_question_reponse_courte_puis_detail_par_sms(francais, exemples, session_admin):
    francais.choisir("Questions fréquentes")
    ecran = francais.choisir("Mes réponses au recensement")
    assert "Oui, vos réponses sont confidentielles" in ecran
    assert "\n1 Détail par SMS" in ecran
    lectures = session_admin.scalars(select(Interaction).where(Interaction.canal == "ussd")).all()
    assert [(i.resultat, i.contenu_id) for i in lectures] == [
        ("reponse", exemples["exemple-confidentialite"])]
    assert lectures[0].usager_empreinte is not None

    ecran = francais.taper("1")
    assert ecran == "END Le détail vous est envoyé par SMS."
    (sms,) = passerelle().derniers(INTERNATIONAL)
    assert sms.startswith("[EXEMPLE non validé] Oui. Vos réponses sont protégées")
    # Revenir à la liste ne compte pas une seconde lecture.
    assert compter(session_admin, Interaction) == 1


def test_question_sans_reponse_courte_absente(francais, exemples, session_admin):
    from coeur.connaissances.modeles import Traduction
    session_admin.query(Traduction).filter(
        Traduction.contenu_id == exemples["exemple-confidentialite"]).update({"reponse_courte": None})
    session_admin.commit()
    ecran = francais.choisir("Questions fréquentes")
    assert "confidentielles" not in ecran and "Mes réponses" not in ecran


def test_date_de_passage(francais, calendrier, session_admin):
    francais.choisir("Date de passage des agents")
    francais.choisir("Nord-Kivu")
    ecran = francais.choisir("Goma")
    assert ecran == "END Passage des agents à Goma : du 17/05/2027 au 06/06/2027."

    francais.composer()
    francais.choisir("Date de passage des agents")
    francais.choisir("Nord-Kivu")
    ecran = francais.choisir("Beni")  # période en brouillon : pas servie
    assert ecran.startswith("END Les dates de passage à Beni ne sont pas encore publiées")
    assert sorted(session_admin.execute(
        select(Consultation.resultat, Consultation.territoire_code, Consultation.canal))) == [
        ("non_publie", "NKV-BEN", "ussd"), ("trouve", "NKV-GOM", "ussd")]


def test_liste_paginee_des_provinces(francais):
    ecran = francais.choisir("Date de passage des agents")
    assert "\n98 Suite" in ecran and ecran.endswith("\n0 Retour")
    francais.choisir("Tanganyika")  # sur une page suivante
    assert "Kalemie" in francais.ecran


def test_badge_valide_retire_inconnu(francais, badges, session_admin):
    francais.choisir("Vérifier un agent")
    assert francais.taper("ab-1234").startswith(
        "END Badge AB1234 VALIDE : agent du recensement affecté à Goma.")

    francais.composer()
    francais.choisir("Vérifier un agent")
    assert francais.taper("XY9999").startswith("END Badge XY9999 RETIRÉ")

    francais.composer()
    francais.choisir("Vérifier un agent")
    ecran = francais.taper("ZZ0000")
    assert ecran.startswith("CON Badge ZZ0000 INCONNU.")
    francais.choisir("Signaler cet agent")
    francais.choisir("Nord-Kivu")
    ecran = francais.choisir("Goma")
    assert ecran.startswith("CON Signaler un faux agent à Goma ?\n1 Confirmer")
    ecran = francais.taper("1")
    assert re.match(r"END Merci\. Signalement \d+ enregistré", ecran)

    signalement = session_admin.scalar(select(Signalement))
    assert (signalement.type, signalement.canal, signalement.territoire_code,
            signalement.description) == ("agent_douteux", "ussd", "NKV-GOM",
                                         "Badge présenté : ZZ0000")
    # Chaque badge vérifié une seule fois, même si la saisie est rejouée à chaque écran.
    assert sorted(session_admin.scalars(select(Consultation.resultat))) == [
        "inconnu", "retire", "valide"]


def test_badge_mal_saisi(francais):
    francais.choisir("Vérifier un agent")
    ecran = francais.taper("A*")
    assert ecran.startswith("CON Numéro de badge non valide.")
    assert "Tapez le numéro inscrit" in ecran


def test_verifications_de_badge_plafonnees(client, badges):
    for i in range(10):
        tel = Telephone(client, session=f"b{i}")
        tel.composer()
        if i == 0:
            tel.choisir("Français")
            tel.composer()
        tel.choisir("Vérifier un agent")
        assert "INCONNU" in tel.taper(f"QQ{i:04d}")
    tel = Telephone(client, session="b10")
    tel.composer()
    tel.choisir("Vérifier un agent")
    assert tel.taper("QQ9999") == "END Trop de vérifications. Réessayez dans une heure."
    # Un autre numéro n'est pas concerné.
    autre = Telephone(client, numero="0899999999", session="b11")
    autre.composer()
    autre.choisir("Français")
    autre.choisir("Vérifier un agent")
    assert "INCONNU" in autre.taper("QQ9999")


def test_menage_non_recense(francais, session_admin):
    francais.choisir("Ménage non recensé")
    francais.choisir("Nord-Kivu")
    francais.choisir("Goma")
    ecran = francais.taper("Himbi 2, 0997123456")
    assert ecran.startswith("CON Signaler un ménage non recensé à Goma, Himbi 2")
    francais.taper("1")
    signalement = session_admin.scalar(select(Signalement))
    assert (signalement.type, signalement.localite) == ("menage_non_visite", "Himbi 2, [masqué]")


def test_menage_non_recense_sans_quartier(francais, session_admin):
    francais.choisir("Ménage non recensé")
    francais.choisir("Kinshasa")
    francais.choisir("Ville de Kinshasa")
    assert "à Ville de Kinshasa ?" in francais.taper("1")
    francais.taper("1")
    assert session_admin.scalar(select(Signalement.localite)) is None


def test_requete_repetee_par_la_passerelle_sans_doublon(francais, session_admin):
    francais.choisir("Ménage non recensé")
    francais.choisir("Kinshasa")
    francais.choisir("Ville de Kinshasa")
    francais.taper("1")
    premier = francais.taper("1")
    assert francais.envoyer("*".join(francais.saisies)) == premier
    assert compter(session_admin, Signalement) == 1


def test_demande_de_rappel(client, francais, session_admin):
    ecran = francais.choisir("Parler à un conseiller")
    assert ecran.startswith("CON Appelez gratuitement le 0800 000 000")
    assert francais.choisir("Être rappelé").startswith("END Demande enregistrée.")
    rappel = session_admin.scalar(select(Rappel))
    assert (rappel.origine, rappel.langue, rappel.statut) == ("ussd", "fr", "a_rappeler")
    assert dechiffrer_numero(rappel.numero_chiffre) == INTERNATIONAL

    autre_session = Telephone(client, session="s9")
    autre_session.composer()
    autre_session.choisir("Parler à un conseiller")
    assert "déjà enregistrée" in autre_session.choisir("Être rappelé")
    assert compter(session_admin, Rappel) == 1


def test_aucun_numero_en_clair(francais, badges, session_admin):
    francais.choisir("Ménage non recensé")
    francais.choisir("Kinshasa")
    francais.choisir("Ville de Kinshasa")
    francais.taper("1")
    francais.taper("1")
    francais.composer()
    francais.choisir("Parler à un conseiller")
    francais.choisir("Être rappelé")
    for table in ("coeur.interactions", "coeur.signalements", "coeur.consultations",
                  "coeur.preferences_langue", "coeur.rappels"):
        contenu = session_admin.execute(
            text(f"SELECT coalesce(string_agg(t::text, ' '), '') FROM {table} t")).scalar()
        assert "812345678" not in contenu, table
