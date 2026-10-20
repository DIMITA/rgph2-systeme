from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from coeur.base import nouvelle_session
from coeur.interactions.modeles import Interaction
from coeur.retention.service import purger
from coeur.signalements.modeles import Signalement
from tests.integration.conftest import WEB


def test_purge_supprime_les_donnees_anciennes_seulement(client, exemples, session_admin):
    for _ in range(3):
        client.post("/v1/questions", json={"texte": "bonjour"}, headers=WEB)
    client.post("/v1/signalements", json={"type": "rumeur", "territoire_code": "KIN-V"}, headers=WEB)

    ancien = datetime.now(timezone.utc) - timedelta(days=400)
    premier = session_admin.scalar(select(func.min(Interaction.id)))
    session_admin.execute(update(Interaction).where(Interaction.id == premier).values(horodatage=ancien))
    session_admin.execute(update(Signalement).values(horodatage=ancien))
    session_admin.commit()

    # La purge tourne avec le rôle de l'API : il doit avoir le droit de supprimer.
    with nouvelle_session() as session:
        supprimes = purger(session, datetime.now(timezone.utc) - timedelta(days=180))

    assert supprimes == {"interactions": 1, "signalements": 1}
    assert session_admin.scalar(select(func.count()).select_from(Interaction)) == 2
    assert session_admin.scalar(select(func.count()).select_from(Signalement)) == 0


def test_purge_totale(client, exemples, session_admin):
    client.post("/v1/questions", json={"texte": "bonjour"}, headers=WEB)
    with nouvelle_session() as session:
        purger(session, datetime.now(timezone.utc) + timedelta(days=1))
    assert session_admin.scalar(select(func.count()).select_from(Interaction)) == 0
