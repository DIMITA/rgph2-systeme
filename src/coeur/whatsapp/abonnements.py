"""Rappels de passage par WhatsApp : abonnement, envoi avant le passage, arrêt, expiration."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from coeur.calendrier.modeles import Passage
from coeur.calendrier.service import passages_publies
from coeur.centre_appels.service import chiffrer_numero, dechiffrer_numero
from coeur.config import Parametres
from coeur.connaissances.modeles import STATUT_PUBLIE
from coeur.mobile.service import Usager
from coeur.territoires.modeles import Territoire
from coeur.whatsapp.messages import Modele
from coeur.whatsapp.modeles import Abonnement
from coeur.whatsapp.envoi import envoyer


def abonner(session: Session, u: Usager, territoire: Territoire, reglages: Parametres) -> str:
    """« cree », « deja » ou « maximum » (WHATSAPP_ABONNEMENTS_MAX territoires par usager)."""
    if session.scalar(select(Abonnement.id).where(
            Abonnement.usager_empreinte == u.empreinte,
            Abonnement.territoire_code == territoire.code)):
        return "deja"
    nombre = session.scalar(select(func.count()).select_from(Abonnement).where(
        Abonnement.usager_empreinte == u.empreinte))
    if nombre >= reglages.whatsapp_abonnements_max:
        return "maximum"
    session.add(Abonnement(usager_empreinte=u.empreinte, numero_chiffre=chiffrer_numero(u.telephone),
                           territoire_code=territoire.code, langue=u.langue, envoyes=[]))
    session.commit()
    return "cree"


def arreter(session: Session, empreinte: str) -> int:
    """« STOP » : efface tous les abonnements de l'usager, et donc son numéro."""
    supprimes = session.execute(
        delete(Abonnement).where(Abonnement.usager_empreinte == empreinte)).rowcount
    session.commit()
    return supprimes


def _date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def envoyer_rappels(session: Session, reglages: Parametres,
                    maintenant: datetime | None = None) -> int:
    """Envoie les rappels dus (J-3, veille…) dans la plage horaire autorisée. Renvoie le nombre."""
    fuseau = ZoneInfo(reglages.fuseau_horaire)
    maintenant = (maintenant or datetime.now(timezone.utc)).astimezone(fuseau)
    if not reglages.whatsapp_heure_debut <= maintenant.hour < reglages.whatsapp_heure_fin:
        return 0
    aujourd_hui = maintenant.date()
    etapes = reglages.jours_rappels()
    envoyes = 0
    for abonnement in session.scalars(select(Abonnement).order_by(Abonnement.id)):
        territoire = session.get(Territoire, abonnement.territoire_code)
        for periode in passages_publies(session, abonnement.territoire_code):
            jours = (periode.date_debut - aujourd_hui).days
            # Un rappel manqué (service arrêté) part au passage suivant de la tâche, tant
            # que le passage n'a pas commencé ; on n'envoie jamais deux fois la même étape.
            dues = [etiquette for j, etiquette in etapes.items() if 0 < jours <= j]
            cle = f"{periode.id}:{min(dues, key=lambda e: int(e[1:]))}" if dues else None
            if cle is None or cle in (abonnement.envoyes or []):
                continue
            message = Modele(reglages.whatsapp_modele_rappel,
                             reglages.langue_modele(abonnement.langue),
                             [territoire.nom, _date(periode.date_debut), _date(periode.date_fin)])
            numero = dechiffrer_numero(abonnement.numero_chiffre)
            if envoyer(session, numero, abonnement.usager_empreinte, [message], categorie="modele"):
                # Toutes les étapes plus lointaines sont réputées faites (pas de rattrapage).
                faites = [f"{periode.id}:{e}" for j, e in etapes.items() if j >= jours]
                abonnement.envoyes = sorted(set(abonnement.envoyes or []) | set(faites))
                session.commit()
                envoyes += 1
    return envoyes


def expirer(session: Session, reglages: Parametres, aujourd_hui: date | None = None) -> int:
    """Efface les abonnements dont tous les passages publiés sont finis depuis X jours."""
    aujourd_hui = aujourd_hui or datetime.now(ZoneInfo(reglages.fuseau_horaire)).date()
    limite = aujourd_hui - timedelta(days=reglages.whatsapp_abonnement_jours_apres)
    derniere_fin = (select(Passage.territoire_code, func.max(Passage.date_fin).label("fin"))
                    .where(Passage.statut == STATUT_PUBLIE)
                    .group_by(Passage.territoire_code).subquery())
    finis = select(derniere_fin.c.territoire_code).where(derniere_fin.c.fin < limite)
    supprimes = session.execute(
        delete(Abonnement).where(Abonnement.territoire_code.in_(finis))).rowcount
    session.commit()
    return supprimes


def nombre_abonnes(session: Session) -> int:
    return session.scalar(select(func.count(Abonnement.usager_empreinte.distinct()))) or 0
