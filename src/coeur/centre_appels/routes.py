"""API réservée au serveur téléphonique (clé du canal centre_ecoute)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from coeur.base import session_db
from coeur.centre_appels import service
from coeur.centre_appels.schemas import EvenementAppel, MenuSvi, QuestionVocale
from coeur.commun import Canal
from coeur.config import Parametres, parametres
from coeur.connaissances.depot import Corpus
from coeur.connaissances.routes import corpus_courant
from coeur.securite import canal_appelant

routeur = APIRouter(prefix="/v1/appels", tags=["centre d'appels"])


def canal_centre_ecoute(canal: Canal = Depends(canal_appelant)) -> Canal:
    if canal is not Canal.CENTRE_ECOUTE:
        raise HTTPException(403, "Réservé au serveur téléphonique (canal centre_ecoute)")
    return canal


@routeur.get("/svi", response_model=MenuSvi, dependencies=[Depends(canal_centre_ecoute)])
def menu_svi(
    session: Session = Depends(session_db),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
):
    """Menu du serveur vocal : uniquement des contenus publiés (validés BCR)."""
    return service.menu_svi(session, corpus, reglages)


@routeur.post("/evenements", dependencies=[Depends(canal_centre_ecoute)])
def evenement(
    ev: Annotated[EvenementAppel, Form()],
    session: Session = Depends(session_db),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
) -> dict:
    """Étape d'un appel : début, langue, réponse écoutée, file, décroché, rappel, fin."""
    return service.traiter_evenement(session, corpus, reglages, ev)


@routeur.post("/question-vocale", response_model=QuestionVocale,
              dependencies=[Depends(canal_centre_ecoute)])
async def question_vocale(
    request: Request,
    appel: str = Query(max_length=64, pattern=r"^[\w.\-]+$"),
    langue: str = Query(pattern=r"^[a-z]{2,3}$"),
    session: Session = Depends(session_db),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
):
    """Question dite au SVI (corps : l'enregistrement). Le sujet compris est renvoyé pour
    confirmation par le citoyen ; rien n'est répondu ici."""
    audio = await request.body()
    if len(audio) > reglages.transcription_taille_max_ko * 1024:
        raise HTTPException(413, "Enregistrement trop long")
    # Transcription : plusieurs secondes, hors de la boucle asynchrone.
    return await run_in_threadpool(
        service.question_vocale, session, corpus, reglages, appel, langue, audio,
        request.headers.get("content-type", "audio/wav"))
