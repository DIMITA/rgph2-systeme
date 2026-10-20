from coeur.config import parametres
from coeur.connaissances.depot import Corpus, TextePublie
from coeur.connaissances.evaluation import Cas, evaluer, issue, lire_cas, rapport
from coeur.connaissances.exemples import EXEMPLES
from coeur.connaissances.moteur import Entree, MoteurLexical


def corpus_exemple() -> Corpus:
    entrees, textes = [], {}
    for i, ex in enumerate(EXEMPLES, start=1):
        entrees.append(Entree(i, "fr", ex["question"]))
        entrees += [Entree(i, "fr", f) for f in ex["formulations"]]
        textes[(i, "fr")] = TextePublie(i, ex["cle"], ex["categorie"], "fr", ex["question"],
                                        "réponse", None, None)
    return Corpus(moteur=MoteurLexical(entrees), textes=textes)


def test_issues():
    assert issue("a", "a") == "juste"
    assert issue(None, None) == "juste"
    assert issue("a", "b") == "fausse"
    assert issue("a", None) == "escalade_a_tort"
    assert issue(None, "a") == "reponse_hors_champ"


def test_evaluation_par_langue():
    cas = [
        Cas("fr", "c'est quand le passage des agents", "exemple-calendrier-passage"),
        Cas("fr", "quel est le prix du riz au marché ?", None),
        # Lingala sans formulation dans le corpus : la question ne peut pas être reconnue.
        Cas("ln", "Ntango nini bato ya mokanda bakoya ?", "exemple-calendrier-passage"),
    ]
    resultat = evaluer(corpus_exemple(), cas, parametres(), seuil=0.5)
    assert resultat.par_langue["fr"]["juste"] == 2
    assert resultat.par_langue["ln"]["escalade_a_tort"] == 1
    assert resultat.taux("ln", "juste") == 0.0
    assert [c.langue for c, _, _ in resultat.erreurs] == ["ln"]
    texte = rapport(resultat, 0.5, details=True)
    assert "escalade_a_tort" in texte and "Ntango" in texte


def test_fichier_d_exemple_lisible():
    from pathlib import Path

    cas = lire_cas(Path(__file__).parents[2] / "donnees" / "evaluation_exemple.csv")
    assert cas[-1].attendu is None
    resultat = evaluer(corpus_exemple(), cas, parametres())
    assert resultat.par_langue["fr"]["juste"] == len(cas)


def test_colonnes_manquantes(tmp_path):
    import pytest

    fichier = tmp_path / "q.csv"
    fichier.write_text("langue,question\nfr,bonjour\n", encoding="utf-8")
    with pytest.raises(ValueError, match="attendu"):
        lire_cas(fichier)
