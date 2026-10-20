from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from coeur.interactions.modeles import Interaction
from coeur.signalements.modeles import Signalement


def purger(session: Session, avant: datetime) -> dict[str, int]:
    """Supprime définitivement tout ce qui a été enregistré avant `avant`."""
    resultat = {
        "interactions": session.execute(
            delete(Interaction).where(Interaction.horodatage < avant)
        ).rowcount,
        "signalements": session.execute(
            delete(Signalement).where(Signalement.horodatage < avant)
        ).rowcount,
    }
    session.commit()
    return resultat
