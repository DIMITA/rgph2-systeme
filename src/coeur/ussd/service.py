import threading
import time

from sqlalchemy.orm import Session

from coeur.commun import Canal
from coeur.config import Parametres
from coeur.confidentialite.service import normaliser_telephone
from coeur.connaissances.depot import Corpus
from coeur.mobile import service as mobile
from coeur.mobile.textes import textes
from coeur.ussd.moteur import Contexte, Ecran, assembler, parcourir

# Les passerelles renvoient parfois une requête restée sans réponse : la même saisie
# d'une même session reçoit alors le même écran, sans refaire l'action.
DUREE_MEMOIRE = 300


class MemoireCourte:
    """(session USSD, saisie) → écran, oublié après DUREE_MEMOIRE secondes."""

    def __init__(self) -> None:
        self._ecrans: dict[tuple[str, str], tuple[float, Ecran]] = {}
        self._verrou = threading.Lock()

    def lire(self, cle: tuple[str, str]) -> Ecran | None:
        with self._verrou:
            limite = time.monotonic() - DUREE_MEMOIRE
            for c in [c for c, (t, _) in self._ecrans.items() if t < limite]:
                del self._ecrans[c]
            trouve = self._ecrans.get(cle)
            return trouve[1] if trouve else None

    def garder(self, cle: tuple[str, str], ecran: Ecran) -> None:
        with self._verrou:
            self._ecrans[cle] = (time.monotonic(), ecran)

    def vider(self) -> None:
        with self._verrou:
            self._ecrans.clear()


memoire = MemoireCourte()


def saisies(texte: str) -> list[str]:
    return [s.strip() for s in texte.split("*")] if texte.strip() else []


def traiter(session: Session, corpus: Corpus, reglages: Parametres, *,
            session_id: str, telephone: str, texte: str) -> Ecran:
    cle = (session_id, texte)
    deja = memoire.lire(cle)
    if deja is not None:
        return deja
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
    memoire.garder(cle, ecran)
    return ecran
