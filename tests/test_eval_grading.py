from datetime import datetime, timedelta, timezone

from conftest import site_case as _case

from uisce.eval_grading import (
    Event,
    letter,
    monthly_counts,
    near_another,
    outside_band,
    supply_events,
)
from uisce.site import SUPPLY_CUTS, TownLookup, build_site

NOW = datetime(2026, 10, 6, tzinfo=timezone.utc)
TOWNS = TownLookup([("SA1", "T1", "Testtown", "Carlow", 52.836, -6.926, 1000)])
DAY = datetime(2026, 5, 4, 9, tzinfo=timezone.utc)


def _event(lat=52.836, lon=-6.926, day=0, sev="outage", investigation=False):
    return Event("Carlow", sev, DAY + timedelta(days=day), False, investigation, ((lat, lon),))


def test_the_count_is_the_one_the_site_publishes():
    rows = [
        _case(id=1, reference_num="CAR00000001"),
        _case(id=2, reference_num="CAR00000002", work_category="essential_works",
              work_type="Planned"),
        _case(id=3, reference_num="CAR00000003", work_category="discolouration"),
        _case(id=4, reference_num="HM0000000004", work_category="investigation"),
    ]
    events = supply_events(rows, NOW)
    site = build_site(rows, NOW, TOWNS)
    may = site["counties"]["Carlow"]["months"]["2026-05"]
    assert monthly_counts(events, ["2026-05"])["Carlow", "2026-05"] == may["supply_notices"] == 3
    assert sum(e.planned for e in events.values()) == may["planned"] == 1
    assert [e.investigation for e in events.values()].count(True) == 1


def test_letter_reads_the_site_cuts_unless_told_others():
    assert [letter(cut) for cut in SUPPLY_CUTS] == list("BCDEF")
    assert letter(5.5) == "D" and letter(5.5, (2, 3, 4, 5, 6)) == "E"


def test_an_investigation_pairs_with_an_outage_notice_near_it_in_place_and_time():
    events = {
        "inv": _event(investigation=True),
        "near": _event(lat=52.839, day=4),          # about 330 m north, 4 days on
        "far": _event(lat=52.846, day=1),           # about 1.1 km north
        "late": _event(day=6),
    }
    assert near_another(events, {"inv"}, {"near"}, 0.5, 5) == {"inv"}
    assert near_another(events, {"inv"}, {"far", "late"}, 0.5, 5) == set()


def test_an_event_is_not_its_own_neighbour():
    events = {"a": _event(), "b": _event(lat=53.5)}
    assert near_another(events, {"a", "b"}, {"a", "b"}, 0.2, 14) == set()


def test_a_month_outside_the_band_is_named():
    national = {"2026-05": 3.59, "2026-07": 5.51, "2026-12": 2.99}
    assert outside_band(national) == [("2026-07", 5.51), ("2026-12", 2.99)]
    assert outside_band({"2026-05": 3.0, "2026-06": 5.5}) == []
