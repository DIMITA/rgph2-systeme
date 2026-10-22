"""Centre d'appels côté cœur : menu du SVI, événements d'appel, rappels, enregistrements."""

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select, text, update

from coeur.centre_appels import service
from coeur.centre_appels.modeles import Appel, Enregistrement, Rappel
from coeur.connaissances.modeles import Contenu, Traduction
from coeur.interactions.modeles import Interaction
from tests.conftest import CLE_CENTRE
from tests.integration.conftest import WEB

CENTRE = {"X-Cle-API": CLE_CENTRE}
NUMERO = "0812345678"


def evenement(client, **donnees):
    return client.post("/v1/appels/evenements", data=donnees, headers=CENTRE)


@pytest.fixture
def svi(session_admin, exemples):
    """Calendrier en 1er, vérification d'agent en 2e ; les autres exemples hors du menu."""
    session_admin.execute(update(Contenu).values(ordre_svi=None))
    for cle, ordre in (("exemple-calendrier-passage", 1), ("exemple-verifier-agent", 2)):
        session_admin.get(Contenu, exemples[cle]).ordre_svi = ordre
    session_admin.commit()
    return exemples


def compter(session, modele, *conditions):
    return session.scalar(select(func.count()).select_from(modele).where(*conditions))


# --- Accès -----------------------------------------------------------------------------

def test_reserve_au_canal_centre_ecoute(client, svi):
    assert client.get("/v1/appels/svi").status_code == 401
    assert client.get("/v1/appels/svi", headers=WEB).status_code == 403
    assert client.post("/v1/appels/evenements", data={"type": "debut", "appel": "a1"},
                       headers=WEB).status_code == 403


# --- Menu du SVI -----------------------------------------------------------------------

def test_menu_langues_dans_l_ordre_des_touches(client, svi):
    menu = client.get("/v1/appels/svi", headers=CENTRE).json()
    assert [(l["code"], l["touche"]) for l in menu["langues"]] == [
        ("fr", 1), ("ln", 2), ("sw", 3), ("kg", 4), ("lua", 5)]


def test_menu_ne_contient_que_les_contenus_publies_et_places(client, svi, session_admin):
    brouillon = Contenu(cle="brouillon-svi", statut="brouillon", ordre_svi=3)
    session_admin.add(brouillon)
    session_admin.flush()
    session_admin.add(Traduction(contenu_id=brouillon.id, langue_code="fr", statut="publie",
                                 question="Q ?", reponse="R"))
    session_admin.commit()
    fr = client.get("/v1/appels/svi", headers=CENTRE).json()["menus"]["fr"]
    assert [(i["touche"], i["cle"]) for i in fr] == [
        (1, "exemple-calendrier-passage"), (2, "exemple-verifier-agent")]
    assert fr[0]["question"].startswith("Quand les agents")
    assert fr[0]["repli_langue"] is False


def test_menu_repli_en_francais(client, svi):
    ln = client.get("/v1/appels/svi", headers=CENTRE).json()["menus"]["ln"]
    assert [i["langue"] for i in ln] == ["fr", "fr"]
    assert all(i["repli_langue"] for i in ln)


def test_menu_limite_a_huit_touches(client, session_admin):
    for n in range(1, 9):
        c = Contenu(cle=f"c{n}", statut="publie", ordre_svi=n)
        session_admin.add(c)
        session_admin.flush()
        session_admin.add(Traduction(contenu_id=c.id, langue_code="fr", statut="publie",
                                     question=f"Q{n}", reponse="R"))
    session_admin.commit()
    fr = client.get("/v1/appels/svi", headers=CENTRE).json()["menus"]["fr"]
    assert [i["touche"] for i in fr] == list(range(1, 9))


# --- Événements ------------------------------------------------------------------------

def test_debut_d_appel_sans_numero_en_clair(client, session_admin):
    assert evenement(client, type="debut", appel="1700000000.1", numero=NUMERO).status_code == 200
    evenement(client, type="debut", appel="1700000000.1", numero=NUMERO)  # répété : sans effet
    appel = session_admin.scalars(select(Appel)).one()
    assert len(appel.usager_empreinte) == 64
    ligne = session_admin.execute(text("SELECT row_to_json(a)::text FROM coeur.appels a")).scalar()
    assert "812345678" not in ligne


