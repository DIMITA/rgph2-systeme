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


def test_taux_d_erreur_de_mots():
    from coeur.connaissances.evaluation import taux_erreur_mots

    assert taux_erreur_mots("Ntango nini bakoya", "ntango nini bakoya") == 0
    assert taux_erreur_mots("ntango nini bakoya", "ntango bakoya") == 1 / 3      # suppression
    assert taux_erreur_mots("ntango nini bakoya", "tango nini bakoya awa") == 2 / 3  # subst. + insertion
    assert taux_erreur_mots("", "") == 0


def test_evaluation_de_messages_vocaux(tmp_path):
    from coeur.comprehension.transcription import TranscripteurSimulation

    # En simulation, le « son » est le texte : un fichier vide est un audio incompris.
    (tmp_path / "q1.ogg").write_bytes("c'est quand le passage des agents".encode())
    (tmp_path / "q2.ogg").write_bytes(b"")
    (tmp_path / "q.csv").write_text(
        "langue,audio,transcription,attendu\n"
        "fr,q1.ogg,c'est quand le passage des agents recenseurs,exemple-calendrier-passage\n"
        "fr,q2.ogg,,exemple-verifier-agent\n", encoding="utf-8")
    cas = lire_cas(tmp_path / "q.csv")
    assert cas[0].audio == tmp_path / "q1.ogg" and cas[0].question is None
    resultat = evaluer(corpus_exemple(), cas, parametres(), seuil=0.5,
                       moteur=TranscripteurSimulation())
    assert resultat.par_langue["fr"]["juste"] == 1
    assert resultat.par_langue["fr"]["escalade_a_tort"] == 1
    assert resultat.non_transcrits["fr"] == 1
    assert resultat.wer_moyen("fr") == 1 / 8  # « recenseurs » manquant (« c est » : deux mots)
    assert "[audio] q2.ogg" in rapport(resultat, 0.5, details=True)


def test_audio_sans_transcripteur(tmp_path):
    import pytest

    (tmp_path / "q.ogg").write_bytes(b"x")
    with pytest.raises(ValueError, match="TRANSCRIPTION"):
        evaluer(corpus_exemple(), [Cas("ln", None, None, tmp_path / "q.ogg")], parametres())
