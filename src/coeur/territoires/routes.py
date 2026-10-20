from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.territoires import service
from coeur.territoires.schemas import ProvinceSortie

routeur = APIRouter(prefix="/v1/territoires", tags=["territoires"])


@routeur.get("", response_model=list[ProvinceSortie])
def lister_territoires(session: Session = Depends(session_db)):
    """Référentiel public : provinces et leurs territoires."""
    return service.lister(session)
