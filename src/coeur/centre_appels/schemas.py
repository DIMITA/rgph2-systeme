from typing import Literal

from pydantic import BaseModel, Field, field_validator

from coeur.commun import SchemaEntree

TypeEvenement = Literal[
    "debut", "langue", "svi_ecoute", "file_entree", "decroche", "rappel", "fin",
    # Réponse du citoyen au sujet compris d'une question dite (touche 1 : oui).
    "vocal_confirme",
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
    # Touche tapée après « Vous voulez savoir : … ? » (1 : oui ; autre ou rien : non).
    touche: str | None = Field(default=None, pattern=r"^[0-9*#]$")

    @field_validator("numero", "langue", "contenu_id", "poste", "fichier", "touche",
                     mode="before")
    @classmethod
    def _vide_vaut_none(cls, valeur):
        return None if valeur == "" else valeur


class ReponseAudio(BaseModel):
    contenu_id: int
    cle: str
    # Langue du texte servi (« fr » si la langue demandée n'a pas encore de version validée).
    langue: str
    repli_langue: bool
    question: str
    reponse: str
    audio_url: str | None
    audio_question_url: str | None


class ElementMenu(ReponseAudio):
    touche: int


class LangueMenu(BaseModel):
    code: str
    nom: str
    touche: int


class MenuSvi(BaseModel):
    langues: list[LangueMenu]
    # Code de langue → éléments du menu, touches 1 à 8 (0 = conseiller).
    menus: dict[str, list[ElementMenu]]
    # Langues où le citoyen peut dire sa question (touche 9), et pour chacune toutes
    # les réponses publiées qu'elle peut faire entendre, menu ou non.
    vocal: list[str] = []
    catalogue: dict[str, list[ReponseAudio]] = {}


class QuestionVocale(BaseModel):
    """« proposition » : faire confirmer `contenu_id` ; « conseiller » : passer la main."""

    issue: Literal["proposition", "conseiller"]
    contenu_id: int | None = None
