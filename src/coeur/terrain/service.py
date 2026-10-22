"""Appareils de terrain : enrôlement, paquet hors ligne, remontées."""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from coeur.calendrier.modeles import Passage
from coeur.commun import Canal
from coeur.config import Parametres
from coeur.confidentialite.service import masquer_donnees_sensibles
from coeur.connaissances import service as connaissances
from coeur.connaissances.depot import Corpus
from coeur.connaissances.modeles import STATUT_PUBLIE
from coeur.connaissances.schemas import ReponseSortie
from coeur.interactions import service as interactions
from coeur.mobile.modeles import Consultation
from coeur.mobile.service import ordre_menu
from coeur.signalements.modeles import Signalement
from coeur.terrain import schemas
from coeur.terrain.modeles import Appareil, RemonteeRecue
from coeur.terrain.textes import textes
from coeur.territoires.service import lister as lister_territoires
from coeur.territoires.service import territoire_existe

# Sans 0/O, 1/I/L : le code est recopié à la main sur la tablette.
ALPHABET_ACTIVATION = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LONGUEUR_ACTIVATION = 12
# Une remontée datée de plus loin (horloge de l'appareil déréglée) prend l'heure de réception.
ANCIENNETE_MAX = timedelta(days=60)
AVANCE_MAX = timedelta(minutes=10)
REMONTEES_PAR_ENVOI = 200

_ADAPTATEUR = TypeAdapter(schemas.Remontee)


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _empreinte(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def normaliser_code(code: str) -> str:
    return re.sub(r"[\s\-]", "", code).upper()


# --- Enrôlement -----------------------------------------------------------------------------

def _nouveau_code_activation(appareil: Appareil, jours: int) -> str:
    code = "".join(secrets.choice(ALPHABET_ACTIVATION) for _ in range(LONGUEUR_ACTIVATION))
    appareil.activation_empreinte = _empreinte(code)
    appareil.activation_expire_a = _maintenant() + timedelta(days=jours)
    return "-".join(code[i:i + 4] for i in range(0, LONGUEUR_ACTIVATION, 4))


def creer(session: Session, *, type_: str, code: str, territoire_code: str, langues: list[str],
          lieu: str | None, jours_activation: int) -> tuple[Appareil, str]:
    """Crée l'appareil et renvoie son code d'activation, montré une seule fois.

    ValueError si le code est déjà pris ou le territoire inconnu.
    """
    code = code.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9\-]{2,39}", code):
        raise ValueError("Code d'appareil invalide (lettres, chiffres et tirets)")
    if not territoire_existe(session, territoire_code):
        raise ValueError("Territoire inconnu")
    if session.scalar(select(Appareil.id).where(Appareil.code == code)) is not None:
        raise ValueError(f"Le code {code} est déjà utilisé")
    langues = list(dict.fromkeys(["fr", *langues]))
    appareil = Appareil(type=type_, code=code, territoire_code=territoire_code,
                        langues=",".join(langues), lieu=(lieu or "").strip()[:120] or None)
    activation = _nouveau_code_activation(appareil, jours_activation)
    session.add(appareil)
    session.commit()
    return appareil, activation


def reactiver(session: Session, appareil: Appareil, jours_activation: int) -> str:
    """Nouveau code d'activation (tablette remplacée, application réinstallée).

    L'ancien jeton cesse aussitôt de fonctionner.
    """
    activation = _nouveau_code_activation(appareil, jours_activation)
    appareil.jeton_empreinte = None
    appareil.revoque_a = None
    session.commit()
    return activation


def revoquer(session: Session, appareil: Appareil) -> None:
    """Appareil perdu ou volé : jeton et code d'activation n'ouvrent plus rien."""
    appareil.jeton_empreinte = None
    appareil.activation_empreinte = None
    appareil.revoque_a = _maintenant()
    session.commit()


def activer(session: Session, code: str) -> str | None:
    """Échange un code d'activation valide contre le jeton de l'appareil (une seule fois)."""
    appareil = session.scalar(
        select(Appareil).where(Appareil.activation_empreinte == _empreinte(normaliser_code(code)))
        .with_for_update()
    )
    if appareil is None or appareil.activation_expire_a is None \
            or appareil.activation_expire_a < _maintenant():
        return None
    jeton = secrets.token_urlsafe(32)
    appareil.jeton_empreinte = _empreinte(jeton)
    appareil.activation_empreinte = None
    appareil.activation_expire_a = None
    appareil.active_a = _maintenant()
    session.commit()
    return jeton


def par_jeton(session: Session, jeton: str) -> Appareil | None:
    return session.scalar(select(Appareil).where(Appareil.jeton_empreinte == _empreinte(jeton)))


def lister(session: Session) -> list[Appareil]:
    return list(session.scalars(select(Appareil).order_by(Appareil.type, Appareil.code)))


# --- Paquet ---------------------------------------------------------------------------------

def langues_du_paquet(session: Session, appareil: Appareil) -> list[schemas.LangueSortie]:
    actives = {l.code: l.nom for l in connaissances.langues_actives(session)}
    return [schemas.LangueSortie(code=c, nom=actives[c])
            for c in appareil.liste_langues() if c in actives]


