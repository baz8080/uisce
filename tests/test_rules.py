"""The rules extractor: template coverage, and above all its abstentions.

The contract under test is rules.py's: extract() answers only when a known
template matches, and the only classes it may ever emit are completion_update
and scheduled_end_with_time. Everything surprising abstains — a wrong answer
here is worse than no answer, because abstention falls back to the LLM while
a wrong answer lands in the site's numbers.
"""

import pytest

from uisce.rules import RULES_VERSION, extract

START = "2026-07-01T10:00:00+00:00"

BOILERPLATE = (
    " We recommend that you allow 3-4 hours after the estimated restoration "
    "time for your supply to fully return. Please take note of the following "
    "reference number: GAL00111111. LA01"
)


def test_rules_version_is_stamped():
    assert RULES_VERSION == "rules-v1"


class TestCompletionUpdates:
    def test_header_with_completion_phrase(self):
        result = extract(START, "<b>**Update 10:15am 18/05/2026**</b> Works are now "
                                "complete and supply should have returned." + BOILERPLATE)
        assert result["end_source"] == "completion_update"
        assert result["local_date"] == "2026-05-18"
        assert result["local_time"] == "10:15"
        assert result["recurrence"] == "none"

    def test_completion_beats_stale_schedule_below(self):
        result = extract(START, "**Update 4:51pm 15/7/2026** Works are now complete. "
                                "Works are scheduled to take place until 2pm on 15 July.")
        assert result["end_source"] == "completion_update"
        assert (result["local_date"], result["local_time"]) == ("2026-07-15", "16:51")

    def test_header_without_minutes(self):
        result = extract(START, "**Update 9am 15/07/2026** Works are now complete.")
        assert (result["local_date"], result["local_time"]) == ("2026-07-15", "09:00")

    def test_header_missing_closing_stars(self):
        result = extract(START, "**Update 2:42pm 02/07/2026 Works are now complete.")
        assert (result["local_date"], result["local_time"]) == ("2026-07-02", "14:42")

    def test_header_with_on_before_date(self):
        result = extract(START, "**Update 9:37am on 13/07/2026** Works are now completed.")
        assert (result["local_date"], result["local_time"]) == ("2026-07-13", "09:37")

    def test_header_with_dot_time(self):
        result = extract(START, "**Update 10.15am 18/05/2026** Works are now complete.")
        assert result["local_time"] == "10:15"

    def test_irish_header_meridiems(self):
        # "rn" is AM, "in" is PM, glued to the digits, no "update" word.
        result = extract(START, "**4:15in 16/07/2026** Works are now complete.")
        assert (result["local_date"], result["local_time"]) == ("2026-07-16", "16:15")
        result = extract(START, "**9:05rn 16/07/2026** Works are now complete.")
        assert result["local_time"] == "09:05"

    def test_completion_in_older_block_still_wins(self):
        result = extract(START, "**Update 8am 16/07/2026** Crews remain on site. "
                                "**Update 4:51pm 15/7/2026** Works are now complete.")
        assert result["end_source"] == "completion_update"
        assert (result["local_date"], result["local_time"]) == ("2026-07-15", "16:51")

    def test_headerless_completion_abstains(self):
        assert extract(START, "Works are now complete at 4:13pm on 28/04/2026.") is None

    def test_header_without_time_abstains(self):
        assert extract(START, "**Update am 15/07/2026** Works are now complete.") is None


class TestScheduledEnds:
    def test_until_time_on_date(self):
        result = extract(START, "Repairs to a burst water main may cause supply "
                                "disruptions. Works are scheduled to take place until "
                                "2pm on 28 April." + BOILERPLATE)
        assert result["end_source"] == "scheduled_end_with_time"
        assert (result["local_date"], result["local_time"]) == ("2026-04-28", "14:00")

    def test_from_until_same_day(self):
        result = extract(START, "Works are scheduled to take place from 10am until "
                                "7pm on 09 May." + BOILERPLATE)
        assert (result["local_date"], result["local_time"]) == ("2026-05-09", "19:00")

    def test_overnight_continuous_period(self):
        result = extract(START, "Works are scheduled to take place from 8pm on 06 July "
                                "until 11pm on 07 July." + BOILERPLATE)
        assert (result["local_date"], result["local_time"]) == ("2026-07-07", "23:00")

    def test_estimated_completion_time(self):
        result = extract(START, "Works now have an estimated completion time of 5pm "
                                "on 15 July." + BOILERPLATE)
        assert (result["local_date"], result["local_time"]) == ("2026-07-15", "17:00")

    def test_time_words(self):
        result = extract(START, "Works are scheduled to take place until midday on 3 July.")
        assert result["local_time"] == "12:00"
        result = extract(START, "Works are scheduled to take place from 4pm until "
                                "midnight on 30 April.")
        assert (result["local_date"], result["local_time"]) == ("2026-04-30", "00:00")

    def test_24_hour_time(self):
        result = extract(START, "Works are scheduled to take place until 17:00 on 3 July.")
        assert result["local_time"] == "17:00"

    def test_unil_typo(self):
        result = extract(START, "Works are scheduled to take place unil 2pm on 28 April.")
        assert (result["local_date"], result["local_time"]) == ("2026-04-28", "14:00")

    def test_numeric_date(self):
        result = extract(START, "Works are scheduled to take place until 2pm on 28/04/2026.")
        assert result["local_date"] == "2026-04-28"

    def test_year_resolves_forward_across_new_year(self):
        result = extract("2026-12-28T10:00:00+00:00",
                         "Works are scheduled to take place until 2pm on 3 January.")
        assert result["local_date"] == "2027-01-03"

    def test_newest_update_block_owns_the_schedule(self):
        result = extract(START, "**Update 8am 10/07/2026** Works are extended until 9pm "
                                "on 10 July. **Update 7am 09/07/2026** Works are "
                                "scheduled to take place until 2pm on 09 July.")
        assert (result["local_date"], result["local_time"]) == ("2026-07-10", "21:00")

    def test_conflicting_schedules_in_one_block_abstain(self):
        # The original notice carries no header of its own, so a revising
        # update and the stale text below it share a segment; two different
        # ends there is ambiguity, and ambiguity is the model's job.
        assert extract(START, "**Update 8am 10/07/2026** Works are extended until 9pm "
                              "on 10 July. Works are scheduled to take place until "
                              "2pm on 09 July.") is None