def test_numero_masque_accepte(client, session_admin):
    assert evenement(client, type="debut", appel="a1", numero="anonymous").status_code == 200
    assert session_admin.scalars(select(Appel)).one().usager_empreinte is None


def test_reponse_ecoutee_comptee_comme_interaction(client, svi, session_admin):
    evenement(client, type="debut", appel="a1", numero=NUMERO)
    evenement(client, type="langue", appel="a1", langue="ln")
    evenement(client, type="svi_ecoute", appel="a1", contenu_id=svi["exemple-verifier-agent"])
    interaction = session_admin.scalars(select(Interaction)).one()
    assert (interaction.canal, interaction.resultat) == ("centre_ecoute", "reponse")
    assert interaction.contenu_id == svi["exemple-verifier-agent"]
    assert (interaction.langue_demandee, interaction.langue_servie) == ("ln", "fr")
    assert len(interaction.usager_empreinte) == 64


def test_contenu_non_publie_jamais_compte(client, svi, session_admin):
    cid = svi["exemple-verifier-agent"]
    session_admin.execute(update(Contenu).where(Contenu.id == cid).values(statut="archive"))
    session_admin.commit()
    evenement(client, type="svi_ecoute", appel="a1", contenu_id=cid)
    assert compter(session_admin, Interaction) == 0


def test_mise_en_file_comptee_une_seule_fois(client, session_admin):
    evenement(client, type="debut", appel="a1", numero=NUMERO)
    evenement(client, type="file_entree", appel="a1", langue="fr")
    evenement(client, type="file_entree", appel="a1", langue="fr")  # le citoyen repatiente
    interaction = session_admin.scalars(select(Interaction)).one()
    assert (interaction.resultat, interaction.motif_escalade) == ("escalade", "demande_humain")
    assert session_admin.scalars(select(Appel)).one().entree_file_a is not None


def test_decroche_et_enregistrement(client, session_admin):
    evenement(client, type="debut", appel="a1", numero=NUMERO)
    r = evenement(client, type="decroche", appel="a1", poste="poste3",
                  fichier="20270501-090000-a1.wav")
    assert r.status_code == 200
    appel = session_admin.scalars(select(Appel)).one()
    assert (appel.poste, appel.decroche_a is not None) == ("poste3", True)
    assert session_admin.scalars(select(Enregistrement.fichier)).one() == "20270501-090000-a1.wav"


@pytest.mark.parametrize("fichier", ["../../etc/passwd", "a/b.wav", "x.mp3", "x .wav"])
def test_nom_de_fichier_dangereux_refuse(client, fichier):
    assert evenement(client, type="decroche", appel="a1", fichier=fichier).status_code == 422


def test_champ_non_prevu_refuse(client):
    assert evenement(client, type="debut", appel="a1", nom="Kabila").status_code == 422


def test_fin_d_appel(client, session_admin):
    evenement(client, type="debut", appel="a1")
    evenement(client, type="fin", appel="a1")
    assert session_admin.scalars(select(Appel)).one().fin_a is not None


def test_evenement_sans_debut_cree_l_appel(client, session_admin):
    evenement(client, type="file_entree", appel="perdu", langue="fr")
    assert session_admin.scalars(select(Appel.reference)).one() == "perdu"


# --- Rappels ---------------------------------------------------------------------------

def test_demande_de_rappel_chiffree(client, session_admin):
    evenement(client, type="debut", appel="a1", numero=NUMERO)
    r = evenement(client, type="rappel", appel="a1", numero=NUMERO, langue="ln")
    assert r.json() == {"enregistre": True}
    rappel = session_admin.scalars(select(Rappel)).one()
    assert "812345678" not in rappel.numero_chiffre
    assert service.dechiffrer_numero(rappel.numero_chiffre) == "243812345678"
    assert (rappel.langue, rappel.statut) == ("ln", "a_rappeler")
    assert session_admin.scalars(select(Appel)).one().rappel_demande is True


def test_rappel_impossible_sans_numero_valide(client, session_admin):
    r = evenement(client, type="rappel", appel="a1", numero="anonymous")
    assert r.json() == {"enregistre": False}
    assert compter(session_admin, Rappel) == 0


