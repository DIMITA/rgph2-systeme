"""Kiosques et Ambassadeurs : enrôlement, paquet hors ligne, remontées."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text, update

from coeur.interactions.modeles import Interaction
from coeur.mobile.modeles import Consultation
from coeur.signalements.modeles import Signalement
from coeur.terrain import service
from coeur.terrain.modeles import Appareil, RemonteeRecue


def nouvel_appareil(session, type_="kiosque", code="KIO-NKV-GOM-01", langues=("ln",)):
    return service.creer(session, type_=type_, code=code, territoire_code="NKV-GOM",
                         langues=list(langues), lieu="École primaire Himbi", jours_activation=7)


@pytest.fixture
def kiosque(client, session_admin):
    """En-têtes d'un kiosque activé."""
    _, code = nouvel_appareil(session_admin)
    jeton = client.post("/v1/terrain/activation", json={"code": code}).json()["jeton"]
    return {"Authorization": f"Bearer {jeton}"}


def remontee(type_, **champs):
    return {"id": str(uuid.uuid4()), "type": type_, **champs}


def compter(session, modele, *conditions):
    return session.scalar(select(func.count()).select_from(modele).where(*conditions))


# --- Enrôlement ---------------------------------------------------------------------------------

def test_activation_une_seule_fois(client, session_admin):
    appareil, code = nouvel_appareil(session_admin)
    assert len(code) == 14 and code.count("-") == 2
    # Saisi à la main, en minuscules et sans tirets : accepté.
    r = client.post("/v1/terrain/activation", json={"code": code.replace("-", "").lower()})
    assert r.status_code == 200
    jeton = r.json()["jeton"]
    assert len(jeton) >= 40
    assert client.post("/v1/terrain/activation", json={"code": code}).status_code == 400
    session_admin.refresh(appareil)
    # Ni le jeton ni le code ne sont gardés en clair.
    assert appareil.jeton_empreinte != jeton and appareil.activation_empreinte is None
    assert appareil.active_a is not None


def test_code_expire_ou_faux(client, session_admin):
    appareil, code = nouvel_appareil(session_admin)
    assert client.post("/v1/terrain/activation", json={"code": "AAAA-BBBB-CCCC"}).status_code == 400
    session_admin.execute(update(Appareil).values(
        activation_expire_a=datetime.now(timezone.utc) - timedelta(minutes=1)))
    session_admin.commit()
    assert client.post("/v1/terrain/activation", json={"code": code}).status_code == 400


def test_essais_d_activation_limites(client):
    from coeur.terrain.routes import limiteurs

    limiteurs()[0].reinitialiser()
    statuts = [client.post("/v1/terrain/activation", json={"code": "AAAA-BBBB-CCCC"}).status_code
               for _ in range(11)]
    assert statuts[:10] == [400] * 10 and statuts[10] == 429


def test_code_d_appareil_unique_et_territoire_connu(session_admin):
    nouvel_appareil(session_admin)
    with pytest.raises(ValueError, match="déjà utilisé"):
        nouvel_appareil(session_admin)
    with pytest.raises(ValueError, match="Territoire inconnu"):
        service.creer(session_admin, type_="kiosque", code="KIO-X", territoire_code="XXX",
                      langues=[], lieu=None, jours_activation=7)


def test_sans_jeton_ou_revoque(client, session_admin, kiosque):
    assert client.get("/v1/terrain/paquet").status_code == 401
    assert client.get("/v1/terrain/paquet", headers={"Authorization": "Bearer faux"}).status_code == 401
    assert client.get("/v1/terrain/paquet", headers=kiosque).status_code == 200
    service.revoquer(session_admin, session_admin.scalar(select(Appareil)))
    assert client.get("/v1/terrain/paquet", headers=kiosque).status_code == 401


def test_nouveau_code_coupe_l_ancien_jeton(client, session_admin, kiosque):
    appareil = session_admin.scalar(select(Appareil))
    code = service.reactiver(session_admin, appareil, 7)
    assert client.get("/v1/terrain/paquet", headers=kiosque).status_code == 401
    jeton = client.post("/v1/terrain/activation", json={"code": code}).json()["jeton"]
    assert client.get("/v1/terrain/paquet",
                      headers={"Authorization": f"Bearer {jeton}"}).status_code == 200


