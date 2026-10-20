from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.commun import Canal
from coeur.config import Parametres, parametres
from coeur.securite import acces_ministere, canal_appelant
from coeur.signalements import service
from coeur.signalements.schemas import (
    ChangementStatut,
    SignalementCree,
    SignalementEntree,
    SignalementSortie,
    StatutSignalement,
)
from coeur.territoires.service import territoire_existe

# 422 : écrit en clair, le nom de la constante a changé selon les versions de Starlette.
ENTITE_INVALIDE = 422

routeur = APIRouter(prefix="/v1/signalements", tags=["signalements"])


@routeur.post("", response_model=SignalementCree, status_code=status.HTTP_201_CREATED)
def creer_signalement(
    entree: SignalementEntree,
    canal: Canal = Depends(canal_appelant),
    session: Session = Depends(session_db),
    reglages: Parametres = Depends(parametres),
):
    if not territoire_existe(session, entree.territoire_code):
        raise HTTPException(ENTITE_INVALIDE, "Territoire inconnu")
    signalement = service.creer(session, entree, canal, reglages.pepper_telephone)
    return SignalementCree(id=signalement.id, statut=signalement.statut)


@routeur.get("", response_model=list[SignalementSortie], dependencies=[Depends(acces_ministere)])
def lister_signalements(
    territoire_code: str | None = None,
    statut: StatutSignalement | None = None,
    limite: int = Query(default=100, ge=1, le=1000),
    decalage: int = Query(default=0, ge=0),
    session: Session = Depends(session_db),
):
    """Réservé au Ministère : suivi opérationnel des signalements."""
    return service.lister(session, territoire_code, statut, limite, decalage)


@routeur.patch(
    "/{signalement_id}", response_model=SignalementSortie, dependencies=[Depends(acces_ministere)]
)
def modifier_statut(
    signalement_id: int, entree: ChangementStatut, session: Session = Depends(session_db)
):
    signalement = service.changer_statut(session, signalement_id, entree.statut)
    if signalement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Signalement introuvable")
    return signalement
