"""Services rendus aux téléphones basiques, communs à l'USSD et au SMS."""

from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from coeur.badges import service as badges
from coeur.calendrier.service import passages_publies
from coeur.centre_appels.modeles import Rappel
from coeur.centre_appels.service import chiffrer_numero
from coeur.commun import Canal
from coeur.config import Parametres, parametres
from coeur.confidentialite.service import empreinte_telephone, masquer_donnees_sensibles
from coeur.connaissances import service as connaissances
from coeur.connaissances.depot import Corpus
from coeur.connaissances.modeles import STATUT_PUBLIE, Contenu
from coeur.connaissances.schemas import ContenuSortie, ReponseSortie
from coeur.interactions import service as interactions
from coeur.limiteur import LimiteurDebit
from coeur.mobile.gsm import nb_segments
from coeur.mobile.modeles import Consultation, PreferenceLangue
from coeur.mobile.textes import textes
from coeur.signalements.modeles import Signalement
from coeur.territoires.modeles import Province, Territoire


@dataclass
class Usager:
    """Celui qui écrit ou compose : son numéro ne sert que le temps de la requête."""

    canal: Canal
    telephone: str
    empreinte: str
    langue: str

    @property
    def t(self) -> dict[str, str]:
        return textes(self.langue)


# --- Langue ------------------------------------------------------------------------------

def langues_proposees(session: Session, reglages: Parametres) -> list[tuple[int, str, str]]:
    """(touche, code, nom) des langues actives, avec les mêmes touches qu'au téléphone."""
    actives = {l.code: l.nom for l in connaissances.langues_actives(session)}
    return [(touche, code, actives[code])
            for code, touche in sorted(reglages.touches_langues().items(), key=lambda p: p[1])
            if code in actives]


def langue_preferee(session: Session, empreinte: str) -> str | None:
    return session.scalar(
        select(PreferenceLangue.langue).where(PreferenceLangue.usager_empreinte == empreinte)
    )


def langue_en_debut_de_session(session: Session, empreinte: str,
                               session_ussd: str) -> str | None:
    """Langue connue au premier écran de cette session USSD (None : premier contact)."""
    pref = session.get(PreferenceLangue, empreinte)
    if pref is None:
        return None
    return pref.langue_avant if pref.session_ussd == session_ussd else pref.langue


def enregistrer_langue(session: Session, empreinte: str, langue: str,
                       session_ussd: str | None = None) -> None:
    pref = session.get(PreferenceLangue, empreinte, with_for_update=True)
    if pref is None:
        session.add(PreferenceLangue(usager_empreinte=empreinte, langue=langue,
                                     session_ussd=session_ussd))
    else:
        if session_ussd and pref.session_ussd != session_ussd:
            pref.session_ussd, pref.langue_avant = session_ussd, pref.langue
        pref.langue, pref.maj_a = langue, func.now()
    session.commit()


def usager(session: Session, canal: Canal, telephone: str, reglages: Parametres) -> Usager:
    """ValueError si le numéro n'est pas un numéro de téléphone."""
    empreinte = empreinte_telephone(telephone, reglages.pepper_telephone)
    langue = langue_preferee(session, empreinte) or reglages.langue_par_defaut
    return Usager(canal, telephone, empreinte, langue)


# --- Questions fréquentes ----------------------------------------------------------------

def contenus_courts(session: Session, corpus: Corpus, langue: str,
                    reglages: Parametres) -> list[ContenuSortie]:
    """Contenus publiés ayant une réponse courte, dans l'ordre du menu téléphonique."""
    ordre = {cid: (o is None, o or 0, cid) for cid, o in session.execute(
        select(Contenu.id, Contenu.ordre_svi).where(Contenu.statut == STATUT_PUBLIE))}
    resultat = []
    for cid in sorted(corpus.ids_contenus(), key=lambda c: ordre.get(c, (True, 0, c))):
        texte = connaissances.texte_servi(corpus, cid, langue, reglages.langue_par_defaut)
        if texte is not None and texte.reponse_courte:
            resultat.append(texte)
    return resultat


def journaliser_lecture(session: Session, u: Usager, contenu: ContenuSortie) -> None:
    interactions.enregistrer(
        session, canal=u.canal,
        texte=f"[{u.canal.value.upper()}] question consultée : {contenu.cle}",
        langue_demandee=u.langue, territoire_code=None, usager_empreinte=u.empreinte,
        reponse=ReponseSortie(type="reponse", contenu=contenu, score=1.0),
    )