# --- Paquet -------------------------------------------------------------------------------------

def test_paquet_hors_ligne(client, session_admin, kiosque, exemples):
    from coeur.calendrier.service import charger_exemples

    charger_exemples(session_admin)
    r = client.get("/v1/terrain/paquet", headers=kiosque)
    assert r.status_code == 200
    p = r.json()
    assert p["appareil"] == {"code": "KIO-NKV-GOM-01", "type": "kiosque",
                             "lieu": "École primaire Himbi", "territoire_code": "NKV-GOM"}
    assert [l["code"] for l in p["langues"]] == ["fr", "ln"]
    assert len(p["faq"]["fr"]) == 5
    # Rien n'est encore traduit en lingala : réponses françaises, repli signalé.
    assert all(c["repli_langue"] for c in p["faq"]["ln"])
    assert {"territoire_code": "NKV-GOM", "debut": "2027-05-17", "fin": "2027-06-06"} in p["calendrier"]
    assert any(t["code"] == "NKV-GOM" for prov in p["provinces"] for t in prov["territoires"])
    assert p["textes"]["fr"]["titre"]
    assert p["numero_vert"] == "0800 000 000"

    # Inchangé : 304 sans corps, et l'heure de synchronisation est notée.
    etag = r.headers["ETag"]
    r2 = client.get("/v1/terrain/paquet", headers={**kiosque, "If-None-Match": etag})
    assert r2.status_code == 304 and r2.content == b""
    appareil = session_admin.scalar(select(Appareil))
    session_admin.refresh(appareil)
    assert appareil.derniere_synchro_a is not None
    assert f'"{appareil.version_paquet}"' == etag


def test_paquet_change_quand_un_contenu_est_publie(client, session_admin, kiosque, exemples):
    etag = client.get("/v1/terrain/paquet", headers=kiosque).headers["ETag"]
    session_admin.execute(text("UPDATE contenus_traductions SET reponse = reponse || ' (mis à jour)'"))
    session_admin.commit()
    from coeur.connaissances.depot import cache
    cache.invalider()
    r = client.get("/v1/terrain/paquet", headers={**kiosque, "If-None-Match": etag})
    assert r.status_code == 200 and r.headers["ETag"] != etag


def test_le_paquet_ne_contient_que_du_publie(client, session_admin, kiosque, exemples):
    session_admin.execute(text("UPDATE contenus SET statut = 'brouillon' "
                               "WHERE cle = 'exemple-confidentialite'"))
    session_admin.commit()
    cles = {c["cle"] for c in client.get("/v1/terrain/paquet", headers=kiosque).json()["faq"]["fr"]}
    assert "exemple-confidentialite" not in cles and len(cles) == 4


# --- Remontées ----------------------------------------------------------------------------------

def test_remontees_de_tous_types(client, session_admin, kiosque, exemples):
    hier = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    lot = [
        remontee("consultation", contenu_id=exemples["exemple-confidentialite"], langue="ln",
                 horodatage=hier),
        remontee("question", texte="Est-ce que le recensement est payant ? Tél 0812345678",
                 langue="fr"),
        remontee("signalement", signalement="menage_non_visite", territoire_code="NKV-GOM",
                 localite="Himbi, avenue 3", description="Personne n'est passé"),
        remontee("passage", territoire_code="NKV-GOM", langue="fr", resultat="trouve"),
    ]
    r = client.post("/v1/terrain/remontees", json=lot, headers=kiosque)
    assert r.status_code == 200, r.text
    assert r.json() == {"acceptes": [x["id"] for x in lot], "rejetes": []}

    lecture, question = session_admin.scalars(select(Interaction).order_by(Interaction.id)).all()
    assert (lecture.canal, lecture.resultat, lecture.contenu_id, lecture.territoire_code) == (
        "kiosque", "reponse", exemples["exemple-confidentialite"], "NKV-GOM")
    assert lecture.horodatage.date() == datetime.fromisoformat(hier).date()
    assert (question.resultat, question.motif_escalade) == ("escalade", "remontee_terrain")
    assert "0812345678" not in question.texte_masque
    signalement = session_admin.scalar(select(Signalement))
    assert (signalement.canal, signalement.type, signalement.localite) == (
        "kiosque", "menage_non_visite", "Himbi, avenue 3")
    assert compter(session_admin, Consultation, Consultation.service == "passage") == 1


