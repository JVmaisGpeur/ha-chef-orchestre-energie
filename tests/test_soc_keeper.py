"""E2 : réserve de SOC min et SOC max à 100 %, sans jamais perdre le réglage de l'utilisateur."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import _load

K = _load("soc_keeper")
TZ = ZoneInfo("Europe/Paris")
T0 = datetime(2026, 11, 23, 20, 0, tzinfo=TZ)


def tgt(eid, kind, cur):
    return K.Target(eid, kind, cur, *((0, 50) if kind == "min" else (70, 100)))


def test_reserve_puis_retour():
    k = K.SocKeeper()
    assert k.writes([tgt("n.min1", "min", 10)], T0, reserve=50, full_charge=False) == [("n.min1", 50)]
    assert k.active
    # le plan redevient rentable : on rend 10 %, même moins de 30 min après
    assert k.writes([tgt("n.min1", "min", 50)], T0 + timedelta(minutes=5), reserve=None, full_charge=False) == [("n.min1", 10)]
    assert not k.active


def test_pas_d_ecriture_inutile():
    k = K.SocKeeper()
    assert k.writes([tgt("n.min1", "min", 45)], T0, reserve=40, full_charge=False) == []  # déjà au-dessus
    k.writes([tgt("n.min2", "min", 10)], T0, reserve=50, full_charge=False)
    assert k.writes([tgt("n.min2", "min", 50)], T0 + timedelta(minutes=15), reserve=50, full_charge=False) == []


def test_limite_de_frequence():
    k = K.SocKeeper()
    k.writes([tgt("n.max", "max", 90)], T0, reserve=None, full_charge=True)
    # on rend 90 % tout de suite, puis on voudrait remonter à 100 % : il faut attendre
    assert k.writes([tgt("n.max", "max", 100)], T0 + timedelta(minutes=10), reserve=None, full_charge=False) == [("n.max", 90)]
    assert k.writes([tgt("n.max", "max", 90)], T0 + timedelta(minutes=20), reserve=None, full_charge=True) == []
    assert k.writes([tgt("n.max", "max", 90)], T0 + timedelta(minutes=45), reserve=None, full_charge=True) == [("n.max", 100)]


def test_changement_par_l_utilisateur():
    k = K.SocKeeper()
    k.writes([tgt("n.min", "min", 10)], T0, reserve=50, full_charge=False)
    # l'utilisateur met 20 % pendant la réserve : mémorisé, pas réécrasé avant le calcul suivant
    assert k.writes([tgt("n.min", "min", 20)], T0 + timedelta(hours=1), reserve=50, full_charge=False) == []
    assert k.memo["n.min"] == 20
    k.new_plan()
    assert k.writes([tgt("n.min", "min", 20)], T0 + timedelta(hours=2), reserve=50, full_charge=False) == [("n.min", 50)]
    assert k.restore_all() == [("n.min", 20)]


def test_restitution_et_memoire_persistante():
    k = K.SocKeeper()
    k.writes([tgt("a.min", "min", 15), tgt("a.max", "max", 90)], T0, reserve=50, full_charge=True)
    k2 = K.SocKeeper(k.dump())  # redémarrage de Home Assistant
    assert sorted(k2.restore_all()) == [("a.max", 90), ("a.min", 15)]


def test_bornes_de_l_entite():
    k = K.SocKeeper()
    assert k.writes([tgt("n.min", "min", 10)], T0, reserve=70, full_charge=False) == [("n.min", 50)]


# ---------------------------------------------------------------- R1 (v1.3.5)
def tgt_soc(eid, cur, soc):
    return K.Target(eid, "min", cur, 0, 50, soc)


def test_r1_batterie_deja_sous_la_reserve_garde_son_niveau():
    k = K.SocKeeper()
    # 12,4 % au début des heures creuses : la réserve s'arrête à 12 %, pas de charge réseau
    assert k.writes([tgt_soc("n.min", 5, 12.4)], T0, reserve=50, full_charge=False) == [("n.min", 12)]
    # Batterie déjà au SOC min de l'utilisateur : rien à écrire
    k2 = K.SocKeeper()
    assert k2.writes([tgt_soc("n.min", 5, 4.0)], T0, reserve=50, full_charge=False) == []


def test_r1_une_pose_et_une_levee_par_nuit():
    """Contrôle toutes les minutes de 21:00 à 07:00, réserve de 22:00 à 06:00 : deux écritures."""
    k = K.SocKeeper()
    start = datetime(2026, 11, 26, 21, 0, tzinfo=TZ)
    pose, levee = datetime(2026, 11, 26, 22, 0, tzinfo=TZ), datetime(2026, 11, 27, 6, 0, tzinfo=TZ)
    current, soc, writes = 5.0, 60.0, []
    for minute in range(10 * 60):
        now = start + timedelta(minutes=minute)
        reserve = 50 if pose <= now < levee else None
        soc = max(45.0, soc - 0.05)  # la batterie bouge un peu pendant la nuit
        out = k.writes([tgt_soc("n.min", current, soc)], now, reserve=reserve, full_charge=False)
        for _eid, value in out:
            current = value
            writes.append((now, value))
    assert writes == [(pose, 50), (levee, 5.0)]


# ---------------------------------------------------------------- R2 (v1.3.6)
NUIT = datetime(2026, 11, 26, 22, 0, tzinfo=TZ)


def poser_reserve(k, eid="n.min"):
    """Réglage de l'utilisateur 5 %, réserve de 50 % posée à 22:00."""
    k.reserve_setting = 50
    assert k.writes([tgt(eid, "min", 5)], NUIT, reserve=50, full_charge=False) == [(eid, 50)]


