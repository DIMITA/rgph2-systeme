"""Masquage complémentaire : aucune case masquée ne se retrouve par différence."""

from coeur.statistiques.service import groupes_de_cases, masquage_complementaire

SEUIL = 5


def test_une_case_masquee_seule_entraine_un_second_masque():
    # Total publié 27 : sans second masque, 27 - 20 - 5 = 2.
    valeurs = [20, 5, 2]
    assert masquage_complementaire(valeurs, {2}, [[0, 1, 2]], SEUIL) == {1, 2}


def test_deux_petites_cases_dont_la_somme_est_sous_le_seuil():
    # 1 + 1 = 2 : connaissant la somme (2) et le minimum (1), chacune vaut 1.
    valeurs = [30, 9, 1, 1]
    assert masquage_complementaire(valeurs, {2, 3}, [[0, 1, 2, 3]], SEUIL) == {1, 2, 3}


def test_rien_a_faire_quand_le_groupe_est_protege():
    valeurs = [30, 3, 4]
    assert masquage_complementaire(valeurs, {1, 2}, [[0, 1, 2]], SEUIL) == {1, 2}


def test_les_cases_nulles_ne_protegent_rien():
    valeurs = [30, 0, 2]
    assert masquage_complementaire(valeurs, {2}, [[0, 1, 2]], SEUIL) == {0, 2}


def test_propagation_d_un_groupe_a_l_autre():
    # Tableau 2 × 2 : lignes et colonnes publiées.
    #         c1  c2
    #   l1     2  10
    #   l2    10  10
    cles = [("l1", "c1"), ("l1", "c2"), ("l2", "c1"), ("l2", "c2")]
    valeurs = [2, 10, 10, 10]
    masques = masquage_complementaire(valeurs, {0}, groupes_de_cases(cles), SEUIL)
    # Ligne l1 et colonne c1 doivent chacune avoir deux cases masquées.
    for groupe in ([0, 1], [0, 2], [2, 3], [1, 3]):
        caches = [i for i in groupe if i in masques]
        assert not caches or len(caches) >= 2


def test_groupes_par_province():
    cles = [("KCE-MAT",), ("KCE-MBZ",), ("NKV-GOM",)]
    parents = {"KCE-MAT": "KCE", "KCE-MBZ": "KCE", "NKV-GOM": "NKV"}
    groupes = groupes_de_cases(cles, parents)
    assert [0, 1, 2] in groupes and [0, 1] in groupes
