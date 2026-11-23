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
