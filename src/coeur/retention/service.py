from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from coeur.centre_appels.modeles import Appel, Ecoute, Rappel
from coeur.centre_appels.service import supprimer_enregistrements_avant
from coeur.interactions.modeles import Interaction
from coeur.signalements.modeles import Signalement


def purger(session: Session, avant: datetime) -> dict[str, int]:
    """Supprime définitivement tout ce qui a été enregistré avant `avant`,
    y compris les fichiers d'enregistrement des conversations."""
    resultat = {
        "interactions": session.execute(
            delete(Interaction).where(Interaction.horodatage < avant)
        ).rowcount,
        "signalements": session.execute(
            delete(Signalement).where(Signalement.horodatage < avant)
        ).rowcount,
        "appels": session.execute(delete(Appel).where(Appel.debut < avant)).rowcount,
        "rappels": session.execute(delete(Rappel).where(Rappel.cree_a < avant)).rowcount,
        "ecoutes": session.execute(delete(Ecoute).where(Ecoute.ecoute_a < avant)).rowcount,
    }
    session.commit()
    resultat["enregistrements"] = supprimer_enregistrements_avant(session, avant)
    return resultat
