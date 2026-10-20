"""Menus USSD.

Les passerelles USSD renvoient à chaque échange tout ce que l'usager a tapé depuis
le début de la session, séparé par « * » (ex. « 2*5*3 »). Le moteur rejoue donc le
parcours depuis l'écran d'accueil : aucune session n'est gardée côté serveur.

Conséquence : une action qui a un effet (signalement, rappel, SMS, compteur de
vérifications) ne s'exécute que pour la dernière saisie (`ctx.actif`), jamais
quand une saisie plus ancienne est rejouée.

Conventions de navigation : « 0 » revient à l'écran précédent, « 98 » affiche la
suite d'une liste trop longue pour un seul écran (182 caractères au plus).
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from coeur.badges import service as badges
from coeur.config import Parametres
from coeur.connaissances.depot import Corpus
from coeur.connaissances.schemas import ContenuSortie
from coeur.mobile import service as mobile
from coeur.mobile.gsm import couper, en_gsm
from coeur.mobile.service import Usager
from coeur.sms import service as sms
from coeur.territoires.modeles import Territoire

LONGUEUR_ECRAN = 182
# Place gardée pour « Choix invalide. » au-dessus d'une liste.
RESERVE_ERREUR = 22
LONGUEUR_LIBELLE = 40
RETOUR = "0"
SUITE = "98"


@dataclass
class Ecran:
    texte: str
    # Vrai : dernier écran, la session USSD se termine.
    fin: bool = False


@dataclass
class Erreur:
    """Saisie refusée : le message s'affiche au-dessus de l'écran courant."""

    message: str


@dataclass
class Contexte:
    session: Session
    corpus: Corpus
    reglages: Parametres
    usager: Usager
    # Identifiant de session de la passerelle (sert de référence aux demandes de rappel).
    reference: str
    # Vrai seulement pendant le traitement de la dernière saisie.
    actif: bool = False

    @property
    def t(self) -> dict[str, str]:
        return self.usager.t


Suite = "Etat | Ecran | Erreur | None"


def assembler(lignes: list[str], retour: str | None = None) -> str:
    """Écran final : alphabet GSM, et « 0 Retour » abandonné plutôt que dépasser 182."""
    texte = en_gsm("\n".join(lignes))
    if retour:
        avec_retour = en_gsm(f"{texte}\n{RETOUR} {retour}")
        if len(avec_retour) <= LONGUEUR_ECRAN:
            return avec_retour
    return texte[:LONGUEUR_ECRAN]


class Etat:
    # Un état « racine » vide l'historique : « 0 » n'y ramène nulle part.
    racine = False

    def ecran(self, ctx: Contexte) -> str:
        raise NotImplementedError

    def choisir(self, ctx: Contexte, saisie: str) -> Suite:
        """Nouvel état, écran de fin, Erreur, ou None (choix invalide)."""
        raise NotImplementedError


Action = Callable[[Contexte], Suite]


@dataclass
class Menu(Etat):
    """Liste numérotée, découpée en pages tenant chacune dans un écran."""

    titre: str
    options: list[tuple[str, Action]]
    racine: bool = False
    page: int = 0
    _pages: list[range] = field(default_factory=list, init=False, repr=False)

    def _decouper(self, ctx: Contexte) -> list[range]:
        if self._pages:
            return self._pages
        pied_retour = 0 if self.racine else len(f"\n{RETOUR} {ctx.t['retour']}")
        pied_suite = len(f"\n{SUITE} {ctx.t['suite']}")
        lignes = [len(f"\n{i + 1} {couper(libelle, LONGUEUR_LIBELLE)}")
                  for i, (libelle, _) in enumerate(self.options)]
        # Une liste qui tient entière dans un écran n'est jamais découpée (le message
        # « Choix invalide » sera alors omis plutôt que de couper le menu).
        if len(self.titre) + sum(lignes) + pied_retour <= LONGUEUR_ECRAN:
            self._pages = [range(len(self.options))]
            return self._pages
        budget = LONGUEUR_ECRAN - RESERVE_ERREUR
        debut, taille = 0, len(self.titre)
        for i, (libelle, _) in enumerate(self.options):
            ligne = len(f"\n{i + 1} {couper(libelle, LONGUEUR_LIBELLE)}")
            reste = i + 1 < len(self.options)
            if i > debut and taille + ligne + pied_retour + (pied_suite if reste else 0) > budget:
                self._pages.append(range(debut, i))
                debut, taille = i, len(self.titre)
            taille += ligne
        self._pages.append(range(debut, len(self.options)))
        return self._pages

    def ecran(self, ctx: Contexte) -> str:
        pages = self._decouper(ctx)
        lignes = [self.titre]
        lignes += [f"{i + 1} {couper(self.options[i][0], LONGUEUR_LIBELLE)}" for i in pages[self.page]]
        if self.page + 1 < len(pages):
            lignes.append(f"{SUITE} {ctx.t['suite']}")
        return assembler(lignes, None if self.racine else ctx.t["retour"])

    def a_suite(self, ctx: Contexte) -> bool:
        return self.page + 1 < len(self._decouper(ctx))

    def choisir(self, ctx: Contexte, saisie: str) -> Suite:
        if not saisie.isdigit() or int(saisie) - 1 not in self._decouper(ctx)[self.page]:
            return None
        return self.options[int(saisie) - 1][1](ctx)


@dataclass
class Saisie(Etat):
    """Texte libre (numéro de badge, quartier) : toute saisie autre que « 0 » est transmise."""

    consigne: str
    traiter: Callable[[Contexte, str], Suite]

    def ecran(self, ctx: Contexte) -> str:
        return assembler([self.consigne], ctx.t["retour"])

    def choisir(self, ctx: Contexte, saisie: str) -> Suite:
        return self.traiter(ctx, saisie.strip())


@dataclass
class Reponse(Etat):
    """Réponse courte validée, avec l'envoi possible de la réponse complète par SMS."""

    contenu: ContenuSortie

    def ecran(self, ctx: Contexte) -> str:
        if ctx.actif:  # compté une fois, à l'arrivée sur la réponse
            mobile.journaliser_lecture(ctx.session, ctx.usager, self.contenu)
        return assembler([self.contenu.reponse_courte or "", f"1 {ctx.t['detail_sms']}"],
                         ctx.t["retour"])

    def choisir(self, ctx: Contexte, saisie: str) -> Suite:
        if saisie != "1":
            return None
        if not ctx.actif:
            return Ecran("", fin=True)
        resultat = sms.envoyer(ctx.session, ctx.reglages, ctx.usager.telephone,
                               mobile.texte_detail(self.contenu, ctx.reglages))
        cle = {"envoye": "sms_envoye", "plafond": "sms_plafond"}.get(resultat, "sms_echec")
        return fin(ctx, ctx.t[cle])


