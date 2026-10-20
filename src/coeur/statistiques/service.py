"""Agrégation des interactions et signalements par unité (pays, province ou territoire).

Deux garde-fous :
- la maille ne peut être que nationale, provinciale ou territoriale (type `Niveau`) ;
  la localité des signalements n'est jamais lue ici ;
- secret statistique : tout effectif compris entre 1 et `seuil - 1` est masqué,
  et une ligne entière est masquée si son nombre d'interactions est sous le seuil.
"""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import ColumnElement, func, literal, select
from sqlalchemy.orm import Session

from coeur.interactions.modeles import Interaction
from coeur.signalements.modeles import Signalement
from coeur.statistiques.schemas import (
    LigneInteractions,
    LigneSignalements,
    Niveau,
    StatistiquesSortie,
)
from coeur.territoires.modeles import Territoire

UNITE_NATIONALE = "RDC"
UNITE_INCONNUE = "non_renseigne"


def masquer(valeur: int, seuil: int) -> int | None:
    return None if 0 < valeur < seuil else valeur


def _unite(niveau: Niveau, colonne_territoire) -> ColumnElement[str]:
    if niveau is Niveau.NATIONAL:
        return literal(UNITE_NATIONALE)
    if niveau is Niveau.PROVINCE:
        return func.coalesce(Territoire.province_code, UNITE_INCONNUE)
    return func.coalesce(colonne_territoire, UNITE_INCONNUE)


def _bornes(colonne, depuis: date | None, jusqu_a: date | None) -> list:
    conditions = []
    if depuis:
        conditions.append(colonne >= datetime.combine(depuis, time.min, timezone.utc))
    if jusqu_a:
        lendemain = datetime.combine(jusqu_a + timedelta(days=1), time.min, timezone.utc)
        conditions.append(colonne < lendemain)
    return conditions


def calculer(
    session: Session, niveau: Niveau, depuis: date | None, jusqu_a: date | None, seuil: int
) -> StatistiquesSortie:
    unite_i = _unite(niveau, Interaction.territoire_code).label("unite")
    lignes_i = session.execute(
        select(
            unite_i,
            Interaction.canal,
            Interaction.langue_demandee,
            func.count(),
            func.count().filter(Interaction.resultat == "escalade"),
            func.count(Interaction.usager_empreinte.distinct()),
        )
        .outerjoin(Territoire, Territoire.code == Interaction.territoire_code)
        .where(*_bornes(Interaction.horodatage, depuis, jusqu_a))
        .group_by(unite_i, Interaction.canal, Interaction.langue_demandee)
        .order_by(unite_i, Interaction.canal, Interaction.langue_demandee)
    ).all()

    interactions = []
    for unite, canal, langue, total, escalades, usagers in lignes_i:
        if total < seuil:
            interactions.append(
                LigneInteractions(
                    unite=unite, canal=canal, langue=langue, nb_interactions=None,
                    nb_escalades=None, nb_usagers_uniques=None, masque=True,
                )
            )
        else:
            interactions.append(
                LigneInteractions(
                    unite=unite, canal=canal, langue=langue, nb_interactions=total,
                    nb_escalades=masquer(escalades, seuil),
                    nb_usagers_uniques=masquer(usagers, seuil),
                    masque=masquer(escalades, seuil) is None or masquer(usagers, seuil) is None,
                )
            )

    unite_s = _unite(niveau, Signalement.territoire_code).label("unite")
    lignes_s = session.execute(
        select(unite_s, Signalement.type, func.count())
        .outerjoin(Territoire, Territoire.code == Signalement.territoire_code)
        .where(*_bornes(Signalement.horodatage, depuis, jusqu_a))
        .group_by(unite_s, Signalement.type)
        .order_by(unite_s, Signalement.type)
    ).all()
    signalements = [
        LigneSignalements(
            unite=unite, type=type_, nb_signalements=masquer(n, seuil),
            masque=masquer(n, seuil) is None,
        )
        for unite, type_, n in lignes_s
    ]

    return StatistiquesSortie(
        niveau=niveau, depuis=depuis, jusqu_a=jusqu_a, seuil_secret=seuil,
        interactions=interactions, signalements=signalements,
    )
