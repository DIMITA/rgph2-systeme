"""Paramètres de l'application, lus dans les variables d'environnement (ou le fichier .env)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from coeur.commun import Canal


class Parametres(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environnement: str = "developpement"

    # Connexion de l'API (rôle rgph_api : lecture seule sur les contenus du CMS).
    database_url: str

    # Clé secrète servant à calculer l'empreinte des numéros de téléphone.
    # La perdre empêche de relier les nouvelles interactions aux anciennes ;
    # la divulguer permet de retrouver un numéro par essais successifs.
    pepper_telephone: str = Field(min_length=32)

    # Une clé par canal, au format "canal:cle,canal:cle".
    cles_api: str = ""
    # Clé réservée au Ministère (statistiques, liste des signalements).
    cle_ministere: str = Field(min_length=16)

    # Base de connaissances fermée : en dessous de ce score, on escalade vers un humain.
    seuil_confiance: float = 0.5
    # Si deux contenus différents ont des scores plus proches que cette marge, on escalade.
    marge_ambiguite: float = 0.1
    # Toute case statistique strictement inférieure à ce seuil (et non nulle) est masquée.
    seuil_secret_statistique: int = 5
    # Durée pendant laquelle les contenus publiés restent en mémoire avant relecture.
    cache_contenus_secondes: int = 60
    langue_par_defaut: str = "fr"

    def cles_par_canal(self) -> dict[str, Canal]:
        """Associe chaque clé d'API au canal qu'elle identifie."""
        resultat: dict[str, Canal] = {}
        for paire in filter(None, (p.strip() for p in self.cles_api.split(","))):
            canal, _, cle = paire.partition(":")
            if not cle:
                raise ValueError(f"Entrée CLES_API invalide : {paire!r} (attendu canal:cle)")
            resultat[cle.strip()] = Canal(canal.strip())
        return resultat


@lru_cache
def parametres() -> Parametres:
    return Parametres()
