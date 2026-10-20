from sqlalchemy import select

from coeur.signalements.modeles import Signalement
from tests.integration.conftest import MINISTERE, WEB

SIGNALEMENT = {
    "type": "menage_non_visite",
    "territoire_code": "NKV-GOM",
    "localite": "Quartier Himbi",
    "description": "Personne n'est passé, rappelez le 0812345678",
    "telephone": "0812345678",
}


def signaler(client, corps=SIGNALEMENT, entetes=WEB):
    return client.post("/v1/signalements", json=corps, headers=entetes)


def test_creation_d_un_signalement(client, session_admin):
    r = signaler(client)
    assert r.status_code == 201
    assert r.json()["statut"] == "nouveau"
    signalement = session_admin.scalars(select(Signalement)).one()
    assert signalement.canal == "web"
    assert signalement.localite == "Quartier Himbi"
    assert "812345678" not in signalement.description
    assert len(signalement.usager_empreinte) == 64


def test_territoire_obligatoire_et_connu(client):
    assert signaler(client, {**SIGNALEMENT, "territoire_code": "XXX"}).status_code == 422
    sans = {k: v for k, v in SIGNALEMENT.items() if k != "territoire_code"}
    assert signaler(client, sans).status_code == 422


def test_type_inconnu_refuse(client):
    assert signaler(client, {**SIGNALEMENT, "type": "plainte"}).status_code == 422


def test_donnee_personnelle_non_prevue_refusee(client):
    assert signaler(client, {**SIGNALEMENT, "nom_chef_menage": "Mukendi"}).status_code == 422
    assert signaler(client, {**SIGNALEMENT, "nombre_personnes": 6}).status_code == 422


def test_liste_reservee_au_ministere_et_sans_empreinte(client):
    signaler(client)
    assert client.get("/v1/signalements", headers=WEB).status_code == 401
    liste = client.get("/v1/signalements", headers=MINISTERE).json()
    assert len(liste) == 1
    assert "usager_empreinte" not in liste[0]
    assert "telephone" not in liste[0]


def test_filtre_par_territoire(client):
    signaler(client)
    signaler(client, {**SIGNALEMENT, "territoire_code": "KCE-MAT"})
    liste = client.get("/v1/signalements?territoire_code=KCE-MAT", headers=MINISTERE).json()
    assert [s["territoire_code"] for s in liste] == ["KCE-MAT"]


def test_changement_de_statut(client):
    sid = signaler(client).json()["id"]
    r = client.patch(f"/v1/signalements/{sid}", json={"statut": "clos"}, headers=MINISTERE)
    assert r.json()["statut"] == "clos"
    assert client.patch(f"/v1/signalements/{sid}", json={"statut": "clos"}, headers=WEB).status_code == 401
    assert client.patch("/v1/signalements/999", json={"statut": "clos"}, headers=MINISTERE).status_code == 404