def test_r2_rechargement_pendant_la_reserve_zendure_lent():
    k = K.SocKeeper()
    poser_reserve(k)
    # Rechargement de l'intégration à 23:00 : la valeur de l'utilisateur est renvoyée…
    t = NUIT + timedelta(hours=1)
    assert k.restore_all(t) == [("n.min", 5)]
    k2 = K.SocKeeper(k.dump())
    k2.reserve_setting = 50
    # … mais Zendure affiche encore 50 % plusieurs minutes : jamais pris pour le réglage
    for minute in range(1, 20):
        assert k2.user_value(tgt("n.min", "min", 50)) == 5
        assert k2.pending_writes([tgt("n.min", "min", 50)], t + timedelta(minutes=minute)) == []
    # toujours 50 % au bout de 30 min : renvoyé une fois (limite des écritures)
    assert k2.pending_writes([tgt("n.min", "min", 50)], t + timedelta(minutes=31)) == [("n.min", 5)]
    # la batterie confirme : restitution terminée, réglage 5 %
    assert k2.user_value(tgt("n.min", "min", 5)) == 5
    assert not k2.pending and not k2.applied


def test_r2_redemarrage_pendant_la_reserve_puis_sortie_des_heures_creuses():
    k = K.SocKeeper()
    poser_reserve(k)
    k2 = K.SocKeeper(k.dump())  # redémarrage de Home Assistant à 02:00, réserve toujours affichée
    k2.reserve_setting = 50
    k2.new_plan()
    assert k2.user_value(tgt("n.min", "min", 50)) == 5
    assert k2.writes([tgt("n.min", "min", 50)], NUIT + timedelta(hours=4), reserve=50, full_charge=False) == []
    # 06:00 : la réserve est levée, retour à 5 %
    fin = NUIT + timedelta(hours=8)
    assert k2.writes([tgt("n.min", "min", 50)], fin, reserve=None, full_charge=False) == [("n.min", 5)]
    # Zendure lent : rien de plus avant 30 min, et le réglage reste 5 %
    assert k2.writes([tgt("n.min", "min", 50)], fin + timedelta(minutes=5), reserve=None, full_charge=False) == []
    assert k2.memo["n.min"] == 5
    assert k2.writes([tgt("n.min", "min", 5)], fin + timedelta(minutes=6), reserve=None, full_charge=False) == []
    assert not k2.pending and not k2.applied


