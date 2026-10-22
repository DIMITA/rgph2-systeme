"""Agrégation des interactions et signalements par unité (pays, province ou territoire).

Quatre garde-fous :
- la maille ne peut être que nationale, provinciale ou territoriale (type `Niveau`) ;
  la localité des signalements n'est jamais lue ici ;
- secret statistique : tout effectif compris entre 1 et `seuil - 1` est masqué,
  et une ligne entière est masquée si son nombre d'interactions est sous le seuil ;
- masquage complémentaire : une case masquée ne doit pas pouvoir se retrouver par
  différence avec un total publié (national moins somme des territoires, province
  moins ses autres territoires…). Voir `masquage_complementaire` ;
- perturbation par clé de cellule : chaque effectif publié est décalé de -2 à +2,
  toujours de la même façon pour les mêmes enregistrements. La différence entre
  deux périodes choisies (du 1er au 10 moins du 1er au 9) ne révèle donc plus une
  petite valeur exacte. Voir `perturber`.
"""

from collections import defaultdict
from collections.abc import Hashable, Sequence
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from itertools import combinations

from sqlalchemy import ColumnElement, func, literal, select
from sqlalchemy.orm import Session

from coeur.config import parametres
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


def bornes_journees(colonne, depuis: date | None, jusqu_a: date | None,
            fuseau: tzinfo = timezone.utc) -> list:
    """Journées entières, découpées selon `fuseau` (UTC par défaut)."""
    conditions = []
    if depuis:
        conditions.append(colonne >= datetime.combine(depuis, time.min, fuseau))
    if jusqu_a:
        lendemain = datetime.combine(jusqu_a + timedelta(days=1), time.min, fuseau)
        conditions.append(colonne < lendemain)
    return conditions


def masquage_complementaire(valeurs: Sequence[int], masques: set[int],
                            groupes: Sequence[Sequence[int]], seuil: int) -> set[int]:
    """Indices des cases à masquer, masquage complémentaire compris.

    `valeurs` : effectifs réels ; `masques` : cases déjà masquées ; `groupes` :
    ensembles de cases dont la somme est publiée, ou déductible d'un autre tableau.
    Dans chaque groupe qui contient une case masquée, il en faut au moins deux,
    dont la somme atteint le seuil : sinon, on masque en plus la plus petite case
    visible. Sans cette règle, total - cases visibles = la case masquée ; et deux
    cases masquées dont la somme vaut 2 valent forcément 1 chacune.
    On recommence jusqu'à ce que tous les groupes soient protégés, car masquer
    une case dans un groupe peut en découvrir un autre.
    """
    masques = set(masques)
    modifie = True
    while modifie:
        modifie = False
        for groupe in groupes:
            caches = [i for i in groupe if i in masques]
            if not caches or (len(caches) >= 2 and sum(valeurs[i] for i in caches) >= seuil):
                continue
            visibles = [i for i in groupe if i not in masques and valeurs[i] > 0]
            if visibles:
                masques.add(min(visibles, key=lambda i: (valeurs[i], i)))
                modifie = True
    return masques


def groupes_de_cases(cles: Sequence[tuple[Hashable, ...]],
                     parents: dict[Hashable, Hashable] | None = None) -> list[list[int]]:
    """Groupes de cases d'un tableau croisé dont les sommes sont publiées.

    `cles` : coordonnées de chaque case (unité, canal, langue…), la première étant
    l'unité géographique. Toute combinaison de dimensions fixées donne une marge
    publiée quelque part (tableau de bord, autre niveau de l'API). `parents` :
    unité → unité englobante (territoire → province) : la somme des territoires
    d'une province est publiée au niveau provincial.
    """
    nb_dimensions = len(cles[0]) if cles else 0
    groupes: list[list[int]] = []
    for taille in range(nb_dimensions):
        for fixees in combinations(range(nb_dimensions), taille):
            par_marge: dict[tuple, list[int]] = defaultdict(list)
            for i, cle in enumerate(cles):
                par_marge[tuple(cle[d] for d in fixees)].append(i)
            groupes.extend(g for g in par_marge.values() if len(g) > 1)
            if parents and 0 not in fixees:
                par_parent: dict[tuple, list[int]] = defaultdict(list)
                for i, cle in enumerate(cles):
                    par_parent[(parents.get(cle[0]),) + tuple(cle[d] for d in fixees)].append(i)
                groupes.extend(g for g in par_parent.values() if len(g) > 1)
    return groupes


