"""API réservée au serveur téléphonique (clé du canal centre_ecoute)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.centre_appels import service
from coeur.centre_appels.schemas import EvenementAppel, MenuSvi
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
