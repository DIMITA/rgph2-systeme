"""Lecture des contenus publiés dans le CMS, gardés en mémoire quelques secondes."""

import threading
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from coeur.connaissances.modeles import STATUT_PUBLIE, Contenu, Formulation, Traduction
from coeur.connaissances.moteur import Entree, MoteurLexical, MoteurRecherche


@dataclass(frozen=True)
class TextePublie:
    contenu_id: int
    cle: str
    categorie: str
    langue: str
    question: str
    reponse: str
    reponse_courte: str | None
    audio_url: str | None
    audio_question_url: str | None = None


@dataclass(frozen=True)
class Corpus:
    moteur: MoteurRecherche
    # (contenu_id, langue) -> texte. Ne contient que les traductions publiées
    # de contenus eux-mêmes publiés : c'est la seule source de réponses.
    textes: dict[tuple[int, str], TextePublie]

    def ids_contenus(self) -> list[int]:
        return sorted({cid for cid, _ in self.textes})


def charger_corpus(session: Session) -> Corpus:
    lignes = session.execute(
        select(Traduction, Contenu)
        .join(Contenu, Traduction.contenu_id == Contenu.id)
        .where(Contenu.statut == STATUT_PUBLIE, Traduction.statut == STATUT_PUBLIE)
    ).all()
    textes = {
        (c.id, t.langue_code): TextePublie(
            contenu_id=c.id,
            cle=c.cle,
            categorie=c.categorie,
            langue=t.langue_code,
            question=t.question,
            reponse=t.reponse,
            reponse_courte=t.reponse_courte,
            audio_url=t.audio_url,
            audio_question_url=t.audio_question_url,
        )
        for t, c in lignes
    }
    servables = {cid for cid, _ in textes}
    entrees = [Entree(t.contenu_id, t.langue, t.question) for t in textes.values()]
    formulations = session.scalars(
        select(Formulation).where(Formulation.contenu_id.in_(servables))
    ).all()
    entrees += [Entree(f.contenu_id, f.langue_code, f.texte) for f in formulations]
    return Corpus(moteur=MoteurLexical(entrees), textes=textes)


class CacheCorpus:
    """Évite de relire la base à chaque question ; une modification dans Directus
    est prise en compte au plus tard après `duree` secondes."""

    def __init__(self) -> None:
        self._corpus: Corpus | None = None
        self._charge_a = 0.0
        self._verrou = threading.Lock()

    def obtenir(self, session: Session, duree: float) -> Corpus:
        with self._verrou:
            if self._corpus is None or time.monotonic() - self._charge_a >= duree:
                self._corpus = charger_corpus(session)
                self._charge_a = time.monotonic()
            return self._corpus

    def invalider(self) -> None:
        with self._verrou:
            self._corpus = None


cache = CacheCorpus()
