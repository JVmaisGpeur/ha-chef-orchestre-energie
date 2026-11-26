"""Arbitrage batteries / routeur F1ATB (N5)."""

from datetime import datetime, timedelta, timezone

from conftest import router_logic as rl

T0 = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)


def inp(t=0, **kw):
    base = dict(
        now=T0 + timedelta(minutes=t), priority=rl.BATTERY_FIRST, routed_w=0, load_w=2400,
        target_reached=False, on_slot=False, battery_w=0, max_charge_w=2400, all_full=False,
        grid_export=False, soc=60, summer_soc=90, batteries_sun_ok=False, ballon_sun_ok=False,
    )
    base.update(kw)
    return rl.RouterInputs(**base)


def test_batteries_d_abord_verrouille_puis_deverrouille_apres_2_min():
    lg = rl.RouterLogic()
    assert lg.step(inp(0, battery_w=1500)).lock
    assert lg.step(inp(1, battery_w=2350, grid_export=True)).lock
    assert lg.step(inp(2, battery_w=2350, grid_export=True)).lock
    assert not lg.step(inp(3, battery_w=2350, grid_export=True)).lock  # 2 min tenues
    # reverrouillage immédiat dès que la charge passe sous 80 %
    assert lg.step(inp(4, battery_w=1800)).lock


def test_batteries_pleines_deverrouillent():
    lg = rl.RouterLogic()
    lg.step(inp(0, all_full=True))
    lg.step(inp(1, all_full=True))
    assert not lg.step(inp(2, all_full=True)).lock
    # pleines : une charge faible ne reverrouille pas, une décharge oui
    assert not lg.step(inp(3, all_full=True, battery_w=0)).lock
    assert lg.step(inp(4, all_full=True, battery_w=-300)).lock


def test_plage_on_interdit_la_decharge_ou_est_bloquee():
    lg = rl.RouterLogic()
    d = lg.step(inp(0, on_slot=True))
    assert not d.lock and d.no_discharge and d.reason == rl.R_BOOST
    assert lg.step(inp(1, on_slot=True, target_reached=True)).reason == rl.R_ON_BLOCKED
    assert lg.step(inp(2, on_slot=True, ballon_sun_ok=True)).lock


def test_routeur_d_abord_plafond_de_charge():
    lg = rl.RouterLogic()
    d = lg.step(inp(0, priority=rl.ROUTER_FIRST, routed_w=1200))
    assert not d.lock and d.charge_ceiling_w == 0.0
    assert lg.step(inp(1, priority=rl.ROUTER_FIRST, routed_w=2350)).charge_ceiling_w is None
    assert lg.step(inp(2, priority=rl.ROUTER_FIRST, target_reached=True)).charge_ceiling_w is None


def test_surveillance_deleste_si_les_batteries_chauffent_le_ballon():
    lg = rl.RouterLogic()
    kw = dict(priority=rl.ROUTER_FIRST, battery_w=-800, routed_w=900)
    assert not lg.step(inp(0, **kw)).lock
    assert not lg.step(inp(1, **kw)).lock
    assert lg.step(inp(2, **kw)).reason == rl.R_SHED
    # relâché une minute après que la batterie ne se décharge plus
    assert lg.step(inp(3, priority=rl.ROUTER_FIRST, battery_w=0, routed_w=900)).lock
    assert not lg.step(inp(4, priority=rl.ROUTER_FIRST, battery_w=0, routed_w=900)).lock


def test_exception_ete():
    lg = rl.RouterLogic()
    kw = dict(priority=rl.ROUTER_FIRST, battery_w=-800, routed_w=900, soc=95, batteries_sun_ok=True)
    for t in range(5):
        assert not lg.step(inp(t, **kw)).lock


def test_combinaison_des_routeurs():
    a = rl.RouterDecision(False, rl.R_ROUTING, charge_ceiling_w=0.0)
    b = rl.RouterDecision(False, rl.R_BOOST, no_discharge=True)
    assert rl.combine([a, b]) == (0.0, True)
    assert rl.combine([]) == (None, False)


def test_charge_reseau_leve_le_plafond_routeur_d_abord():
    # La nuit, le routeur ne route rien : sans cette règle, la charge en HC serait bloquée à 0 W
    lg = rl.RouterLogic()
    d = lg.step(inp(0, priority=rl.ROUTER_FIRST, routed_w=0))
    assert d.charge_ceiling_w == 0.0
    assert rl.combine([d], grid_charging=True) == (None, False)
    boost = rl.RouterDecision(False, rl.R_BOOST, no_discharge=True)
    assert rl.combine([d, boost], grid_charging=True) == (None, True)


# Planning réel d'un ECS_F1ATB : plage ON de 4:00 à 5:59, chauffe sous 50 °C
SLOTS = [
    {"start_min": 0, "end_min": 240, "kind": "off", "temp_channel": 0, "t_below": 45},
    {"start_min": 240, "end_min": 359, "kind": "on", "temp_channel": 0, "t_below": 50},
    {"start_min": 359, "end_min": 570, "kind": "off", "temp_channel": -1, "t_below": None},
    {"start_min": 570, "end_min": 1110, "kind": "route", "temp_channel": 0, "t_below": 60},
    {"start_min": 1110, "end_min": 1440, "kind": "off", "temp_channel": -1, "t_below": None},
]


