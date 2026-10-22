"""Évaluation de la compréhension, langue par langue, sur de vraies questions écrites ou dites.

    python -m coeur.connaissances.evaluation questions.csv
    python -m coeur.connaissances.evaluation questions.csv --seuils 0.4,0.5,0.6 --details

Le fichier CSV (UTF-8) a les colonnes `langue`, `attendu`, et `question` (texte) ou
`audio` (chemin d'un fichier, relatif au CSV), ou les deux. `attendu` est la clé du
contenu qui doit répondre, ou vide si la question est hors du champ de la FAQ (il
faut alors escalader). Pour un audio, une colonne facultative `transcription` donne
ce qui est réellement dit : elle sert à mesurer le taux d'erreur de mots (WER) du
transcripteur. Exemple : `donnees/evaluation_exemple.csv`.

Les audios passent par le transcripteur configuré (TRANSCRIPTION, TRANSCRIPTION_URL),
que leur langue soit ouverte ou non : c'est justement pour décider de l'ouvrir.
Les questions sont posées au corpus publié, tel que l'API le sert, mais rien n'est
journalisé : l'évaluation ne fausse pas les statistiques.

Quatre issues possibles par question :
- `juste` : le bon contenu, ou une escalade pour une question hors champ ;
- `fausse` : un autre contenu que celui attendu. À l'écrit, c'est la pire : le citoyen
  reçoit une information officielle qui ne répond pas à sa question. À la voix, il se
  voit demander de confirmer un mauvais sujet, et répond « Non » ;
- `escalade_a_tort` : la FAQ avait la réponse, il a fallu passer la main (y compris
  quand la voix n'a pas pu être transcrite) ;
- `reponse_hors_champ` : une réponse alors que la question était hors champ.
"""

import argparse
import csv
import mimetypes
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from coeur.comprehension.transcription import Transcripteur, transcripteur
from coeur.config import Parametres, parametres
from coeur.connaissances.depot import Corpus
from coeur.connaissances.moteur import decider, normaliser

ISSUES = ("juste", "fausse", "escalade_a_tort", "reponse_hors_champ")


@dataclass(frozen=True)
class Cas:
    langue: str
    question: str | None
    attendu: str | None
    audio: Path | None = None
    # Ce qui est réellement dit dans l'audio (pour le taux d'erreur de mots).
    reference: str | None = None


@dataclass
class Resultat:
    """Décompte des issues par langue, et les cas qui ne sont pas justes."""

    par_langue: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    erreurs: list[tuple[Cas, str, str | None]] = field(default_factory=list)
    # Langue → taux d'erreur de mots de chaque audio dont la transcription de référence est connue.
    wer: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    # Langue → nombre d'audios que le transcripteur n'a pas pu transcrire.
    non_transcrits: Counter = field(default_factory=Counter)

    def taux(self, langue: str, issue: str) -> float:
        compte = self.par_langue[langue]
        total = sum(compte.values())
        return compte[issue] / total if total else 0.0

    def wer_moyen(self, langue: str) -> float | None:
        valeurs = self.wer.get(langue)
        return sum(valeurs) / len(valeurs) if valeurs else None


def taux_erreur_mots(reference: str, transcription: str) -> float:
    """WER : (substitutions + suppressions + insertions) / mots de la référence."""
    ref, hyp = normaliser(reference).split(), normaliser(transcription).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    precedente = list(range(len(hyp) + 1))
    for i, mot in enumerate(ref, start=1):
        courante = [i]
        for j, autre in enumerate(hyp, start=1):
            courante.append(min(precedente[j] + 1, courante[j - 1] + 1,
                                precedente[j - 1] + (mot != autre)))
        precedente = courante
    return precedente[-1] / len(ref)


def lire_cas(chemin: Path) -> list[Cas]:
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        lecteur = csv.DictReader(fichier)
        colonnes = set(lecteur.fieldnames or [])
        manquantes = {"langue", "attendu"} - colonnes
        if not colonnes & {"question", "audio"}:
            manquantes.add("question ou audio")
        if manquantes:
            raise ValueError(f"Colonnes manquantes : {', '.join(sorted(manquantes))}")
        cas = []
        for ligne in lecteur:
            question = (ligne.get("question") or "").strip() or None
            audio = (ligne.get("audio") or "").strip()
            if not question and not audio:
                continue
            cas.append(Cas(ligne["langue"].strip(), question, ligne["attendu"].strip() or None,
                           chemin.parent / audio if audio else None,
                           (ligne.get("transcription") or "").strip() or None))
        return cas


def _cles(corpus: Corpus) -> dict[int, str]:
    return {texte.contenu_id: texte.cle for texte in corpus.textes.values()}


def issue(attendu: str | None, trouve: str | None) -> str:
    if trouve == attendu:
        return "juste"
    if attendu is None:
        return "reponse_hors_champ"
    return "escalade_a_tort" if trouve is None else "fausse"


