from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.config import Parametres, parametres
from coeur.securite import acces_ministere
from coeur.statistiques import service
from coeur.statistiques.schemas import Niveau, StatistiquesSortie

routeur = APIRouter(
    prefix="/v1/statistiques", tags=["statistiques"], dependencies=[Depends(acces_ministere)]
)


@routeur.get("", response_model=StatistiquesSortie)
def statistiques(
    niveau: Niveau = Niveau.NATIONAL,
    depuis: date | None = None,
    jusqu_a: date | None = None,
    session: Session = Depends(session_db),
    reglages: Parametres = Depends(parametres),
):
    """Usage par canal, langue et unité. Maille la plus fine : le territoire."""
    return service.calculer(session, niveau, depuis, jusqu_a, reglages.seuil_secret_statistique)
