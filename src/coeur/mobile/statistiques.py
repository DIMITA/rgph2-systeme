"""Chiffres des services USSD et SMS pour le tableau de bord (secret statistique appliqué)."""

from datetime import date, tzinfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from coeur.mobile.modeles import Consultation, MessageSms
from coeur.statistiques.service import bornes_journees, masquer


def statistiques_mobile(session: Session, depuis: date | None, jusqu_a: date | None,
                        fuseau: tzinfo, seuil: int) -> dict:
    """Dates de passage consultées, badges vérifiés, SMS reçus et envoyés.

    Les SMS envoyés sont comptés en segments facturés : c'est le coût pour l'opérateur.
    """
    passages, valides, douteux = session.execute(
        select(
            func.count().filter(Consultation.service == "passage"),
            func.count().filter(Consultation.service == "badge", Consultation.resultat == "valide"),
            func.count().filter(Consultation.service == "badge",
                                Consultation.resultat.in_(("inconnu", "retire"))),
        ).where(*bornes_journees(Consultation.horodatage, depuis, jusqu_a, fuseau))
    ).one()
    recus, segments, plafonnes = session.execute(
        select(
            func.count().filter(MessageSms.sens == "entrant"),
            func.coalesce(func.sum(MessageSms.segments).filter(MessageSms.sens == "sortant"), 0),
            func.count().filter(MessageSms.statut == "plafond"),
        ).where(*bornes_journees(MessageSms.horodatage, depuis, jusqu_a, fuseau))
    ).one()
    return {
        "passages": masquer(passages, seuil),
        "badges_valides": masquer(valides, seuil),
        "badges_douteux": masquer(douteux, seuil),
        "sms_recus": masquer(recus, seuil),
        "sms_segments": masquer(segments, seuil),
        "sms_plafonnes": masquer(plafonnes, seuil),
    }
