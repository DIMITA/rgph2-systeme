from coeur.portail.limiteur import LimiteurDebit


def test_autorise_jusqu_a_la_limite_puis_refuse():
    limiteur = LimiteurDebit(limite=3, fenetre_secondes=60)
    assert [limiteur.autoriser("a", maintenant=0) for _ in range(4)] == [True, True, True, False]


def test_chaque_adresse_a_son_propre_compteur():
    limiteur = LimiteurDebit(limite=1, fenetre_secondes=60)
    assert limiteur.autoriser("a", maintenant=0)
    assert limiteur.autoriser("b", maintenant=0)
    assert not limiteur.autoriser("a", maintenant=1)


def test_la_fenetre_glisse():
    limiteur = LimiteurDebit(limite=2, fenetre_secondes=60)
    assert limiteur.autoriser("a", maintenant=0)
    assert limiteur.autoriser("a", maintenant=30)
    assert not limiteur.autoriser("a", maintenant=59)
    assert limiteur.autoriser("a", maintenant=61)


def test_oubli_des_adresses_inactives():
    limiteur = LimiteurDebit(limite=5, fenetre_secondes=60)
    limiteur.autoriser("a", maintenant=0)
    limiteur.autoriser("b", maintenant=100)
    assert limiteur.nb_adresses_suivies() == 1
