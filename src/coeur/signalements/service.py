from sqlalchemy import select
from sqlalchemy.orm import Session

from coeur.commun import Canal
from coeur.confidentialite.service import empreinte_telephone, masquer_donnees_sensibles
from coeur.signalements.modeles import Signalement
from coeur.signalements.schemas import SignalementEntree


def creer(session: Session, entree: SignalementEntree, canal: Canal, pepper: str) -> Signalement:
    signalement = Signalement(
        canal=canal.value,
        type=entree.type,
        territoire_code=entree.territoire_code,
        localite=masquer_donnees_sensibles(entree.localite) if entree.localite else None,
        description=masquer_donnees_sensibles(entree.description) if entree.description else None,
        usager_empreinte=empreinte_telephone(entree.telephone, pepper) if entree.telephone else None,
        statut="nouveau",
    )
    session.add(signalement)
    session.commit()
    return signalement


def lister(
    session: Session,
    territoire_code: str | None = None,
    statut: str | None = None,
    limite: int = 100,
    decalage: int = 0,
) -> list[Signalement]:
    requete = select(Signalement).order_by(Signalement.horodatage.desc(), Signalement.id.desc())
    if territoire_code:
        requete = requete.where(Signalement.territoire_code == territoire_code)
    if statut:
        requete = requete.where(Signalement.statut == statut)
    return list(session.scalars(requete.limit(limite).offset(decalage)))


def changer_statut(session: Session, signalement_id: int, statut: str) -> Signalement | None:
    signalement = session.get(Signalement, signalement_id)
    if signalement is None:
        return None
    signalement.statut = statut
    session.commit()
    return signalement
