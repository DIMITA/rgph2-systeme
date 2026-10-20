"""Base de connaissances fermée : on ne sert que ce qui est publié, sinon on escalade."""

from sqlalchemy import select, text

from coeur.connaissances.modeles import Contenu, Formulation, Traduction
from coeur.interactions.modeles import Interaction
from tests.integration.conftest import MINISTERE, USSD, WEB

QUESTION_CALENDRIER = {"texte": "Quand les agents recenseurs passeront-ils chez moi ?"}


def poser(client, corps, entetes=WEB):
    return client.post("/v1/questions", json=corps, headers=entetes)


def ajouter_contenu(session, cle, question, statut_contenu="publie", statut_traduction="publie",
                    langue="fr"):
    contenu = Contenu(cle=cle, categorie="test", statut=statut_contenu)
    session.add(contenu)
    session.flush()
    session.add(Traduction(contenu_id=contenu.id, langue_code=langue, question=question,
                           reponse=f"Réponse à : {question}", statut=statut_traduction))
    session.commit()
    return contenu.id


def test_question_connue_recoit_le_contenu_valide(client, exemples):
    r = poser(client, QUESTION_CALENDRIER)
    assert r.status_code == 200
    corps = r.json()
    assert corps["type"] == "reponse"
    assert corps["contenu"]["cle"] == "exemple-calendrier-passage"
    assert corps["contenu"]["langue"] == "fr"
    assert corps["contenu"]["repli_langue"] is False
    assert corps["contenu"]["reponse_courte"]
    assert corps["message"] is None


def test_question_hors_base_escalade_vers_un_humain(client, exemples):
    corps = poser(client, {"texte": "Quel est le prix du riz au marché ?"}).json()
    assert corps == {
        "type": "escalade",
        "contenu": None,
        "message": "escalade vers un humain",
        "motif": "aucune_reponse_validee",
        "score": corps["score"],
    }


def test_base_vide_escalade_toujours(client):
    corps = poser(client, QUESTION_CALENDRIER).json()
    assert corps["type"] == "escalade"


def test_demande_explicite_d_un_humain(client, exemples):
    corps = poser(client, {"texte": "je veux parler à un conseiller"}).json()
    assert corps["type"] == "escalade"
    assert corps["motif"] == "demande_humain"


def test_contenu_en_brouillon_jamais_servi(client, session_admin):
    question = "Où se trouve le bureau provincial du recensement ?"
    ajouter_contenu(session_admin, "bureau", question, statut_contenu="brouillon")
    assert poser(client, {"texte": question}).json()["type"] == "escalade"


def test_contenu_en_revue_ou_archive_jamais_servi(client, session_admin):
    q1, q2 = "Combien de temps dure l'entretien ?", "Faut-il présenter une pièce d'identité ?"
    ajouter_contenu(session_admin, "duree", q1, statut_contenu="en_revue")
    ajouter_contenu(session_admin, "piece", q2, statut_contenu="archive")
    assert poser(client, {"texte": q1}).json()["type"] == "escalade"
    assert poser(client, {"texte": q2}).json()["type"] == "escalade"


def test_traduction_non_validee_jamais_servie(client, session_admin):
    question = "Où se trouve le bureau provincial du recensement ?"
    ajouter_contenu(session_admin, "bureau", question, statut_traduction="en_revue")
    assert poser(client, {"texte": question}).json()["type"] == "escalade"


def test_publication_dans_le_cms_prise_en_compte(client, session_admin):
    question = "Où se trouve le bureau provincial du recensement ?"
    cid = ajouter_contenu(session_admin, "bureau", question, statut_contenu="brouillon")
    assert poser(client, {"texte": question}).json()["type"] == "escalade"
    session_admin.get(Contenu, cid).statut = "publie"
    session_admin.commit()
    assert poser(client, {"texte": question}).json()["type"] == "reponse"


def test_repli_en_francais_si_langue_non_traduite(client, exemples):
    corps = poser(client, {**QUESTION_CALENDRIER, "langue": "ln"}).json()
    assert corps["type"] == "reponse"
    assert corps["contenu"]["langue"] == "fr"
    assert corps["contenu"]["repli_langue"] is True


