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