def test_numero_efface_des_que_le_rappel_est_traite(client, session_admin):
    evenement(client, type="rappel", appel="a1", numero=NUMERO)
    rid = session_admin.scalars(select(Rappel.id)).one()
    service.traiter_rappel(session_admin, rid, "rappele", "agent@bcr.cd")
    rappel = session_admin.get(Rappel, rid)
    assert (rappel.statut, rappel.numero_chiffre, rappel.traite_par) == (
        "rappele", None, "agent@bcr.cd")


def test_rappels_expires_apres_sept_jours(client, session_admin):
    evenement(client, type="rappel", appel="ancien", numero=NUMERO)
    evenement(client, type="rappel", appel="recent", numero="0899999999")
    session_admin.execute(update(Rappel).where(Rappel.appel_reference == "ancien")
                          .values(cree_a=datetime.now(timezone.utc) - timedelta(days=8)))
    session_admin.commit()
    assert service.expirer_rappels(session_admin, jours=7) == 1
    session_admin.expire_all()
    ancien = session_admin.scalars(select(Rappel).where(Rappel.appel_reference == "ancien")).one()
    recent = session_admin.scalars(select(Rappel).where(Rappel.appel_reference == "recent")).one()
    assert (ancien.statut, ancien.numero_chiffre) == ("expire", None)
    assert recent.numero_chiffre is not None


def test_cle_de_chiffrement_valide():
    from coeur.config import parametres

    Fernet(parametres().cle_chiffrement)  # lève une erreur si la clé est invalide


# --- Enregistrements -------------------------------------------------------------------

def test_purge_des_enregistrements_anciens(client, session_admin, tmp_path, monkeypatch):
    from coeur.config import parametres

    monkeypatch.setattr(parametres(), "dossier_enregistrements", str(tmp_path))
    for nom in ("ancien.wav", "recent.wav"):
        (tmp_path / nom).write_bytes(b"RIFF")
        evenement(client, type="decroche", appel=nom[:-4], fichier=nom)
    session_admin.execute(update(Enregistrement).where(Enregistrement.fichier == "ancien.wav")
                          .values(cree_a=datetime.now(timezone.utc) - timedelta(days=91)))
    session_admin.commit()

    assert service.purger_enregistrements(session_admin, jours=90) == 1
    assert not (tmp_path / "ancien.wav").exists()
    assert (tmp_path / "recent.wav").exists()
    assert session_admin.scalars(select(Enregistrement.fichier)).all() == ["recent.wav"]


def test_purge_de_fin_de_conservation_inclut_la_telephonie(client, session_admin, tmp_path,
                                                          monkeypatch):
    from coeur.base import nouvelle_session
    from coeur.config import parametres
    from coeur.retention.service import purger

    monkeypatch.setattr(parametres(), "dossier_enregistrements", str(tmp_path))
    (tmp_path / "x.wav").write_bytes(b"RIFF")
    evenement(client, type="debut", appel="a1", numero=NUMERO)
    evenement(client, type="decroche", appel="a1", fichier="x.wav")
    evenement(client, type="rappel", appel="a1", numero=NUMERO)
    with nouvelle_session() as session:
        supprimes = purger(session, datetime.now(timezone.utc) + timedelta(days=1))
    assert supprimes["appels"] == 1 and supprimes["rappels"] == 1
    assert supprimes["enregistrements"] == 1
    assert not (tmp_path / "x.wav").exists()


# --- Postes ----------------------------------------------------------------------------

def test_mots_de_passe_des_postes():
    from coeur.centre_appels.postes import mot_de_passe_poste, postes

    assert postes(3) == ["poste1", "poste2", "poste3"]
    a, b = mot_de_passe_poste("s" * 32, "poste1"), mot_de_passe_poste("s" * 32, "poste2")
    assert a != b and len(a) == 32
    assert mot_de_passe_poste("s" * 32, "poste1") == a


# --- Question dite au SVI (touche 9) -----------------------------------------------------

@pytest.fixture
def voix(monkeypatch):
    """Transcription simulée (le « son » est le texte), ouverte au français seulement."""
    from coeur.comprehension.transcription import transcripteur
    from coeur.config import parametres

    monkeypatch.setattr(parametres(), "transcription", "simulation")
    monkeypatch.setattr(parametres(), "transcription_langues", "fr")
    transcripteur.cache_clear()
    yield
    transcripteur.cache_clear()


def dire(client, paroles: bytes, appel="qv1", langue="fr"):
    return client.post("/v1/appels/question-vocale", params={"appel": appel, "langue": langue},
                       content=paroles, headers={**CENTRE, "Content-Type": "audio/wav"})


