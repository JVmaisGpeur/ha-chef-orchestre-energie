"""Charge complète et calibration (N3)."""

from datetime import datetime, timedelta, timezone

from conftest import fullcharge as fc

T0 = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
UNITS = ["u1", "u2"]


def make(days1=0, days2=0):
    t = fc.FullChargeTracker()
    t.start("u1", T0 - timedelta(days=days1), estimated=False)
    t.start("u2", T0 - timedelta(days=days2), estimated=False)
    return t


def test_compteur_et_remise_a_zero():
    t = make(12, 22)
    assert round(t.days("u1", T0)) == 12
    assert t.due_units(UNITS, T0, 20) == ["u2"]
    t.observe("u2", 100, T0)
    assert t.days("u2", T0) == 0
    assert t.calibration_due("u1") == T0 - timedelta(days=12) + timedelta(days=30)


def test_soleil_prefere_puis_nuit():
    t = make(5, 22)
    assert t.decide(UNITS, T0, threshold=20, auto_enabled=True, sunny=True, tonight_ok=True)[:2] == ("sun", ["u2"])
    assert t.decide(UNITS, T0, threshold=20, auto_enabled=True, sunny=False, tonight_ok=True)[0] == "tonight"
    # veille d'un jour cher : on attend, sans alerte tant qu'on n'est pas en retard
    assert t.decide(UNITS, T0, threshold=20, auto_enabled=True, sunny=False, tonight_ok=False) == (None, ["u2"], False)


def test_en_retard_charge_meme_veille_de_jour_cher():
    t = make(5, 28)
    assert t.decide(UNITS, T0, threshold=20, auto_enabled=True, sunny=False, tonight_ok=False)[0] == "tonight"


def test_rien_sous_le_seuil_ou_anticipation_coupee():
    assert make(5, 10).decide(UNITS, T0, threshold=20, auto_enabled=True, sunny=True, tonight_ok=True)[0] is None
    assert make(5, 25).decide(UNITS, T0, threshold=20, auto_enabled=False, sunny=True, tonight_ok=True)[0] is None


def test_demandes_manuelles():
    t = make(5, 10)
    t.set_request("now", UNITS, T0, {"u1": 100, "u2": 80})
    assert t.decide(UNITS, T0, threshold=20, auto_enabled=False, sunny=False, tonight_ok=False)[:2] == ("now", ["u2"])
    assert t.observe("u2", 100, T0) is True
    assert t.request == "auto"
    t.set_request("next_sun", UNITS, T0, {"u1": 60, "u2": 60})
    assert t.decide(UNITS, T0, threshold=20, auto_enabled=True, sunny=False, tonight_ok=True)[0] is None
    assert t.decide(UNITS, T0, threshold=20, auto_enabled=True, sunny=True, tonight_ok=True)[0] == "sun"


def test_ignorer_ce_cycle_jusqu_a_la_prochaine_charge():
    t = make(25, 25)
    t.set_request("skip", UNITS, T0, {"u1": 60, "u2": 60})
    assert t.decide(UNITS, T0, threshold=20, auto_enabled=True, sunny=True, tonight_ok=True) == (None, [], False)
    t.observe("u1", 100, T0)
    assert t.request == "skip"
    t.observe("u2", 100, T0)
    assert t.request == "auto"


def test_persistance():
    t = make(3, 4)
    t.set_request("tonight", UNITS, T0, {"u1": 50, "u2": 50})
    again = fc.FullChargeTracker(t.dump())
    assert again.request == "tonight" and again.request_units == UNITS
    assert round(again.days("u2", T0)) == 4