def test_lot_rejoue_sans_doublon(client, session_admin, kiosque):
    lot = [remontee("signalement", signalement="rumeur", territoire_code="NKV-GOM",
                    description="On dit que le recensement sert aux impôts")]
    for _ in range(2):
        assert client.post("/v1/terrain/remontees", json=lot,
                           headers=kiosque).json()["acceptes"] == [lot[0]["id"]]
    assert compter(session_admin, Signalement) == 1
    assert compter(session_admin, RemonteeRecue) == 1


def test_elements_invalides_rejetes_un_par_un(client, session_admin, kiosque):
    bon = remontee("question", texte="Combien de temps dure l'entretien ?", langue="fr")
    lot = [
        bon,
        remontee("signalement", signalement="rumeur", territoire_code="XXX-YYY"),
        remontee("question", texte="", langue="fr"),
        remontee("question", texte="nom ?", langue="fr", nom="Kabila"),  # champ non prévu
        {"id": "pas-un-uuid", "type": "question", "texte": "x", "langue": "fr"},
        "pas un objet",
    ]
    corps = client.post("/v1/terrain/remontees", json=lot, headers=kiosque).json()
    assert corps["acceptes"] == [bon["id"]]
    assert [r["raison"] for r in corps["rejetes"]] == [
        "territoire_inconnu", "invalide", "invalide", "invalide", "invalide"]
    assert compter(session_admin, Interaction) == 1


def test_horloge_dereglee_ramenee_a_l_heure_de_reception(client, session_admin, kiosque):
    lot = [remontee("question", texte="question d'une tablette en 2019", langue="fr",
                    horodatage="2019-01-01T08:00:00+00:00")]
    client.post("/v1/terrain/remontees", json=lot, headers=kiosque)
    horodatage = session_admin.scalar(select(Interaction.horodatage))
    assert horodatage > datetime.now(timezone.utc) - timedelta(minutes=5)


def test_lot_trop_gros(client, kiosque):
    lot = [remontee("question", texte="x", langue="fr") for _ in range(201)]
    assert client.post("/v1/terrain/remontees", json=lot, headers=kiosque).status_code == 422


def test_ambassadeur_remonte_une_rumeur(client, session_admin):
    _, code = nouvel_appareil(session_admin, "ambassadeur", "AMB-NKV-GOM-07")
    jeton = client.post("/v1/terrain/activation", json={"code": code}).json()["jeton"]
    lot = [remontee("signalement", signalement="rumeur", territoire_code="KCE-MAT",
                    description="Les agents prendraient les enfants")]
    client.post("/v1/terrain/remontees", json=lot, headers={"Authorization": f"Bearer {jeton}"})
    signalement = session_admin.scalar(select(Signalement))
    assert (signalement.canal, signalement.territoire_code) == ("ambassadeur", "KCE-MAT")


def test_purge_des_identifiants(client, session_admin, kiosque):
    client.post("/v1/terrain/remontees", headers=kiosque,
                json=[remontee("question", texte="x", langue="fr")])
    session_admin.execute(update(RemonteeRecue).values(
        recu_a=datetime.now(timezone.utc) - timedelta(days=61)))
    session_admin.commit()
    assert service.purger_remontees(session_admin, 60) == 1


# --- Badge (en ligne) ---------------------------------------------------------------------------

def test_verification_de_badge(client, session_admin, kiosque, badges):
    r = client.post("/v1/terrain/badge", json={"numero": "ab-1234"}, headers=kiosque)
    assert r.json() == {"statut": "valide", "territoire_code": "NKV-GOM", "territoire_nom": "Goma"}
    assert client.post("/v1/terrain/badge", json={"numero": "?"}, headers=kiosque).status_code == 422
    assert compter(session_admin, Consultation, Consultation.canal == "kiosque",
                   Consultation.service == "badge") == 1
