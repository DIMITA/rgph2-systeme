import base64
import importlib.util
from pathlib import Path

CHEMIN = Path(__file__).resolve().parents[2] / "outils" / "preparer_env.py"
_spec = importlib.util.spec_from_file_location("preparer_env", CHEMIN)
preparer_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(preparer_env)

MODELE = Path(__file__).resolve().parents[2] / ".env.exemple"


def test_premier_env(tmp_path):
    cible = tmp_path / ".env"
    preparer_env.preparer(MODELE, cible, tmp_path / ".a", interactif=False)
    valeurs = preparer_env.lire_env(cible)
    assert not any(v.startswith("@") for v in valeurs.values())
    assert len(base64.urlsafe_b64decode(valeurs["CLE_MAITRE"])) == 32
    assert len(valeurs["POSTGRES_MDP_ADMIN"]) >= 40
    assert valeurs["POSTGRES_MDP_ADMIN"] != valeurs["RGPH_API_MDP"]
    assert [c.split(":")[0] for c in valeurs["CLES_API"].split(",")] == list(preparer_env.CANAUX)
    assert valeurs["DIRECTUS_ADMIN_EMAIL"] == "admin@exemple.cd"
    assert valeurs["OPERATEUR_SIP_HOTE"] == ""
    assert cible.stat().st_mode & 0o777 == 0o600
    assert "# Mots de passe PostgreSQL (un par rôle)" in cible.read_text(encoding="utf-8")


def test_relance_sans_rien_perdre_et_ancien_env_mis_de_cote(tmp_path):
    cible = tmp_path / ".env"
    cible.write_text("CLE_MAITRE=ma-cle\nOPERATEUR_SIP_HOTE=sip.operateur.cd\n"
                     "PEPPER_TELEPHONE=ancien-pepper\n", encoding="utf-8")
    restes = preparer_env.preparer(MODELE, cible, tmp_path / ".a", interactif=False)
    valeurs = preparer_env.lire_env(cible)
    assert valeurs["CLE_MAITRE"] == "ma-cle"
    assert valeurs["OPERATEUR_SIP_HOTE"] == "sip.operateur.cd"
    assert "PEPPER_TELEPHONE" not in valeurs and restes == ["PEPPER_TELEPHONE"]
    assert (tmp_path / ".a").read_text(encoding="utf-8") == "PEPPER_TELEPHONE=ancien-pepper\n"


def test_questions(tmp_path, monkeypatch):
    reponses = iter(["sip.operateur.cd", "rgph", "", "", "smpp.operateur.cd", "", "x@ins.cd", ""])
    monkeypatch.setattr("builtins.input", lambda invite="": next(reponses))
    monkeypatch.setattr("getpass.getpass", lambda invite="": "mot-de-passe-operateur")
    preparer_env.preparer(MODELE, tmp_path / ".env", tmp_path / ".a", interactif=True)
    valeurs = preparer_env.lire_env(tmp_path / ".env")
    assert valeurs["OPERATEUR_SIP_HOTE"] == "sip.operateur.cd"
    assert valeurs["OPERATEUR_SIP_MDP"] == "mot-de-passe-operateur"
    assert valeurs["ASTERISK_WS_URL"] == "ws://localhost:8088/ws"  # Entrée : défaut proposé
    assert valeurs["DIRECTUS_ADMIN_EMAIL"] == "x@ins.cd"
