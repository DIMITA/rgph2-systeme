"""Conversation WhatsApp : menus en listes et boutons, questions libres, mêmes services
que l'USSD et le SMS (socle `mobile`).

Chaque bouton ou ligne de liste porte un identifiant qui dit où l'on va (« q:12 »,
« terr:passage:NKV-GOM »…) : la conversation n'a besoin de mémoire que lorsqu'une
réponse libre est attendue (numéro de badge, quartier), voir `modeles.Conversation`.

Les messages vocaux sont transcrits (`coeur.comprehension`), puis traités comme une
question écrite, à une différence près : le citoyen confirme le sujet compris avant
de recevoir la réponse.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from coeur.comprehension.transcription import langue_ouverte, transcripteur
from coeur.config import Parametres
from coeur.confidentialite.service import masquer_donnees_sensibles
from coeur.connaissances import service as connaissances
from coeur.connaissances.depot import Corpus
from coeur.connaissances.schemas import ContenuSortie, ReponseSortie
from coeur.interactions import service as interactions
from coeur.mobile import service as mobile
from coeur.mobile.service import Usager
from coeur.sms.analyse import normaliser
from coeur.sms.service import executer_commande
from coeur.territoires.modeles import Territoire
from coeur.whatsapp import abonnements
from coeur.whatsapp.messages import MAX_LIGNES, Boutons, Ligne, Liste, Media, Message, Texte
from coeur.whatsapp.modeles import Conversation
from coeur.whatsapp.passerelle import passerelle

MOTS_STOP = {"STOP", "ARRET", "ARRETER", "DESABONNER"}
SALUTATIONS = {"BONJOUR", "BONSOIR", "SALUT", "MENU", "AIDE", "MBOTE", "JAMBO", "HELLO", "START"}
# Buts d'un choix de territoire.
PASSAGE, NON_VISITE, FAUX_AGENT = "passage", "nonvisite", "fauxagent"


@dataclass(frozen=True)
class Entree:
    """Message reçu : texte écrit, choix dans une liste ou un bouton, message vocal, ou
    autre (image, vidéo…)."""

    type: str  # « texte », « choix », « vocal » ou « autre »
    # Texte, identifiant du choix, ou identifiant du média chez Meta (message vocal).
    valeur: str = ""


@dataclass
class Contexte:
    session: Session
    corpus: Corpus
    reglages: Parametres
    usager: Usager

    @property
    def t(self) -> dict[str, str]:
        return self.usager.t


# --- Mémoire de la conversation ---------------------------------------------------------------

def _conversation(ctx: Contexte) -> Conversation:
    conv = ctx.session.get(Conversation, ctx.usager.empreinte)
    if conv is None:
        conv = Conversation(usager_empreinte=ctx.usager.empreinte, attente=None, contexte={})
        ctx.session.add(conv)
    return conv


def attendre(ctx: Contexte, attente: str | None, **contexte) -> None:
    conv = _conversation(ctx)
    conv.attente, conv.contexte = attente, contexte
    conv.maj_a = datetime.now(timezone.utc)
    ctx.session.commit()


def attente_en_cours(ctx: Contexte) -> tuple[str | None, dict]:
    conv = ctx.session.get(Conversation, ctx.usager.empreinte)
    if conv is None or conv.attente is None and not conv.contexte:
        return None, {}
    limite = datetime.now(timezone.utc) - timedelta(minutes=ctx.reglages.whatsapp_attente_minutes)
    if conv.maj_a.replace(tzinfo=conv.maj_a.tzinfo or timezone.utc) < limite:
        attendre(ctx, None)
        return None, {}
    return conv.attente, dict(conv.contexte or {})


# --- Écrans -----------------------------------------------------------------------------------

def menu(ctx: Contexte, intro: str | None = None) -> list[Message]:
    t = ctx.t
    lignes = [Ligne("faq", t["menu_faq"]), Ligne("passage", t["menu_passage"]),
              Ligne("badge", t["menu_badge"]), Ligne("nonvisite", t["menu_non_visite"]),
              Ligne("conseiller", t["menu_conseiller"]), Ligne("langues", t["menu_langue"])]
    corps = f"{intro}\n\n{t['wa_menu']}" if intro else t["wa_menu"]
    return [Liste(corps, t["wa_bouton_menu"], lignes)]


def bouton_menu(ctx: Contexte, corps: str) -> Boutons:
    return Boutons(corps, [("menu", ctx.t["wa_bouton_menu"])])


def langues(ctx: Contexte, intro: str | None = None) -> list[Message]:
    lignes = [Ligne(f"langue:{code}", nom)
              for _, code, nom in mobile.langues_proposees(ctx.session, ctx.reglages)]
    corps = f"{intro}\n\n{ctx.t['wa_choisir_langue']}" if intro else ctx.t["wa_choisir_langue"]
    return [Liste(corps, ctx.t["wa_bouton_choisir"], lignes)]


def paginer(ctx: Contexte, corps: str, lignes: list[Ligne], prefixe_page: str,
            page: int) -> Liste:
    """Liste de 10 lignes au plus ; au-delà, la 10e mène à la suite."""
    par_page = MAX_LIGNES - 1
    debut = page * par_page
    morceau = lignes[debut:debut + par_page]
    if len(lignes) > debut + par_page:
        morceau.append(Ligne(f"{prefixe_page}:{page + 1}", ctx.t["wa_suite"]))
    elif len(lignes) == MAX_LIGNES and page == 0:
        morceau = lignes  # exactement 10 : pas besoin de suite
    return Liste(corps, ctx.t["wa_bouton_choisir"], morceau)


def questions(ctx: Contexte, page: int = 0) -> list[Message]:
    contenus = [c for c in (connaissances.texte_servi(ctx.corpus, cid, ctx.usager.langue,
                                                      ctx.reglages.langue_par_defaut)
                            for cid in mobile.ordre_menu(ctx.session, ctx.corpus))
                if c is not None]
    if not contenus:
        return [bouton_menu(ctx, ctx.t["aucune_question"])]
    lignes = [Ligne(f"q:{c.contenu_id}", c.question, c.question) for c in contenus]
    return [paginer(ctx, ctx.t["wa_choisir_question"], lignes, "faq", page)]


def reponse(ctx: Contexte, contenu: ContenuSortie) -> list[Message]:
    """Réponse validée complète, puis son audio et sa vidéo en langue locale s'il y en a."""
    t = ctx.t
    entete = t["wa_reponse_officielle"]
    if contenu.repli_langue:
        entete = f"{t['wa_reponse_en_francais']}\n{entete}"
    messages: list[Message] = [Texte(f"*{contenu.question}*\n\n{entete}\n{contenu.reponse}")]
    if contenu.audio_url:
        messages.append(Media("audio", contenu.audio_url))
    if contenu.video_url:
        messages.append(Media("video", contenu.video_url, contenu.question))
    messages.append(bouton_menu(ctx, t["wa_menu"]))
    return messages


