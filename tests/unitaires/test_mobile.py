"""USSD et SMS sans base : alphabet GSM, mots-clés, badges, textes, découpage des menus."""

import json
import re
from types import SimpleNamespace

import pytest

from coeur.badges.service import empreinte_badge, normaliser_badge
from coeur.mobile.gsm import couper, en_gsm, longueur_gsm, nb_segments
from coeur.mobile.textes import DOSSIER, textes
from coeur.sms.analyse import analyser, normaliser, trouver_territoire
from coeur.ussd.moteur import LONGUEUR_ECRAN, Menu, assembler
from tests.conftest import PEPPER

LANGUES = sorted(p.stem for p in DOSSIER.glob("*.json"))
FRANCAIS = json.loads((DOSSIER / "fr.json").read_text(encoding="utf-8"))


# --- Alphabet GSM ----------------------------------------------------------------------------

def test_en_gsm_garde_les_accents_de_l_alphabet_et_remplace_les_autres():
    assert en_gsm("Vérifiez à côté : « être » prêt…") == 'Vérifiez à coté : " etre " pret...'
    assert en_gsm("Ménage où élève") == "Ménage où élève"


def test_nb_segments():
    assert nb_segments("a" * 160) == 1
    assert nb_segments("a" * 161) == 2
    assert nb_segments("a" * 306) == 2
    assert nb_segments("a" * 307) == 3
    assert longueur_gsm("[]") == 4  # caractères de l'extension : comptent double


def test_couper():
    assert couper("court", 10) == "court"
    assert couper("une question bien trop longue", 12) == "une quest..."


# --- Badges ------------------------------------------------------------------------------------

def test_normaliser_badge():
    assert normaliser_badge(" rgph-0012 34 ") == "RGPH001234"
    for invalide in ("", "ab", "AB*12", "x" * 21, "AB_12"):
        with pytest.raises(ValueError):
            normaliser_badge(invalide)


def test_empreinte_badge_independante_de_la_presentation():
    assert empreinte_badge("ab-12 34", PEPPER) == empreinte_badge("AB1234", PEPPER)
    assert empreinte_badge("AB1234", PEPPER) != empreinte_badge("AB1235", PEPPER)
    assert "AB1234" not in empreinte_badge("AB1234", PEPPER)


# --- Mots-clés SMS ----------------------------------------------------------------------------

@pytest.mark.parametrize("texte, nom, mots", [
    ("AGENT AB1234", "agent", ["AB1234"]),
    ("agent ab1234", "agent", ["ab1234"]),
    ("Passage Goma", "passage", ["Goma"]),
    ("NON VISITE Goma Himbi", "non_visite", ["Goma", "Himbi"]),
    ("non-visite Goma", "non_visite", ["Goma"]),
    ("Faux-agent Goma XY99", "faux_agent", ["Goma", "XY99"]),
    ("Rappel", "rappel", []),
    ("langue ln", "langue", ["ln"]),
    ("", "aide", []),
    ("Quand passent les agents ?", None, ["Quand", "passent", "les", "agents", "?"]),
])
def test_analyser(texte, nom, mots):
    commande = analyser(texte)
    assert (commande.nom, commande.mots) == (nom, mots)


REFERENTIEL = [("KIN-V", "Ville de Kinshasa"), ("KCE-MBZ", "Mbanza-Ngungu"),
               ("NKV-GOM", "Goma"), ("KAS-TSH", "Tshikapa"), ("KAS-TST", "Tshikapa")]


@pytest.mark.parametrize("mots, codes, reste", [
    (["goma", "Himbi", "2"], ["NKV-GOM"], ["Himbi", "2"]),
    (["KINSHASA"], ["KIN-V"], []),
    (["ville", "de", "kinshasa", "Limete"], ["KIN-V"], ["Limete"]),
    (["mbanza", "ngungu"], ["KCE-MBZ"], []),
    (["Mbanza-Ngungu"], ["KCE-MBZ"], []),
    (["nkv-gom"], ["NKV-GOM"], []),
    (["Tshikapa"], ["KAS-TSH", "KAS-TST"], []),
    (["Lisala"], [], ["Lisala"]),
])
def test_trouver_territoire(mots, codes, reste):
    assert trouver_territoire(REFERENTIEL, mots) == (codes, reste)


def test_normaliser():
    assert normaliser("  Équateur-Nord l'île ") == "EQUATEUR NORD L ILE"


# --- Textes ---------------------------------------------------------------------------------

