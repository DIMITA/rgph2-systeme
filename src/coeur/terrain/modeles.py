from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from coeur.base import SCHEMA_COEUR, Base

TYPES_APPAREIL = ("kiosque", "ambassadeur")


class Appareil(Base):
    """Tablette de kiosque ou téléphone d'Ambassadeur.

    Aucun nom de personne : un Ambassadeur n'est connu ici que par son code (la liste
    des noms reste à l'INS). Le jeton et le code d'activation ne sont gardés que sous
    forme d'empreinte SHA-256.
    """

    __tablename__ = "appareils"
    __table_args__ = (
        CheckConstraint(f"type IN {TYPES_APPAREIL}", name="type"),
        {"schema": SCHEMA_COEUR},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(12))
    # Code lisible, unique : « KIO-NKV-GOM-01 », « AMB-KCE-MAT-07 »…
    code: Mapped[str] = mapped_column(String(40), unique=True)
    # Lieu d'un kiosque (école, mairie…). Jamais le nom d'une personne.
    lieu: Mapped[str | None] = mapped_column(String(120))
    territoire_code: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA_COEUR}.territoires.code"), index=True
    )
    # Langues embarquées dans le paquet, séparées par des virgules (« fr,ln »).
    langues: Mapped[str] = mapped_column(String(60))
    jeton_empreinte: Mapped[str | None] = mapped_column(String(64), unique=True)
    activation_empreinte: Mapped[str | None] = mapped_column(String(64), unique=True)
    activation_expire_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cree_a: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    active_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoque_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    derniere_synchro_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Version du paquet téléchargé lors de la dernière synchronisation.
    version_paquet: Mapped[str | None] = mapped_column(String(64))

    def liste_langues(self) -> list[str]:
        return [l.strip() for l in self.langues.split(",") if l.strip()]


class RemonteeRecue(Base):
    """Identifiant de chaque remontée déjà enregistrée : un envoi rejoué n'est pas doublé.

    L'identifiant est tiré au hasard par l'appareil. Effacé après CONSERVATION_REMONTEES_JOURS.
    """

    __tablename__ = "remontees_terrain"
    __table_args__ = {"schema": SCHEMA_COEUR}

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    appareil_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA_COEUR}.appareils.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(16))
    recu_a: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
