from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from coeur.commun import Canal
from coeur.config import parametres
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
    conservation = parametres().conservation_texte_questions
    garder_texte = conservation == "tout" or (
        conservation == "escalades" and reponse.type == "escalade")
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
        texte_masque=masquer_donnees_sensibles(texte)[:500] if garder_texte else None,
    )
    session.add(interaction)
    session.commit()
    return interaction


def escalades_recentes(
    session: Session, langue: str | None = None, motif: str | None = None,
    limite: int = 50, decalage: int = 0,
) -> list[Interaction]:
    """Questions restées sans réponse validée, les plus récentes d'abord."""
    requete = select(Interaction).where(Interaction.resultat == "escalade")
    if langue:
        requete = requete.where(Interaction.langue_demandee == langue)
    if motif:
        requete = requete.where(Interaction.motif_escalade == motif)
    requete = requete.order_by(Interaction.horodatage.desc(), Interaction.id.desc())
    return list(session.scalars(requete.limit(limite).offset(decalage)))


def escalades_frequentes(
    session: Session, depuis: datetime | None = None, limite: int = 20
) -> list[tuple[str, str, int]]:
    """Questions escaladées les plus posées : (texte, langue, nombre).

    Regroupe les textes identiques à la casse et aux espaces près : ce sont les
    premiers candidats à une nouvelle entrée de FAQ ou à une formulation.
    """
    texte = func.lower(func.trim(Interaction.texte_masque)).label("texte")
    requete = select(texte, Interaction.langue_demandee, func.count()).where(
        Interaction.resultat == "escalade", Interaction.motif_escalade != "demande_humain",
        Interaction.texte_masque.is_not(None),
    )
    if depuis:
        requete = requete.where(Interaction.horodatage >= depuis)
    requete = (
        requete.group_by(texte, Interaction.langue_demandee)
        .order_by(func.count().desc(), texte)
        .limit(limite)
    )
    return [(t, langue, n) for t, langue, n in session.execute(requete)]
