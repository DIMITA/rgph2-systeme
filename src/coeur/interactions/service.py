from sqlalchemy.orm import Session

from coeur.commun import Canal
from coeur.confidentialite.service import masquer_donnees_sensibles
from coeur.connaissances.schemas import ReponseSortie
from coeur.interactions.modeles import Interaction


def enregistrer(
    session: Session,
    *,
    canal: Canal,
    texte: str,
    langue_demandee: str,
    territoire_code: str | None,
    usager_empreinte: str | None,
    reponse: ReponseSortie,
) -> Interaction:
    interaction = Interaction(
        canal=canal.value,
        langue_demandee=langue_demandee,
        langue_servie=reponse.contenu.langue if reponse.contenu else None,
        territoire_code=territoire_code,
        usager_empreinte=usager_empreinte,
        resultat=reponse.type,
        motif_escalade=reponse.motif,
        contenu_id=reponse.contenu.contenu_id if reponse.contenu else None,
        score=reponse.score,
        texte_masque=masquer_donnees_sensibles(texte)[:500],
    )
    session.add(interaction)
    session.commit()
    return interaction
