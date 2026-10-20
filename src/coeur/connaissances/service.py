from sqlalchemy import select
from sqlalchemy.orm import Session

from coeur.commun import Canal
from coeur.config import Parametres
from coeur.confidentialite.service import empreinte_telephone
from coeur.connaissances.depot import Corpus
from coeur.connaissances.modeles import Langue
from coeur.connaissances.moteur import decider, demande_humain
from coeur.connaissances.schemas import (
    MESSAGE_ESCALADE,
    ContenuSortie,
    MotifEscalade,
    ReponseSortie,
)
from coeur.interactions import service as interactions


def texte_servi(corpus: Corpus, contenu_id: int, langue: str, langue_repli: str) -> ContenuSortie | None:
    """Texte publié dans la langue demandée, sinon dans la langue de repli (français)."""
    for essai in dict.fromkeys((langue, langue_repli)):
        texte = corpus.textes.get((contenu_id, essai))
        if texte:
            return ContenuSortie(
                contenu_id=texte.contenu_id,
                cle=texte.cle,
                categorie=texte.categorie,
                langue=texte.langue,
                repli_langue=essai != langue,
                question=texte.question,
                reponse=texte.reponse,
                reponse_courte=texte.reponse_courte,
                audio_url=texte.audio_url,
                audio_question_url=texte.audio_question_url,
            )
    return None


def escalade(motif: MotifEscalade, score: float = 0.0) -> ReponseSortie:
    return ReponseSortie(type="escalade", message=MESSAGE_ESCALADE, motif=motif, score=score)


def repondre(corpus: Corpus, texte: str, langue: str, reglages: Parametres) -> ReponseSortie:
    """Choisit un contenu validé ou escalade. Ne produit jamais de texte nouveau."""
    if demande_humain(texte):
        return escalade("demande_humain")

    langues = list(dict.fromkeys((langue, reglages.langue_par_defaut)))
    candidats = corpus.moteur.rechercher(texte, langues)
    decision = decider(candidats, reglages.seuil_confiance, reglages.marge_ambiguite)
    if decision.contenu_id is None:
        return escalade(decision.motif_escalade, decision.score)

    contenu = texte_servi(corpus, decision.contenu_id, langue, reglages.langue_par_defaut)
    if contenu is None:
        return escalade("traduction_indisponible", decision.score)
    return ReponseSortie(type="reponse", contenu=contenu, score=decision.score)


def traiter_question(
    session: Session,
    corpus: Corpus,
    reglages: Parametres,
    *,
    canal: Canal,
    texte: str,
    langue: str,
    territoire_code: str | None = None,
    telephone: str | None = None,
) -> ReponseSortie:
    """Répond puis journalise l'échange. Utilisé par l'API et par le portail web."""
    reponse = repondre(corpus, texte, langue, reglages)
    interactions.enregistrer(
        session,
        canal=canal,
        texte=texte,
        langue_demandee=langue,
        territoire_code=territoire_code,
        usager_empreinte=(
            empreinte_telephone(telephone, reglages.pepper_telephone) if telephone else None
        ),
        reponse=reponse,
    )
    return reponse


def langues_actives(session: Session) -> list[Langue]:
    """Langues proposées aux citoyens, le français en premier."""
    requete = select(Langue).where(Langue.active).order_by(Langue.code != "fr", Langue.nom)
    return list(session.scalars(requete))