def _texte(c: Cas, moteur: Transcripteur | None, resultat: Resultat) -> str | None:
    """Le texte écrit, ou la transcription de l'audio (None si elle a échoué)."""
    if c.audio is None:
        return c.question
    if moteur is None:
        raise ValueError("Des audios à évaluer, mais aucun transcripteur : régler TRANSCRIPTION")
    type_mime = mimetypes.guess_type(c.audio.name)[0] or "application/octet-stream"
    transcription = moteur.transcrire(c.audio.read_bytes(), type_mime, c.langue)
    if transcription is None:
        resultat.non_transcrits[c.langue] += 1
        return None
    if c.reference:
        resultat.wer[c.langue].append(taux_erreur_mots(c.reference, transcription.texte))
    return transcription.texte


def evaluer(corpus: Corpus, cas: list[Cas], reglages: Parametres, seuil: float | None = None,
            moteur: Transcripteur | None = None) -> Resultat:
    """Même règle de décision que l'API (`decider`), au seuil donné."""
    seuil = reglages.seuil_confiance if seuil is None else seuil
    cles = _cles(corpus)
    resultat = Resultat()
    for c in cas:
        texte = _texte(c, moteur, resultat)
        trouve = None
        if texte:
            langues = list(dict.fromkeys((c.langue, reglages.langue_par_defaut)))
            decision = decider(corpus.moteur.rechercher(texte, langues), seuil,
                               reglages.marge_ambiguite)
            trouve = cles.get(decision.contenu_id) if decision.contenu_id is not None else None
        verdict = issue(c.attendu, trouve)
        resultat.par_langue[c.langue][verdict] += 1
        if verdict != "juste":
            resultat.erreurs.append((c, verdict, trouve))
    return resultat


def rapport(resultat: Resultat, seuil: float, details: bool) -> str:
    lignes = [f"Seuil de confiance {seuil:.2f}",
              f"{'langue':<8}{'questions':>10}" + "".join(f"{i:>20}" for i in ISSUES)
              + f"{'non transcrits':>16}{'WER':>8}"]
    for langue in sorted(resultat.par_langue):
        total = sum(resultat.par_langue[langue].values())
        wer = resultat.wer_moyen(langue)
        lignes.append(f"{langue:<8}{total:>10}" + "".join(
            f"{resultat.par_langue[langue][i]:>10} ({resultat.taux(langue, i):>5.0%})"
            for i in ISSUES) + f"{resultat.non_transcrits[langue]:>16}"
            + (f"{wer:>8.0%}" if wer is not None else f"{'—':>8}"))
    if details:
        for cas, verdict, trouve in resultat.erreurs:
            entree = repr(cas.question) if cas.audio is None else f"[audio] {cas.audio.name}"
            lignes.append(f"  [{cas.langue}] {verdict:<19} {entree} : attendu "
                          f"{cas.attendu or 'escalade'}, obtenu {trouve or 'escalade'}")
    return "\n".join(lignes)


def main(arguments: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(prog="python -m coeur.connaissances.evaluation")
    analyseur.add_argument("fichier", type=Path,
                           help="CSV : langue, attendu, question et/ou audio[, transcription]")
    analyseur.add_argument("--seuils", help="Seuils de confiance à comparer, ex. 0.4,0.5,0.6 "
                                            "(par défaut : SEUIL_CONFIANCE)")
    analyseur.add_argument("--details", action="store_true",
                           help="Lister chaque question qui n'a pas la bonne issue")
    args = analyseur.parse_args(arguments)

    from coeur.base import nouvelle_session
    from coeur.connaissances.depot import charger_corpus

    reglages = parametres()
    cas = lire_cas(args.fichier)
    with nouvelle_session() as session:
        corpus = charger_corpus(session)
    inconnues = {c.attendu for c in cas if c.attendu} - set(_cles(corpus).values())
    if inconnues:
        print(f"Clés absentes du corpus publié : {', '.join(sorted(inconnues))}", file=sys.stderr)
        return 1
    seuils = ([float(s) for s in args.seuils.split(",")] if args.seuils
              else [reglages.seuil_confiance])
    # Chaque audio n'est transcrit qu'une fois, quel que soit le nombre de seuils comparés.
    moteur = transcripteur()
    if any(c.audio for c in cas):
        transcrits = Resultat()
        cas = [Cas(c.langue, _texte(c, moteur, transcrits), c.attendu) if c.audio else c
               for c in cas]
    else:
        transcrits = None
    sorties = []
    for s in seuils:
        resultat = evaluer(corpus, cas, reglages, s)
        if transcrits is not None:
            resultat.wer, resultat.non_transcrits = transcrits.wer, transcrits.non_transcrits
        sorties.append(rapport(resultat, s, args.details))
    print("\n\n".join(sorties))
    return 0


if __name__ == "__main__":
    sys.exit(main())