def provinces(ctx: Contexte, but: str, page: int = 0) -> list[Message]:
    lignes = [Ligne(f"prov:{but}:{p.code}", p.nom) for p in mobile.provinces(ctx.session)]
    return [paginer(ctx, ctx.t["choisir_province"], lignes, f"provp:{but}", page)]


def territoires(ctx: Contexte, but: str, province: str, page: int = 0) -> list[Message]:
    lignes = [Ligne(f"terr:{but}:{t.code}", t.nom) for t in mobile.territoires(ctx.session, province)]
    if not lignes:
        return provinces(ctx, but)
    return [paginer(ctx, ctx.t["choisir_territoire"], lignes, f"terrp:{but}:{province}", page)]


def confirmation(ctx: Contexte, type_: str, territoire: Territoire, localite: str | None = None,
                 badge: str | None = None) -> list[Message]:
    attendre(ctx, "confirmation", type=type_, territoire=territoire.code, localite=localite,
             badge=badge)
    lieu = ", ".join(filter(None, (territoire.nom, localite)))
    cle = "confirmer_agent" if type_ == "agent_douteux" else "confirmer_non_visite"
    return [Boutons(ctx.t[cle].format(lieu=lieu),
                    [("confirmer", ctx.t["confirmer"]), ("menu", ctx.t["wa_bouton_menu"])])]