def test_traduction_publiee_servie_dans_la_langue_demandee(client, session_admin, exemples):
    cid = exemples["exemple-calendrier-passage"]
    session_admin.add(Traduction(contenu_id=cid, langue_code="ln", question="[test ln] question",
                                 reponse="[test ln] reponse", statut="publie"))
    session_admin.add(Formulation(contenu_id=cid, langue_code="ln", texte="mokolo nini"))
    session_admin.commit()
    corps = poser(client, {"texte": "mokolo nini", "langue": "ln"}).json()
    assert corps["type"] == "reponse"
    assert corps["contenu"]["langue"] == "ln"
    assert corps["contenu"]["repli_langue"] is False


def test_cle_absente_ou_invalide_refusee(client, exemples):
    assert poser(client, QUESTION_CALENDRIER, entetes={}).status_code == 401
    assert poser(client, QUESTION_CALENDRIER, entetes={"X-Cle-API": "mauvaise"}).status_code == 401
    assert poser(client, QUESTION_CALENDRIER, entetes=MINISTERE).status_code == 401


def test_champ_non_prevu_refuse(client, exemples):
    r = poser(client, {**QUESTION_CALENDRIER, "nom": "Kabila"})
    assert r.status_code == 422


def test_territoire_inconnu_refuse(client, exemples):
    r = poser(client, {**QUESTION_CALENDRIER, "territoire_code": "XXX"})
    assert r.status_code == 422


def test_telephone_invalide_refuse(client, exemples):
    assert poser(client, {**QUESTION_CALENDRIER, "telephone": "12"}).status_code == 422


def test_interaction_journalisee_sans_donnee_personnelle(client, exemples, session_admin):
    poser(client, {"texte": "appelez-moi au 0812345678, quand passent les agents ?",
                   "telephone": "+243 812 345 678", "territoire_code": "NKV-GOM"}, USSD)
    interaction = session_admin.scalars(select(Interaction)).one()
    assert interaction.canal == "ussd"
    assert interaction.territoire_code == "NKV-GOM"
    assert len(interaction.usager_empreinte) == 64
    assert "[masqué]" in interaction.texte_masque
    ligne = session_admin.execute(text("SELECT row_to_json(i)::text FROM coeur.interactions i")).scalar()
    assert "812345678" not in ligne


def test_meme_numero_meme_empreinte(client, exemples, session_admin):
    poser(client, {**QUESTION_CALENDRIER, "telephone": "0812345678"})
    poser(client, {**QUESTION_CALENDRIER, "telephone": "+243812345678"})
    empreintes = session_admin.scalars(select(Interaction.usager_empreinte)).all()
    assert len(set(empreintes)) == 1


def test_escalade_aussi_journalisee(client, exemples, session_admin):
    poser(client, {"texte": "qui a gagné le match ?"})
    interaction = session_admin.scalars(select(Interaction)).one()
    assert interaction.resultat == "escalade"
    assert interaction.contenu_id is None


def test_faq_ne_liste_que_les_contenus_publies(client, session_admin, exemples):
    ajouter_contenu(session_admin, "brouillon", "Question en brouillon ?", statut_contenu="brouillon")
    faq = client.get("/v1/faq", headers=WEB).json()
    assert {c["cle"] for c in faq} == set(exemples)


def test_lecture_d_un_contenu(client, session_admin, exemples):
    cid = exemples["exemple-confidentialite"]
    assert client.get(f"/v1/contenus/{cid}", headers=WEB).json()["cle"] == "exemple-confidentialite"
    brouillon = ajouter_contenu(session_admin, "b", "Question ?", statut_contenu="brouillon")
    assert client.get(f"/v1/contenus/{brouillon}", headers=WEB).status_code == 404


def test_conservation_du_texte_limitee_aux_escalades(client, exemples, session_admin, monkeypatch):
    from coeur.config import parametres

    monkeypatch.setattr(parametres(), "conservation_texte_questions", "escalades")
    poser(client, QUESTION_CALENDRIER)
    poser(client, {"texte": "qui a gagné le match ?"})
    textes = dict(session_admin.execute(select(Interaction.resultat, Interaction.texte_masque)).all())
    assert textes == {"reponse": None, "escalade": "qui a gagné le match ?"}


def test_aucun_texte_conserve(client, exemples, session_admin, monkeypatch):
    from coeur.config import parametres
    from coeur.interactions.service import escalades_frequentes

    monkeypatch.setattr(parametres(), "conservation_texte_questions", "aucun")
    poser(client, QUESTION_CALENDRIER)
    poser(client, {"texte": "qui a gagné le match ?"})
    assert set(session_admin.scalars(select(Interaction.texte_masque))) == {None}
    assert escalades_frequentes(session_admin) == []