def test_r2_reglage_de_l_utilisateur_pendant_la_reserve_rendu_a_la_fin():
    k = K.SocKeeper()
    poser_reserve(k)
    k.writes([tgt("n.min", "min", 20)], NUIT + timedelta(hours=1), reserve=50, full_charge=False)
    assert k.memo["n.min"] == 20
    k.new_plan()
    k.writes([tgt("n.min", "min", 20)], NUIT + timedelta(hours=2), reserve=50, full_charge=False)  # réserve reposée
    assert k.writes([tgt("n.min", "min", 50)], NUIT + timedelta(hours=8), reserve=None, full_charge=False) == [("n.min", 20)]
    assert k.memo["n.min"] == 20


def test_r2_migration_d_une_memoire_faussee():
    # État laissé par la v1.3.5 : réglage mémorisé 50 % (la réserve), rien de posé
    k = K.SocKeeper({"memo": {"a.min": 50, "b.min": 50}, "applied": {}, "last_write": {"a.min": NUIT.isoformat(), "b.min": NUIT.isoformat()}})
    k.reserve_setting = 50
    histories = {"a.min": [5, 5, 50, 50, 5, 50], "b.min": []}
    fixes = k.migrate(["a.min", "b.min"], histories, 50)
    # a : 5 % retrouvé dans l'historique ; b : pas d'historique, la valeur saine de a
    assert fixes == [("a.min", 5), ("b.min", 5)]
    assert k.memo == {"a.min": 5, "b.min": 5}
    assert k.user_value(tgt("a.min", "min", 50)) == 5  # la batterie affiche encore 50 % : on attend
    # une seule fois
    assert k.migrate(["a.min", "b.min"], histories, 50) == []
    assert K.SocKeeper(k.dump()).version == K.VERSION


def test_r2_migration_sans_ecriture_du_chef_garde_50():
    # 50 % sans que le Chef n'ait jamais écrit : c'est bien le réglage de l'utilisateur
    k = K.SocKeeper({"memo": {"a.min": 50}})
    assert k.migrate(["a.min"], {"a.min": [50]}, 50) == []
    assert k.memo["a.min"] == 50


def test_r2_migration_sans_historique_signalee():
    k = K.SocKeeper({"memo": {"a.min": 50}, "last_write": {"a.min": NUIT.isoformat()}})
    assert k.migrate(["a.min"], {}, 50) == [("a.min", None)]
    assert k.suspect == {"a.min": 50}


def test_r2_garde_fou_valeur_egale_a_la_reserve():
    k = K.SocKeeper()
    poser_reserve(k)
    # Levée confirmée : réglage 5 %, mais une réserve a été posée depuis
    k.writes([tgt("n.min", "min", 50)], NUIT + timedelta(hours=8), reserve=None, full_charge=False)
    k.user_value(tgt("n.min", "min", 5))
    assert not k.pending
    # Plus tard, 50 % reparaît sans écriture du Chef : refusé, signalé, 5 % rendu
    t = NUIT + timedelta(hours=10)
    assert k.user_value(tgt("n.min", "min", 50)) == 5
    assert k.suspect == {"n.min": 50}
    assert [e[0] for e in k.events] == ["suspect"]
    assert k.writes([tgt("n.min", "min", 50)], t, reserve=None, full_charge=False) == [("n.min", 5)]
    # Une autre valeur que la réserve reste un réglage de l'utilisateur
    k2 = K.SocKeeper()
    poser_reserve(k2)
    k2.writes([tgt("n.min", "min", 50)], NUIT + timedelta(hours=8), reserve=None, full_charge=False)
    k2.user_value(tgt("n.min", "min", 5))
    assert k2.user_value(tgt("n.min", "min", 30)) == 30


def test_r2_reparation_valeur_choisie():
    k = K.SocKeeper({"memo": {"a.min": 50}, "last_write": {"a.min": NUIT.isoformat()}})
    k.migrate(["a.min"], {}, 50)
    assert k.set_user("a.min", 5, 50) is True  # à écrire sur la batterie
    assert k.memo["a.min"] == 5 and not k.suspect
    assert k.user_value(tgt("a.min", "min", 50)) == 5  # Zendure lent
    assert k.user_value(tgt("a.min", "min", 5)) == 5
    assert not k.pending and not k.applied