def fin(ctx: Contexte, texte: str) -> Ecran:
    return Ecran(assembler([texte]), fin=True)


# --- Écrans ----------------------------------------------------------------------------------

def menu_langue(ctx: Contexte) -> Menu:
    def choisir(code: str) -> Action:
        def action(c: Contexte) -> Suite:
            if c.actif:  # rejouée, la saisie change seulement la langue des écrans
                mobile.enregistrer_langue(c.session, c.usager.empreinte, code, c.reference)
            c.usager.langue = code
            return menu_principal(c)
        return action

    langues = mobile.langues_proposees(ctx.session, ctx.reglages)
    return Menu(ctx.t["choix_langue"], [(nom, choisir(code)) for _, code, nom in langues],
                racine=True)


def menu_principal(ctx: Contexte) -> Menu:
    t = ctx.t
    return Menu(t["accueil"], [
        (t["menu_faq"], questions),
        (t["menu_passage"], lambda c: choix_lieu(c, passage)),
        (t["menu_badge"], saisie_badge),
        (t["menu_non_visite"], lambda c: choix_lieu(c, saisie_localite)),
        (t["menu_conseiller"], conseiller),
        (t["menu_langue"], menu_langue),
    ], racine=True)


def questions(ctx: Contexte) -> Suite:
    contenus = mobile.contenus_courts(ctx.session, ctx.corpus, ctx.usager.langue, ctx.reglages)
    if not contenus:
        return Erreur(ctx.t["aucune_question"])
    return Menu(ctx.t["menu_faq"], [(c.question, lambda _c, c_=c: Reponse(c_)) for c in contenus])


def choix_lieu(ctx: Contexte, suite: Callable[[Contexte, Territoire], Suite]) -> Menu:
    """Province, puis territoire ; `suite` reçoit le territoire choisi."""
    def territoires(code: str) -> Action:
        return lambda c: Menu(c.t["choisir_territoire"], [
            (t.nom, lambda c2, t_=t: suite(c2, t_))
            for t in mobile.territoires(c.session, code)])

    return Menu(ctx.t["choisir_province"],
                [(p.nom, territoires(p.code)) for p in mobile.provinces(ctx.session)])


