from fastapi import APIRouter, Depends, Form
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.commun import Canal
from coeur.config import Parametres, parametres
from coeur.connaissances.depot import Corpus
from coeur.connaissances.routes import corpus_courant
from coeur.securite import passerelle
from coeur.ussd import service

routeur = APIRouter(prefix="/v1/ussd", tags=["USSD"])


@routeur.post("", response_class=PlainTextResponse,
              dependencies=[Depends(passerelle(Canal.USSD))])
def ussd(
    sessionId: str = Form(max_length=100),
    phoneNumber: str = Form(max_length=20),
    text: str = Form(default="", max_length=500),
    serviceCode: str = Form(default="", max_length=20),
    session: Session = Depends(session_db),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
):
    """Échange USSD, au format le plus répandu chez les agrégateurs.

    Reçoit la saisie cumulée (`text`, ex. « 2*5*3 ») et répond en texte brut :
    `CON <écran>` pour attendre une saisie, `END <écran>` pour clore la session.
    """
    ecran = service.traiter(session, corpus, reglages, session_id=sessionId,
                            telephone=phoneNumber, texte=text)
    return ("END " if ecran.fin else "CON ") + ecran.texte
