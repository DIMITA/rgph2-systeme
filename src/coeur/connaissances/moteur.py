"""Recherche du contenu validé le plus proche d'une question.

Ce moteur ne génère aucun texte : il ne fait que *choisir* parmi les contenus
publiés, et dit à quel point il est sûr de son choix. Le service décide ensuite
de répondre ou d'escalader vers un humain.

Le moteur lexical ci-dessous compare les mots de la question à ceux des
questions et formulations enregistrées dans le CMS, en tolérant les variantes
(pluriels, conjugaisons, fautes de frappe légères) et en donnant moins de poids
aux mots présents partout (« recensement »). Un autre moteur (par exemple
Rasa, une fois évalué langue par langue) peut le remplacer s'il respecte
l'interface `MoteurRecherche`.
"""

import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

# Mots trop fréquents pour aider à choisir un contenu.
MOTS_VIDES = frozenset(
    """
    a ai as au aux avec c ca ce ces cet cette d de des du elle elles en est et etre
    il ils j je l la le les leur leurs lui m ma me mes moi mon n ne nos notre nous
    on ont ou par pas pour qu que s sa se ses si son sont sur t ta te tes toi ton
    tu un une va vais vont vos votre vous y est-ce estce cela suis sera seront
    """.split()
)

# Expressions par lesquelles un usager demande explicitement à parler à quelqu'un.
_DEMANDE_HUMAIN = re.compile(
    r"\b(humain|conseiller|conseillere|operateur|operatrice|parler a (une? )?(personne|quelqu))"
)


@dataclass(frozen=True)
class Entree:
    """Un texte cherchable rattaché à un contenu : sa question ou une formulation."""

    contenu_id: int
    langue: str
    texte: str


@dataclass(frozen=True)
class Candidat:
    contenu_id: int
    score: float


class MoteurRecherche(Protocol):
    def rechercher(self, texte: str, langues: Sequence[str]) -> list[Candidat]:
        """Renvoie les contenus classés du plus au moins probable (score entre 0 et 1)."""
        ...


def normaliser(texte: str) -> str:
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", " ", sans_accents.lower()).strip()


def mots_significatifs(texte: str) -> list[str]:
    return [m for m in normaliser(texte).split() if len(m) >= 2 and m not in MOTS_VIDES]


def demande_humain(texte: str) -> bool:
    return bool(_DEMANDE_HUMAIN.search(normaliser(texte)))


def _trigrammes(mot: str) -> frozenset[str]:
    m = f"  {mot} "
    return frozenset(m[i : i + 3] for i in range(len(m) - 2))


@lru_cache(maxsize=100_000)
def similarite_mots(a: str, b: str) -> float:
    """1 si identiques, 0,9 si même racine apparente, sinon similarité de trigrammes."""
    if a == b:
        return 1.0
    prefixe = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        prefixe += 1
    if prefixe >= max(4, 0.5 * min(len(a), len(b))):
        return 0.9
    if min(len(a), len(b)) < 5:
        return 0.0
    ta, tb = _trigrammes(a), _trigrammes(b)
    jaccard = len(ta & tb) / len(ta | tb)
    return jaccard if jaccard >= 0.5 else 0.0


class MoteurLexical:
    def __init__(self, entrees: Iterable[Entree]):
        self._entrees = [(e, mots_significatifs(e.texte)) for e in entrees]
        # Poids d'un mot : d'autant plus faible qu'il apparaît dans beaucoup de contenus.
        contenus_par_mot: dict[str, set[int]] = {}
        for entree, mots in self._entrees:
            for mot in mots:
                contenus_par_mot.setdefault(mot, set()).add(entree.contenu_id)
        nb_contenus = len({e.contenu_id for e, _ in self._entrees}) or 1
        self._poids = {
            mot: math.log(1 + nb_contenus / len(ids)) for mot, ids in contenus_par_mot.items()
        }
        self._poids_max = math.log(1 + nb_contenus)

    def _poids_mot(self, mot: str) -> float:
        return self._poids.get(mot, self._poids_max)

    def _couverture(self, mots: list[str], autres: list[str]) -> float:
        """Part (pondérée) des `mots` retrouvés dans `autres`."""
        total = sum(self._poids_mot(m) for m in mots)
        if not total:
            return 0.0
        trouves = sum(
            self._poids_mot(m) * max((similarite_mots(m, a) for a in autres), default=0.0)
            for m in mots
        )
        return trouves / total

    def _score(self, question: list[str], reference: list[str]) -> float:
        rappel = self._couverture(reference, question)
        precision = self._couverture(question, reference)
        if not rappel or not precision:
            return 0.0
        return 2 * rappel * precision / (rappel + precision)

    def rechercher(self, texte: str, langues: Sequence[str]) -> list[Candidat]:
        question = mots_significatifs(texte)
        if not question:
            return []
        meilleurs: dict[int, float] = {}
        for entree, reference in self._entrees:
            if entree.langue not in langues or not reference:
                continue
            score = self._score(question, reference)
            if score > meilleurs.get(entree.contenu_id, 0.0):
                meilleurs[entree.contenu_id] = score
        return sorted(
            (Candidat(cid, round(s, 4)) for cid, s in meilleurs.items()),
            key=lambda c: c.score,
            reverse=True,
        )


@dataclass(frozen=True)
class Decision:
    contenu_id: int | None
    score: float
    motif_escalade: str | None = None


def decider(candidats: Sequence[Candidat], seuil: float, marge: float) -> Decision:
    """Répondre seulement si le meilleur contenu est sûr et nettement devant le suivant."""
    if not candidats or candidats[0].score < seuil:
        meilleur = candidats[0].score if candidats else 0.0
        return Decision(None, meilleur, "aucune_reponse_validee")
    premier = candidats[0]
    if len(candidats) > 1 and premier.score - candidats[1].score < marge:
        return Decision(None, premier.score, "ambigu")
    return Decision(premier.contenu_id, premier.score)
