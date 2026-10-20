from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from coeur.commun import SchemaEntree
from coeur.connaissances.schemas import ContenuSortie
from coeur.signalements.schemas import TypeSignalement
from coeur.territoires.schemas import ProvinceSortie

# Identifiant tiré au hasard par l'appareil (UUID), pour ne jamais enregistrer deux fois.
Identifiant = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
Langue = Annotated[str, Field(pattern=r"^[a-z]{2,3}$")]


class ActivationEntree(SchemaEntree):
    code: str = Field(min_length=6, max_length=40)


class ActivationSortie(BaseModel):
    # Montré une seule fois : l'appareil le garde, le serveur n'en garde que l'empreinte.
    jeton: str


class BadgeTerrain(SchemaEntree):
    numero: str = Field(max_length=40)
    langue: Langue = "fr"


class _Remontee(SchemaEntree):
    id: Identifiant
    # Heure de l'appareil. Ramenée à l'heure de réception si elle est invraisemblable.
    horodatage: datetime | None = None


class Consultation(_Remontee):
    """Une réponse de la FAQ ouverte sur l'appareil."""

    type: Literal["consultation"]
    contenu_id: int
    langue: Langue


class Question(_Remontee):
    """Question restée sans réponse (kiosque) ou doute recueilli par un Ambassadeur."""

    type: Literal["question"]
    texte: str = Field(min_length=1, max_length=500)
    langue: Langue


class Signalement(_Remontee):
    type: Literal["signalement"]
    signalement: TypeSignalement
    territoire_code: str = Field(max_length=16)
    localite: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class Passage(_Remontee):
    """Date de passage consultée sur l'appareil."""

    type: Literal["passage"]
    territoire_code: str = Field(max_length=16)
    langue: Langue
    resultat: Literal["trouve", "non_publie"]


Remontee = Annotated[Consultation | Question | Signalement | Passage, Field(discriminator="type")]


class Rejet(BaseModel):
    id: str | None
    raison: str


class RemonteesSortie(BaseModel):
    """`acceptes` : enregistrées maintenant ou déjà reçues. L'appareil les oublie, ainsi
    que les rejetées : une remontée invalide ne deviendra pas valide en la renvoyant."""

    acceptes: list[str]
    rejetes: list[Rejet]


class LangueSortie(BaseModel):
    code: str
    nom: str


class PeriodeSortie(BaseModel):
    territoire_code: str
    debut: date
    fin: date


class AppareilSortie(BaseModel):
    code: str
    type: Literal["kiosque", "ambassadeur"]
    lieu: str | None
    territoire_code: str


class PaquetSortie(BaseModel):
    """Tout ce dont l'appareil a besoin hors ligne."""

    version: str
    genere_a: datetime
    appareil: AppareilSortie
    langues: list[LangueSortie]
    # Langue → contenus publiés, dans l'ordre du menu (repli en français signalé).
    faq: dict[str, list[ContenuSortie]]
    provinces: list[ProvinceSortie]
    calendrier: list[PeriodeSortie]
    # Langue → textes de l'interface (le français complète les clés manquantes).
    textes: dict[str, dict[str, str]]
    numero_vert: str
    ussd_code: str
