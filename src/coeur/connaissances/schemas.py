from typing import Literal

from pydantic import BaseModel, Field, field_validator

from coeur.commun import SchemaEntree
from coeur.confidentialite.service import normaliser_telephone

MESSAGE_ESCALADE = "escalade vers un humain"

MotifEscalade = Literal[
    "aucune_reponse_validee", "ambigu", "demande_humain", "traduction_indisponible",
    # Question recueillie hors ligne (kiosque, Ambassadeur) : jamais passée par le moteur.
    "remontee_terrain",
    # Message vocal : le citoyen a répondu « Non » au sujet compris.
    "vocal_non_confirme",
]


class QuestionEntree(SchemaEntree):
    texte: str = Field(min_length=1, max_length=500)
    langue: str = Field(default="fr", pattern=r"^[a-z]{2,3}$")
    territoire_code: str | None = Field(default=None, max_length=16)
    # Sert seulement à calculer une empreinte ; jamais enregistré tel quel.
    telephone: str | None = Field(default=None, max_length=20)

    @field_validator("telephone")
    @classmethod
    def _telephone_valide(cls, valeur: str | None) -> str | None:
        if valeur is not None:
            normaliser_telephone(valeur)
        return valeur


class ContenuSortie(BaseModel):
    contenu_id: int
    cle: str
    categorie: str
    langue: str
    # Vrai si le contenu n'existe pas (encore validé) dans la langue demandée
    # et qu'il est servi en français.
    repli_langue: bool
    question: str
    reponse: str
    reponse_courte: str | None
    audio_url: str | None
    audio_question_url: str | None = None
    video_url: str | None = None


class ReponseSortie(BaseModel):
    type: Literal["reponse", "escalade"]
    contenu: ContenuSortie | None = None
    message: str | None = None
    motif: MotifEscalade | None = None
    score: float