def conseiller(ctx: Contexte) -> list[Message]:
    t = ctx.t
    corps = (t["conseiller_numero"].format(numero=ctx.reglages.numero_vert)
             if ctx.reglages.numero_vert else t["conseiller_sans_numero"])
    return [Boutons(corps, [("rappel", t["etre_rappele"]), ("menu", t["wa_bouton_menu"])])]


# --- Réactions ------------------------------------------------------------------------------

def choisir(ctx: Contexte, choix: str) -> list[Message]:
    """Réponse à un bouton ou à une ligne de liste."""
    t, u = ctx.t, ctx.usager
    partie = choix.split(":")
    action = partie[0]

    codes = {code for _, code, _ in mobile.langues_proposees(ctx.session, ctx.reglages)}
    if action == "langue" and len(partie) == 2 and partie[1] in codes:
        mobile.enregistrer_langue(ctx.session, u.empreinte, partie[1])
        u.langue = partie[1]
        attente, contexte = attente_en_cours(ctx)
        if attente == "question" and contexte.get("question"):
            attendre(ctx, None)
            return ecrire(ctx, contexte["question"])
        return menu(ctx)
    if action == "langues":
        return langues(ctx)
    if action == "faq":
        return questions(ctx, int(partie[1]) if len(partie) == 2 and partie[1].isdigit() else 0)
    if action == "q" and len(partie) == 2 and partie[1].isdigit():
        contenu = connaissances.texte_servi(ctx.corpus, int(partie[1]), u.langue,
                                            ctx.reglages.langue_par_defaut)
        if contenu is None:  # dé-publié depuis l'envoi de la liste
            return questions(ctx)
        mobile.journaliser_lecture(ctx.session, u, contenu)
        return reponse(ctx, contenu)
    if action == "passage":
        return provinces(ctx, PASSAGE)
    if action == "nonvisite":
        return provinces(ctx, NON_VISITE)
    if action == "badge":
        attendre(ctx, "badge")
        return [Texte(t["saisir_badge"])]
    if action == "faux" and len(partie) == 2:
        attendre(ctx, None, badge=partie[1])
        return provinces(ctx, FAUX_AGENT)
    if action in ("provp", "prov", "terrp") and len(partie) >= 3:
        if action == "provp":
            return provinces(ctx, partie[1], int(partie[2]) if partie[2].isdigit() else 0)
        if action == "prov":
            return territoires(ctx, partie[1], partie[2])
        page = int(partie[3]) if len(partie) == 4 and partie[3].isdigit() else 0
        return territoires(ctx, partie[1], partie[2], page)
    if action == "terr" and len(partie) == 3:
        territoire = ctx.session.get(Territoire, partie[2])
        if territoire is None:
            return menu(ctx)
        if partie[1] == PASSAGE:
            # Proposé que les dates soient publiées ou non : le rappel partira dès qu'elles le seront.
            return [Boutons(mobile.consulter_passage(ctx.session, u, territoire),
                            [(f"abonner:{territoire.code}", t["wa_prevenez_moi"]),
                             ("menu", t["wa_bouton_menu"])])]
        if partie[1] == NON_VISITE:
            attendre(ctx, "localite", territoire=territoire.code)
            return [Boutons(t["wa_saisir_localite"], [("passer", t["wa_passer"])])]
        _, contexte = attente_en_cours(ctx)
        return confirmation(ctx, "agent_douteux", territoire, badge=contexte.get("badge"))
    if action == "passer":
        attente, contexte = attente_en_cours(ctx)
        territoire = ctx.session.get(Territoire, contexte.get("territoire") or "")
        if attente == "localite" and territoire is not None:
            return confirmation(ctx, "menage_non_visite", territoire)
        return menu(ctx, t["wa_attente_expiree"])
    if action == "confirmer":
        attente, contexte = attente_en_cours(ctx)
        territoire = ctx.session.get(Territoire, contexte.get("territoire") or "")
        if attente != "confirmation" or territoire is None:
            return menu(ctx, t["wa_attente_expiree"])
        attendre(ctx, None)
        s = mobile.signaler(ctx.session, u, contexte["type"], territoire.code,
                            localite=contexte.get("localite"), badge=contexte.get("badge"))
        return [bouton_menu(ctx, t["signalement_enregistre"].format(id=s.id))]
    if action == "abonner" and len(partie) == 2:
        territoire = ctx.session.get(Territoire, partie[1])
        if territoire is None:
            return menu(ctx)
        resultat = abonnements.abonner(ctx.session, u, territoire, ctx.reglages)
        cle = {"cree": "wa_abonnement_ok", "deja": "wa_abonnement_deja",
               "maximum": "wa_abonnements_max"}[resultat]
        return [bouton_menu(ctx, t[cle].format(territoire=territoire.nom,
                                               maximum=ctx.reglages.whatsapp_abonnements_max))]
    if action == "vocal" and len(partie) == 2:
        return confirmer_vocal(ctx, partie[1] == "oui")
    if action == "stop":
        return arreter(ctx)
    if action == "conseiller":
        return conseiller(ctx)
    if action == "rappel":
        cree = mobile.demander_rappel(ctx.session, u, "whatsapp")
        return [bouton_menu(ctx, t["rappel_enregistre" if cree else "rappel_deja"])]
    return menu(ctx)


