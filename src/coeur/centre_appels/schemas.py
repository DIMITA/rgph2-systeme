from typing import Literal

from pydantic import BaseModel, Field, field_validator

from coeur.commun import SchemaEntree

TypeEvenement = Literal[
    "debut", "langue", "svi_ecoute", "file_entree", "decroche", "rappel", "fin"
]


class EvenementAppel(SchemaEntree):
    """Étape d'un appel, envoyée par Asterisk (formulaire HTTP, fonction CURL du dialplan).

    Asterisk envoie une chaîne vide pour une variable non définie : elle vaut None ici.
    """

    type: TypeEvenement
    appel: str = Field(max_length=64, pattern=r"^[\w.\-]+$")
    numero: str | None = Field(default=None, max_length=32)
    langue: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")
    contenu_id: int | None = None
    poste: str | None = Field(default=None, max_length=32, pattern=r"^[\w\-]+$")
    # Nom simple, sans dossier : impossible d'écrire ou de supprimer ailleurs.
    fichier: str | None = Field(default=None, max_length=200, pattern=r"^[\w\-.]+\.wav$")

    @field_validator("numero", "langue", "contenu_id", "poste", "fichier", mode="before")
    @classmethod
    def _vide_vaut_none(cls, valeur):
        return None if valeur == "" else valeur


class ElementMenu(BaseModel):
    touche: int
    contenu_id: int
    cle: str
    # Langue du texte servi (« fr » si la langue demandée n'a pas encore de version validée).
    langue: str
    repli_langue: bool
    question: str
    reponse: str
    audio_url: str | None
    audio_question_url: str | None


class LangueMenu(BaseModel):
    code: str
    nom: str
    touche: int


class MenuSvi(BaseModel):
    langues: list[LangueMenu]
    # Code de langue → éléments du menu, touches 1 à 8 (0 = conseiller).
    menus: dict[str, list[ElementMenu]]
