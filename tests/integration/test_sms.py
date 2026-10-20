"""Canal SMS de bout en bout : Kannel transmet le SMS reçu, la réponse part par la passerelle."""

import pytest
from sqlalchemy import func, select

from coeur.calendrier.modeles import Passage
from coeur.centre_appels.modeles import Rappel
from coeur.config import parametres
from coeur.interactions.modeles import Interaction
from coeur.mobile.modeles import Consultation, MessageSms
from coeur.signalements.modeles import Signalement
from coeur.sms.passerelle import passerelle
from tests.integration.conftest import USSD, WEB

NUMERO = "+243 81 234 5678"
INTERNATIONAL = "243812345678"
CLE_SMS = "cle-sms-test"


@pytest.fixture(autouse=True)
def canal_sms(monkeypatch):
    reglages = parametres()
    monkeypatch.setattr(reglages, "cles_api", reglages.cles_api + f",sms:{CLE_SMS}")


def sms(client, texte: str, de: str = NUMERO) -> str | None:
    """Envoie un SMS au cœur comme Kannel (GET, clé dans l'adresse) ; renvoie la réponse."""
    avant = len(passerelle().messages)
    r = client.get("/v1/sms/entrant", params={"cle": CLE_SMS, "de": de, "texte": texte})
    assert r.status_code == 200 and r.text == ""
    nouveaux = list(passerelle().messages)[avant:]
    assert len(nouveaux) <= 1
    return nouveaux[0][1] if nouveaux else None


def compter(session, modele, *conditions):
    return session.scalar(select(func.count()).select_from(modele).where(*conditions))


def test_reserve_a_la_passerelle_sms(client):
    params = {"de": NUMERO, "texte": "AIDE"}
    assert client.get("/v1/sms/entrant", params=params).status_code == 401
    assert client.get("/v1/sms/entrant", params=params, headers=WEB).status_code == 403
    assert client.get("/v1/sms/entrant", params={**params, "cle": USSD["X-Cle-API"]}).status_code == 403


def test_aide(client):
    reponse = sms(client, "aide")
    assert reponse.startswith("RGPH-2 : envoyez votre question, ou AGENT + badge")
    assert "(fr, ln, sw, kg, lua)" in reponse
    assert passerelle().messages[-1][0] == INTERNATIONAL


def test_question_avec_reponse_validee(client, exemples, session_admin):
    reponse = sms(client, "Comment reconnaitre un vrai agent recenseur ?")
    assert reponse.startswith("[EXEMPLE non validé] Un agent recenseur porte un badge officiel")
    interaction = session_admin.scalar(select(Interaction))
    assert (interaction.canal, interaction.resultat) == ("sms", "reponse")
    assert interaction.usager_empreinte is not None


def test_question_sans_reponse_validee(client, exemples, session_admin):
    reponse = sms(client, "Combien coûte un sac de ciment à Kisangani ?")
    assert reponse == ("Pas de réponse validée à votre question. Appelez le 0800 000 000 "
                       "(gratuit) ou envoyez RAPPEL pour etre rappelé.")  # alphabet GSM
    assert session_admin.scalar(select(Interaction.resultat)) == "escalade"


def test_reponse_longue_remplacee_par_la_version_courte(client, exemples, session_admin,
                                                         monkeypatch):
    monkeypatch.setattr(parametres(), "sms_segments_max", 1)
    reponse = sms(client, "Comment reconnaitre un vrai agent recenseur ?")
    assert reponse == ("Un vrai agent porte un badge officiel avec photo et numéro, "
                       "vérifiable par SMS.")


def test_verifier_un_badge(client, badges, session_admin):
    assert sms(client, "agent ab-1234").startswith("Badge AB1234 VALIDE")
    reponse = sms(client, "AGENT ZZ 0000")
    assert reponse.startswith("Badge ZZ0000 INCONNU.")
    assert "FAUXAGENT GOMA ZZ0000" in reponse
    assert sms(client, "AGENT") == "Envoyez AGENT suivi du numéro du badge. Exemple : AGENT AB1234"
    assert sorted(session_admin.scalars(select(Consultation.resultat))) == ["inconnu", "valide"]