class TestAbstentions:
    @pytest.mark.parametrize("description", [
        None,
        "",
        # no usable signal
        "We are investigating reports of supply disruptions. More information to follow.",
        # recurring windows are model territory (site.py:recurring_events)
        "Works are scheduled to take place nightly from 10pm until 7am, "
        "from 08 July until 17 August.",
        "Works are scheduled to take place daily from 9am until 6pm "
        "from 12 June until 15 June.",
        # enumerated day lists are the recurring form RECURRENCE_TEXT misses
        "Works are scheduled to take place until 5pm on 26 May and 27 May.",
        "Works are scheduled to take place from 9am until 5pm on 17 June, "
        "18 June and19 June.",  # feed writes "and19" with no space (case 236066)
        "Works are scheduled to take place from 9am until 5pm on 26 and 27 May.",
        # double "until": garbled at source (case 232976) or a date range the
        # model reads as recurring (case 240600)
        "Works are scheduled to take place until 6pm on 9 May until 9pm 13 May.",
        "Works are scheduled to take place from 8am until 5pm on 05 August "
        "until 07 August.",
        "A Boil Water Notice remains in place until further notice.",
        # lift wording is lifted_immediate territory
        "The Boil Water Notice which has been in place is now lifted with "
        "immediate effect.",
        # a date without its time must never become scheduled_end_date_only
        "Works are scheduled to take place until 28 April.",
        # an invalid date is a typo the model should read, not a rule
        "Works are scheduled to take place until 2pm on 31/09/2026.",
        # Irish-only completion: the English half below is stale
        "Meastar go mbeidh críoch leis an obair seo ag a 9in ar an 1ú Bealtaine. "
        "Works are scheduled to take place until 9pm on 1 May.",
        # two different schedules in one block
        "Works are scheduled to take place until 2pm on 28 April. Works are "
        "scheduled to take place until 5pm on 29 April.",
    ])
    def test_abstains(self, description):
        assert extract(START, description) is None

    def test_missing_start_date_abstains_when_year_is_needed(self):
        assert extract(None, "Works are scheduled to take place until 2pm on 28 April.") is None
        # ... but an explicit year needs no start_date to resolve
        result = extract(None, "Works are scheduled to take place until 2pm on 28/04/2026.")
        assert result["local_date"] == "2026-04-28"


# Shapes drawn from every template family above plus the known-hostile ones.
# Whatever these rules come to match in future versions, the only classes
# they may ever emit are the two below, with no window fields — emitting
# scheduled_end_date_only would silently shift ends to 23:59:59
# (build.py:reported_end_utc), and window values are the model's job.
GUARD_INPUTS = [
    "**Update 10:15am 18/05/2026** Works are now complete." + BOILERPLATE,
    "Works are scheduled to take place until 2pm on 28 April." + BOILERPLATE,
    "Works are scheduled to take place until 28 April.",
    "Works are scheduled to take place nightly from 10pm until 7am, "
    "from 08 July until 17 August.",
    "The notice has been lifted with immediate effect.",
    "We are investigating reports of supply disruptions.",
    "Due to elevated turbidity, a Boil Water Notice is issued with immediate "
    "effect until further notice.",
    "**Update 9am 2/06/2026** Works are now complete.",
    "Works now have an estimated completion time of 3pm on 29 May.",
]


class TestEmissionGuard:
    @pytest.mark.parametrize("description", GUARD_INPUTS)
    def test_only_two_classes_ever_emitted(self, description):
        result = extract(START, description)
        if result is None:
            return
        assert result["end_source"] in {"completion_update", "scheduled_end_with_time"}
        assert result["local_date"] and result["local_time"]
        assert result["recurrence"] == "none"
        assert result["window_open"] is None
        assert result["window_close"] is None
        assert result["window_first_date"] is None
        assert result["notes"].startswith("rules:")
