from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.commun import Canal
from coeur.config import Parametres, parametres
from coeur.connaissances.depot import Corpus
from coeur.connaissances.routes import corpus_courant
from coeur.securite import passerelle
from coeur.sms import service

routeur = APIRouter(prefix="/v1/sms", tags=["SMS"])


@routeur.api_route("/entrant", methods=["GET", "POST"], response_class=PlainTextResponse,
                   dependencies=[Depends(passerelle(Canal.SMS))])
def sms_entrant(
    de: str = Query(max_length=30),
    texte: str = Query(default="", max_length=1600),
    session: Session = Depends(session_db),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
):
    """SMS reçu, transmis par Kannel (`get-url`). La réponse part par SMS, pas dans ce corps."""
    service.recevoir(session, corpus, reglages, de, texte)
    return ""
