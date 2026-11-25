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
