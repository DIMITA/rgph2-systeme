"""Évaluation du moteur de recherche, langue par langue, sur de vraies questions.

    python -m coeur.connaissances.evaluation questions.csv
    python -m coeur.connaissances.evaluation questions.csv --seuils 0.4,0.5,0.6 --details

Le fichier CSV (UTF-8) a trois colonnes : `langue`, `question`, `attendu`. `attendu`
est la clé du contenu qui doit répondre, ou vide si la question est hors du champ
de la FAQ (le moteur doit alors escalader). Exemple : `donnees/evaluation_exemple.csv`.

Les questions sont posées au corpus publié, tel que l'API le sert, mais rien n'est
journalisé : l'évaluation ne fausse pas les statistiques.

Quatre issues possibles par question :
- `juste` : le bon contenu, ou une escalade pour une question hors champ ;
- `fausse` : un autre contenu que celui attendu. C'est la pire : le citoyen reçoit
  une information officielle qui ne répond pas à sa question ;
- `escalade_a_tort` : la FAQ avait la réponse, le moteur a passé la main ;
- `reponse_hors_champ` : une réponse alors que la question était hors champ.
"""

import argparse
import csv
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from coeur.config import Parametres, parametres
from coeur.connaissances.depot import Corpus
from coeur.connaissances.moteur import decider

ISSUES = ("juste", "fausse", "escalade_a_tort", "reponse_hors_champ")


@dataclass(frozen=True)
class Cas:
    langue: str
    question: str
    attendu: str | None


@dataclass
class Resultat:
    """Décompte des issues par langue, et les cas qui ne sont pas justes."""

    par_langue: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    erreurs: list[tuple[Cas, str, str | None]] = field(default_factory=list)

    def taux(self, langue: str, issue: str) -> float:
        compte = self.par_langue[langue]
        total = sum(compte.values())
        return compte[issue] / total if total else 0.0


def lire_cas(chemin: Path) -> list[Cas]:
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        lecteur = csv.DictReader(fichier)
        manquantes = {"langue", "question", "attendu"} - set(lecteur.fieldnames or [])
        if manquantes:
            raise ValueError(f"Colonnes manquantes : {', '.join(sorted(manquantes))}")
        return [Cas(ligne["langue"].strip(), ligne["question"].strip(),
                    ligne["attendu"].strip() or None)
                for ligne in lecteur if ligne["question"].strip()]


def _cles(corpus: Corpus) -> dict[int, str]:
    return {texte.contenu_id: texte.cle for texte in corpus.textes.values()}


def issue(attendu: str | None, trouve: str | None) -> str:
    if trouve == attendu:
        return "juste"
    if attendu is None:
        return "reponse_hors_champ"
    return "escalade_a_tort" if trouve is None else "fausse"


def evaluer(corpus: Corpus, cas: list[Cas], reglages: Parametres,
            seuil: float | None = None) -> Resultat:
    """Même règle de décision que l'API (`decider`), au seuil donné."""
    seuil = reglages.seuil_confiance if seuil is None else seuil
    cles = _cles(corpus)
    resultat = Resultat()
    for c in cas:
        langues = list(dict.fromkeys((c.langue, reglages.langue_par_defaut)))
        decision = decider(corpus.moteur.rechercher(c.question, langues), seuil,
                           reglages.marge_ambiguite)
        trouve = cles.get(decision.contenu_id) if decision.contenu_id is not None else None
        verdict = issue(c.attendu, trouve)
        resultat.par_langue[c.langue][verdict] += 1
        if verdict != "juste":
            resultat.erreurs.append((c, verdict, trouve))
    return resultat


def rapport(resultat: Resultat, seuil: float, details: bool) -> str:
    lignes = [f"Seuil de confiance {seuil:.2f}",
              f"{'langue':<8}{'questions':>10}" + "".join(f"{i:>20}" for i in ISSUES)]
    for langue in sorted(resultat.par_langue):
        total = sum(resultat.par_langue[langue].values())
        lignes.append(f"{langue:<8}{total:>10}" + "".join(
            f"{resultat.par_langue[langue][i]:>10} ({resultat.taux(langue, i):>5.0%})"
            for i in ISSUES))
    if details:
        for cas, verdict, trouve in resultat.erreurs:
            lignes.append(f"  [{cas.langue}] {verdict:<19} {cas.question!r} : attendu "
                          f"{cas.attendu or 'escalade'}, obtenu {trouve or 'escalade'}")
    return "\n".join(lignes)


def main(arguments: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(prog="python -m coeur.connaissances.evaluation")
    analyseur.add_argument("fichier", type=Path, help="CSV : langue, question, attendu")
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
    print("\n\n".join(rapport(evaluer(corpus, cas, reglages, s), s, args.details)
                      for s in seuils))
    return 0


if __name__ == "__main__":
    sys.exit(main())
