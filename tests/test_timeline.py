from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import _load

T = _load("timeline")
TZ = ZoneInfo("Europe/Paris")


def seg(h0, h1, prix, periode, hc, couleur=None, day=23, **kw):
    d = {
        "debut": datetime(2026, 11, day, h0, tzinfo=TZ).isoformat(),
        "fin": datetime(2026, 11, day, h1, tzinfo=TZ).isoformat(),
        "periode": periode,
        "libelle": "x",
        "prix": prix,
        "couleur": couleur,
        "saison": None,
        "jour_special": None,
        "heures_creuses": hc,
    }
    d.update(kw)
    return d


def test_lecture_des_tranches():
    resp = {"segments": [seg(6, 22, 0.3, "hp", False), seg(22, 23, 0.2, "HC", True, jour_special_confirme=False)]}
    s = T.parse_segments(resp)
    assert len(s) == 2
    assert s[1].period == "hc" and s[1].off_peak and not s[1].special_confirmed
    assert s[0].special_confirmed


def test_prix_tempo_inconnu_couleur_supposee():
    resp = {"segments": [seg(6, 22, 0.20, "hp", False, "bleu"), seg(22, 23, None, "hc", True)]}
    s = T.parse_segments(resp)
    grid = {"lignes": [{"libelle": "blanc", "prix": {"HP": 0.25, "HC": 0.17}}]}
    assert T.fill_unknown_prices(s, grid, "blanc") == 1
    assert s[1].price == 0.17


def test_prix_inconnu_sans_grille():
    resp = {"segments": [seg(1, 6, 0.15, "hc", True), seg(6, 22, 0.2, "hp", False), seg(22, 23, None, "hc", True), seg(23, 23, None, "xx", False)]}
    s = T.parse_segments(resp)
    T.fill_unknown_prices(s, None, "blanc")
    assert s[2].price == 0.15  # même période
    assert s[3].price == 0.2  # le plus cher connu


def test_repartition_par_pas():
    starts = T.step_starts(datetime(2026, 11, 23, 10, 7, tzinfo=TZ), 2, 15)
    assert starts[0].minute == 0 and len(starts) == 8
    periods = [(starts[0], starts[0] + timedelta(hours=1), 1.0)]
    out = T.spread(periods, starts, timedelta(minutes=15))
    assert out[:4] == [0.25] * 4 and out[4:] == [0.0] * 4


def test_wh_hours():
    base = datetime(2026, 11, 23, 9, tzinfo=TZ)
    wh = {(base + timedelta(hours=i)).isoformat(): 500 for i in range(3)}
    wh[(base + timedelta(hours=20)).isoformat()] = 100
    p = T.wh_hours_to_periods(wh)
    assert p[0] == (base, base + timedelta(hours=1), 0.5)
    assert p[-1][1] - p[-1][0] == timedelta(hours=1)


def test_fenetres_habituelles():
    w = T.parse_window("23:00-02:00")
    assert T.in_window(datetime(2026, 1, 1, 23, 30), w)
    assert T.in_window(datetime(2026, 1, 1, 1, 0), w)
    assert not T.in_window(datetime(2026, 1, 1, 3, 0), w)
    assert T.parse_window("bad") is None
    assert not T.in_window(datetime(2026, 1, 1, 1, 0), None)


def test_premier_pas_avant_le_debut_des_tranches():
    """Les tranches commencent à l'instant de l'appel, la grille au quart d'heure précédent."""
    now = datetime(2026, 11, 22, 23, 49, 12, tzinfo=TZ)
    resp = {"segments": [{"debut": now.isoformat(), "fin": datetime(2026, 11, 23, 6, tzinfo=TZ).isoformat(),
                          "periode": "hc", "prix": 0.17, "heures_creuses": True}]}
    segs = T.parse_segments(resp)
    starts = T.step_starts(now, 1, 15)
    assert starts[0].minute == 45
    assert T.at(segs, starts[0]) is None  # l'ancien comportement
    assert T.segment_for_step(segs, starts[0], timedelta(minutes=15)).price == 0.17
