"""API des appareils de terrain. Authentification : `Authorization: Bearer <jeton>`."""

from functools import lru_cache

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from coeur.badges import service as badges
from coeur.badges.schemas import BadgeSortie
from coeur.base import session_db
from coeur.config import Parametres, parametres
from coeur.connaissances.depot import Corpus
from coeur.connaissances.routes import corpus_courant
from coeur.limiteur import LimiteurDebit
from coeur.mobile.modeles import Consultation
from coeur.terrain import service
from coeur.terrain.modeles import Appareil
from coeur.terrain.schemas import (
    ActivationEntree,
    ActivationSortie,
    BadgeTerrain,
    PaquetSortie,
    RemonteesSortie,
)

routeur = APIRouter(prefix="/v1/terrain", tags=["kiosques et Ambassadeurs"])


@lru_cache
def limiteurs() -> tuple[LimiteurDebit, LimiteurDebit]:
    """(essais d'activation par adresse IP, vérifications de badge par appareil)."""
    reglages = parametres()
    return (LimiteurDebit("terrain_activation", 10, 15 * 60),
            LimiteurDebit("terrain_badges", reglages.badges_verifications_par_heure, 3600))


def appareil_connecte(
    authorization: str | None = Header(default=None),
    session: Session = Depends(session_db),
) -> Appareil:
    jeton = (authorization or "").removeprefix("Bearer ").strip()
    appareil = service.par_jeton(session, jeton) if jeton else None
    if appareil is None:
        # 401 : jeton inconnu ou révoqué. L'application redemande alors un code d'activation.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Appareil inconnu ou révoqué",
                            headers={"WWW-Authenticate": "Bearer"})
    return appareil


@routeur.post("/activation", response_model=ActivationSortie)
def activer(entree: ActivationEntree, request: Request, session: Session = Depends(session_db)):
    """Échange le code d'activation remis par le Ministère contre le jeton de l'appareil."""
    adresse = request.client.host if request.client else "inconnue"
    if not limiteurs()[0].autoriser(adresse):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Trop d'essais. Réessayez dans un quart d'heure.")
    jeton = service.activer(session, entree.code)
    if jeton is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code d'activation invalide ou expiré")
    return ActivationSortie(jeton=jeton)


@routeur.get("/paquet", response_model=PaquetSortie,
             responses={304: {"description": "Le paquet de l'appareil est à jour"}})
def paquet(
    response: Response,
    if_none_match: str | None = Header(default=None),
    appareil: Appareil = Depends(appareil_connecte),
    session: Session = Depends(session_db),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
):
    """FAQ publiée, calendrier et territoires, à garder hors ligne.

    Renvoyer l'ETag reçu dans `If-None-Match` : 304 sans corps si rien n'a changé,
    ce qui économise la bande passante des zones mal couvertes.
    """
    contenu = service.paquet(session, corpus, reglages, appareil)
    service.noter_synchronisation(session, appareil, contenu.version)
    etag = f'"{contenu.version}"'
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "no-store"
    return contenu


@routeur.post("/remontees", response_model=RemonteesSortie)
def remontees(
    elements: list = Body(max_length=service.REMONTEES_PAR_ENVOI),
    appareil: Appareil = Depends(appareil_connecte),
    session: Session = Depends(session_db),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
):
    """Ce que l'appareil a recueilli hors ligne, par lots de 200 au plus.

    Chaque élément porte un identifiant (UUID) tiré par l'appareil : renvoyer un lot
    dont la réponse s'est perdue ne crée aucun doublon.
    """
    return service.recevoir(session, corpus, reglages, appareil, elements)


@routeur.post("/badge", response_model=BadgeSortie)
def verifier_badge(
    entree: BadgeTerrain,
    appareil: Appareil = Depends(appareil_connecte),
    session: Session = Depends(session_db),
    reglages: Parametres = Depends(parametres),
):
    """Vérification d'un badge, en ligne seulement : la liste ne quitte jamais le serveur.

    Plafonnée par appareil (BADGES_VERIFICATIONS_PAR_HEURE), contre l'essai de numéros.
    """
    try:
        badges.normaliser_badge(entree.numero)
    except ValueError as erreur:
        raise HTTPException(422, "Numéro de badge invalide") from erreur
    if not limiteurs()[1].autoriser(str(appareil.id)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Trop de vérifications")
    v = badges.verifier(session, entree.numero, reglages.pepper_telephone)
    session.add(Consultation(canal=appareil.type, service="badge", resultat=v.statut,
                             langue=entree.langue, territoire_code=v.territoire_code))
    session.commit()
    return BadgeSortie(statut=v.statut, territoire_code=v.territoire_code,
                       territoire_nom=v.territoire_nom)
