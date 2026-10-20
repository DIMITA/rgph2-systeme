"""Authentification des appelants : une clé d'API par canal, une clé pour le Ministère."""

import hmac

from fastapi import Depends, Header, HTTPException, status

from coeur.commun import Canal
from coeur.config import Parametres, parametres

EN_TETE = "X-Cle-API"


def canal_appelant(
    cle: str | None = Header(default=None, alias=EN_TETE),
    reglages: Parametres = Depends(parametres),
) -> Canal:
    """Identifie le canal à partir de sa clé. Refuse toute clé inconnue."""
    if cle:
        for cle_connue, canal in reglages.cles_par_canal().items():
            if hmac.compare_digest(cle.encode(), cle_connue.encode()):
                return canal
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Clé d'API de canal invalide")


def acces_ministere(
    cle: str | None = Header(default=None, alias=EN_TETE),
    reglages: Parametres = Depends(parametres),
) -> None:
    if not cle or not hmac.compare_digest(cle.encode(), reglages.cle_ministere.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Clé d'API du Ministère requise")
