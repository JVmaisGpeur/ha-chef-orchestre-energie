"""Scénarios du calcul du soir (cahier des charges, section « Calcul du soir »)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from conftest import planner as P

TZ = ZoneInfo("Europe/Paris")
STEP = timedelta(minutes=15)


def build(
    start=datetime(2026, 11, 23, 20, 0, tzinfo=TZ),  # lundi 20 h
    hours=36,
    hp=0.30,
    hc=0.20,
    hc_hours=lambda t: t.hour >= 23 or t.hour < 6,
    cons_kw=0.6,
    solar_kw=lambda t: 0.0,
    loads_w=lambda t: 0.0,
):
    steps = []
    t = start
    for _ in range(int(hours * 4)):
        off = hc_hours(t)
        steps.append(
            P.Step(
                start=t,
                consumption_kwh=cons_kw * 0.25,
                solar_kwh=solar_kw(t) * 0.25,
                price=hc if off else hp,
                off_peak=off,
                loads_w=loads_w(t),
            )
        )
        t += STEP
    return steps


def bat(soc=20, cap=12.0, soc_min=10, soc_max=100, pmax=2400):
    return P.Battery(cap, soc, soc_min, soc_max, pmax, pmax)


def sunny(t):
    """Belle journée : 0 à 4 kW entre 8 h et 18 h."""
    if 8 <= t.hour < 18:
        return 4.0 * (1 - abs(t.hour + t.minute / 60 - 13) / 5)
    return 0.0


def test_hiver_sans_soleil_charge_rentable():
    # Besoin : 17 h d'heures pleines à 0,6 kW + 10 % ≈ 11,2 kWh, batterie de 20 kWh
    plan = P.compute_plan(build(), bat(cap=20), P.Settings())
    assert plan.state == P.PLAN_CHARGE
    assert plan.reason == P.REASON_CHARGE_NEEDED
    assert plan.window_start.hour == 23 and plan.window_end.hour == 6
    assert 60 < plan.target_soc < 100
    # Les 2 kWh présents (SOC 20 %) partent ce soir ; il faut stocker 11,22 kWh
    # à rendre, donc 11,22 / √0,85 ≈ 12,17 kWh stockés
    assert abs(plan.energy_to_charge_kwh - 11.22 / 0.85 ** 0.5) < 0.05
    assert plan.charge_start >= plan.window_start
    # la charge finit avant 5 h 30 (30 min d'avance)
    charging = [sp for sp in plan.steps if sp.mode == P.MODE_GRID_CHARGE]
    assert charging and all(sp.start < plan.window_end for sp in charging)
    assert not plan.may_not_finish
    # Heures pleines de demain : la batterie fournit la maison
    assert any(sp.mode == P.MODE_SMART for sp in plan.steps if sp.start > plan.window_end)


def test_charge_le_plus_tard_possible():
    # Petite charge : elle doit démarrer en fin de nuit, pas à 23 h
    plan = P.compute_plan(build(cons_kw=0.15), bat(soc=10), P.Settings())
    assert plan.state == P.PLAN_CHARGE
    assert plan.charge_start.hour >= 3
    assert plan.charge_start + timedelta(minutes=30) <= plan.window_end


def test_ecart_non_rentable_batterie_a_l_arret():
    # 0,25 − 0,21 / 0,85 = 0,003 €/kWh < seuil de 0,02
    plan = P.compute_plan(build(hp=0.25, hc=0.21), bat(), P.Settings())
    assert plan.state == P.PLAN_NOT_PROFITABLE
    assert plan.energy_to_charge_kwh == 0
    night = [sp for sp in plan.steps if plan.window_start <= sp.start < plan.window_end]
    assert night and all(sp.mode == P.MODE_OFF for sp in night)
    # mais l'énergie déjà stockée sert aux heures pleines
    assert any(sp.mode == P.MODE_SMART for sp in plan.steps)


def test_seuil_reglable():
    s = P.Settings(gain_threshold=0.0)
    plan = P.compute_plan(build(hp=0.25, hc=0.21), bat(), s)
    assert plan.state == P.PLAN_CHARGE
    s = P.Settings(gain_threshold=0.10)
    plan = P.compute_plan(build(), bat(), s)  # gain 0,065 < 0,10
    assert plan.state == P.PLAN_NOT_PROFITABLE


def test_ete_tres_solaire_pas_de_charge():
    plan = P.compute_plan(build(solar_kw=sunny, cons_kw=0.4), bat(soc=60), P.Settings())
    assert plan.state == P.PLAN_IDLE
    assert plan.energy_to_charge_kwh == 0


def test_soleil_reduit_la_charge():
    winter = P.compute_plan(build(), bat(cap=20), P.Settings())
    sunny_plan = P.compute_plan(build(solar_kw=lambda t: sunny(t) / 4), bat(cap=20), P.Settings())
    assert 0 < sunny_plan.energy_to_charge_kwh < winter.energy_to_charge_kwh


def test_week_end_en_heures_creuses_rien_a_couvrir():
    # Samedi 20 h, tout le week-end en HC, horizon jusqu'à dimanche soir
    start = datetime(2026, 11, 28, 20, 0, tzinfo=TZ)
    plan = P.compute_plan(build(start=start, hc_hours=lambda t: True, hours=24), bat(), P.Settings())
    assert plan.state == P.PLAN_NOTHING_TO_COVER
    assert plan.energy_to_charge_kwh == 0


def test_tempo_rouge_capacite_insuffisante_reserve_les_heures_cheres():
    # Heures pleines rouges à prix variable pour tester la réserve
    def hp_price(t):
        return 0.75 if 17 <= t.hour < 21 else 0.60

    steps = build(hp=0.60, hc=0.15, cons_kw=1.5)
    for st in steps:
        if not st.off_peak:
            st.price = hp_price(st.start)
    plan = P.compute_plan(steps, bat(cap=5.0), P.Settings())
    assert plan.state == P.PLAN_CHARGE
    assert plan.capacity_short
    assert plan.reason == P.REASON_CAPACITY_SHORT
    assert plan.target_soc == 100
    tomorrow = [sp for sp in plan.steps if plan.window_end <= sp.start < plan.cover_end]
    reserved = [sp for sp in tomorrow if sp.mode == P.MODE_SMART_CHARGE]
    used = [sp for sp in tomorrow if sp.mode == P.MODE_SMART]
    assert reserved and used
    # la batterie sert aux heures les plus chères en priorité
    assert min(sp.price for sp in used) >= max(sp.price for sp in reserved)


def test_batterie_deja_assez_chargee():
    plan = P.compute_plan(build(cons_kw=0.2), bat(soc=100, cap=20), P.Settings())
    assert plan.state == P.PLAN_IDLE
    assert plan.reason == P.REASON_ENOUGH_ENERGY
    night = [sp for sp in plan.steps if plan.window_start <= sp.start < plan.window_end]
    assert all(sp.mode == P.MODE_OFF for sp in night)


def test_forcer_la_nuit():
    plan = P.compute_plan(build(), bat(), P.Settings(), P.Override("idle"))
    assert plan.state == P.PLAN_IDLE and plan.reason == P.REASON_FORCED_IDLE
    plan = P.compute_plan(build(hp=0.25, hc=0.21), bat(soc=20), P.Settings(), P.Override("charge", 80))
    assert plan.state == P.PLAN_CHARGE and plan.reason == P.REASON_FORCED_CHARGE
    assert plan.target_soc == 80


def test_gros_consommateur_avance_la_charge_et_alerte():
    def ce(t):  # chauffe-eau 3 kW de 23 h à 2 h
        return 3000.0 if t.hour >= 23 or t.hour < 2 else 0.0

    base = P.compute_plan(build(), bat(soc=10), P.Settings(import_limit_w=5400))
    with_load = P.compute_plan(build(loads_w=ce), bat(soc=10), P.Settings(import_limit_w=5400))
    assert with_load.charge_start <= base.charge_start
    alert = P.compute_plan(build(loads_w=ce), bat(soc=10), P.Settings(import_limit_w=3000))
    assert alert.power_alert


def test_pas_assez_de_temps():
    plan = P.compute_plan(
        build(hc_hours=lambda t: t.hour == 23), bat(soc=10, cap=20, pmax=2000), P.Settings()
    )
    assert plan.state == P.PLAN_CHARGE
    assert plan.may_not_finish


def test_prix_inconnu_donnees_manquantes():
    steps = build()
    for st in steps:
        if st.off_peak:
            st.price = None
    plan = P.compute_plan(steps, bat(), P.Settings())
    assert plan.state == P.PLAN_MISSING_DATA


def test_offre_base_sans_heures_creuses():
    plan = P.compute_plan(build(hc_hours=lambda t: False), bat(), P.Settings())
    assert plan.state == P.PLAN_NOTHING_TO_COVER
    assert all(sp.mode == P.MODE_SMART for sp in plan.steps)


def test_simulation_soc_coherente():
    plan = P.compute_plan(build(), bat(soc=20), P.Settings())
    socs = [sp.soc for sp in plan.steps]
    assert all(10 - 1e-6 <= v <= 100 + 1e-6 for v in socs)
    end_of_night = [sp for sp in plan.steps if sp.start < plan.window_end][-1]
    assert end_of_night.soc >= plan.target_soc - 3


def test_gain_positif_quand_rentable():
    plan = P.compute_plan(build(hp=0.40, hc=0.15), bat(), P.Settings())
    assert plan.forecast_gain_eur > 0


@pytest.mark.parametrize(
    "kva,margin,tri,expected", [(9, 0.10, False, 8100), (9, 0.05, False, 8100), (9, 0.2, False, 7200), (12, 0.1, True, 3600)]
)
def test_limite_de_soutirage(kva, margin, tri, expected):
    assert P.import_limit_w(kva, margin, tri) == expected


# ---------------------------------------------------------------- E2 (v1.2.0)
def test_reserve_si_non_rentable():
    # R1 (v1.3.5) : la réserve est prévue pour les heures creuses de la nuit seulement
    steps = build(hp=0.25, hc=0.21)
    plan = P.compute_plan_with_reserve(steps, bat(soc=80), P.Settings(), reserve_soc=50)
    assert plan.state == P.PLAN_NOT_PROFITABLE
    assert plan.reserve_soc == 50 and plan.soc_min == 10
    assert plan.reserve_from == datetime(2026, 11, 23, 23, 0, tzinfo=TZ)
    assert plan.reserve_until == datetime(2026, 11, 24, 6, 0, tzinfo=TZ)
    # en heures pleines, la batterie descend jusqu'au SOC min de l'utilisateur
    assert min(sp.soc for sp in plan.steps) < 50


def test_reserve_ignoree_si_rentable():
    plan = P.compute_plan_with_reserve(build(), bat(soc=80, cap=20), P.Settings(), reserve_soc=50)
    assert plan.state in (P.PLAN_CHARGE, P.PLAN_IDLE)
    assert plan.reserve_soc is None and plan.soc_min == 10
    assert plan.reserve_from is None and plan.reserve_until is None
    assert all(P.reserve_at(plan, sp.start) is None for sp in plan.steps)


def test_reserve_ne_fait_pas_charger():
    # SOC déjà sous la réserve : la réserve ne crée aucune charge réseau
    steps = build(hp=0.25, hc=0.21, solar_kw=lambda t: sunny(t) / 2)
    plan = P.compute_plan_with_reserve(steps, bat(soc=30), P.Settings(), reserve_soc=50)
    assert plan.reserve_soc == 50
    assert plan.state == P.PLAN_NOT_PROFITABLE
    assert all(sp.charge_kwh == 0 for sp in plan.steps)


# ---------------------------------------------------------------- R1 (v1.3.5)
def tempo_rouge_26_11(late_peak=False):
    """26/11/2026 jour rouge (HP 0,7295 jusqu'à 22:00), HC rouges 0,1615, 27/11 blanc (HP 0,1921)."""
    hc_hours = lambda t: t.hour >= 22 or t.hour < 6
    steps = build(start=datetime(2026, 11, 26, 12, 0, tzinfo=TZ), hours=36, hc_hours=hc_hours, cons_kw=1.0)
    for st in steps:
        if st.off_peak:
            st.price = 0.1615
        else:
            st.price = 0.7295 if st.start.day == 26 else 0.1921
        if late_peak and st.start.day == 26 and st.start.hour == 22 and st.start.minute < 30:
            st.price = 0.7295  # heure pleine tardive (jour spécial) marquée creuse
    return steps


def test_r1_jour_rouge_reserve_seulement_en_heures_creuses():
    plan = P.compute_plan_with_reserve(
        tempo_rouge_26_11(), bat(soc=40, cap=10, soc_min=5), P.Settings(gain_threshold=0.05), reserve_soc=50
    )
    assert plan.state == P.PLAN_NOT_PROFITABLE
    at = lambda d, h, m=0: datetime(2026, 11, d, h, m, tzinfo=TZ)
    # à 12:00 : SOC min de l'utilisateur, la batterie peut descendre jusqu'à 5 % avant 22:00
    assert P.reserve_at(plan, at(26, 12)) is None
    assert P.reserve_at(plan, at(26, 21, 59)) is None
    assert plan.soc_min == 5
    assert min(sp.soc for sp in plan.steps if sp.start < at(26, 22)) <= 5 + 1e-6
    # 22:00 → 06:00 : réserve de 50 %, levée à 06:00
    assert (plan.reserve_from, plan.reserve_until) == (at(26, 22), at(27, 6))
    assert P.reserve_at(plan, at(26, 22)) == 50
    assert P.reserve_at(plan, at(27, 5, 59)) == 50
    assert P.reserve_at(plan, at(27, 6)) is None


def test_r1_jamais_de_reserve_sur_une_heure_pleine_tardive():
    plan = P.compute_plan_with_reserve(
        tempo_rouge_26_11(late_peak=True), bat(soc=40, cap=10, soc_min=5), P.Settings(gain_threshold=0.05), reserve_soc=50
    )
    at = lambda d, h, m=0: datetime(2026, 11, d, h, m, tzinfo=TZ)
    assert P.reserve_at(plan, at(26, 22)) is None
    assert P.reserve_at(plan, at(26, 22, 15)) is None
    assert plan.reserve_from == at(26, 22, 30) and plan.reserve_until == at(27, 6)


def test_r1_reserve_pendant_les_heures_creuses_en_cours():
    # Calcul fait à 23:30, en pleine nuit : réserve tout de suite, jusqu'à 06:00
    steps = build(start=datetime(2026, 11, 23, 23, 30, tzinfo=TZ), hp=0.25, hc=0.21)
    plan = P.compute_plan_with_reserve(steps, bat(soc=80), P.Settings(), reserve_soc=50)
    assert P.reserve_at(plan, datetime(2026, 11, 23, 23, 30, tzinfo=TZ)) == 50
    assert plan.reserve_until == datetime(2026, 11, 24, 6, 0, tzinfo=TZ)


def test_soc_max_100_si_le_soleil_deborde():
    steps = build(cons_kw=0.3, solar_kw=sunny)
    b = bat(soc=70, cap=10, soc_max=90)
    plan = P.compute_plan(steps, b, P.Settings())
    assert P.daylight_overflow(plan) >= 0.2
    assert P.wants_full_charge(plan)
    # peu de soleil : pas de passage à 100 %
    small = P.compute_plan(build(cons_kw=0.6, solar_kw=lambda t: sunny(t) / 8), b, P.Settings())
    assert not P.wants_full_charge(small)


def test_charge_reseau_plafonnee_au_max_utilisateur():
    b = P.Battery(10, 10, 10, 100, 2400, 2400, grid_soc_max=90)
    plan = P.compute_plan(build(cons_kw=1.5), b, P.Settings())
    assert plan.state == P.PLAN_CHARGE
    assert plan.target_soc <= 90
    night = [sp for sp in plan.steps if plan.window_start <= sp.start < plan.window_end]
    assert max(sp.soc for sp in night) <= 90 + 1e-6


def test_ecart_de_prix_et_fin_de_charge():
    plan = P.compute_plan(build(), bat(cap=20), P.Settings())
    assert abs(plan.price_gap - (0.30 - 0.20 / 0.85)) < 1e-3
    assert plan.charge_start < plan.charge_end <= plan.window_end
