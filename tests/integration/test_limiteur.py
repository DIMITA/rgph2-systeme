from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text

from coeur.limiteur import CompteurDebit, LimiteurDebit, Marque, MemoireCourte, purger


def test_autorise_jusqu_a_la_limite_puis_refuse():
    limiteur = LimiteurDebit("test", limite=3, fenetre_secondes=60)
    assert [limiteur.autoriser("a", maintenant=0) for _ in range(4)] == [True, True, True, False]


def test_chaque_cle_et_chaque_espace_ont_leur_compteur():
    limiteur = LimiteurDebit("test", limite=1, fenetre_secondes=60)
    assert limiteur.autoriser("a", maintenant=0)
    assert limiteur.autoriser("b", maintenant=0)
    assert not limiteur.autoriser("a", maintenant=1)
    assert LimiteurDebit("autre", limite=1, fenetre_secondes=60).autoriser("a", maintenant=1)


def test_la_fenetre_glisse():
    limiteur = LimiteurDebit("test", limite=2, fenetre_secondes=60)
    assert limiteur.autoriser("a", maintenant=0)
    assert limiteur.autoriser("a", maintenant=30)
    # Fenêtre suivante, mais la précédente compte encore presque entièrement.
    assert not limiteur.autoriser("a", maintenant=61)
    # Deux fenêtres plus tard, tout est oublié.
    assert limiteur.autoriser("a", maintenant=125)


def test_le_compteur_est_partage_entre_instances():
    """Deux processus = deux instances : la limite reste la même pour la clé."""
    premier = LimiteurDebit("test", limite=2, fenetre_secondes=60)
    second = LimiteurDebit("test", limite=2, fenetre_secondes=60)
    assert premier.autoriser("a", maintenant=0)
    assert second.autoriser("a", maintenant=0)
    assert not premier.autoriser("a", maintenant=0)


def test_la_cle_n_est_jamais_enregistree_en_clair(session_admin):
    LimiteurDebit("test", limite=5, fenetre_secondes=60).autoriser("192.0.2.7")
    MemoireCourte("test", 60).nouveau("wamid.secret")
    contenu = session_admin.execute(text(
        "SELECT string_agg(cle, ' ') FROM (SELECT cle FROM coeur.compteurs_debit "
        "UNION ALL SELECT cle FROM coeur.memoire_courte) t")).scalar()
    assert "192.0.2.7" not in contenu and "wamid" not in contenu


def test_memoire_courte():
    memoire = MemoireCourte("test", 60)
    assert memoire.nouveau("m1")
    assert not memoire.nouveau("m1")
    assert MemoireCourte("autre", 60).nouveau("m1")
    assert memoire.lire("ecran") is None
    memoire.garder("ecran", {"texte": "Bonjour", "fin": False})
    assert memoire.lire("ecran") == {"texte": "Bonjour", "fin": False}


def test_memoire_expiree_oubliee():
    memoire = MemoireCourte("test", -1)
    assert memoire.nouveau("m1")
    assert memoire.nouveau("m1")
    memoire.garder("ecran", {"texte": "x"})
    assert memoire.lire("ecran") is None


def test_purge(session_admin):
    LimiteurDebit("test", limite=5, fenetre_secondes=60).autoriser("a")
    MemoireCourte("test", 60).nouveau("m1")
    dans_une_heure = datetime.now(timezone.utc) + timedelta(hours=1)
    assert purger(session_admin, datetime.now(timezone.utc)) == 0
    assert purger(session_admin, dans_une_heure) == 2
    session_admin.commit()
    for modele in (CompteurDebit, Marque):
        assert session_admin.scalar(select(func.count()).select_from(modele)) == 0


def test_compteurs_disponibles_quand_le_pool_des_requetes_est_plein():
    """Chaque requête tient sa connexion, puis demande un compteur. Dans le même pool, sous
    charge, elles s'attendaient toutes (interblocage constaté au test de charge)."""
    from coeur.base import moteur_court, moteur_sql

    assert moteur_court() is not moteur_sql()
    pool = moteur_sql().pool
    tenues = [moteur_sql().connect() for _ in range(pool.size() + pool._max_overflow)]
    try:
        assert LimiteurDebit("pool_plein", 5, 60).autoriser("cle")
        assert MemoireCourte("pool_plein", 60).nouveau("cle")
    finally:
        for connexion in tenues:
            connexion.close()
