"""Statistiques : jamais sous la maille du territoire, petits effectifs masqués."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from coeur.interactions.modeles import Interaction
from coeur.statistiques.schemas import Axe
from coeur.statistiques.service import repartir_interactions, repartir_signalements
from tests.integration.conftest import MINISTERE, USSD, WEB

QUESTION = "Quand les agents recenseurs passeront-ils chez moi ?"


def poser(client, territoire, telephone, entetes=WEB):
    client.post(
        "/v1/questions",
        json={"texte": QUESTION, "territoire_code": territoire, "telephone": telephone},
        headers=entetes,
    )


@pytest.fixture
def activite(client, exemples):
    # Goma : 6 questions de 6 usagers différents. Matadi : 2 questions.
    for i in range(6):
        poser(client, "NKV-GOM", f"08100000{i:02d}")
    poser(client, "KCE-MAT", "0820000001")
    poser(client, "KCE-MAT", "0820000002")
    for _ in range(3):
        client.post(
            "/v1/signalements",
            json={"type": "rumeur", "territoire_code": "NKV-GOM", "localite": "Himbi"},
            headers=USSD,
        )


def stats(client, **params):
    r = client.get("/v1/statistiques", params=params, headers=MINISTERE)
    assert r.status_code == 200, r.text
    return r.json()


def test_reserve_au_ministere(client):
    assert client.get("/v1/statistiques", headers=WEB).status_code == 401
    assert client.get("/v1/statistiques").status_code == 401


@pytest.mark.parametrize("niveau", ["localite", "village", "quartier", "secteur", "usager"])
def test_aucune_maille_plus_fine_que_le_territoire(client, niveau):
    assert client.get(f"/v1/statistiques?niveau={niveau}", headers=MINISTERE).status_code == 422


def test_niveau_national(client, activite):
    resultat = stats(client)
    assert resultat["seuil_secret"] == 5
    [ligne] = resultat["interactions"]
    assert ligne["unite"] == "RDC"
    assert ligne["nb_interactions"] == 8
    assert ligne["nb_usagers_uniques"] == 8
    assert ligne["nb_escalades"] == 0


def test_niveau_province(client, activite):
    lignes = {l["unite"]: l for l in stats(client, niveau="province")["interactions"]}
    assert lignes["NKV"]["nb_interactions"] == 6
    assert lignes["KCE"]["masque"] is True
    assert lignes["KCE"]["nb_interactions"] is None


def test_niveau_territoire_avec_secret_statistique(client, activite):
    lignes = {l["unite"]: l for l in stats(client, niveau="territoire")["interactions"]}
    assert lignes["NKV-GOM"]["nb_interactions"] == 6
    assert lignes["NKV-GOM"]["masque"] is False
    assert lignes["KCE-MAT"] == {
        "unite": "KCE-MAT", "canal": "web", "langue": "fr", "nb_interactions": None,
        "nb_escalades": None, "nb_usagers_uniques": None, "masque": True,
    }


def test_signalements_agreges_sans_localite(client, activite):
    resultat = stats(client, niveau="territoire")
    [ligne] = resultat["signalements"]
    assert ligne == {"unite": "NKV-GOM", "type": "rumeur", "nb_signalements": None, "masque": True}
    assert "Himbi" not in str(resultat)


def test_filtre_par_dates(client, activite, session_admin):
    il_y_a_dix_jours = datetime.now(timezone.utc) - timedelta(days=10)
    session_admin.execute(
        update(Interaction).where(Interaction.territoire_code == "NKV-GOM")
        .values(horodatage=il_y_a_dix_jours)
    )
    session_admin.commit()
    hier = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    lignes = stats(client, niveau="territoire", depuis=hier.isoformat())["interactions"]
    assert {l["unite"] for l in lignes} == {"KCE-MAT"}


def test_repartition_par_axe(session_admin, activite):
    [total] = repartir_interactions(session_admin, None, None, None, 5)
    assert (total.valeur, total.nb_interactions, total.nb_usagers_uniques) == ("RDC", 8, 8)

    lignes = repartir_interactions(session_admin, Axe.TERRITOIRE, None, None, 5)
    par_territoire = {e.valeur: e for e in lignes}
    assert par_territoire["NKV-GOM"].nb_interactions == 6
    assert par_territoire["KCE-MAT"].masque and par_territoire["KCE-MAT"].nb_interactions is None

    [web] = repartir_interactions(session_admin, Axe.CANAL, None, None, 5)
    assert (web.valeur, web.nb_interactions) == ("web", 8)

    [rumeurs] = repartir_signalements(session_admin, Axe.TYPE, None, None, 5)
    assert (rumeurs.valeur, rumeurs.nb_signalements, rumeurs.masque) == ("rumeur", None, True)
    assert repartir_signalements(session_admin, Axe.TYPE, None, None, 3)[0].nb_signalements == 3


def test_axes_incompatibles_refuses(session_admin):
    with pytest.raises(ValueError):
        repartir_interactions(session_admin, Axe.TYPE, None, None, 5)
    with pytest.raises(ValueError):
        repartir_signalements(session_admin, Axe.LANGUE, None, None, 5)


def test_totaux_nationaux(session_admin, activite):
    [signalements] = repartir_signalements(session_admin, None, None, None, 3)
    assert (signalements.valeur, signalements.nb_signalements) == ("RDC", 3)


def test_repartitions_sur_base_vide(session_admin):
    assert repartir_interactions(session_admin, None, None, None, 5) == []
    assert repartir_signalements(session_admin, None, None, None, 5) == []
