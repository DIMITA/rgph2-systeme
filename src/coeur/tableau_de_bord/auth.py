"""Connexion au tableau de bord avec les comptes Directus.

Les comptes sont créés et désactivés par le Ministère dans Directus : il n'y a
pas de second annuaire. L'identifiant et le mot de passe sont vérifiés auprès
de Directus, puis le rôle est comparé à ROLES_TABLEAU_DE_BORD. Le jeton
Directus n'est pas conservé : seule une session signée (cookie) l'est, valable
DUREE_SESSION. Un compte désactivé dans Directus garde donc l'accès jusqu'à
l'expiration de sa session.
"""

from dataclasses import dataclass
from typing import Protocol

import httpx
from fastapi import HTTPException, Request

from coeur.config import parametres

DUREE_SESSION = 8 * 3600
CHEMIN = "/tableau-de-bord"


@dataclass(frozen=True)
class Utilisateur:
    email: str
    role: str | None


class Authentificateur(Protocol):
    def verifier(self, email: str, mdp: str) -> Utilisateur | None:
        """Renvoie l'utilisateur si l'identifiant et le mot de passe sont bons, sinon None."""
        ...


class AuthDirectus:
    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def verifier(self, email: str, mdp: str) -> Utilisateur | None:
        try:
            r = httpx.post(f"{self.url}/auth/login", json={"email": email, "password": mdp},
                           timeout=10)
            if r.status_code != 200:
                return None
            jeton = r.json()["data"]["access_token"]
            moi = httpx.get(f"{self.url}/users/me", params={"fields": "email,role.name"},
                            headers={"Authorization": f"Bearer {jeton}"}, timeout=10)
            moi.raise_for_status()
        except httpx.HTTPError as erreur:
            raise HTTPException(503, "Service d'authentification indisponible") from erreur
        donnees = moi.json()["data"]
        role = (donnees.get("role") or {}).get("name")
        return Utilisateur(email=donnees["email"], role=role)


def authentificateur() -> Authentificateur:
    """Dépendance FastAPI (remplacée par un faux dans les tests)."""
    return AuthDirectus(parametres().directus_url)


def utilisateur_connecte(request: Request) -> Utilisateur:
    """Dépendance des pages protégées : renvoie vers la connexion si besoin."""
    session = request.session
    if not session.get("email"):
        raise HTTPException(303, headers={"Location": f"{CHEMIN}/connexion"})
    return Utilisateur(email=session["email"], role=session.get("role"))