def arreter(ctx: Contexte) -> list[Message]:
    supprimes = abonnements.arreter(ctx.session, ctx.usager.empreinte)
    return [bouton_menu(ctx, ctx.t["wa_stop_ok" if supprimes else "wa_stop_aucun"])]


def _salutation(mots: list[str]) -> bool:
    return not mots or (len(mots) <= 2 and mots[0] in SALUTATIONS)


def ecrire(ctx: Contexte, texte: str) -> list[Message]:
    """Réponse à un message écrit : saisie attendue, mot-clé, salutation ou question."""
    t, u = ctx.t, ctx.usager
    attente, contexte = attente_en_cours(ctx)

    if attente == "badge":
        attendre(ctx, None)
        try:
            v = mobile.verifier_badge(ctx.session, u, texte, ctx.reglages)
        except ValueError:
            attendre(ctx, "badge")
            return [Texte(f"{t['badge_format']}\n{t['saisir_badge']}")]
        except mobile.TropDeVerifications:
            return [bouton_menu(ctx, t["trop_de_verifications"])]
        resultat = mobile.texte_badge(u, v)
        if v.statut != "inconnu":
            return [bouton_menu(ctx, resultat)]
        return [Boutons(resultat, [(f"faux:{v.numero}", t["signaler_agent"]),
                                   ("menu", t["wa_bouton_menu"])])]

    if attente == "localite":
        territoire = ctx.session.get(Territoire, contexte.get("territoire") or "")
        if territoire is not None:
            return confirmation(ctx, "menage_non_visite", territoire, localite=texte[:60])

    mots = normaliser(texte).split()
    if len(mots) == 1 and mots[0] in MOTS_STOP:
        return arreter(ctx)
    if _salutation(mots):
        return menu(ctx, t["wa_bienvenue"])

    reponse_commande = executer_commande(ctx.session, ctx.reglages, u, texte)
    if reponse_commande is not None:
        return [bouton_menu(ctx, reponse_commande)]

    resultat = connaissances.traiter_question(
        ctx.session, ctx.corpus, ctx.reglages, canal=u.canal, texte=texte[:500],
        langue=u.langue, telephone=u.telephone)
    if resultat.contenu is not None:
        return reponse(ctx, resultat.contenu)
    return escalade(ctx)


def escalade(ctx: Contexte) -> list[Message]:
    t = ctx.t
    corps = (t["wa_escalade"].format(numero=ctx.reglages.numero_vert)
             if ctx.reglages.numero_vert else t["wa_escalade_sans_numero"])
    return [Boutons(corps, [("rappel", t["etre_rappele"]), ("menu", t["wa_bouton_menu"])])]


# --- Messages vocaux ------------------------------------------------------------------------

