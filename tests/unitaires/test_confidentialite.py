import pytest

from coeur.confidentialite.service import (
    empreinte_telephone,
    masquer_donnees_sensibles,
    normaliser_telephone,
)

PEPPER = "p" * 32


@pytest.mark.parametrize(
    "saisie",
    ["+243 812 345 678", "00243812345678", "0812345678", "812345678", "243-812-345-678"],
)
def test_toutes_les_ecritures_d_un_numero_donnent_le_meme_format(saisie):
    assert normaliser_telephone(saisie) == "243812345678"


@pytest.mark.parametrize("saisie", ["", "123", "abc", "+1234567890123456789"])
def test_numero_invalide_refuse(saisie):
    with pytest.raises(ValueError):
        normaliser_telephone(saisie)


def test_empreinte_stable_et_independante_de_l_ecriture():
    a = empreinte_telephone("+243 812 345 678", PEPPER)
    b = empreinte_telephone("0812345678", PEPPER)
    assert a == b
    assert len(a) == 64


def test_empreinte_ne_contient_pas_le_numero():
    assert "812345678" not in empreinte_telephone("0812345678", PEPPER)


def test_empreinte_depend_de_la_cle_secrete():
    assert empreinte_telephone("0812345678", PEPPER) != empreinte_telephone("0812345678", "q" * 32)


@pytest.mark.parametrize(
    "texte",
    [
        "appelez-moi au 0812345678",
        "mon numéro +243 812 345 678 svp",
        "carte d'électeur 12345678901",
        "écrivez à jean.kabila@exemple.cd",
    ],
)
def test_masquage_des_numeros_et_courriels(texte):
    masque = masquer_donnees_sensibles(texte)
    assert "[masqué]" in masque
    assert "812345678" not in masque
    assert "12345678901" not in masque
    assert "@" not in masque


@pytest.mark.parametrize(
    "texte",
    ["quand passent les agents en 2027 ?", "le 15/05/2027 à 10h", "j'ai 3 enfants"],
)
def test_masquage_laisse_intacts_les_textes_ordinaires(texte):
    assert masquer_donnees_sensibles(texte) == texte