# Méthode de la clé de cellule (« cell key method », ONS 2021, ABS) : chaque
# enregistrement porte une clé aléatoire secrète entre 0 et 255 (colonne cle_cellule).
# La clé d'une case est la somme des clés de ses enregistrements, modulo 256 ; elle
# choisit le décalage dans ce tableau : -2 (10 %), -1 (20 %), 0 (40 %), +1 (20 %), +2 (10 %).
DECALAGES = ((26, -2), (77, -1), (179, 0), (230, 1), (256, 2))
# Chaque champ d'une même case reçoit un décalage différent.
DECALAGE_PAR_CHAMP = {"nb_interactions": 0, "nb_escalades": 64, "nb_usagers_uniques": 128,
                      "nb_signalements": 0}


def perturber(valeur: int | None, cle: int, seuil: int) -> int | None:
    """Effectif publié : décalé selon la clé de la case, jamais sous le seuil, zéro intact.

    Les mêmes enregistrements donnent toujours la même clé, donc le même chiffre :
    répéter la requête n'apprend rien. Deux périodes qui diffèrent d'un seul
    enregistrement ont des clés sans rapport : leur différence est brouillée.
    """
    if not valeur:
        return valeur
    cle %= 256
    decalage = next(d for borne, d in DECALAGES if cle < borne)
    return max(valeur + decalage, seuil)


def _masquer_tableau(lignes: Sequence[dict], champs: Sequence[str], cles: Sequence[tuple],
                     seuil: int, parents: dict | None = None,
                     ligne_masquee_si: str | None = None) -> list[dict]:
    """Secret statistique sur un tableau : petits effectifs, masquage complémentaire, puis
    perturbation des effectifs publiés (si PERTURBATION_STATISTIQUE).

    `ligne_masquee_si` : champ sous le seuil duquel toute la ligne est masquée. Chaque
    ligne porte « cle_cellule », la somme des clés de ses enregistrements.
    Renvoie des copies des lignes, valeurs masquées à None et « masque » renseigné.
    """
    perturbation = parametres().perturbation_statistique
    groupes = groupes_de_cases(cles, parents)
    masques_par_champ = {}
    for champ in champs:
        valeurs = [ligne[champ] for ligne in lignes]
        primaires = {i for i, ligne in enumerate(lignes)
                     if 0 < ligne[champ] < seuil
                     or (ligne_masquee_si and ligne[ligne_masquee_si] < seuil)}
        masques_par_champ[champ] = masquage_complementaire(valeurs, primaires, groupes, seuil)
    resultat = []
    for i, ligne in enumerate(lignes):
        copie = dict(ligne)
        cle = copie.pop("cle_cellule") or 0
        for champ in champs:
            if i in masques_par_champ[champ]:
                copie[champ] = None
            elif perturbation:
                copie[champ] = perturber(copie[champ], cle + DECALAGE_PAR_CHAMP[champ], seuil)
        copie["masque"] = any(i in m for m in masques_par_champ.values())
        resultat.append(copie)
    return resultat


def _provinces_des_territoires(session: Session) -> dict[str, str]:
    return dict(session.execute(select(Territoire.code, Territoire.province_code)).all())


