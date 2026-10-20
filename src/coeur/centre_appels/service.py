"""Règles du centre d'appels : menu du SVI, suivi des appels, rappels, enregistrements."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from coeur.centre_appels.modeles import Appel, Enregistrement, Rappel
from coeur.centre_appels.schemas import ElementMenu, EvenementAppel, LangueMenu, MenuSvi
from coeur.commun import Canal
from coeur.config import Parametres, parametres
from coeur.confidentialite.service import empreinte_telephone, normaliser_telephone
from coeur.connaissances import service as connaissances
from coeur.connaissances.depot import Corpus
from coeur.connaissances.modeles import STATUT_PUBLIE, Contenu
from coeur.connaissances.schemas import ReponseSortie
from coeur.interactions import service as interactions

NB_TOUCHES_MENU = 8


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


# --- Menu du SVI -------------------------------------------------------------------------

def menu_svi(session: Session, corpus: Corpus, reglages: Parametres) -> MenuSvi:
    """Langues (touches fixes) et, par langue, les contenus publiés placés dans le menu."""
    actives = {l.code: l.nom for l in connaissances.langues_actives(session)}
    langues = [
        LangueMenu(code=code, nom=actives[code], touche=touche)
        for code, touche in sorted(reglages.touches_langues().items(), key=lambda p: p[1])
        if code in actives
    ]
    places = session.scalars(
        select(Contenu.id)
        .where(Contenu.statut == STATUT_PUBLIE, Contenu.ordre_svi.is_not(None))
        .order_by(Contenu.ordre_svi, Contenu.id)
    ).all()
    menus = {}
    for langue in langues:
        elements = []
        for contenu_id in places:
            texte = connaissances.texte_servi(
                corpus, contenu_id, langue.code, reglages.langue_par_defaut
            )
            if texte is None or len(elements) == NB_TOUCHES_MENU:
                continue
            elements.append(ElementMenu(
                touche=len(elements) + 1, contenu_id=contenu_id, cle=texte.cle,
                langue=texte.langue, repli_langue=texte.repli_langue,
                question=texte.question, reponse=texte.reponse,
                audio_url=texte.audio_url, audio_question_url=texte.audio_question_url,
            ))
        menus[langue.code] = elements
    return MenuSvi(langues=langues, menus=menus)


# --- Événements d'appel -----------------------------------------------------------------

def _appel(session: Session, reference: str) -> Appel:
    """Appel existant, ou créé si Asterisk n'a pas pu signaler son début."""
    appel = session.scalar(select(Appel).where(Appel.reference == reference))
    if appel is None:
        appel = Appel(reference=reference)
        session.add(appel)
        session.flush()
    return appel


def _empreinte(numero: str | None, pepper: str) -> str | None:
    try:
        return empreinte_telephone(numero, pepper) if numero else None
    except ValueError:  # numéro masqué (« anonymous »), code court…
        return None


def chiffrer_numero(numero: str) -> str:
    return Fernet(parametres().cle_chiffrement).encrypt(numero.encode()).decode()


def dechiffrer_numero(chiffre: str) -> str:
    return Fernet(parametres().cle_chiffrement).decrypt(chiffre.encode()).decode()


def traiter_evenement(
    session: Session, corpus: Corpus, reglages: Parametres, ev: EvenementAppel
) -> dict:
    appel = _appel(session, ev.appel)
    if ev.langue:
        appel.langue = ev.langue
    resultat: dict = {"enregistre": True}

    if ev.type == "debut":
        appel.usager_empreinte = appel.usager_empreinte or _empreinte(
            ev.numero, reglages.pepper_telephone
        )

    elif ev.type == "svi_ecoute" and ev.contenu_id is not None:
        langue = appel.langue or reglages.langue_par_defaut
        contenu = connaissances.texte_servi(
            corpus, ev.contenu_id, langue, reglages.langue_par_defaut
        )
        if contenu is None:  # dé-publié depuis la dernière synchronisation du SVI
            resultat["enregistre"] = False
        else:
            _journaliser(session, appel, f"[Appel] réponse écoutée : {contenu.cle}",
                         ReponseSortie(type="reponse", contenu=contenu, score=1.0))

    elif ev.type == "file_entree" and appel.entree_file_a is None:
        appel.entree_file_a = _maintenant()
        _journaliser(session, appel, "[Appel] demande à parler à un conseiller",
                     connaissances.escalade("demande_humain"))

    elif ev.type == "decroche":
        appel.decroche_a = appel.decroche_a or _maintenant()
        appel.poste = ev.poste
        if ev.fichier and not session.scalar(
            select(Enregistrement.id).where(Enregistrement.fichier == ev.fichier)
        ):
            session.add(Enregistrement(appel_reference=ev.appel, fichier=ev.fichier,
                                       poste=ev.poste))

    elif ev.type == "rappel":
        try:
            numero = normaliser_telephone(ev.numero or "")
        except ValueError:
            resultat["enregistre"] = False
        else:
            appel.rappel_demande = True
            session.add(Rappel(appel_reference=ev.appel, langue=appel.langue,
                               numero_chiffre=chiffrer_numero(numero)))

    elif ev.type == "fin":
        appel.fin_a = _maintenant()

    session.commit()
    return resultat


def _journaliser(session: Session, appel: Appel, texte: str, reponse: ReponseSortie) -> None:
    interactions.enregistrer(
        session, canal=Canal.CENTRE_ECOUTE, texte=texte,
        langue_demandee=appel.langue or parametres().langue_par_defaut,
        territoire_code=None, usager_empreinte=appel.usager_empreinte, reponse=reponse,
    )


# --- Rappels ----------------------------------------------------------------------------

def traiter_rappel(session: Session, rappel_id: int, statut: str, agent: str) -> Rappel | None:
    """Clôt une demande de rappel et efface aussitôt le numéro."""
    rappel = session.get(Rappel, rappel_id)
    if rappel is None:
        return None
    rappel.statut = statut
    rappel.numero_chiffre = None
    rappel.traite_a = _maintenant()
    rappel.traite_par = agent
    session.commit()
    return rappel


def expirer_rappels(session: Session, jours: int) -> int:
    """Efface le numéro des demandes non traitées depuis plus de `jours` jours."""
    limite = _maintenant() - timedelta(days=jours)
    resultat = session.execute(
        update(Rappel)
        .where(Rappel.cree_a < limite, Rappel.numero_chiffre.is_not(None))
        .values(statut="expire", numero_chiffre=None, traite_a=_maintenant())
    )
    session.commit()
    return resultat.rowcount


# --- Enregistrements --------------------------------------------------------------------

def _supprimer_fichiers(fichiers: list[str]) -> None:
    dossier = Path(parametres().dossier_enregistrements)
    for nom in fichiers:
        (dossier / Path(nom).name).unlink(missing_ok=True)


def supprimer_enregistrements_avant(session: Session, avant: datetime) -> int:
    """Supprime fichiers et lignes des enregistrements créés avant `avant`."""
    fichiers = list(session.scalars(
        select(Enregistrement.fichier).where(Enregistrement.cree_a < avant)
    ))
    _supprimer_fichiers(fichiers)
    session.execute(delete(Enregistrement).where(Enregistrement.cree_a < avant))
    session.commit()
    return len(fichiers)


def purger_enregistrements(session: Session, jours: int) -> int:
    return supprimer_enregistrements_avant(session, _maintenant() - timedelta(days=jours))
