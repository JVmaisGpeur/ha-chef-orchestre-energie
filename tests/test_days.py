"""Plan du jour et du lendemain (v1.4.0, ex-1.3.7)."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from conftest import days as D
from conftest import planner as P

TZ = ZoneInfo("Europe/Paris")
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=TZ)


def steps_from(start, hours, off):
    out, t = [], start
    for _ in range(hours * 4):
        o = off(t)
        out.append(P.Step(start=t, consumption_kwh=0.15, solar_kwh=0.0, price=0.16 if o else 0.27, off_peak=o))
        t += timedelta(minutes=15)
    return out


def tempo(t):
    return t.hour >= 22 or t.hour < 6


def plan_for(off=tempo, soc=20):
    return P.compute_plan(steps_from(NOW, 48, off), P.Battery(12.0, soc, 10, 100, 2400, 2400), P.Settings())


def test_fin_des_heures_creuses():
    plan = plan_for()
    assert plan.state == P.PLAN_CHARGE
    info, (d1, d2) = D.days(plan, NOW, "off_peak_end")
    assert info["time"] == "06:00"
    assert d1["start"] == datetime(2026, 11, 26, 6, 0, tzinfo=TZ).isoformat()
    assert d2["start"] == datetime(2026, 11, 27, 6, 0, tzinfo=TZ).isoformat()
    assert d1["night_decided"] and d1["charge_kwh"] > 0 and d1["night_state"] == P.PLAN_CHARGE
    assert d1["cost"] == round(d1["charge_kwh"] * 0.16, 2)
    assert d2["forecast"] and not d2["night_decided"] and d2["charge_kwh"] == 0


def test_debut_des_heures_creuses():
    plan = plan_for()
    info, (d1, d2) = D.days(plan, NOW, "off_peak_start")
    assert info["time"] == "22:00"
    assert d1["start"] == datetime(2026, 11, 25, 22, 0, tzinfo=TZ).isoformat()
    assert not d1["night_decided"]
    assert d2["night_decided"] and d2["charge_kwh"] > 0


def test_minuit_et_heure_fixe():
    plan = plan_for()
    assert D.days(plan, NOW, "midnight")[1][0]["start"] == datetime(2026, 11, 26, 0, 0, tzinfo=TZ).isoformat()
    info, (d1, _d2) = D.days(plan, NOW, "fixed", time(7, 30))
    assert info["time"] == "07:30" and d1["start"] == datetime(2026, 11, 26, 7, 30, tzinfo=TZ).isoformat()


def test_plusieurs_plages_creuses():
    def two(t):
        m = t.hour * 60 + t.minute
        return 750 <= m < 870 or m >= 1410 or m < 450  # 12:30-14:30 et 23:30-07:30

    plan = plan_for(two)
    assert D.boundary(plan.steps, "off_peak_end") == time(7, 30)
    assert D.boundary(plan.steps, "off_peak_start") == time(23, 30)


def test_offre_base_minuit():
    plan = plan_for(lambda t: False)
    assert D.boundary(plan.steps, "off_peak_end") == time(0, 0)


def test_reserve_dans_la_bonne_case():
    steps = steps_from(NOW, 48, tempo)
    for st in steps:
        st.price = 0.21 if st.off_peak else 0.25
    plan = P.compute_plan_with_reserve(steps, P.Battery(12.0, 80, 10, 100, 2400, 2400), P.Settings(), reserve_soc=50)
    _info, (d1, d2) = D.days(plan, NOW, "off_peak_end")
    assert d1["reserve_soc"] == 50 and d1["reserve_from"].startswith("2026-11-26T22:00")
    assert d2["reserve_soc"] is None


def test_fin_des_previsions():
    plan = P.compute_plan(steps_from(NOW, 36, tempo), P.Battery(12.0, 20, 10, 100, 2400, 2400), P.Settings())
    _info, (_d1, d2) = D.days(plan, NOW, "off_peak_end")
    assert d2["truncated_at"] == datetime(2026, 11, 28, 0, 0, tzinfo=TZ).isoformat()