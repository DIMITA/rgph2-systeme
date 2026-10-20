from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from coeur.calendrier.modeles import Passage
from coeur.connaissances.modeles import STATUT_PUBLIE

# Périodes de démonstration (hors production), chargées avec les contenus d'exemple.
EXEMPLES = [
    ("KIN-V", date(2027, 5, 10), date(2027, 6, 20)),
    ("NKV-GOM", date(2027, 5, 17), date(2027, 6, 6)),
    ("KCE-MAT", date(2027, 5, 24), date(2027, 6, 13)),
]


def passages_publies(session: Session, territoire_code: str) -> list[Passage]:
    """Périodes validées pour un territoire, dans l'ordre chronologique."""
    return list(session.scalars(
        select(Passage)
        .where(Passage.territoire_code == territoire_code, Passage.statut == STATUT_PUBLIE)
        .order_by(Passage.date_debut, Passage.id)
    ))


def charger_exemples(session: Session) -> int:
    for code, debut, fin in EXEMPLES:
        if not session.scalar(select(Passage.id).where(Passage.territoire_code == code)):
            session.add(Passage(territoire_code=code, date_debut=debut, date_fin=fin,
                                statut=STATUT_PUBLIE))
    session.commit()
    return len(EXEMPLES)
