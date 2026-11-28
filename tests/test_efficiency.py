"""C0 (v1.4.0) : rendement aller-retour mesuré côté prise."""

from datetime import datetime, timedelta

from conftest import consumption as C

H0 = datetime(2026, 11, 1)


def hours(values):
    return {H0 + timedelta(hours=i): v for i, v in enumerate(values)}


def test_rendement_cote_prise_et_non_dans_le_pack():
    # 10 kWh entrés côté AC, 9,3 dans le pack, 9,0 sortis du pack, 8,4 vers la maison
    eta, eta_c, eta_d = C.ac_efficiency(
        hours([5.0, 5.0]), hours([4.65, 4.65]), hours([0, 0, 4.5, 4.5]), hours([0, 0, 4.2, 4.2])
    )
    assert abs(eta - 0.868) < 0.005  # ≈ 0,87, pas 0,97 (9,0 ÷ 9,3) mesuré dans le pack
    assert eta_c == 0.93 and abs(eta_d - 0.933) < 0.001
    assert C.within_efficiency_bounds(eta)


def test_rendement_hors_bornes_refuse():
    assert not C.within_efficiency_bounds(0.99)
    assert not C.within_efficiency_bounds(0.55)
    assert not C.within_efficiency_bounds(None)
    assert C.within_efficiency_bounds(0.60) and C.within_efficiency_bounds(0.95)


def test_pas_assez_d_energie():
    assert C.ac_efficiency(hours([1.0]), hours([0.9]), hours([0.9]), hours([0.8])) == (None, None, None)


def test_heures_avec_solaire_continu_ignorees():
    # Heure 1 : le pack reçoit plus que l'entrée AC (PV en courant continu) -> ignorée
    eta, eta_c, _ = C.ac_efficiency(
        hours([6.0, 1.0]), hours([5.4, 3.0]), hours([0, 0, 6.0]), hours([0, 0, 5.4])
    )
    assert eta_c == 0.9
    assert eta == 0.81

# ------------------------------------------------------------------ F2 (v1.4.1) : rendement sur cycles
def test_rendement_sur_cycles_compteurs_identiques():
    # 834 kWh chargés, 736 kWh rendus, niveau inchangé : 88 %
    assert C.cycle_efficiency(834, 736, 0.0, 20.64) == 0.882


def test_rendement_sur_cycles_corrige_du_stock():
    # Même énergie rendue, mais la batterie finit 12 kWh plus vide : sans correction 98 %
    assert C.cycle_efficiency(100, 98, -12.0, 20.0) == 0.86
    # finit plus pleine : l'énergie stockée compte comme rendue
    assert C.cycle_efficiency(100, 76, 12.0, 20.0) == 0.88


def test_rendement_sur_cycles_trop_peu_de_cycles():
    assert C.cycle_efficiency(40, 35, 0.0, 20.0) is None  # moins de 3 cycles
    assert C.cycle_efficiency(5, 4, 0.0, 1.0) is None  # moins de 10 kWh
    assert C.cycle_efficiency(100, 60, 30.0, 20.0) is None  # stock trop changeant
