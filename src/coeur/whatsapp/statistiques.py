"""Chiffres WhatsApp pour le tableau de bord (secret statistique appliqué)."""

from datetime import date, tzinfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from coeur.interactions.modeles import Interaction
from coeur.statistiques.service import bornes_journees, masquer
from coeur.whatsapp.abonnements import nombre_abonnes
from coeur.whatsapp.modeles import MessageWhatsapp


def statistiques_whatsapp(session: Session, depuis: date | None, jusqu_a: date | None,
                          fuseau: tzinfo, seuil: int) -> dict:
    """Messages reçus, usagers distincts, réponses (gratuites), rappels (modèles facturés).

    Les abonnés sont comptés à l'instant présent, quelle que soit la période choisie.
    """
    recus, usagers, reponses, modeles, echecs = session.execute(
        select(
            func.count().filter(MessageWhatsapp.sens == "entrant"),
            func.count(MessageWhatsapp.usager_empreinte.distinct()).filter(
                MessageWhatsapp.sens == "entrant"),
            func.count().filter(MessageWhatsapp.sens == "sortant",
                                MessageWhatsapp.categorie == "service",
                                MessageWhatsapp.statut == "envoye"),
            func.count().filter(MessageWhatsapp.categorie == "modele",
                                MessageWhatsapp.statut == "envoye"),
            func.count().filter(MessageWhatsapp.statut == "echec"),
        ).where(*bornes_journees(MessageWhatsapp.horodatage, depuis, jusqu_a, fuseau))
    ).one()
    # Messages vocaux : sujet compris et confirmé, ou refusé par le citoyen (« Non »).
    # Le taux de refus mesure la qualité de la transcription, langue par langue.
    vocaux_confirmes, vocaux_refuses = session.execute(
        select(
            func.count().filter(Interaction.resultat == "reponse"),
            func.count().filter(Interaction.motif_escalade == "vocal_non_confirme"),
        ).where(Interaction.canal == "whatsapp", Interaction.entree == "voix",
                *bornes_journees(Interaction.horodatage, depuis, jusqu_a, fuseau))
    ).one()
    return {
        "vocaux_confirmes": masquer(vocaux_confirmes, seuil),
        "vocaux_refuses": masquer(vocaux_refuses, seuil),
        "recus": masquer(recus, seuil), "usagers": masquer(usagers, seuil),
        "reponses": masquer(reponses, seuil), "rappels": masquer(modeles, seuil),
        "echecs": masquer(echecs, seuil), "abonnes": masquer(nombre_abonnes(session), seuil),
    }