def paquet(session: Session, corpus: Corpus, reglages: Parametres,
           appareil: Appareil) -> schemas.PaquetSortie:
    langues = langues_du_paquet(session, appareil)
    ordre = ordre_menu(session, corpus)
    faq = {
        l.code: [c for c in (connaissances.texte_servi(corpus, cid, l.code,
                                                       reglages.langue_par_defaut)
                             for cid in ordre) if c is not None]
        for l in langues
    }
    calendrier = [
        schemas.PeriodeSortie(territoire_code=p.territoire_code, debut=p.date_debut, fin=p.date_fin)
        for p in session.scalars(select(Passage).where(Passage.statut == STATUT_PUBLIE)
                                 .order_by(Passage.territoire_code, Passage.date_debut, Passage.id))
    ]
    contenu = schemas.PaquetSortie(
        version="", genere_a=_maintenant(),
        appareil=schemas.AppareilSortie(code=appareil.code, type=appareil.type,
                                        lieu=appareil.lieu,
                                        territoire_code=appareil.territoire_code),
        langues=langues, faq=faq, provinces=lister_territoires(session), calendrier=calendrier,
        textes={l.code: textes(l.code) for l in langues},
        numero_vert=reglages.numero_vert, ussd_code=reglages.ussd_code,
    )
    # La version ne dépend que du contenu : inchangée, l'appareil ne retélécharge rien.
    serialise = contenu.model_dump_json(exclude={"version", "genere_a"})
    return contenu.model_copy(update={"version": hashlib.sha256(serialise.encode()).hexdigest()[:32]})


def noter_synchronisation(session: Session, appareil: Appareil, version: str) -> None:
    appareil.derniere_synchro_a = _maintenant()
    appareil.version_paquet = version
    session.commit()


# --- Remontées ------------------------------------------------------------------------------

def _heure(horodatage: datetime | None) -> datetime:
    maintenant = _maintenant()
    if horodatage is None:
        return maintenant
    if horodatage.tzinfo is None:
        horodatage = horodatage.replace(tzinfo=timezone.utc)
    if not maintenant - ANCIENNETE_MAX <= horodatage <= maintenant + AVANCE_MAX:
        return maintenant
    return horodatage


def _enregistrer(session: Session, corpus: Corpus, reglages: Parametres, appareil: Appareil,
                 r: schemas.Consultation | schemas.Question | schemas.Signalement
                 | schemas.Passage) -> None:
    """Ajoute la remontée à la session ; l'appelant valide (commit) ou annule."""
    canal = Canal(appareil.type)
    heure = _heure(r.horodatage)
    if isinstance(r, schemas.Consultation):
        contenu = connaissances.texte_servi(corpus, r.contenu_id, r.langue,
                                            reglages.langue_par_defaut)
        cle = contenu.cle if contenu else f"#{r.contenu_id}"
        interactions.enregistrer(
            session, canal=canal, texte=f"[{canal.value.upper()}] question consultée : {cle}",
            langue_demandee=r.langue, territoire_code=appareil.territoire_code,
            usager_empreinte=None, horodatage=heure,
            reponse=ReponseSortie(type="reponse", contenu=contenu, score=1.0),
        )
    elif isinstance(r, schemas.Question):
        interactions.enregistrer(
            session, canal=canal, texte=r.texte, langue_demandee=r.langue,
            territoire_code=appareil.territoire_code, usager_empreinte=None, horodatage=heure,
            reponse=connaissances.escalade("remontee_terrain"),
        )
    elif isinstance(r, schemas.Signalement):
        session.add(Signalement(
            horodatage=heure, canal=canal.value, type=r.signalement,
            territoire_code=r.territoire_code,
            localite=masquer_donnees_sensibles(r.localite)[:120] if r.localite else None,
            description=masquer_donnees_sensibles(r.description)[:500] if r.description else None,
            usager_empreinte=None, statut="nouveau",
        ))
    else:
        session.add(Consultation(horodatage=heure, canal=canal.value, service="passage",
                                 resultat=r.resultat, langue=r.langue,
                                 territoire_code=r.territoire_code, usager_empreinte=None))


def recevoir(session: Session, corpus: Corpus, reglages: Parametres, appareil: Appareil,
             elements: list) -> schemas.RemonteesSortie:
    """Enregistre chaque remontée dans sa propre transaction, une seule fois par identifiant."""
    acceptes, rejetes = [], []
    for element in elements:
        identifiant = element.get("id") if isinstance(element, dict) else None
        identifiant = identifiant if isinstance(identifiant, str) else None
        try:
            remontee = _ADAPTATEUR.validate_python(element)
        except ValidationError:
            rejetes.append(schemas.Rejet(id=identifiant, raison="invalide"))
            continue
        if session.get(RemonteeRecue, remontee.id) is not None:
            acceptes.append(remontee.id)
            continue
        territoire = getattr(remontee, "territoire_code", None)
        if territoire is not None and not territoire_existe(session, territoire):
            rejetes.append(schemas.Rejet(id=remontee.id, raison="territoire_inconnu"))
            continue
        session.add(RemonteeRecue(id=remontee.id, appareil_id=appareil.id, type=remontee.type))
        try:
            # Les interactions valident elles-mêmes ; sinon, on valide ici.
            _enregistrer(session, corpus, reglages, appareil, remontee)
            session.commit()
        except IntegrityError:
            # Même identifiant reçu en parallèle par un autre processus : déjà enregistrée.
            session.rollback()
        acceptes.append(remontee.id)
    return schemas.RemonteesSortie(acceptes=acceptes, rejetes=rejetes)


def purger_remontees(session: Session, jours: int) -> int:
    limite = _maintenant() - timedelta(days=jours)
    return session.execute(delete(RemonteeRecue).where(RemonteeRecue.recu_a < limite)).rowcount