def passage(ctx: Contexte, territoire: Territoire) -> Suite:
    if not ctx.actif:
        return Ecran("", fin=True)
    return fin(ctx, mobile.consulter_passage(ctx.session, ctx.usager, territoire))


def saisie_badge(ctx: Contexte) -> Saisie:
    def traiter(c: Contexte, numero: str) -> Suite:
        try:
            if c.actif:
                v = mobile.verifier_badge(c.session, c.usager, numero, c.reglages)
            else:  # saisie rejouée : ni compteur, ni journal
                v = badges.verifier(c.session, numero, c.reglages.pepper_telephone)
        except ValueError:
            return Erreur(c.t["badge_format"])
        except mobile.TropDeVerifications:
            return fin(c, c.t["trop_de_verifications"])
        texte = mobile.texte_badge(c.usager, v)
        if v.statut != "inconnu":
            return fin(c, texte)
        return Menu(texte, [(c.t["signaler_agent"], lambda c2: choix_lieu(
            c2, lambda c3, t: Confirmation("agent_douteux", t, badge=v.numero)))])

    return Saisie(ctx.t["saisir_badge"], traiter)


def saisie_localite(ctx: Contexte, territoire: Territoire) -> Saisie:
    def traiter(c: Contexte, texte: str) -> Suite:
        localite = None if texte == "1" else texte[:60]
        return Confirmation("menage_non_visite", territoire, localite=localite)

    return Saisie(ctx.t["saisir_localite"], traiter)


@dataclass
class Confirmation(Etat):
    type_: str
    territoire: Territoire
    localite: str | None = None
    badge: str | None = None

    def ecran(self, ctx: Contexte) -> str:
        lieu = ", ".join(filter(None, (self.territoire.nom, self.localite)))
        cle = "confirmer_agent" if self.type_ == "agent_douteux" else "confirmer_non_visite"
        return assembler([ctx.t[cle].format(lieu=lieu), f"1 {ctx.t['confirmer']}"],
                         ctx.t["retour"])

    def choisir(self, ctx: Contexte, saisie: str) -> Suite:
        if saisie != "1":
            return None
        if not ctx.actif:
            return Ecran("", fin=True)
        s = mobile.signaler(ctx.session, ctx.usager, self.type_, self.territoire.code,
                            localite=self.localite, badge=self.badge)
        return fin(ctx, ctx.t["signalement_enregistre"].format(id=s.id))


def conseiller(ctx: Contexte) -> Menu:
    t = ctx.t
    titre = (t["conseiller_numero"].format(numero=ctx.reglages.numero_vert)
             if ctx.reglages.numero_vert else t["conseiller_sans_numero"])

    def rappel(c: Contexte) -> Suite:
        if not c.actif:
            return Ecran("", fin=True)
        cree = mobile.demander_rappel(c.session, c.usager, f"ussd-{c.reference}")
        return fin(c, c.t["rappel_enregistre" if cree else "rappel_deja"])

    return Menu(titre, [(t["etre_rappele"], rappel)])


# --- Parcours ----------------------------------------------------------------------------------

def accueil(ctx: Contexte, langue_connue: bool) -> Etat:
    return menu_principal(ctx) if langue_connue else menu_langue(ctx)


def parcourir(ctx: Contexte, saisies: list[str], langue_connue: bool) -> Ecran:
    pile: list[Etat] = [accueil(ctx, langue_connue)]
    message = None
    for i, saisie in enumerate(saisies):
        ctx.actif = i == len(saisies) - 1
        etat, message = pile[-1], None
        if saisie == RETOUR and len(pile) > 1:
            pile.pop()
            continue
        if saisie == SUITE and isinstance(etat, Menu) and etat.a_suite(ctx):
            pile[-1] = Menu(etat.titre, etat.options, etat.racine, etat.page + 1)
            continue
        suite = etat.choisir(ctx, saisie)
        if isinstance(suite, Ecran):
            return suite
        if suite is None or isinstance(suite, Erreur):
            message = suite.message if suite else ctx.t["choix_invalide"]
            continue
        if suite.racine:
            pile.clear()
        pile.append(suite)
    # Effets de l'affichage (réponse lue) seulement si la dernière saisie y a conduit.
    ctx.actif = bool(saisies) and message is None and saisies[-1] not in (RETOUR, SUITE)
    ecran = pile[-1].ecran(ctx)
    if message:
        avec_message = assembler([message, ecran])
        # Plutôt que couper l'écran, on renonce au message.
        ecran = avec_message if len(avec_message) <= LONGUEUR_ECRAN else ecran
    return Ecran(ecran)