CHAMPS_INTERACTIONS = ("nb_interactions", "nb_escalades", "nb_usagers_uniques")


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
            func.sum(Interaction.cle_cellule),
        )
        .outerjoin(Territoire, Territoire.code == Interaction.territoire_code)
        .where(*bornes_journees(Interaction.horodatage, depuis, jusqu_a))
        .group_by(unite_i, Interaction.canal, Interaction.langue_demandee)
        .order_by(unite_i, Interaction.canal, Interaction.langue_demandee)
    ).all()

    parents = _provinces_des_territoires(session) if niveau is Niveau.TERRITOIRE else None
    brutes = [
        {"unite": unite, "canal": canal, "langue": langue, "nb_interactions": total,
         "nb_escalades": escalades, "nb_usagers_uniques": usagers, "cle_cellule": cle}
        for unite, canal, langue, total, escalades, usagers, cle in lignes_i
    ]
    interactions = [
        LigneInteractions(**ligne)
        for ligne in _masquer_tableau(
            brutes, CHAMPS_INTERACTIONS, [(l["unite"], l["canal"], l["langue"]) for l in brutes],
            seuil, parents, ligne_masquee_si="nb_interactions")
    ]

    unite_s = _unite(niveau, Signalement.territoire_code).label("unite")
    lignes_s = session.execute(
        select(unite_s, Signalement.type, func.count(), func.sum(Signalement.cle_cellule))
        .outerjoin(Territoire, Territoire.code == Signalement.territoire_code)
        .where(*bornes_journees(Signalement.horodatage, depuis, jusqu_a))
        .group_by(unite_s, Signalement.type)
        .order_by(unite_s, Signalement.type)
    ).all()
    brutes_s = [{"unite": unite, "type": type_, "nb_signalements": n, "cle_cellule": cle}
                for unite, type_, n, cle in lignes_s]
    signalements = [
        LigneSignalements(**ligne)
        for ligne in _masquer_tableau(brutes_s, ("nb_signalements",),
                                      [(l["unite"], l["type"]) for l in brutes_s], seuil, parents)
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
            func.sum(Interaction.cle_cellule),
        )
        .select_from(Interaction)
        .outerjoin(Territoire, Territoire.code == Interaction.territoire_code)
        .where(*bornes_journees(Interaction.horodatage, depuis, jusqu_a, fuseau))
        .group_by(valeur)
        .order_by(func.count().desc(), valeur)
    ).all()
    brutes = [{"valeur": v, "nb_interactions": total, "nb_escalades": esc,
               "nb_usagers_uniques": usagers, "cle_cellule": cle}
              for v, total, esc, usagers, cle in lignes]
    return [Effectifs(**ligne) for ligne in _masquer_tableau(
        brutes, CHAMPS_INTERACTIONS, [(l["valeur"],) for l in brutes], seuil,
        _parents(session, axe), ligne_masquee_si="nb_interactions")]


def repartir_signalements(
    session: Session, axe: Axe | None, depuis: date | None, jusqu_a: date | None, seuil: int,
    fuseau: tzinfo = timezone.utc,
) -> list[Effectifs]:
    if axe is Axe.LANGUE:
        raise ValueError("Les signalements n'ont pas de langue")
    valeur = (_expression_axe(axe, Signalement) if axe else literal(UNITE_NATIONALE)).label("v")
    lignes = session.execute(
        select(valeur, func.count(), func.sum(Signalement.cle_cellule))
        .select_from(Signalement)
        .outerjoin(Territoire, Territoire.code == Signalement.territoire_code)
        .where(*bornes_journees(Signalement.horodatage, depuis, jusqu_a, fuseau))
        .group_by(valeur)
        .order_by(func.count().desc(), valeur)
    ).all()
    brutes = [{"valeur": v, "nb_signalements": n, "cle_cellule": cle} for v, n, cle in lignes]
    return [Effectifs(**ligne) for ligne in _masquer_tableau(
        brutes, ("nb_signalements",), [(l["valeur"],) for l in brutes], seuil,
        _parents(session, axe))]


def _parents(session: Session, axe: Axe | None) -> dict[str, str] | None:
    """Par territoire, la somme d'une province est publiée sur l'axe province."""
    return _provinces_des_territoires(session) if axe is Axe.TERRITOIRE else None
