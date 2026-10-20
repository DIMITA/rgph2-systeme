"""Authentification des appelants : une clé d'API par canal, une clé pour le Ministère."""

import hmac

from fastapi import Depends, Header, HTTPException, Query, status

from coeur.commun import Canal
from coeur.config import Parametres, parametres

EN_TETE = "X-Cle-API"


def _canal(cle: str | None, reglages: Parametres) -> Canal:
    if cle:
        for cle_connue, canal in reglages.cles_par_canal().items():
            if hmac.compare_digest(cle.encode(), cle_connue.encode()):
                return canal
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Clé d'API de canal invalide")


def canal_appelant(
    cle: str | None = Header(default=None, alias=EN_TETE),
    reglages: Parametres = Depends(parametres),
) -> Canal:
    """Identifie le canal à partir de sa clé. Refuse toute clé inconnue."""
    return _canal(cle, reglages)


def passerelle(attendu: Canal):
    """Dépendance des passerelles d'opérateur (USSD, SMS).

    Elles ne savent souvent pas ajouter d'en-tête : la clé est alors acceptée dans
    l'adresse (`?cle=…`). Seule la clé du canal attendu est admise.
    """
    def dependance(
        cle_entete: str | None = Header(default=None, alias=EN_TETE),
        cle: str | None = Query(default=None),
        reglages: Parametres = Depends(parametres),
    ) -> Canal:
        canal = _canal(cle_entete or cle, reglages)
        if canal is not attendu:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Réservé à la passerelle {attendu.value}")
        return canal

    return dependance


def acces_ministere(
    cle: str | None = Header(default=None, alias=EN_TETE),
    reglages: Parametres = Depends(parametres),
) -> None:
    if not cle or not hmac.compare_digest(cle.encode(), reglages.cle_ministere.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Clé d'API du Ministère requise")
