import pytest

from coeur.connaissances.exemples import EXEMPLES
from coeur.connaissances.moteur import (
    Candidat,
    Entree,
    MoteurLexical,
    decider,
    demande_humain,
    normaliser,
    similarite_mots,
)

SEUIL, MARGE = 0.5, 0.1


@pytest.fixture(scope="module")
def moteur():
    entrees = []
    for i, ex in enumerate(EXEMPLES, start=1):
        entrees.append(Entree(i, "fr", ex["question"]))
        entrees += [Entree(i, "fr", f) for f in ex["formulations"]]
    return MoteurLexical(entrees)


def cle_trouvee(moteur, question, langues=("fr",)):
    decision = decider(moteur.rechercher(question, langues), SEUIL, MARGE)
    return None if decision.contenu_id is None else EXEMPLES[decision.contenu_id - 1]["cle"]


def test_normalisation_retire_accents_casse_et_ponctuation():
    assert normaliser("  Où est l'Agent ?! ") == "ou est l agent"


def test_similarite_tolere_conjugaisons_pluriels_et_fautes():
    assert similarite_mots("passage", "passeront") >= 0.9
    assert similarite_mots("recensement", "recensemant") > 0.5
    assert similarite_mots("agent", "date") == 0.0


@pytest.mark.parametrize(
    "question, attendu",
    [
        ("Quand les agents recenseurs passeront-ils chez moi ?", "exemple-calendrier-passage"),
        ("c'est quand le passage des agents", "exemple-calendrier-passage"),
        ("QUEL JOUR LE RECENSEMENT ARRIVE", "exemple-calendrier-passage"),
        ("comment verifier qu'un agent est vrai", "exemple-verifier-agent"),
        ("je crois que c'est un faux agent", "exemple-verifier-agent"),
        ("qui va voir mes réponses ?", "exemple-confidentialite"),
        ("mes donnees sont protegees ?", "exemple-confidentialite"),
        ("personne n'est venu chez nous", "exemple-menage-non-visite"),
        ("ma famille n'a pas été recensée", "exemple-menage-non-visite"),
        ("pourquoi le recensement", "exemple-pourquoi-recensement"),
    ],
)
def test_questions_reconnues(moteur, question, attendu):
    assert cle_trouvee(moteur, question) == attendu


@pytest.mark.parametrize(
    "question",
    [
        "quel est le prix du riz au marché",
        "qui a gagné le match hier",
        "est-ce que je peux avoir un emploi",
        "bonjour",
        "recensement",
        "???",
        "",
    ],
)
def test_questions_hors_base_escaladees(moteur, question):
    assert cle_trouvee(moteur, question) is None


def test_recherche_limitee_aux_langues_demandees(moteur):
    assert moteur.rechercher("calendrier du recensement", ["ln"]) == []


def test_decider_escalade_si_score_trop_faible():
    decision = decider([Candidat(1, 0.3)], SEUIL, MARGE)
    assert decision.contenu_id is None
    assert decision.motif_escalade == "aucune_reponse_validee"


def test_decider_escalade_si_deux_contenus_trop_proches():
    decision = decider([Candidat(1, 0.8), Candidat(2, 0.78)], SEUIL, MARGE)
    assert decision.contenu_id is None
    assert decision.motif_escalade == "ambigu"


def test_decider_repond_si_net():
    decision = decider([Candidat(1, 0.8), Candidat(2, 0.5)], SEUIL, MARGE)
    assert decision.contenu_id == 1
    assert decision.motif_escalade is None


def test_decider_sans_candidat():
    assert decider([], SEUIL, MARGE).motif_escalade == "aucune_reponse_validee"


@pytest.mark.parametrize(
    "texte", ["je veux parler à un humain", "passez-moi un conseiller", "parler à quelqu'un svp"]
)
def test_demande_explicite_d_un_humain(texte):
    assert demande_humain(texte)


def test_question_ordinaire_n_est_pas_une_demande_humain():
    assert not demande_humain("comment reconnaître un agent recenseur")
