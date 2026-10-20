"""Réglages du cœur chiffrés en base : lecture par l'API, assistant d'initialisation."""

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from coeur.config import Parametres
from coeur.reglages import service
from coeur.reglages.__main__ import main
from coeur.reglages.source import CleMaitreInvalide
from tests.conftest import URL_ADMIN, URL_API

CLE = Fernet.generate_key().decode()


@pytest.fixture
def cle_maitre(monkeypatch):
    monkeypatch.setenv("CLE_MAITRE", CLE)
    return CLE


@pytest.fixture
def admin(monkeypatch, cle_maitre):
    """Comme l'assistant : rôle propriétaire de la base."""
    monkeypatch.setenv("DATABASE_URL", URL_ADMIN)
    with Session(create_engine(URL_ADMIN)) as session:
        yield session


def test_valeurs_chiffrees_en_base(admin):
    service.ecrire(admin, CLE, {"numero_vert": "0800 123 456", "whatsapp_jeton": "EAAG-secret-123"})
    brut = admin.execute(text("SELECT string_agg(valeur, ' ') FROM coeur.reglages")).scalar()
    assert "0800 123 456" not in brut and "EAAG" not in brut
    assert service.lire(admin, CLE) == {"numero_vert": "0800 123 456",
                                        "whatsapp_jeton": "EAAG-secret-123"}


@pytest.mark.parametrize("champ, valeur, message", [
    ("database_url", "postgresql://x", "reste dans .env"),
    ("secret_postes", "x" * 40, "reste dans .env"),
    ("nimporte_quoi", "1", "inconnu"),
    ("cle_ministere", "court", "cle_ministere"),
    ("transcription", "whisper", "transcription"),
    ("terrain_activation_jours", "sept", "terrain_activation_jours"),
])
def test_validation(champ, valeur, message):
    with pytest.raises(ValueError, match=message):
        service.valider(champ, valeur)


def test_l_api_lit_ses_reglages_en_base(admin, monkeypatch):
    service.ecrire(admin, CLE, {"numero_vert": "0800 123 456", "ussd_code": "*123#"})
    monkeypatch.setenv("DATABASE_URL", URL_API)
    monkeypatch.delenv("NUMERO_VERT", raising=False)
    reglages = Parametres()
    assert (reglages.numero_vert, reglages.ussd_code) == ("0800 123 456", "*123#")
    # Une variable d'environnement l'emporte toujours (dépannage, tests).
    monkeypatch.setenv("NUMERO_VERT", "0800 999 999")
    assert Parametres().numero_vert == "0800 999 999"


def test_mauvaise_cle_maitre_refusee(admin, monkeypatch):
    service.ecrire(admin, CLE, {"numero_vert": "0800 123 456"})
    monkeypatch.setenv("CLE_MAITRE", Fernet.generate_key().decode())
    with pytest.raises(CleMaitreInvalide, match="mauvaise clé"):
        Parametres()


def test_l_api_ne_peut_pas_modifier_ses_reglages(admin):
    with create_engine(URL_API).connect() as connexion, pytest.raises(ProgrammingError):
        connexion.execute(text("INSERT INTO coeur.reglages VALUES ('numero_vert', 'x', now())"))


def test_assistant_genere_les_secrets_une_seule_fois(admin, capsys):
    assert main(["initialiser", "--non-interactif"]) in (0, 1)
    premiers = service.lire(admin, CLE)
    assert len(premiers["pepper_telephone"]) >= 32
    Fernet(premiers["cle_chiffrement"].encode())  # clé Fernet valide
    assert premiers["whatsapp_passerelle"] == "simulation"
    assert premiers["transcription"] == "aucune"
    main(["initialiser", "--non-interactif"])
    # Le pepper ne doit jamais changer : les usagers ne seraient plus reconnus.
    assert service.lire(admin, CLE)["pepper_telephone"] == premiers["pepper_telephone"]


def test_assistant_interactif(admin, monkeypatch, capsys):
    reponses = iter(["0800 000 111", "*144#", "faux", "meta", "1234567890", "aucune", "escalades"])
    secrets_saisis = iter(["EAAG-jeton-permanent", "secret-app-meta"])
    monkeypatch.setattr("builtins.input", lambda invite="": next(reponses))
    monkeypatch.setattr("getpass.getpass", lambda invite="": next(secrets_saisis))
    main(["initialiser"])
    sortie = capsys.readouterr().out
    assert "Répondre par : simulation, meta" in sortie  # « faux » refusé, question reposée
    valeurs = service.lire(admin, CLE)
    assert valeurs["numero_vert"] == "0800 000 111"
    assert valeurs["whatsapp_passerelle"] == "meta"
    assert valeurs["whatsapp_jeton"] == "EAAG-jeton-permanent"
    assert valeurs["conservation_texte_questions"] == "escalades"
    assert "transcription_langues" not in valeurs  # pas demandé sans transcription
    assert "EAAG-jeton-permanent" not in sortie

    # Seconde fois : Entrée garde la valeur actuelle.
    monkeypatch.setattr("builtins.input", lambda invite="": "")
    monkeypatch.setattr("getpass.getpass", lambda invite="": "")
    main(["initialiser"])
    assert service.lire(admin, CLE)["whatsapp_jeton"] == "EAAG-jeton-permanent"


def test_lister_masque_les_secrets(admin, capsys):
    service.ecrire(admin, CLE, {"whatsapp_jeton": "EAAG-jeton-tres-secret", "numero_vert": "0800"})
    main(["lister"])
    sortie = capsys.readouterr().out
    assert "EAAG-jeton-tres-secret" not in sortie and "0800" in sortie


def test_definir_refuse_une_valeur_invalide(admin, capsys):
    assert main(["definir", "cle_ministere", "court"]) == 1
    assert main(["definir", "numero_vert", "0800 222 333"]) == 0
    assert service.lire(admin, CLE)["numero_vert"] == "0800 222 333"


def test_importer_l_ancien_env(admin, monkeypatch, capsys):
    monkeypatch.setenv("WHATSAPP_JETON", "EAAG-ancien")
    main(["importer-env"])
    valeurs = service.lire(admin, CLE)
    assert valeurs["whatsapp_jeton"] == "EAAG-ancien"
    assert "database_url" not in valeurs and "secret_postes" not in valeurs


def test_changer_la_cle_maitre(admin, monkeypatch):
    service.ecrire(admin, CLE, {"numero_vert": "0800 123 456"})
    nouvelle = Fernet.generate_key().decode()
    monkeypatch.setenv("CLE_MAITRE_NOUVELLE", nouvelle)
    assert main(["changer-cle-maitre"]) == 0
    assert service.lire(admin, nouvelle) == {"numero_vert": "0800 123 456"}


def test_importer_un_fichier_sur_l_entree_standard(admin, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("PEPPER_TELEPHONE=" + "p" * 40 + "\n"
                                                 "SECRET_POSTES=" + "s" * 40 + "\n"))
    main(["importer-env", "-"])
    assert service.lire(admin, CLE) == {"pepper_telephone": "p" * 40}


def test_afficher_un_reglage_en_clair(admin, capsys):
    service.ecrire(admin, CLE, {"whatsapp_jeton_verification": "jeton-a-recopier-chez-meta"})
    assert main(["afficher", "whatsapp_jeton_verification"]) == 0
    assert capsys.readouterr().out.strip() == "jeton-a-recopier-chez-meta"
    assert main(["afficher", "numero_vert"]) == 1