def test_phrase_commencant_par_un_mot_cle_traitee_comme_question(client, exemples, badges,
                                                                  session_admin):
    reponse = sms(client, "Agent recenseur faux que faire")
    assert not reponse.startswith("Badge")
    assert compter(session_admin, Consultation) == 0
    assert compter(session_admin, Interaction) == 1


def test_date_de_passage(client, session_admin):
    session_admin.add(Passage(territoire_code="KIN-V", date_debut="2027-05-10",
                              date_fin="2027-06-20", statut="publie"))
    session_admin.commit()
    assert sms(client, "PASSAGE Kinshasa") == (
        "Passage des agents à Ville de Kinshasa : du 10/05/2027 au 20/06/2027.")
    assert sms(client, "passage goma").startswith("Les dates de passage à Goma ne sont pas")
    assert sms(client, "PASSAGE Lisala") == "Territoire introuvable. Exemple : PASSAGE GOMA"


def test_menage_non_recense(client, session_admin):
    reponse = sms(client, "nonvisite Goma Himbi 2")
    assert reponse.startswith("Merci. Signalement 1 enregistré")
    s = session_admin.scalar(select(Signalement))
    assert (s.type, s.canal, s.territoire_code, s.localite) == (
        "menage_non_visite", "sms", "NKV-GOM", "Himbi 2")
    assert sms(client, "NONVISITE") == "Territoire introuvable. Exemple : NONVISITE GOMA"


def test_signaler_un_faux_agent(client, session_admin):
    sms(client, "FAUXAGENT Mbanza-Ngungu zz0000")
    s = session_admin.scalar(select(Signalement))
    assert (s.type, s.territoire_code, s.description) == (
        "agent_douteux", "KCE-MBZ", "Badge présenté : ZZ0000")


def test_demande_de_rappel(client, session_admin):
    assert sms(client, "RAPPEL").startswith("Demande enregistrée.")
    assert sms(client, "rappel").startswith("Votre demande de rappel est déjà enregistrée")
    rappel = session_admin.scalar(select(Rappel))
    assert (rappel.origine, rappel.statut) == ("sms", "a_rappeler")


def test_changer_de_langue(client):
    assert sms(client, "LANGUE ln") == "Lokota ekomami : Lingala."  # dans la nouvelle langue
    assert sms(client, "aide").startswith("RGPH-2 : tinda motuna na yo")
    assert sms(client, "LANGUE klingon").startswith("Lokota eyebani te. Ba code : fr, ln")
    assert sms(client, "langue francais") == "Langue enregistrée : Francais."
    assert sms(client, "Langue KISWAHILI").startswith("Langue enregistrée : Kiswahili")


def test_plafond_de_sms_par_jour(client, session_admin, monkeypatch):
    monkeypatch.setattr(parametres(), "sms_reponses_par_jour", 2)
    assert sms(client, "aide") is not None
    assert sms(client, "aide") is not None
    assert sms(client, "aide") is None
    assert sms(client, "aide", de="0899999999") is not None  # un autre numéro
    statuts = session_admin.execute(
        select(MessageSms.sens, MessageSms.statut, func.count())
        .group_by(MessageSms.sens, MessageSms.statut)).all()
    assert sorted(statuts) == [("entrant", "recu", 4), ("sortant", "envoye", 3),
                               ("sortant", "plafond", 1)]


def test_expediteur_qui_n_est_pas_un_numero_ignore(client, session_admin):
    assert sms(client, "Votre forfait expire demain", de="VODACOM") is None
    assert compter(session_admin, MessageSms) == 0


def test_reponse_dans_l_alphabet_gsm(client, monkeypatch):
    monkeypatch.setattr(parametres(), "numero_vert", "")
    reponse = sms(client, "Où se trouve la côte ?")
    assert "ê" not in reponse and "être" not in reponse and "etre" in reponse
