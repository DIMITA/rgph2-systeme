"""Canal SMS : mots-clés pour les services, toute autre phrase va à la base de connaissances.

Les mots-clés sont tolérants (majuscules, accents, tirets indifférents). Un message
qui commence par un mot-clé mais ressemble à une question (« agent recenseur faux,
que faire ? ») est traité comme une question : la base fermée répond ou escalade.
"""

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from coeur.badges.service import normaliser_badge
from coeur.commun import Canal
from coeur.config import Parametres
from coeur.confidentialite.service import empreinte_telephone, normaliser_telephone
from coeur.connaissances import service as connaissances
from coeur.connaissances.depot import Corpus
from coeur.mobile import service as mobile
from coeur.mobile.gsm import en_gsm, nb_segments
from coeur.mobile.modeles import MessageSms
from coeur.mobile.service import Usager
from coeur.sms.analyse import analyser, normaliser, trouver_territoire
from coeur.sms.passerelle import passerelle
from coeur.statistiques.service import bornes_journees
from coeur.territoires.modeles import Territoire

ResultatEnvoi = Literal["envoye", "plafond", "echec"]


# --- Envoi ---------------------------------------------------------------------------------

def envoyes_aujourd_hui(session: Session, empreinte: str, reglages: Parametres) -> int:
    aujourd_hui = datetime.now(ZoneInfo(reglages.fuseau_horaire)).date()
    return session.scalar(select(func.count()).where(
        MessageSms.usager_empreinte == empreinte, MessageSms.sens == "sortant",
        MessageSms.statut == "envoye",
        *bornes_journees(MessageSms.horodatage, aujourd_hui, aujourd_hui,
                         ZoneInfo(reglages.fuseau_horaire)),
    )) or 0


def envoyer(session: Session, reglages: Parametres, telephone: str, texte: str) -> ResultatEnvoi:
    """Envoie un SMS dans l'alphabet GSM, dans la limite de SMS_REPONSES_PAR_JOUR."""
    numero = normaliser_telephone(telephone)
    empreinte = empreinte_telephone(numero, reglages.pepper_telephone)
    texte = en_gsm(texte)
    if envoyes_aujourd_hui(session, empreinte, reglages) >= reglages.sms_reponses_par_jour:
        statut: ResultatEnvoi = "plafond"
    else:
        statut = "envoye" if passerelle().envoyer(numero, texte) else "echec"
    session.add(MessageSms(sens="sortant", usager_empreinte=empreinte, statut=statut,
                           segments=nb_segments(texte) if statut == "envoye" else 0))
    session.commit()
    return statut


# --- Réception -----------------------------------------------------------------------------

def _codes_langues(session: Session, reglages: Parametres) -> str:
    return ", ".join(code for _, code, _ in mobile.langues_proposees(session, reglages))


def _territoire(session: Session, u: Usager, mots: list[str],
                mot_cle: str) -> tuple[Territoire | None, list[str], str | None]:
    """(territoire, mots restants, message d'erreur à renvoyer)."""
    references = [(t.code, t.nom) for t in session.scalars(select(Territoire))]
    codes, reste = trouver_territoire(references, mots)
    if len(codes) == 1:
        return session.get(Territoire, codes[0]), reste, None
    if codes:  # homonymes (ville et territoire du même nom) : on demande le code
        return None, reste, u.t["sms_territoire_ambigu"].format(
            mot=mot_cle, codes=", ".join(codes))
    return None, reste, u.t["sms_territoire_introuvable"].format(mot=mot_cle)


def _question(session: Session, corpus: Corpus, reglages: Parametres, u: Usager,
              texte: str) -> str:
    reponse = connaissances.traiter_question(
        session, corpus, reglages, canal=Canal.SMS, texte=texte[:500], langue=u.langue,
        telephone=u.telephone,
    )
    if reponse.contenu is not None:
        return mobile.texte_detail(reponse.contenu, reglages)
    return mobile.message_escalade(u, reglages)


def repondre(session: Session, corpus: Corpus, reglages: Parametres, u: Usager,
             texte: str) -> str:
    """Texte de la réponse à un SMS reçu (et effets : signalement, rappel, langue…)."""
    commande = analyser(texte)
    mots, t = commande.mots, u.t

    if commande.nom == "aide" and not mots:
        return t["sms_aide"].format(codes=_codes_langues(session, reglages))

    if commande.nom == "agent" and 0 < len(mots) <= 2:
        badge = "".join(mots)
        if any(c.isdigit() for c in badge):
            try:
                v = mobile.verifier_badge(session, u, badge, reglages)
            except ValueError:
                return t["badge_format"]
            except mobile.TropDeVerifications:
                return t["trop_de_verifications"]
            reponse = mobile.texte_badge(u, v)
            if v.statut == "inconnu":
                reponse += " " + t["sms_signaler_agent"].format(numero=v.numero)
            return reponse
    if commande.nom == "agent" and not mots:
        return t["sms_badge_manquant"]

    if commande.nom == "passage" and mots:
        territoire, reste, erreur = _territoire(session, u, mots, "PASSAGE")
        if territoire is not None:
            return mobile.consulter_passage(session, u, territoire)
        if len(mots) <= 3:
            return erreur
        # Sinon : sans doute une phrase (« passage des agents dans mon village ? »).

    if commande.nom in ("non_visite", "faux_agent"):
        territoire, reste, erreur = _territoire(
            session, u, mots, "NONVISITE" if commande.nom == "non_visite" else "FAUXAGENT")
        if territoire is None:
            return erreur
        if commande.nom == "non_visite":
            s = mobile.signaler(session, u, "menage_non_visite", territoire.code,
                                localite=" ".join(reste) or None)
        else:
            try:
                badge = normaliser_badge("".join(reste)) if reste else None
            except ValueError:
                badge = None
            s = mobile.signaler(session, u, "agent_douteux", territoire.code, badge=badge)
        return t["signalement_enregistre"].format(id=s.id)

    if commande.nom == "rappel" and len(mots) <= 1:
        cree = mobile.demander_rappel(session, u, "sms")
        return t["rappel_enregistre" if cree else "rappel_deja"]

    if commande.nom == "langue" and len(mots) == 1:
        langues = mobile.langues_proposees(session, reglages)
        choix = normaliser(mots[0])
        for _, code, nom in langues:
            if choix in (normaliser(code), normaliser(nom)):
                mobile.enregistrer_langue(session, u.empreinte, code)
                u.langue = code
                return u.t["sms_langue_ok"].format(langue=nom)
        return t["sms_langue_inconnue"].format(codes=_codes_langues(session, reglages))

    return _question(session, corpus, reglages, u, texte)


def recevoir(session: Session, corpus: Corpus, reglages: Parametres, de: str,
             texte: str) -> tuple[str | None, ResultatEnvoi | None]:
    """Traite un SMS reçu et envoie la réponse. (texte de la réponse, résultat de l'envoi).

    Un expéditeur qui n'est pas un numéro (nom d'opérateur, service) est ignoré.
    """
    try:
        u = mobile.usager(session, Canal.SMS, normaliser_telephone(de), reglages)
    except ValueError:
        return None, None
    session.add(MessageSms(sens="entrant", usager_empreinte=u.empreinte, statut="recu",
                           segments=nb_segments(en_gsm(texte))))
    session.commit()
    reponse = repondre(session, corpus, reglages, u, texte.strip())
    return reponse, envoyer(session, reglages, u.telephone, reponse)
