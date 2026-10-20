"""Scripts du conteneur Asterisk : rendu de la configuration et génération du menu vocal."""

import sys
from pathlib import Path

import pytest

DOSSIER = Path(__file__).resolve().parents[2] / "asterisk"
sys.path.insert(0, str(DOSSIER / "synchro"))

import configurer  # noqa: E402
import messages  # noqa: E402
from synchroniser_svi import generer_dialplan  # noqa: E402

from coeur.centre_appels.postes import mot_de_passe_poste  # noqa: E402
from coeur.config import Parametres  # noqa: E402

LANGUES = [{"code": "fr", "touche": 1}, {"code": "ln", "touche": 2}]


@pytest.fixture
def environnement(monkeypatch):
    monkeypatch.setenv("SECRET_POSTES", "s" * 40)
    monkeypatch.setenv("CLE_API_CENTRE_ECOUTE", "cle-centre")
    monkeypatch.setenv("NB_POSTES", "3")
    monkeypatch.setenv("SIMULATEUR_MDP", "mdp-simu")
    monkeypatch.setenv("OPERATEUR_SIP_HOTE", "")


def test_mot_de_passe_identique_au_coeur():
    assert configurer.mot_de_passe_poste("s" * 40, "poste2") == mot_de_passe_poste("s" * 40, "poste2")


def test_touches_des_langues_lues_comme_dans_le_coeur():
    texte = "fr:1, ln:2,sw:3"
    attendu = Parametres.model_construct(svi_touches_langues=texte).touches_langues()
    assert messages.touches_langues(texte) == attendu == {"fr": 1, "ln": 2, "sw": 3}


def test_marqueur_oublie_detecte():
    with pytest.raises(ValueError, match="Marqueur non remplacé"):
        configurer.rendre("a={{INCONNU}}", {})


@pytest.mark.parametrize("modele", sorted((DOSSIER / "config").glob("*.conf")),
                         ids=lambda p: p.name)
def test_chaque_modele_se_rend_completement(environnement, modele):
    texte = configurer.rendre(modele.read_text(encoding="utf-8"), configurer.valeurs())
    assert "{{" not in texte


def test_postes_et_file(environnement):
    v = configurer.valeurs()
    assert v["POSTES"].count("type=endpoint") == 3
    assert "webrtc=yes" in v["POSTES"]
    assert "rewrite_contact=yes" in v["POSTES"]  # indispensable pour joindre un poste WebRTC
    assert "from_domain=rgph2.local" in v["POSTES"]  # JsSIP refuse le nom du conteneur
    assert "opus" not in v["POSTES"]  # pas de transcodeur Opus libre : G.711 seulement
    assert v["MEMBRES"].splitlines()[-1] == "member => PJSIP/poste3,0,Poste 3,PJSIP/poste3"
    assert v["OPERATEUR"].startswith("; Liaison opérateur non configurée")


def test_liaison_operateur(environnement, monkeypatch):
    monkeypatch.setenv("OPERATEUR_SIP_HOTE", "sip.operateur.cd")
    monkeypatch.setenv("OPERATEUR_SIP_UTILISATEUR", "rgph")
    monkeypatch.setenv("OPERATEUR_SIP_MDP", "x")
    monkeypatch.setenv("OPERATEUR_SIP_ENREGISTREMENT", "true")
    section = configurer.section_operateur()
    assert "context=entree-operateur" in section
    assert "type=registration" in section
    assert "match=sip.operateur.cd" in section


def test_secret_obligatoire(monkeypatch):
    monkeypatch.setenv("SECRET_POSTES", "court")
    with pytest.raises(SystemExit):
        configurer.valeurs()


def test_logs_et_cdr_sans_numero_en_clair():
    logger = (DOSSIER / "config" / "logger.conf").read_text(encoding="utf-8")
    assert "queue_log=no" in logger
    assert "verbose" not in logger.split("[logfiles]")[1]
    assert "enable=no" in (DOSSIER / "config" / "cdr.conf").read_text(encoding="utf-8")


def test_messages_complets():
    assert {f"touche_{n}" for n in range(1, 9)} <= set(messages.PHRASES)
    assert "enregistré" in messages.PHRASES["accueil"]  # annonce légale de l'enregistrement
    assert messages.phrase_choix_langue("ln", 2) == "Pour le lingala, tapez 2."


# --- Dialplan du SVI -------------------------------------------------------------------

def test_dialplan_du_svi():
    texte = generer_dialplan(LANGUES, {"fr": [(1, 12), (2, 15)], "ln": [(1, 12)]})
    assert "[svi-langue]" in texte and "[svi-fr]" in texte and "[svi-ln]" in texte
    assert "/var/lib/asterisk/sounds/fr/rgph/choix_langue&/var/lib/asterisk/sounds/ln/rgph/choix_langue" in texte
    assert "exten => 2,1,Set(__LANGUE=ln)" in texte
    assert "Background(rgph/touche_1&rgph/svi/q-12&rgph/touche_2&rgph/svi/q-15)" in texte
    assert "exten => 2,1,Gosub(evenement,s,1(type=svi_ecoute&contenu_id=15))" in texte
    assert "Playback(rgph/svi/r-15)" in texte
    assert "exten => 0,1,Goto(file-attente,s,1)" in texte


def test_sans_choix_le_francais_par_defaut():
    texte = generer_dialplan(LANGUES, {"fr": [(1, 12)]})
    langue = texte.split("[svi-fr]")[0]
    assert " same => n,Goto(1,1)" in langue


def test_langue_sans_reponse_audio_va_au_conseiller():
    texte = generer_dialplan(LANGUES, {"fr": [(1, 12)], "ln": []})
    ln = texte.split("[svi-ln]")[1]
    assert "Playback(rgph/aucune_reponse_langue)" in ln
    assert "Goto(file-attente,s,1)" in ln


def test_aucune_langue():
    texte = generer_dialplan([], {})
    assert "Goto(file-attente,s,1)" in texte


def test_rappels_sortants(environnement, monkeypatch):
    assert configurer.appel_sortant().startswith("Dial(PJSIP/simulateur")
    monkeypatch.setenv("OPERATEUR_SIP_HOTE", "sip.operateur.cd")
    assert configurer.appel_sortant() == "Dial(PJSIP/${EXTEN}@operateur,60)"
    monkeypatch.setenv("OPERATEUR_SIP_HOTE", "")
    monkeypatch.setenv("SIMULATEUR_MDP", "")
    assert configurer.appel_sortant().startswith("Playback(")


def test_candidats_ice(environnement, monkeypatch):
    monkeypatch.setenv("SIP_ADRESSE_EXTERNE", "")
    assert configurer.ice_hotes().startswith(";")
    monkeypatch.setenv("SIP_ADRESSE_EXTERNE", "41.243.1.2")
    texte = configurer.ice_hotes()
    assert texte.startswith("[ice_host_candidates]\n") and texte.endswith(" => 41.243.1.2")


def test_codes_de_pause_des_agents():
    texte = (DOSSIER / "config" / "extensions.conf").read_text(encoding="utf-8")
    assert "exten => *1,1,Answer()" in texte and "PauseQueueMember(rgph," in texte
    assert "UnpauseQueueMember(rgph," in texte
