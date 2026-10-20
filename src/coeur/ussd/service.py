from sqlalchemy.orm import Session

from coeur.commun import Canal
from coeur.config import Parametres
from coeur.confidentialite.service import normaliser_telephone
from coeur.connaissances.depot import Corpus
from coeur.limiteur import MemoireCourte
from coeur.mobile import service as mobile
from coeur.mobile.textes import textes
from coeur.ussd.moteur import Contexte, Ecran, assembler, parcourir

# Les passerelles renvoient parfois une requête restée sans réponse : la même saisie
# d'une même session reçoit alors le même écran, sans refaire l'action.
DUREE_MEMOIRE = 300


# (session USSD, saisie cumulée) → écran, partagé par tous les processus.
memoire = MemoireCourte("ussd", DUREE_MEMOIRE)


def saisies(texte: str) -> list[str]:
    return [s.strip() for s in texte.split("*")] if texte.strip() else []


def traiter(session: Session, corpus: Corpus, reglages: Parametres, *,
            session_id: str, telephone: str, texte: str) -> Ecran:
    cle = f"{session_id}\n{texte}"
    deja = memoire.lire(cle)
    if deja is not None:
        return Ecran(**deja)
    try:
        numero = normaliser_telephone(telephone)
    except ValueError:
        return Ecran(assembler([textes(reglages.langue_par_defaut)["choix_invalide"]]), fin=True)
    u = mobile.usager(session, Canal.USSD, numero, reglages)
    # Le parcours est rejoué depuis le premier écran : dans la langue de ce moment-là.
    langue_initiale = mobile.langue_en_debut_de_session(session, u.empreinte, session_id)
    u.langue = langue_initiale or reglages.langue_par_defaut
    ctx = Contexte(session=session, corpus=corpus, reglages=reglages, usager=u,
                   reference=session_id)
    ecran = parcourir(ctx, saisies(texte), langue_connue=langue_initiale is not None)
    memoire.garder(cle, {"texte": ecran.texte, "fin": ecran.fin})
    return ecran
