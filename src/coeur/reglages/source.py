"""Lecture des réglages chiffrés, branchée dans `coeur.config.Parametres`.

Ce module n'importe rien du cœur : `config` l'importe, il doit rester à la base.
"""

import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from dotenv import dotenv_values
from pydantic.fields import FieldInfo
from pydantic_settings import PydanticBaseSettingsSource
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

journal = logging.getLogger(__name__)
TABLE = "coeur.reglages"


class CleMaitreInvalide(RuntimeError):
    pass


def cle_maitre() -> str | None:
    """CLE_MAITRE : variable d'environnement, sinon fichier .env (développement)."""
    return os.environ.get("CLE_MAITRE") or dotenv_values(".env").get("CLE_MAITRE") or None


def chiffreur(cle: str) -> Fernet:
    try:
        return Fernet(cle.encode())
    except ValueError as erreur:
        raise CleMaitreInvalide("CLE_MAITRE n'est pas une clé Fernet (44 caractères)") from erreur


def lire(database_url: str, cle: str) -> dict[str, str]:
    """Tous les réglages en base, déchiffrés. {} si la table n'existe pas encore."""
    moteur = create_engine(database_url, pool_pre_ping=False)
    try:
        with moteur.connect() as connexion:
            lignes = connexion.execute(text(f"SELECT cle, valeur FROM {TABLE}")).all()
    except DBAPIError as erreur:
        # Avant les migrations, ou base injoignable : les champs obligatoires manquants
        # le diront plus clairement qu'ici.
        journal.warning("Réglages en base illisibles : %s", type(erreur.orig).__name__)
        return {}
    finally:
        moteur.dispose()
    fernet = chiffreur(cle)
    try:
        return {nom: fernet.decrypt(valeur.encode()).decode() for nom, valeur in lignes}
    except InvalidToken as erreur:
        raise CleMaitreInvalide(
            "CLE_MAITRE ne déchiffre pas les réglages en base : mauvaise clé ?") from erreur


class SourceReglages(PydanticBaseSettingsSource):
    """Source de réglages après l'environnement et le .env : ceux-ci l'emportent."""

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[None, str, bool]:
        return None, field_name, False  # tout est lu d'un coup dans __call__

    def __call__(self) -> dict[str, str]:
        cle = cle_maitre()
        url = self.current_state.get("database_url")
        if not cle or not url:
            return {}
        connus = self.settings_cls.model_fields
        return {nom: valeur for nom, valeur in lire(url, cle).items() if nom in connus}
