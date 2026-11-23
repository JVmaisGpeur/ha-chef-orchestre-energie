from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import consumption as C

TZ = ZoneInfo("Europe/Paris")


def test_paques_et_feries():
    assert C.easter(2026) == date(2026, 4, 5)
    assert C.easter(2027) == date(2027, 3, 28)
    h = C.french_holidays(2026)
    assert date(2026, 4, 6) in h  # lundi de Pâques
    assert date(2026, 5, 14) in h  # Ascension
    assert date(2026, 5, 25) in h  # Pentecôte
    assert date(2026, 7, 14) in h and date(2026, 12, 25) in h


def test_types_de_jour():
    assert C.day_type(date(2026, 11, 23)) == C.WEEKDAY
    assert C.day_type(date(2026, 11, 28)) == C.SATURDAY
    assert C.day_type(date(2026, 11, 29)) == C.SUNDAY
    assert C.day_type(date(2026, 11, 11)) == C.SUNDAY  # férié un mercredi


def samples(days, kwh=lambda t: 0.5):
    start = datetime(2026, 11, 22, tzinfo=TZ) - timedelta(days=days)
    return [(start + timedelta(hours=h), kwh(start + timedelta(hours=h))) for h in range(days * 24)]


def test_demarrage_a_froid():
    p = C.ConsumptionProfile(daily_kwh_fallback=12)
    p.learn(samples(3))
    assert p.reliability == C.RELIABILITY_LOW
    assert abs(p.day_kwh(date(2026, 11, 23), TZ) - 12) < 0.01


def test_apprentissage_mediane():
    def kwh(t):
        if t.date() == date(2026, 11, 18):  # journée exceptionnelle
            return 5.0
        return 1.0 if t.hour == 19 else 0.3

    p = C.ConsumptionProfile(10)
    p.learn(samples(28, kwh))
    assert p.reliability == C.RELIABILITY_GOOD
    when = datetime(2026, 11, 24, 19, tzinfo=TZ)
    assert p.hour_kwh(when) == 1.0
    assert p.hour_kwh(when.replace(hour=3)) == 0.3


def test_fiabilite_moyenne():
    p = C.ConsumptionProfile(10)
    p.learn(samples(10))
    assert p.reliability == C.RELIABILITY_MEDIUM


def test_valeurs_aberrantes_ignorees():
    p = C.ConsumptionProfile(10)
    data = samples(14) + [(datetime(2026, 11, 21, 12, tzinfo=TZ), -3.0), (datetime(2026, 11, 21, 13, tzinfo=TZ), 99.0)]
    p.learn(data)
    assert p.hour_kwh(datetime(2026, 11, 23, 12, tzinfo=TZ)) == 0.5


def test_releves_cumules():
    pts = [(datetime(2026, 1, 1, h, tzinfo=TZ), v) for h, v in enumerate([100, 100.5, 101.5, 0.2, 0.7])]
    assert C.hourly_changes(pts) == [
        (pts[0][0], 0.5),
        (pts[1][0], 1.0),
        (pts[3][0], 0.5),
    ]


def test_facteur_correction_solaire():
    assert C.correction_factor([(10, 8), (12, 9), (8, 6)]) == 0.767
    assert C.correction_factor([(10, 30), (10, 30), (10, 30)]) == 1.5
    assert C.correction_factor([(10, 8)]) == 1.0  # pas assez de jours
    assert C.correction_factor([(0.1, 1), (0.2, 1), (0.3, 1)]) == 1.0


def test_rendement_mesure():
    assert C.measured_efficiency(100, 86, 0.85) == 0.86
    assert C.measured_efficiency(2, 1, 0.85) == 0.85
    assert C.measured_efficiency(100, 10, 0.85) == 0.6


def test_unites_d_energie():
    assert C.energy_factor("MWh") == 1000
    assert C.energy_factor("Wh") == 0.001
    assert C.energy_factor("kWh") == 1
    assert C.energy_factor(None) == 1


def test_tableau_energie():
    ancien = {"energy_sources": [
        {"type": "grid", "flow_from": [{"stat_energy_from": "sensor.import"}], "flow_to": [{"stat_energy_to": "sensor.export"}]},
        {"type": "solar", "stat_energy_from": "sensor.prod"},
        {"type": "battery", "stat_energy_from": "sensor.bat_out", "stat_energy_to": "sensor.bat_in"},
    ]}
    s = C.energy_dashboard_stats(ancien)
    assert s == {"import": ["sensor.import"], "export": ["sensor.export"], "solar": ["sensor.prod"],
                 "charge": ["sensor.bat_in"], "discharge": ["sensor.bat_out"]}
    plat = {"energy_sources": [{"type": "grid", "stat_energy_from": "sensor.i", "stat_energy_to": "sensor.e"}]}
    assert C.energy_dashboard_stats(plat)["import"] == ["sensor.i"]
    assert C.energy_dashboard_stats(None)["solar"] == []
