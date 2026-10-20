"""Types partagés par tous les modules."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Canal(StrEnum):
    USSD = "ussd"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    WEB = "web"
    KIOSQUE = "kiosque"
    AMBASSADEUR = "ambassadeur"
    CENTRE_ECOUTE = "centre_ecoute"


class SchemaEntree(BaseModel):
    """Base de tous les corps de requête.

    `extra="forbid"` : tout champ non prévu (nom, pièce d'identité…) est refusé.
    C'est une garantie technique qu'aucune donnée personnelle non prévue n'entre.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