def test_prochaine_plage_on_le_lendemain():
    soir = datetime(2026, 11, 26, 20, tzinfo=timezone.utc)
    start, end, t_below = rl.next_on_slot(SLOTS, soir)
    assert start == datetime(2026, 11, 27, 4, tzinfo=timezone.utc)
    assert end == datetime(2026, 11, 27, 5, 59, tzinfo=timezone.utc)
    assert t_below == 50


def test_plage_on_en_cours_puis_aucune_apres_la_fin():
    nuit = datetime(2026, 11, 26, 5, tzinfo=timezone.utc)
    assert rl.next_on_slot(SLOTS, nuit)[0] == datetime(2026, 11, 26, 4, tzinfo=timezone.utc)
    matin = datetime(2026, 11, 26, 7, tzinfo=timezone.utc)
    assert rl.next_on_slot(SLOTS, matin)[0] == datetime(2026, 11, 27, 4, tzinfo=timezone.utc)
    assert rl.next_on_slot(SLOTS, matin, timedelta(hours=12)) is None
    assert rl.next_on_slot([s for s in SLOTS if s["kind"] != "on"], matin) is None
    assert rl.next_on_slot(None, matin) is None


def test_plage_on_sans_sonde_sans_seuil():
    slots = [{"start_min": 1380, "end_min": 120, "kind": "on", "temp_channel": -1, "t_below": 50}]
    start, end, t_below = rl.next_on_slot(slots, datetime(2026, 11, 26, 20, tzinfo=timezone.utc))
    assert (start.hour, end.day, end.hour, t_below) == (23, 27, 2, None)


def test_prevision_de_la_plage_on():
    assert rl.on_slot_outlook(41, 50, False, False) == rl.OUTLOOK_HEAT
    assert rl.on_slot_outlook(41, 50, False, True) == rl.OUTLOOK_SUN
    assert rl.on_slot_outlook(51, 50, False, False) == rl.OUTLOOK_HOT
    assert rl.on_slot_outlook(41, 50, True, False) == rl.OUTLOOK_HOT
    assert rl.on_slot_outlook(None, None, False, False) == rl.OUTLOOK_HEAT


# ---- Chauffe déplacée par le Chef (option router_shift, v1.3.4)
STEP = timedelta(minutes=15)
NIGHT0 = datetime(2026, 11, 26, 22, tzinfo=timezone.utc)  # 22:00, HC de 23:00 à 6:00


def night(charge_w=0.0, charge_from=None, charge_to=None, base_w=300.0):
    out = []
    for k in range(40):  # 22:00 → 8:00
        t = NIGHT0 + k * STEP
        off_peak = datetime(2026, 11, 26, 23, tzinfo=timezone.utc) <= t < datetime(2026, 11, 27, 6, tzinfo=timezone.utc)
        charging = charge_from is not None and charge_from <= t < charge_to
        out.append(rl.NightStep(t, off_peak, base_w + (charge_w if charging else 0.0), charging))
    return out


def at(h, m=0):
    return datetime(2026, 11, 27 if h < 12 else 26, h, m, tzinfo=timezone.utc)


def choose(n, previous=None, slot=(at(4), at(5, 59))):
    return rl.choose_heat_window(n, STEP, slot[0], slot[1], 2000.0, 4500.0, previous)


def test_plage_libre_gardee():
    assert choose(night()) == (at(4), at(5, 59), None)


def test_plage_deplacee_hors_charge_des_batteries():
    # Charge à 2400 W de 4:00 à 6:00 : 300 + 2400 + 2000 > 4500 W
    start, end, why = choose(night(2400, at(4), at(6)))
    assert (start, end, why) == (at(2), at(3, 59), rl.WHY_POWER)
    # Petite charge : pas de dépassement, mais la chauffe la ralentirait
    assert choose(night(1000, at(4), at(6)))[2] == rl.WHY_BATTERY


def test_pas_de_va_et_vient():
    assert choose(night(2400, at(4), at(6)), previous=at(1))[0] == at(1)


def test_reste_dans_les_heures_creuses():
    start, end, _ = choose(night(2400, at(23), at(6)), slot=(at(4), at(5, 59)))
    assert at(23) <= start and end <= at(6)
    # Plage hors heures creuses : jamais déplacée
    assert choose(night(2400, at(23), at(6)), slot=(at(7), at(7, 30)))[2] is None


def test_chauffe_deplacee_forcee_puis_plage_bloquee():
    lg = rl.RouterLogic()
    d = lg.step(inp(0, force_heat=True, on_slot=True, slot_shifted=True))
    assert d.force and not d.lock and d.no_discharge and d.reason == rl.R_SHIFT_HEAT
    d = lg.step(inp(1, on_slot=True, slot_shifted=True))
    assert d.lock and not d.force and d.reason == rl.R_SHIFTED
