"""Agrégation des interactions et signalements par unité (pays, province ou territoire).

Deux garde-fous :
- la maille ne peut être que nationale, provinciale ou territoriale (type `Niveau`) ;
  la localité des signalements n'est jamais lue ici ;
- secret statistique : tout effectif compris entre 1 et `seuil - 1` est masqué,
  et une ligne entière est masquée si son nombre d'interactions est sous le seuil.
"""

from datetime import date, datetime, time, timedelta, timezone, tzinfo

from sqlalchemy import ColumnElement, func, literal, select
from sqlalchemy.orm import Session

from coeur.interactions.modeles import Interaction
from coeur.signalements.modeles import Signalement
from coeur.statistiques.schemas import (
    LigneInteractions,
    Axe,
    Effectifs,
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


def _bornes(colonne, depuis: date | None, jusqu_a: date | None,
            fuseau: tzinfo = timezone.utc) -> list:
    """Journées entières, découpées selon `fuseau` (UTC par défaut)."""
    conditions = []
    if depuis:
        conditions.append(colonne >= datetime.combine(depuis, time.min, fuseau))
    if jusqu_a:
        lendemain = datetime.combine(jusqu_a + timedelta(days=1), time.min, fuseau)
        conditions.append(colonne < lendemain)
    return conditions


def _effectifs_interactions(total: int, escalades: int, usagers: int, seuil: int) -> dict:
    """Ligne entière masquée sous le seuil ; sinon, chaque petit effectif est masqué."""
    if total < seuil:
        return {"nb_interactions": None, "nb_escalades": None,
                "nb_usagers_uniques": None, "masque": True}
    escalades_m, usagers_m = masquer(escalades, seuil), masquer(usagers, seuil)
    return {"nb_interactions": total, "nb_escalades": escalades_m,
            "nb_usagers_uniques": usagers_m,
            "masque": escalades_m is None or usagers_m is None}


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

    interactions = [
        LigneInteractions(
            unite=unite, canal=canal, langue=langue,
            **_effectifs_interactions(total, escalades, usagers, seuil),
        )
        for unite, canal, langue, total, escalades, usagers in lignes_i
    ]

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


def _expression_axe(axe: Axe, modele) -> ColumnElement[str]:
    if axe is Axe.CANAL:
        return modele.canal
    if axe is Axe.LANGUE:
        return modele.langue_demandee
    if axe is Axe.PROVINCE:
        return func.coalesce(Territoire.province_code, UNITE_INCONNUE)
    if axe is Axe.TERRITOIRE:
        return func.coalesce(modele.territoire_code, UNITE_INCONNUE)
    return modele.type


def repartir_interactions(
    session: Session, axe: Axe | None, depuis: date | None, jusqu_a: date | None, seuil: int,
    fuseau: tzinfo = timezone.utc,
) -> list[Effectifs]:
    """Interactions réparties sur un axe (ou total national si axe=None)."""
    if axe is Axe.TYPE:
        raise ValueError("L'axe « type » ne concerne que les signalements")
    valeur = (_expression_axe(axe, Interaction) if axe else literal(UNITE_NATIONALE)).label("v")
    lignes = session.execute(
        select(
            valeur,
            func.count(),
            func.count().filter(Interaction.resultat == "escalade"),
            func.count(Interaction.usager_empreinte.distinct()),
        )
        .select_from(Interaction)
        .outerjoin(Territoire, Territoire.code == Interaction.territoire_code)
        .where(*_bornes(Interaction.horodatage, depuis, jusqu_a, fuseau))
        .group_by(valeur)
        .order_by(func.count().desc(), valeur)
    ).all()
    return [
        Effectifs(valeur=v, **_effectifs_interactions(total, esc, usagers, seuil))
        for v, total, esc, usagers in lignes
    ]


def repartir_signalements(
    session: Session, axe: Axe | None, depuis: date | None, jusqu_a: date | None, seuil: int,
    fuseau: tzinfo = timezone.utc,
) -> list[Effectifs]:
    if axe is Axe.LANGUE:
        raise ValueError("Les signalements n'ont pas de langue")
    valeur = (_expression_axe(axe, Signalement) if axe else literal(UNITE_NATIONALE)).label("v")
    lignes = session.execute(
        select(valeur, func.count())
        .select_from(Signalement)
        .outerjoin(Territoire, Territoire.code == Signalement.territoire_code)
        .where(*_bornes(Signalement.horodatage, depuis, jusqu_a, fuseau))
        .group_by(valeur)
        .order_by(func.count().desc(), valeur)
    ).all()
    return [
        Effectifs(valeur=v, nb_signalements=masquer(n, seuil), masque=masquer(n, seuil) is None)
        for v, n in lignes
    ]