def test_menu_annonce_la_question_dite_dans_les_langues_transcrites(client, svi, voix):
    menu = client.get("/v1/appels/svi", headers=CENTRE).json()
    assert menu["vocal"] == ["fr"]
    # Tout contenu publié peut être proposé, pas seulement les huit du menu.
    assert {i["cle"] for i in menu["catalogue"]["fr"]} >= {
        "exemple-calendrier-passage", "exemple-verifier-agent"}
    assert len(menu["catalogue"]["fr"]) > len(menu["menus"]["fr"])


def test_menu_sans_transcription_pas_de_question_dite(client, svi):
    menu = client.get("/v1/appels/svi", headers=CENTRE).json()
    assert menu["vocal"] == [] and menu["catalogue"] == {}


def test_question_dite_confirmee_puis_journalisee(client, svi, voix, session_admin):
    evenement(client, type="debut", appel="qv1", numero=NUMERO)
    r = dire(client, "Quand les agents recenseurs passeront chez moi ?".encode())
    assert r.status_code == 200
    assert r.json() == {"issue": "proposition",
                        "contenu_id": svi["exemple-calendrier-passage"]}
    # Rien n'est journalisé avant la confirmation.
    assert compter(session_admin, Interaction) == 0

    assert evenement(client, type="vocal_confirme", appel="qv1", touche="1").json() == {
        "enregistre": True}
    interaction = session_admin.scalars(select(Interaction)).one()
    assert (interaction.canal, interaction.entree, interaction.resultat) == (
        "centre_ecoute", "voix", "reponse")
    assert interaction.contenu_id == svi["exemple-calendrier-passage"]
    appel = session_admin.scalars(select(Appel).where(Appel.reference == "qv1")).one()
    session_admin.refresh(appel)
    assert appel.question_texte is None and appel.question_contenu_id is None


def test_question_dite_refusee_escalade(client, svi, voix, session_admin):
    dire(client, "Quand les agents recenseurs passeront chez moi ?".encode(), appel="qv2")
    evenement(client, type="vocal_confirme", appel="qv2", touche="2")
    interaction = session_admin.scalars(select(Interaction)).one()
    assert (interaction.resultat, interaction.motif_escalade) == ("escalade", "vocal_non_confirme")
    # Une seconde confirmation sans nouvelle question n'est pas comptée.
    assert evenement(client, type="vocal_confirme", appel="qv2", touche="1").json() == {
        "enregistre": False}


def test_question_dite_masquee(client, svi, voix, session_admin):
    dire(client, "Quand les agents passeront chez moi ? Mon numéro 0812345678".encode(),
         appel="qv3")
    evenement(client, type="vocal_confirme", appel="qv3", touche="1")
    texte = session_admin.scalars(select(Interaction.texte_masque)).one()
    assert "0812345678" not in (texte or "")


def test_question_dite_incomprise_va_au_conseiller(client, svi, voix, session_admin):
    assert dire(client, b"", appel="qv4").json() == {"issue": "conseiller", "contenu_id": None}
    r = dire(client, "xyzzy plugh".encode(), appel="qv5")
    assert r.json()["issue"] == "conseiller"
    assert session_admin.scalars(select(Interaction.entree)).all() == ["voix"]


def test_question_dite_langue_non_transcrite(client, svi, voix):
    assert dire(client, "Quand les agents passeront ?".encode(), langue="ln").json()[
        "issue"] == "conseiller"


def test_question_dite_reservee_au_centre_ecoute(client, svi, voix):
    r = client.post("/v1/appels/question-vocale", params={"appel": "x", "langue": "fr"},
                    content=b"a", headers=WEB)
    assert r.status_code == 403


def test_question_dite_trop_longue(client, svi, voix, monkeypatch):
    from coeur.config import parametres

    monkeypatch.setattr(parametres(), "transcription_taille_max_ko", 1)
    assert dire(client, b"a" * 2000).status_code == 413


def test_fin_d_appel_oublie_la_question(client, svi, voix, session_admin):
    dire(client, "Quand les agents recenseurs passeront chez moi ?".encode(), appel="qv6")
    evenement(client, type="fin", appel="qv6")
    appel = session_admin.scalars(select(Appel).where(Appel.reference == "qv6")).one()
    assert appel.question_texte is None and appel.question_contenu_id is None
