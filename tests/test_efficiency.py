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