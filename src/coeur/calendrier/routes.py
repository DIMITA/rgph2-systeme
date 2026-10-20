from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.calendrier.schemas import CalendrierSortie, PeriodeSortie
from coeur.calendrier.service import passages_publies
from coeur.commun import Canal
from coeur.securite import canal_appelant
from coeur.territoires.modeles import Territoire

routeur = APIRouter(prefix="/v1/calendrier", tags=["calendrier"])


@routeur.get("/{territoire_code}", response_model=CalendrierSortie)
def calendrier(
    territoire_code: str,
    _canal: Canal = Depends(canal_appelant),
    session: Session = Depends(session_db),
):
    """Dates de passage validées par le BCR pour un territoire."""
    territoire = session.get(Territoire, territoire_code)
    if territoire is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Territoire inconnu")
    return CalendrierSortie(
        territoire_code=territoire.code, territoire_nom=territoire.nom,
        passages=[PeriodeSortie(date_debut=p.date_debut, date_fin=p.date_fin)
                  for p in passages_publies(session, territoire.code)],
    )
