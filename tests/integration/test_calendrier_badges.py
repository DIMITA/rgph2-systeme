"""Calendrier de passage et liste des badges : API, import, droits, purge, tableau de bord."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import ProgrammingError

from coeur.badges.modeles import Badge
from coeur.badges.service import importer_csv
from coeur.base import nouvelle_session
from coeur.calendrier.modeles import Passage
from coeur.mobile.modeles import Consultation, MessageSms, PreferenceLangue
from coeur.retention.service import purger
from tests.conftest import PEPPER, URL_API, URL_DIRECTUS
from tests.integration.conftest import WEB


@pytest.fixture
def calendrier(session_admin):
    session_admin.add_all([
        Passage(territoire_code="NKV-GOM", date_debut="2027-06-01", date_fin="2027-06-10",
                statut="publie"),
        Passage(territoire_code="NKV-GOM", date_debut="2027-05-17", date_fin="2027-05-25",
                statut="publie"),
        Passage(territoire_code="NKV-GOM", date_debut="2027-07-01", date_fin="2027-07-05",
                statut="en_revue"),
    ])
    session_admin.commit()


# --- Calendrier ---------------------------------------------------------------------------

def test_calendrier_publie_seulement_dans_l_ordre(client, calendrier):
    r = client.get("/v1/calendrier/NKV-GOM", headers=WEB)
    assert r.json() == {"territoire_code": "NKV-GOM", "territoire_nom": "Goma", "passages": [
        {"date_debut": "2027-05-17", "date_fin": "2027-05-25"},
        {"date_debut": "2027-06-01", "date_fin": "2027-06-10"}]}
    assert client.get("/v1/calendrier/KIN-V", headers=WEB).json()["passages"] == []
    assert client.get("/v1/calendrier/XXX", headers=WEB).status_code == 404
    assert client.get("/v1/calendrier/NKV-GOM").status_code == 401


def test_dates_incoherentes_refusees(session_admin):
    session_admin.add(Passage(territoire_code="KIN-V", date_debut="2027-06-01",
                              date_fin="2027-05-01"))
    with pytest.raises(Exception, match="ck_calendrier_passages_dates"):
        session_admin.commit()
    session_admin.rollback()


# --- Badges -----------------------------------------------------------------------------------

def test_verification_par_l_api(client, badges):
    def verifier(numero, **kw):
        return client.post("/v1/badges/verification", json={"numero": numero, **kw}, headers=WEB)

    assert verifier("AB 1234").json() == {"statut": "valide", "territoire_code": "NKV-GOM",
                                          "territoire_nom": "Goma"}
    assert verifier("XY9999").json()["statut"] == "retire"
    assert verifier("ZZ0000").json() == {"statut": "inconnu", "territoire_code": None,
                                         "territoire_nom": None}
    assert verifier("A!").status_code == 422
    assert verifier("AB1234", nom="Kabila").status_code == 422  # champ non prévu refusé
    for _ in range(10):
        assert verifier("QQ0000", telephone="0811111111").status_code == 200
    assert verifier("QQ0000", telephone="0811111111").status_code == 429


def test_badges_stockes_sous_forme_d_empreinte(badges, session_admin):
    contenu = session_admin.execute(
        text("SELECT string_agg(t::text, ' ') FROM coeur.badges t")).scalar()
    assert "AB1234" not in contenu and "XY9999" not in contenu
    assert session_admin.scalar(select(func.count()).select_from(Badge)) == 2


def test_import_remplace_toute_la_liste(badges, session_admin, tmp_path):
    fichier = tmp_path / "nouvelle.csv"
    fichier.write_text("numero,territoire_code,actif\nCD5678,KIN-V,oui\n", encoding="utf-8")
    assert importer_csv(session_admin, fichier, PEPPER) == (1, 0)
    assert session_admin.scalar(select(func.count()).select_from(Badge)) == 1


def test_import_refuse_en_entier_si_une_ligne_est_invalide(badges, session_admin, tmp_path):
    fichier = tmp_path / "erreurs.csv"
    fichier.write_text("numero,territoire_code,actif\nCD5678,KIN-V,1\nCD9,XXX,1\n**,KIN-V,1\n",
                       encoding="utf-8")
    with pytest.raises(ValueError) as erreur:
        importer_csv(session_admin, fichier, PEPPER)
    assert "ligne 3 : territoire inconnu 'XXX'" in str(erreur.value)
    assert "ligne 4 : numéro de badge invalide" in str(erreur.value)
    assert session_admin.scalar(select(func.count()).select_from(Badge)) == 2  # liste intacte


def test_import_colonnes_manquantes(session_admin, tmp_path):
    fichier = tmp_path / "colonnes.csv"
    fichier.write_text("badge,territoire\nAB1234,KIN-V\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Colonnes manquantes"):
        importer_csv(session_admin, fichier, PEPPER)


# --- Droits -------------------------------------------------------------------------------------

def refuse(url, sql):
    moteur = create_engine(url)
    try:
        with pytest.raises(ProgrammingError, match="permission denied"):
            with moteur.begin() as connexion:
                connexion.execute(text(sql))
    finally:
        moteur.dispose()


def test_l_api_ne_peut_ni_ajouter_ni_modifier_un_badge():
    refuse(URL_API, "INSERT INTO coeur.badges (empreinte, territoire_code) VALUES ('x', 'KIN-V')")
    refuse(URL_API, "UPDATE coeur.badges SET actif = true")
    refuse(URL_API, "INSERT INTO calendrier_passages (territoire_code, date_debut, date_fin) "
                    "VALUES ('KIN-V', '2027-01-01', '2027-01-02')")


def test_directus_ne_voit_ni_badges_ni_journaux_mobiles():
    for table in ("badges", "consultations", "sms", "preferences_langue"):
        refuse(URL_DIRECTUS, f"SELECT * FROM coeur.{table}")


def test_directus_edite_le_calendrier():
    moteur = create_engine(URL_DIRECTUS)
    with moteur.begin() as connexion:
        connexion.execute(text("INSERT INTO calendrier_passages (territoire_code, date_debut, "
                               "date_fin) VALUES ('KIN-V', '2027-05-10', '2027-06-20')"))
    moteur.dispose()


# --- Purge ----------------------------------------------------------------------------------------

def test_purge_des_donnees_mobiles(client, badges, session_admin):
    session_admin.add_all([
        Consultation(canal="ussd", service="badge", resultat="valide", langue="fr"),
        MessageSms(sens="entrant", usager_empreinte="e" * 64, statut="recu"),
        PreferenceLangue(usager_empreinte="e" * 64, langue="ln"),
    ])
    session_admin.commit()
    with nouvelle_session() as session:
        supprimes = purger(session, datetime.now(timezone.utc) + timedelta(days=1))
    assert {k: supprimes[k] for k in ("consultations", "sms", "preferences_langue", "badges")} == {
        "consultations": 1, "sms": 1, "preferences_langue": 1, "badges": 2}