def texte_detail(contenu: ContenuSortie, reglages: Parametres) -> str:
    """Réponse complète si elle tient dans SMS_SEGMENTS_MAX, sinon la réponse courte.

    Une réponse validée n'est jamais tronquée : on choisit l'une des deux versions.
    """
    if nb_segments(contenu.reponse) <= reglages.sms_segments_max or not contenu.reponse_courte:
        return contenu.reponse
    return contenu.reponse_courte


# --- Référentiel ---------------------------------------------------------------------------

def provinces(session: Session) -> list[Province]:
    """Provinces ayant au moins un territoire."""
    return list(session.scalars(
        select(Province).where(Province.code.in_(select(Territoire.province_code).distinct()))
        .order_by(Province.nom)))


def territoires(session: Session, province_code: str) -> list[Territoire]:
    return list(session.scalars(
        select(Territoire).where(Territoire.province_code == province_code)
        .order_by(Territoire.nom)))


# --- Date de passage ------------------------------------------------------------------------

def _date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def consulter_passage(session: Session, u: Usager, territoire: Territoire) -> str:
    periodes = passages_publies(session, territoire.code)
    _consigner(session, u, "passage", "trouve" if periodes else "non_publie", territoire.code)
    if not periodes:
        return u.t["passage_non_publie"].format(territoire=territoire.nom)
    dates = ", ".join(u.t["periode"].format(debut=_date(p.date_debut), fin=_date(p.date_fin))
                      for p in periodes[:3])
    return u.t["passage_prevu"].format(territoire=territoire.nom, dates=dates)


# --- Badges ----------------------------------------------------------------------------------

@lru_cache
def limiteur_badges() -> LimiteurDebit:
    return LimiteurDebit(parametres().badges_verifications_par_heure, 3600)


class TropDeVerifications(Exception):
    pass


def verifier_badge(session: Session, u: Usager, numero: str,
                   reglages: Parametres) -> badges.Verification:
    """ValueError si le format est invalide ; TropDeVerifications au-delà du plafond horaire."""
    badges.normaliser_badge(numero)
    if not limiteur_badges().autoriser(u.empreinte):
        raise TropDeVerifications
    verification = badges.verifier(session, numero, reglages.pepper_telephone)
    _consigner(session, u, "badge", verification.statut, verification.territoire_code)
    return verification


def texte_badge(u: Usager, v: badges.Verification) -> str:
    cle = {"valide": "badge_valide", "retire": "badge_retire", "inconnu": "badge_inconnu"}[v.statut]
    return u.t[cle].format(numero=v.numero, territoire=v.territoire_nom or "")


# --- Signalements et rappels --------------------------------------------------------------

def signaler(session: Session, u: Usager, type_: str, territoire_code: str,
             localite: str | None = None, badge: str | None = None) -> Signalement:
    signalement = Signalement(
        canal=u.canal.value, type=type_, territoire_code=territoire_code,
        localite=masquer_donnees_sensibles(localite)[:120] if localite else None,
        # Numéro du badge présenté par un faux agent : utile à l'enquête, pas une donnée du citoyen.
        description=f"Badge présenté : {badges.normaliser_badge(badge)}" if badge else None,
        usager_empreinte=u.empreinte, statut="nouveau",
    )
    session.add(signalement)
    session.commit()
    return signalement


def demander_rappel(session: Session, u: Usager, reference: str) -> bool:
    """Crée une demande de rappel (numéro chiffré). False si une demande est déjà ouverte."""
    deja = session.scalar(select(Rappel.id).where(
        Rappel.usager_empreinte == u.empreinte, Rappel.statut.in_(("a_rappeler", "en_cours"))))
    if deja:
        return False
    session.add(Rappel(appel_reference=reference[:64], langue=u.langue, origine=u.canal.value,
                       usager_empreinte=u.empreinte, numero_chiffre=chiffrer_numero(u.telephone)))
    interactions.enregistrer(
        session, canal=u.canal, texte=f"[{u.canal.value.upper()}] demande de rappel",
        langue_demandee=u.langue, territoire_code=None, usager_empreinte=u.empreinte,
        reponse=connaissances.escalade("demande_humain"),
    )
    return True


def message_escalade(u: Usager, reglages: Parametres) -> str:
    if reglages.numero_vert:
        return u.t["escalade"].format(numero=reglages.numero_vert)
    return u.t["escalade_sans_numero"]


# --- Journal --------------------------------------------------------------------------------

def _consigner(session: Session, u: Usager, service: str, resultat: str,
               territoire_code: str | None) -> None:
    session.add(Consultation(canal=u.canal.value, service=service, resultat=resultat,
                             langue=u.langue, territoire_code=territoire_code,
                             usager_empreinte=u.empreinte))
    session.commit()
