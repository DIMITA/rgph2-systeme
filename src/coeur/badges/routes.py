from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from coeur.badges.schemas import BadgeEntree, BadgeSortie
from coeur.badges.service import verifier
from coeur.base import session_db
from coeur.commun import Canal
from coeur.config import Parametres, parametres
from coeur.mobile import service as mobile
from coeur.securite import canal_appelant

ENTITE_INVALIDE = 422
TROP_DE_REQUETES = 429

routeur = APIRouter(prefix="/v1/badges", tags=["badges"])


@routeur.post("/verification", response_model=BadgeSortie)
def verifier_badge(
    entree: BadgeEntree,
    canal: Canal = Depends(canal_appelant),
    session: Session = Depends(session_db),
    reglages: Parametres = Depends(parametres),
):
    """Un badge est-il valide ? Pour les canaux autres que l'USSD et le SMS (WhatsApp…).

    Avec un numéro de téléphone, les essais sont plafonnés (BADGES_VERIFICATIONS_PAR_HEURE).
    """
    try:
        if entree.telephone:
            u = mobile.usager(session, canal, entree.telephone, reglages)
            v = mobile.verifier_badge(session, u, entree.numero, reglages)
        else:
            v = verifier(session, entree.numero, reglages.pepper_telephone)
    except ValueError as erreur:
        raise HTTPException(ENTITE_INVALIDE, str(erreur)) from erreur
    except mobile.TropDeVerifications as erreur:
        raise HTTPException(TROP_DE_REQUETES, "Trop de vérifications, réessayer plus tard") from erreur
    return BadgeSortie(statut=v.statut, territoire_code=v.territoire_code,
                       territoire_nom=v.territoire_nom)
