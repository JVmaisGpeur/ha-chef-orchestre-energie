"""C1 à C4 (v1.4.0) : coût réel de la recharge, coût de l'énergie en stock, usure."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import costs as K

TZ = ZoneInfo("Europe/Paris")
T0 = datetime(2026, 11, 23, 23, 0, tzinfo=TZ)


def test_charge_reseau_2_kwh():
    c = K.ChargeCost()
    c.update(T0, 10.0, 0.0, 0.1615, 0.0)  # première lecture : point de départ
    c.update(T0 + timedelta(hours=1), 12.0, 0.0, 0.1615, 0.0)
    assert abs(c.cost_eur - 0.323) < 0.001 and c.grid_kwh == 2.0
    assert c.average_price == 0.1615


def test_chaque_minute_a_son_prix():
    # HC à 23:30 ; 2 kW de 23:15 à 23:45 -> 0,5 kWh HP + 0,5 kWh HC
    c = K.ChargeCost()
    t = T0 + timedelta(minutes=15)
    c.update(t, 0.0, 0.0, 0.25, 0)
    e = 0.0
    for m in range(30):
        t += timedelta(minutes=1)
        e += 2.0 / 60
        price = 0.25 if t <= T0 + timedelta(minutes=30) else 0.16
        c.update(t, e, 0.0, price, 0)
    assert abs(c.cost_eur - (0.5 * 0.25 + 0.5 * 0.16)) < 0.002


def test_prix_inconnu_attend_le_premier_prix():
    c = K.ChargeCost()
    c.update(T0, 0.0, 0.0, None, 0)
    c.update(T0 + timedelta(minutes=1), 1.0, 0.0, None, 0)
    assert c.cost_eur == 0 and c.pending_kwh == 1.0
    c.update(T0 + timedelta(minutes=2), 1.5, 0.0, 0.2, 0)
    assert abs(c.cost_eur - 0.3) < 1e-9 and c.pending_kwh == 0


def test_compteur_qui_repart_a_zero():
    c = K.ChargeCost()
    c.update(T0, 50.0, 0.0, 0.2, 0)
    c.update(T0 + timedelta(minutes=1), 0.5, 0.0, 0.2, 0)
    assert c.cost_eur == 0
    c.update(T0 + timedelta(minutes=2), 1.5, 0.0, 0.2, 0)
    assert abs(c.cost_eur - 0.2) < 1e-9


def test_solaire_stocke_au_prix_de_revente():
    c = K.ChargeCost()
    c.update(T0, 0.0, 0.0, 0.2, 0.10)
    g, s = c.update(T0 + timedelta(hours=1), 0.0, 1.0, 0.2, 0.10)
    assert g == 0 and abs(s - 0.10) < 1e-9 and abs(c.solar_value_eur - 0.10) < 1e-9


def test_remise_a_zero_le_1er_du_mois():
    c = K.ChargeCost()
    c.update(datetime(2026, 11, 30, 23, 0, tzinfo=TZ), 0.0, 0.0, 0.2, 0)
    c.update(datetime(2026, 11, 30, 23, 30, tzinfo=TZ), 1.0, 0.0, 0.2, 0)
    c.update(datetime(2026, 12, 1, 0, 30, tzinfo=TZ), 2.0, 0.0, 0.2, 0)
    assert c.month == "2026-12" and abs(c.cost_eur - 0.2) < 1e-9 and c.grid_kwh == 1.0


def test_persistance():
    c = K.ChargeCost()
    c.update(T0, 1.0, 2.0, 0.2, 0.1)
    c.update(T0 + timedelta(hours=1), 2.0, 2.0, 0.2, 0.1)
    d = K.ChargeCost.load(c.dump())
    assert d.dump() == c.dump()


def test_stock_decharge_de_moitie_prix_inchange():
    s = K.StockCost()
    assert s.start(4.0, 0.0, 0.20, 0.0)
    assert abs(s.cost_grid - 0.80) < 1e-9 and s.price_stored() == 0.2
    s.update(2.0, 0.0)
    assert abs(s.cost_grid - 0.40) < 1e-9 and s.price_stored() == 0.2


def test_stock_reserve_sans_charge_ni_decharge():
    s = K.StockCost()
    s.start(4.0, 2.0, 0.20, 0.05)
    before = s.price_stored()
    for _ in range(10):
        s.update(4.0, 2.0)
    assert s.price_stored() == before


def test_stock_charge_ajoute_son_cout():
    s = K.StockCost()
    s.start(0.0, 1.0, 0.20, 0.10)
    s.update(1.0, 1.0, add_grid=0.2)
    assert abs(s.cost_grid - 0.2) < 1e-9
    assert s.price_stored() == 0.15  # (0,2 + 0,1) / 2
    assert s.price_delivered(0.93) == round(0.15 / 0.93, 4)
    assert s.solar_share == 50.0


def test_stock_initial_estime():
    s = K.StockCost()
    assert not s.start(4.0, 0.0, None, 0)  # pas encore de prix HC : on attend
    s.start(4.0, 0.0, 0.2, 0)
    s.initial_share = 0.5
    assert s.estimated
    s.initial_share = 0.05
    assert not s.estimated


def test_rattrapage_par_tranches():
    slices = [(T0 + timedelta(minutes=5 * i), 0.1) for i in range(12)]  # 1,2 kWh en 1 h
    prices = [(T0 - timedelta(hours=1), 0.25), (T0 + timedelta(minutes=30), 0.16)]
    cost, unpriced = K.value_slices(slices, prices, 0.2)
    assert abs(cost - (0.6 * 0.25 + 0.6 * 0.16)) < 1e-9 and unpriced == 0
    cost, unpriced = K.value_slices(slices, [], 0.2)
    assert abs(cost - 0.24) < 1e-9 and abs(unpriced - 1.2) < 1e-9


def test_usure_moyenne_ponderee():
    assert K.weighted_wear([]) is None
    assert K.weighted_wear([(0.05, None)]) == 0.05
    assert K.weighted_wear([(0.04, 4.0), (0.10, 2.0)]) == 0.06
    assert K.weighted_wear([(0.04, None), (0.10, 2.0)]) == 0.07