@pytest.mark.parametrize("langue", LANGUES)
def test_textes_memes_cles_et_memes_marqueurs_que_le_francais(langue):
    fichier = json.loads((DOSSIER / f"{langue}.json").read_text(encoding="utf-8"))
    assert set(fichier) <= set(FRANCAIS), f"clés inconnues : {set(fichier) - set(FRANCAIS)}"
    for cle, valeur in fichier.items():
        assert set(re.findall(r"\{\w+\}", valeur)) == set(re.findall(r"\{\w+\}", FRANCAIS[cle])), cle


LONGUES = {"numero": "ABCDEFGHIJ0123456789", "territoire": "Ville de Kinshasa",
           "lieu": "Mbanza-Ngungu, " + "q" * 60, "dates": "du 10/05/2027 au 20/06/2027",
           "debut": "10/05/2027", "fin": "20/06/2027", "id": "1234567",
           "mot": "NONVISITE", "codes": "fr, ln, sw, kg, lua", "langue": "Kiswahili",
           "maximum": "3", "question": "Mes réponses au recensement sont-elles confidentielles ?"}


@pytest.mark.parametrize("langue", LANGUES)
def test_chaque_message_tient_dans_un_sms(langue):
    """160 caractères : un SMS facturé, et assez court pour un écran USSD avec son menu."""
    trop_longs = {cle: n for cle, valeur in textes(langue).items()
                  if (n := longueur_gsm(en_gsm(valeur.format(**LONGUES)))) > 160}
    assert not trop_longs


def contexte(langue: str):
    return SimpleNamespace(t=textes(langue))


@pytest.mark.parametrize("langue", LANGUES)
def test_menu_decoupe_en_ecrans_de_182_caracteres(langue):
    ctx = contexte(langue)
    options = [(f"Territoire numéro {i} au nom assez long", lambda c: None) for i in range(1, 30)]
    menu = Menu(ctx.t["choisir_territoire"], options)
    pages = menu._decouper(ctx)
    assert len(pages) > 2
    assert [i for page in pages for i in page] == list(range(29))  # rien de perdu
    for n in range(len(pages)):
        ecran = Menu(menu.titre, options, page=n).ecran(ctx)
        assert len(ecran) <= LONGUEUR_ECRAN
        assert ecran.endswith(f"0 {ctx.t['retour']}")  # « Retour » jamais sacrifié dans une liste
        assert ("98 " in ecran) == (n < len(pages) - 1)


def test_assembler_renonce_au_retour_plutot_que_depasser():
    assert assembler(["x" * 175], "Retour") == "x" * 175
    assert assembler(["court"], "Retour") == "court\n0 Retour"


@pytest.mark.parametrize("langue", LANGUES)
def test_menu_principal_sur_un_seul_ecran(langue):
    ctx = contexte(langue)
    cles = ("menu_faq", "menu_passage", "menu_badge", "menu_non_visite", "menu_conseiller",
            "menu_langue")
    menu = Menu(ctx.t["accueil"], [(ctx.t[c], lambda c: None) for c in cles], racine=True)
    assert len(menu._decouper(ctx)) == 1
    assert len(menu.ecran(ctx)) <= LONGUEUR_ECRAN


# --- Passerelle Kannel ---------------------------------------------------------------------

def test_passerelle_kannel():
    import httpx

    from coeur.sms.passerelle import PasserelleKannel

    requetes = []

    def repondre(requete):
        requetes.append(requete)
        return httpx.Response(202, text="0: Accepted for delivery")

    p = PasserelleKannel("http://sms:13013/cgi-bin/sendsms", "rgph", "secret", "RGPH2")
    p.http = httpx.Client(transport=httpx.MockTransport(repondre))
    assert p.envoyer("243812345678", "Badge valide")
    params = dict(requetes[0].url.params)
    assert params == {"username": "rgph", "password": "secret", "to": "+243812345678",
                      "from": "RGPH2", "text": "Badge valide", "charset": "UTF-8"}

    p.http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    assert not p.envoyer("243812345678", "x")

    def injoignable(requete):
        raise httpx.ConnectError("refusé")

    p.http = httpx.Client(transport=httpx.MockTransport(injoignable))
    assert not p.envoyer("243812345678", "x")


def test_journal_d_acces_sans_parametres():
    import logging

    from coeur.journalisation import SansParametres

    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                               ("10.0.0.1:5", "GET", "/v1/sms/entrant?cle=k&de=243810000001&texte=AIDE",
                                "1.1", 200), None)
    SansParametres().filter(record)
    assert record.getMessage() == '10.0.0.1:5 - "GET /v1/sms/entrant HTTP/1.1" 200'