def _proposer_rappel(ctx: Contexte, cle: str) -> list[Message]:
    t = ctx.t
    return [Boutons(t[cle], [("rappel", t["etre_rappele"]), ("menu", t["wa_bouton_menu"])])]


def _journaliser_vocal(ctx: Contexte, texte: str, reponse_: ReponseSortie) -> None:
    interactions.enregistrer(
        ctx.session, canal=ctx.usager.canal, texte=texte, langue_demandee=ctx.usager.langue,
        territoire_code=None, usager_empreinte=ctx.usager.empreinte, reponse=reponse_,
        entree="voix")


def ecouter(ctx: Contexte, media_id: str) -> list[Message]:
    """Message vocal : transcrit, puis le sujet compris est soumis au citoyen (Oui / Non).

    La voix n'est gardée qu'en mémoire, le temps de la transcription. Rien ne répond
    sans confirmation : une erreur de compréhension coûte un « Non », jamais une
    fausse information officielle.
    """
    reglages = ctx.reglages
    moteur = transcripteur()
    if moteur is None or not langue_ouverte(ctx.usager.langue, reglages):
        return _proposer_rappel(ctx, "wa_vocal_langue_fermee")
    media = passerelle().telecharger(media_id, reglages.transcription_taille_max_ko * 1024)
    if media is None:
        return _proposer_rappel(ctx, "wa_vocal_illisible")
    transcription = moteur.transcrire(media[0], media[1], ctx.usager.langue)
    if transcription is None:
        return _proposer_rappel(ctx, "wa_vocal_non_compris")
    texte = transcription.texte[:500]
    resultat = connaissances.repondre(ctx.corpus, texte, ctx.usager.langue, reglages)
    if resultat.contenu is None:
        _journaliser_vocal(ctx, texte, resultat)
        return escalade(ctx)
    contenu = resultat.contenu
    attendre(ctx, "confirmation_vocale", contenu=contenu.contenu_id,
             texte=masquer_donnees_sensibles(texte)[:500], score=resultat.score)
    messages: list[Message] = []
    if contenu.audio_question_url:
        messages.append(Media("audio", contenu.audio_question_url))
    messages.append(Boutons(ctx.t["wa_vocal_confirmer"].format(question=contenu.question),
                            [("vocal:oui", ctx.t["wa_oui"]), ("vocal:non", ctx.t["wa_non"])]))
    return messages


def confirmer_vocal(ctx: Contexte, oui: bool) -> list[Message]:
    attente, contexte = attente_en_cours(ctx)
    if attente != "confirmation_vocale":
        return menu(ctx, ctx.t["wa_attente_expiree"])
    attendre(ctx, None)
    contenu = connaissances.texte_servi(ctx.corpus, contexte["contenu"], ctx.usager.langue,
                                        ctx.reglages.langue_par_defaut)
    if oui and contenu is not None:
        _journaliser_vocal(ctx, contexte["texte"], ReponseSortie(
            type="reponse", contenu=contenu, score=contexte.get("score", 0.0)))
        return reponse(ctx, contenu)
    _journaliser_vocal(ctx, contexte["texte"], connaissances.escalade(
        "vocal_non_confirme", contexte.get("score", 0.0)))
    return _proposer_rappel(ctx, "wa_vocal_reformuler")


def traiter(ctx: Contexte, entree: Entree, premier_contact: bool) -> list[Message]:
    if premier_contact:
        # Une question posée dans le premier message est gardée (masquée) le temps du
        # choix de la langue, puis traitée comme si elle venait d'être écrite.
        texte = entree.valeur.strip() if entree.type == "texte" else ""
        if not _salutation(normaliser(texte).split()):
            attendre(ctx, "question", question=masquer_donnees_sensibles(texte)[:500])
        return langues(ctx, ctx.t["wa_bienvenue"])
    if entree.type == "choix":
        return choisir(ctx, entree.valeur)
    if entree.type == "texte":
        return ecrire(ctx, entree.valeur.strip())
    if entree.type == "vocal":
        return ecouter(ctx, entree.valeur)
    return menu(ctx, ctx.t["wa_media_non_lu"])
