import pytest

from coeur.territoires.service import importer_csv
from tests.integration.conftest import RACINE


def test_sante(client):
    assert client.get("/sante").json() == {"statut": "ok"}


def test_referentiel_public(client):
    provinces = client.get("/v1/territoires").json()
    assert len(provinces) == 26
    nord_kivu = next(p for p in provinces if p["code"] == "NKV")
    assert {t["code"] for t in nord_kivu["territoires"]} >= {"NKV-GOM", "NKV-BEN"}


def test_import_idempotent(client, session_admin):
    importer_csv(session_admin, RACINE / "donnees" / "territoires.csv")
    assert len(client.get("/v1/territoires").json()) == 26


def test_import_refuse_un_fichier_mal_forme(session_admin, tmp_path):
    fichier = tmp_path / "t.csv"
    fichier.write_text("code,nom\nX,Y\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Colonnes manquantes"):
        importer_csv(session_admin, fichier)
